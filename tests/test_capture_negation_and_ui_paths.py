"""Capture ignores causes the expert denies; the safety hazard (G2b) and
unknown-asset escalation (G5) are reachable from the UI."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import llm
from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_mock_extractor_does_not_draft_a_heuristic_for_a_denied_cause():
    transcript = (
        "Interviewer: Tell me about a recent sensor failure you diagnosed.\n\n"
        "Technician: We had a supply air thermistor that just went dead one "
        "morning. I checked it wasn't the bus, not the controller, every "
        "other tag on that bus was reporting fine. The wiring was not loose "
        "either, I checked the terminal and it was seated properly. Turned "
        "out the thermistor was past its calibration date and just hit end "
        "of life. I replaced it and logged the work.\n"
    )
    result = llm._mock_extract(transcript)
    causes = {h["likely_cause"] for h in result["heuristics"]}
    assert causes == {"sensor_hardware_failure"}, (
        f"denied causes must not be drafted as heuristics, got {causes}"
    )


def test_mock_extractor_still_drafts_the_sample_interviews_heuristics():
    from technical_services_pill.capture import SAMPLE_INTERVIEW
    result = llm._mock_extract(SAMPLE_INTERVIEW)
    causes = {h["likely_cause"] for h in result["heuristics"]}
    assert causes == {
        "refrigerant_leak", "condenser_fouling", "communication_bus_controller_failure",
        "sensor_hardware_failure", "shaft_misalignment",
    }


def test_g2b_hazard_is_named_in_the_guardrail_result_the_decision_screen_reads(client: TestClient):
    """The AOM Decision screen renders from guardrail_result -- confirm the
    hazard reason is actually present in the API payload it reads (the
    screen fix is a frontend change verified visually; this pins the data
    contract so the frontend has something to render)."""
    resp = client.post("/cases", params={
        "asset_id": "CHILLER-DC1-01", "sensor_id": "CHILLER-DC1-01-s", "user": "tech1",
        "observation_type": "chiller_compressor_trip", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["current_state"] == "AWAITING_APPROVAL"
    reasons = snap["guardrail_result"]["reasons"]
    assert any("G2b" in r for r in reasons)
    assert any("hazard" in r.lower() or "safety" in r.lower() for r in reasons)


def test_unknown_asset_still_escalates_via_g5_api(client: TestClient):
    """Backend contract unchanged (the fix is giving the UI a path to call
    this with an arbitrary asset id, not changing the guardrail itself)."""
    resp = client.post("/cases", params={
        "asset_id": "NOPE-999", "sensor_id": "X", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["current_state"] == "ESCALATED"
    assert "G5" in snap["guardrail_result"]["rule_ids"]
