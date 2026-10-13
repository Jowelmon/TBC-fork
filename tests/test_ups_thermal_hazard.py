"""A hot battery whose temperature is still rising is a hazard whatever the
diagnosed cause (G2b), and at 40 °C and rising the UPS tree diagnoses
thermal runaway risk first, which G2 escalates to a person."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.guardrails import hazard_signals
from technical_services_pill.models import EvidenceItem


def _ev(payload):
    return EvidenceItem(source="ups", type="thermal", payload=payload, tool="asset_telemetry",
                        retrieved_at=datetime.now(timezone.utc))


def test_hot_and_rising_is_a_hazard_hot_alone_is_not():
    assert hazard_signals([_ev({"battery_temp_c": 41.0, "temp_rising": True})])
    assert not hazard_signals([_ev({"battery_temp_c": 41.0, "temp_rising": False})])
    assert not hazard_signals([_ev({"battery_temp_c": 30.0, "temp_rising": True})])


def test_ups_dc1_02_is_diagnosed_as_thermal_runaway_and_escalated():
    client = TestClient(app)
    cid = client.post("/cases", params={
        "asset_id": "UPS-DC1-02", "sensor_id": "UPS-DC1-02-BATT", "user": "tech1",
        "observation_type": "ups_battery_fault", "reading_status": "invalid"}).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    assert snap["diagnosis"]["top_cause_id"] == "thermal_runaway_risk"
    assert snap["current_state"] == "ESCALATED"
    reasons = snap["guardrail_result"]["reasons"]
    assert any(r.startswith("[G2]") for r in reasons), reasons
    assert any(r.startswith("[G2b]") and "rising" in r for r in reasons), reasons
    # Nothing to approve: a person handles it, never a work order from the AI.
    r = client.post(f"/cases/{cid}/approval", params={
        "user": "mgr1", "decision": "approve", "rationale": "x", "hazard_acknowledged": "true"})
    assert r.status_code != 200
