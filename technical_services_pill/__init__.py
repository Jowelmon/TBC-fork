"""Technical Services Fault Diagnosis — Intelligence Pill.

Public surface:
    AgentState              — the deterministic, audit-chained agent state
    AgentStateName          — state enum (TRIGGERED … CLOSED)
    HumanDecision / HumanDecisionRecord
    Observation / EvidenceItem / Diagnosis / Recommendation / Outcome
    GuardrailResult / GuardrailContext
    check_guardrails / sanitize_metadata
    constants: MIN_RECO_CONFIDENCE, ESCALATE_CONFIDENCE, ...
"""
from .agent_state import AgentState
from .ai_reasoning import generate_diagnostic_hypothesis
from .audit import GENESIS_HASH, canonical_json, compute_hash
from .capture import capture_expert_knowledge
from .cause_registry import (
    CAUSE_BATTERY_EOL,
    CAUSE_COMM_BUS_FAILURE,
    CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE,
    CAUSE_CONFIG_DRIFT,
    CAUSE_SENSOR_HARDWARE_FAILURE,
    CANONICAL_CAUSE_IDS,
    canonicalize_cause_id,
)
from .confidence import score_confidence, evidence_coverage_score
from .decision_tree import evaluate_decision_tree, DecisionResult
from .guardrails import check_guardrails, sanitize_metadata
from .learning import LearningStore, STORE as LEARNING_STORE
from .models import (
    ESCALATE_CONFIDENCE,
    MAX_GATHERING_LOOPS,
    MIN_EVIDENCE_COUNT,
    MIN_RECO_CONFIDENCE,
    AgentStateName,
    CandidateCause,
    Diagnosis,
    EvidenceItem,
    FeedbackRecord,
    GuardrailContext,
    GuardrailResult,
    HistoryEntry,
    HumanDecision,
    HumanDecisionRecord,
    Observation,
    Outcome,
    OutcomeResult,
    ReadingStatus,
    Recommendation,
    RecommendationAction,
    ValidatedCase,
)

__all__ = [
    # state machine
    "AgentState",
    "AgentStateName",
    # decision / HITL
    "HumanDecision",
    "HumanDecisionRecord",
    # core record types
    "Observation",
    "EvidenceItem",
    "CandidateCause",
    "Diagnosis",
    "Recommendation",
    "RecommendationAction",
    "Outcome",
    "OutcomeResult",
    "ReadingStatus",
    # guardrails
    "GuardrailResult",
    "GuardrailContext",
    "check_guardrails",
    "sanitize_metadata",
    "capture_expert_knowledge",
    # ai / cause registry
    "generate_diagnostic_hypothesis",
    "CANONICAL_CAUSE_IDS",
    "canonicalize_cause_id",
    "CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE",
    "CAUSE_COMM_BUS_FAILURE",
    "CAUSE_SENSOR_HARDWARE_FAILURE",
    "CAUSE_CONFIG_DRIFT",
    "CAUSE_BATTERY_EOL",
    # reasoning
    "evaluate_decision_tree",
    "DecisionResult",
    "score_confidence",
    "evidence_coverage_score",
    # audit
    "HistoryEntry",
    "GENESIS_HASH",
    "canonical_json",
    "compute_hash",
    # thresholds
    "MIN_RECO_CONFIDENCE",
    "ESCALATE_CONFIDENCE",
    "MIN_EVIDENCE_COUNT",
    "MAX_GATHERING_LOOPS",
    # learning loop (spec §7)
    "LearningStore",
    "LEARNING_STORE",
    "ValidatedCase",
    "FeedbackRecord",
]
