"""The sentinel: an independent supervisor that re-checks each case after
every write. It must stay silent in normal operation and stop a case the
moment its record breaks a rule, with an auditor deciding what happens next."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import sentinel, store
from technical_services_pill.app import app, seed_demo_cases
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _case(client, asset="CRAH-DC1-01", sensor="SA-TEMP-01", fault="temperature_measurement_missing"):
    cid = client.post("/cases", params={"asset_id": asset, "sensor_id": sensor, "user": "tech1",
                                        "observation_type": fault}).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def test_normal_operation_never_trips_the_sentinel(client):
    closed = _case(client)
    for step, params in [("approval", {"user": "mgr1", "decision": "approve", "rationale": "ok"}),
                         ("work-order", {"user": "mgr1"}),
                         ("outcome", {"user": "tech1", "result": "resolved",
                                      "root_cause_confirmed": "sensor_hardware_failure"}),
                         ("feedback", {"user": "steward1"})]:
        assert client.post(f"/cases/{closed}/{step}", params=params).status_code == 200, step
    escalated = _case(client, asset="CRAH-DC1-02", sensor="SA-TEMP-02")
    client.post(f"/cases/{escalated}/escalation/close", params={"user": "mgr1", "reason": "bus reset by vendor"})
    rejected = _case(client)
    client.post(f"/cases/{rejected}/approval", params={"user": "mgr1", "decision": "reject", "rationale": "no"})
    seeded = seed_demo_cases()
    for cid in [closed, escalated, rejected, *seeded]:
        state = store.STORE.get(cid)
        assert sentinel.inspect(state) == [], (cid, sentinel.inspect(state))
        assert not (state.sentinel_hold or {}).get("active")


def test_a_defective_tool_is_stopped_recorded_and_reported(client):
    assert client.post("/sentinel/drill", params={"user": "mgr1"}).status_code == 403
    r = client.post("/sentinel/drill", params={"user": "admin1"}).json()
    assert r["held"] and any("evidence the case does not have" in f for f in r["findings"])
    cid = r["case_id"]

    snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
    assert snap["sentinel_hold"]["active"] and snap["audit_chain_valid"]
    assert snap["history"][-1]["actor"] == "sentinel"            # reason recorded on the chain
    assert snap["sentinel_hold"]["seen"]["recommendation"]        # evidence preserved
    assert client.post(f"/cases/{cid}/approval", params={         # stopped
        "user": "mgr1", "decision": "approve", "rationale": "ok"}).status_code == 423
    held = client.get("/sentinel", params={"user": "tech1"}).json()["held"]
    assert cid in [h["case_id"] for h in held]                     # everyone is told

    assert client.post("/sentinel/review", params={
        "user": "mgr1", "case_id": cid, "decision": "release", "reason": "x"}).status_code == 403
    r = client.post("/sentinel/review", params={
        "user": "auditor1", "case_id": cid, "decision": "quarantine", "reason": "drill"})
    assert r.status_code == 200 and r.json()["current_state"] == "CLOSED"
    assert LSTORE.ledger[-1]["action"] == "integrity_review"
    assert store.STORE.get(cid).verify_audit_chain()


def test_a_released_case_is_not_stopped_again_for_the_same_finding(client):
    cid = client.post("/sentinel/drill", params={"user": "admin1"}).json()["case_id"]
    assert client.post("/sentinel/review", params={
        "user": "auditor1", "case_id": cid, "decision": "release",
        "reason": "the vendor portal reading exists on paper"}).status_code == 200
    assert sentinel.inspect(store.STORE.get(cid)) == []
    r = client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "reject", "rationale": "drill"})
    assert r.status_code == 200


@pytest.mark.parametrize("break_it, finding", [
    (lambda s: setattr(s, "work_order_id", "WO-FAKE"), "work order exists without"),
    (lambda s: setattr(s, "confidence", 1.7), "outside 0 to 1"),
    (lambda s: s.ai_hypothesis.update(hypothesis="bearing_wear"), "outside this asset's pill"),
])
def test_the_sentinel_names_what_is_wrong(client, break_it, finding):
    state = store.STORE.get(_case(client))
    break_it(state)
    assert any(finding in f for f in sentinel.inspect(state))


def test_the_review_reason_can_come_from_a_json_body_like_the_ui_sends(client):
    cid = client.post("/sentinel/drill", params={"user": "admin1"}).json()["case_id"]
    r = client.post("/sentinel/review", params={"user": "auditor1", "case_id": cid, "decision": "quarantine"},
                    json={"reason": "drill"})
    assert r.status_code == 200, r.text
