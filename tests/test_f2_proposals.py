"""F2 acceptance tests: feedback governance via proposals.

Tests the proposal workflow: feedback creates a pending proposal, the
steward approves or rejects it, and rollback removes approved cases.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE
from technical_services_pill.store import STORE as CASE_STORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_closed_case(client: TestClient, asset_id: str = "CRAH-DC1-01", corrections: dict | None = None) -> str:
    """Create a case, advance it, approve, record outcome, submit feedback.

    Returns the feedback_id of the submitted proposal.
    """
    # Create + advance
    resp = client.post("/cases", params={
        "asset_id": asset_id, "sensor_id": "SA-TEMP-01",
        "user": "tech1", "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    assert resp.status_code == 200
    case_id = resp.json()["case_id"]

    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200

    # Approve (need manager)
    resp = client.post(f"/cases/{case_id}/approval", params={
        "user": "mgr1", "decision": "approve",
        "rationale": "test approval",
    })
    assert resp.status_code == 200

    # Work order
    resp = client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    assert resp.status_code == 200

    # Outcome
    resp = client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved",
        "root_cause_confirmed": "sensor_hardware_failure",
        "verified_by": "tech1",
    })
    assert resp.status_code == 200

    # Feedback (creates a pending proposal)
    resp = client.post(f"/cases/{case_id}/feedback", params={
        "user": "steward1",
    }, json=corrections)
    assert resp.status_code == 200, resp.text
    fb_id = resp.json()["feedback_id"]

    # Verify proposal is pending
    assert resp.json()["proposal_status"] == "pending"
    return fb_id


def test_f2_feedback_creates_pending_proposal(client: TestClient):
    """Feedback must create a pending proposal, not enter the KB directly."""
    fb_id = _create_closed_case(client)

    # Check the queue
    resp = client.get("/kb/queue", params={"user": "steward1"})
    assert resp.status_code == 200
    queue = resp.json()["queue"]
    assert any(p["feedback_id"] == fb_id for p in queue), (
        "proposal must appear in the pending queue"
    )


def test_f2_approve_proposal_ingests_into_kb(client: TestClient):
    """Approving a proposal ingests it into the KB and bumps the version."""
    fb_id = _create_closed_case(client)
    version_before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]

    # Find the proposal
    resp = client.get("/kb/queue", params={"user": "steward1"})
    proposal_id = next(
        p["proposal_id"] for p in resp.json()["queue"] if p["feedback_id"] == fb_id
    )

    # Approve it
    resp = client.post(f"/kb/proposals/{proposal_id}/approve", params={"user": "steward2"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    version_after = resp.json()["kb_version"]
    assert version_after == version_before + 1, "KB version must increment on approve"

    # Verify it's no longer pending
    resp = client.get("/kb/queue", params={"user": "steward1"})
    assert not any(p["proposal_id"] == proposal_id for p in resp.json()["queue"])

    # Verify feedback_added increased
    stats = client.get("/kb/stats", params={"user": "tech1"}).json()
    assert stats["feedback_added"] > 0, "approved proposal must count as feedback_added"


def test_f2_reject_proposal_does_not_enter_kb(client: TestClient):
    """Rejecting a proposal keeps it out of the KB."""
    fb_id = _create_closed_case(client)
    version_before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]

    resp = client.get("/kb/queue", params={"user": "steward1"})
    proposal_id = next(
        p["proposal_id"] for p in resp.json()["queue"] if p["feedback_id"] == fb_id
    )

    resp = client.post(f"/kb/proposals/{proposal_id}/reject", params={
        "user": "steward1", "reason": "invalid cause attribution",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # Version must NOT increment
    version_after = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    assert version_after == version_before, "KB version must not change on reject"

    # Not in queue anymore
    resp = client.get("/kb/queue", params={"user": "steward1"})
    assert not any(p["proposal_id"] == proposal_id for p in resp.json()["queue"])


def test_f2_rollback_removes_approved_cases(client: TestClient):
    """Rollback removes all cases added after the target version."""
    fb1 = _create_closed_case(client)
    # Approve first proposal
    resp = client.get("/kb/queue", params={"user": "steward1"})
    pid1 = next(p["proposal_id"] for p in resp.json()["queue"] if p["feedback_id"] == fb1)
    client.post(f"/kb/proposals/{pid1}/approve", params={"user": "steward2"})

    fb2 = _create_closed_case(client)
    resp = client.get("/kb/queue", params={"user": "steward1"})
    pid2 = next(p["proposal_id"] for p in resp.json()["queue"] if p["feedback_id"] == fb2)
    client.post(f"/kb/proposals/{pid2}/approve", params={"user": "steward2"})

    version = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    assert version >= 2

    # Rollback to version 1 (keep only first approved proposal)
    # Requires rollback_knowledge_version capability (admin only)
    resp = client.post("/kb/rollback/1", params={"user": "admin1"})
    assert resp.status_code == 200
    assert resp.json()["rolled_back_to"] == 1
    assert resp.json()["removed_cases"] >= 1

    # Version should be 1 now
    stats = client.get("/kb/stats", params={"user": "tech1"}).json()
    assert stats["kb_version"] == 1


def test_f2_rbac_kb_queue_requires_steward(client: TestClient):
    """Technician cannot access the KB queue (requires approve_knowledge_version)."""
    resp = client.get("/kb/queue", params={"user": "tech1"})
    assert resp.status_code == 403, "technician must not access KB queue"


def test_f2_rbac_rollback_requires_steward(client: TestClient):
    """Technician cannot rollback (requires rollback_knowledge_version — admin only)."""
    resp = client.post("/kb/rollback/0", params={"user": "tech1"})
    assert resp.status_code == 403, "technician must not rollback KB"


def test_f2_proposer_cannot_approve_own_proposal(client: TestClient):
    """Separation of actors: whoever submitted the feedback cannot approve it."""
    _create_closed_case(client)  # submitted by steward1
    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    pid = queue[-1]["proposal_id"]
    assert queue[-1]["submitted_by"] == "steward1"

    own = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1"})
    assert own.status_code == 403
    other = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2"})
    assert other.status_code == 200


def test_f2_submitted_by_cannot_be_spoofed(client: TestClient):
    """A client-supplied submitted_by is ignored; the caller is the proposer."""
    _create_closed_case(client, corrections={"submitted_by": "steward2"})
    queue = client.get("/kb/queue", params={"user": "steward2"}).json()["queue"]
    assert queue[-1]["submitted_by"] == "steward1"
