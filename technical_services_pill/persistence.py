"""SQLite persistence for cases, knowledge proposals and KB versions.

The engine keeps its working state in two in-process singletons:
``store.STORE`` (cases, each with its hash-chained audit trail) and
``learning.STORE`` (validated knowledge, pending/approved proposals, KB
version). This module snapshots both into a local SQLite file after every
state-changing request and restores them on startup, so a server restart
loses nothing: not cases, not pending proposals, not version history.

Integrity on restore: every case's SHA-256 audit chain is re-verified after
loading. A case whose chain no longer validates is reported in
``load_state()``'s result rather than silently trusted.

Scope note: snapshots use ``pickle`` and must only ever be loaded from a
file this service wrote itself (the default ``data/`` path is gitignored).
A production deployment would move to a relational schema in Postgres; the
store interfaces (``CaseStore``, ``LearningStore``) are the seam for that.
"""
from __future__ import annotations

import os
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import learning, store, tools

DEFAULT_DB_PATH = Path("data") / "tbc.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    key       TEXT PRIMARY KEY,
    blob      BLOB NOT NULL,
    saved_at  TEXT NOT NULL
)
"""


def db_path() -> Path:
    """Resolve the database path from ``TBC_DB_PATH`` or the default."""
    return Path(os.environ.get("TBC_DB_PATH", str(DEFAULT_DB_PATH)))


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def _state() -> dict[str, Any]:
    return {
        "cases": store.STORE._cases,
        "learning": learning.STORE.__dict__,
        "tool_audit_log": tools.TOOL_AUDIT_LOG,
    }


def save_state(path: Path | None = None) -> None:
    """Write the current engine state to SQLite in one transaction."""
    path = path or db_path()
    now = datetime.now(timezone.utc).isoformat()
    with _connect(path) as conn:
        for key, value in _state().items():
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (key, blob, saved_at) VALUES (?, ?, ?)",
                (key, pickle.dumps(value), now),
            )


def load_state(path: Path | None = None) -> dict[str, Any]:
    """Restore engine state from SQLite into the live singletons.

    Returns a summary including any cases whose audit chain failed
    re-verification. A missing database is not an error: the engine simply
    starts from seed data.
    """
    path = path or db_path()
    if not path.exists():
        return {"restored": False, "reason": "no database yet", "path": str(path)}

    with _connect(path) as conn:
        rows = dict(conn.execute("SELECT key, blob FROM snapshots").fetchall())
    if not rows:
        return {"restored": False, "reason": "database empty", "path": str(path)}

    if "cases" in rows:
        store.STORE._cases.clear()
        store.STORE._cases.update(pickle.loads(rows["cases"]))
    if "learning" in rows:
        restored = pickle.loads(rows["learning"])
        # Snapshots written before a field existed restore without it; take
        # that field's fresh default rather than failing on first access.
        for key, value in learning.LearningStore().__dict__.items():
            restored.setdefault(key, value)
        learning.STORE.__dict__.clear()
        learning.STORE.__dict__.update(restored)
    if "tool_audit_log" in rows:
        tools.TOOL_AUDIT_LOG[:] = pickle.loads(rows["tool_audit_log"])

    broken = [
        cid for cid, st in store.STORE._cases.items() if not st.verify_audit_chain()
    ]
    return {
        "restored": True,
        "path": str(path),
        "cases": len(store.STORE._cases),
        "kb_version": learning.STORE.get_kb_version_label(),
        "pending_proposals": len(learning.STORE.list_pending_proposals()),
        "audit_chain_failures": broken,
    }
