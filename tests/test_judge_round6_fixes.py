"""Fixes for docs/JUDGE_REPORT_2026-10-07_round6.md (70/100)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import capture, persistence
from technical_services_pill.app import app
from technical_services_pill.evidence_flags import abnormal_fields
from technical_services_pill.guardrails import flag_ai_disagreement
from technical_services_pill.learning import STORE as LSTORE
from technical_services_pill.models import GuardrailResult


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _case(client, asset, sensor, fault, reading="absent"):
    cid = client.post("/cases", params={
        "asset_id": asset, "sensor_id": sensor, "user": "tech1",
        "observation_type": fault, "reading_status": reading,
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()


def _approve_sample(client) -> str:
    sample = client.get("/capture/sample", params={"user": "steward1"}).json()
    pid = client.post("/capture/interview", params={"user": "steward1"}, json={
        **{k: sample[k] for k in ("expert_name", "expert_role", "asset_type", "transcript")},
        "expert_consent": True}).json()["proposal_id"]
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", "rationale": "reviewed against the transcript"}).status_code == 200
    return pid


# 1. Re-score that escalates leaves no actionable recommendation ------------------
def test_rescore_that_escalates_drops_the_recommendation(client):
    for p in LSTORE.list_all_proposals():  # start from "pump knowledge not captured"
        if p["status"] == "approved" and any(
                h.get("likely_cause") == "shaft_misalignment" for h in p.get("heuristics") or []):
            client.post(f"/kb/proposals/{p['proposal_id']}/revoke", params={"user": "admin1", "reason": "baseline"})
    pid = _approve_sample(client)
    snap = _case(client, "PUMP-DC1-01", "PUMP-DC1-01-VIB", "pump_vibration_high", "invalid")
    assert snap["current_state"] == "AWAITING_APPROVAL"
    client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "re-check"})
    cid = snap["case_id"]
    assert client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["knowledge_withdrawn"]
    assert client.post(f"/cases/{cid}/rescore", params={"user": "mgr1"}).json()["current_state"] == "ESCALATED"
    after = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()
    assert after["recommendation"] is None
    assert after["audit_chain_valid"] is True


# 2. Abnormal highlights follow the decision trees' thresholds ----------------------
@pytest.mark.parametrize("payload,flagged,not_flagged", [
    ({"charge_pct": 95}, [], ["charge_pct"]),
    ({"charge_pct": 42, "leak_detected": True}, ["charge_pct", "leak_detected"], []),
    ({"soh_pct": 58, "age_months": 40}, ["soh_pct"], ["age_months"]),
    ({"approach_temp": 4.2}, ["approach_temp"], []),
    ({"approach_temp": 1.5}, [], ["approach_temp"]),
    ({"temp_c": 62.0}, [], ["temp_c"]),
    ({"balance_ok": False, "charger_ok": True}, ["balance_ok"], ["charger_ok"]),
])
def test_abnormal_fields_match_the_trees(payload, flagged, not_flagged):
    out = abnormal_fields(payload)
    assert all(f in out for f in flagged)
    assert not any(f in out for f in not_flagged)


def test_case_snapshot_carries_abnormal_flags(client):
    snap = _case(client, "CHILLER-DC1-02", "x", "chiller_compressor_trip")
    flags = {f for ev in snap["evidence"] for f in ev["abnormal"]}
    assert "approach_temp" in flags and "charge_pct" not in flags


# 3. "No opinion" is not a disagreement --------------------------------------------
def test_no_ai_opinion_does_not_raise_g9():
    gr = flag_ai_disagreement(GuardrailResult(), rule_cause="battery_eol",
                              ai_hypothesis={"status": "ok", "hypothesis": None, "agrees_with_rules": False})
    assert "G9" not in gr.rule_ids


# 4. Cause priors cannot be edited on their own -------------------------------------
def test_cause_priors_are_verified_and_rebuilt_from_validated_cases(tmp_path):
    assert LSTORE.verify_ledger()
    saved = {k: dict(v) for k, v in LSTORE._cause_stats.items()}
    LSTORE._cause_stats["battery_eol"] = {"confirmed": 1, "total": 40}
    try:
        assert LSTORE.verify_ledger() is False
        db = tmp_path / "s.sqlite"
        persistence.save_state(db)
        persistence.load_state(db)  # priors are rebuilt, not trusted from disk
        assert LSTORE._cause_stats == saved
        assert LSTORE.verify_ledger()
    finally:
        LSTORE._cause_stats = saved


# 5. Capture: a quote that rules out its own cause is flagged ----------------------
def test_quote_that_denies_its_cause_is_flagged():
    items = [{"symptom_pattern": "x", "likely_cause": "sensor_hardware_failure",
              "evidence_quote": "If every tag on the bus has gone quiet at once, it's almost never the sensor."}]
    kept, warnings = capture._validate_items(capture.SAMPLE_INTERVIEW, items, "CRAH")
    assert kept[0]["check_cause"] is True and warnings


def test_registry_lists_assets_with_their_fault(client):
    assets = {a["asset_id"]: a for a in client.get("/assets", params={"user": "tech1"}).json()["assets"]}
    assert assets["PUMP-DC1-01"]["fault_type"] == "pump_vibration_high"
    assert assets["CRAH-DC1-01"]["default_sensor"] == "SA-TEMP-01"


def test_pill_registry_credits_each_pill_an_interview_files_under(client):
    _approve_sample(client)
    pump = next(p for p in client.get("/pills", params={"user": "tech1"}).json()["pills"] if p["asset_type"] == "Pump")
    assert pump["proposals_submitted"] >= 1
