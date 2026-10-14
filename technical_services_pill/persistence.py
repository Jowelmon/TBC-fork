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

Tamper evidence survives clean restarts: a snapshot whose on-disk contents
changed while the process was not looking (an external edit between saves, or
an edit made after a graceful shutdown) is archived to
``tbc.tampered.<timestamp>.sqlite`` and logged in the ``integrity_events``
table *before* the clean state overwrites it, so the FAIL badge a later
restart shows is backed by preserved evidence, not memory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import sys
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
);
CREATE TABLE IF NOT EXISTS integrity_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,
    event         TEXT NOT NULL,
    detail        TEXT NOT NULL,
    archived_path TEXT
);
"""

_log = logging.getLogger("tbc.persistence")

# In-session ledger of integrity events (also persisted; a restart replays
# this table into memory so the UI keeps showing what the service has seen).
_INTEGRITY_EVENTS: list[dict[str, Any]] = []

# keyed by (str(db_path), snapshot_key) -> the exact text we last loaded or
# wrote. save_state() compares the on-disk blob against this before
# overwriting: if they differ the disk was modified outside this process, and
# that evidence is archived instead of silently replaced.
_last_written: dict[tuple[str, str], str] = {}

# Tampering already archived and logged, so the same edit is never reported twice.
_reported: set[tuple] = set()

# _cause_stats is not saved: it is rebuilt from the validated cases on load.
_LEARNING_FIELDS = (
    "_proposals", "_kb_version", "_version_seq", "_versions",
    "ledger", "ledger_seal", "_revocations", "expert_heuristics", "rollback_requests",
)


_VERIFIED_KEY = "learning_verified"


def db_path() -> Path:
    """Resolve the database path from ``TBC_DB_PATH`` or the default."""
    return Path(os.environ.get("TBC_DB_PATH", str(DEFAULT_DB_PATH)))


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
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


def integrity_events() -> list[dict[str, Any]]:
    """Integrity events this process has seen (persisted across restarts)."""
    return list(_INTEGRITY_EVENTS)


def _archive(path: Path) -> str | None:
    """Copy the DB file as-is so tampered evidence survives the next write."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = path.with_name(f"{path.stem}.tampered.{ts}{path.suffix}")
    try:
        shutil.copyfile(path, target)
    except OSError:
        _log.exception("could not archive tampered snapshot to %s", target)
        return None
    return str(target)


def _record_event(
    path: Path,
    event: str,
    detail: str,
    archived_path: str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "detail": detail,
        "archived_path": archived_path,
    }
    _INTEGRITY_EVENTS.append(row)
    sql = ("INSERT INTO integrity_events (at, event, detail, archived_path)"
           " VALUES (?, ?, ?, ?)")
    args = (row["at"], row["event"], row["detail"], row["archived_path"])
    try:
        if conn is None:
            with _connect(path) as own:
                own.execute(sql, args)
        else:
            conn.execute(sql, args)
    except sqlite3.Error:
        # The event still shows for this session even if persisting it failed.
        _log.exception("could not persist integrity event %r", event)


def _load_events(conn: sqlite3.Connection) -> None:
    _INTEGRITY_EVENTS.clear()
    try:
        for at, event, detail, archived in conn.execute(
            "SELECT at, event, detail, archived_path FROM integrity_events ORDER BY id"
        ):
            _INTEGRITY_EVENTS.append(
                {"at": at, "event": event, "detail": detail, "archived_path": archived}
            )
    except sqlite3.Error:
        _log.exception("could not read integrity_events from %s", db_path())


def save_state(path: Path | None = None) -> None:
    """Write the current engine state to SQLite in one transaction.

    Before overwriting a snapshot that we previously wrote or loaded, its
    on-disk contents are compared against what we last saw. A mismatch means
    the file was edited outside this process since our last write: the
    tampered copy is archived and an integrity event is recorded. The write
    then goes ahead, but the tamper stays provable (archive + logged event),
    so a graceful shutdown can never make the evidence silently disappear.
    """
    path = path or db_path()
    now = datetime.now(timezone.utc).isoformat()
    keyed = str(path)

    with _connect(path) as conn:
        state = {k: json.dumps(v, default=str) for k, v in _state().items()}
        db_id = _db_id(path, conn) or _db_ids.setdefault(str(path), secrets.token_hex(12))
        state["meta"] = json.dumps({"db_id": db_id})
        # The last knowledge base the ledger vouched for: what an auditor can
        # restore after an edit outside governance, instead of re-signing it.
        if learning.STORE.verify_ledger():
            state[_VERIFIED_KEY] = state["learning"]

        # Pass 1: detect disk edits we never made, before writing anything.
        for key in state:
            row = conn.execute("SELECT blob FROM snapshots WHERE key = ?", (key,)).fetchone()
            disk = row[0] if row else None
            prev = _last_written.get((keyed, key))
            if prev is not None and disk is not None and disk != prev:
                marker = (keyed, key, hashlib.sha256(str(disk).encode()).hexdigest())
                if marker not in _reported:
                    _reported.add(marker)
                    _record_event(
                        path,
                        "snapshot_modified_between_saves",
                        f"snapshot {key!r} changed on disk since this process "
                        "wrote it; tampered copy preserved",
                        _archive(path),
                        conn=conn,
                    )

        # Pass 2: write the snapshots and remember exactly what we wrote.
        for key, blob in state.items():
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (key, blob, saved_at) VALUES (?, ?, ?)",
                (key, blob, now),
            )
            _last_written[(keyed, key)] = blob
    _write_anchor(path, db_id)


# Each database carries a random id (snapshot "meta"); its anchor is filed
# under that id, so moving or renaming the file does not lose it. An index
# of path -> id also catches a different database swapped in at the same
# path: the previous database's anchor is then applied, and fails.
_db_ids: dict[str, str] = {}
# Paths whose database was swapped and not yet reviewed: their anchor and
# index entry are left alone, so one save cannot launder the swap.
_replaced: set[str] = set()


def _anchor_dir() -> Path:
    from .audit import key_dir

    return Path(os.environ["TBC_ANCHOR_DIR"]) if os.environ.get("TBC_ANCHOR_DIR") else key_dir()


def _path_key(path: Path) -> str:
    p = os.path.realpath(path)
    # macOS and Windows file systems ignore case: one file, one key.
    return p.lower() if sys.platform in ("darwin", "win32") else p


def _db_id(path: Path, conn: sqlite3.Connection | None = None) -> str | None:
    key = str(path)
    if key not in _db_ids:
        try:
            if conn is not None:
                row = conn.execute("SELECT blob FROM snapshots WHERE key = 'meta'").fetchone()
            elif Path(path).exists():
                with _connect(path) as c:
                    row = c.execute("SELECT blob FROM snapshots WHERE key = 'meta'").fetchone()
            else:
                row = None
            if row:
                _db_ids[key] = json.loads(row[0])["db_id"]
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            return None
    return _db_ids.get(key)


def anchor_path(path: Path | None = None) -> Path:
    """Where this database's anchor lives: beside the audit key (or in
    ``TBC_ANCHOR_DIR``), never beside the database, so whoever can put an
    older database back cannot also put back an older anchor."""
    db_id = _db_id(path or db_path()) or "unidentified"
    return _anchor_dir() / f"anchor-{db_id}.json"


def _signed_read(target: Path, kind: str) -> dict[str, Any] | None:
    from .audit import compute_hash

    try:
        rec = json.loads(target.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"invalid": True}
    body = {k: v for k, v in rec.items() if k != "sig"}
    return body if rec.get("sig") == compute_hash(kind, body) else {"invalid": True}


def _signed_write(target: Path, kind: str, body: dict[str, Any]) -> None:
    from .audit import compute_hash

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({**body, "sig": compute_hash(kind, body)}))
        os.replace(tmp, target)
    except OSError:
        _log.exception("could not write the integrity record %s", target)


def _read_anchor(path: Path, db_id: str | None) -> tuple[dict[str, Any] | None, str]:
    """(anchor, how). If this path last held a different database, that
    one's anchor applies ("replaced"): a database swapped in at the path
    is checked against what was there, not trusted for being well signed.
    Otherwise the anchor filed under this database's own id ("own")."""
    index = _signed_read(_anchor_dir() / "anchor-index.json", "anchor-index") or {}
    prev = None if index.get("invalid") else (index.get("paths") or {}).get(_path_key(path))
    if prev and prev != db_id:
        a = _signed_read(_anchor_dir() / f"anchor-{prev}.json", "anchor")
        if a is not None and not a.get("invalid"):
            return a, "replaced"
    if db_id:
        a = _signed_read(_anchor_dir() / f"anchor-{db_id}.json", "anchor")
        if a is not None:
            return a, "invalid" if a.get("invalid") else "own"
    return None, "missing"


def _write_anchor(path: Path, db_id: str) -> None:
    """Record the high-water mark: the ledger's length and head while it
    verifies, and each case's history length and head while its chain
    verifies. A part that fails verification keeps its last good value."""
    ls, cases = learning.STORE, store.STORE
    if str(path) in _replaced:
        if not (ls.verify_ledger() and cases.verify_registry()):
            return
        _replaced.discard(str(path))  # an auditor has reviewed it: new baseline
    old, how = _read_anchor(path, db_id)
    old = old if how == "own" else {}
    old_cases = old.get("cases") if isinstance(old.get("cases"), dict) else {}
    case_heads = dict(old_cases)
    if cases.verify_registry():
        case_heads = {cid: old_cases.get(cid) for cid in cases._cases}
    for cid, st in cases._cases.items():
        if st.history and st.verify_audit_chain():
            case_heads[cid] = {"length": len(st.history), "head": st.history[-1].hash}
    body = {
        "db_id": db_id,
        "ledger": ({"length": len(ls.ledger), "head": ls.ledger[-1]["hash"]}
                   if ls.ledger and ls.verify_ledger() else old.get("ledger")),
        "cases": case_heads,
    }
    _signed_write(_anchor_dir() / f"anchor-{db_id}.json", "anchor", body)
    index = _signed_read(_anchor_dir() / "anchor-index.json", "anchor-index") or {}
    paths = {} if index.get("invalid") else dict(index.get("paths") or {})
    if paths.get(_path_key(path)) != db_id:
        paths[_path_key(path)] = db_id
        _signed_write(_anchor_dir() / "anchor-index.json", "anchor-index", {"paths": paths})


def _apply_learning(rec: dict[str, Any]) -> None:
    ls = learning.STORE
    ls.validated = [ValidatedCase.model_validate(v) for v in rec["validated"]]
    for f in _LEARNING_FIELDS:
        # Snapshots from before rollback requests existed have no such list.
        setattr(ls, f, rec.get(f, []) if f == "rollback_requests" else rec[f])
    ls.rebuild_stats()


def restore_verified_learning(path: Path | None = None) -> None:
    """Put back the last knowledge base whose ledger verified when saved.

    The snapshot is only trusted if its own ledger still verifies with this
    deployment's key and reaches the anchor recorded outside the database,
    so neither editing it nor planting an older genuine copy gets through.
    On any failure the live (broken) state is left exactly as it was."""
    path = path or db_path()
    with _connect(path) as conn:
        row = conn.execute("SELECT blob FROM snapshots WHERE key = ?", (_VERIFIED_KEY,)).fetchone()
    if row is None:
        raise ValueError("there is no verified knowledge snapshot to restore")
    current = json.loads(json.dumps(_state()["learning"], default=str))
    _apply_learning(json.loads(row[0]))
    if not learning.STORE.verify_ledger():
        _apply_learning(current)
        raise ValueError("the last verified knowledge snapshot no longer verifies either; "
                         "compare it with the archived copies listed under Integrity events before deciding to accept")


def load_state(path: Path | None = None) -> dict[str, Any]:
    """Restore engine state from SQLite into the live singletons.

    A missing or empty database is not an error: the engine starts from
    seed data. A snapshot in an older, non-JSON format is ignored (run
    ``make reset``) rather than deserialised.

    Integrity: if any case's audit chain fails, the database is archived to a
    ``tbc.tampered.<timestamp>.sqlite`` file and logged as an integrity event
    *before* anything can overwrite it, so a clean restart later cannot make
    the tamper evidence disappear.
    """
    path = path or db_path()
    keyed = str(path)
    if not path.exists():
        return {"restored": False, "reason": "no database yet", "path": str(path)}

    with _connect(path) as conn:
        rows = dict(conn.execute("SELECT key, blob FROM snapshots").fetchall())
        _load_events(conn)
    if not rows:
        return {"restored": False, "reason": "database empty", "path": str(path)}
    try:
        data = {k: json.loads(v) for k, v in rows.items()}
    except (TypeError, ValueError):
        return {"restored": False, "reason": "snapshot is not JSON (older format); run make reset",
                "path": str(path)}

    # A snapshot we just loaded is the baseline for in-session edit detection.
    for key, blob in rows.items():
        _last_written[(keyed, key)] = blob

    if "cases" in data:
        store.STORE._cases.clear()
        for cid, rec in data["cases"].items():
            store.STORE._cases[cid] = store.STORE._restore_from_snapshot(rec)
    if "learning" in data:
        _apply_learning(data["learning"])
    if "tool_audit_log" in data:
        tools.TOOL_AUDIT_LOG[:] = data["tool_audit_log"]
    if "seals" in data:
        store.STORE.registry_seal = data["seals"]["registry"]
        tools.TOOL_LOG_SEAL["seal"] = data["seals"]["tool_log"]

    # The anchor says how far this database had got. Without it, an older
    # genuine copy put back in place would pass every check inside it.
    db_id = (data.get("meta") or {}).get("db_id")
    _db_ids.pop(keyed, None)
    if db_id:
        _db_ids[keyed] = db_id
    anchor, how = _read_anchor(path, db_id)
    if how == "missing":
        _record_event(path, "anchor_missing",
                      "no integrity anchor for this database: expected only after a reset or a "
                      "move; otherwise an older copy may have been put back undetected")
    elif how == "invalid":
        _record_event(path, "anchor_invalid",
                      "the integrity anchor for this database was edited (signature fails); "
                      "a rollback cannot be ruled out")
    _replaced.discard(keyed)
    if how == "replaced":
        _replaced.add(keyed)
        _record_event(path, "database_replaced",
                      "a different database was put in place of the one this deployment last "
                      "recorded at this path; it is checked against that one's anchor")
    if how in ("own", "replaced"):
        learning.STORE.anchor = anchor.get("ledger")
        heads = anchor.get("cases")
        heads = heads if isinstance(heads, dict) else {cid: None for cid in heads or ()}
        store.STORE.anchor_cases = set(heads)
        for cid, st in store.STORE._cases.items():
            st.anchor = heads.get(cid)

    broken = [cid for cid, st in store.STORE._cases.items() if not st.verify_audit_chain()]
    if broken:
        # One incident per broken case set: a NEW tamper (a different affected
        # case) gets a new marker and is reported again.
        marker = (keyed, "audit_chain_failure", frozenset(broken))
        if marker not in _reported:
            _reported.add(marker)
            _record_event(
                path,
                "audit_chain_failure_on_load",
                "audit chain failed for " + ", ".join(broken) + "; "
                "tampered snapshot preserved before any later save",
                _archive(path),
            )
    return {
        "restored": True,
        "path": str(path),
        "cases": len(store.STORE._cases),
        "kb_versions": learning.STORE.labels(),
        "pending_proposals": len(learning.STORE.list_pending_proposals()),
        "audit_chain_failures": broken,
        "ledger_valid": learning.STORE.verify_ledger(),
        "registry_valid": store.STORE.verify_registry(),
        "tool_log_valid": tools.verify_tool_log(),
        "integrity_events": list(_INTEGRITY_EVENTS),
    }
