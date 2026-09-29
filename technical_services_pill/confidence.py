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

from .models import MIN_EVIDENCE_COUNT, EvidenceItem

# --- 【ASSUMPTION】 tunable weights (spec §4.3) -----------------------------
W1 = 0.30  # evidence_coverage  (fraction of decision-tree branches resolvable)
W2 = 0.20  # peer_agreement     (do peer sensors / adjacent assets corroborate?)
W3 = 0.25  # kb_match           (similarity to validated past cases via RAG)
W4 = 0.10  # data_staleness     (penalty: telemetry older than freshness SLA)
W5 = 0.15  # conflict_penalty   (penalty: contradictions in evidence)


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
    "W1",
    "W2",
    "W3",
    "W4",
    "W5",
    "MIN_EVIDENCE_COUNT",
    "score_confidence",
    "evidence_coverage_score",
]