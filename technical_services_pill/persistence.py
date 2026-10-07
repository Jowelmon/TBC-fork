"""SQLite persistence for cases, knowledge proposals and KB versions.

The engine keeps its working state in two in-process singletons:
``store.STORE`` (cases, each with its keyed audit chain) and
``learning.STORE`` (validated knowledge, proposals, versions and the
governance ledger). This module snapshots both into a local SQLite file as
JSON after every state-changing request and restores them on startup, so a
server restart loses nothing.

Snapshots are plain JSON, never pickle: loading a snapshot can only ever
produce data, not run code. Integrity on restore: every case's audit chain
and the governance ledger are re-verified after loading, and failures are
reported rather than silently trusted.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import learning, store, tools
from .models import ValidatedCase

DEFAULT_DB_PATH = Path("data") / "tbc.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    key       TEXT PRIMARY KEY,
    blob      TEXT NOT NULL,
    saved_at  TEXT NOT NULL
)
"""

_LEARNING_FIELDS = (
    "_cause_stats", "_proposals", "_kb_version", "_version_seq", "_versions",
    "ledger", "ledger_seal", "_revocations", "expert_heuristics",
)


def db_path() -> Path:
    """Resolve the database path from ``TBC_DB_PATH`` or the default."""
    return Path(os.environ.get("TBC_DB_PATH", str(DEFAULT_DB_PATH)))


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def _case_record(state) -> dict[str, Any]:
    snap = state.snapshot()
    snap.pop("audit_chain_valid", None)
    snap["_gathering_loops"] = state._gathering_loops
    snap["_retrieval_rounds"] = state._retrieval_rounds
    return snap


def _state() -> dict[str, Any]:
    ls = learning.STORE
    return {
        "cases": {cid: _case_record(st) for cid, st in store.STORE._cases.items()},
        "learning": {
            "validated": [vc.model_dump(mode="json") for vc in ls.validated],
            **{f: getattr(ls, f) for f in _LEARNING_FIELDS},
        },
        "tool_audit_log": tools.TOOL_AUDIT_LOG,
        "seals": {"registry": store.STORE.registry_seal, "tool_log": tools.TOOL_LOG_SEAL["seal"]},
    }


def save_state(path: Path | None = None) -> None:
    """Write the current engine state to SQLite in one transaction."""
    path = path or db_path()
    now = datetime.now(timezone.utc).isoformat()
    with _connect(path) as conn:
        for key, value in _state().items():
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (key, blob, saved_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), now),
            )


def load_state(path: Path | None = None) -> dict[str, Any]:
    """Restore engine state from SQLite into the live singletons.

    A missing or empty database is not an error: the engine starts from
    seed data. A snapshot in an older, non-JSON format is ignored (run
    ``make reset``) rather than deserialised.
    """
    path = path or db_path()
    if not path.exists():
        return {"restored": False, "reason": "no database yet", "path": str(path)}

    with _connect(path) as conn:
        rows = dict(conn.execute("SELECT key, blob FROM snapshots").fetchall())
    if not rows:
        return {"restored": False, "reason": "database empty", "path": str(path)}
    try:
        data = {k: json.loads(v) for k, v in rows.items()}
    except (TypeError, ValueError):
        return {"restored": False, "reason": "snapshot is not JSON (older format); run make reset",
                "path": str(path)}

    if "cases" in data:
        store.STORE._cases.clear()
        for cid, rec in data["cases"].items():
            store.STORE._cases[cid] = store.STORE._restore_from_snapshot(rec)
    if "learning" in data:
        ls = learning.STORE
        rec = data["learning"]
        ls.validated = [ValidatedCase.model_validate(v) for v in rec["validated"]]
        for f in _LEARNING_FIELDS:
            setattr(ls, f, rec[f])
    if "tool_audit_log" in data:
        tools.TOOL_AUDIT_LOG[:] = data["tool_audit_log"]
    if "seals" in data:
        store.STORE.registry_seal = data["seals"]["registry"]
        tools.TOOL_LOG_SEAL["seal"] = data["seals"]["tool_log"]

    broken = [cid for cid, st in store.STORE._cases.items() if not st.verify_audit_chain()]
    return {
        "restored": True,
        "path": str(path),
        "cases": len(store.STORE._cases),
        "kb_version": learning.STORE.get_kb_version_label(),
        "pending_proposals": len(learning.STORE.list_pending_proposals()),
        "audit_chain_failures": broken,
        "ledger_valid": learning.STORE.verify_ledger(),
        "registry_valid": store.STORE.verify_registry(),
        "tool_log_valid": tools.verify_tool_log(),
    }
