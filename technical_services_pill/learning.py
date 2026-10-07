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

from .cause_registry import cause_label
from .models import FeedbackRecord, ValidatedCase

SEED_KB_MAJOR = 1
SEED_KB_MINOR = 3


class SelfApprovalError(ValueError):
    """Raised when the approver of a knowledge proposal is its proposer."""


def kb_version_label(version: int) -> str:
    """Map a KB version number to its displayed semantic version.

    Version numbers are allocated once and never reused (a rollback does not
    rewind the counter), so a label always names exactly one KB state.
    """
    return f"{SEED_KB_MAJOR}.{SEED_KB_MINOR + version}.0"


LEDGER_FIELDS = (
    "seq", "at", "actor", "action", "proposal_id", "reason",
    "version_before", "version_after", "kb_digest",
)


_STOP = {
    "with", "when", "what", "that", "this", "then", "than", "there", "their", "they", "from",
    "have", "will", "your", "into", "before", "after", "anything", "else", "fine", "every",
    "week", "usually", "story", "especially", "almost", "never", "always", "just", "only",
    "first", "thing", "look", "check", "sure", "make", "it's", "that's", "sensor", "sensors",
    "pump", "chiller", "unit", "ups", "crah", "if", "the", "and", "for", "you", "it",
}


def _terms(text: str) -> set[str]:
    import re

    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOP and (len(w) >= 4 or any(c.isdigit() for c in w))}


def corroborating_terms(heuristic_text: str, evidence_terms: set[str] | None) -> list[str]:
    """Distinctive words of an expert's described condition that also
    appear in a case's evidence. Empty means the case does not show what
    the expert said to look for."""
    if not evidence_terms:
        return []
    return sorted(_terms(heuristic_text) & evidence_terms)


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
        # Highest version number ever issued. Never decremented, so labels
        # are never reused after a rollback.
        self._version_seq: int = 0
        self._versions: list[dict[str, Any]] = [{
            "version": 0, "status": "live", "proposal_id": None,
            "created_by": "seed", "created_at": _now(),
        }]
        # Keyed, hash-chained record of every governance action. Each entry
        # also carries a digest of the KB's contents and proposals, and the
        # chain is sealed, so editing knowledge or truncating the ledger is
        # caught, not only editing an entry.
        self.ledger: list[dict[str, Any]] = []
        self.ledger_seal: str | None = None
        # (version of the withdrawn knowledge, ledger seq of the withdrawal)
        self._revocations: list[dict[str, int]] = []
        # Expert heuristics captured from interviews, live once approved.
        self.expert_heuristics: list[dict[str, Any]] = []
        self._seed_from_registry()
        self._log(actor="system", action="seeded",
                  reason=f"seed knowledge base: {len(self.validated)} validated cases")

    # ------------------------------------------------------------------ #
    # Governance ledger
    # ------------------------------------------------------------------ #
    def _log(self, *, actor: str, action: str, proposal_id: str | None = None,
             reason: str = "", version_before: int | None = None,
             version_after: int | None = None) -> dict[str, Any]:
        from .audit import GENESIS_HASH, compute_hash

        before = self._kb_version if version_before is None else version_before
        after = self._kb_version if version_after is None else version_after
        entry: dict[str, Any] = {
            "seq": len(self.ledger) + 1,
            "at": _now().isoformat(),
            "actor": actor,
            "action": action,
            "proposal_id": proposal_id,
            "reason": reason,
            "version_before": before,
            "version_after": after,
            "kb_digest": self._kb_digest(),
            "prev_hash": self.ledger[-1]["hash"] if self.ledger else GENESIS_HASH,
        }
        entry["hash"] = compute_hash(entry["prev_hash"], {f: entry[f] for f in LEDGER_FIELDS})
        self.ledger.append(entry)
        self.ledger_seal = compute_hash("seal", {"length": len(self.ledger), "head": entry["hash"]})
        return entry

    def _kb_digest(self) -> str:
        """SHA-256 over the knowledge the engine actually uses and every
        proposal's status, so edits outside the governance flow show up."""
        import hashlib

        from .audit import canonical_json

        material = {
            "kb_version": self._kb_version,
            "version_seq": self._version_seq,
            "versions": [(v["version"], v["status"]) for v in self._versions],
            "validated": sorted(
                (vc.id, vc.case_id, vc.asset_type, vc.confirmed_cause, vc.outcome,
                 vc.kb_version, vc.weight, vc.fault_signature, vc.validated_by)
                for vc in self.validated
            ),
            "heuristics": sorted(
                (h["id"], h["likely_cause"], h["asset_type"], h["evidence_quote"],
                 h["kb_version"], h["approved_by"])
                for h in self.expert_heuristics
            ),
            "proposals": [
                (p["proposal_id"], p["status"], p.get("submitted_by"), p.get("decided_by"),
                 p.get("confirmed_cause"), p.get("asset_type"), p.get("kb_version"), p.get("reason"))
                for p in self._proposals
            ],
        }
        return hashlib.sha256(canonical_json(material).encode()).hexdigest()

    def verify_ledger(self) -> bool:
        from .audit import compute_hash, verify_chain

        if not self.ledger or not verify_chain(self.ledger, LEDGER_FIELDS):
            return False
        if self.ledger[-1]["kb_digest"] != self._kb_digest():
            return False
        return self.ledger_seal == compute_hash(
            "seal", {"length": len(self.ledger), "head": self.ledger[-1]["hash"]})

    def withdrawn_reason(self, kb_version_used: int | None, ledger_seq_at_use: int | None) -> str | None:
        """Why knowledge a case was scored against is no longer in force, or None."""
        if kb_version_used is None:
            return None
        live = {v["version"] for v in self._versions if v["status"] == "live"}
        if kb_version_used not in live:
            return f"KB v{kb_version_label(kb_version_used)} was rolled back after this case was diagnosed"
        for r in self._revocations:
            if r["proposal_version"] <= kb_version_used and r["ledger_seq"] > (ledger_seq_at_use or 0):
                return (f"knowledge approved in v{kb_version_label(r['proposal_version'])} "
                        "was revoked after this case was diagnosed")
        return None

    def revoke_proposal(self, proposal_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        """Withdraw one approved proposal's knowledge without rolling back
        anything else. The KB moves to a new version; the revocation is
        permanent (a later rollback does not bring it back)."""
        if not reason.strip():
            raise ValueError("a revocation needs a reason")
        p = self._find_proposal(proposal_id)
        if p is None:
            raise ValueError(f"proposal {proposal_id} not found")
        if p["status"] != "approved":
            raise ValueError(f"proposal {proposal_id} is {p['status']}, not approved")
        ids = set(p.get("expert_heuristic_ids") or [])
        if p.get("validated_case_id"):
            ids.add(p["validated_case_id"])
        for vc in [vc for vc in self.validated if vc.id in ids]:
            self._remove(vc)
        self.expert_heuristics = [h for h in self.expert_heuristics if h.get("proposal_id") != proposal_id]
        p["status"] = "revoked"
        version_before = self._kb_version
        self._version_seq += 1
        self._kb_version = self._version_seq
        self._versions.append({
            "version": self._kb_version, "status": "live", "proposal_id": None,
            "created_by": actor, "created_at": _now(),
        })
        self._revocations.append({"proposal_version": p["kb_version"], "ledger_seq": len(self.ledger) + 1})
        self._log(actor=actor, action="proposal_revoked", proposal_id=proposal_id,
                  reason=reason.strip(), version_before=version_before, version_after=self._kb_version)
        return {"revoked": proposal_id, "removed_items": len(ids), "kb_version": self._kb_version}

    def list_versions(self) -> list[dict[str, Any]]:
        return [{**v, "label": kb_version_label(v["version"])} for v in self._versions]

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
        from .cause_registry import canonicalize_cause_id

        vc.proposed_cause = canonicalize_cause_id(vc.proposed_cause) or vc.proposed_cause
        vc.confirmed_cause = canonicalize_cause_id(vc.confirmed_cause) or vc.confirmed_cause
        self.validated.append(vc)
        if vc.case_id == "EXPERT":
            # An interview is a claim, not an observed outcome: it never
            # moves the cause's confirmation rate.
            return
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
        if vc.case_id == "EXPERT":
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
            "kind": "outcome_feedback",
            "proposal_type": "CASE_FEEDBACK",
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
        self._log(actor=fb.submitted_by, action="proposal_submitted", proposal_id=proposal_id,
                  reason=f"outcome feedback on {fb.case_id}: {cause_label(fb.confirmed_cause)}")
        return proposal

    def record_escalation_resolution(
        self, *, case_id: str, asset_id: str, asset_type: str, confirmed_cause: str,
        proposed_cause: str | None, fault_signature: str, resolution: str,
        confidence: float, submitted_by: str,
    ) -> dict[str, Any]:
        """Queue how an expert resolved an escalation as a knowledge proposal.

        Escalations are where the pill did not know the answer, so the
        expert's resolution is exactly the know-how worth keeping. Approval
        works like outcome feedback: a different steward must approve it.
        """
        proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
        proposal: dict[str, Any] = {
            "proposal_id": proposal_id,
            "kind": "escalation_resolution",
            "proposal_type": "ESCALATION_RESOLUTION",
            "feedback_id": f"ESC-{uuid.uuid4().hex[:8].upper()}",
            "case_id": case_id,
            "asset_id": asset_id,
            "asset_type": asset_type,
            "confirmed_cause": confirmed_cause,
            "proposed_cause": proposed_cause,
            "corrected": proposed_cause is not None and proposed_cause != confirmed_cause,
            "confidence": confidence,
            "action_taken": resolution,
            "resolution": resolution,
            "fault_signature": fault_signature,
            "outcome": "resolved",
            "submitted_by": submitted_by,
            "status": "pending",
            "created_at": _now(),
            "decided_by": None,
            "decided_at": None,
            "reason": None,
            "kb_version": None,
        }
        self._proposals.append(proposal)
        self._log(actor=submitted_by, action="proposal_submitted", proposal_id=proposal_id,
                  reason=f"escalation resolution on {case_id}: {cause_label(confirmed_cause)}")
        return proposal

    def record_expert_capture(
        self,
        *,
        draft: dict[str, Any],
        submitted_by: str,
        expert_name: str,
        expert_role: str,
        asset_type: str,
    ) -> dict[str, Any]:
        """Queue AI-drafted expert knowledge as a pending proposal.

        Nothing reaches the live KB until a different knowledge steward
        approves it, exactly like outcome feedback.
        """
        proposal: dict[str, Any] = {
            "proposal_id": f"PROP-{uuid.uuid4().hex[:8].upper()}",
            "kind": "expert_capture",
            "proposal_type": "EXPERT_CAPTURE",
            "feedback_id": None,
            "case_id": None,
            "asset_id": None,
            "asset_type": asset_type,
            "confirmed_cause": ", ".join(
                sorted({h["likely_cause"] for h in draft["heuristics"]})
            ),
            "expert_name": expert_name,
            "expert_role": expert_role,
            "heuristics": draft["heuristics"],
            "provider": draft.get("provider"),
            "warnings": draft.get("warnings", []),
            "submitted_by": submitted_by,
            "status": "pending",
            "created_at": _now(),
            "decided_by": None,
            "decided_at": None,
            "reason": None,
            "kb_version": None,
        }
        self._proposals.append(proposal)
        self._log(actor=submitted_by, action="proposal_submitted",
                  proposal_id=proposal["proposal_id"],
                  reason=f"expert interview with {expert_name}: "
                         f"{len(draft['heuristics'])} heuristic(s)")
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
        if decided_by == p.get("submitted_by"):
            raise SelfApprovalError(
                f"{decided_by} proposed {proposal_id} and cannot also approve it; "
                "a different knowledge steward must review it"
            )
        p["status"] = "approved"
        p["decided_by"] = decided_by
        p["decided_at"] = _now()
        version_before = self._kb_version
        self._version_seq += 1
        self._kb_version = self._version_seq
        self._versions.append({
            "version": self._kb_version, "status": "live", "proposal_id": proposal_id,
            "created_by": decided_by, "created_at": p["decided_at"],
        })
        p["kb_version"] = self._kb_version
        if p.get("kind") == "expert_capture":
            self._ingest_expert_capture(p)
        else:
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
                validated_by=decided_by,
                corrected=p["corrected"],
                weight=1.0,
                created_at=_now(),
                kb_version=self._kb_version,
            )
            self._ingest(vc)
            p["validated_case_id"] = vc.id
        self._log(actor=decided_by, action="proposal_approved", proposal_id=proposal_id,
                  reason=f"approved proposal from {p.get('submitted_by')}",
                  version_before=version_before, version_after=self._kb_version)
        return p

    def _ingest_expert_capture(self, p: dict[str, Any]) -> None:
        """Make approved expert heuristics live.

        Heuristics on a known cause also enter the validated library, which
        raises that cause's empirical prior and so the confidence of future
        diagnoses that land on it. Heuristics proposing a new cause are kept
        as knowledge only: a new cause needs an engineered decision-tree
        branch before the engine can ever diagnose it.
        """
        from .cause_registry import canonicalize_cause_id
        from .decision_tree import KNOWN_CAUSE_IDS

        added: list[str] = []
        for i, h in enumerate(p["heuristics"]):
            hid = f"KB-EXP-{p['proposal_id'][5:]}-{i + 1}"
            # Store canonical IDs and the owning pill's asset type, so the
            # diagnosis screen can match approved knowledge reliably (older
            # drafts stored aliases and the interview-level asset type).
            h = {**h, "likely_cause": canonicalize_cause_id(h["likely_cause"]) or h["likely_cause"]}
            asset_type = h.get("asset_type") or p["asset_type"]
            entry = {
                **h,
                "id": hid,
                "expert_name": p["expert_name"],
                "expert_role": p["expert_role"],
                "asset_type": asset_type,
                "proposal_id": p["proposal_id"],
                "approved_by": p["decided_by"],
                "kb_version": self._kb_version,
            }
            self.expert_heuristics.append(entry)
            added.append(hid)
            if h["likely_cause"] in KNOWN_CAUSE_IDS:
                self._ingest(ValidatedCase(
                    id=hid,
                    case_id="EXPERT",
                    asset_id="EXPERT",
                    asset_type=asset_type,
                    fault_signature=h["symptom_pattern"].lower(),
                    proposed_cause=h["likely_cause"],
                    confirmed_cause=h["likely_cause"],
                    action_taken="; ".join(h.get("checks", [])),
                    outcome="resolved",
                    confidence=0.0,
                    validated_by=p["expert_name"],
                    corrected=False,
                    created_at=_now(),
                    kb_version=self._kb_version,
                ))
        p["expert_heuristic_ids"] = added

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
        self._log(actor=decided_by, action="proposal_rejected", proposal_id=proposal_id,
                  reason=reason)
        return p

    def rollback(self, target_version: int, *, actor: str = "system", reason: str = "") -> dict[str, Any]:
        """Return the KB to ``target_version``, a version still in the live lineage.

        Removes every validated case and heuristic added after it and marks
        the later versions rolled back. Version numbers are not reused: the
        next approval gets a fresh number, so no label ever names two states.
        """
        if not reason.strip():
            raise ValueError("a rollback needs a reason")
        live = {v["version"] for v in self._versions if v["status"] == "live"}
        if target_version not in live:
            raise ValueError(
                f"version {target_version} is not in the live lineage "
                f"(live: {sorted(live)})"
            )
        if target_version == self._kb_version:
            raise ValueError(f"version {target_version} is already current")
        version_before = self._kb_version
        removed: list[ValidatedCase] = [
            vc for vc in self.validated if vc.kb_version > target_version
        ]
        for vc in removed:
            self._remove(vc)
        # Mark approved proposals after target_version as rolled back
        rolled_back: list[str] = []
        for p in self._proposals:
            if p["status"] == "approved" and p["kb_version"] > target_version:
                p["status"] = "rolled_back"
                rolled_back.append(p["proposal_id"])
        self.expert_heuristics = [
            h for h in self.expert_heuristics if h["kb_version"] <= target_version
        ]
        for v in self._versions:
            if v["status"] == "live" and v["version"] > target_version:
                v["status"] = "rolled_back"
        self._kb_version = target_version
        self._log(actor=actor, action="rollback", reason=reason.strip(),
                  version_before=version_before, version_after=target_version)
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
    def get_similar(self, fault_signature: str, asset_type: str | None = None, k: int = 3,
                    evidence_terms: set[str] | None = None) -> list[ValidatedCase]:
        """Top-k validated cases by Jaccard token overlap + asset-type bonus.

        Expert-interview entries only count when the condition the expert
        described is visible in this case's evidence (``evidence_terms``).
        """
        scored: list[tuple[float, ValidatedCase]] = []
        for vc in self.validated:
            if vc.case_id == "EXPERT" and not corroborating_terms(vc.fault_signature, evidence_terms):
                continue
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

    def kb_match_score(self, fault_signature: str, confirmed_cause: str, asset_type: str | None = None,
                       evidence_terms: set[str] | None = None) -> float:
        """0-1 score: how well the KB supports (signature, cause) for this case.

        Combines best-similarity of matching cases with the cause's empirical
        confirmation rate. Used as ``kb_match`` input to ``score_confidence``.
        """
        similar = self.get_similar(fault_signature, asset_type, k=3, evidence_terms=evidence_terms)
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
            "feedback_added": sum(
                1 for vc in self.validated if vc.case_id not in ("SEED", "EXPERT")
            ),
            "expert_heuristics": len(self.expert_heuristics),
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