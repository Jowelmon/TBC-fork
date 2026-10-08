"""Governance integrity: feedback cannot poison the KB, the knowledge ledger
records every decision, labels are never reused, identity needs a PIN,
seeding is never attributed to real users, and capture works offline."""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import llm
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _case(client, asset="CRAH-DC1-01", sensor="SA-TEMP-01", fault="temperature_measurement_missing"):
    cid = client.post("/cases", params={
        "asset_id": asset, "sensor_id": sensor, "user": "tech1",
        "observation_type": fault, "reading_status": "absent",
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def _to_feedback_queued(client):
    cid = _case(client)
    client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "ok"})
    client.post(f"/cases/{cid}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{cid}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure"})
    return cid


# 1. Feedback poisoning --------------------------------------------------------
def test_rejected_feedback_leaves_no_proposal_behind(client):
    cid = _to_feedback_queued(client)
    assert client.post(f"/cases/{cid}/feedback", params={"user": "steward1"}).status_code == 200
    before = len(LSTORE.list_all_proposals())
    resp = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"},
                       json={"confirmed_cause": "aliens_did_it", "asset_type": "UPS"})
    assert resp.status_code == 409
    assert len(LSTORE.list_all_proposals()) == before


def test_feedback_rejects_unknown_and_cross_asset_causes(client):
    cid = _to_feedback_queued(client)
    before = len(LSTORE.list_all_proposals())
    for cause in ("aliens_did_it", "refrigerant_leak"):
        resp = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"},
                           json={"confirmed_cause": cause})
        assert resp.status_code == 400, cause
    assert len(LSTORE.list_all_proposals()) == before


def test_feedback_ignores_client_asset_type_and_signature(client):
    cid = _to_feedback_queued(client)
    fb = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"}, json={
        "confirmed_cause": "sensor_hardware_failure", "asset_type": "UPS",
        "fault_signature": "aliens", "submitted_by": "steward2"}).json()
    p = next(p for p in LSTORE.list_all_proposals() if p["feedback_id"] == fb["feedback_id"])
    assert p["asset_type"] == "CRAH"
    assert "aliens" not in p["fault_signature"]
    assert p["submitted_by"] == "steward1"


# 2. Governance ledger, keyed chain, immutable labels ---------------------------
def test_ledger_records_approval_rejection_and_rollback_with_reasons(client):
    cid = _to_feedback_queued(client)
    fb = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"}).json()
    pid = next(p["proposal_id"] for p in LSTORE.list_all_proposals() if p["feedback_id"] == fb["feedback_id"])
    before = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "reviewed against the transcript"})
    assert client.post(f"/kb/rollback/{before['current_version']}",
                       params={"user": "admin1", "pill": "CRAH"}).status_code == 400  # reason required
    assert client.post(f"/kb/rollback/{before['current_version']}",
                       params={"user": "admin1", "pill": "CRAH", "reason": "bad batch"}).status_code == 200

    ledger = client.get("/kb/ledger", params={"user": "auditor1"}).json()
    assert ledger["chain_valid"] is True
    actions = [(e["action"], e["actor"]) for e in ledger["entries"]]
    assert ("proposal_approved", "steward2") in actions
    assert ("rollback", "admin1") in actions
    assert any(e["action"] == "rollback" and e["reason"] == "bad batch" for e in ledger["entries"])


def test_version_label_is_never_reused_after_rollback(client):
    def approve_one():
        cid = _to_feedback_queued(client)
        fb = client.post(f"/cases/{cid}/feedback", params={"user": "steward1"}).json()
        pid = next(p["proposal_id"] for p in LSTORE.list_all_proposals() if p["feedback_id"] == fb["feedback_id"])
        client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "reviewed against the transcript"})
        return client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()["current_label"]

    start = client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()["current_version"]
    first = approve_one()
    client.post(f"/kb/rollback/{start}", params={"user": "admin1", "pill": "CRAH", "reason": "test"})
    second = approve_one()
    assert second != first
    labels = [v["label"] for v in client.get("/kb/versions", params={"user": "tech1", "pill": "CRAH"}).json()["versions"]]
    assert len(labels) == len(set(labels))


def test_ledger_tampering_is_detected():
    entry = LSTORE.ledger[-1] if LSTORE.ledger else None
    if entry is None:
        LSTORE._log(actor="steward1", action="proposal_rejected", reason="seed")
        entry = LSTORE.ledger[-1]
    original = entry["actor"]
    entry["actor"] = "someone-else"
    try:
        assert LSTORE.verify_ledger() is False
    finally:
        entry["actor"] = original
    assert LSTORE.verify_ledger() is True


def test_recomputing_the_chain_without_the_key_does_not_verify(client):
    from technical_services_pill.audit import GENESIS_HASH, canonical_json

    cid = _case(client)
    state = __import__("technical_services_pill.store", fromlist=["STORE"]).STORE.get(cid)
    saved = [(h.actor, h.prev_hash, h.hash) for h in state.history]
    prev = GENESIS_HASH
    for h in state.history:  # attacker rewrites actors and re-hashes with plain SHA-256
        h.actor = "TAMPERED"
        h.prev_hash = prev
        h.hash = hashlib.sha256(canonical_json({"prev_hash": prev, **h._payload_for_hash()}).encode()).hexdigest()
        prev = h.hash
    try:
        assert state.verify_audit_chain() is False
        # and a case that fails verification is frozen against changes
        assert client.post(f"/cases/{cid}/advance", params={"user": "tech1"}).status_code == 423
    finally:
        for h, (actor, ph, hs) in zip(state.history, saved):
            h.actor, h.prev_hash, h.hash = actor, ph, hs
    assert state.verify_audit_chain() is True


# 3. Identity and attribution -------------------------------------------------
def test_login_requires_the_users_pin(monkeypatch):
    monkeypatch.setenv("TBC_DEMO_INSECURE", "0")
    c = TestClient(app)
    assert c.post("/login", json={"user_id": "admin1"}).status_code == 401
    assert c.post("/login", json={"user_id": "admin1", "pin": "0000"}).status_code == 401
    assert c.post("/login", json={"user_id": "admin1", "pin": "9999"}).status_code == 200


def test_seeding_is_admin_only_and_never_attributed_to_real_users(client):
    assert client.post("/demo/seed", params={"user": "tech1"}).status_code == 403
    seeded = client.post("/demo/seed", params={"user": "admin1"}).json()["seeded"]
    for cid in seeded:
        actors = {h["actor"] for h in client.get(f"/cases/{cid}", params={"user": "tech1"}).json()["history"]}
        assert not actors & {"tech1", "mgr1", "steward1", "steward2", "admin1"}, actors


def test_unknown_asset_escalates_at_creation_with_a_true_record(client):
    resp = client.post("/cases", params={
        "asset_id": "NOPE-999", "sensor_id": "X", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent"}).json()
    assert resp["current_state"] == "ESCALATED"
    assert resp["evidence_count"] == 0
    snap = client.get(f"/cases/{resp['case_id']}", params={"user": "tech1"}).json()
    assert "NOT in the asset registry" in snap["history"][0]["reason"]
    assert snap["history"][0]["actor"] == "tech1"


# 4. The decision is informed and accountable ----------------------------------
def test_approval_needs_a_rationale(client):
    cid = _case(client)
    resp = client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve"})
    assert resp.status_code == 400


def test_hazard_must_be_acknowledged_before_approval(client):
    cid = _case(client, "CHILLER-DC1-01", "CH-COMP-PRESSURE", "chiller_compressor_trip")
    params = {"user": "mgr1", "decision": "approve", "rationale": "leak confirmed on site"}
    assert client.post(f"/cases/{cid}/approval", params=params).status_code == 400
    assert client.post(f"/cases/{cid}/approval", params={**params, "hazard_acknowledged": "true"}).status_code == 200
    reasons = [h["reason"] for h in client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["history"]]
    assert any("safety hazard acknowledged" in r for r in reasons)


def test_closing_an_escalation_can_harvest_the_resolution(client):
    cid = _case(client, "CRAH-DC1-02", "SA-TEMP-02")
    snap = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    assert snap["current_state"] == "ESCALATED"
    resp = client.post(f"/cases/{cid}/escalation/close", params={
        "user": "mgr1", "reason": "BMS vendor replaced CTL-02",
        "confirmed_cause": "communication_bus_controller_failure"}).json()
    p = next(p for p in LSTORE.list_all_proposals() if p["proposal_id"] == resp["knowledge_proposal_id"])
    assert p["kind"] == "escalation_resolution"
    assert p["resolution"] == "BMS vendor replaced CTL-02"
    assert client.post(f"/kb/proposals/{p['proposal_id']}/approve", params={"user": "steward1", "rationale": "reviewed against the transcript"}).status_code == 200


def test_escalation_audit_names_the_guardrail_that_fired(client):
    cid = _case(client, "CRAH-DC1-02", "SA-TEMP-02")
    reasons = [h["reason"] for h in client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["history"]]
    assert any("[G3]" in r for r in reasons)


# 5. Capture beyond the canned sample -----------------------------------------
PUMP = """Interviewer: What do you do when a chilled water pump starts vibrating?

Technician: First I put the analyser on it. If the axial vibration is high and the 2x peak dominates, that's misalignment at the coupling, so we laser align it. Never just tighten the base bolts and hope.

If it sounds like it's pumping gravel, that's cavitation. Check the strainer is not clogged and look at the suction pressure. Call the vendor if the impeller is already pitted.
"""


def test_mock_extractor_handles_a_pump_interview():
    causes = [h["likely_cause"] for h in llm._mock_extract(PUMP)["heuristics"]]
    assert sorted(causes) == ["cavitation", "shaft_misalignment"]


def test_advice_containing_not_is_kept_but_a_denial_is_dropped():
    cav = next(h for h in llm._mock_extract(PUMP)["heuristics"] if h["likely_cause"] == "cavitation")
    assert any("strainer is not clogged" in c for c in cav["checks"])
    ups = "Technician: It's not the charger in that case, check the float voltage is normal first."
    assert llm._mock_extract(ups)["heuristics"] == []


def test_manual_capture_works_with_the_ai_offline(client, monkeypatch):
    monkeypatch.setenv("TBC_LLM_PROVIDER", "adp")
    monkeypatch.delenv("ADP_APP_KEY", raising=False)
    body = {"expert_name": "J. Lim", "expert_role": "Pump fitter", "asset_type": "Pump",
            "transcript": PUMP, "expert_consent": True, "heuristics": [{
                "symptom_pattern": "pumping gravel", "likely_cause": "cavitation",
                "checks": ["Check the strainer"], "do_not": [], "escalate_when": [],
                "evidence_quote": "If it sounds like it's pumping gravel, that's cavitation."}]}
    resp = client.post("/capture/interview", params={"user": "steward1"}, json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider"] == "manual"


def test_ai_offline_is_not_logged_as_a_disagreement(client, monkeypatch):
    monkeypatch.setenv("TBC_LLM_PROVIDER", "adp")
    monkeypatch.delenv("ADP_APP_KEY", raising=False)
    cid = _case(client)
    reasons = [h["reason"] for h in client.get(f"/cases/{cid}", params={"user": "tech1"}).json()["history"]]
    assert any("AI second opinion unavailable" in r for r in reasons)
    assert not any("agrees_with_rules=False" in r for r in reasons)
