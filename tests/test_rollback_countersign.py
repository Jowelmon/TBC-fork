"""Rollback is two-person: an admin asks, the pill's steward countersigns.
Nothing changes until then, and the ledger names both people."""
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE

import pytest


@pytest.fixture(autouse=True)
def _no_requests_left_by_earlier_tests():
    # The store is shared across the suite; a request one test leaves pending
    # would block the next test's request for the same pill.
    LSTORE.rollback_requests = []



def _client() -> TestClient:
    return TestClient(app)


def _move_crah_forward() -> tuple[int, int]:
    """Approve one CRAH proposal. Returns (the live version before it, the
    version now): the rollback target is the one before, which is live."""
    from tests.test_audit_and_stale_knowledge import _approved_feedback

    before = LSTORE.version_of("CRAH")
    _approved_feedback(_client())
    return before, LSTORE.version_of("CRAH")


def test_asking_for_a_rollback_changes_nothing_until_countersigned():
    client = _client()
    target, current = _move_crah_forward()
    asked = client.post(f"/kb/rollback/{target}",
                        params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"})
    assert asked.status_code == 200, asked.text
    body = asked.json()
    assert body["status"] == "awaiting_countersign"
    assert body["countersigned_by"] == "steward1"
    assert LSTORE.version_of("CRAH") == current, "the rollback must wait for countersign"
    preview = body["request"]["preview"]
    assert set(preview) >= {"validated_cases", "expert_heuristics", "proposals", "versions"}


def test_admin_cannot_countersign_their_own_request():
    client = _client()
    target, current = _move_crah_forward()
    rid = client.post(f"/kb/rollback/{target}",
                      params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).json()["request"]["request_id"]
    assert client.post(f"/kb/rollback-requests/{rid}/countersign",
                       params={"user": "admin1", "reason": "ok"}).status_code == 403
    assert LSTORE.version_of("CRAH") == current


def test_a_steward_who_does_not_decide_the_pill_cannot_countersign():
    client = _client()
    target, current = _move_crah_forward()
    rid = client.post(f"/kb/rollback/{target}",
                      params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).json()["request"]["request_id"]
    # steward2 owns Chiller and Pump, not CRAH.
    assert client.post(f"/kb/rollback-requests/{rid}/countersign",
                       params={"user": "steward2", "reason": "ok"}).status_code == 403
    assert LSTORE.version_of("CRAH") == current


def test_owner_countersign_rolls_back_and_the_ledger_names_both_people():
    client = _client()
    target, current = _move_crah_forward()
    rid = client.post(f"/kb/rollback/{target}",
                      params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).json()["request"]["request_id"]
    done = client.post(f"/kb/rollback-requests/{rid}/countersign",
                       params={"user": "steward1", "reason": "agreed"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "countersigned"
    assert done.json()["result"]["rolled_back_to"] == target
    assert LSTORE.version_of("CRAH") == target

    entries = client.get("/kb/ledger", params={"user": "auditor1"}).json()["entries"]
    assert any(e["action"] == "rollback_requested" and e["actor"] == "admin1" for e in entries)
    assert any(e["action"] == "rollback" and e["actor"] == "admin1, countersigned by steward1"
               for e in entries)


def test_countersigning_twice_is_refused():
    client = _client()
    target, current = _move_crah_forward()
    rid = client.post(f"/kb/rollback/{target}",
                      params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).json()["request"]["request_id"]
    assert client.post(f"/kb/rollback-requests/{rid}/countersign",
                       params={"user": "steward1", "reason": "ok"}).status_code == 200
    again = client.post(f"/kb/rollback-requests/{rid}/countersign",
                        params={"user": "steward1", "reason": "ok"})
    assert again.status_code == 409


def test_a_second_request_for_the_same_pill_waits_for_the_first():
    client = _client()
    target, current = _move_crah_forward()
    first = client.post(f"/kb/rollback/{target}",
                        params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"})
    assert first.status_code == 200
    second = client.post(f"/kb/rollback/{target}",
                         params={"user": "admin1", "pill": "CRAH", "reason": "again"})
    assert second.status_code == 409
    assert "already waiting" in second.text


def test_a_refused_rollback_changes_nothing_and_needs_a_reason():
    client = _client()
    target, current = _move_crah_forward()
    rid = client.post(f"/kb/rollback/{target}",
                      params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).json()["request"]["request_id"]
    assert client.post(f"/kb/rollback-requests/{rid}/reject",
                       params={"user": "steward1"}).status_code == 400
    refused = client.post(f"/kb/rollback-requests/{rid}/reject",
                          params={"user": "steward1", "reason": "the batch is fine"})
    assert refused.status_code == 200
    assert refused.json()["status"] == "rejected"
    assert LSTORE.version_of("CRAH") == current


def test_technician_cannot_ask_or_countersign():
    client = _client()
    assert client.post("/kb/rollback/0", params={"user": "tech1", "pill": "CRAH", "reason": "x"}).status_code == 403
    assert client.get("/kb/rollback-requests", params={"user": "tech1"}).status_code == 200
