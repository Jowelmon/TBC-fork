"""Putting an older, genuinely signed copy of the database back in place.

Every seal lives inside the snapshot it protects, so an older snapshot
verifies on its own. A signed anchor kept beside the audit key (not beside
the database) records how far the ledger and the case set had got: a
replayed copy fails verification, Restore refuses a planted older copy, and
an auditor's Accept makes the older copy the new baseline on the record."""
from __future__ import annotations

import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import learning, persistence, store, tools
from technical_services_pill.app import app

QUOTE = "If the sensor reads nothing and it is past its calibration date, check the alarm log, then replace it."
NEW_CASE = {"user": "tech1", "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01",
            "observation_type": "temperature_measurement_missing", "reading_status": "absent"}


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "tbc.sqlite"
    monkeypatch.setenv("TBC_DB_PATH", str(path))
    monkeypatch.setenv("TBC_PERSIST", "1")
    for reset in (persistence._INTEGRITY_EVENTS, persistence._last_written, persistence._reported):
        reset.clear()
    store.STORE._cases.clear()
    store.STORE.reseal()
    learning.STORE.__init__()
    tools.TOOL_AUDIT_LOG[:] = []
    yield path
    store.STORE._cases.clear()
    store.STORE.reseal()
    learning.STORE.__init__()


def _restart():
    for reset in (persistence._last_written, persistence._reported):
        reset.clear()


def _two_sessions(db):
    """Session A: one case. Session B: approved knowledge and a second case.
    Returns (copy of A's database, the second case id)."""
    with TestClient(app) as c:
        c.post("/cases", params=NEW_CASE)
    older = db.with_name("older.sqlite")
    shutil.copyfile(db, older)
    with TestClient(app) as c:
        pid = c.post("/capture/interview", params={"user": "steward1"}, json={
            "expert_name": "K. Wong", "expert_role": "Senior Technician", "asset_type": "CRAH",
            "transcript": f"Technician: {QUOTE}\n", "expert_consent": True,
            "heuristics": [{"symptom_pattern": QUOTE, "likely_cause": "sensor_hardware_failure",
                            "evidence_quote": QUOTE, "checks": [], "do_not": [], "escalate_when": []}],
        }).json()["proposal_id"]
        r = c.post(f"/kb/proposals/{pid}/approve",
                   params={"user": "steward2", "rationale": "checked", "safety_reviewed": "true"})
        assert r.status_code == 200, r.text
        second = c.post("/cases", params=NEW_CASE).json()["case_id"]
    return older, second


def _status(c):
    return c.get("/audit/status", params={"user": "auditor1"}).json()



def _acknowledge_tamper(c):
    """An auditor acknowledges every tamper event recorded by the restart(s)."""
    for e in _status(c)["unacknowledged_tamper_events"]:
        r = c.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": e["at"],
                                                        "reason": "reviewed with the case and ledger reviews"})
        assert r.status_code == 200, r.text

def test_a_replayed_older_database_is_caught_and_cannot_be_restored_over(db):
    older, second = _two_sessions(db)
    shutil.copyfile(older, db)  # the whole older database, every seal intact
    _restart()
    with TestClient(app) as c:
        st = _status(c)
        assert st["ledger_valid"] is False and "older copy" in st["ledger_problem"]
        assert st["registry_valid"] is False and second in st["missing_cases"]
        # Its own "last verified" copy is just as old: Restore refuses it.
        r = c.post("/audit/review", params={"user": "auditor1", "target": "ledger",
                                            "decision": "restore", "reason": "try the backup"})
        assert r.status_code == 409 and "no longer verifies" in r.json()["detail"]
        # Accepting it is possible, and on the record.
        r = c.post("/audit/review", params={"user": "auditor1", "target": "ledger", "decision": "accept",
                                            "reason": "restored from last night's backup on purpose"})
        assert r.status_code == 200 and r.json()["ledger_valid"] is True
        assert "older copy" in learning.STORE.ledger[-1]["reason"]
        r = c.post("/audit/review", params={"user": "auditor1", "target": "registry", "decision": "accept",
                                            "reason": "same restore"})
        assert r.status_code == 200 and _status(c)["ok"] is True
    _restart()
    with TestClient(app) as c:  # the accepted copy is the new baseline
        _acknowledge_tamper(c)
        assert _status(c)["ok"] is True


def test_replaying_only_the_knowledge_base_is_undone_by_restore(db):
    _two_sessions(db)
    with sqlite3.connect(db) as conn:
        approved = conn.execute("SELECT blob FROM snapshots WHERE key='learning'").fetchone()[0]
    older = db.with_name("older.sqlite")
    with sqlite3.connect(older) as conn:
        old_learning = conn.execute("SELECT blob FROM snapshots WHERE key='learning'").fetchone()[0]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE snapshots SET blob=? WHERE key='learning'", (old_learning,))
    _restart()
    with TestClient(app) as c:
        assert "older copy" in _status(c)["ledger_problem"]
        r = c.post("/audit/review", params={"user": "auditor1", "target": "ledger",
                                            "decision": "restore", "reason": "rolled back by hand"})
        assert r.status_code == 200, r.text
        _acknowledge_tamper(c)
        assert _status(c)["ok"] is True
        assert any(p["status"] == "approved" for p in learning.STORE._proposals)
    assert approved  # (the approved state existed before the replay)


def test_an_edited_anchor_is_reported(db):
    _two_sessions(db)
    anchor = persistence.anchor_path(db)
    anchor.write_text(anchor.read_text().replace('"length": ', '"length": 1'))
    _restart()
    with TestClient(app) as c:
        events = c.get("/system/integrity", params={"user": "auditor1"}).json()["events"]
    assert any(e["event"] == "anchor_invalid" for e in events)


def _awaiting_case(c) -> str:
    cid = c.post("/cases", params=NEW_CASE).json()["case_id"]
    c.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def test_rolling_back_a_single_case_is_caught(db):
    """Judge 6: copy the database, reject a case, put the copy back. The
    ledger and the case set are unchanged, but the case's own history is
    shorter than the anchor recorded, so it is frozen until reviewed."""
    with TestClient(app) as c:
        cid = _awaiting_case(c)
    older = db.with_name("older.sqlite")
    shutil.copyfile(db, older)
    with TestClient(app) as c:
        r = c.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "reject", "rationale": "wrong cause"})
        assert r.status_code == 200, r.text
    shutil.copyfile(older, db)
    _restart()
    with TestClient(app) as c:
        st = _status(c)
        assert cid in st["broken_cases"] and "older copy of this case" in st["case_problems"][cid]
        r = c.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "x"})
        assert r.status_code == 423  # the rejection cannot be undone by putting a file back
        r = c.post("/audit/review", params={"user": "auditor1", "target": f"case:{cid}", "decision": "quarantine",
                                            "reason": "record rolled back outside the app"})
        assert r.status_code == 200 and cid not in r.json()["broken_cases"]
    _restart()
    with TestClient(app) as c:
        _acknowledge_tamper(c)
        assert _status(c)["ok"] is True


def test_the_anchor_follows_the_database_not_its_path(db, monkeypatch):
    """Moved or opened under a differently-cased path, an older copy is still
    checked against its own anchor (it carries its id inside)."""
    older, _ = _two_sessions(db)
    moved = db.with_name("Moved-DB.sqlite")
    shutil.copyfile(older, moved)
    monkeypatch.setenv("TBC_DB_PATH", str(moved))
    _restart()
    with TestClient(app) as c:
        assert "older copy" in (_status(c)["ledger_problem"] or "")


def test_a_different_database_at_the_same_path_is_reported_and_checked(db, tmp_path, monkeypatch):
    _two_sessions(db)
    other = tmp_path / "other" / "tbc.sqlite"
    monkeypatch.setenv("TBC_DB_PATH", str(other))
    for reset in (persistence._last_written, persistence._reported):
        reset.clear()
    store.STORE._cases.clear()
    store.STORE.reseal()
    learning.STORE.__init__()
    with TestClient(app) as c:
        c.post("/cases", params=NEW_CASE)
    shutil.copyfile(other, db)  # another deployment's database, its own seals intact
    monkeypatch.setenv("TBC_DB_PATH", str(db))
    _restart()
    with TestClient(app) as c:
        events = c.get("/system/integrity", params={"user": "auditor1"}).json()["events"]
        assert any(e["event"] == "database_replaced" for e in events)
        assert _status(c)["ok"] is False
        c.post("/cases", params=NEW_CASE)  # saves happen; they must not launder the swap
    _restart()
    with TestClient(app) as c:
        assert _status(c)["ok"] is False
        r = c.post("/audit/review", params={"user": "auditor1", "target": "ledger", "decision": "accept",
                                            "reason": "moved the other site's database here on purpose"})
        assert r.status_code == 200, r.text
        for target in ("registry",):
            if not _status(c)["registry_valid"]:
                c.post("/audit/review", params={"user": "auditor1", "target": target, "decision": "accept",
                                                "reason": "same move"})
        for cid in _status(c)["broken_cases"]:
            c.post("/audit/review", params={"user": "auditor1", "target": f"case:{cid}", "decision": "accept",
                                            "reason": "same move"})
        _acknowledge_tamper(c)
        assert _status(c)["ok"] is True
    _restart()
    with TestClient(app) as c:  # accepted: the new database is the baseline now
        _acknowledge_tamper(c)
        assert _status(c)["ok"] is True
