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

RBAC via ``?user=<demo_user_id>`` query param (mapped in rbac.DEMO_USERS).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .agent_state import AgentState
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

app = FastAPI(title="Technical Services Fault Diagnosis Pill", version="1.0.0")


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

    Built from the observation type, resolved cause and grounding kb_refs —
    not from CRAH-specific token names — so chiller/UPS/pump diagnoses query
    the KB with their own signature (which honestly starts empty in a cold
    KB, yielding a low ``kb_match`` and a conservative confidence).
    """
    parts = [state.observation.type.replace("_", " "), top_cause_id.replace("_", " ")]
    parts.extend(r.replace(":", " ").replace("_", " ") for r in kb_refs)
    return " ".join(parts)


# ========================================================================== #
# Case lifecycle
# ========================================================================== #
@app.post("/cases")
def create_case(
    asset_id: str,
    sensor_id: str,
    user: str,
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
def list_cases(user: str) -> dict:
    _need(user, "view_case")
    return {"cases": STORE.list()}


@app.post("/cases/{case_id}/advance")
def advance_case(case_id: str, user: str) -> dict:
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
        from .confidence import score_confidence, evidence_coverage_score
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
        conf = score_confidence(evidence_coverage=coverage, peer_agreement=1.0,
                                kb_match=kb_match)
        new_st = state.complete_diagnosis(diag, conf, actor="agent")
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

    return {"case_id": case_id, "current_state": state.current_state.value,
            "confidence": state.confidence}


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: str) -> dict:
    _need(user, "view_case")
    snap = STORE.snapshot(case_id)
    if snap is None:
        raise HTTPException(404, "case not found")
    return snap


@app.get("/cases/{case_id}/evidence")
def get_evidence(case_id: str, user: str) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"evidence": [e.model_dump(mode="json") for e in state.evidence]}


@app.get("/cases/{case_id}/diagnosis")
def get_diagnosis(case_id: str, user: str) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    diag = state.diagnosis
    return {"diagnosis": diag.model_dump(mode="json") if diag else None,
            "confidence": state.confidence}


@app.get("/cases/{case_id}/recommendation")
def get_recommendation(case_id: str, user: str) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    rec = state.recommendation
    gr = state.guardrail_result
    return {"recommendation": rec.model_dump(mode="json") if rec else None,
            "guardrail_result": gr.model_dump(mode="json") if gr else None,
            "guardrail_route_explanation": _route_explanation(state)}


@app.post("/cases/{case_id}/approval")
def post_approval(
    case_id: str,
    decision: str,
    user: str,
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
def get_work_order(case_id: str, user: str) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"work_order_id": state.work_order_id}


@app.post("/cases/{case_id}/work-order")
def create_work_order(case_id: str, user: str) -> dict:
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
    user: str,
    root_cause_confirmed: str | None = None,
    verified_by: str = "tech1",
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
        verified_by=verified_by, notes=notes,
    )
    try:
        state.record_outcome(outcome)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.post("/cases/{case_id}/feedback")
def post_feedback(
    case_id: str,
    user: str,
    corrections: dict | None = None,
) -> dict:
    _need(user, "submit_feedback")
    state = _get_case(case_id)
    from .tools import submit_feedback as _fb
    corrections = corrections or {}
    corrections.setdefault("submitted_by", user)
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


@app.get("/kb/stats")
def get_kb_stats(user: str) -> dict:
    """Knowledge-base learning stats: validated cases, cause priors."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return _LSTORE.stats()


@app.get("/kb/queue")
def get_kb_queue(user: str) -> dict:
    """List pending knowledge proposals awaiting steward approval (F2).

    Requires ``approve_knowledge_version`` capability (knowledge steward
    or admin). Returns the list of pending proposals with their metadata.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    pending = _LSTORE.list_pending_proposals()
    return {"queue": pending, "pending_count": len(pending)}


@app.post("/kb/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, user: str) -> dict:
    """Approve a pending knowledge proposal and ingest it into the live KB (F2).

    Requires ``approve_knowledge_version`` capability. On approval the KB
    version increments and the proposal's feedback is promoted to a
    ValidatedCase retrievable by future diagnoses.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    try:
        proposal = _LSTORE.approve_proposal(proposal_id, decided_by=user)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"proposal_id": proposal_id, "status": "approved",
            "decided_by": user, "kb_version": _LSTORE.get_kb_version(),
            "validated_case_id": proposal.get("validated_case_id")}


@app.post("/kb/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, user: str, reason: str) -> dict:
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
def rollback_kb(target_version: int, user: str) -> dict:
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
def close_escalation(case_id: str, user: str, reason: str) -> dict:
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
def request_more_evidence(case_id: str, user: str, reason: str) -> dict:
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
    user: str,
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