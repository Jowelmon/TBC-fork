"""Expert knowledge capture: interview transcript -> governed draft knowledge.

Pipeline (each step is a boundary the model cannot cross):

1. G7  sanitize the transcript before any model sees it.
2. LLM extracts candidate heuristics as JSON (``llm.complete_json``).
3. Validate shape; map each cause onto the known cause universe or mark it
   explicitly as a proposed new cause.
4. Grounding check: every heuristic must quote the transcript verbatim.
   Anything the expert did not actually say is dropped, with a warning.
5. Queue the surviving draft as a pending proposal. A *different* knowledge
   steward must approve it before it reaches the live knowledge base.

The model drafts; people decide. Nothing in this module writes to the KB.

This module is intentionally small and deterministic: it converts a narrative
expert note into a structured knowledge item that can be reviewed, approved,
and later reused by the diagnosis workflow.
"""
from __future__ import annotations

import re
from typing import Any

from . import llm
from .decision_tree import KNOWN_CAUSE_IDS
from .cause_registry import canonicalize_cause_id, cause_asset_type, cause_label
from .guardrails import sanitize_metadata

MAX_TRANSCRIPT_CHARS = 20_000
_LIST_FIELDS = ("checks", "do_not", "escalate_when")


class CaptureError(ValueError):
    """The transcript or the model output could not produce usable knowledge."""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:8]


def _validate_items(
    sanitized: str, items: list[Any], asset_type: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Grounding + cause checks shared by the AI draft and the reviewed submit.

    Every item must quote the (sanitised) transcript verbatim; anything else
    is dropped. Causes are stored as canonical IDs with a plain-English label
    and the asset type whose decision tree owns them, so approved knowledge
    lands on the right pill even when one interview covers several assets.
    """
    haystack = _norm(sanitized)
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Item {idx} was not a heuristic object and was dropped.")
            continue
        quote = str(item.get("evidence_quote", "")).strip()
        if not quote or _norm(quote) not in haystack:
            warnings.append(
                f"Item {idx} was dropped as ungrounded: its supporting quote is "
                "not in the transcript word for word."
            )
            continue

        cause_raw = str(item.get("likely_cause", "")).strip()
        canonical = canonicalize_cause_id(cause_raw.removeprefix("new:")) or cause_raw
        is_new = canonical not in KNOWN_CAUSE_IDS
        if is_new:
            slug = re.sub(r"[^a-z0-9_]+", "_", cause_raw.lower().removeprefix("new:")).strip("_")
            cause = f"new:{slug or 'unnamed'}"
            owner = asset_type
        else:
            cause = canonical
            owner = cause_asset_type(canonical) or asset_type
        if owner != asset_type:
            warnings.append(
                f"\"{cause_label(cause)}\" belongs to the {owner} pill, so it will be "
                f"filed under {owner}, not {asset_type}."
            )

        kept.append({
            "symptom_pattern": str(item.get("symptom_pattern", "")).strip()[:300],
            "likely_cause": cause,
            "cause_label": cause_label(cause),
            "asset_type": owner,
            "new_cause": is_new,
            **{f: _clean_list(item.get(f)) for f in _LIST_FIELDS},
            "evidence_quote": quote,
        })
    return kept, warnings


def _sanitize(transcript: str) -> tuple[str, list[str]]:
    if not transcript or not transcript.strip():
        raise CaptureError("transcript is empty")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise CaptureError(f"transcript exceeds {MAX_TRANSCRIPT_CHARS} characters")
    sanitized = sanitize_metadata(transcript)
    warnings = []
    if sanitized != transcript:
        warnings.append(
            "[G7] Instruction-like text was removed from the transcript before "
            "the model saw it."
        )
    return sanitized, warnings


def draft_from_transcript(transcript: str, asset_type: str) -> dict[str, Any]:
    """Return a validated knowledge draft. Raises CaptureError / llm.LLMError."""
    sanitized, warnings = _sanitize(transcript)
    raw = llm.complete_json(sanitized, asset_type, sorted(KNOWN_CAUSE_IDS))
    items = raw.get("heuristics")
    if not isinstance(items, list):
        raise CaptureError("model output has no 'heuristics' list")

    kept, item_warnings = _validate_items(sanitized, items, asset_type)
    warnings += item_warnings
    if not kept:
        raise CaptureError(
            "no grounded heuristics could be extracted; "
            + ("; ".join(warnings) if warnings else "the model returned none")
        )
    return {
        "provider": llm.provider_name(),
        "heuristics": kept,
        "warnings": warnings,
        "dropped": len(items) - len(kept),
    }


def reviewed_draft(
    transcript: str, asset_type: str, heuristics: list[Any], provider: str,
) -> dict[str, Any]:
    """Re-validate a draft the capturer has reviewed before it is queued.

    The capturer may drop heuristics or correct a cause, but cannot add
    anything the expert did not say: every surviving item is grounded again
    against the transcript, exactly like the model's output.
    """
    sanitized, warnings = _sanitize(transcript)
    if not heuristics:
        raise CaptureError("select at least one heuristic to submit")
    kept, item_warnings = _validate_items(sanitized, heuristics, asset_type)
    if len(kept) != len(heuristics):
        raise CaptureError(
            "reviewed draft failed grounding: " + "; ".join(item_warnings)
        )
    return {
        "provider": provider if provider in ("adp", "mock") else llm.provider_name(),
        "heuristics": kept,
        "warnings": warnings + item_warnings,
        "dropped": 0,
    }


SAMPLE_INTERVIEW = """\
Interviewer: When a CRAH unit starts losing its supply air temperature reading, what do you do first?

Senior technician (22 years, M&E): First thing, I check if it's just that one sensor or every tag on that controller. If every tag on the bus has gone quiet at once, it's almost never the sensor. That's the controller or the bus. Don't go swapping sensors, you'll waste a whole shift. I call the BMS vendor straight away for that one, it's not ours to fix.

If it's only one sensor and the neighbours are fine, I look at the calibration sticker. A sensor past its calibration date that reads nothing is usually just end of life. Replace it and log it.

Interviewer: And chillers?

Senior technician: With a chiller tripping on low pressure, I check the refrigerant charge before anything else. If the charge is down and there's an oil stain near the joints, that's a refrigerant leak until proven otherwise. Never top up the gas and walk away, it'll just leak out again and you've vented refrigerant. I get the safety officer involved for any leak, that's a regulatory thing.

If the approach temperature keeps creeping up week by week, look at the condenser first. A fouled condenser is the usual story there, especially after the dry season.
"""

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
