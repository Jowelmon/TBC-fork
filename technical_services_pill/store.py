"""Case store with a SQLite-backed persistence layer and a memory cache.

The repository originally used a process-local in-memory store. This version
adds persisted storage without breaking the existing public API: the app still
works with ``CaseStore().create(...)``, ``get()``, ``list()``, and
``snapshot()`` semantics, but state survives a restart.
"""
from __future__ import annotations

import uuid
from typing import Any

from .agent_state import AgentState
from .database import SQLiteStore
from .models import (
    AgentStateName,
    Diagnosis,
    EvidenceItem,
    GuardrailResult,
    HistoryEntry,
    HumanDecisionRecord,
    Observation,
    Outcome,
    Recommendation,
)


class CaseStore:
    """Persistent store of ``AgentState`` by case id."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db = SQLiteStore(db_path)
        self._cases: dict[str, AgentState] = {}
        for case_id in self._db.list_case_ids():
            data = self._db.get_case_state(case_id)
            if data is not None:
                self._cases[case_id] = self._restore_from_snapshot(data)
        self.registry_seal: str | None = None
        self.reseal()

    def reseal(self) -> None:
        """Keyed seal over the set of case ids: deleting or inserting a case
        outside the API no longer passes verification."""
        from .audit import compute_hash

        self.registry_seal = compute_hash("registry", {"cases": sorted(self._cases)})

    def verify_registry(self) -> bool:
        from .audit import compute_hash

        return self.registry_seal == compute_hash("registry", {"cases": sorted(self._cases)})

    def _restore_from_snapshot(self, data: dict[str, Any]) -> AgentState:
        obs = Observation.model_validate(data["observation"])
        state = AgentState(asset_id=data["asset_id"], observation=obs, case_id=data["case_id"])
        state.evidence = [EvidenceItem.model_validate(item) for item in data.get("evidence", [])]
        state.diagnosis = Diagnosis.model_validate(data["diagnosis"]) if data.get("diagnosis") else None
        state.confidence = float(data.get("confidence", 0.0))
        state.recommendation = Recommendation.model_validate(data["recommendation"]) if data.get("recommendation") else None
        state.human_decision = HumanDecisionRecord.model_validate(data["human_decision"]) if data.get("human_decision") else None
        state.outcome = Outcome.model_validate(data["outcome"]) if data.get("outcome") else None
        state.guardrail_result = GuardrailResult.model_validate(data["guardrail_result"]) if data.get("guardrail_result") else None
        state.ai_hypothesis = data.get("ai_hypothesis")
        state.confidence_breakdown = data.get("confidence_breakdown")
        state.work_order_id = data.get("work_order_id")
        state.feedback_id = data.get("feedback_id")
        state.history = [HistoryEntry.model_validate(item) for item in data.get("history", [])]
        state.chain_seal = data.get("chain_seal")
        state.current_state = AgentStateName(data.get("current_state", state.current_state.value))
        state._gathering_loops = int(data.get("_gathering_loops", 0))
        state._retrieval_rounds = int(data.get("_retrieval_rounds", 0))
        return state

    def create(self, state: AgentState) -> str:
        case_id = state.case_id or f"CASE-{uuid.uuid4().hex[:8]}"
        state.case_id = case_id
        self._cases[case_id] = state
        self.reseal()
        self._db.save_case_state(case_id, state.snapshot())
        return case_id

    def get(self, case_id: str) -> AgentState | None:
        state = self._cases.get(case_id)
        if state is None:
            data = self._db.get_case_state(case_id)
            if data is None:
                return None
            state = self._restore_from_snapshot(data)
            self._cases[case_id] = state
        return state

    def list(self) -> list[str]:
        return list(self._cases.keys())

    def snapshot(self, case_id: str) -> dict | None:
        state = self.get(case_id)
        if state is None:
            return None
        snap = state.snapshot()
        self._db.save_case_state(case_id, snap)
        return snap

    def audit_trace(self, case_id: str) -> list[dict]:
        state = self.get(case_id)
        if state is None:
            return []
        chain_valid = state.verify_audit_chain()
        return [{**entry.model_dump(mode="json"), "chain_valid": chain_valid} for entry in state.history]

    def all_audit_traces(self, *, actor: str | None = None, case_id: str | None = None) -> list[dict]:
        out: list[dict] = []
        targets = [case_id] if case_id is not None else list(self._cases.keys())
        for cid in targets:
            state = self.get(cid)
            if state is None:
                continue
            for entry in state.history:
                d: dict[str, Any] = entry.model_dump(mode="json")
                d["case_id"] = cid
                d["chain_valid"] = state.verify_audit_chain()
                if actor is not None and d.get("actor") != actor:
                    continue
                out.append(d)
        return out


STORE = CaseStore()

__all__ = ["CaseStore", "STORE"]