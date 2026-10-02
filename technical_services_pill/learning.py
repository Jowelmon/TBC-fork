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

F2: Feedback governance via proposals. Feedback no longer enters the live KB
directly — it creates a pending proposal that must be approved by a knowledge
steward before it is ingested. Rejected proposals are recorded for audit.
Rollback removes all cases added after a target KB version.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .models import FeedbackRecord, ValidatedCase

SEED_KB_MAJOR = 1
SEED_KB_MINOR = 3


def kb_version_label(approved_updates: int) -> str:
    """Map the internal approval counter to the displayed semantic version."""
    return f"{SEED_KB_MAJOR}.{SEED_KB_MINOR + approved_updates}.0"


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

    F2: Feedback goes through a proposal workflow:
      - ``record_feedback`` creates a *pending proposal* (not ingested).
      - ``approve_proposal`` ingests the proposal into the live KB and
        increments the KB version.
      - ``reject_proposal`` marks the proposal as rejected (audit trail).
      - ``rollback`` removes all cases added after a target KB version.
    """

    def __init__(self) -> None:
        self.validated: list[ValidatedCase] = []
        self._cause_stats: dict[str, dict[str, int]] = {}  # cause -> {confirmed, total}
        self._proposals: list[dict[str, Any]] = []
        self._kb_version: int = 0  # 0 = seeded registry only
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
                kb_version=0,
            )
            self._ingest(vc)

    def _ingest(self, vc: ValidatedCase) -> None:
        self.validated.append(vc)
        st = self._cause_stats.setdefault(vc.confirmed_cause, {"confirmed": 0, "total": 0})
        st["total"] += 1
        if vc.outcome == "resolved":
            st["confirmed"] += 1

    def _remove(self, vc: ValidatedCase) -> None:
        """Remove a validated case and update stats."""
        try:
            self.validated.remove(vc)
        except ValueError:
            return
        st = self._cause_stats.get(vc.confirmed_cause)
        if st:
            st["total"] = max(0, st["total"] - 1)
            if vc.outcome == "resolved":
                st["confirmed"] = max(0, st["confirmed"] - 1)
            if st["total"] == 0:
                del self._cause_stats[vc.confirmed_cause]

    # ------------------------------------------------------------------ #
    # F2: Proposal workflow
    # ------------------------------------------------------------------ #
    def record_feedback(self, fb: FeedbackRecord, *, confidence: float, action_taken: str = "") -> dict:
        """Create a pending proposal from feedback (NOT ingested into KB yet).

        F2: Feedback no longer enters the live KB directly. It creates a
        proposal with status 'pending' that must be approved by a knowledge
        steward before it is ingested.
        """
        proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
        proposal: dict[str, Any] = {
            "proposal_id": proposal_id,
            "feedback_id": fb.feedback_id,
            "case_id": fb.case_id,
            "asset_id": fb.asset_id,
            "asset_type": fb.asset_type,
            "confirmed_cause": fb.confirmed_cause,
            "proposed_cause": fb.proposed_cause,
            "corrected": fb.proposed_cause is not None and fb.proposed_cause != fb.confirmed_cause,
            "confidence": confidence,
            "action_taken": action_taken,
            "fault_signature": fb.corrections.get("fault_signature", ""),
            "outcome": fb.corrections.get("outcome", "resolved"),
            "submitted_by": fb.submitted_by,
            "status": "pending",
            "created_at": _now(),
            "decided_by": None,
            "decided_at": None,
            "reason": None,
            "kb_version": None,
        }
        self._proposals.append(proposal)
        return proposal

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        """All proposals with status 'pending'."""
        return [p for p in self._proposals if p["status"] == "pending"]

    def list_all_proposals(self) -> list[dict[str, Any]]:
        """All proposals (pending, approved, rejected) for audit."""
        return list(self._proposals)

    def _find_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        for p in self._proposals:
            if p["proposal_id"] == proposal_id:
                return p
        return None

    def _find_by_feedback_id(self, feedback_id: str) -> dict[str, Any] | None:
        for p in self._proposals:
            if p["feedback_id"] == feedback_id:
                return p
        return None

    def approve_proposal(self, proposal_id: str, *, decided_by: str) -> dict[str, Any]:
        """Approve a pending proposal and ingest it into the live KB."""
        p = self._find_proposal(proposal_id)
        if p is None:
            raise ValueError(f"proposal {proposal_id} not found")
        if p["status"] != "pending":
            raise ValueError(f"proposal {proposal_id} is {p['status']}, not pending")
        p["status"] = "approved"
        p["decided_by"] = decided_by
        p["decided_at"] = _now()
        self._kb_version += 1
        p["kb_version"] = self._kb_version
        vc = ValidatedCase(
            id=f"KB-FB-{p['feedback_id']}",
            case_id=p["case_id"],
            asset_id=p["asset_id"],
            asset_type=p["asset_type"],
            fault_signature=p["fault_signature"],
            proposed_cause=p["proposed_cause"] or p["confirmed_cause"],
            confirmed_cause=p["confirmed_cause"],
            action_taken=p["action_taken"],
            outcome=p["outcome"],
            confidence=p["confidence"],
            validated_by=p["submitted_by"],
            corrected=p["corrected"],
            weight=1.0,
            created_at=_now(),
            kb_version=self._kb_version,
        )
        self._ingest(vc)
        p["validated_case_id"] = vc.id
        return p

    def approve_by_feedback_id(self, feedback_id: str, *, decided_by: str) -> dict[str, Any]:
        """Convenience: approve the proposal created from a given feedback_id."""
        p = self._find_by_feedback_id(feedback_id)
        if p is None:
            raise ValueError(f"no proposal for feedback_id {feedback_id}")
        return self.approve_proposal(p["proposal_id"], decided_by=decided_by)

    def reject_proposal(self, proposal_id: str, *, decided_by: str, reason: str) -> dict[str, Any]:
        """Reject a pending proposal (not ingested into KB)."""
        p = self._find_proposal(proposal_id)
        if p is None:
            raise ValueError(f"proposal {proposal_id} not found")
        if p["status"] != "pending":
            raise ValueError(f"proposal {proposal_id} is {p['status']}, not pending")
        p["status"] = "rejected"
        p["decided_by"] = decided_by
        p["decided_at"] = _now()
        p["reason"] = reason
        return p

    def rollback(self, target_version: int) -> dict[str, Any]:
        """Remove all validated cases added after ``target_version``.

        Seed cases (kb_version=0) are never removed. Resets _kb_version to
        target_version.
        """
        if target_version < 0:
            raise ValueError("target_version must be >= 0")
        if target_version > self._kb_version:
            raise ValueError(
                f"target_version {target_version} > current version {self._kb_version}"
            )
        removed: list[ValidatedCase] = [
            vc for vc in self.validated if vc.kb_version > target_version
        ]
        for vc in removed:
            self._remove(vc)
        # Mark approved proposals after target_version as rolled back
        rolled_back: list[str] = []
        for p in self._proposals:
            if p.get("kb_version") and p["kb_version"] > target_version:
                p["status"] = "rolled_back"
                rolled_back.append(p["proposal_id"])
        self._kb_version = target_version
        return {
            "rolled_back_to": target_version,
            "removed_cases": len(removed),
            "rolled_back_proposals": rolled_back,
        }

    def get_kb_version(self) -> int:
        return self._kb_version

    def get_kb_version_label(self) -> str:
        """Human-facing semantic version. Seed knowledge is 1.3.0; each
        steward-approved proposal bumps the minor version (1.3.0 -> 1.4.0)."""
        return kb_version_label(self._kb_version)

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
        matching = [vc for vc in similar if vc.confirmed_cause == confirmed_cause]
        best_sim = (
            max(jaccard(fault_signature, vc.fault_signature) for vc in matching)
            if matching
            else 0.0
        )
        prior = self.cause_prior(confirmed_cause)
        # weight similarity 0.6, prior 0.4  【ASSUMPTION】
        return min(1.0, 0.6 * best_sim + 0.4 * prior)

    # ------------------------------------------------------------------ #
    def stats(self) -> dict[str, Any]:
        return {
            "total_validated_cases": len(self.validated),
            "feedback_added": sum(1 for vc in self.validated if vc.case_id != "SEED"),
            "corrected_count": sum(1 for vc in self.validated if vc.corrected),
            "pending_proposals": len(self.list_pending_proposals()),
            "kb_version": self._kb_version,
            "kb_version_label": self.get_kb_version_label(),
            "cause_priors": {
                cause: {"confirmed": st["confirmed"], "total": st["total"], "rate": round(st["confirmed"] / st["total"], 3)}
                for cause, st in self._cause_stats.items()
            },
        }


# module-level singleton for the app + demo
STORE = LearningStore()