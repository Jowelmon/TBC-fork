"""Fixes for docs/JUDGE_REPORT_2026-10-07_round4.md (62/100)."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from technical_services_pill import auth, llm, persistence, store
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _case(client, asset="CRAH-DC1-01", sensor="SA-TEMP-01", fault="temperature_measurement_missing"):
    cid = client.post("/cases", params={
        "asset_id": asset, "sensor_id": sensor, "user": "tech1", "observation_type": fault,
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def _approved_feedback(client, approver="steward2"):
    cid = _case(client)
    client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "ok"})
    client.post(f"/cases/{cid}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{cid}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure"})
    fb = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"}).json()
    pid = next(p["proposal_id"] for p in LSTORE.list_all_proposals() if p["feedback_id"] == fb["feedback_id"])
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": approver}).status_code == 200
    return pid


# 1. Audit integrity ----------------------------------------------------------
def test_truncating_a_case_history_is_detected(client):
    state = store.STORE.get(_case(client))
    assert state.verify_audit_chain()
    dropped = state.history.pop()
    try:
        assert state.verify_audit_chain() is False
    finally:
        state.history.append(dropped)
    assert state.verify_audit_chain()


def test_editing_an_unhashed_looking_field_is_detected(client):
    cid = _case(client)
    client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "ok"})
    state = store.STORE.get(cid)
    original = state.human_decision.decided_by
    state.human_decision.decided_by = "someone-else"
    try:
        assert state.verify_audit_chain() is False
    finally:
        state.human_decision.decided_by = original
    state.diagnosis.top_cause_id, saved = "bearing_wear", state.diagnosis.top_cause_id
    try:
        assert state.verify_audit_chain() is False
    finally:
        state.diagnosis.top_cause_id = saved
    assert state.verify_audit_chain()


def test_truncating_the_ledger_or_editing_knowledge_is_detected(client):
    _approved_feedback(client)
    assert LSTORE.verify_ledger()
    last = LSTORE.ledger.pop()
    try:
        assert LSTORE.verify_ledger() is False
    finally:
        LSTORE.ledger.append(last)
    vc = LSTORE.validated[-1]
    vc.confirmed_cause, saved = "aliens_did_it", vc.confirmed_cause
    try:
        assert LSTORE.verify_ledger() is False
    finally:
        vc.confirmed_cause = saved
    assert LSTORE.verify_ledger()


def test_snapshots_are_json_not_pickle(tmp_path, client):
    import sqlite3

    _case(client)
    db = tmp_path / "s.sqlite"
    persistence.save_state(db)
    blobs = sqlite3.connect(db).execute("SELECT blob FROM snapshots").fetchall()
    for (blob,) in blobs:
        assert isinstance(blob, str) and blob.lstrip()[:1] in "{["


# 2. Stale knowledge -----------------------------------------------------------
def test_rolled_back_knowledge_blocks_approval_until_rescored(client):
    start = client.get("/kb/versions", params={"user": "tech1"}).json()["current_version"]
    _approved_feedback(client)
    cid = _case(client)  # scored against the new version
    client.post(f"/kb/rollback/{start}", params={"user": "admin1", "reason": "bad batch"})
    snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    assert snap["knowledge_withdrawn"]
    resp = client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "ok"})
    assert resp.status_code == 409
    assert client.post(f"/cases/{cid}/rescore", params={"user": "mgr1"}).status_code == 200
    snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    if snap["current_state"] == "AWAITING_APPROVAL":
        assert not snap["knowledge_withdrawn"]
        assert client.post(f"/cases/{cid}/approval", params={
            "user": "mgr1", "decision": "approve", "rationale": "ok"}).status_code == 200


def test_one_proposal_can_be_revoked_without_rolling_back_others(client):
    keep = _approved_feedback(client)
    drop = _approved_feedback(client)
    resp = client.post(f"/kb/proposals/{drop}/revoke", params={"user": "steward2", "reason": "wrong cause"})
    assert resp.status_code == 200, resp.text
    statuses = {p["proposal_id"]: p["status"] for p in LSTORE.list_all_proposals()}
    assert statuses[drop] == "revoked" and statuses[keep] == "approved"
    assert not any(vc.id == f"KB-FB-{p['feedback_id']}" for p in LSTORE.list_all_proposals()
                   if p["proposal_id"] == drop for vc in LSTORE.validated)


def test_validated_by_is_the_approver_not_the_proposer(client):
    pid = _approved_feedback(client)
    p = next(p for p in LSTORE.list_all_proposals() if p["proposal_id"] == pid)
    vc = next(vc for vc in LSTORE.validated if vc.id == p["validated_case_id"])
    assert vc.validated_by == "steward2"


# 3. AI ---------------------------------------------------------------------
def test_second_opinion_can_disagree_and_cites_readable_evidence(client):
    cid = _case(client, "UPS-DC1-02", "UPS-DC1-02-BATT", "ups_battery_fault")
    snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    hyp = snap["ai_hypothesis"]
    assert snap["diagnosis"]["top_cause_id"] == "battery_eol"
    assert hyp["hypothesis"] == "thermal_runaway_risk" and hyp["agrees_with_rules"] is False
    assert hyp["supporting_evidence"] and not any("{" in e for e in hyp["supporting_evidence"])
    g9 = next(r for r in snap["guardrail_result"]["reasons"] if r.startswith("[G9]"))
    assert "Battery thermal runaway risk" in g9


def test_adp_errors_are_plain_language(monkeypatch):
    monkeypatch.setenv("ADP_APP_KEY", "bad")
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, text='data: {"Type":"error","Error":{"Code":4505004,"Message":"App key invalid"},"TraceId":"x"}\n'))
    with pytest.raises(llm.LLMError) as exc:
        llm._call_adp("s", "u", transport=transport)
    assert "rejected the app key" in str(exc.value)
    assert "TraceId" not in str(exc.value)
    assert llm.LAST_CALL["ok"] is False


# 4. Escalations explained, no contradictions -----------------------------------
def test_every_escalation_has_a_reason(client):
    for asset, fault in [("PUMP-DC1-01", "pump_vibration_high"), ("UPS-DC1-01", "ups_battery_fault")]:
        cid = _case(client, asset, f"{asset}-S", fault)
        snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
        if snap["current_state"] == "ESCALATED":
            assert snap["guardrail_result"]["must_escalate"] is True
            assert snap["guardrail_result"]["reasons"]


def test_fault_type_must_match_the_asset(client):
    resp = client.post("/cases", params={"asset_id": "PUMP-DC1-01", "sensor_id": "x", "user": "tech1",
                                         "observation_type": "ups_battery_fault"})
    assert resp.status_code == 400


# 5. Governance and identity ----------------------------------------------------
def test_owning_steward_is_enforced(client):
    cid = _case(client, "CRAH-DC1-02", "SA-TEMP-02")
    pid = client.post(f"/cases/{cid}/escalation/close", params={
        "user": "mgr1", "reason": "vendor fixed bus",
        "confirmed_cause": "communication_bus_controller_failure"}).json()["knowledge_proposal_id"]
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2"}).status_code == 403
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1"}).status_code == 200


def test_expert_knowledge_only_counts_when_seen_in_evidence(client):
    from technical_services_pill.learning import corroborating_terms

    assert corroborating_terms("If the axial vibration is high", {"axial", "vibration", "2x"})
    assert not corroborating_terms("If the bearing is grinding", {"axial", "vibration", "2x"})


def test_pin_lockout_and_unlock_cookie(monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    auth._failures.clear()
    c = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        assert c.post("/login", json={"user_id": "auditor1", "pin": "0000"}).status_code == 401
    assert c.post("/login", json={"user_id": "auditor1", "pin": "5555"}).status_code == 429
    auth._failures.clear()

    assert c.post("/login", json={"user_id": "tech1"}).status_code == 401  # never proven here
    assert c.post("/login", json={"user_id": "tech1", "pin": "1111"}).status_code == 200
    assert c.post("/login", json={"user_id": "mgr1", "pin": "2222"}).status_code == 200
    me = c.post("/login", json={"user_id": "tech1"})  # switching back needs no PIN
    assert me.status_code == 200 and me.json()["role"] == "technician"
    assert c.get("/me").json()["capabilities"] == me.json()["capabilities"]
