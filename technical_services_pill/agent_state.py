"""AgentState — the Technical Services Fault Diagnosis agent state.

Implements the deterministic state machine from spec §2 with the
product-owner-confirmed field contract:

  REQUIRED CORE (8):
    asset_id, observation, evidence, diagnosis, confidence,
    recommendation, human_decision, outcome

  OPTIONAL COMPANIONS (from spec §2, kept for auditability/bounded behaviour):
    case_id, current_state, guardrail_result, work_order_id,
    feedback_id, history

Field-name mapping to spec §2 ``AgentState``:
    observation      <- fault  (the trigger alert)
    evidence         <- evidence_bundle
    diagnosis        <- ranked_diagnosis + candidate_causes (flattened)
    confidence       <- ranked_diagnosis.confidence  (promoted to top-level)
    recommendation   <- recommendation
    human_decision   <- approval  (approve/reject/modify verdict)
    outcome          <- outcome
    current_state    <- current_state
    guardrail_result <- guardrail_result
    history          <- history (hash-chained, see audit.py)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field, model_validator

from .audit import GENESIS_HASH
from .guardrails import SAFETY_CRITICAL_CAUSE_IDS, check_guardrails
from .models import (
    ESCALATE_CONFIDENCE,
    MIN_EVIDENCE_COUNT,
    MIN_RECO_CONFIDENCE,
    AgentStateName,
    CandidateCause,
    Diagnosis,
    EvidenceItem,
    GuardrailContext,
    GuardrailResult,
    HistoryEntry,
    HumanDecision,
    HumanDecisionRecord,
    Observation,
    Outcome,
    Recommendation,
)


class AgentState:
    """Mutable, deterministic, audit-chained agent state.

    Plain-Python holder (not a frozen Pydantic model) because a state machine
    transitions in place. The *contents* are validated Pydantic models; every
    transition is recorded in a tamper-evident hash chain.
    """

    # --- required core fields ---
    asset_id: str
    observation: Observation
    evidence: list[EvidenceItem]
    diagnosis: Diagnosis | None
    confidence: float
    recommendation: Recommendation | None
    human_decision: HumanDecisionRecord | None
    outcome: Outcome | None

    # --- optional companions (spec §2) ---
    case_id: str | None
    current_state: AgentStateName
    guardrail_result: GuardrailResult | None
    work_order_id: str | None
    feedback_id: str | None
    history: list[HistoryEntry]

    # --- internal counters (spec §2 loop caps) ---
    _gathering_loops: int
    _retrieval_rounds: int

    def __init__(
        self,
        *,
        asset_id: str,
        observation: Observation,
        case_id: str | None = None,
        actor: str = "system",
    ) -> None:
        self.asset_id = asset_id
        self.observation = observation
        self.evidence: list[EvidenceItem] = []
        self.diagnosis: Diagnosis | None = None
        self.confidence: float = 0.0
        self.recommendation: Recommendation | None = None
        self.human_decision: HumanDecisionRecord | None = None
        self.outcome: Outcome | None = None

        self.case_id = case_id
        self.current_state = AgentStateName.TRIGGERED
        self.guardrail_result: GuardrailResult | None = None
        self.work_order_id = None
        self.feedback_id = None
        self.history: list[HistoryEntry] = []

        self._gathering_loops = 0
        self._retrieval_rounds = 0

        # TRIGGERED -> GATHERING_EVIDENCE immediately (alert validated against
        # asset registry by the constructor's asset_id presence).
        self._transition(
            AgentStateName.GATHERING_EVIDENCE,
            actor=actor,
            reason="fault alert validated against asset registry",
        )

    # ------------------------------------------------------------------ #
    # Transition machinery
    # ------------------------------------------------------------------ #
    _ALLOWED: dict[tuple[AgentStateName, AgentStateName], str] = {
        # (from, to): rationale tag
        (AgentStateName.TRIGGERED, AgentStateName.GATHERING_EVIDENCE): "alert validated",
        (AgentStateName.GATHERING_EVIDENCE, AgentStateName.DIAGNOSING): "min evidence present or rounds elapsed",
        (AgentStateName.GATHERING_EVIDENCE, AgentStateName.ESCALATED): "evidence insufficient",
        (AgentStateName.DIAGNOSING, AgentStateName.RECOMMENDING): "confidence >= MIN_RECO_CONFIDENCE",
        (AgentStateName.DIAGNOSING, AgentStateName.GATHERING_EVIDENCE): "confidence too low; request more evidence",
        (AgentStateName.DIAGNOSING, AgentStateName.ESCALATED): "out of scope / safety / low confidence",
        (AgentStateName.RECOMMENDING, AgentStateName.AWAITING_APPROVAL): "guardrail requires approval",
        (AgentStateName.RECOMMENDING, AgentStateName.ESCALATED): "guardrail must escalate",
        (AgentStateName.AWAITING_APPROVAL, AgentStateName.EXECUTING): "human approve/modify",
        (AgentStateName.AWAITING_APPROVAL, AgentStateName.CLOSED): "human reject",
        (AgentStateName.AWAITING_APPROVAL, AgentStateName.ESCALATED): "approval timeout",
        (AgentStateName.EXECUTING, AgentStateName.MONITORING_OUTCOME): "work order acknowledged",
        (AgentStateName.MONITORING_OUTCOME, AgentStateName.RECORDING_OUTCOME): "outcome submitted",
        (AgentStateName.RECORDING_OUTCOME, AgentStateName.FEEDBACK_QUEUED): "outcome persisted",
        (AgentStateName.FEEDBACK_QUEUED, AgentStateName.CLOSED): "feedback accepted into governance queue",
        (AgentStateName.ESCALATED, AgentStateName.GATHERING_EVIDENCE): "expert requests more evidence",
        (AgentStateName.ESCALATED, AgentStateName.CLOSED): "escalation resolved/closed by expert",
    }

    def _transition(
        self,
        to_state: AgentStateName,
        *,
        actor: str,
        reason: str,
    ) -> None:
        from_state = self.current_state
        key = (from_state, to_state)
        if key not in self._ALLOWED:
            allowed_targets = [
                t.value for (f, t) in self._ALLOWED if f == from_state
            ]
            raise ValueError(
                f"illegal transition {from_state.value} -> {to_state.value}: "
                f"{reason} (allowed targets from {from_state.value}: {allowed_targets})"
            )
        prev_hash = self.history[-1].hash if self.history else GENESIS_HASH
        entry = HistoryEntry(
            from_state=from_state,
            to_state=to_state,
            at=datetime.now(),
            actor=actor,
            reason=reason,
            prev_hash=prev_hash,
        )
        self.history.append(entry)
        self.current_state = to_state

    # ------------------------------------------------------------------ #
    # Lifecycle helpers (tools/state-machine facade)
    # ------------------------------------------------------------------ #
    def add_evidence(self, item: EvidenceItem, *, actor: str = "agent") -> None:
        """Append retrieved evidence. Stays in GATHERING_EVIDENCE."""
        if self.current_state not in (
            AgentStateName.GATHERING_EVIDENCE,
            AgentStateName.ESCALATED,
        ):
            raise ValueError("evidence can only be added while gathering or escalated")
        self.evidence.append(item)
        self._retrieval_rounds += 1

    def begin_diagnosing(
        self, *, actor: str = "agent", force: bool = False
    ) -> None:
        """GATHERING_EVIDENCE -> DIAGNOSING.

        Allowed when min evidence count met OR max retrieval rounds elapsed
        (spec §2). ``force`` lets a caller proceed regardless (e.g. test seed).
        """
        ready = (
            len(self.evidence) >= MIN_EVIDENCE_COUNT
            or self._retrieval_rounds >= 3
        )
        if not (ready or force):
            raise ValueError(
                f"insufficient evidence: {len(self.evidence)} items, "
                f"{self._retrieval_rounds} rounds (need {MIN_EVIDENCE_COUNT} items "
                f"or 3 rounds)"
            )
        self._transition(
            AgentStateName.DIAGNOSING,
            actor=actor,
            reason=f"begin diagnosis ({len(self.evidence)} evidence items)",
        )

    def escalate_for_evidence(self, *, actor: str = "agent") -> None:
        """GATHERING_EVIDENCE -> ESCALATED when evidence cannot be resolved."""
        self._transition(
            AgentStateName.ESCALATED,
            actor=actor,
            reason="evidence insufficient and not resolvable automatically",
        )

    def complete_diagnosis(
        self,
        diagnosis: Diagnosis,
        confidence: float,
        *,
        actor: str = "agent",
        guardrail_ctx: GuardrailContext | None = None,
    ) -> AgentStateName:
        """DIAGNOSING -> RECOMMENDING | GATHERING_EVIDENCE | ESCALATED.

        Routing (spec §2 + §4.3):
          - confidence < ESCALATE_CONFIDENCE       -> ESCALATED (G4)
          - confidence < MIN_RECO_CONFIDENCE       -> GATHERING_EVIDENCE (max 2 loops)
          - confidence >= MIN_RECO_CONFIDENCE      -> RECOMMENDING
        """
        if self.current_state != AgentStateName.DIAGNOSING:
            raise ValueError("complete_diagnosis only valid in DIAGNOSING")

        self.diagnosis = diagnosis
        self.confidence = confidence

        if confidence < ESCALATE_CONFIDENCE:
            self._transition(
                AgentStateName.ESCALATED,
                actor=actor,
                reason=f"confidence {confidence:.2f} < ESCALATE_CONFIDENCE "
                       f"{ESCALATE_CONFIDENCE:.2f}",
            )
            return self.current_state

        if confidence < MIN_RECO_CONFIDENCE:
            if self._gathering_loops >= 2:
                self._transition(
                    AgentStateName.ESCALATED,
                    actor=actor,
                    reason="low confidence and max gathering loops (2) exhausted",
                )
                return self.current_state
            self._gathering_loops += 1
            self._transition(
                AgentStateName.GATHERING_EVIDENCE,
                actor=actor,
                reason=f"confidence {confidence:.2f} < MIN_RECO_CONFIDENCE; "
                       f"request more evidence (loop {self._gathering_loops}/2)",
            )
            return self.current_state

        self._transition(
            AgentStateName.RECOMMENDING,
            actor=actor,
            reason=f"confidence {confidence:.2f} >= MIN_RECO_CONFIDENCE",
        )
        return self.current_state

    def propose_recommendation(
        self,
        recommendation: Recommendation,
        *,
        guardrail_ctx: GuardrailContext | None = None,
        actor: str = "agent",
    ) -> GuardrailResult:
        """RECOMMENDING -> AWAITING_APPROVAL | ESCALATED via guardrail engine.

        Runs the deterministic guardrail (G1–G8) and routes by its result:
          - must_escalate or not allowed -> ESCALATED
          - requires_approval            -> AWAITING_APPROVAL
        """
        if self.current_state != AgentStateName.RECOMMENDING:
            raise ValueError("propose_recommendation only valid in RECOMMENDING")

        ctx = guardrail_ctx or GuardrailContext(asset_known=True)
        top_label = None
        if self.diagnosis and self.diagnosis.top_cause_id:
            # G2 activation: if the top cause is a known safety-critical
            # condition (e.g. UPS thermal runaway), flag the context so the
            # guardrail engine forces escalation — even at high confidence.
            if self.diagnosis.top_cause_id in SAFETY_CRITICAL_CAUSE_IDS:
                ctx = ctx.model_copy(update={"safety_critical": True})
            for c in self.diagnosis.candidate_causes:
                if c.id == self.diagnosis.top_cause_id:
                    top_label = c.label
                    break
        result = check_guardrails(
            recommendation, ctx, confidence=self.confidence, top_cause_label=top_label
        )
        self.recommendation = recommendation
        self.guardrail_result = result

        if result.must_escalate or not result.allowed:
            self._transition(
                AgentStateName.ESCALATED,
                actor=actor,
                reason="guardrail escalation: " + "; ".join(result.reasons),
            )
        else:
            self._transition(
                AgentStateName.AWAITING_APPROVAL,
                actor=actor,
                reason="guardrail passed; awaiting human approval (G6)",
            )
        return result

    def record_human_decision(
        self,
        decision: HumanDecisionRecord,
        *,
        actor: str | None = None,
    ) -> AgentStateName:
        """AWAITING_APPROVAL -> EXECUTING (approve/modify) | CLOSED (reject).

        On ``modify``, original actions are preserved alongside modified ones
        (spec §7 step 6; edge case E7) so the delta feeds the governance queue.
        """
        if self.current_state != AgentStateName.AWAITING_APPROVAL:
            raise ValueError("record_human_decision only valid in AWAITING_APPROVAL")

        self.human_decision = decision
        act = actor or decision.decided_by

        if decision.decision == HumanDecision.REJECT:
            self._transition(
                AgentStateName.CLOSED,
                actor=act,
                reason=f"rejected by {decision.decided_by}: {decision.rationale}",
            )
            return self.current_state

        # approve or modify -> EXECUTING
        if decision.decision == HumanDecision.MODIFY:
            # keep originals for governance delta
            if self.recommendation and decision.original_actions is None:
                decision.original_actions = list(self.recommendation.actions)
            reason = f"modified by {decision.decided_by}: {decision.rationale}"
        else:
            reason = f"approved by {decision.decided_by}"

        self._transition(AgentStateName.EXECUTING, actor=act, reason=reason)
        return self.current_state

    def acknowledge_work_order(
        self, work_order_id: str, *, actor: str = "system"
    ) -> None:
        """EXECUTING -> MONITORING_OUTCOME once CMMS acknowledges the WO.

        Per spec §3 tool guardrail, the WO may only be created after an
        approval/modify decision exists — enforced by the state precondition.
        """
        if self.current_state != AgentStateName.EXECUTING:
            raise ValueError("acknowledge_work_order only valid in EXECUTING")
        self.work_order_id = work_order_id
        self._transition(
            AgentStateName.MONITORING_OUTCOME,
            actor=actor,
            reason=f"work order {work_order_id} acknowledged by CMMS",
        )

    def record_outcome(self, outcome: Outcome) -> None:
        """MONITORING_OUTCOME -> RECORDING_OUTCOME -> FEEDBACK_QUEUED."""
        if self.current_state != AgentStateName.MONITORING_OUTCOME:
            raise ValueError("record_outcome only valid in MONITORING_OUTCOME")
        self.outcome = outcome
        self._transition(
            AgentStateName.RECORDING_OUTCOME,
            actor=outcome.verified_by,
            reason=f"outcome submitted: {outcome.result.value}",
        )
        self._transition(
            AgentStateName.FEEDBACK_QUEUED,
            actor=outcome.verified_by,
            reason="outcome persisted; routed to governance pipeline",
        )

    def queue_feedback(self, feedback_id: str, *, actor: str = "system") -> None:
        """FEEDBACK_QUEUED -> CLOSED once feedback is accepted into governance."""
        if self.current_state != AgentStateName.FEEDBACK_QUEUED:
            raise ValueError("queue_feedback only valid in FEEDBACK_QUEUED")
        self.feedback_id = feedback_id
        self._transition(
            AgentStateName.CLOSED,
            actor=actor,
            reason=f"feedback {feedback_id} accepted into governance queue",
        )

    def close_escalation(self, *, actor: str, reason: str) -> None:
        """ESCALATED -> CLOSED by an expert."""
        if self.current_state != AgentStateName.ESCALATED:
            raise ValueError("close_escalation only valid in ESCALATED")
        self._transition(AgentStateName.CLOSED, actor=actor, reason=reason)

    def request_more_evidence(self, *, actor: str, reason: str) -> None:
        """ESCALATED -> GATHERING_EVIDENCE: expert requests additional evidence.

        The only re-entry path from ESCALATED back into the diagnosis loop
        (spec §2 transition table). ``reason`` is REQUIRED for auditability
        — the audit entry must record why additional evidence was needed.
        """
        if self.current_state != AgentStateName.ESCALATED:
            raise ValueError("request_more_evidence only valid in ESCALATED")
        self._transition(
            AgentStateName.GATHERING_EVIDENCE,
            actor=actor,
            reason=f"expert requests more evidence: {reason}",
        )

    # ------------------------------------------------------------------ #
    # Audit / observability
    # ------------------------------------------------------------------ #
    def verify_audit_chain(self) -> bool:
        """Recompute every history hash from genesis; True iff chain is intact."""
        from .audit import compute_hash

        prev = GENESIS_HASH
        for i, entry in enumerate(self.history):
            if entry.prev_hash != prev:
                return False
            expected = compute_hash(prev, entry._payload_for_hash())
            if entry.hash != expected:
                return False
            prev = entry.hash
        return True

    def snapshot(self) -> dict:
        """Serialise the state for the HITL UI / API (brief: "Transparent")."""
        return {
            "case_id": self.case_id,
            "asset_id": self.asset_id,
            "current_state": self.current_state.value,
            "observation": self.observation.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in self.evidence],
            "diagnosis": self.diagnosis.model_dump(mode="json") if self.diagnosis else None,
            "confidence": self.confidence,
            "recommendation": (
                self.recommendation.model_dump(mode="json")
                if self.recommendation
                else None
            ),
            "guardrail_result": (
                self.guardrail_result.model_dump(mode="json")
                if self.guardrail_result
                else None
            ),
            "human_decision": (
                self.human_decision.model_dump(mode="json")
                if self.human_decision
                else None
            ),
            "work_order_id": self.work_order_id,
            "outcome": self.outcome.model_dump(mode="json") if self.outcome else None,
            "feedback_id": self.feedback_id,
            "history": [h.model_dump(mode="json") for h in self.history],
            "audit_chain_valid": self.verify_audit_chain(),
        }
