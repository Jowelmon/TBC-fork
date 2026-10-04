"""Expert knowledge capture for AI HARVEST.

This module is intentionally small and deterministic: it converts a narrative
expert note into a structured knowledge item that can be reviewed, approved,
and later reused by the diagnosis workflow.
"""
from __future__ import annotations

import re
from typing import Any

from .cause_registry import canonicalize_cause_id

_CANONICAL_PATTERN_HINTS: dict[str, list[str]] = {
    "loose_wiring_after_service": ["loose wiring", "wiring", "connection", "physical connection", "after maintenance"],
    "sensor_hardware_failure": ["sensor failed", "sensor fault", "rtd failed", "temperature sensor"],
    "configuration_drift": ["configuration drift", "tag changed", "tag removed", "renamed tag"],
    "communication_bus_controller_failure": ["bus dead", "communication failed", "controller failure", "controller offline"],
    "data_path_drop": ["data path", "gateway", "scada", "signal drop"],
    "refrigerant_leak": ["refrigerant leak", "low pressure", "pressure leak"],
    "condenser_fouling": ["condenser fouling", "high head pressure", "dirty coil"],
    "thermal_runaway_risk": ["thermal runaway", "battery temp", "overheat"],
}


def capture_expert_knowledge(text: str, *, asset_type: str | None = None) -> dict[str, Any]:
    """Turn a narrative expert note into a structured knowledge proposal.

    The result is intentionally conservative: it extracts symptoms, evidence,
    likely cause, and a human-readable recommendation, but it never becomes a
    direct maintenance action without steward review.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("expert narrative cannot be empty")

    lowered = cleaned.lower()
    symptoms = []
    evidence_pattern = []
    if "temperature measurement" in lowered or "temperature" in lowered:
        symptoms.append("temperature measurement missing")
        evidence_pattern.append("temperature unavailable while system remains otherwise active")
    if "communication" in lowered or "communicating" in lowered:
        evidence_pattern.append("sensor communicating")
    if "maintenance" in lowered or "service" in lowered:
        evidence_pattern.append("recent maintenance")
    if "powered" in lowered:
        evidence_pattern.append("sensor powered")
    if not symptoms:
        symptoms.append("equipment anomaly reported by expert")
    if not evidence_pattern:
        evidence_pattern.append("historical expert observation")

    likely_cause = "loose_wiring_after_service"
    best_match_score = -1
    for cause_id, hints in _CANONICAL_PATTERN_HINTS.items():
        score = sum(1 for hint in hints if hint.lower() in lowered)
        if score > best_match_score:
            best_match_score = score
            likely_cause = cause_id
    likely_cause = canonicalize_cause_id(likely_cause) or likely_cause

    if "inspect" in lowered or "check" in lowered:
        recommended_check = "Inspect the reported physical connection and validate wiring integrity before replacement."
    else:
        recommended_check = "Validate the most likely physical or configuration cause before recommending replacement."

    if "replace" in lowered:
        recommended_action = "Replace the failed component only after the physical/wiring check is complete."
    else:
        recommended_action = "Perform the targeted inspection and re-test before any component replacement."

    return {
        "symptoms": symptoms,
        "evidence_pattern": evidence_pattern,
        "likely_cause": likely_cause,
        "recommended_check": recommended_check,
        "recommended_action": recommended_action,
        "expert_reasoning": cleaned,
        "confidence": 0.87,
        "knowledge_source": "expert_interview",
        "asset_type": asset_type or "UNKNOWN",
    }


__all__ = ["capture_expert_knowledge"]
