"""Knowledge about protective devices needs a steward's safety review and
never raises confidence; only stewards decide on knowledge; a broken chain
has a recorded way out (an auditor's review); the evidence check uses
abnormal readings only; and small operability fixes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import store
from technical_services_pill.app import _evidence_terms, app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


QUOTE = "If the sensor reads nothing and it is past its calibration date, check the alarm log, then replace it."
TRANSCRIPT = f"Interviewer: The CRAH supply sensor reads nothing.\n\nTechnician: {QUOTE}\n"


def _capture(client, quote=QUOTE, transcript=TRANSCRIPT, user="steward1"):
    return client.post("/capture/interview", params={"user": user}, json={
        "expert_name": "K. Wong", "expert_role": "Senior Technician", "asset_type": "CRAH",
        "transcript": transcript, "expert_consent": True,
        "heuristics": [{"symptom_pattern": quote, "likely_cause": "sensor_hardware_failure",
                        "evidence_quote": quote, "checks": [], "do_not": [], "escalate_when": []}],
    })


def _case(client, asset="CRAH-DC1-01"):
    cid = client.post("/cases", params={
        "asset_id": asset, "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


# 1. Safety review -------------------------------------------------------------
def test_an_alarm_bypass_cannot_be_submitted(client):
    bypass = "I tie the alarm contact out with a short bit of wire so it stops calling the night shift."
    r = _capture(client, quote=bypass, transcript=f"Technician: {bypass}\n")
    assert r.status_code == 422
    assert "safety device" in r.json()["detail"]


def test_knowledge_naming_a_protection_needs_review_and_never_raises_confidence(client):
    before = client.get(f"/cases/{_case(client)}", params={"user": "tech1"}).json()["confidence"]
    r = _capture(client)
    assert r.status_code == 200, r.text
    assert r.json()["heuristics"][0]["safety_review"]
    pid = r.json()["proposal_id"]

    unticked = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "checked"})
    assert unticked.status_code == 400 and "safety review" in unticked.json()["detail"]
    ok = client.post(f"/kb/proposals/{pid}/approve",
                     params={"user": "steward2", "rationale": "checked", "safety_reviewed": "true"})
    assert ok.status_code == 200, ok.text
    try:
        assert "safety review confirmed" in LSTORE.ledger[-1]["reason"]
        cid = _case(client)
        after = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()["confidence"]
        assert after == pytest.approx(before)  # guidance only: confidence did not move
        match = next(m for m in client.get(f"/cases/{cid}/expert-knowledge", params={"user": "tech1"}).json()["matches"]
                     if m["knowledge_id"].startswith(f"KB-EXP-{pid[5:]}"))
        assert match["guidance_only"] and match["safety_reviewed_by"] == "steward2"
        assert match["approved_by"] == "steward2"
    finally:
        client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "test cleanup"})


# 2. Only stewards decide on knowledge -----------------------------------------
def test_admin_cannot_approve_or_reject_knowledge(client):
    pid = _capture(client).json()["proposal_id"]
    for verb, extra in (("approve", {"rationale": "x", "safety_reviewed": "true"}), ("reject", {"reason": "x"})):
        r = client.post(f"/kb/proposals/{pid}/{verb}", params={"user": "admin1", **extra})
        assert r.status_code == 403 and "knowledge steward" in r.json()["detail"]
    client.post(f"/kb/proposals/{pid}/reject", params={"user": "steward2", "reason": "test cleanup"})


# 3. Integrity review ----------------------------------------------------------
def test_a_broken_ledger_withholds_knowledge_blocks_approval_until_an_auditor_reviews_it(client):
    cid = _case(client)
    entry = LSTORE.ledger[-1]
    entry["reason"] += " (edited outside the app)"
    try:
        ek = client.get(f"/cases/{cid}/expert-knowledge", params={"user": "tech1"}).json()
        assert ek["matches"] == []
        snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
        assert snap["ledger_valid"] is False and "ledger" in snap["knowledge_withdrawn"]
        assert client.post(f"/cases/{cid}/approval", params={
            "user": "mgr1", "decision": "approve", "rationale": "ok"}).status_code == 409

        assert client.post("/audit/review", params={
            "user": "tech1", "target": "ledger", "decision": "accept", "reason": "x"}).status_code == 403
        assert client.post("/audit/review", params={
            "user": "auditor1", "target": "ledger", "decision": "accept"}).status_code == 400
        r = client.post("/audit/review", params={
            "user": "auditor1", "target": "ledger", "decision": "accept",
            "reason": "compared with the nightly backup; the edit is a typo fix"})
        assert r.status_code == 200, r.text
        assert r.json()["ledger_valid"] is True
    finally:
        if not LSTORE.verify_ledger():  # leave the shared store usable if an assert failed
            LSTORE.review_broken_ledger(actor="test", reason="cleanup")
    assert LSTORE.ledger[-1]["action"] == "integrity_review"
    assert LSTORE.ledger[-1]["actor"] == "auditor1"
    assert client.post("/audit/review", params={
        "user": "auditor1", "target": "ledger", "decision": "accept", "reason": "again"}).status_code == 409


def test_a_frozen_case_can_be_accepted_or_quarantined_by_an_auditor(client):
    accepted, quarantined = _case(client), _case(client)
    for cid in (accepted, quarantined):
        store.STORE.get(cid).history[0].reason = "edited outside the app"
        assert client.post(f"/cases/{cid}/approval", params={
            "user": "mgr1", "decision": "approve", "rationale": "ok"}).status_code == 423

    r = client.post("/audit/review", params={"user": "auditor1", "target": f"case:{accepted}",
                                             "decision": "accept", "reason": "matches the paper log"})
    assert r.status_code == 200, r.text
    assert accepted not in r.json()["broken_cases"]
    assert client.post(f"/cases/{accepted}/approval", params={
        "user": "mgr1", "decision": "approve", "rationale": "ok"}).status_code == 200

    r = client.post("/audit/review", params={"user": "auditor1", "target": f"case:{quarantined}",
                                             "decision": "quarantine", "reason": "origin unknown"})
    assert r.status_code == 200, r.text
    snap = client.get(f"/cases/{quarantined}", params={"user": "tech1"}).json()
    assert snap["current_state"] == "CLOSED" and snap["audit_chain_valid"] is True
    assert "quarantined" in snap["history"][-1]["reason"]
    assert any(e["action"] == "integrity_review" and quarantined in e["reason"] for e in LSTORE.ledger)


def test_only_a_case_can_be_quarantined(client):
    assert client.post("/audit/review", params={"user": "auditor1", "target": "ledger",
                                                "decision": "quarantine", "reason": "x"}).status_code == 400


# 4. Evidence check uses abnormal readings only ---------------------------------
def test_evidence_terms_are_the_trigger_and_abnormal_readings_only(client):
    state = store.STORE.get(_case(client))
    terms = _evidence_terms(state)
    assert "calibration" in terms or "past" in terms  # the sensor's abnormal flags
    healthy = {"alive", "reachable", "controller", "protocol", "location", "commissioned"}
    assert not (terms & healthy)


# 5. Operability -----------------------------------------------------------------
def test_health_needs_no_session(monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    assert TestClient(app).get("/health").json() == {"ok": True}


def test_a_lower_case_asset_id_is_the_registered_asset(client):
    cid = client.post("/cases", params={
        "asset_id": "crah-dc1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing"}).json()["case_id"]
    snap = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
    assert snap["asset_id"] == "CRAH-DC1-01" and snap["current_state"] != "ESCALATED"


def test_audit_reasons_use_plain_words_not_constant_names(client):
    cid = _case(client)
    reasons = " ".join(h["reason"] for h in client.get(f"/cases/{cid}", params={"user": "tech1"}).json()["history"])
    assert "_CONFIDENCE" not in reasons
