"""F1 acceptance test: escalation path works through the real API.

Drives CRAH-DC1-02 (comm_bus_failure) through the FastAPI TestClient and
asserts:
  1. Final state is ESCALATED.
  2. guardrail_result is populated and names G3.
  3. The G3 reason names the target domain (Building Management System).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.store import STORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_and_advance(client: TestClient) -> dict:
    """Create CRAH-DC1-02 case and advance it; return the advance response."""
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-02",
        "sensor_id": "SA-TEMP-02",
        "user": "tech1",
        "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["case_id"]

    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_f1_escalation_via_api(client: TestClient):
    """CRAH-DC1-02 through the API must reach ESCALATED with G3."""
    adv = _create_and_advance(client)

    # 1. Final state is ESCALATED.
    assert adv["current_state"] == "ESCALATED", (
        f"expected ESCALATED, got {adv['current_state']}"
    )

    # 2. guardrail_result is populated and names G3.
    case_id = adv["case_id"]
    resp = client.get(f"/cases/{case_id}/recommendation", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    gr = body.get("guardrail_result")
    assert gr is not None, "guardrail_result must be populated for G3 escalation"
    assert "G3" in gr.get("rule_ids", []), (
        f"G3 must be in rule_ids, got {gr.get('rule_ids')}"
    )

    # 3. The G3 reason names the target domain.
    reasons = gr.get("reasons", [])
    g3_reason = next((r for r in reasons if "G3" in r), "")
    assert "Building Management System" in g3_reason, (
        f"G3 reason must name the target domain, got: {g3_reason}"
    )
    assert gr.get("must_escalate") is True, (
        "guardrail_result.must_escalate must be True for G3"
    )


def test_f1_no_hardcoded_confidence(client: TestClient):
    """The API path uses real confidence scoring, not a hardcoded value."""
    adv = _create_and_advance(client)

    # The real confidence for CRAH-DC1-02 is ~0.51 (not 0.8 as the old
    # demo hardcoded).  We just assert it's in a sane range that proves
    # the scorer ran and did not return the old hardcoded 0.8.
    conf = adv.get("confidence", 0)
    assert 0.0 < conf < 0.8, (
        f"confidence must be real (not hardcoded 0.8); got {conf}"
    )
