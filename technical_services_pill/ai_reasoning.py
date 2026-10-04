"""Tencent Cloud ADP / LLM adapter boundary.

This module keeps Tencent-specific integration isolated behind a stable internal
interface. The rest of the application should not call network code directly.
When the environment is not configured or the service is unavailable, a safe,
structured fallback is returned instead of breaking the deterministic workflow.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

_DEFAULT_FALLBACK = {
    "status": "unavailable",
    "hypothesis": None,
    "confidence": 0.0,
    "summary": "ADP unavailable; deterministic diagnosis remains authoritative.",
    "supporting_evidence": [],
    "conflicting_evidence": [],
    "missing_evidence": [],
    "recommended_next_check": "Collect missing evidence and require human approval.",
}


def _env_var(name: str) -> str | None:
    return os.getenv(name)


def _llm_configured() -> bool:
    return bool(
        _env_var("TENCENT_ADP_APP_KEY")
        and _env_var("TENCENT_ADP_API_SECRET")
        and _env_var("TENCENT_ADP_ENDPOINT")
    )


def _build_payload(**kwargs: Any) -> dict[str, Any]:
    asset = kwargs.get("asset") or {}
    observations = kwargs.get("observations") or {}
    evidence = kwargs.get("evidence") or []
    candidate_causes = kwargs.get("candidate_causes") or []
    knowledge = kwargs.get("knowledge") or []
    return {
        "asset": {
            "asset_id": asset.get("asset_id"),
            "asset_type": asset.get("asset_type"),
        },
        "observations": observations,
        "evidence": [
            {
                "source": item.get("source"),
                "finding": item.get("finding") or item.get("summary") or item.get("type"),
            }
            for item in evidence
        ],
        "candidate_causes": list(candidate_causes),
        "validated_knowledge": knowledge,
    }


def _validate_response(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("AI response must be an object")
    cleaned = dict(data)
    cleaned.setdefault("status", "ok")
    cleaned.setdefault("hypothesis", cleaned.get("hypothesis") or cleaned.get("recommended_cause"))
    cleaned.setdefault("confidence", float(cleaned.get("confidence", 0.0) or 0.0))
    cleaned.setdefault("summary", cleaned.get("summary") or "")
    cleaned.setdefault("supporting_evidence", cleaned.get("supporting_evidence") or [])
    cleaned.setdefault("conflicting_evidence", cleaned.get("conflicting_evidence") or [])
    cleaned.setdefault("missing_evidence", cleaned.get("missing_evidence") or [])
    cleaned.setdefault("recommended_next_check", cleaned.get("recommended_next_check") or "")
    return cleaned


def _fallback_response(candidate_causes: list[str] | None = None) -> dict[str, Any]:
    fallback = dict(_DEFAULT_FALLBACK)
    if candidate_causes:
        fallback["hypothesis"] = candidate_causes[0]
        fallback["summary"] = (
            f"Deterministic candidate causes were {candidate_causes}; "
            "ADP was unavailable so the human remains accountable."
        )
    return fallback


def generate_diagnostic_hypothesis(
    *,
    asset: dict[str, Any],
    observations: dict[str, Any],
    evidence: list[dict[str, Any]],
    candidate_causes: list[str],
    knowledge: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Request a bounded ADP hypothesis used only for human review.

    Returns a structured JSON payload even when the LLM is unavailable.
    """
    payload = _build_payload(
        asset=asset,
        observations=observations,
        evidence=evidence,
        candidate_causes=candidate_causes,
        knowledge=knowledge or [],
    )

    if not _llm_configured():
        return _fallback_response(candidate_causes)

    endpoint = _env_var("TENCENT_ADP_ENDPOINT")
    req = request.Request(
        endpoint,
        data=json.dumps({"messages": [{"role": "user", "content": json.dumps(payload)}]}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-App-Key": _env_var("TENCENT_ADP_APP_KEY") or "",
            "X-API-Secret": _env_var("TENCENT_ADP_API_SECRET") or "",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            result = _validate_response(data)
            if not result.get("hypothesis"):
                raise ValueError("AI result missing hypothesis")
            return result
    except (ValueError, TypeError, json.JSONDecodeError, error.URLError, TimeoutError):
        return _fallback_response(candidate_causes)


__all__ = ["generate_diagnostic_hypothesis"]
