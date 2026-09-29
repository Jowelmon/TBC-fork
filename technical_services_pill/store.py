"""In-memory case store for the Technical Services Fault Diagnosis pill.

Holds ``AgentState`` instances keyed by ``case_id`` and exposes the read
surfaces the spec §5 API needs: create, get, list, snapshot, audit trace.
A module-level singleton ``STORE`` is provided for the FastAPI app; all
state is process-local and deterministic.

Thread-safety: for the hackathon demo (single-worker FastAPI) no locking is
needed. If this moves behind a multi-worker deployment, wrap ``_cases`` in a
``threading.Lock`` or move to an external store.
"""
from __future__ import annotations

import uuid
from typing import Any

from .agent_state import AgentState


class CaseStore:
    """In-memory store of ``AgentState`` by case id."""

    def __init__(self) -> None:
        self._cases: dict[str, AgentState] = {}

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def create(self, state: AgentState) -> str:
        """Persist ``state``. Assigns a case id if none, sets it on the state,
        and returns it."""
        case_id = state.case_id or f"CASE-{uuid.uuid4().hex[:8]}"
        state.case_id = case_id
        self._cases[case_id] = state
        return case_id

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get(self, case_id: str) -> AgentState | None:
        return self._cases.get(case_id)

    def list(self) -> list[str]:
        """All stored case ids."""
        return list(self._cases.keys())

    def snapshot(self, case_id: str) -> dict | None:
        """Full state snapshot for the HITL UI (spec §5 GET /cases/{id})."""
        state = self._cases.get(case_id)
        return state.snapshot() if state is not None else None

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #
    def audit_trace(self, case_id: str) -> list[dict]:
        """History entries for one case as dicts, each tagged with the
        per-chain ``chain_valid`` flag from ``AgentState.verify_audit_chain``.

        Returns an empty list if the case is unknown.
        """
        state = self._cases.get(case_id)
        if state is None:
            return []
        chain_valid = state.verify_audit_chain()
        return [
            {**entry.model_dump(mode="json"), "chain_valid": chain_valid}
            for entry in state.history
        ]

    def all_audit_traces(
        self,
        *,
        actor: str | None = None,
        case_id: str | None = None,
    ) -> list[dict]:
        """Audit entries across all cases (spec §5 GET /audit/trace).

        Optional filters:
          actor   — keep only entries whose ``actor`` matches exactly.
          case_id — restrict to a single case (None = all cases).

        Each returned dict is a history entry with the owning ``case_id``
        and the chain-validity flag merged in.
        """
        out: list[dict] = []
        targets = (
            [case_id] if case_id is not None else list(self._cases.keys())
        )
        for cid in targets:
            state = self._cases.get(cid)
            if state is None:
                continue
            chain_valid = state.verify_audit_chain()
            for entry in state.history:
                d: dict[str, Any] = entry.model_dump(mode="json")
                d["case_id"] = cid
                d["chain_valid"] = chain_valid
                if actor is not None and d.get("actor") != actor:
                    continue
                out.append(d)
        return out


# Module-level singleton for the FastAPI app.
STORE = CaseStore()