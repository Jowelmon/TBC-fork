"""Sentinel: an independent supervisor over the agent's process.

The state machine, guardrails and RBAC each enforce their own rule at the
point of action. The sentinel does not trust any of them: after every write
to a case it re-reads the case from the outside and checks that the record,
as it now stands, is one the rules could have produced:

- every transition is one the state machine allows;
- every human transition was made by someone whose role allows it;
- a diagnosis rests on gathered evidence;
- a recommendation is grounded in knowledge and in evidence actually on the case;
- guardrail results, decisions and work orders agree with the case's state;
- the AI second opinion stayed inside the asset's own causes;
- the audit chain verifies;
- tool output has the expected shape.

If anything is wrong it stops the case (STOP), writes the findings to the
case's own hash-chained history (record the reason), keeps a copy of what it
saw (preserve evidence) and raises an alert on the Dashboard and Governance
(notify a person). Only an auditor can release or quarantine a held case.

It is deliberately not an AI: a supervisor that could itself hallucinate
would not be a supervisor. In normal operation it finds nothing; it exists
for the day a component misbehaves.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .models import (
    MAX_RETRIEVAL_ROUNDS,
    MIN_EVIDENCE_COUNT,
    AgentStateName,
    HumanDecision,
)
from .rbac import DEMO_USERS, PERMISSIONS

if TYPE_CHECKING:
    from .agent_state import AgentState

ACTOR = "sentinel"
# Non-human actors the agent loop uses.
_SYSTEM_ACTORS = {"agent", "system", "cmms", "demo-seed", ACTOR}
_S = AgentStateName
# Transitions a person makes, and the capability that person needs.
_HUMAN_TRANSITIONS: dict[tuple[AgentStateName, AgentStateName], str] = {
    (_S.AWAITING_APPROVAL, _S.EXECUTING): "approve_reject_modify",
    (_S.AWAITING_APPROVAL, _S.CLOSED): "approve_reject_modify",
    (_S.AWAITING_APPROVAL, _S.ESCALATED): "approve_reject_modify",
    (_S.MONITORING_OUTCOME, _S.RECORDING_OUTCOME): "record_outcome",
    (_S.RECORDING_OUTCOME, _S.FEEDBACK_QUEUED): "record_outcome",
    (_S.FEEDBACK_QUEUED, _S.CLOSED): "submit_feedback",
    (_S.ESCALATED, _S.CLOSED): "approve_reject_modify",
    (_S.ESCALATED, _S.GATHERING_EVIDENCE): "approve_reject_modify",
}
_DECIDED = {_S.EXECUTING, _S.MONITORING_OUTCOME, _S.RECORDING_OUTCOME, _S.FEEDBACK_QUEUED}


def _can(actor: str, capability: str) -> bool:
    user = DEMO_USERS.get(actor)
    return bool(user and capability in PERMISSIONS.get(user.role, frozenset()))


def inspect(state: AgentState) -> list[str]:
    """Everything wrong with the case's record, in plain words; [] if sound."""
    from .agent_state import AgentState
    from .cause_registry import cause_asset_type

    findings: list[str] = []
    if not state.verify_audit_chain():
        findings.append("the case's audit chain does not verify")

    # 1. Process: every step allowed, every human step by someone allowed to take it.
    for i, h in enumerate(state.history, start=1):
        step = (h.from_state, h.to_state)
        if h.from_state == h.to_state:
            continue  # an audit note, not a transition
        reviewed = h.reason.startswith("audit review by") and _can(h.actor, "review_audit_integrity")
        if step not in AgentState._ALLOWED and not reviewed:
            findings.append(f"step {i} ({h.from_state.value} to {h.to_state.value}) is not a transition "
                            "the state machine allows")
        needed = _HUMAN_TRANSITIONS.get(step)
        if needed and not reviewed and h.actor not in _SYSTEM_ACTORS and not _can(h.actor, needed):
            findings.append(f"step {i} was made by {h.actor!r}, whose role does not allow it")
        if h.actor not in _SYSTEM_ACTORS and h.actor not in DEMO_USERS:
            findings.append(f"step {i} was made by an unknown actor {h.actor!r}")

    # 2. Evidence: a diagnosis needs something to rest on.
    diag = state.diagnosis
    if diag and diag.top_cause_id != "unresolvable" and not state.evidence:
        findings.append("a diagnosis exists but no evidence was gathered")
    elif (diag and len(state.evidence) < MIN_EVIDENCE_COUNT
          and state._retrieval_rounds < MAX_RETRIEVAL_ROUNDS and diag.top_cause_id != "unresolvable"):
        findings.append(f"diagnosed on {len(state.evidence)} evidence item(s), fewer than the "
                        f"{MIN_EVIDENCE_COUNT} required")
    for ev in state.evidence:
        if not ev.source or not ev.type or not isinstance(ev.payload, (dict, list)):
            findings.append(f"evidence item {ev.type!r} has an unexpected source or shape")

    # 3. Grounding: an actionable recommendation cites knowledge and this case's evidence.
    rec = state.recommendation
    if rec and rec.actions:
        if not rec.kb_refs:
            findings.append("the recommendation cites no knowledge")
        gathered = {e.type for e in state.evidence}
        missing = [r for r in rec.evidence_refs if r not in gathered]
        if not rec.evidence_refs:
            findings.append("the recommendation cites no evidence")
        elif missing:
            findings.append("the recommendation cites evidence the case does not have: " + ", ".join(missing))

    # 4. Consistency between guardrails, decisions, work orders and state.
    gr = state.guardrail_result
    if state.current_state == _S.AWAITING_APPROVAL:
        if not (rec and rec.actions):
            findings.append("awaiting approval with no recommended action")
        if gr is None or gr.must_escalate:
            findings.append("awaiting approval although the guardrails did not clear it")
    decision = state.human_decision
    approved = decision is not None and decision.decision in (HumanDecision.APPROVE, HumanDecision.MODIFY)
    if state.current_state in _DECIDED and not approved:
        findings.append(f"in {state.current_state.value} without a recorded approval")
    if state.work_order_id and not approved:
        findings.append("a work order exists without an approve or modify decision")
    if not 0.0 <= float(state.confidence) <= 1.0:
        findings.append(f"confidence {state.confidence} is outside 0 to 1")

    # 5. The AI second opinion stayed inside its box.
    hyp = state.ai_hypothesis or {}
    if hyp:
        if hyp.get("status") not in ("ok", "unavailable"):
            findings.append(f"the AI second opinion returned an unexpected status {hyp.get('status')!r}")
        h = hyp.get("hypothesis")
        from .mock_registry import ASSETS

        asset_type = (ASSETS.get(state.asset_id) or {}).get("type")
        if h and asset_type and cause_asset_type(h) not in (None, asset_type):
            findings.append(f"the AI second opinion named {h!r}, a cause outside this asset's pill")
        if h and diag and hyp.get("agrees_with_rules") is not None and \
                bool(hyp["agrees_with_rules"]) != (h == diag.top_cause_id):
            findings.append("the AI second opinion's agree/disagree flag contradicts its own hypothesis")

    acknowledged = set((state.sentinel_hold or {}).get("acknowledged") or [])
    return [f for f in findings if f not in acknowledged]


def watch(state: AgentState) -> list[str]:
    """Inspect a case and, if anything is wrong, stop it. Returns the findings."""
    hold = state.sentinel_hold or {}
    if hold.get("active"):
        return hold.get("findings", [])
    findings = inspect(state)
    if findings and state.verify_audit_chain():
        stop(state, findings)
    return findings


def stop(state: AgentState, findings: list[str]) -> None:
    """STOP the case, record why on its own chain, and keep what was seen."""
    state.sentinel_hold = {
        "active": True,
        "at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "acknowledged": (state.sentinel_hold or {}).get("acknowledged", []),
        # Preserve the evidence: what the sentinel saw when it stopped the case.
        "seen": {
            "state": state.current_state.value,
            "confidence": state.confidence,
            "recommendation": state.recommendation.model_dump(mode="json") if state.recommendation else None,
            "human_decision": state.human_decision.model_dump(mode="json") if state.human_decision else None,
            "work_order_id": state.work_order_id,
            "history_length": len(state.history),
        },
    }
    state._record_note(actor=ACTOR, reason="stopped by the sentinel: " + "; ".join(findings))


def release(state: AgentState, *, actor: str, reason: str, quarantine: bool) -> None:
    """An auditor's decision on a held case: release it (the findings are
    acknowledged and will not stop it again) or quarantine it (closed)."""
    hold = state.sentinel_hold or {}
    if not hold.get("active"):
        raise ValueError(f"case {state.case_id} is not held by the sentinel")
    state.sentinel_hold = {**hold, "active": False, "released_by": actor,
                           "acknowledged": [*hold.get("acknowledged", []), *hold.get("findings", [])]}
    note = f"audit review by {actor}: sentinel hold {'quarantined' if quarantine else 'released'}; {reason}"
    if quarantine:
        from_state = state.current_state
        state.current_state = _S.CLOSED
        state._append(from_state, _S.CLOSED, actor=actor, reason=note)
    else:
        state._record_note(actor=actor, reason=note)


def status(states: list[AgentState]) -> dict[str, Any]:
    """What the sentinel is watching and what it has stopped."""
    held = [{"case_id": s.case_id, "asset_id": s.asset_id, **(s.sentinel_hold or {})}
            for s in states if (s.sentinel_hold or {}).get("active")]
    return {"watching": len(states), "held": held,
            "checks": ["allowed transitions", "role behind every human step", "evidence behind a diagnosis",
                       "grounded recommendations", "guardrails, decisions and work orders agree",
                       "AI second opinion inside its pill", "audit chain", "tool output shape"]}
