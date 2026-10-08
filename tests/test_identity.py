"""Phase 2: identity is a signed session cookie, not a spoofable ?user=.

Covers:
  1. POST /login sets a cookie; it alone is enough to act as that user.
  2. A valid session cookie always wins over a spoofed ?user= query param.
  3. Outcome.verified_by is the cookie user, even if ?user= names someone else.
  4. With no cookie and TBC_DEMO_INSECURE unset, ?user= is refused (401).
  5. TBC_DEMO_INSECURE=1 restores the ?user= fallback (test/demo convenience).
  6. A tampered cookie is treated as no session at all.
  7. /system/info reports demo_insecure accurately.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.auth import SESSION_COOKIE


@pytest.fixture()
def secure_client(monkeypatch) -> TestClient:
    """A client with TBC_DEMO_INSECURE off, overriding the suite default."""
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    return TestClient(app)


def _create_and_advance(client: TestClient) -> str:
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["case_id"]
    resp = client.post(f"/cases/{case_id}/advance")
    assert resp.status_code == 200, resp.text
    return case_id


# --------------------------------------------------------------------------- #
# 1 & 4. No session at all -> refused; /login sets a working cookie
# --------------------------------------------------------------------------- #
def test_no_session_is_refused(secure_client: TestClient):
    resp = secure_client.get("/cases")
    assert resp.status_code == 401


def test_login_sets_a_working_cookie(secure_client: TestClient):
    resp = secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"] == "tech1"
    assert resp.json()["role"] == "technician"
    assert "approve_reject_modify" not in resp.json()["capabilities"]
    assert SESSION_COOKIE in resp.cookies

    # No ?user= needed anymore: the cookie alone authenticates.
    resp = secure_client.get("/cases")
    assert resp.status_code == 200, resp.text


def test_unknown_user_id_is_rejected(secure_client: TestClient):
    resp = secure_client.post("/login", json={"user_id": "nobody"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# 2 & 3. Session cookie beats a spoofed ?user=, including on write paths
# --------------------------------------------------------------------------- #
def test_cookie_wins_over_spoofed_user_param(secure_client: TestClient):
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})

    # tech1's session cannot approve regardless of what ?user= claims.
    case_id = _create_and_advance(secure_client)
    resp = secure_client.post(
        f"/cases/{case_id}/approval",
        params={"user": "admin1", "decision": "approve", "rationale": "spoof attempt"},
    )
    assert resp.status_code == 403, (
        "a technician session must not be escalated by a spoofed ?user=admin1"
    )


def test_outcome_verified_by_is_the_cookie_user_not_the_spoofed_param(secure_client: TestClient):
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})
    case_id = _create_and_advance(secure_client)

    secure_client.post("/login", json={"user_id": "mgr1", "pin": "2222"})
    resp = secure_client.post(f"/cases/{case_id}/approval", params={
        "decision": "approve", "rationale": "ok",
    })
    assert resp.status_code == 200, resp.text
    secure_client.post(f"/cases/{case_id}/work-order")

    # Log back in as tech1, then try to attribute the outcome to admin1
    # via a spoofed ?user=. verified_by always comes from the resolved
    # session (post_outcome never takes it as a client param), so it must
    # be tech1 regardless of what ?user= claims.
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})
    resp = secure_client.post(f"/cases/{case_id}/outcome", params={
        "user": "admin1", "result": "resolved",
        "root_cause_confirmed": "sensor_hardware_failure",
    })
    assert resp.status_code == 200, resp.text

    snap = secure_client.get(f"/cases/{case_id}").json()
    assert snap["outcome"]["verified_by"] == "tech1"
    # And the audit trail actor is the session user, not the spoofed one.
    resp = secure_client.get("/audit/trace", params={"case_id": case_id})
    assert resp.status_code == 403, "tech1 lacks read_audit_trail -- confirms RBAC used the real session"


# --------------------------------------------------------------------------- #
# 5. TBC_DEMO_INSECURE=1 restores ?user= as a fallback with no cookie
# --------------------------------------------------------------------------- #
def test_demo_insecure_restores_user_param_fallback(secure_client: TestClient, monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "1")
    resp = secure_client.get("/cases", params={"user": "tech1"})
    assert resp.status_code == 200, resp.text


def test_demo_insecure_still_loses_to_a_real_cookie(secure_client: TestClient, monkeypatch):
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})
    monkeypatch.setenv("TBC_DEMO_INSECURE", "1")
    case_id = _create_and_advance(secure_client)
    resp = secure_client.post(f"/cases/{case_id}/approval", params={
        "user": "admin1", "decision": "approve", "rationale": "spoof attempt",
    })
    assert resp.status_code == 403, "a present session cookie must still win even in insecure mode"


# --------------------------------------------------------------------------- #
# 6. A tampered cookie is worthless
# --------------------------------------------------------------------------- #
def test_tampered_cookie_is_rejected(secure_client: TestClient):
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})
    secure_client.cookies.set(SESSION_COOKIE, "admin1.0" * 8)  # forged signature
    resp = secure_client.get("/cases")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# 7. /system/info reports the flag accurately
# --------------------------------------------------------------------------- #
def test_system_info_reports_demo_insecure_flag(secure_client: TestClient, monkeypatch):
    secure_client.post("/login", json={"user_id": "tech1", "pin": "1111"})

    resp = secure_client.get("/system/info")
    assert resp.json()["demo_insecure"] is False

    monkeypatch.setenv("TBC_DEMO_INSECURE", "1")
    resp = secure_client.get("/system/info")
    assert resp.json()["demo_insecure"] is True
