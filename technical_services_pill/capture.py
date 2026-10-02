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
"""
from __future__ import annotations

import re
from typing import Any

from . import llm
from .decision_tree import KNOWN_CAUSE_IDS
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


def draft_from_transcript(transcript: str, asset_type: str) -> dict[str, Any]:
    """Return a validated knowledge draft. Raises CaptureError / llm.LLMError."""
    if not transcript or not transcript.strip():
        raise CaptureError("transcript is empty")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise CaptureError(f"transcript exceeds {MAX_TRANSCRIPT_CHARS} characters")

    sanitized = sanitize_metadata(transcript)
    injection_found = sanitized != transcript

    raw = llm.complete_json(sanitized, asset_type, sorted(KNOWN_CAUSE_IDS))
    items = raw.get("heuristics")
    if not isinstance(items, list):
        raise CaptureError("model output has no 'heuristics' list")

    haystack = _norm(sanitized)
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    if injection_found:
        warnings.append(
            "[G7] instruction-like text was redacted from the transcript before "
            "the model saw it"
        )

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"item {idx}: not an object, dropped")
            continue
        quote = str(item.get("evidence_quote", "")).strip()
        if not quote or _norm(quote) not in haystack:
            warnings.append(
                f"item {idx}: supporting quote not found verbatim in the transcript, "
                "dropped as ungrounded"
            )
            continue

        cause = str(item.get("likely_cause", "")).strip()
        is_new = cause not in KNOWN_CAUSE_IDS
        if is_new:
            slug = re.sub(r"[^a-z0-9_]+", "_", cause.lower().removeprefix("new:")).strip("_")
            cause = f"new:{slug or 'unnamed'}"

        kept.append({
            "symptom_pattern": str(item.get("symptom_pattern", "")).strip()[:300],
            "likely_cause": cause,
            "new_cause": is_new,
            **{f: _clean_list(item.get(f)) for f in _LIST_FIELDS},
            "evidence_quote": quote,
        })

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


SAMPLE_INTERVIEW = """\
Interviewer: When a CRAH unit starts losing its supply air temperature reading, what do you do first?

Senior technician (22 years, M&E): First thing, I check if it's just that one sensor or every tag on that controller. If every tag on the bus has gone quiet at once, it's almost never the sensor. That's the controller or the bus. Don't go swapping sensors, you'll waste a whole shift. I call the BMS vendor straight away for that one, it's not ours to fix.

If it's only one sensor and the neighbours are fine, I look at the calibration sticker. A sensor past its calibration date that reads nothing is usually just end of life. Replace it and log it.

Interviewer: And chillers?

Senior technician: With a chiller tripping on low pressure, I check the refrigerant charge before anything else. If the charge is down and there's an oil stain near the joints, that's a refrigerant leak until proven otherwise. Never top up the gas and walk away, it'll just leak out again and you've vented refrigerant. I get the safety officer involved for any leak, that's a regulatory thing.

If the approach temperature keeps creeping up week by week, look at the condenser first. A fouled condenser is the usual story there, especially after the dry season.
"""
