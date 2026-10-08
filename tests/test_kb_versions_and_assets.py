"""KB version addressing for rollback, and the second asset per pill that
lets more than one captured cause be reached in a live diagnosis."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.learning import kb_version_label


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_kb_versions_maps_int_to_the_same_label_shown_on_screen(client: TestClient):
    resp = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_label"] == f"CRAH v{kb_version_label(body['current_version'])}"
    for v in body["versions"]:
        assert v["label"] == kb_version_label(v["version"])
    # version 0 (seed) is always addressable, matching /kb/rollback/0 being valid.
    assert any(v["version"] == 0 for v in body["versions"])


def test_rollback_endpoint_and_versions_endpoint_agree_after_an_approval(client: TestClient):
    before = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()
    # Approve something to move the version forward.
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    client.post(f"/cases/{case_id}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "x"})
    client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure",
    })
    fb = client.post(f"/cases/{case_id}/feedback", params={"user": "steward1"}).json()
    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    pid = next(p["proposal_id"] for p in queue if p["feedback_id"] == fb["feedback_id"])
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "reviewed against the transcript"})

    after = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()
    assert after["current_version"] > before["current_version"]
    used_labels = {v["label"] for v in before["versions"]}
    assert after["current_label"] not in used_labels, "a version label must never be reused"
    # Rolling back to the pre-approval version via the exact int /kb/versions offered.
    resp = client.post(f"/kb/rollback/{before['current_version']}", params={"user": "admin1", "pill": "CRAH", "reason": "test rollback"})
    assert resp.status_code == 200, resp.text
    restored = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()
    assert restored["current_label"] == before["current_label"]


def test_chiller_dc1_02_resolves_to_condenser_fouling(client: TestClient):
    """Previously: every chiller case always resolved to refrigerant_leak,
    so condenser-fouling knowledge (e.g. from the sample interview) could
    never be demonstrated as reused. CHILLER-DC1-02 closes that gap."""
    resp = client.post("/cases", params={
        "asset_id": "CHILLER-DC1-02", "sensor_id": "CHILLER-DC1-02-s", "user": "tech1",
        "observation_type": "chiller_compressor_trip", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["diagnosis"]["top_cause_id"] == "condenser_fouling"


def test_pump_dc1_02_resolves_to_cavitation(client: TestClient):
    """Previously: every pump case always resolved to shaft_misalignment."""
    resp = client.post("/cases", params={
        "asset_id": "PUMP-DC1-02", "sensor_id": "PUMP-DC1-02-s", "user": "tech1",
        "observation_type": "pump_vibration_high", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["diagnosis"]["top_cause_id"] == "cavitation"


def test_versions_requires_only_view_case_but_rollback_requires_admin(client: TestClient):
    resp = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"})
    assert resp.status_code == 200
    resp = client.post("/kb/rollback/0", params={"user": "tech1", "pill": "CRAH"})
    assert resp.status_code == 403
