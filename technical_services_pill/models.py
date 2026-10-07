"""Pydantic v2 domain models for the Technical Services Fault Diagnosis pill.

Field names follow the product-owner-confirmed contract (8 required core
fields + optional spec §2 operational companions). See ``agent_state.py`` for
the field-name mapping to the spec's §2 ``AgentState`` JSON schema.

All assumed thresholds below are tagged ``【ASSUMPTION】`` in the spec
(§4.3 / Appendix A #5): they are illustrative expert heuristics that MUST be
validated with Keppel technical-services SMEs before deployment. They are
surfaced as module constants so they are configurable, not hard-coded.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .audit import GENESIS_HASH, compute_hash

# --- Assumed thresholds (spec §4.3, Appendix A #5) ------------------------
MIN_RECO_CONFIDENCE = 0.55  # DIAGNOSING -> RECOMMENDING requires confidence >= this
ESCALATE_CONFIDENCE = 0.35  # confidence below this -> ESCALATED (no recommendation)
MAX_GATHERING_LOOPS = 2  # DIAGNOSING -> GATHERING_EVIDENCE loop cap before escalate
MIN_EVIDENCE_COUNT = 3  # GATHERING_EVIDENCE -> DIAGNOSING needs >= this many items
MAX_RETRIEVAL_ROUNDS = 3  # ...or this many retrieval rounds (spec §2 transition rule)


# --- Enums -----------------------------------------------------------------
class AgentStateName(str, Enum):
    """States of the deterministic Diagnosis Agent (spec §2 diagram)."""

    TRIGGERED = "TRIGGERED"
    GATHERING_EVIDENCE = "GATHERING_EVIDENCE"
    DIAGNOSING = "DIAGNOSING"
    RECOMMENDING = "RECOMMENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    MONITORING_OUTCOME = "MONITORING_OUTCOME"
    RECORDING_OUTCOME = "RECORDING_OUTCOME"
    FEEDBACK_QUEUED = "FEEDBACK_QUEUED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class HumanDecision(str, Enum):
    """HITL verdict by the Asset Operations Manager (spec §5 approval contract)."""

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


class OutcomeResult(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class ReadingStatus(str, Enum):
    """Sensor reading disposition at trigger time (spec §4.2 Q1)."""

    ABSENT = "absent"  # no value
    INVALID = "invalid"  # value present but implausible (< -40 or > 150 C)


# --- Sub-models ------------------------------------------------------------
class Observation(BaseModel):
    """The fault alert that triggers a case.

    Maps to the spec's ``fault`` object. ``asset_id`` is an optional echo of
    the alerting asset (validated against ``AgentState.asset_id``).
    """

    type: str  # e.g. "temperature_measurement_missing"
    sensor_id: str
    detected_at: datetime
    reading_status: ReadingStatus
    raw_value: float | None = None  # present only when INVALID / implausible
    asset_id: str | None = None


class EvidenceItem(BaseModel):
    """One piece of retrieved evidence (spec §6 ``Evidence``)."""

    source: str  # bms | sensor | history | config | case_memory
    type: str  # reading | metadata | status | log
    payload: dict
    retrieved_at: datetime
    tool: str
    kb_refs: list[str] = Field(default_factory=list)


class CandidateCause(BaseModel):
    id: str
    label: str
    likelihood: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    """Ranked diagnosis (spec §6 ``Diagnosis``).

    NOTE: spec §6 nests ``confidence`` here. Per product-owner decision the
    canonical confidence is the TOP-LEVEL ``AgentState.confidence`` field, so
    it is intentionally NOT duplicated on this model (single source of truth).
    """

    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    top_cause_id: str | None = None
    reasoning_trace: str
    kb_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class RecommendationAction(BaseModel):
    type: str  # e.g. "onsite_inspection","sensor_replacement","controller_swap",...
    target: str
    detail: str
    kb_refs: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """Draft recommendation gated by Layer 4 + Layer 5 (spec §6).

    ``confidence`` intentionally omitted — see ``AgentState.confidence``.
    """

    actions: list[RecommendationAction] = Field(default_factory=list)
    kb_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class HumanDecisionRecord(BaseModel):
    """A HITL decision (the value of ``AgentState.human_decision``).

    Maps to spec §6 ``Approval``: decider, rationale, modified vs original
    actions, timestamp, signature (brief: "Accountable").
    """

    decision: HumanDecision
    decided_by: str
    rationale: str | None = None  # required for reject/modify (validated below)
    modified_actions: list[RecommendationAction] | None = None
    original_actions: list[RecommendationAction] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    signature: str | None = None

    model_config = ConfigDict(validate_assignment=True)

    @model_validator(mode="after")
    def _require_rationale_and_modifications(self) -> "HumanDecisionRecord":
        if self.decision in (HumanDecision.REJECT, HumanDecision.MODIFY):
            if not (self.rationale and self.rationale.strip()):
                raise ValueError("rationale is required for reject/modify decisions")
        if self.decision == HumanDecision.MODIFY and not self.modified_actions:
            raise ValueError("modified_actions is required for a modify decision")
        return self


class Outcome(BaseModel):
    """Recorded maintenance outcome (spec §6 ``Outcome``)."""

    result: OutcomeResult
    root_cause_confirmed: str | None = None
    actual_actions_taken: list[str] = Field(default_factory=list)
    verified_by: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    notes: str | None = None


class GuardrailResult(BaseModel):
    """Output of the deterministic guardrail engine (spec §4.4)."""

    allowed: bool = True
    requires_approval: bool = False
    must_escalate: bool = False
    reasons: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)

    def add(
        self,
        rule_id: str,
        reason: str,
        *,
        escalate: bool = False,
        block: bool = False,
        require_approval: bool = False,
    ) -> None:
        self.rule_ids.append(rule_id)
        self.reasons.append(f"[{rule_id}] {reason}")
        if escalate:
            self.must_escalate = True
        if block:
            self.allowed = False
        if require_approval:
            self.requires_approval = True


class GuardrailContext(BaseModel):
    """Context flags the guardrail engine needs but cannot infer from the
    recommendation itself (spec §4.4 G2/G5)."""

    asset_known: bool = True
    safety_critical: bool = False  # e.g. cooling lost AND temperature rising


class HistoryEntry(BaseModel):
    """One audited state transition, hash-chained to its predecessor.

    Chains to ``prev_hash``; ``hash`` is computed automatically if omitted.
    """

    from_state: AgentStateName
    to_state: AgentStateName
    at: datetime
    actor: str  # agent | user_id | system
    reason: str
    # Digest of the case's material state (diagnosis, decision, outcome...)
    # right after this entry, so editing those fields breaks the chain too.
    state_digest: str | None = None
    prev_hash: str = GENESIS_HASH
    hash: str | None = None

    model_config = ConfigDict(validate_assignment=True)

    def _payload_for_hash(self) -> dict[str, str | None]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "at": self.at.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "state_digest": self.state_digest,
        }

    @model_validator(mode="after")
    def _set_hash(self) -> "HistoryEntry":
        if self.hash is None:
            self.hash = compute_hash(self.prev_hash, self._payload_for_hash())
        return self


# --------------------------------------------------------------------------- #
# Learning-loop models  (spec §7 governance feedback -> knowledge base)
# --------------------------------------------------------------------------- #
class ValidatedCase(BaseModel):
    """A confirmed-or-corrected diagnosis case, written back to the KB.

    Lives in the LearningStore and is retrieved by future diagnoses via
    similarity matching, nudging ``kb_match`` (and thus confidence) upward
    for recurring fault signatures.
    """

    id: str
    case_id: str
    asset_id: str
    asset_type: str
    fault_signature: str
    proposed_cause: str
    confirmed_cause: str
    action_taken: str
    outcome: str
    confidence: float
    validated_by: str
    corrected: bool  # True if feedback overturned the proposed cause
    weight: float = 1.0  # decays/boosts similarity contribution
    created_at: datetime
    kb_version: int = 0  # KB version when this case was ingested (0 = seed)

    model_config = ConfigDict(validate_assignment=True)


class FeedbackRecord(BaseModel):
    """A human feedback/correction submitted on a closed case.

    ``corrections`` is a free-form dict; key entry points are
    ``confirmed_cause`` (the human-verified root cause) and ``notes``.
    """

    feedback_id: str
    case_id: str
    asset_id: str
    asset_type: str
    proposed_cause: str | None
    confirmed_cause: str
    corrections: dict[str, Any] = {}
    submitted_by: str
    submitted_at: datetime