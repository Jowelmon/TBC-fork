"""Phase 3: "Re-run diagnosis on similar open cases" (Governance).

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
