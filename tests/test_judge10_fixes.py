"""Judge 10 fixes: a recorded tamper event stays open until an auditor
acknowledges it, and the acknowledgement lives in the governance ledger."""
from pathlib import Path

from fastapi.testclient import TestClient

from technical_services_pill import persistence
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


def _record_tamper(tmp_path: Path) -> str:
    persistence._record_event(tmp_path / "tbc.sqlite", "snapshot_modified_between_saves",
                              "test: snapshot changed outside the app")
    return persistence._INTEGRITY_EVENTS[-1]["at"]


def test_a_tamper_event_keeps_the_audit_verdict_open_until_an_auditor_acknowledges_it(tmp_path):
    client = TestClient(app)
    at = _record_tamper(tmp_path)
    try:
        status = client.get("/audit/status", params={"user": "tech1"}).json()
        assert status["ok"] is False
        assert any(e["at"] == at for e in status["unacknowledged_tamper_events"])

        # Only the auditor acknowledges; a steward or a technician cannot.
        assert client.post("/audit/tamper/acknowledge", params={"user": "steward1", "event_at": at,
                           "reason": "looked"}).status_code == 403
        assert client.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": at}).status_code == 400
        assert client.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": "1999-01-01",
                           "reason": "x"}).status_code == 404

        ok = client.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": at,
                         "reason": "reviewed the archived copy"})
        assert ok.status_code == 200, ok.text
        assert client.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": at,
                           "reason": "again"}).status_code == 409

        status = client.get("/audit/status", params={"user": "tech1"}).json()
        assert not any(e["at"] == at for e in status["unacknowledged_tamper_events"])
        listed = client.get("/system/integrity", params={"user": "auditor1"}).json()["events"]
        assert any(e["at"] == at and e["acknowledged"] for e in listed)
        assert any(e["action"] == "integrity_review" and f"tamper event {at} acknowledged" in e["reason"]
                   for e in LSTORE.ledger)
    finally:
        # Leave the shared suite state clean if an assertion failed part-way.
        client.post("/audit/tamper/acknowledge", params={"user": "auditor1", "event_at": at,
                    "reason": "test cleanup"})
