"""Governed knowledge base for the four Intelligence Pills.

    diagnosis -> recommendation -> human decision -> outcome
        -> feedback / expert interview / escalation resolution
            -> pending proposal -> a different steward approves
                -> knowledge for that pill goes live at a new version
                    -> retrieved by future diagnoses (kb_match -> confidence)

Each pill (CRAH, Chiller, UPS, Pump) has its own knowledge version, version
history, rollback and revocation record: approving chiller knowledge moves
only the Chiller version, and rolling the CRAH pill back leaves the others
alone. An interview that files knowledge under several pills moves each of
them. One keyed, hash-chained ledger records every governance action
across all pills, so there is a single audit trail.

All assumed thresholds below are tagged ``【ASSUMPTION】``: tunable, to be
validated with Keppel technical-services SMEs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .cause_registry import cause_label
from .models import FeedbackRecord, ValidatedCase

SEED_KB_MAJOR = 1
SEED_KB_MINOR = 3
PILLS = ("CRAH", "Chiller", "UPS", "Pump")


class LedgerBrokenError(ValueError):
    """A write was refused because the knowledge ledger fails verification."""


class SelfApprovalError(ValueError):
    """Raised when the approver of a knowledge proposal is its proposer."""


def kb_version_label(version: int) -> str:
    """A pill's version number as the label shown on screen (0 -> 1.3.0).

    Numbers are allocated once per pill and never reused (a rollback does
    not rewind the counter), so a label always names exactly one state.
    """
    return f"{SEED_KB_MAJOR}.{SEED_KB_MINOR + version}.0"


# 【ASSUMPTION】 how far one approved expert heuristic alone can move the
# similarity behind kb_match (1.0 would let a single interview max it out).
EXPERT_SIMILARITY_CAP = 0.7

LEDGER_FIELDS = (
    "seq", "at", "actor", "action", "proposal_id", "reason",
    "versions_before", "versions_after", "kb_digest",
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


def needs_safety_review(p: dict[str, Any]) -> list[str]:
    """Lines of a proposal's heuristics the approver must explicitly
    safety-review: every check (an action someone will take on equipment,
    however it is worded) and every line naming a protective device (see
    ``safety.py``). A word list cannot recognise every workaround, so no
    action reaches the AOM without a person confirming it."""
    lines: list[str] = []
    for h in p.get("heuristics") or []:
        lines += [*(h.get("checks") or []), *(h.get("safety_review") or [])]
    return list(dict.fromkeys(lines))


def proposal_pills(p: dict[str, Any]) -> list[str]:
    """The pills a proposal files knowledge under."""
    if p.get("kind") == "expert_capture":
        pills = {h.get("asset_type") or p.get("asset_type") for h in p.get("heuristics") or []}
    else:
        pills = {p.get("asset_type")}
    return sorted(x for x in pills if x in PILLS)


class LearningStore:
    """Validated cases, expert heuristics, proposals and per-pill versions.

    Seeded from the registry's historical cases (every pill at version 0,
    shown as 1.3.0) so retrieval is useful before any feedback arrives.
    """

    def __init__(self) -> None:
        self.validated: list[ValidatedCase] = []
        self._cause_stats: dict[str, dict[str, int]] = {}  # derived; see rebuild_stats
        self._proposals: list[dict[str, Any]] = []
        self._kb_version: dict[str, int] = {pill: 0 for pill in PILLS}
        # Highest version ever issued per pill; never decremented.
        self._version_seq: dict[str, int] = {pill: 0 for pill in PILLS}
        self._versions: dict[str, list[dict[str, Any]]] = {
            pill: [{"version": 0, "status": "live", "proposal_id": None,
                    "created_by": "seed", "created_at": _now().isoformat()}]
            for pill in PILLS
        }
        # Keyed, hash-chained record of every governance action, with a
        # digest of the KB's contents in each entry and a seal over the
        # chain, so editing knowledge or truncating the ledger is caught.
        self.ledger: list[dict[str, Any]] = []
        self.ledger_seal: str | None = None
        # {pill, version the withdrawn knowledge went live at, ledger seq}
        self._revocations: list[dict[str, Any]] = []
        self.expert_heuristics: list[dict[str, Any]] = []
        self._seed_from_registry()
        self._log(actor="system", action="seeded",
                  reason=f"seed knowledge base: {len(self.validated)} validated cases")

    # ------------------------------------------------------------------ #
    # Versions
    # ------------------------------------------------------------------ #
    def version_of(self, pill: str) -> int:
        return self._kb_version.get(pill, 0)

    def label_of(self, pill: str) -> str:
        """``"CRAH v1.4.0"``: a version number means nothing without its pill."""
        return f"{pill} v{kb_version_label(self.version_of(pill))}"

    def labels(self) -> dict[str, str]:
        return {pill: self.label_of(pill) for pill in PILLS}

    def list_versions(self, pill: str) -> list[dict[str, Any]]:
        return [{**v, "label": kb_version_label(v["version"])} for v in self._versions.get(pill, [])]

    def _bump(self, pill: str, *, actor: str, proposal_id: str | None) -> int:
        self._version_seq[pill] += 1
        self._kb_version[pill] = self._version_seq[pill]
        self._versions[pill].append({
            "version": self._kb_version[pill], "status": "live", "proposal_id": proposal_id,
            "created_by": actor, "created_at": _now().isoformat(),
        })
        return self._kb_version[pill]

    # ------------------------------------------------------------------ #
    # Governance ledger
    # ------------------------------------------------------------------ #
    def _require_verified(self) -> None:
        """Called before any change that the ledger will record. Each entry
        carries a digest of the knowledge base as it then is, so writing to a
        ledger that already fails verification would silently vouch for
        whatever broke it. Only the auditor's ledger review may proceed."""
        if self.ledger and not self.verify_ledger():
            raise LedgerBrokenError("the knowledge ledger failed verification; an auditor must "
                                    "review it before anything else is recorded")

    def _log(self, *, actor: str, action: str, proposal_id: str | None = None, reason: str = "",
             versions_before: dict[str, int] | None = None) -> dict[str, Any]:
        from .audit import GENESIS_HASH, compute_hash


        after = dict(self._kb_version)
        entry: dict[str, Any] = {
            "seq": len(self.ledger) + 1,
            "at": _now().isoformat(),
            "actor": actor,
            "action": action,
            "proposal_id": proposal_id,
            "reason": reason,
            "versions_before": dict(versions_before) if versions_before is not None else after,
            "versions_after": after,
            "kb_digest": self._kb_digest(),
            "prev_hash": self.ledger[-1]["hash"] if self.ledger else GENESIS_HASH,
        }
        entry["hash"] = compute_hash(entry["prev_hash"], {f: entry[f] for f in LEDGER_FIELDS})
        self.ledger.append(entry)
        self.ledger_seal = compute_hash("seal", {"length": len(self.ledger), "head": entry["hash"]})
        return entry

    def _kb_digest(self) -> str:
        """SHA-256 over the knowledge the engine uses, every proposal and
        every pill's version history, so edits outside the governance flow
        show up."""
        import hashlib

        from .audit import canonical_json

        material = {
            "kb_version": self._kb_version,
            "version_seq": self._version_seq,
            "versions": {p: [(v["version"], v["status"]) for v in vs] for p, vs in self._versions.items()},
            "revocations": self._revocations,
            "validated": sorted(
                (vc.id, vc.case_id, vc.asset_type, vc.confirmed_cause, vc.outcome,
                 vc.kb_version, vc.weight, vc.fault_signature, vc.validated_by, vc.action_taken)
                for vc in self.validated
            ),
            # Every field shown to an AOM is covered, not only the ids.
            "heuristics": sorted(
                (h["id"], h["likely_cause"], h["asset_type"], h["evidence_quote"],
                 h["kb_version"], h["approved_by"], h.get("expert_name"), h.get("expert_role"),
                 h.get("symptom_pattern"), tuple(h.get("checks") or ()),
                 tuple(h.get("do_not") or ()), tuple(h.get("escalate_when") or ()),
                 tuple(h.get("safety_review") or ()), h.get("safety_reviewed_by"))
                for h in self.expert_heuristics
            ),
            "proposals": [
                (p["proposal_id"], p["status"], p.get("submitted_by"), p.get("decided_by"),
                 p.get("confirmed_cause"), p.get("asset_type"), p.get("kb_versions"), p.get("reason"),
                 p.get("expert_name"), p.get("resolution"), p.get("heuristics"),
                 p.get("rolled_back_pills"))
                for p in self._proposals
            ],
        }
        return hashlib.sha256(canonical_json(material).encode()).hexdigest()

    def verify_ledger(self) -> bool:
        from .audit import compute_hash, verify_chain

        if not self.ledger or not verify_chain(self.ledger, LEDGER_FIELDS):
            return False
        if self._cause_stats != self._derived_stats():
            return False
        if self.ledger[-1]["kb_digest"] != self._kb_digest():
            return False
        return self.ledger_seal == compute_hash(
            "seal", {"length": len(self.ledger), "head": self.ledger[-1]["hash"]})

    def review_broken_ledger(self, *, actor: str, reason: str) -> dict[str, Any]:
        """An auditor's disposition of a ledger that failed verification: the
        entries are re-signed as they stand, statistics are rebuilt from the
        validated cases, and a new entry records who accepted the current
        knowledge base and why (with the head hash that had failed)."""
        from .audit import resign_chain

        if self.verify_ledger():
            raise ValueError("the knowledge ledger verifies; there is nothing to review")
        old_head = self.ledger[-1]["hash"] if self.ledger else ""
        problem = self.ledger_problem()
        resign_chain(self.ledger, LEDGER_FIELDS)
        self.rebuild_stats()
        return self._log(actor=actor, action="integrity_review",
                         reason=f"knowledge ledger accepted after review ({problem}; failed head "
                                f"{old_head[:12]}): {reason}")

    def ledger_problem(self) -> str | None:
        """What failed, in words an auditor can investigate, or None."""
        from .audit import GENESIS_HASH, compute_hash

        prev = GENESIS_HASH
        for e in self.ledger:
            if e.get("prev_hash") != prev or e.get("hash") != compute_hash(
                    prev, {f: e.get(f) for f in LEDGER_FIELDS}):
                return f"ledger entry #{e.get('seq')} ({e.get('action')} by {e.get('actor')}) was altered"
            prev = e["hash"]
        if not self.ledger:
            return "the ledger is empty"
        if self._cause_stats != self._derived_stats():
            return "cause statistics no longer match the validated cases"
        if self.ledger[-1]["kb_digest"] != self._kb_digest():
            return ("the knowledge base (cases, expert heuristics, proposals or versions) was changed "
                    f"outside the governance flow after entry #{self.ledger[-1]['seq']}")
        if self.ledger_seal != compute_hash("seal", {"length": len(self.ledger), "head": prev}):
            return "the ledger was truncated (its seal does not match)"
        return None

    def record_integrity_review(self, *, actor: str, reason: str) -> dict[str, Any]:
        """Record an auditor's review of another chain (a case, the case
        registry, the tool log) in the governance ledger."""
        self._require_verified()
        return self._log(actor=actor, action="integrity_review", reason=reason)

    def withdrawn_reason(self, pill: str | None, kb_version_used: int | None,
                         ledger_seq_at_use: int | None) -> str | None:
        """Why the pill knowledge a case was scored against is no longer in
        force, or None."""
        if pill is None or kb_version_used is None:
            return None
        live = {v["version"] for v in self._versions.get(pill, []) if v["status"] == "live"}
        if kb_version_used not in live:
            return (f"{pill} KB v{kb_version_label(kb_version_used)} was rolled back after this "
                    "case was diagnosed")
        for r in self._revocations:
            if (r["pill"] == pill and r["proposal_version"] <= kb_version_used
                    and r["ledger_seq"] > (ledger_seq_at_use or 0)):
                return (f"{pill} knowledge approved in v{kb_version_label(r['proposal_version'])} "
                        "was revoked after this case was diagnosed")
        return None

    # ------------------------------------------------------------------ #
    def _seed_from_registry(self) -> None:
        # A broken registry must fail loudly, not start an empty KB.
        from .mock_registry import get_registry

        kb = get_registry()["KNOWLEDGE_BASE"]["cases"]
        for i, c in enumerate(kb):
            cause = c.get("root_cause", "")
            self._ingest(ValidatedCase(
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
            ))

    def _ingest(self, vc: ValidatedCase) -> None:
        from .cause_registry import canonicalize_cause_id

        vc.proposed_cause = canonicalize_cause_id(vc.proposed_cause) or vc.proposed_cause
        vc.confirmed_cause = canonicalize_cause_id(vc.confirmed_cause) or vc.confirmed_cause
        self.validated.append(vc)
        self.rebuild_stats()

    def _derived_stats(self) -> dict[str, dict[str, int]]:
        """Cause confirmation counts, computed from validated outcomes.
        An interview is a claim, not an observed outcome: never counted."""
        stats: dict[str, dict[str, int]] = {}
        for vc in self.validated:
            if vc.case_id == "EXPERT":
                continue
            st = stats.setdefault(vc.confirmed_cause, {"confirmed": 0, "total": 0})
            st["total"] += 1
            if vc.outcome == "resolved":
                st["confirmed"] += 1
        return stats

    def rebuild_stats(self) -> None:
        """Priors are never stored on their own: they are rebuilt from the
        hashed validated cases, so they cannot be edited independently."""
        self._cause_stats = self._derived_stats()

    def _remove_where(self, keep) -> int:
        before = len(self.validated)
        self.validated = [vc for vc in self.validated if keep(vc)]
        self.rebuild_stats()
        return before - len(self.validated)

    # ------------------------------------------------------------------ #
    # Proposals
    # ------------------------------------------------------------------ #
    def _new_proposal(self, **fields: Any) -> dict[str, Any]:
        proposal = {
            "proposal_id": f"PROP-{uuid.uuid4().hex[:8].upper()}",
            "status": "pending",
            "created_at": _now().isoformat(),
            "decided_by": None,
            "decided_at": None,
            "reason": None,
            "kb_versions": None,
            **fields,
        }
        self._proposals.append(proposal)
        return proposal

    def record_feedback(self, fb: FeedbackRecord, *, confidence: float, action_taken: str = "") -> dict:
        """A pending proposal from outcome feedback; nothing is live yet."""
        self._require_verified()
        p = self._new_proposal(
            kind="outcome_feedback", feedback_id=fb.feedback_id, case_id=fb.case_id,
            asset_id=fb.asset_id, asset_type=fb.asset_type, confirmed_cause=fb.confirmed_cause,
            proposed_cause=fb.proposed_cause,
            corrected=fb.proposed_cause is not None and fb.proposed_cause != fb.confirmed_cause,
            confidence=confidence, action_taken=action_taken,
            fault_signature=fb.corrections.get("fault_signature", ""),
            outcome=fb.corrections.get("outcome", "resolved"), submitted_by=fb.submitted_by,
        )
        self._log(actor=fb.submitted_by, action="proposal_submitted", proposal_id=p["proposal_id"],
                  reason=f"outcome feedback on {fb.case_id}: {cause_label(fb.confirmed_cause)}")
        return p

    def record_escalation_resolution(
        self, *, case_id: str, asset_id: str, asset_type: str, confirmed_cause: str,
        proposed_cause: str | None, fault_signature: str, resolution: str,
        confidence: float, submitted_by: str,
    ) -> dict[str, Any]:
        """Queue how an expert resolved an escalation as a knowledge proposal:
        the cases the pill could not solve are where the know-how is."""
        self._require_verified()
        p = self._new_proposal(
            kind="escalation_resolution", feedback_id=f"ESC-{uuid.uuid4().hex[:8].upper()}",
            case_id=case_id, asset_id=asset_id, asset_type=asset_type,
            confirmed_cause=confirmed_cause, proposed_cause=proposed_cause,
            corrected=proposed_cause is not None and proposed_cause != confirmed_cause,
            confidence=confidence, action_taken=resolution, resolution=resolution,
            fault_signature=fault_signature, outcome="resolved", submitted_by=submitted_by,
        )
        self._log(actor=submitted_by, action="proposal_submitted", proposal_id=p["proposal_id"],
                  reason=f"escalation resolution on {case_id}: {cause_label(confirmed_cause)}")
        return p

    def record_expert_capture(self, *, draft: dict[str, Any], submitted_by: str, expert_name: str,
                              expert_role: str, asset_type: str, expert_consent: bool) -> dict[str, Any]:
        """Queue drafted expert knowledge; a different steward must approve."""
        self._require_verified()
        p = self._new_proposal(
            kind="expert_capture", feedback_id=None, case_id=None, asset_id=None,
            asset_type=asset_type,
            confirmed_cause=", ".join(sorted({h["likely_cause"] for h in draft["heuristics"]})),
            expert_name=expert_name, expert_role=expert_role, expert_consent=expert_consent,
            heuristics=draft["heuristics"], provider=draft.get("provider"),
            warnings=draft.get("warnings", []), submitted_by=submitted_by,
        )
        self._log(actor=submitted_by, action="proposal_submitted", proposal_id=p["proposal_id"],
                  reason=f"expert interview with {expert_name}: {len(draft['heuristics'])} heuristic(s)")
        return p

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        return [p for p in self._proposals if p["status"] == "pending"]

    def list_all_proposals(self) -> list[dict[str, Any]]:
        return list(self._proposals)

    def find_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return next((p for p in self._proposals if p["proposal_id"] == proposal_id), None)

    def _pending(self, proposal_id: str, decided_by: str, verb: str) -> dict[str, Any]:
        p = self.find_proposal(proposal_id)
        if p is None:
            raise ValueError(f"proposal {proposal_id} not found")
        if p["status"] != "pending":
            raise ValueError(f"proposal {proposal_id} is {p['status']}, not pending")
        if decided_by == p.get("submitted_by"):
            raise SelfApprovalError(
                f"{decided_by} proposed {proposal_id} and cannot also {verb} it; "
                "a different knowledge steward must review it"
            )
        return p

    def approve_proposal(self, proposal_id: str, *, decided_by: str, rationale: str,
                         safety_reviewed: bool = False) -> dict[str, Any]:
        """Approve a pending proposal: its knowledge goes live and each pill
        it files knowledge under moves to a new version. Expert knowledge
        needs the approver's explicit safety review (``needs_safety_review``)."""
        self._require_verified()
        if not rationale.strip():
            raise ValueError("approving knowledge needs a rationale")
        p = self._pending(proposal_id, decided_by, "approve")
        held = needs_safety_review(p)
        if held and not safety_reviewed:
            raise ValueError(
                f"approving expert knowledge needs a safety review: confirm that none of its "
                f"{len(held)} check(s) or protective-device line(s) tells anyone to defeat, bypass "
                "or weaken a protection (safety_reviewed=true)")
        before = dict(self._kb_version)
        if held:
            p["safety_reviewed_by"] = decided_by
        p["status"] = "approved"
        p["decided_by"] = decided_by
        p["decided_at"] = _now().isoformat()
        p["reason"] = rationale.strip()
        p["kb_versions"] = {pill: self._bump(pill, actor=decided_by, proposal_id=proposal_id)
                            for pill in proposal_pills(p)}
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
                kb_version=p["kb_versions"].get(p["asset_type"], 0),
            )
            self._ingest(vc)
            p["validated_case_id"] = vc.id
        review = f" (safety review confirmed for {len(held)} line(s))" if held else ""
        self._log(actor=decided_by, action="proposal_approved", proposal_id=proposal_id,
                  reason=f"approved proposal from {p.get('submitted_by')}{review}: {rationale.strip()}",
                  versions_before=before)
        return p

    def _ingest_expert_capture(self, p: dict[str, Any]) -> None:
        """Make approved expert heuristics live, each under its own pill.

        A heuristic on a known cause also enters the validated library, so
        it can support a matching case's confidence when the case shows the
        condition the expert described. A proposed new cause stays reference
        knowledge until an engineer adds a decision-tree branch for it.
        """
        from .cause_registry import canonicalize_cause_id
        from .decision_tree import KNOWN_CAUSE_IDS

        added: list[str] = []
        for i, h in enumerate(p["heuristics"]):
            hid = f"KB-EXP-{p['proposal_id'][5:]}-{i + 1}"
            h = {**h, "likely_cause": canonicalize_cause_id(h["likely_cause"]) or h["likely_cause"]}
            pill = h.get("asset_type") or p["asset_type"]
            version = p["kb_versions"].get(pill, 0)
            self.expert_heuristics.append({
                **h,
                "id": hid,
                "expert_name": p["expert_name"],
                "expert_role": p["expert_role"],
                "asset_type": pill,
                "proposal_id": p["proposal_id"],
                "approved_by": p["decided_by"],
                "safety_reviewed_by": p.get("safety_reviewed_by"),
                "kb_version": version,
            })
            added.append(hid)
            # Knowledge about a protective device is guidance for a person,
            # reviewed as such: it never raises a diagnosis's confidence.
            if h["likely_cause"] in KNOWN_CAUSE_IDS and not h.get("safety_review"):
                self._ingest(ValidatedCase(
                    id=hid,
                    case_id="EXPERT",
                    asset_id="EXPERT",
                    asset_type=pill,
                    fault_signature=h["symptom_pattern"].lower(),
                    proposed_cause=h["likely_cause"],
                    confirmed_cause=h["likely_cause"],
                    action_taken="; ".join(h.get("checks", [])),
                    outcome="resolved",
                    confidence=0.0,
                    validated_by=p["expert_name"],
                    corrected=False,
                    created_at=_now(),
                    kb_version=version,
                ))
        p["expert_heuristic_ids"] = added

    def approve_by_feedback_id(self, feedback_id: str, *, decided_by: str,
                               rationale: str = "outcome confirmed by the work order") -> dict[str, Any]:
        p = next((x for x in self._proposals if x.get("feedback_id") == feedback_id), None)
        if p is None:
            raise ValueError(f"no proposal for feedback_id {feedback_id}")
        return self.approve_proposal(p["proposal_id"], decided_by=decided_by, rationale=rationale)

    def reject_proposal(self, proposal_id: str, *, decided_by: str, reason: str) -> dict[str, Any]:
        """Reject a pending proposal. A reason is required, and the proposer
        cannot reject their own proposal any more than approve it."""
        self._require_verified()
        if not reason.strip():
            raise ValueError("rejecting knowledge needs a reason")
        p = self._pending(proposal_id, decided_by, "reject")
        p["status"] = "rejected"
        p["decided_by"] = decided_by
        p["decided_at"] = _now().isoformat()
        p["reason"] = reason.strip()
        self._log(actor=decided_by, action="proposal_rejected", proposal_id=proposal_id,
                  reason=reason.strip())
        return p

    def revoke_proposal(self, proposal_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        """Withdraw one approved proposal's knowledge, leaving everything
        else. Each affected pill moves to a new version; the revocation is
        permanent (a later rollback does not bring it back)."""
        self._require_verified()
        if not reason.strip():
            raise ValueError("a revocation needs a reason")
        p = self.find_proposal(proposal_id)
        if p is None:
            raise ValueError(f"proposal {proposal_id} not found")
        if p["status"] != "approved":
            raise ValueError(f"proposal {proposal_id} is {p['status']}, not approved")
        ids = set(p.get("expert_heuristic_ids") or [])
        if p.get("validated_case_id"):
            ids.add(p["validated_case_id"])
        removed = self._remove_where(lambda vc: vc.id not in ids)
        self.expert_heuristics = [h for h in self.expert_heuristics if h.get("proposal_id") != proposal_id]
        before = dict(self._kb_version)
        p["status"] = "revoked"
        still_live = {pill: v for pill, v in (p.get("kb_versions") or {}).items()
                      if pill not in (p.get("rolled_back_pills") or [])}
        for pill, version in still_live.items():
            self._bump(pill, actor=actor, proposal_id=None)
            self._revocations.append({"pill": pill, "proposal_version": version,
                                      "ledger_seq": len(self.ledger) + 1})
        self._log(actor=actor, action="proposal_revoked", proposal_id=proposal_id,
                  reason=reason.strip(), versions_before=before)
        return {"revoked": proposal_id, "removed_items": removed, "pills": sorted(still_live),
                "kb_versions": {pill: self._kb_version[pill] for pill in still_live}}

    def rollback(self, pill: str, target_version: int, *, actor: str = "system",
                 reason: str = "") -> dict[str, Any]:
        """Return one pill's knowledge to an earlier live version.

        Removes that pill's cases and heuristics approved after it and marks
        its later versions rolled back; other pills are untouched. Version
        numbers are not reused, so no label ever names two states.
        """
        self._require_verified()
        if not reason.strip():
            raise ValueError("a rollback needs a reason")
        if pill not in PILLS:
            raise ValueError(f"unknown pill {pill!r}; expected one of {list(PILLS)}")
        live = {v["version"] for v in self._versions[pill] if v["status"] == "live"}
        if target_version not in live:
            raise ValueError(f"{pill} version {target_version} is not in the live lineage "
                             f"(live: {sorted(live)})")
        if target_version == self._kb_version[pill]:
            raise ValueError(f"{pill} is already at version {target_version}")
        before = dict(self._kb_version)
        removed = self._remove_where(
            lambda vc: not (vc.asset_type == pill and vc.kb_version > target_version))
        self.expert_heuristics = [
            h for h in self.expert_heuristics
            if not (h["asset_type"] == pill and h["kb_version"] > target_version)
        ]
        rolled_back: list[str] = []
        for p in self._proposals:
            versions = p.get("kb_versions") or {}
            if p["status"] == "approved" and versions.get(pill, -1) > target_version:
                p["rolled_back_pills"] = sorted({*(p.get("rolled_back_pills") or []), pill})
                if set(p["rolled_back_pills"]) >= set(versions):
                    p["status"] = "rolled_back"
                rolled_back.append(p["proposal_id"])
        for v in self._versions[pill]:
            if v["status"] == "live" and v["version"] > target_version:
                v["status"] = "rolled_back"
        self._kb_version[pill] = target_version
        self._log(actor=actor, action="rollback", reason=reason.strip(),
                  versions_before=before)
        return {"pill": pill, "rolled_back_to": target_version, "removed_cases": removed,
                "rolled_back_proposals": rolled_back}

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    def _similarity(self, fault_signature: str, vc: ValidatedCase,
                    evidence_terms: set[str] | None) -> float:
        """Validated outcomes: Jaccard overlap of fault signatures. Expert
        heuristics: how many distinctive words of the condition the expert
        described appear in this case's evidence (three or more is full
        support); none means the heuristic does not apply to this case."""
        if vc.case_id == "EXPERT":
            # One interview is one person's word, not an observed outcome: on
            # its own it can lift kb_match only part of the way (validated
            # outcomes on the same cause carry it further).
            matched = corroborating_terms(vc.fault_signature, evidence_terms)
            return EXPERT_SIMILARITY_CAP * min(1.0, len(matched) / 3)
        return jaccard(fault_signature, vc.fault_signature)

    def get_similar(self, fault_signature: str, asset_type: str | None = None, k: int = 3,
                    evidence_terms: set[str] | None = None) -> list[ValidatedCase]:
        """Top-k KB entries supporting this case, plus an asset-type bonus."""
        scored: list[tuple[float, ValidatedCase]] = []
        # Expert knowledge is only as good as the ledger vouching for it.
        trust_expert = self.verify_ledger()
        for vc in self.validated:
            if vc.case_id == "EXPERT" and not trust_expert:
                continue
            sim = self._similarity(fault_signature, vc, evidence_terms)
            if vc.case_id == "EXPERT" and sim <= 0.0:
                continue  # the expert's condition is not in this case's evidence
            if asset_type and vc.asset_type == asset_type:
                sim += 0.1  # 【ASSUMPTION】 asset-type prior bonus
            sim *= vc.weight
            scored.append((sim, vc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [vc for s, vc in scored[:k] if s > 0.0]

    def cause_prior(self, cause_id: str) -> float:
        """Empirical confirmation rate for a cause (0.6 if unseen 【ASSUMPTION】)."""
        st = self._cause_stats.get(cause_id)
        if not st or st["total"] == 0:
            return 0.6
        return st["confirmed"] / st["total"]

    def kb_match_score(self, fault_signature: str, confirmed_cause: str, asset_type: str | None = None,
                       evidence_terms: set[str] | None = None) -> float:
        """0-1: how well the KB supports (signature, cause) for this case;
        the ``kb_match`` input to ``score_confidence``."""
        similar = self.get_similar(fault_signature, asset_type, k=3, evidence_terms=evidence_terms)
        if not similar:
            return 0.2  # 【ASSUMPTION】 low-but-nonzero baseline
        matching = [vc for vc in similar if vc.confirmed_cause == confirmed_cause]
        best_sim = max((self._similarity(fault_signature, vc, evidence_terms) for vc in matching),
                       default=0.0)
        # weight similarity 0.6, prior 0.4  【ASSUMPTION】
        return min(1.0, 0.6 * best_sim + 0.4 * self.cause_prior(confirmed_cause))

    def stats(self) -> dict[str, Any]:
        return {
            "total_validated_cases": len(self.validated),
            "feedback_added": sum(1 for vc in self.validated if vc.case_id not in ("SEED", "EXPERT")),
            "expert_heuristics": len(self.expert_heuristics),
            "corrected_count": sum(1 for vc in self.validated if vc.corrected),
            "pending_proposals": len(self.list_pending_proposals()),
            "kb_versions": dict(self._kb_version),
            "kb_version_labels": self.labels(),
            "cause_priors": {
                cause: {"confirmed": st["confirmed"], "total": st["total"],
                        "rate": round(st["confirmed"] / st["total"], 3)}
                for cause, st in self._cause_stats.items()
            },
        }


# module-level singleton for the app + demo
STORE = LearningStore()
