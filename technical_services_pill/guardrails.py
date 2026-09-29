"""Deterministic guardrail / policy engine (spec §4, Layer 4).

This engine is INTENTIONALLY independent of the LLM: it is pure Python that
runs *before* any recommendation reaches a human and *before* any work order
is created (spec §1 layer 4). It implements rules G1–G8 from spec §4.4.

Public API
----------
- ``check_guardrails(recommendation, ctx)`` -> ``GuardrailResult``
- ``sanitize_metadata(text)`` -> ``str``  (G7, called before LLM sees metadata)

Rule reference (spec §4.4)
-------------------------
G1  recommendation implies BMS setpoint/interlock/safety change -> block + escalate
G2  fault classified safety-critical (cooling lost AND temp rising) -> must escalate
G3  root cause maps to another pill -> coordinate + escalate
G4  confidence < ESCALATE_CONFIDENCE -> escalate (do not recommend)
G5  asset not in registry / unknown asset -> escalate
G6  any recommended action -> force AWAITING_APPROVAL (no auto-execute)
G7  sensor-metadata/tag-name contains injection patterns -> sanitize before LLM
G8  recommendation not grounded in kb_refs/evidence -> reject as ungrounded
"""
from __future__ import annotations

import re

from .models import (
    ESCALATE_CONFIDENCE,
    GuardrailContext,
    GuardrailResult,
    Recommendation,
)

# --- Banned actions (G1): the agent may NEVER recommend these ------------
# Enforces "Clearly bounded" — no BMS setpoint / interlock / safety changes.
BANNED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "bms_setpoint_change",
        "interlock_modify",
        "safety_system_override",
        "bms_config_write",
        "controller_firmware_flash",
    }
)

_BANNED_PATTERN = re.compile(
    r"\b(setpoint|interlock|safety\s*override|firmware|bms\s*config)\b",
    re.IGNORECASE,
)

# --- Cross-domain root-cause keywords (G3) --------------------------------
# When the confirmed/top root cause points to another pill's domain, the
# Technical Services agent must coordinate + escalate instead of recommending
# (spec §4.1 "Must escalate", edge case E5).
CROSS_DOMAIN_CAUSE_KEYWORDS: dict[str, str] = {
    "chiller": "Energy/Ops pill (chiller plant failure)",
    "chilled_water_plant": "Energy/Ops pill (chiller plant failure)",
    "power": "Energy/Ops pill (electrical)",
    "ups": "Energy/Ops pill (power)",
    "electrical": "Energy/Ops pill (electrical)",
    "leasable_area": "Leasing pill",
    "lease": "Leasing pill",
    "tenant": "Tenant Experience pill",
    "sustainability": "Sustainability pill",
    # BMS bus / controller failures are Building Management System domain,
    # not Technical-Services field-layer sensor work (edge case E5).
    "communication bus": "Building Management System pill (bus/controller)",
    "controller failure": "Building Management System pill (bus/controller)",
    "bus failure": "Building Management System pill (bus/controller)",
}

# --- Safety-critical cause IDs (G2) --------------------------------------
# These causes represent conditions where escalating to a human expert is
# mandatory regardless of confidence — they imply imminent physical or
# safety risk that the agent must NOT merely recommend around.
SAFETY_CRITICAL_CAUSE_IDS: frozenset[str] = frozenset({
    "thermal_runaway_risk",  # UPS battery thermal runaway — fire risk
    # (cavitation/bearing wear are progressive, not imminent-safety)
})

# --- Prompt-injection patterns (G7) -------------------------------------
_INJECTION_PATTERN = re.compile(
    r"(?i)\b(ignore\s+(all\s+)?(prior|previous)\s+instructions|"
    r"system\s*prompt|disregard\s+(the\s+)?above|"
    r"you\s+are\s+(now|a)| новым\s+правилам)\b"
)


def sanitize_metadata(text: str | None) -> str:
    """G7: redact prompt-injection patterns from sensor metadata / tag names
    *before* the LLM ever sees them (spec §9 E10). The raw value is still
    stored in the audit log; only the LLM-facing copy is sanitized.
    """
    if not text:
        return ""
    return _INJECTION_PATTERN.sub("[REDACTED-INJECTION]", text)


def _is_banned_action(action_type: str, detail: str) -> bool:
    if action_type in BANNED_ACTION_TYPES:
        return True
    return bool(_BANNED_PATTERN.search(f"{action_type} {detail}"))


def check_guardrails(
    recommendation: Recommendation,
    ctx: GuardrailContext,
    confidence: float,
    top_cause_label: str | None = None,
) -> GuardrailResult:
    """Evaluate G1–G8 against a draft recommendation.

    Deterministic and LLM-independent. The caller is responsible for routing
    based on the result:
      - ``must_escalate``  -> ESCALATED (do not surface as a recommendation)
      - ``not allowed``    -> RECOMMENDING -> ESCALATED or re-reason
      - ``requires_approval`` -> AWAITING_APPROVAL (default for Technical Services)
    """
    res = GuardrailResult()

    # G5 — unknown asset: escalate, do not diagnose further.
    if not ctx.asset_known:
        res.add("G5", "asset not in registry; cannot diagnose unknown asset",
                escalate=True, block=True)
        return res  # short-circuit: nothing else is meaningful

    # G4 — confidence below escalate floor: must NOT recommend.
    if confidence < ESCALATE_CONFIDENCE:
        res.add("G4", f"confidence {confidence:.2f} < ESCALATE_CONFIDENCE "
                       f"{ESCALATE_CONFIDENCE:.2f}; escalate, do not recommend",
                 escalate=True, block=True)

    # G1 — banned physical/safety actions: block + escalate.
    for action in recommendation.actions:
        if _is_banned_action(action.type, action.detail):
            res.add("G1", f"action '{action.type}' modifies BMS setpoint/interlock/"
                          "safety — out of bounds", escalate=True, block=True)

    # G2 — safety-critical condition: must escalate (cannot merely recommend).
    if ctx.safety_critical:
        res.add("G2", "safety-critical condition (e.g. cooling lost AND temperature "
                      "rising) — must escalate", escalate=True)

    # G3 — cross-domain root cause: coordinate + escalate to that pill's owner.
    if top_cause_label:
        lowered = top_cause_label.lower()
        for kw, pill in CROSS_DOMAIN_CAUSE_KEYWORDS.items():
            if kw in lowered:
                res.add("G3", f"root cause '{top_cause_label}' maps to {pill}; "
                              f"coordinate + escalate", escalate=True)
                break

    # G8 — anti-hallucination: recommendation must be grounded in retrieved
    # kb_refs AND evidence_refs. Ungrounded drafts are rejected.
    has_kb = bool(recommendation.kb_refs)
    has_ev = bool(recommendation.evidence_refs)
    if not (has_kb and has_ev):
        missing = []
        if not has_kb:
            missing.append("kb_refs")
        if not has_ev:
            missing.append("evidence_refs")
        res.add("G8", f"recommendation not grounded (missing: {', '.join(missing)}); "
                      "rejected as ungrounded", escalate=True, block=True)

    # G6 — any recommended action forces AWAITING_APPROVAL. No auto-execute.
    if recommendation.actions and res.allowed and not res.must_escalate:
        res.add("G6", "recommended action requires human approval before execution",
                require_approval=True)

    return res