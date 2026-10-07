"""FastAPI app for the Technical Services Fault Diagnosis pill (spec §5).

Endpoints:
    POST   /cases                         create a case (trigger diagnosis)
    GET    /cases                          list case ids
    GET    /cases/{id}                     full state snapshot
    GET    /cases/{id}/evidence            evidence bundle
    GET    /cases/{id}/diagnosis           ranked diagnosis
    GET    /cases/{id}/recommendation      recommendation + guardrail result
    POST   /cases/{id}/approval            HITL approve/reject/modify  (manager)
    GET    /cases/{id}/work-order          work order id
    POST   /cases/{id}/outcome             record maintenance outcome  (technician)
    POST   /cases/{id}/feedback            submit feedback             (steward)
    GET    /audit/trace                    tamper-evident audit trail   (auditor)

Identity via a signed session cookie set by ``POST /login`` (see ``auth.py``);
``?user=<demo_user_id>`` is a fallback only under ``TBC_DEMO_INSECURE=1``.
RBAC capabilities are mapped per role in ``rbac.DEMO_USERS``.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response

from .agent_state import AgentState
from .ai_reasoning import generate_diagnostic_hypothesis
from .auth import check_pin, clear_cookie, demo_insecure, issue_cookie, resolve_user
from .models import (
    AgentStateName,
    HumanDecision,
    HumanDecisionRecord,
    Observation,
    Outcome,
    OutcomeResult,
    ReadingStatus,
    Recommendation,
)
from .rbac import DEMO_USERS, require
from .store import STORE

_log = logging.getLogger("tbc.persistence")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    from . import persistence

    persistent = os.environ.get("TBC_PERSIST", "1") != "0"
    if persistent:
        summary = persistence.load_state()
        _log.info("persistence restore: %s", summary)
        if summary.get("audit_chain_failures"):
            _log.error("invalid audit chains on restore: %s", summary["audit_chain_failures"])
    if not STORE.list() and os.environ.get("TBC_AUTO_SEED", "1") != "0":
        _log.info("empty store: seeded demo cases %s", seed_demo_cases())
        if persistent:
            persistence.save_state()
    try:
        yield
    finally:
        if persistent:
            persistence.save_state()


app = FastAPI(
    title="Technical Services Fault Diagnosis Pill",
    version="1.0.0",
    lifespan=_lifespan,
)


@app.middleware("http")
async def _snapshot_after_write(request, call_next):
    response = await call_next(request)
    if (
        os.environ.get("TBC_PERSIST", "1") != "0"
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and response.status_code < 400
    ):
        from . import persistence

        persistence.save_state()
    return response


# --- auth helper ----------------------------------------------------------
def _user(user_id: str):
    u = DEMO_USERS.get(user_id)
    if u is None:
        raise HTTPException(status_code=401, detail=f"unknown user {user_id!r}")
    return u


def _need(user_id: str, capability: str):
    u = _user(user_id)
    try:
        require(u.role, capability)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return u


def _get_case(case_id: str) -> AgentState:
    state = STORE.get(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return state


def _get_case_for_write(case_id: str) -> AgentState:
    """A case whose audit chain fails verification is frozen: it can be
    read and investigated, never advanced, approved or closed."""
    state = _get_case(case_id)
    if not state.verify_audit_chain():
        raise HTTPException(
            423, f"case {case_id} audit chain failed verification; frozen pending audit review")
    return state


def _asset_type(asset_id: str) -> str:
    """Asset type from the registry (e.g. "UPS"); "UNKNOWN" if unregistered."""
    from .mock_registry import ASSETS

    return ASSETS.get(asset_id, {}).get("type", "UNKNOWN")


def _fault_signature(state: AgentState, top_cause_id: str, kb_refs: list[str]) -> str:
    """Deterministic, asset-agnostic fault signature for KB retrieval.

    Delegates to ``tools.build_fault_signature`` so diagnosis time (here)
    and feedback time (``tools.submit_feedback``) build it identically —
    a validated case must match the next identical fault's query signature.
    """
    from .tools import build_fault_signature

    return build_fault_signature(state.observation.type, top_cause_id, kb_refs)


# ========================================================================== #
# Identity: a signed session cookie, not a spoofable ?user= param (see auth.py)
# ========================================================================== #
@app.post("/login")
def login(user_id: str, response: Response, pin: str | None = None) -> dict:
    """Check the user's PIN and set a signed session cookie for them.

    The top-bar role switcher calls this. Everything downstream reads the
    caller from the cookie, so logging in here is the only way to change
    who you act as. Naming a user is not enough: their PIN is required.
    """
    u = _user(user_id)
    if not check_pin(u.user_id, pin):
        raise HTTPException(401, f"wrong or missing PIN for {user_id}")
    issue_cookie(response, u.user_id)
    return {"user": u.user_id, "role": u.role.value}


@app.post("/logout")
def logout(response: Response) -> dict:
    clear_cookie(response)
    return {"status": "logged out"}


# ========================================================================== #
# Case lifecycle
# ========================================================================== #
@app.post("/cases")
def create_case(
    asset_id: str,
    sensor_id: str,
    user: str = Depends(resolve_user),
    observation_type: str = "temperature_measurement_missing",
    reading_status: str = "absent",
    raw_value: float | None = None,
) -> dict:
    """Trigger a diagnosis case. Gathers evidence + runs the decision tree.

    ``observation_type`` routes the case to a fault-specific causal tree
    (CRAH temp-missing / chiller / UPS / pump). Unknown types are rejected
    with 400 so an un-routable observation is never built. ``raw_value`` is
    required semantics for an INVALID reading (spec §4.2 Q1).
    """
    _need(user, "view_case")
    from .decision_tree import KNOWN_FAULT_TYPES

    if observation_type not in KNOWN_FAULT_TYPES:
        raise HTTPException(
            400,
            f"unknown observation_type {observation_type!r}; "
            f"expected one of {list(KNOWN_FAULT_TYPES)}",
        )
    try:
        rs = ReadingStatus(reading_status)
    except ValueError:
        raise HTTPException(400, f"invalid reading_status {reading_status!r}")
    state = _new_case(asset_id, sensor_id, observation_type, rs, raw_value, actor=user)
    return {"case_id": state.case_id, "current_state": state.current_state.value,
            "evidence_count": len(state.evidence)}


def _new_case(asset_id: str, sensor_id: str, observation_type: str,
              reading_status: ReadingStatus, raw_value: float | None = None,
              *, actor: str) -> AgentState:
    from .mock_registry import ASSETS
    from .models import GuardrailResult
    from .tools import gather_evidence_for_fault

    observation = Observation(
        type=observation_type,
        sensor_id=sensor_id,
        detected_at=datetime.now(timezone.utc),
        reading_status=reading_status,
        raw_value=raw_value,
        asset_id=asset_id,
    )
    registered = asset_id in ASSETS
    state = AgentState(asset_id=asset_id, observation=observation, actor=actor,
                       asset_registered=registered)
    if registered:
        for ev in gather_evidence_for_fault(asset_id, observation_type):
            state.add_evidence(ev, actor="agent")
    else:
        # G5: nothing is known about this asset, so nothing is gathered or
        # diagnosed; it escalates the moment it is raised.
        gr = GuardrailResult()
        gr.add("G5", "asset not in registry; cannot diagnose unknown asset",
               escalate=True, block=True)
        state.guardrail_result = gr
        state.escalate_for_evidence(actor="agent", reason="[G5] unknown asset; outside pill scope")
    STORE.create(state)
    return state


@app.get("/cases")
def list_cases(user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    return {"cases": STORE.list()}


@app.post("/cases/{case_id}/advance")
def advance_case(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Drive the agent loop to a terminal or waiting state in one call.

    Loops through GATHERING_EVIDENCE -> DIAGNOSING -> (RECOMMENDING |
    GATHERING_EVIDENCE | ESCALATED) until the state is no longer
    GATHERING_EVIDENCE. The state machine's ``_gathering_loops`` counter
    caps the loop at 2 iterations before forcing ESCALATED.

    When the case escalates via G4 (low confidence / max gathering loops)
    but a diagnosis with a top cause exists, guardrails are evaluated
    anyway so that G3 cross-domain escalation is surfaced with
    ``guardrail_result`` populated — the proximate cause of escalation is
    recorded, but the guardrail attribution is not lost.
    """
    _need(user, "view_case")
    state = _get_case_for_write(case_id)
    _advance(state)
    return {"case_id": case_id, "current_state": state.current_state.value,
            "confidence": state.confidence}


def _advance(state: AgentState) -> None:
    while state.current_state == AgentStateName.GATHERING_EVIDENCE:
        from .confidence import derive_confidence_signals, score_confidence, evidence_coverage_score
        from .decision_tree import evaluate_decision_tree, FAULT_BRANCH_COUNTS
        from .models import CandidateCause, Diagnosis, Recommendation

        # G5: an asset outside the registry is out of this pill's scope.
        # Escalate before diagnosing instead of stalling in GATHERING_EVIDENCE.
        from .mock_registry import ASSETS
        from .models import GuardrailResult

        if state.asset_id not in ASSETS:
            gr = GuardrailResult()
            gr.add("G5", "asset not in registry; cannot diagnose unknown asset",
                   escalate=True, block=True)
            state.guardrail_result = gr
            state.escalate_for_evidence(
                actor="agent", reason="[G5] unknown asset; outside pill scope")
            break

        try:
            state.begin_diagnosing(actor="agent")
        except ValueError as exc:
            # Evidence can never reach the minimum: escalate, never stall.
            state.escalate_for_evidence(actor="agent", reason=str(exc))
            break
        results = evaluate_decision_tree(state.observation, state.evidence)
        if not results:
            from .models import CandidateCause, Diagnosis

            unknown = CandidateCause(
                id="unresolvable", label="No candidate cause resolved",
                likelihood=0.0, evidence_refs=[],
            )
            diag = Diagnosis(
                candidate_causes=[unknown], top_cause_id="unresolvable",
                reasoning_trace="decision tree returned no candidate cause",
                kb_refs=[],
            )
            state.complete_diagnosis(diag, 0.0, actor="agent")
            break

        top = results[0]
        candidates = [
            CandidateCause(id=r.cause_id, label=r.cause_label,
                           likelihood=0.9 if r is top else 0.3,
                           evidence_refs=r.kb_refs)
            for r in results
        ]
        diag = Diagnosis(
            candidate_causes=candidates, top_cause_id=top.cause_id,
            reasoning_trace=f"decision tree -> {top.cause_id}",
            kb_refs=top.kb_refs,
        )
        coverage = evidence_coverage_score(
            state.evidence,
            FAULT_BRANCH_COUNTS.get(state.observation.type, 6),
        )
        sig = _fault_signature(state, top.cause_id, top.kb_refs)
        from .learning import STORE as _LSTORE

        kb_match = _LSTORE.kb_match_score(sig, top.cause_id, _asset_type(state.asset_id))
        signals = derive_confidence_signals(
            state.evidence, asset_id=state.asset_id, sensor_id=state.observation.sensor_id,
        )
        conf = score_confidence(
            evidence_coverage=coverage,
            peer_agreement=signals["peer_agreement"],
            kb_match=kb_match,
            data_staleness=signals["data_staleness"],
            conflict_penalty=signals["conflict_penalty"],
        )
        breakdown = {
            "evidence_coverage": coverage,
            "peer_agreement": signals["peer_agreement"],
            "kb_match": kb_match,
            "data_staleness": signals["data_staleness"],
            "conflict_penalty": signals["conflict_penalty"],
            "kb_version_label": _LSTORE.get_kb_version_label(),
        }
        hypothesis = generate_diagnostic_hypothesis(
            asset={"asset_id": state.asset_id, "asset_type": _asset_type(state.asset_id)},
            observations={
                "type": state.observation.type,
                "sensor_id": state.observation.sensor_id,
                "reading_status": state.observation.reading_status.value,
            },
            evidence=[
                {
                    "source": ev.source, "finding": ev.type, "summary": str(ev.payload),
                    "conflict": isinstance(ev.payload, dict) and ev.payload.get("conflict") is True,
                }
                for ev in state.evidence
            ],
            candidate_causes=[r.cause_id for r in results],
            rule_top_cause=top.cause_id,
            knowledge=[{"cause": top.cause_id, "kb_ref": ref} for ref in top.kb_refs],
        )
        state.record_ai_second_opinion(hypothesis, actor="agent")
        new_st = state.complete_diagnosis(diag, conf, actor="agent", confidence_breakdown=breakdown)
        if new_st == AgentStateName.RECOMMENDING:
            rec = Recommendation(
                actions=[top.action], kb_refs=top.kb_refs,
                evidence_refs=[e.type for e in state.evidence],
            )
            state.propose_recommendation(rec, actor="agent")
            break
        if new_st == AgentStateName.GATHERING_EVIDENCE:
            # Low confidence: actually re-query the evidence sources. If they
            # return nothing new, another pass would only re-run the same
            # data, so hand the case to a human instead.
            from .tools import gather_evidence_for_fault

            seen = {(e.source, e.type, repr(e.payload)) for e in state.evidence}
            fresh = [ev for ev in gather_evidence_for_fault(state.asset_id, state.observation.type)
                     if (ev.source, ev.type, repr(ev.payload)) not in seen]
            if not fresh:
                state.escalate_for_evidence(
                    actor="agent",
                    reason=(f"confidence {conf:.2f} is below the recommendation threshold and "
                            "re-querying every evidence source returned nothing new; "
                            "needs a human"),
                )
                break
            for ev in fresh:
                state.add_evidence(ev, actor="agent")

    # If the case escalated via G4 (low confidence / max gathering loops)
    # but a diagnosis with a resolvable top cause exists, evaluate
    # guardrails anyway so G3 cross-domain escalation is surfaced with
    # guardrail_result populated (spec §4.4 edge case E5).
    if (
        state.current_state == AgentStateName.ESCALATED
        and state.guardrail_result is None
        and state.diagnosis
        and state.diagnosis.top_cause_id
        and state.diagnosis.top_cause_id != "unresolvable"
    ):
        from .guardrails import SAFETY_CRITICAL_CAUSE_IDS, check_guardrails
        from .models import GuardrailContext, Recommendation

        top_label = None
        for c in state.diagnosis.candidate_causes:
            if c.id == state.diagnosis.top_cause_id:
                top_label = c.label
                break
        ctx = GuardrailContext(asset_known=True)
        if state.diagnosis.top_cause_id in SAFETY_CRITICAL_CAUSE_IDS:
            ctx = ctx.model_copy(update={"safety_critical": True})
        rec = Recommendation(
            actions=[],
            kb_refs=list(state.diagnosis.kb_refs or []),
            evidence_refs=[e.type for e in state.evidence],
        )
        gr = check_guardrails(
            rec, ctx, confidence=state.confidence, top_cause_label=top_label,
        )
        if gr.must_escalate or not gr.allowed:
            state.guardrail_result = gr
            state.recommendation = rec
            state._record_note(
                actor="agent",
                reason="guardrail review of the escalated case: " + "; ".join(gr.reasons),
            )

    # G9: surface an AI/rules disagreement, if any, on whatever guardrail
    # result exists by now. Advisory only — never changes current_state.
    if state.guardrail_result is not None:
        from .guardrails import flag_ai_disagreement

        flag_ai_disagreement(
            state.guardrail_result,
            ai_hypothesis=state.ai_hypothesis,
            rule_cause=state.diagnosis.top_cause_id if state.diagnosis else None,
        )


@app.get("/cases/similar")
def list_similar_cases(
    cause: str, asset_type: str | None = None, user: str = Depends(resolve_user),
) -> dict:
    """Open (not CLOSED) cases currently diagnosed with ``cause`` — the
    candidates a steward can re-score after approving a proposal for that
    cause.

    Registered before ``/cases/{case_id}`` below: a literal path must be
    declared ahead of a param route with the same shape, or the param
    route shadows it and every call here 404s as case_id="similar".
    """
    _need(user, "view_case")
    matches = []
    for case_id in STORE.list():
        state = STORE.get(case_id)
        if state is None or state.current_state == AgentStateName.CLOSED:
            continue
        if not state.diagnosis or state.diagnosis.top_cause_id != cause:
            continue
        if asset_type and _asset_type(state.asset_id) != asset_type:
            continue
        matches.append({
            "case_id": case_id, "asset_id": state.asset_id,
            "current_state": state.current_state.value, "confidence": state.confidence,
        })
    return {"matches": matches}


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    snap = STORE.snapshot(case_id)
    if snap is None:
        raise HTTPException(404, "case not found")
    snap["asset_type"] = _asset_type(snap["asset_id"])
    return snap


@app.get("/cases/{case_id}/evidence")
def get_evidence(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"evidence": [e.model_dump(mode="json") for e in state.evidence]}


@app.get("/cases/{case_id}/diagnosis")
def get_diagnosis(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    diag = state.diagnosis
    return {"diagnosis": diag.model_dump(mode="json") if diag else None,
            "confidence": state.confidence}


@app.get("/cases/{case_id}/recommendation")
def get_recommendation(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    rec = state.recommendation
    gr = state.guardrail_result
    return {"recommendation": rec.model_dump(mode="json") if rec else None,
            "guardrail_result": gr.model_dump(mode="json") if gr else None,
            "guardrail_route_explanation": _route_explanation(state)}


@app.get("/cases/{case_id}/confidence-preview")
def preview_confidence(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Non-destructive: re-score this case's EXISTING evidence against the
    CURRENT KB and registry, without mutating the case.

    Lets Governance show a steward the before/after effect a just-approved
    proposal has on a similar still-open case ("Re-run diagnosis on similar
    open cases"). Nothing here changes ``current_state`` or ``confidence``
    on the stored case -- it's a preview, not a re-diagnosis.
    """
    _need(user, "view_case")
    state = _get_case(case_id)
    if not state.diagnosis or not state.diagnosis.top_cause_id or state.diagnosis.top_cause_id == "unresolvable":
        raise HTTPException(409, "case has no resolvable diagnosis to re-score")

    from .confidence import derive_confidence_signals, evidence_coverage_score, score_confidence
    from .decision_tree import FAULT_BRANCH_COUNTS
    from .learning import STORE as _LSTORE

    coverage = evidence_coverage_score(
        state.evidence, FAULT_BRANCH_COUNTS.get(state.observation.type, 6),
    )
    sig = _fault_signature(state, state.diagnosis.top_cause_id, state.diagnosis.kb_refs)
    kb_match = _LSTORE.kb_match_score(sig, state.diagnosis.top_cause_id, _asset_type(state.asset_id))
    signals = derive_confidence_signals(
        state.evidence, asset_id=state.asset_id, sensor_id=state.observation.sensor_id,
    )
    after = score_confidence(
        evidence_coverage=coverage,
        peer_agreement=signals["peer_agreement"],
        kb_match=kb_match,
        data_staleness=signals["data_staleness"],
        conflict_penalty=signals["conflict_penalty"],
    )
    return {
        "case_id": case_id,
        "before": state.confidence,
        "after": after,
        "delta": after - state.confidence,
        "breakdown": {
            "evidence_coverage": coverage,
            "peer_agreement": signals["peer_agreement"],
            "kb_match": kb_match,
            "data_staleness": signals["data_staleness"],
            "conflict_penalty": signals["conflict_penalty"],
            "kb_version_label": _LSTORE.get_kb_version_label(),
        },
    }


@app.post("/cases/{case_id}/approval")
def post_approval(
    case_id: str,
    decision: str,
    user: str = Depends(resolve_user),
    rationale: str | None = None,
    modified_action_type: str | None = None,
    modified_action_target: str | None = None,
    modified_action_detail: str | None = None,
    hazard_acknowledged: bool = False,
) -> dict:
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    try:
        dec = HumanDecision(decision)
    except ValueError:
        raise HTTPException(400, f"invalid decision {decision!r}")
    if not (rationale or "").strip():
        raise HTTPException(400, f"a rationale is required to {dec.value}")
    hazard = state.guardrail_result is not None and any(
        r.startswith(("[G2]", "[G2b]")) for r in state.guardrail_result.reasons)
    if hazard and dec != HumanDecision.REJECT and not hazard_acknowledged:
        raise HTTPException(
            400, "this recommendation carries a safety/environmental hazard; "
                 "acknowledge it (hazard_acknowledged=true) before approving or modifying")

    if hazard and dec != HumanDecision.REJECT:
        rationale = f"{rationale.strip()} [safety hazard acknowledged]"

    modified_actions = None
    original_actions = None
    if dec == HumanDecision.MODIFY:
        if not (modified_action_type and modified_action_target):
            raise HTTPException(
                400,
                "modify requires modified_action_type and modified_action_target",
            )
        from .models import RecommendationAction

        modified_actions = [
            RecommendationAction(
                type=modified_action_type,
                target=modified_action_target,
                detail=modified_action_detail or "",
                kb_refs=list(state.recommendation.actions[0].kb_refs)
                if state.recommendation and state.recommendation.actions
                else [],
            )
        ]
        if state.recommendation and state.recommendation.actions:
            original_actions = list(state.recommendation.actions)

    from pydantic import ValidationError as PydanticValidationError

    try:
        hd = HumanDecisionRecord(
            decision=dec, decided_by=user, rationale=rationale,
            modified_actions=modified_actions,
            original_actions=original_actions,
        )
        state.record_human_decision(hd, actor=user)
    except PydanticValidationError as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if dec == HumanDecision.MODIFY:
        # apply the manager's modified action set while preserving G8
        # grounding metadata (kb_refs / evidence_refs) from the original
        # recommendation so the audit trail stays fully grounded.
        orig = state.recommendation
        state.recommendation = Recommendation(
            actions=modified_actions or [],
            kb_refs=list(orig.kb_refs) if orig and orig.kb_refs else [],
            evidence_refs=list(orig.evidence_refs) if orig and orig.evidence_refs else [],
        )
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.get("/cases/{case_id}/work-order")
def get_work_order(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"work_order_id": state.work_order_id}


@app.post("/cases/{case_id}/work-order")
def create_work_order(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Raise + acknowledge the CMMS work order (EXECUTING -> MONITORING_OUTCOME).

    Spec §3 guardrail: refused unless an approve/modify decision is recorded.
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    if not state.recommendation or not state.recommendation.actions:
        raise HTTPException(409, "no recommendation to action")
    from .tools import create_work_order_for_state
    try:
        wo_id = create_work_order_for_state(state, state.recommendation.actions[0])
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"case_id": case_id, "work_order_id": wo_id,
            "current_state": state.current_state.value}


@app.post("/cases/{case_id}/outcome")
def post_outcome(
    case_id: str,
    result: str,
    user: str = Depends(resolve_user),
    root_cause_confirmed: str | None = None,
    notes: str | None = None,
) -> dict:
    _need(user, "record_outcome")
    state = _get_case_for_write(case_id)
    try:
        res = OutcomeResult(result)
    except ValueError:
        raise HTTPException(400, f"invalid result {result!r}")
    # Validate root_cause_confirmed against the diagnosed cause universe so
    # free-text typos cannot flow into the KB via the feedback loop (spec §7).
    # None/blank stays allowed (outcome recorded without cause confirmation).
    from .decision_tree import KNOWN_CAUSE_IDS

    if root_cause_confirmed and root_cause_confirmed.strip():
        rcc = root_cause_confirmed.strip()
        if rcc not in KNOWN_CAUSE_IDS:
            raise HTTPException(
                400,
                f"unknown root_cause_confirmed {rcc!r}; expected one of "
                f"{sorted(KNOWN_CAUSE_IDS)} (or omit)",
            )
    outcome = Outcome(
        result=res, root_cause_confirmed=root_cause_confirmed,
        verified_by=user, notes=notes,
    )
    try:
        state.record_outcome(outcome)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.post("/cases/{case_id}/feedback")
def post_feedback(
    case_id: str,
    user: str = Depends(resolve_user),
    corrections: dict | None = None,
) -> dict:
    _need(user, "submit_feedback")
    state = _get_case_for_write(case_id)
    from .cause_registry import canonicalize_cause_id, cause_asset_type
    from .decision_tree import KNOWN_CAUSE_IDS
    from .tools import submit_feedback as _fb

    # Every check runs before a proposal exists: a rejected request must
    # leave nothing behind in the governance queue.
    if state.current_state != AgentStateName.FEEDBACK_QUEUED or state.outcome is None:
        raise HTTPException(
            409,
            f"feedback is only accepted once an outcome is recorded and before the "
            f"case closes (case is {state.current_state.value})",
        )
    supplied = corrections or {}
    raw_cause = (supplied.get("confirmed_cause") or "").strip()
    if not raw_cause:
        raw_cause = (state.outcome.root_cause_confirmed or "").strip()
    if not raw_cause and state.diagnosis:
        raw_cause = state.diagnosis.top_cause_id or ""
    confirmed = canonicalize_cause_id(raw_cause) if raw_cause else None
    if not confirmed or confirmed not in KNOWN_CAUSE_IDS:
        raise HTTPException(400, f"unknown confirmed_cause {raw_cause!r}")
    case_asset_type = _asset_type(state.asset_id)
    if cause_asset_type(confirmed) != case_asset_type:
        raise HTTPException(
            400,
            f"cause {confirmed!r} belongs to the {cause_asset_type(confirmed)} pill, "
            f"not this {case_asset_type} case",
        )
    # Only the cause and notes come from the client. Asset type and fault
    # signature are derived from the case itself, the outcome from the
    # recorded outcome, and the proposer is always the authenticated caller.
    clean = {
        "confirmed_cause": confirmed,
        "notes": str(supplied.get("notes") or "")[:2000],
        "outcome": state.outcome.result.value,
        "submitted_by": user,
    }
    fb_id = _fb(case_id, clean, state=state)
    state.queue_feedback(fb_id, actor=user)
    from .learning import STORE as _LSTORE
    stats = _LSTORE.stats()
    return {"case_id": case_id, "feedback_id": fb_id,
            "current_state": state.current_state.value,
            "proposal_status": "pending",
            "kb_cases_total": stats["total_validated_cases"],
            "kb_feedback_added": stats["feedback_added"],
            "pending_proposals": stats["pending_proposals"]}


# --------------------------------------------------------------------------- #
# Expert knowledge capture (LLM drafts, steward approves)
# --------------------------------------------------------------------------- #
from pydantic import BaseModel as _BaseModel, Field as _Field


class CaptureInterviewRequest(_BaseModel):
    expert_name: str = _Field(min_length=1, max_length=120)
    expert_role: str = _Field(min_length=1, max_length=120)
    asset_type: str = _Field(min_length=1, max_length=40)
    transcript: str = _Field(min_length=1)
    # Optional: the heuristics the capturer kept after reviewing a draft from
    # /capture/draft. They are re-grounded against the transcript server-side.
    heuristics: list[dict] | None = None
    provider: str | None = None


class CaptureDraftRequest(_BaseModel):
    asset_type: str = _Field(min_length=1, max_length=40)
    transcript: str = _Field(min_length=1)


@app.get("/causes")
def get_causes(user: str = Depends(resolve_user), asset_type: str | None = None) -> dict:
    """Canonical causes with plain-English labels and owning asset type."""
    _need(user, "view_case")
    from .cause_registry import list_causes
    causes = list_causes()
    if asset_type:
        causes = [c for c in causes if c["asset_type"] == asset_type]
    return {"causes": causes}


# Which knowledge steward owns review for each pill (spec §7 governance).
# A registry-level assignment, not sourced from any HR/roster system --
# the two stewards this demo seeds (steward1, steward2) split the four
# pills so the "second steward must approve" rule has a concrete owner
# to name per pill.
PILL_OWNERS: dict[str, str] = {
    "CRAH": "steward1",
    "Chiller": "steward2",
    "UPS": "steward1",
    "Pump": "steward2",
}


@app.get("/pills")
def list_pills(user: str = Depends(resolve_user)) -> dict:
    """Registry of the four Intelligence Pills this deployment covers.

    All four currently share one knowledge base (there is a single
    LearningStore, not one per pill), so kb_version_label is the same
    for every row -- that is the real, current architecture, not a
    per-pill version this repo doesn't actually track.
    """
    _need(user, "view_case")
    from .learning import STORE as _LSTORE

    all_proposals = _LSTORE.list_all_proposals()
    pills = []
    for asset_type, owner in PILL_OWNERS.items():
        knowledge_count = sum(1 for vc in _LSTORE.validated if vc.asset_type == asset_type)
        knowledge_count += sum(1 for h in _LSTORE.expert_heuristics if h.get("asset_type") == asset_type)
        relevant = [p for p in all_proposals if p.get("asset_type") == asset_type]
        decided = [p for p in relevant if p.get("status") in ("approved", "rejected")]
        approved = [p for p in decided if p.get("status") == "approved"]
        pills.append({
            "asset_type": asset_type,
            "owner_steward": owner,
            "kb_version_label": _LSTORE.get_kb_version_label(),
            "knowledge_count": knowledge_count,
            "proposals_submitted": len(relevant),
            "proposals_decided": len(decided),
            "proposals_pending": sum(1 for p in relevant if p.get("status") == "pending"),
            "proposals_approved": len(approved),
            "approval_rate": round(len(approved) / len(decided), 3) if decided else None,
        })
    return {"pills": pills}


@app.get("/system/info")
def get_system_info(user: str = Depends(resolve_user)) -> dict:
    """Which model drafts expert knowledge, for the UI badge. Never returns secrets."""
    _need(user, "view_case")
    from . import llm
    provider = llm.provider_name()
    return {
        "llm_provider": provider,
        "llm_label": "Tencent Cloud ADP" if provider == "adp" else "Offline mock model",
        "adp_configured": llm.adp_configured(),
        "diagnosis": "deterministic decision tree",
        "demo_insecure": demo_insecure(),
    }


@app.get("/capture/sample")
def get_capture_sample(user: str = Depends(resolve_user)) -> dict:
    """A sample technician interview for the demo."""
    _need(user, "view_case")
    from .capture import SAMPLE_INTERVIEW
    return {"expert_name": "R. Tan", "expert_role": "Senior M&E Technician, 22 years",
            "asset_type": "CRAH", "transcript": SAMPLE_INTERVIEW}


@app.post("/capture/interview")
def post_capture_interview(body: CaptureInterviewRequest, user: str = Depends(resolve_user)) -> dict:
    """Turn an expert interview into a pending knowledge proposal.

    The LLM drafts structured heuristics; capture.py drops anything not
    quoted verbatim from the transcript; the result is queued for a
    different knowledge steward to approve. Nothing enters the KB here.
    """
    _need(user, "capture_expert_knowledge")
    from . import capture, llm
    from .learning import STORE as _LSTORE
    from .tools import _log

    try:
        if body.heuristics is not None:
            draft = capture.reviewed_draft(
                body.transcript, body.asset_type, body.heuristics,
                body.provider or llm.provider_name(),
            )
        else:
            draft = capture.draft_from_transcript(body.transcript, body.asset_type)
    except capture.CaptureError as exc:
        raise HTTPException(422, str(exc))
    except llm.LLMError as exc:
        raise HTTPException(502, f"knowledge extraction failed: {exc}")

    proposal = _LSTORE.record_expert_capture(
        draft=draft, submitted_by=user, expert_name=body.expert_name,
        expert_role=body.expert_role, asset_type=body.asset_type,
    )
    _log("capture_expert_knowledge",
         {"expert": body.expert_name, "asset_type": body.asset_type,
          "provider": draft["provider"], "submitted_by": user},
         proposal)
    return {"proposal_id": proposal["proposal_id"], "status": "pending",
            "provider": draft["provider"], "heuristics": draft["heuristics"],
            "warnings": draft["warnings"], "dropped": draft["dropped"]}


@app.post("/capture/draft")
def post_capture_draft(body: CaptureDraftRequest, user: str = Depends(resolve_user)) -> dict:
    """Draft heuristics for review WITHOUT queuing anything.

    The capturer reviews the draft (drop items, correct a cause) and then
    submits it to /capture/interview with ``heuristics`` set.
    """
    _need(user, "capture_expert_knowledge")
    from . import capture, llm
    try:
        draft = capture.draft_from_transcript(body.transcript, body.asset_type)
    except capture.CaptureError as exc:
        raise HTTPException(422, str(exc))
    except llm.LLMError as exc:
        raise HTTPException(502, f"knowledge extraction failed: {exc}")
    return {"status": "draft", **draft}


@app.get("/kb/expert-heuristics")
def get_expert_heuristics(user: str = Depends(resolve_user)) -> dict:
    """Approved, live expert heuristics with provenance."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return {"heuristics": _LSTORE.expert_heuristics}


@app.get("/cases/{case_id}/expert-knowledge")
def get_case_expert_knowledge(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Return approved expert heuristics matching this diagnosis and asset."""
    _need(user, "view_case")
    state = _get_case(case_id)
    from .cause_registry import canonicalize_cause_id
    from .learning import STORE as _LSTORE, kb_version_label

    diagnosis = state.diagnosis
    cause_id = canonicalize_cause_id(diagnosis.top_cause_id) if diagnosis else None
    asset_type = _asset_type(state.asset_id)
    matches = []
    if cause_id and cause_id != "unresolvable":
        matches = [
            {
                "knowledge_id": item["id"],
                "expert_name": item["expert_name"],
                "expert_role": item["expert_role"],
                "asset_type": item["asset_type"],
                "likely_cause": item["likely_cause"],
                "symptom_pattern": item["symptom_pattern"],
                "checks": item.get("checks", []),
                "do_not": item.get("do_not", []),
                "escalate_when": item.get("escalate_when", []),
                "evidence_quote": item["evidence_quote"],
                "kb_version": item["kb_version"],
                "kb_version_label": kb_version_label(item["kb_version"]),
                "approved_by": item["approved_by"],
            }
            for item in _LSTORE.expert_heuristics
            if canonicalize_cause_id(item["likely_cause"]) == cause_id
            and item["asset_type"] == asset_type
        ]
    return {
        "matches": matches,
        "match_basis": "exact asset type and diagnosed cause",
        "asset_type": asset_type,
        "cause_id": cause_id,
        "kb_version": _LSTORE.get_kb_version_label(),
    }


@app.get("/kb/stats")
def get_kb_stats(user: str = Depends(resolve_user)) -> dict:
    """Knowledge-base learning stats: validated cases, cause priors."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return _LSTORE.stats()


@app.get("/kb/queue")
def get_kb_queue(user: str = Depends(resolve_user)) -> dict:
    """List pending knowledge proposals awaiting steward approval (F2).

    Requires ``approve_knowledge_version`` capability (knowledge steward
    or admin). Returns the list of pending proposals with their metadata.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    pending = _LSTORE.list_pending_proposals()
    return {"queue": pending, "pending_count": len(pending)}


@app.post("/kb/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, user: str = Depends(resolve_user)) -> dict:
    """Approve a pending knowledge proposal and ingest it into the live KB (F2).

    Requires ``approve_knowledge_version`` capability. On approval the KB
    version increments and the proposal's feedback is promoted to a
    ValidatedCase retrievable by future diagnoses.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE, SelfApprovalError
    try:
        proposal = _LSTORE.approve_proposal(proposal_id, decided_by=user)
    except SelfApprovalError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"proposal_id": proposal_id, "status": "approved",
            "decided_by": user, "kb_version": _LSTORE.get_kb_version(),
            "validated_case_id": proposal.get("validated_case_id")}


@app.post("/kb/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, reason: str, user: str = Depends(resolve_user)) -> dict:
    """Reject a pending knowledge proposal (F2).

    Requires ``approve_knowledge_version`` capability. The rejected
    proposal is retained in the audit trail but never ingested into the KB.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    try:
        proposal = _LSTORE.reject_proposal(proposal_id, decided_by=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"proposal_id": proposal_id, "status": "rejected",
            "decided_by": user, "reason": reason}


@app.get("/kb/versions")
def list_kb_versions(user: str = Depends(resolve_user)) -> dict:
    """Addressable KB versions, each with the raw int `/kb/rollback/{N}`
    takes AND the semver label every screen displays (e.g. version 1 ->
    "1.4.0") -- so a UI control can roll back to what's actually on
    screen instead of making someone guess the mapping.
    """
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return {
        "current_version": _LSTORE.get_kb_version(),
        "current_label": _LSTORE.get_kb_version_label(),
        "versions": [
            {"version": v["version"], "label": v["label"], "status": v["status"],
             "proposal_id": v["proposal_id"], "created_by": v["created_by"]}
            for v in _LSTORE.list_versions()
        ],
    }


@app.post("/kb/rollback/{target_version}")
def rollback_kb(target_version: int, reason: str = "", user: str = Depends(resolve_user)) -> dict:
    """Roll the KB back to an earlier live version (admin only, reason required).

    Removes knowledge added after it and records the rollback, its actor
    and reason in the keyed governance ledger.
    """
    _need(user, "rollback_knowledge_version")
    from .learning import STORE as _LSTORE
    if not reason.strip():
        raise HTTPException(400, "a rollback needs a reason")
    try:
        return _LSTORE.rollback(target_version, actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/kb/ledger")
def get_kb_ledger(user: str = Depends(resolve_user)) -> dict:
    """The keyed, hash-chained governance ledger: every proposal submitted,
    approved or rejected and every rollback, with actor and reason."""
    _need(user, "read_audit_trail")
    from .learning import STORE as _LSTORE, kb_version_label
    entries = [{**e, "label_before": kb_version_label(e["version_before"]),
                "label_after": kb_version_label(e["version_after"])} for e in _LSTORE.ledger]
    return {"entries": entries, "chain_valid": _LSTORE.verify_ledger()}


SEED_ACTOR = "demo-seed"


def seed_demo_cases() -> list[str]:
    """Create the three demo scenarios: one CLOSED, one ESCALATED, one
    AWAITING_APPROVAL. Every step is attributed to ``demo-seed``, never to
    a real user, so the audit trail does not claim a manager approved it.
    """
    from .tools import create_work_order_for_state, submit_feedback

    closed = _new_case("CRAH-DC1-01", "SA-TEMP-01", "temperature_measurement_missing",
                       ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(closed)
    closed.record_human_decision(HumanDecisionRecord(
        decision=HumanDecision.APPROVE, decided_by=SEED_ACTOR,
        rationale="seeded demo scenario (not a real approval)",
    ), actor=SEED_ACTOR)
    create_work_order_for_state(closed, closed.recommendation.actions[0])
    closed.record_outcome(Outcome(
        result=OutcomeResult.RESOLVED, root_cause_confirmed="sensor_hardware_failure",
        verified_by=SEED_ACTOR, notes="seeded: sensor replaced, temperature restored",
    ))
    fb_id = submit_feedback(closed.case_id, {
        "confirmed_cause": "sensor_hardware_failure", "outcome": "resolved",
        "submitted_by": SEED_ACTOR,
    }, state=closed)
    closed.queue_feedback(fb_id, actor=SEED_ACTOR)

    escalated = _new_case("CRAH-DC1-02", "SA-TEMP-02", "temperature_measurement_missing",
                          ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(escalated)

    awaiting = _new_case("CHILLER-DC1-01", "CH-COMP-PRESSURE", "chiller_compressor_trip",
                         ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(awaiting)
    return [closed.case_id, escalated.case_id, awaiting.case_id]


@app.post("/demo/seed")
def post_demo_seed(user: str = Depends(resolve_user)) -> dict:
    """Admin only: add the three demo scenarios, attributed to demo-seed."""
    from .rbac import Role

    if _user(user).role != Role.ADMIN:
        raise HTTPException(403, "seeding demo cases is limited to the admin role")
    return {"seeded": seed_demo_cases(), "actor": SEED_ACTOR}


@app.get("/audit/status")
def get_audit_status(user: str = Depends(resolve_user)) -> dict:
    """Integrity summary for the dashboard banner: any case chain or the
    governance ledger failing verification. Visible to every role."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    broken = [cid for cid in STORE.list()
              if (st := STORE.get(cid)) is not None and not st.verify_audit_chain()]
    return {"broken_cases": broken, "ledger_valid": _LSTORE.verify_ledger(),
            "ok": not broken and _LSTORE.verify_ledger()}


@app.post("/cases/{case_id}/escalation/close")
def close_escalation(
    case_id: str, reason: str, user: str = Depends(resolve_user),
    confirmed_cause: str | None = None,
) -> dict:
    """Close an escalated case (ESCALATED -> CLOSED) with the resolution.

    ``reason`` (the resolution) is required. If ``confirmed_cause`` is
    given, the resolution is also queued as a knowledge proposal for a
    knowledge steward, so what the expert worked out is not lost.
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    if not reason.strip():
        raise HTTPException(400, "closing an escalation needs the resolution")
    confirmed = None
    if confirmed_cause:
        from .cause_registry import canonicalize_cause_id, cause_asset_type
        from .decision_tree import KNOWN_CAUSE_IDS

        confirmed = canonicalize_cause_id(confirmed_cause.strip())
        if confirmed not in KNOWN_CAUSE_IDS:
            raise HTTPException(400, f"unknown confirmed_cause {confirmed_cause!r}")
        if cause_asset_type(confirmed) != _asset_type(state.asset_id):
            raise HTTPException(400, f"cause {confirmed!r} does not belong to this asset type")
    try:
        state.close_escalation(actor=user, reason=f"escalation resolved by {user}: {reason.strip()}")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    proposal_id = None
    if confirmed:
        from .learning import STORE as _LSTORE
        from .tools import build_fault_signature

        diag = state.diagnosis
        proposal = _LSTORE.record_escalation_resolution(
            case_id=case_id, asset_id=state.asset_id, asset_type=_asset_type(state.asset_id),
            confirmed_cause=confirmed,
            proposed_cause=diag.top_cause_id if diag and diag.top_cause_id != "unresolvable" else None,
            fault_signature=build_fault_signature(
                state.observation.type, confirmed, diag.kb_refs if diag else []),
            resolution=reason.strip(), confidence=state.confidence, submitted_by=user,
        )
        proposal_id = proposal["proposal_id"]
    return {"case_id": case_id, "current_state": state.current_state.value,
            "knowledge_proposal_id": proposal_id}


@app.post("/cases/{case_id}/escalation/evidence")
def request_more_evidence(case_id: str, reason: str, user: str = Depends(resolve_user)) -> dict:
    """Request more evidence on an escalated case (ESCALATED -> GATHERING_EVIDENCE).

    The only HTTP re-entry path from ESCALATED back into the diagnosis loop
    (spec §2 transition table). An expert who needs additional sensor data
    or telemetry calls this to send the case back to evidence gathering.
    ``reason`` is REQUIRED for auditability. Requires ``approve_reject_modify``
    capability (expert/manager role).
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    try:
        state.request_more_evidence(actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.get("/audit/trace")
def get_audit_trace(
    user: str = Depends(resolve_user),
    actor: str | None = None,
    case_id: str | None = None,
) -> dict:
    _need(user, "read_audit_trail")
    return {"entries": STORE.all_audit_traces(actor=actor, case_id=case_id)}


# --- helpers ---------------------------------------------------------------
def _route_explanation(state: AgentState) -> str:
    gr = state.guardrail_result
    if gr is None:
        return "no guardrail run yet"
    if gr.must_escalate or not gr.allowed:
        return "escalated: " + "; ".join(gr.reasons)
    if gr.requires_approval:
        return "awaiting human approval (G6)"
    return "allowed"