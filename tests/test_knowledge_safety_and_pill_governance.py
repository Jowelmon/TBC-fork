"""Expert knowledge is safety-screened, decisions on it follow one set of
rules, and each pill's knowledge is versioned on its own.

- Capture drops any line that tells someone to defeat a protective device;
  a prohibition ("never bypass the interlock") is kept.
- Display screens stored knowledge again and withholds what fails.
- Rejecting follows the same separation of duties as approving.
- Knowledge changes are frozen (423) while the ledger fails verification.
- Rolling one pill back leaves every other pill's knowledge alone.
- Logout revokes the unlock cookie too; a non-ASCII PIN is a failed login,
  not a server error.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import auth, capture
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE
from technical_services_pill.safety import defeats_safety, said_as_prohibition


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# 1. Safety screen ------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Just bypass the interlock and restart it.",
    "Don't wait for the vendor, just bypass the interlock.",
    "If it keeps tripping I bridge out the high-temp interlock.",
    "Leave the trip bypassed overnight.",
    "Keep the pressure switch jumpered until the vendor comes.",
    "Raise the trip setpoint by two degrees.",
    "The trip keeps going, so jumper it out.",
    "Silence the alarm and carry on.",
    "Use a link wire across the HP switch.",
    "We usually switched off the low-temp cut-out in summer.",
    "Never mind the alarm, override the interlock.",
])
def test_instructions_to_defeat_a_protection_are_caught(text):
    assert defeats_safety(text)


@pytest.mark.parametrize("text", [
    "Never bypass the interlock, call the vendor.",
    "If it trips twice, never bypass the interlock, call the vendor.",
    "Never bypass the trip or silence the alarm.",
    "I get the safety officer involved for any leak.",
    "Check the alignment with the laser kit before you touch anything else.",
    "Isolate and lock out the pump before opening the coupling guard.",
    "Don't go swapping sensors, you'll waste a whole shift.",
    "Check the refrigerant charge before anything else.",
])
def test_prohibitions_and_ordinary_advice_are_kept(text):
    assert not defeats_safety(text)


def test_a_never_line_trimmed_of_its_never_still_counts_as_a_prohibition():
    answer = "Never just tighten the base bolts and hope, the vibration comes straight back."
    assert said_as_prohibition("just tighten the base bolts and hope", answer)
    assert not said_as_prohibition("check the alignment", "Check the alignment first.")


TRANSCRIPT = (
    "Interviewer: The CRAH supply sensor reads nothing. What do you do?\n\n"
    "Technician: If the sensor reads nothing and it is past its calibration date, it is end of life. "
    "If the high-temp alarm keeps going, just bypass the interlock so the unit keeps running.\n"
)


def _item(quote: str, **extra) -> dict:
    return {"evidence_quote": quote, "likely_cause": "sensor_hardware_failure",
            "symptom_pattern": quote, **extra}


def test_capture_drops_an_unsafe_quote_and_an_unsafe_check():
    kept, warnings = capture._validate_items(TRANSCRIPT, [
        _item("just bypass the interlock so the unit keeps running"),
        _item("If the sensor reads nothing and it is past its calibration date, it is end of life",
              checks=["just bypass the interlock so the unit keeps running"]),
    ], "CRAH")
    assert len(kept) == 1
    assert kept[0]["checks"] == []
    assert any("defeat a safety device" in w for w in warnings)


def test_capture_flags_a_quote_that_does_not_name_its_cause():
    transcript = "Technician: Always log the work order number before you leave site.\n"
    kept, warnings = capture._validate_items(
        transcript, [_item("Always log the work order number before you leave site")], "CRAH")
    assert kept[0]["off_topic"] is True
    assert any("nothing in the expert's answer names" in w for w in warnings)


def test_stored_knowledge_is_screened_again_when_shown(client):
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    planted = {
        "id": "EK-PLANTED", "expert_name": "planted", "expert_role": "n/a",
        "asset_type": "CRAH", "likely_cause": "sensor_hardware_failure",
        "symptom_pattern": "sensor reads nothing",
        "evidence_quote": "just bypass the interlock so the unit keeps running",
        "checks": [], "do_not": [], "escalate_when": [], "kb_version": 0, "approved_by": "n/a",
    }
    LSTORE.expert_heuristics.append(planted)  # written outside the governance flow
    try:
        body = client.get(f"/cases/{case_id}/expert-knowledge", params={"user": "tech1"}).json()
    finally:
        LSTORE.expert_heuristics.remove(planted)
    assert all(m["knowledge_id"] != "EK-PLANTED" for m in body["matches"])
    assert [w["knowledge_id"] for w in body["withheld"]] == ["EK-PLANTED"]


# 2. One set of rules for decisions -------------------------------------------
def _queued_capture(submitted_by: str = "steward1") -> str:
    draft = capture.draft_from_transcript(capture.SAMPLE_INTERVIEW, "CRAH")
    p = LSTORE.record_expert_capture(
        draft=draft, submitted_by=submitted_by, expert_name="Senior technician",
        expert_role="M&E", asset_type="CRAH", expert_consent=True)
    return p["proposal_id"]


def test_proposer_cannot_reject_their_own_proposal(client):
    pid = _queued_capture("steward1")
    resp = client.post(f"/kb/proposals/{pid}/reject",
                       params={"user": "steward1", "reason": "changed my mind"})
    assert resp.status_code == 403
    assert client.post(f"/kb/proposals/{pid}/reject",
                       params={"user": "steward2", "reason": "not grounded"}).status_code == 200


def test_knowledge_changes_freeze_while_the_ledger_fails_verification(client):
    pid = _queued_capture("steward1")
    entry = LSTORE.ledger[-1]
    original = entry["actor"]
    entry["actor"] = "someone-else"
    try:
        assert not LSTORE.verify_ledger()
        for path, params in [
            (f"/kb/proposals/{pid}/approve", {"user": "steward2", "rationale": "checked"}),
            (f"/kb/proposals/{pid}/reject", {"user": "steward2", "reason": "not grounded"}),
            ("/kb/rollback/0", {"user": "admin1", "pill": "CRAH", "reason": "test"}),
        ]:
            assert client.post(path, params=params).status_code == 423, path
    finally:
        entry["actor"] = original
    assert LSTORE.verify_ledger()
    assert client.post(f"/kb/proposals/{pid}/reject",
                       params={"user": "steward2", "reason": "not grounded"}).status_code == 200


# 3. Per-pill knowledge --------------------------------------------------------
def test_rolling_back_one_pill_leaves_the_others_alone(client):
    pid = _queued_capture("steward1")
    before = {pill: LSTORE.version_of(pill) for pill in ("Chiller", "Pump")}
    LSTORE.approve_proposal(pid, decided_by="steward2", rationale="checked against the transcript")
    after = {pill: LSTORE.version_of(pill) for pill in ("Chiller", "Pump")}
    assert all(after[p] == before[p] + 1 for p in after)

    resp = client.post(f"/kb/rollback/{before['Pump']}",
                       params={"user": "admin1", "pill": "Pump", "reason": "bad pump advice"})
    assert resp.status_code == 200, resp.text
    assert LSTORE.version_of("Pump") == before["Pump"]
    assert LSTORE.version_of("Chiller") == after["Chiller"]
    live = {(h["asset_type"], h["kb_version"]) for h in LSTORE.expert_heuristics}
    assert ("Chiller", after["Chiller"]) in live
    assert ("Pump", after["Pump"]) not in live
    assert LSTORE.find_proposal(pid)["status"] == "approved"  # still live for Chiller and CRAH


def test_rollback_needs_a_known_pill(client):
    assert client.post("/kb/rollback/0", params={"user": "admin1", "pill": "Boiler",
                                                 "reason": "x"}).status_code in (400, 422)


# 4. Identity -------------------------------------------------------------------
def test_logout_revokes_the_unlock_cookie(monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    auth._failures.clear()
    c = TestClient(app)
    assert c.post("/login", json={"user_id": "tech1", "pin": "1111"}).status_code == 200
    unlock = c.cookies.get(auth.UNLOCK_COOKIE)
    assert unlock
    c.post("/logout")
    c.cookies.set(auth.UNLOCK_COOKIE, unlock)  # replay the old cookie
    assert c.post("/login", json={"user_id": "tech1"}).status_code == 401


def test_a_non_ascii_pin_is_a_failed_login_not_a_crash(monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    auth._failures.clear()
    c = TestClient(app)
    assert c.post("/login", json={"user_id": "tech1", "pin": "１１１１"}).status_code == 401
    auth._failures.clear()
