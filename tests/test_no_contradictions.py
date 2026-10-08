"""Phase 4: no on-screen contradictions.

Covers both halves of the requirement:
  - rendered-HTML/static-asset checks that developer text and hardcoded
    escalation reasons/thresholds are gone from what actually ships to the
    browser;
  - API-contract invariants the frontend's "no contradictory badges" logic
    depends on (e.g. a case with no diagnosis never carries a nonzero
    confidence band; an ESCALATED case never carries a recommendation; the
    live KB version is the same number wherever it's read from).
"""
from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from frontend.serve import app
from technical_services_pill import decision_tree


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Static assets: developer text / hardcoded reasons must not ship
# --------------------------------------------------------------------------- #
def test_decision_tree_has_no_developer_jargon_in_action_detail_strings():
    """No raw AgentStateName, '-> HITL', or dev parentheticals in copy an
    AOM reads on the Recommended Action card.

    Scans the module SOURCE rather than calling its internal branch
    functions (whose signatures vary and aren't part of the public API) --
    simpler and doesn't risk exercising unrelated code paths.
    """
    src = inspect.getsource(decision_tree)
    for word in ("HITL", "(likely ESCALATED)", "ESCALATE (safety)"):
        assert word not in src, f"developer jargon {word!r} found in decision_tree.py"


def test_served_js_has_no_hardcoded_escalation_threshold_text(client: TestClient):
    resp = client.get("/static/js/screens.js")
    assert resp.status_code == 200
    src = resp.text
    assert "escalation threshold (0.35)" not in src
    assert "(G4)" not in src
    assert "Escalated - No Recommendation" not in src


# --------------------------------------------------------------------------- #
# API-contract invariants the UI's contradiction-avoidance logic relies on
# --------------------------------------------------------------------------- #
def test_undiagnosed_case_has_no_diagnosis_and_zero_confidence(client: TestClient):
    """The 'Not yet diagnosed' branch only fires correctly if a fresh case
    really has diagnosis=None (not just confidence=0 that looks diagnosed)."""
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["diagnosis"] is None
    assert snap["confidence"] == 0.0
    assert snap["confidence_breakdown"] is None


def test_escalated_case_never_carries_an_actionable_recommendation(client: TestClient):
    """A row can never show 'Escalated' and 'Recommendable' together: an
    escalated case may carry a bookkeeping Recommendation (G3's own
    cross-domain check needs kb_refs/evidence_refs to evaluate against),
    but it must never have actual actions to render as a recommendation."""
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-02", "sensor_id": "SA-TEMP-02", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["current_state"] == "ESCALATED"
    if snap["recommendation"] is not None:
        assert snap["recommendation"]["actions"] == [], (
            "an escalated case's recommendation (if any) must carry no actions"
        )
    assert snap["guardrail_result"] is not None
    assert snap["guardrail_result"]["reasons"], "an escalated case must carry a real reason to show"


def test_kb_version_label_matches_across_endpoints(client: TestClient):
    """The nav footer (/kb/stats) and a just-diagnosed case's confidence
    breakdown must report the identical live KB version -- never two
    different numbers for the same moment."""
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()

    stats = client.get("/kb/stats", params={"user": "tech1"}).json()
    assert snap["confidence_breakdown"]["kb_version_label"] == stats["kb_version_labels"]["CRAH"]
