"""SQLite persistence for case and governance state.

This module intentionally keeps the storage boundary separate from the runtime
state machine so the repository can persist across process restarts without
changing the rest of the API.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            db_path = os.path.join(root, "technical_services_pill.sqlite3")
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT,
                    actor TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    submitted_by TEXT NOT NULL,
                    corrections_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS validated_cases (
                    case_id TEXT PRIMARY KEY,
                    confirmed_cause TEXT NOT NULL,
                    fault_signature TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_versions (
                    version TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def save_case_state(self, case_id: str, state: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cases(case_id, state_json, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(case_id) DO UPDATE SET state_json = excluded.state_json, updated_at = CURRENT_TIMESTAMP",
                (case_id, json.dumps(state, sort_keys=True)),
            )
            conn.commit()

    def get_case_state(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["state_json"])

    def list_case_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT case_id FROM cases ORDER BY case_id").fetchall()
        return [r["case_id"] for r in rows]

    def add_case_event(self, case_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO case_events(case_id, event_type, payload_json) VALUES (?, ?, ?)",
                (case_id, event_type, json.dumps(payload, sort_keys=True)),
            )
            conn.commit()

    def add_audit_event(self, case_id: str | None, actor: str | None, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(case_id, actor, event_type, payload_json) VALUES (?, ?, ?, ?)",
                (case_id, actor, event_type, json.dumps(payload, sort_keys=True)),
            )
            conn.commit()

    def save_feedback(self, feedback_id: str, case_id: str, submitted_by: str, corrections: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback(feedback_id, case_id, submitted_by, corrections_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(feedback_id) DO UPDATE SET case_id = excluded.case_id, submitted_by = excluded.submitted_by, corrections_json = excluded.corrections_json",
                (feedback_id, case_id, submitted_by, json.dumps(corrections, sort_keys=True)),
            )
            conn.commit()

    def save_knowledge_proposal(self, proposal_id: str, case_id: str, status: str, proposal: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO knowledge_proposals(proposal_id, case_id, status, proposal_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(proposal_id) DO UPDATE SET case_id = excluded.case_id, status = excluded.status, proposal_json = excluded.proposal_json",
                (proposal_id, case_id, status, json.dumps(proposal, sort_keys=True)),
            )
            conn.commit()

    def save_validated_case(self, case_id: str, confirmed_cause: str, fault_signature: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO validated_cases(case_id, confirmed_cause, fault_signature, payload_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(case_id) DO UPDATE SET confirmed_cause = excluded.confirmed_cause, fault_signature = excluded.fault_signature, payload_json = excluded.payload_json",
                (case_id, confirmed_cause, fault_signature, json.dumps(payload, sort_keys=True)),
            )
            conn.commit()

    def save_kb_version(self, version: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kb_versions(version, summary) VALUES (?, ?) ON CONFLICT(version) DO UPDATE SET summary = excluded.summary",
                (version, summary),
            )
            conn.commit()

    def list_kb_versions(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT version, summary, created_at FROM kb_versions ORDER BY created_at").fetchall()
        return [{"version": r["version"], "summary": r["summary"], "created_at": r["created_at"]} for r in rows]


DB = SQLiteStore()

__all__ = ["SQLiteStore", "DB"]
