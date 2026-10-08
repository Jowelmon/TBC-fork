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
from .cause_registry import canonicalize_cause_id, cause_asset_type, cause_label
from .decision_tree import KNOWN_CAUSE_IDS
from .guardrails import sanitize_metadata
from .safety import defeats_safety, said_as_prohibition, touches_protection

MAX_TRANSCRIPT_CHARS = 20_000
_LIST_FIELDS = ("checks", "do_not", "escalate_when")


class CaptureError(ValueError):
    """The transcript or the model output could not produce usable knowledge."""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value
            if str(v).strip() and "[REDACTED" not in str(v)][:8]


_TURNS = re.compile(r"\n\s*\n|\n(?=\s*[A-Z][^:\n]{0,60}:)")
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


def _paragraph_of(sanitized: str, quote: str) -> str:
    """The expert answer the quote is from: its paragraph or speaker turn.
    A transcript with neither (one long block) falls back to the quote's
    sentence and the three after it, so a line cannot be borrowed from
    elsewhere in the interview."""
    q = _norm(quote)
    turns = [t for t in _TURNS.split(sanitized) if t.strip()]
    answer = next((t for t in turns if q in _norm(t)), sanitized)
    if len(turns) > 1:
        return answer
    sentences = [x for x in _SENTENCES.split(answer) if x.strip()]
    start = next((i for i, x in enumerate(sentences) if q[:30] in _norm(x)), 0)
    return " ".join(sentences[start:start + 4])


def _closest_sentence(symptom: str, quote: str) -> str:
    """The sentence of the expert's quote that shares most words with a
    reworded symptom (the first, if none do), so the WHEN text stays in the
    expert's words without repeating the whole quote."""
    from .learning import _terms

    sentences = [x.strip() for x in _SENTENCES.split(quote) if x.strip()]
    if len(sentences) <= 1:
        return quote
    wanted = _terms(symptom or "")
    best = max(sentences, key=lambda x: len(wanted & _terms(x)))
    return best if not defeats_safety(best) else sentences[0]


def _ground_lines(lines: list[str], answer: str, field: str, idx: int,
                  warnings: list[str]) -> list[str]:
    """Keep a check / never / escalate-when line only if the expert said it,
    word for word, in the same answer as the quote, and it does not tell
    anyone to defeat a safety device."""
    kept = []
    for line in lines:
        if _norm(line) not in _norm(answer):
            article = "an" if field[0] in "aeiou" else "a"
            warnings.append(f"Item {idx}: dropped {article} {field} line the expert did not say in this answer.")
        elif field == "never" and not said_as_prohibition(line, answer):
            # Shown under "Never", but the expert did not say it as one:
            # it could be read as an instruction, so screen it like one.
            if defeats_safety(line):
                warnings.append(f"Item {idx}: dropped a never line that reads as an instruction "
                                "to defeat a safety device.")
            else:
                kept.append(line)
        elif field != "never" and defeats_safety(line):
            article = "an" if field[0] in "aeiou" else "a"
            warnings.append(f"Item {idx}: dropped {article} {field} line that would defeat a safety device.")
        else:
            kept.append(line)
    return kept


_GENERIC = {"failure", "fault", "hardware", "drop", "risk", "or", "of", "after", "gateway"}


def _cause_terms(cause: str) -> tuple[str, ...]:
    """Words of the cause's label plus its tell-tale phrases."""
    words = {w for w in re.findall(r"[a-z]+", cause_label(cause).lower()) if w not in _GENERIC}
    keywords = next((k for c, k in llm._CAUSE_KEYWORDS if c == cause), ())
    return (*words, *keywords)


def _rules_out(quote: str, cause: str) -> bool:
    """True if the expert's own words deny the cause the item is filed
    under, e.g. "it's almost never the sensor" filed as a sensor failure."""
    low = quote.lower()
    return any(llm._denied(low, pos)
               for term in _cause_terms(cause) for pos in llm._keyword_spans(term, low))


def _mentions_cause(text: str, cause: str) -> bool:
    """Whether the expert's words name the cause (or its tell-tale signs)
    the heuristic is filed under."""
    low = text.lower()
    return any(llm._keyword_spans(term, low) for term in _cause_terms(cause))


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
        notes_from = len(warnings)
        quote = str(item.get("evidence_quote", "")).strip()
        if "[REDACTED" in quote or "[REDACTED" in str(item.get("symptom_pattern", "")):
            warnings.append(f"Item {idx} was dropped: it contains text redacted as an injection attempt.")
            continue
        if not quote or _norm(quote) not in haystack:
            warnings.append(
                f"Item {idx} was dropped as ungrounded: its supporting quote is "
                "not in the transcript word for word."
            )
            continue
        if defeats_safety(quote):
            warnings.append(f"Item {idx} was dropped: the expert's words would defeat a safety device.")
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

        check_cause = not is_new and _rules_out(quote, cause)
        if check_cause:
            warnings.append(
                f"Item {idx}: the expert's words may rule out \"{cause_label(cause)}\"; "
                "check the cause before sending."
            )
        answer = _paragraph_of(sanitized, quote)
        symptom = str(item.get("symptom_pattern", "")).strip()
        if (not symptom or len(symptom) > 600 or _norm(symptom) not in _norm(answer)
                or defeats_safety(symptom)):
            # The expert's own words, never a paraphrase: the sentence of the
            # quote closest to what the draft meant.
            fallback = _closest_sentence(symptom, quote)
            if symptom and _norm(symptom) != _norm(fallback):
                warnings.append(f"Item {idx}: the WHEN text was reworded, so the expert's own sentence "
                                f"is used: \"{fallback}\"")
            symptom = fallback
        off_topic = not is_new and not _mentions_cause(f"{quote} {answer}", cause)
        if off_topic:
            warnings.append(
                f"Item {idx}: nothing in the expert's answer names \"{cause_label(cause)}\" "
                "or its usual signs; check it is filed under the right cause."
            )
        names = {"checks": "check", "do_not": "never", "escalate_when": "escalate-when"}
        lists = {f: _ground_lines(_clean_list(item.get(f)), answer, names[f], idx, warnings)
                 for f in _LIST_FIELDS}
        # Deny by default: any line naming a protective device or its
        # monitoring is held for the approving steward's safety review.
        safety_review = [t for t in (quote, symptom, *lists["checks"], *lists["escalate_when"])
                         if touches_protection(t)]
        safety_review += [t for t in lists["do_not"]
                          if not said_as_prohibition(t, answer) and touches_protection(t)]
        safety_review = list(dict.fromkeys(safety_review))
        if safety_review:
            warnings.append(
                f"Item {idx} names a protective device or work on equipment (alarm, trip, contactor, "
                "probe, hand mode...). The approving steward must confirm a safety review, and it is "
                "shown as guidance only: it never raises confidence.")
        kept.append({
            "check_cause": check_cause,
            "safety_review": safety_review,
            # This item's own warnings, so the review card can show them in place.
            "notes": warnings[notes_from:],
            "off_topic": off_topic,
            "symptom_pattern": symptom,
            "likely_cause": cause,
            "cause_label": cause_label(cause),
            "asset_type": owner,
            "new_cause": is_new,
            **lists,
            "evidence_quote": quote,
        })
    return kept, warnings


def _sanitize(transcript: str) -> tuple[str, list[str]]:
    if not transcript or not transcript.strip():
        raise CaptureError("transcript is empty")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise CaptureError(f"transcript exceeds {MAX_TRANSCRIPT_CHARS} characters")
    sanitized = sanitize_metadata(transcript)
    # Redact the whole sentence around an injection attempt, not only the
    # matched phrase, so no fragment of it can be quoted into knowledge.
    sanitized = re.sub(r"[^.!?\n]*\[REDACTED[^\]]*\][^.!?\n]*[.!?]?", " [REDACTED-INJECTION].", sanitized)
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
        "provider": provider if provider in ("adp", "mock", "manual") else llm.provider_name(),
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

Interviewer: What about the chilled water pumps?

Senior technician: If the axial vibration is high and the 2x peak dominates, that's misalignment at the coupling. Check the alignment with the laser kit before you touch anything else. Never just tighten the base bolts and hope, the vibration comes straight back.
"""

