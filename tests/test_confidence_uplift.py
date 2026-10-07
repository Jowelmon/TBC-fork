"""Phase 3: confidence the KB can move.

Approving a validated case's feedback raises kb_match for the next
identical-signature case, which raises its confidence by at least 0.05;
rolling the KB back restores that confidence exactly (same inputs, same
score -- the scorer is pure).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_and_advance(client: TestClient, asset_id: str = "CRAH-DC1-01") -> dict:
    resp = client.post("/cases", params={
        "asset_id": asset_id, "sensor_id": "SA-TEMP-01",
        "user": "tech1", "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["case_id"]
    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    return client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()


def _close_with_validated_feedback(client: TestClient, snap: dict) -> None:
    """Approve, work-order, resolve, and get the feedback proposal approved
    by a DIFFERENT steward so it's ingested into the KB."""
    case_id = snap["case_id"]
    resp = client.post(f"/cases/{case_id}/approval", params={
        "user": "mgr1", "decision": "approve", "rationale": "test approval",
    })
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved",
        "root_cause_confirmed": "sensor_hardware_failure",
    })
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/cases/{case_id}/feedback", params={"user": "steward1"})
    assert resp.status_code == 200, resp.text
    fb_id = resp.json()["feedback_id"]

    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    proposal_id = next(p["proposal_id"] for p in queue if p["feedback_id"] == fb_id)
    resp = client.post(f"/kb/proposals/{proposal_id}/approve", params={"user": "steward2"})
    assert resp.status_code == 200, resp.text


def test_approving_validated_case_raises_next_identical_case_confidence(client: TestClient):
    first = _create_and_advance(client)
    assert first["diagnosis"]["top_cause_id"] == "sensor_hardware_failure"
    confidence_before = first["confidence"]

    _close_with_validated_feedback(client, first)

    second = _create_and_advance(client)
    assert second["diagnosis"]["top_cause_id"] == "sensor_hardware_failure"
    confidence_after = second["confidence"]

    assert confidence_after >= confidence_before + 0.05, (
        f"expected at least +0.05, got {confidence_before:.3f} -> {confidence_after:.3f}"
    )
    # The breakdown stored on the case should explain the uplift via kb_match.
    assert second["confidence_breakdown"]["kb_match"] > first["confidence_breakdown"]["kb_match"]


def test_rollback_restores_confidence_exactly(client: TestClient):
    # Self-contained: compares against its OWN measured baseline, so it
    # doesn't assume a pristine KB (other tests in this session may have
    # already ingested cases with the same fault signature).
    baseline = _create_and_advance(client)
    confidence_before = baseline["confidence"]
    version_before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]

    _close_with_validated_feedback(client, baseline)
    version_after = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    assert version_after == version_before + 1, "approval must bump the KB version by exactly 1"

    resp = client.post(f"/kb/rollback/{version_before}", params={"user": "admin1"})
    assert resp.status_code == 200, resp.text

    restored = _create_and_advance(client)
    assert restored["confidence"] == pytest.approx(confidence_before, abs=1e-9), (
        "rollback must restore confidence exactly, not just approximately"
    )
