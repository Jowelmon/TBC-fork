"""F3 acceptance test: refrigerant leak forces approval + safety flag (G2b).

Drives CHILLER-DC1-01 (chiller_compressor_trip → refrigerant_leak) through
the FastAPI TestClient and asserts:
  1. Final state is AWAITING_APPROVAL (not ESCALATED — human can approve).
  2. guardrail_result names G2b.
  3. requires_approval is True.
  4. must_escalate is False (does NOT auto-escalate).
  5. The G2b reason mentions the safety / refrigerant-leak hazard.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_and_advance(client: TestClient) -> dict:
    """Create CHILLER-DC1-01 case and advance it; return the advance response."""
    resp = client.post("/cases", params={
        "asset_id": "CHILLER-DC1-01",
        "sensor_id": "CHILLER-DC1-01-s",
        "user": "tech1",
        "observation_type": "chiller_compressor_trip",
        "reading_status": "absent",
    })
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["case_id"]

    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_f3_refrigerant_leak_routes_to_awaiting_approval(client: TestClient):
    """CHILLER-DC1-01 through the API must reach AWAITING_APPROVAL, not ESCALATED."""
    adv = _create_and_advance(client)

    assert adv["current_state"] == "AWAITING_APPROVAL", (
        f"refrigerant_leak must force AWAITING_APPROVAL, "
        f"got {adv['current_state']}"
    )


def test_f3_guardrail_names_g2b(client: TestClient):
    """guardrail_result must contain G2b with the safety flag."""
    adv = _create_and_advance(client)
    case_id = adv["case_id"]

    resp = client.get(f"/cases/{case_id}/recommendation", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    gr = body.get("guardrail_result")
    assert gr is not None, "guardrail_result must be populated for G2b"

    assert "G2b" in gr.get("rule_ids", []), (
        f"G2b must be in rule_ids, got {gr.get('rule_ids')}"
    )
    assert gr.get("requires_approval") is True, (
        "G2b must set requires_approval=True"
    )
    assert gr.get("must_escalate") is False, (
        "G2b must NOT auto-escalate (must_escalate should be False)"
    )

    reasons = gr.get("reasons", [])
    g2b_reason = next((r for r in reasons if "G2b" in r), "")
    assert "refrigerant" in g2b_reason.lower(), (
        f"G2b reason must mention refrigerant leak, got: {g2b_reason}"
    )
    assert "safety" in g2b_reason.lower() or "approval" in g2b_reason.lower(), (
        f"G2b reason must mention safety/approval, got: {g2b_reason}"
    )
