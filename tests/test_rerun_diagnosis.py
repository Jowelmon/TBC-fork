"""Re-run diagnosis on similar open cases (Governance).

Covers the two new read endpoints behind that button:
  - GET /cases/similar       -- open cases sharing a cause (not CLOSED)
  - GET /cases/{id}/confidence-preview -- non-destructive before/after

Also a regression test for a routing bug this phase introduced and fixed:
``/cases/similar`` was shadowed by the earlier ``/cases/{case_id}`` route
(literal paths must be registered before a param route of the same shape).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_and_advance(client: TestClient) -> dict:
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01",
        "user": "tech1", "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["case_id"]
    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    return client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()


def test_cases_similar_route_is_not_shadowed_by_case_id_route(client: TestClient):
    """Regression: /cases/similar must not 404 as case_id='similar'."""
    resp = client.get("/cases/similar", params={"user": "tech1", "cause": "sensor_hardware_failure"})
    assert resp.status_code == 200, resp.text
    assert "matches" in resp.json()


def test_similar_lists_matching_open_cases_only(client: TestClient):
    open_case = _create_and_advance(client)
    assert open_case["diagnosis"]["top_cause_id"] == "sensor_hardware_failure"
    assert open_case["current_state"] != "CLOSED"

    resp = client.get("/cases/similar", params={
        "user": "tech1", "cause": "sensor_hardware_failure", "asset_type": "CRAH",
    })
    assert resp.status_code == 200, resp.text
    ids = [m["case_id"] for m in resp.json()["matches"]]
    assert open_case["case_id"] in ids

    # A cause nothing is diagnosed with returns no matches.
    resp = client.get("/cases/similar", params={"user": "tech1", "cause": "impeller_imbalance"})
    assert resp.json()["matches"] == []


def test_confidence_preview_is_non_destructive(client: TestClient):
    case = _create_and_advance(client)
    case_id = case["case_id"]

    resp = client.get(f"/cases/{case_id}/confidence-preview", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["before"] == case["confidence"]
    assert "after" in body and "breakdown" in body

    # The case itself must be completely unchanged by the preview.
    after_snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert after_snap["confidence"] == case["confidence"]
    assert after_snap["current_state"] == case["current_state"]


def test_confidence_preview_requires_a_resolvable_diagnosis(client: TestClient):
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01",
        "user": "tech1", "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]  # not yet advanced -> no diagnosis
    resp = client.get(f"/cases/{case_id}/confidence-preview", params={"user": "tech1"})
    assert resp.status_code == 409


def test_preview_shows_only_the_knowledges_effect_not_evidence_ageing(client: TestClient):
    """Re-running right after an approval must not show a drop caused by the
    evidence getting older since the case was scored."""
    from datetime import timedelta

    from technical_services_pill import store

    case = _create_and_advance(client)
    state = store.STORE.get(case["case_id"])
    saved = [ev.retrieved_at for ev in state.evidence]
    for ev in state.evidence:
        ev.retrieved_at = ev.retrieved_at - timedelta(hours=6)
    try:
        body = client.get(f"/cases/{case['case_id']}/confidence-preview",
                          params={"user": "tech1"}).json()
    finally:
        for ev, at in zip(state.evidence, saved):
            ev.retrieved_at = at
    assert body["kb_match_after"] == body["kb_match_before"]
    assert body["after"] == pytest.approx(body["before"])
    # The ageing is still reported, on its own.
    assert body["evidence_age_effect"] < 0


def test_a_sensor_not_on_the_asset_is_refused(client: TestClient):
    """BOGUS-99 must not borrow SA-TEMP-01's readings as its evidence."""
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "BOGUS-99", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent"})
    assert resp.status_code == 400
    assert "SA-TEMP-01" in resp.json()["detail"]


def test_evidence_comes_from_the_sensor_the_case_names(client: TestClient):
    from technical_services_pill import store

    cid = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "RA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent"}).json()["case_id"]
    ids = {str(ev.payload.get("sensor_id")) for ev in store.STORE.get(cid).evidence
           if isinstance(ev.payload, dict) and ev.payload.get("sensor_id")}
    assert ids and "SA-TEMP-01" not in ids


@pytest.mark.parametrize("reviewer", ["auditor1", "steward1"])
def test_reviewers_cannot_open_or_drive_a_case(client: TestClient, reviewer):
    params = {"asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01",
              "observation_type": "temperature_measurement_missing", "reading_status": "absent"}
    assert client.post("/cases", params={**params, "user": reviewer}).status_code == 403
    cid = client.post("/cases", params={**params, "user": "tech1"}).json()["case_id"]
    assert client.post(f"/cases/{cid}/advance", params={"user": reviewer}).status_code == 403
    assert client.post(f"/cases/{cid}/advance", params={"user": "tech1"}).status_code == 200
