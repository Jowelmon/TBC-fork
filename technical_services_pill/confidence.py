"""Deterministic confidence scorer (spec §4.3).

    confidence = w1*evidence_coverage
               + w2*peer_agreement
               + w3*kb_match
               - w4*data_staleness
               - w5*conflict_penalty

The result is clamped to [0.0, 1.0]. The scorer is pure and LLM-independent:
identical inputs yield identical confidence, which keeps the agent's
DIAGNOSING -> RECOMMANDING | ESCALATED routing (spec §2) auditable and
unit-testable.

【ASSUMPTION】 The weights W1..W5 are tunable heuristics (spec §4.3, Appendix A
#5). They default to 0.30 / 0.20 / 0.25 / 0.10 / 0.15 and MUST be calibrated
against validated historical cases with Keppel SMEs before deployment. With
the defaults the positive terms sum to 0.75, so a fully-grounded, peer-corroborated,
KB-matched diagnosis with no penalties tops out at 0.75 — deliberately
conservative (you can never be 100% confident from indirect evidence alone).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import MIN_EVIDENCE_COUNT, EvidenceItem

# --- 【ASSUMPTION】 tunable weights (spec §4.3) -----------------------------
W1 = 0.30  # evidence_coverage  (fraction of decision-tree branches resolvable)
W2 = 0.20  # peer_agreement     (do peer sensors / adjacent assets corroborate?)
W3 = 0.25  # kb_match           (similarity to validated past cases via RAG)
W4 = 0.10  # data_staleness     (penalty: telemetry older than freshness SLA)
W5 = 0.15  # conflict_penalty   (penalty: contradictions in evidence)

# --- Freshness SLA per evidence source, in minutes (W4) --------------------
# 【ASSUMPTION】 illustrative; calibrate against real telemetry latency.
_FRESHNESS_SLA_MINUTES: dict[str, float] = {
    "sensor": 30.0,
    "bms": 15.0,
    "history": 24 * 60.0,
    "config": 24 * 60.0,
    "case_memory": 24 * 60.0,
}
_DEFAULT_SLA_MINUTES = 60.0
# Evidence gathered within the same request is fresh: without this grace the
# milliseconds between gathering and scoring would make scores irreproducible.
_FRESH_GRACE_MINUTES = 1.0


def peer_agreement_from_registry(asset_id: str, sensor_id: str | None) -> float:
    """Peer corroboration from real peer sensors / adjacent assets (W2).

    Only applies where ``mock_registry`` actually models individual sensors
    for the asset (CRAH, today): the fraction of that asset's OTHER sensors
    currently reporting "ok". With no sensors of its own on the asset, it
    falls back to sibling assets of the SAME type sharing a parent system;
    with none of those either, it defaults to 0.5 (no signal either way).

    Equipment types the registry has no sensor-level model for at all
    (Chiller/UPS/Pump in this demo — they report generic telemetry, not
    discrete Sensor objects) stay at a neutral 1.0: there is no peer concept
    to measure, so defaulting them to 0.5 would penalise a registry gap
    rather than a real disagreement.
    """
    from .mock_registry import ASSETS, LIVE_READINGS, SENSORS

    asset_sensor_ids = [s["id"] for s in SENSORS.values() if s["asset_id"] == asset_id]
    if not asset_sensor_ids:
        return 1.0  # no sensor-level model for this asset type

    peer_ids = [sid for sid in asset_sensor_ids if sid != sensor_id]
    asset = ASSETS.get(asset_id)
    if not peer_ids and asset:
        parent = asset.get("parent_system_id")
        asset_type = asset.get("type")
        for other in ASSETS.values():
            if (
                other["id"] != asset_id
                and other.get("parent_system_id") == parent
                and other.get("type") == asset_type
            ):
                peer_ids += [s["id"] for s in SENSORS.values() if s["asset_id"] == other["id"]]

    if not peer_ids:
        return 0.5  # a real peer slot exists in principle, but none is populated

    statuses = [LIVE_READINGS.get(pid, {}).get("status") for pid in peer_ids]
    healthy = sum(1 for s in statuses if s == "ok")
    return healthy / len(statuses)


def _staleness_from_age(evidence: list[EvidenceItem], *, now: datetime | None = None) -> float:
    """W4: how far evidence has drifted past its source's freshness SLA.

    Uses each item's own ``retrieved_at`` against ``now`` — not a payload
    flag nothing ever sets. In a live request this is ~0 (evidence is
    gathered moments before scoring); it only bites when older evidence is
    reused unchanged (e.g. re-scoring a case against today's KB).
    """
    now = now or datetime.now(timezone.utc)
    worst = 0.0
    for ev in evidence:
        sla = _FRESHNESS_SLA_MINUTES.get(ev.source, _DEFAULT_SLA_MINUTES)
        if sla <= 0:
            continue
        retrieved = ev.retrieved_at
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        age_minutes = (now - retrieved).total_seconds() / 60.0
        if age_minutes < _FRESH_GRACE_MINUTES:
            continue
        worst = max(worst, min(1.0, age_minutes / sla))
    return worst


def _conflict_from_evidence(evidence: list[EvidenceItem]) -> float:
    """W5: penalty from genuinely contradictory evidence pairs.

    Flags boolean-valued payload fields that appear under the same key in
    more than one evidence item but disagree (e.g. one source reporting a
    bus reachable while another reports it unreachable) — not a payload
    flag nothing ever sets.
    """
    seen: dict[str, bool] = {}
    conflicts = 0
    for ev in evidence:
        payload = ev.payload or {}
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if not isinstance(value, bool):
                continue
            if key in seen:
                if seen[key] != value:
                    conflicts += 1
            else:
                seen[key] = value
    return min(1.0, 0.5 * conflicts)


def derive_confidence_signals(
    evidence: list[EvidenceItem], *, asset_id: str, sensor_id: str | None = None,
) -> dict[str, float]:
    """Derive runtime peer-corroboration and penalty signals from evidence.

    This keeps the scoring model from silently assuming perfect corroboration
    or a clean, fresh evidence set when the live data does not support it.
    """
    return {
        "peer_agreement": peer_agreement_from_registry(asset_id, sensor_id),
        "data_staleness": _staleness_from_age(evidence),
        "conflict_penalty": _conflict_from_evidence(evidence),
    }


def score_confidence(
    *,
    evidence_coverage: float,
    peer_agreement: float = 1.0,
    kb_match: float = 0.0,
    data_staleness: float = 0.0,
    conflict_penalty: float = 0.0,
) -> float:
    """Compute clamped confidence in [0.0, 1.0].

    All inputs are expected in [0.0, 1.0]. ``evidence_coverage`` is the only
    required argument (it is the primary signal); the others default to
    "no extra support, no penalties". The keyword-only signature prevents
    positional mix-ups between the four 0-1 floats.
    """
    raw = (
        W1 * evidence_coverage
        + W2 * peer_agreement
        + W3 * kb_match
        - W4 * data_staleness
        - W5 * conflict_penalty
    )
    return max(0.0, min(1.0, raw))


def evidence_coverage_score(
    evidence: list[EvidenceItem], total_branches: int
) -> float:
    """Approximate ``evidence_coverage`` from the retrieved evidence set.

    Models "fraction of decision-tree branches resolvable with retrieved data"
    (spec §4.3) as ``min(1.0, len(evidence) / total_branches)``: each piece of
    evidence is treated as resolving one branch of the Q1-Q7 tree. When
    ``total_branches <= 0`` the coverage is undefined and returns 0.0.

    This is a deliberate 【ASSUMPTION】 approximation. A richer implementation
    would flag each branch as resolved by inspecting the evidence payloads; the
    decision tree in ``decision_tree.py`` is the source of truth for which
    branches actually resolved. Callers who already know that fraction should
    pass it directly to :func:`score_confidence` instead of using this helper.
    """
    if total_branches <= 0:
        return 0.0
    return min(1.0, len(evidence) / float(total_branches))


# Re-exported for convenience so callers can compute the coverage approximation
# based on the spec's minimum evidence count without importing models separately.
__all__ = [
    "MIN_EVIDENCE_COUNT",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5",
    "evidence_coverage_score",
    "score_confidence",
]