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
from .auth import clear_cookie, demo_insecure, issue_cookie, resolve_user
from .capture import capture_expert_knowledge
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
def login(user_id: str, response: Response) -> dict:
    """Set a signed session cookie for one of the fixed demo users.

    The top-bar role switcher calls this. Everything downstream reads the
    caller from the cookie, so switching role here is the only way to
    change who you act as — appending ``?user=`` to a URL no longer does.
    """
    u = _user(user_id)
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

    observation = Observation(
        type=observation_type,
        sensor_id=sensor_id,
        detected_at=datetime.now(timezone.utc),
        reading_status=rs,
        raw_value=raw_value,
        asset_id=asset_id,
    )
    state = AgentState(asset_id=asset_id, observation=observation)

    # auto-gather evidence (agent loop during GATHERING_EVIDENCE). The
    # fault-aware gatherer routes by observation type so chiller/UPS/pump
    # faults retrieve their own evidence contract — not the CRAH one.
    from .tools import gather_evidence_for_fault

    for ev in gather_evidence_for_fault(asset_id, observation_type):
        state.add_evidence(ev, actor="agent")

    case_id = STORE.create(state)
    return {"case_id": case_id, "current_state": state.current_state.value,
            "evidence_count": len(state.evidence)}


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
    state = _get_case(case_id)

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

    # G9: surface an AI/rules disagreement, if any, on whatever guardrail
    # result exists by now. Advisory only — never changes current_state.
    if state.guardrail_result is not None:
        from .guardrails import flag_ai_disagreement

        flag_ai_disagreement(
            state.guardrail_result,
            ai_hypothesis=state.ai_hypothesis,
            rule_cause=state.diagnosis.top_cause_id if state.diagnosis else None,
        )

    return {"case_id": case_id, "current_state": state.current_state.value,
            "confidence": state.confidence}


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
) -> dict:
    _need(user, "approve_reject_modify")
    state = _get_case(case_id)
    try:
        dec = HumanDecision(decision)
    except ValueError:
        raise HTTPException(400, f"invalid decision {decision!r}")

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
    state = _get_case(case_id)
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
    state = _get_case(case_id)
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
    state = _get_case(case_id)
    from .tools import submit_feedback as _fb
    corrections = corrections or {}
    # The proposer is always the authenticated caller; a client-supplied
    # submitted_by would let anyone pin a proposal on someone else and then
    # approve it themselves.
    corrections["submitted_by"] = user
    fb_id = _fb(case_id, corrections, state=state)
    try:
        state.queue_feedback(fb_id, actor=user)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
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


@app.post("/kb/rollback/{target_version}")
def rollback_kb(target_version: int, user: str = Depends(resolve_user)) -> dict:
    """Roll back the KB to a prior version, removing cases added after it (F2).

    Requires ``rollback_knowledge_version`` capability. Seed cases
    (version 0) are never removed.
    """
    _need(user, "rollback_knowledge_version")
    from .learning import STORE as _LSTORE
    try:
        target_version = int(target_version)
    except (TypeError, ValueError):
        raise HTTPException(400, "target_version must be an integer")
    try:
        result = _LSTORE.rollback(target_version)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return result


@app.post("/cases/{case_id}/escalation/close")
def close_escalation(case_id: str, reason: str, user: str = Depends(resolve_user)) -> dict:
    """Close an escalated case (ESCALATED -> CLOSED) by an expert/manager.

    Resolves the only state with no prior HTTP exit path: until now an
    escalated case could never be closed via the API. ``reason`` is REQUIRED
    (spec §5 accountability — the audit entry must record why the escalation
    was closed). Requires ``approve_reject_modify`` capability.
    """
    _need(user, "approve_reject_modify")
    state = _get_case(case_id)
    try:
        state.close_escalation(actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"case_id": case_id, "current_state": state.current_state.value}


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
    state = _get_case(case_id)
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