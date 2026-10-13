"""An auditor who finds the knowledge base changed outside governance can
put back the last verified snapshot instead of re-signing the edit; the
snapshot is only trusted if its own ledger still verifies."""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import persistence
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _review(client, decision, target="ledger", user="auditor1", reason="compared with the paper records"):
    return client.post("/audit/review", params={
        "user": user, "target": target, "decision": decision, "reason": reason})


def test_restore_puts_back_the_verified_knowledge_and_records_why(client):
    assert LSTORE.verify_ledger()
    persistence.save_state()
    vc = LSTORE.validated[-1]
    genuine = vc.confirmed_cause
    vc.confirmed_cause = "aliens_did_it"
    try:
        assert LSTORE.verify_ledger() is False
        r = _review(client, "restore")
        assert r.status_code == 200, r.text
        assert r.json()["ledger_valid"] is True
    finally:
        if not LSTORE.verify_ledger():
            LSTORE.review_broken_ledger(actor="test", reason="cleanup")
    assert LSTORE.validated[-1].confirmed_cause == genuine
    assert LSTORE.ledger[-1]["actor"] == "auditor1"
    assert "restored to the last verified snapshot" in LSTORE.ledger[-1]["reason"]
    assert _review(client, "restore").status_code == 409  # nothing left to review


def test_restore_is_ledger_only(client):
    r = _review(client, "restore", target="registry")
    assert r.status_code == 400 and "only the knowledge ledger" in r.json()["detail"]


def test_an_edited_verified_snapshot_is_refused_and_nothing_changes(client):
    persistence.save_state()
    db = persistence.db_path()
    with sqlite3.connect(db) as conn:
        (blob,) = conn.execute("SELECT blob FROM snapshots WHERE key = 'learning_verified'").fetchone()
        rec = json.loads(blob)
        rec["validated"][-1]["confirmed_cause"] = "forged_in_the_backup"
        conn.execute("UPDATE snapshots SET blob = ? WHERE key = 'learning_verified'", (json.dumps(rec),))
    vc = LSTORE.validated[-1]
    vc.confirmed_cause, genuine = "aliens_did_it", vc.confirmed_cause
    try:
        r = _review(client, "restore")
        assert r.status_code == 409 and "no longer verifies" in r.json()["detail"]
        assert LSTORE.validated[-1].confirmed_cause == "aliens_did_it"  # left as it was
    finally:
        LSTORE.validated[-1].confirmed_cause = genuine  # the revert loaded fresh objects
        LSTORE.rebuild_stats()
    assert LSTORE.verify_ledger()
    persistence.save_state()  # rewrite a genuine verified snapshot for later tests
