"""Two people per case, and an admin who runs the system but decides nothing.

- The AOM who approved the work cannot also verify its outcome.
- Admin cannot approve cases or review audit integrity.
- The technician who did the work can send feedback (a pending proposal).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _awaiting(client):
    cid = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent"}).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    assert client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["current_state"] == "AWAITING_APPROVAL"
    return cid


def test_approver_cannot_verify_their_own_outcome_but_the_technician_can(client):
    cid = _awaiting(client)
    assert client.post(f"/cases/{cid}/approval", params={
        "user": "mgr1", "decision": "approve", "rationale": "sensor past calibration"}).status_code == 200
    assert client.post(f"/cases/{cid}/work-order", params={"user": "mgr1"}).status_code == 200
    r = client.post(f"/cases/{cid}/outcome", params={
        "user": "mgr1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure"})
    assert r.status_code == 403
    r = client.post(f"/cases/{cid}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure"})
    assert r.status_code == 200, r.text
    r = client.post(f"/cases/{cid}/feedback", params={"user": "tech1"},
                    json={"confirmed_cause": "sensor_hardware_failure", "notes": "RTD open circuit"})
    assert r.status_code == 200, r.text
    assert r.json()["proposal_status"] == "pending"
    pending = [p for p in LSTORE.list_pending_proposals() if p.get("case_id") == cid]
    assert pending and pending[0]["submitted_by"] == "tech1"


def test_admin_cannot_approve_a_case(client):
    cid = _awaiting(client)
    r = client.post(f"/cases/{cid}/approval", params={
        "user": "admin1", "decision": "approve", "rationale": "x"})
    assert r.status_code == 403


def test_admin_cannot_review_audit_integrity(client):
    r = client.post("/audit/review", params={"user": "admin1", "target": "ledger",
                                             "decision": "accept", "reason": "x"})
    assert r.status_code == 403


@pytest.mark.parametrize("atype,detail", [
    ("bms_setpoint_change", "raise the charger setpoint"),
    ("onsite_inspection", "Bypass the battery over-temperature interlock"),
    ("onsite_inspection", "tape over the buzzer while you work"),
])
def test_a_modified_action_still_passes_g1(client, atype, detail):
    cid = _awaiting(client)
    r = client.post(f"/cases/{cid}/approval", params={
        "user": "mgr1", "decision": "modify", "rationale": "x",
        "modified_action_type": atype, "modified_action_target": "battery_bank",
        "modified_action_detail": detail})
    assert r.status_code == 400 and "[G1]" in r.json()["detail"]
    assert client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["current_state"] == "AWAITING_APPROVAL"


def test_a_safe_modified_action_is_marked_as_the_aoms_own(client):
    from technical_services_pill import store

    cid = _awaiting(client)
    r = client.post(f"/cases/{cid}/approval", params={
        "user": "mgr1", "decision": "modify", "rationale": "check wiring first",
        "modified_action_type": "onsite_inspection", "modified_action_target": "sensor_wiring",
        "modified_action_detail": "Onsite re-seat/inspect wiring."})
    assert r.status_code == 200, r.text
    assert store.STORE.get(cid).recommendation.actions[0].kb_refs == []
