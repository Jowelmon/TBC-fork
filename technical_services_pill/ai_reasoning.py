"""Advisory AI second opinion on a completed rule-based diagnosis.

The deterministic decision tree (``decision_tree.py``) always decides first;
this module only asks a model to sanity-check that decision for the human
Asset Operations Manager. It never feeds back into routing: callers display
``generate_diagnostic_hypothesis``'s result, they never branch on it.

Boundary enforced here, in order:
1. G7 sanitise every piece of sensor/evidence text before the model sees it
   (``guardrails.sanitize_metadata``).
2. Call the model through ``llm.diagnostic_second_opinion`` (same provider
   seam as expert capture: ``mock`` offline, ``adp`` for Tencent Cloud).
3. Validate the shape and ground it: a hypothesis outside the supplied
   candidate causes is rejected; evidence citations that don't appear in the
   evidence actually supplied are dropped.
4. Any failure (bad provider, timeout, malformed JSON) returns the same safe
   ``unavailable`` fallback — the deterministic diagnosis is never blocked by
   this call.
"""
from __future__ import annotations

from typing import Any

from .guardrails import sanitize_metadata
from .llm import LLMError, diagnostic_second_opinion

_DEFAULT_FALLBACK: dict[str, Any] = {
    "status": "unavailable",
    "hypothesis": None,
    "agrees_with_rules": False,
    "summary": "AI second opinion unavailable; the rule-based diagnosis remains authoritative.",
    "supporting_evidence": [],
    "conflicting_evidence": [],
    "missing_evidence": [],
    "recommended_next_check": "Collect missing evidence and require human approval.",
}


def _fallback(reason: str) -> dict[str, Any]:
    out = dict(_DEFAULT_FALLBACK)
    out["summary"] = f"{out['summary']} ({reason})"
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _ground(items: Any, haystack: str) -> list[str]:
    """Keep only citations that actually appear in the supplied evidence."""
    if not isinstance(items, list):
        return []
    kept = []
    for item in items:
        text = str(item).strip()
        if text and _norm(text) in haystack:
            kept.append(text)
    return kept[:8]


def _validate(
    data: Any, *, candidate_causes: list[str], evidence_text: list[str], rule_top_cause: str | None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")

    haystack = _norm(" \n ".join(evidence_text))
    hypothesis = data.get("hypothesis")
    if hypothesis is not None and hypothesis not in candidate_causes:
        # The model named a cause we never offered it: untrustworthy, drop it.
        hypothesis = None

    return {
        "status": "ok",
        "hypothesis": hypothesis,
        # Computed from the grounded hypothesis, not taken on the model's
        # word, so "agrees" is always consistent with what is shown.
        "agrees_with_rules": bool(hypothesis) and hypothesis == rule_top_cause,
        "summary": str(data.get("summary") or "").strip()[:500],
        "supporting_evidence": _ground(data.get("supporting_evidence"), haystack),
        "conflicting_evidence": _ground(data.get("conflicting_evidence"), haystack),
        "missing_evidence": [str(m).strip()[:200] for m in (data.get("missing_evidence") or []) if str(m).strip()][:8],
        "recommended_next_check": str(data.get("recommended_next_check") or "").strip()[:300],
    }


def generate_diagnostic_hypothesis(
    *,
    asset: dict[str, Any],
    observations: dict[str, Any],
    evidence: list[dict[str, Any]],
    candidate_causes: list[str],
    rule_top_cause: str | None = None,
    knowledge: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Request a bounded, advisory second opinion for human review.

    Always returns a structured JSON payload, even when the model is
    unavailable or returns something unusable — the caller never needs to
    special-case failure.
    """
    asset_type = sanitize_metadata(str(asset.get("asset_type") or ""))
    sensor_id = sanitize_metadata(str(observations.get("sensor_id") or ""))
    obs_text = f"{observations.get('type', '')} on {sensor_id}: reading {observations.get('reading_status', '')}"

    evidence_text = [sanitize_metadata(obs_text)]
    for item in evidence:
        finding = sanitize_metadata(str(item.get("finding") or ""))
        summary = sanitize_metadata(str(item.get("summary") or ""))
        source = sanitize_metadata(str(item.get("source") or ""))
        conflict = " [conflict]" if item.get("conflict") is True else ""
        evidence_text.append(f"{source} {finding}: {summary}{conflict}")

    knowledge_text = [
        sanitize_metadata(f"{k.get('cause', '')} -> {k.get('kb_ref', '')}")
        for k in (knowledge or [])
    ]

    try:
        raw = diagnostic_second_opinion(
            asset_type=asset_type,
            rule_top_cause=rule_top_cause,
            candidate_causes=list(candidate_causes),
            evidence=evidence_text,
            knowledge=knowledge_text,
        )
        return _validate(
            raw,
            candidate_causes=candidate_causes,
            evidence_text=evidence_text,
            rule_top_cause=rule_top_cause,
        )
    except (LLMError, ValueError, TypeError) as exc:
        return _fallback(str(exc) or exc.__class__.__name__)


__all__ = ["generate_diagnostic_hypothesis"]
