"""In-memory store of cases (``AgentState`` by case id).

Persistence lives in one place, ``persistence.py``, which snapshots this
store and the knowledge base together after every state-changing request
and restores them on startup.
"""
from __future__ import annotations

import uuid
from typing import Any

from .agent_state import AgentState
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
    """Store of ``AgentState`` by case id."""

    def __init__(self) -> None:
        self._cases: dict[str, AgentState] = {}
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
        return case_id

    def get(self, case_id: str) -> AgentState | None:
        return self._cases.get(case_id)

    def list(self) -> list[str]:
        return list(self._cases.keys())

    def snapshot(self, case_id: str) -> dict | None:
        state = self.get(case_id)
        return state.snapshot() if state is not None else None

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

__all__ = ["STORE", "CaseStore"]