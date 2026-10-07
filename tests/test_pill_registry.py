"""Phase 6: GET /pills backs the Governance screen's Pill Registry.

Covers the registry shape (all four pills, owner steward, shared KB
version) and that approval rate moves when a proposal for that pill's
cause is actually approved.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app, PILL_OWNERS


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_pills_lists_all_four_asset_types(client: TestClient):
    resp = client.get("/pills", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    pills = resp.json()["pills"]
    asset_types = {p["asset_type"] for p in pills}
    assert asset_types == {"CRAH", "Chiller", "UPS", "Pump"}
    for p in pills:
        assert p["owner_steward"] == PILL_OWNERS[p["asset_type"]]
        assert p["kb_version_label"]
        assert p["knowledge_count"] >= 0


def test_pills_share_one_kb_version(client: TestClient):
    """All four pills currently share one LearningStore -- the version
    label must be identical across rows, not independently tracked."""
    resp = client.get("/pills", params={"user": "tech1"})
    labels = {p["kb_version_label"] for p in resp.json()["pills"]}
    assert len(labels) == 1


def test_approval_rate_reflects_a_real_approved_proposal(client: TestClient):
    # Close a CRAH case with validated feedback and get it approved.
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    client.post(f"/cases/{case_id}/approval", params={
        "user": "mgr1", "decision": "approve", "rationale": "test",
    })
    client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure",
    })
    fb = client.post(f"/cases/{case_id}/feedback", params={"user": "steward1"}).json()
    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    pid = next(p["proposal_id"] for p in queue if p["feedback_id"] == fb["feedback_id"])
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "reviewed against the transcript"})

    pills = client.get("/pills", params={"user": "tech1"}).json()["pills"]
    crah = next(p for p in pills if p["asset_type"] == "CRAH")
    assert crah["proposals_approved"] >= 1
    assert crah["approval_rate"] is not None and crah["approval_rate"] > 0
