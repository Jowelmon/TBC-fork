"""Tamper evidence must survive clean restarts: a graceful shutdown's
autosave must never silently overwrite a tampered snapshot.

Two complementary mechanisms:
  - load_state() archives + logs an ``audit_chain_failure_on_load`` event for
    any case whose SHA-256 chain fails re-verification, *before* any later
    save can overwrite the tampered snapshot;
  - save_state() compares the on-disk snapshot bytes against what the process
    last wrote/loaded and archives + logs a ``snapshot_modified_between_saves``
    event if they differ, catching edits made while the process is running
    (including across a graceful shutdown).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import learning, persistence, store, tools
from technical_services_pill.app import app

NEW_CASE = {
    "user": "tech1",
    "asset_id": "CRAH-DC1-01",
    "sensor_id": "SA-TEMP-01",
    "observation_type": "temperature_measurement_missing",
    "reading_status": "absent",
}


@pytest.fixture()
def fresh_state():
    """Reset persistence module state so tests can't leak into each other."""
    persistence._INTEGRITY_EVENTS.clear()
    persistence._last_written.clear()
    persistence._reported.clear()
    yield
    persistence._INTEGRITY_EVENTS.clear()
    persistence._last_written.clear()
    persistence._reported.clear()


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path):
    # The engine singletons are process-wide; make each test a clean slate so
    # older tests' cases can't leak into this test's snapshot file.
    store.STORE._cases.clear()
    learning.STORE.__init__()
    tools.TOOL_AUDIT_LOG[:] = []
    return tmp_path


def _tamper_cases_blob(db):
    """Rewrite the persisted cases snapshot with an edited audit reason,
    as a direct edit of ``data/tbc.sqlite`` would."""
    conn = sqlite3.connect(db)
    (blob,) = conn.execute(
        "SELECT blob FROM snapshots WHERE key='cases'"
    ).fetchone()
    data = json.loads(blob)
    mutated = False
    for rec in data.values():
        if rec.get("history"):
            rec["history"][-1]["reason"] += " [TAMPERED-EDIT]"
            mutated = True
            break
    assert mutated, "no case history found to tamper"
    conn.execute(
        "INSERT OR REPLACE INTO snapshots (key, blob, saved_at) VALUES (?, ?, ?)",
        ("cases", json.dumps(data), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _integrity_events(db) -> list[dict]:
    conn = sqlite3.connect(db)
    rows = list(conn.execute(
        "SELECT at, event, detail, archived_path FROM integrity_events ORDER BY id"
    ))
    conn.close()
    return [dict(zip(("at", "event", "detail", "archived_path"), r)) for r in rows]


def test_tamper_while_running_is_archived_at_next_save(
    tmp_path, monkeypatch, fresh_state, isolated_store
):
    """A disk edit inside a running process is caught by the next save --
    no restart needed, so a graceful shutdown cannot silently erase it."""
    db = tmp_path / "tbc.sqlite"
    monkeypatch.setenv("TBC_DB_PATH", str(db))
    monkeypatch.setenv("TBC_PERSIST", "1")

    with TestClient(app) as client:
        cid = client.post("/cases", params=dict(NEW_CASE)).json()["case_id"]
        client.post(f"/cases/{cid}/advance", params={"user": "tech1"})

        _tamper_cases_blob(db)

        # The next state-changing request autosaves and must detect the edit.
        resp = client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
        assert resp.status_code == 200

        events = client.get(
            "/system/integrity", params={"user": "auditor1"}
        ).json()["events"]
        assert any(
            e["event"] == "snapshot_modified_between_saves" for e in events
        ), events

    archived = list(tmp_path.glob("tbc.tampered.*.sqlite"))
    assert len(archived) == 1, "tampered snapshot must be preserved on disk"

    # The live service healed: a fresh restart verifies a clean chain.
    with TestClient(app) as client:
        snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
        assert snap["audit_chain_valid"] is True


def test_offline_tamper_evidence_survives_clean_restarts(
    tmp_path, monkeypatch, fresh_state, isolated_store
):
    """Offline tamper: load archives + reports it; later clean saves and
    restarts keep showing the event and keep the archived proof."""
    db = tmp_path / "tbc.sqlite"
    monkeypatch.setenv("TBC_DB_PATH", str(db))
    monkeypatch.setenv("TBC_PERSIST", "1")

    # Session 1: build a clean case and confirm a pristine start.
    with TestClient(app) as client:
        cid = client.post("/cases", params=dict(NEW_CASE)).json()["case_id"]
        client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    assert _integrity_events(db) == []

    # Intermediate edit with the server down (e.g. after a kill -9),
    # but now the NEXT clean shutdown/restart loop must not erase the proof.
    _tamper_cases_blob(db)

    # Session 2: restart detects the tampered chain and archives it.
    with TestClient(app) as client:
        events = client.get(
            "/system/integrity", params={"user": "auditor1"}
        ).json()["events"]
        assert any(
            e["event"] == "audit_chain_failure_on_load" for e in events
        ), events
        snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
        assert snap["audit_chain_valid"] is False

    archived = list(tmp_path.glob("tbc.tampered.*.sqlite"))
    assert len(archived) == 1

    # Session 3: another clean restart -- the integrity event and its archived
    # file must STILL be there, and the case must STILL be flagged (tampering
    # can't be silently "healed" away by a graceful restart loop).
    with TestClient(app) as client:
        snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
        assert snap["audit_chain_valid"] is False, (
            "tampering must stay detectable, never silently cleaned up"
        )
        events = client.get(
            "/system/integrity", params={"user": "auditor1"}
        ).json()["events"]
        assert any(
            e["event"] == "audit_chain_failure_on_load" for e in events
        ), "event must not vanish after clean restarts"
        assert len([
            e for e in events if e["event"] == "audit_chain_failure_on_load"
        ]) == 1, "the same tamper must not be double-reported"
    assert len(list(tmp_path.glob("tbc.tampered.*.sqlite"))) == 1


def test_integrity_endpoint_is_rbac_gated(
    tmp_path, monkeypatch, fresh_state, isolated_store
):
    monkeypatch.setenv("TBC_DB_PATH", str(tmp_path / "tbc.sqlite"))
    monkeypatch.setenv("TBC_PERSIST", "1")
    with TestClient(app) as client:
        ok = client.get("/system/integrity", params={"user": "auditor1"})
        assert ok.status_code == 200
        assert ok.json() == {"events": []}
        denied = client.get("/system/integrity", params={"user": "tech1"})
        assert denied.status_code == 403

def test_integrity_events_card_is_in_the_ui():
    src = open("frontend/static/js/screens.js", encoding="utf-8").read()
    assert "Integrity Events" in src and "integrity-body" in src
