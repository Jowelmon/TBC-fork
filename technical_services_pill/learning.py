"""Closed-loop learning store (spec §7 governance feedback -> knowledge base).

The learning loop closes the gap between a rule-based decision tree and a
genuinely *self-improving* intelligence pill:

    diagnosis -> recommendation -> human decision -> outcome
        -> submit_feedback  ──▶  LearningStore.record(case)
                                     ├─ appends a ValidatedCase to the KB
                                     ├─ updates per-cause empirical priors
                                     └─ is retrieved by future get_similar_cases
                                            └─ feeds `kb_match` into score_confidence

All assumed thresholds below are tagged ``【ASSUMPTION]`` (spec Appendix A #5):
tunable, must be validated with Keppel technical-services SMEs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FeedbackRecord, ValidatedCase


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(signature: str) -> set[str]:
    return {t for t in signature.lower().replace("_", " ").split() if t}


def jaccard(a: str, b: str) -> float:
    sa, sb = _tokenize(a), _tokenize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class LearningStore:
    """In-memory validated-case library + per-cause empirical priors.

    Seeded from the mock registry's pre-validated KB cases so retrieval is
    useful before any feedback is ever submitted.
    """

    def __init__(self) -> None:
        self.validated: list[ValidatedCase] = []
        self._cause_stats: dict[str, dict[str, int]] = {}  # cause -> {confirmed, total}
        self._seed_from_registry()

    # ------------------------------------------------------------------ #
    def _seed_from_registry(self) -> None:
        try:
            from .mock_registry import get_registry

            kb = get_registry()["KNOWLEDGE_BASE"]["cases"]
        except Exception:
            kb = []
        for i, c in enumerate(kb):
            cause = c.get("root_cause", "")
            vc = ValidatedCase(
                id=c.get("kb_ref") or c.get("id") or f"KB-SEED-{i:03d}",
                case_id="SEED",
                asset_id="SEED",
                asset_type=c.get("asset_type", "CRAH"),
                fault_signature=c.get("fault_signature", ""),
                proposed_cause=cause,
                confirmed_cause=cause,
                action_taken=c.get("action_taken", ""),
                outcome=c.get("outcome", "resolved"),
                confidence=0.8,
                validated_by="historical_kb",
                corrected=False,
                weight=1.0,
                created_at=_now(),
            )
            self._ingest(vc)

    def _ingest(self, vc: ValidatedCase) -> None:
        self.validated.append(vc)
        st = self._cause_stats.setdefault(vc.confirmed_cause, {"confirmed": 0, "total": 0})
        st["total"] += 1
        if vc.outcome == "resolved":
            st["confirmed"] += 1

    # ------------------------------------------------------------------ #
    def record_feedback(self, fb: FeedbackRecord, *, confidence: float, action_taken: str = "") -> ValidatedCase:
        """Promote a feedback record to a validated case in the KB."""
        vc = ValidatedCase(
            id=f"KB-FB-{fb.feedback_id}",
            case_id=fb.case_id,
            asset_id=fb.asset_id,
            asset_type=fb.asset_type,
            fault_signature=fb.corrections.get("fault_signature", ""),
            proposed_cause=fb.proposed_cause or fb.confirmed_cause,
            confirmed_cause=fb.confirmed_cause,
            action_taken=action_taken or fb.corrections.get("action_taken", ""),
            outcome=fb.corrections.get("outcome", "resolved"),
            confidence=confidence,
            validated_by=fb.submitted_by,
            corrected=(fb.proposed_cause is not None and fb.proposed_cause != fb.confirmed_cause),
            weight=1.0,
            created_at=_now(),
        )
        self._ingest(vc)
        return vc

    # ------------------------------------------------------------------ #
    def get_similar(self, fault_signature: str, asset_type: str | None = None, k: int = 3) -> list[ValidatedCase]:
        """Top-k validated cases by Jaccard token overlap + asset-type bonus."""
        scored: list[tuple[float, ValidatedCase]] = []
        for vc in self.validated:
            sim = jaccard(fault_signature, vc.fault_signature)
            if asset_type and vc.asset_type == asset_type:
                sim += 0.1  # 【ASSUMPTION】 asset-type prior bonus
            sim *= vc.weight
            scored.append((sim, vc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [vc for s, vc in scored[:k] if s > 0.0]

    # ------------------------------------------------------------------ #
    def cause_prior(self, cause_id: str) -> float:
        """Empirical confirmation rate for a cause in [0,1] (0.6 default if unseen).

        【ASSUMPTION】 the 0.6 cold-start prior — tunable.
        """
        st = self._cause_stats.get(cause_id)
        if not st or st["total"] == 0:
            return 0.6
        return st["confirmed"] / st["total"]

    def kb_match_score(self, fault_signature: str, confirmed_cause: str, asset_type: str | None = None) -> float:
        """0-1 score: how well the KB supports (signature, cause) for this case.

        Combines best-similarity of matching cases with the cause's empirical
        confirmation rate. Used as ``kb_match`` input to ``score_confidence``.
        """
        similar = self.get_similar(fault_signature, asset_type, k=3)
        if not similar:
            return 0.2  # 【ASSUMPTION】 low-but-nonzero baseline
        best_sim = max(jaccard(fault_signature, vc.fault_signature) for vc in similar if vc.confirmed_cause == confirmed_cause) if any(vc.confirmed_cause == confirmed_cause for vc in similar) else 0.0
        prior = self.cause_prior(confirmed_cause)
        # weight similarity 0.6, prior 0.4  【ASSUMPTION】
        return min(1.0, 0.6 * best_sim + 0.4 * prior)

    # ------------------------------------------------------------------ #
    def stats(self) -> dict[str, Any]:
        return {
            "total_validated_cases": len(self.validated),
            "feedback_added": sum(1 for vc in self.validated if vc.case_id != "SEED"),
            "corrected_count": sum(1 for vc in self.validated if vc.corrected),
            "cause_priors": {
                cause: {"confirmed": st["confirmed"], "total": st["total"], "rate": round(st["confirmed"] / st["total"], 3)}
                for cause, st in self._cause_stats.items()
            },
        }


# module-level singleton for the app + demo
STORE = LearningStore()