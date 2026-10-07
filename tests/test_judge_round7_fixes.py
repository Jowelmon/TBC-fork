"""Fixes for docs/JUDGE_REPORT_2026-10-07_round7.md (69/100)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import capture
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


QUOTE = "With a chiller tripping on low pressure, I check the refrigerant charge before anything else."


def _item(**over):
    return {"symptom_pattern": QUOTE, "likely_cause": "refrigerant_leak", "evidence_quote": QUOTE,
            "checks": [], "do_not": [], "escalate_when": [], **over}


def _body(**extra):
    return {"expert_name": "R. Tan", "expert_role": "Senior M&E Technician", "asset_type": "CRAH",
            "transcript": capture.SAMPLE_INTERVIEW, "expert_consent": True, **extra}


# 1. Every actionable line is grounded in the expert's own answer -----------------
def test_a_check_the_expert_never_said_is_dropped():
    kept, warnings = capture._validate_items(capture.SAMPLE_INTERVIEW, [_item(
        checks=["bypass the low-pressure interlock and restart the compressor"])], "Chiller")
    assert kept[0]["checks"] == [] and warnings


def test_a_line_borrowed_from_another_answer_is_dropped():
    kept, _ = capture._validate_items(capture.SAMPLE_INTERVIEW, [_item(
        checks=["I look at the calibration sticker."])], "Chiller")
    assert kept[0]["checks"] == []


def test_a_safety_bypass_is_dropped_even_if_said_but_a_prohibition_is_kept():
    transcript = ("Technician: With a chiller tripping on low pressure, I check the refrigerant charge "
                  "before anything else. Jumper the low pressure switch to get it running. "
                  "Never bypass the interlock on a leaking unit.\n")
    q = "With a chiller tripping on low pressure, I check the refrigerant charge before anything else."
    kept, warnings = capture._validate_items(transcript, [_item(
        evidence_quote=q, checks=["Jumper the low pressure switch to get it running."],
        do_not=["Never bypass the interlock on a leaking unit."])], "Chiller")
    assert kept[0]["checks"] == []
    assert kept[0]["do_not"] == ["Never bypass the interlock on a leaking unit."]
    assert any("safety device" in w for w in warnings)


def test_a_paraphrased_symptom_falls_back_to_the_experts_words():
    kept, _ = capture._validate_items(capture.SAMPLE_INTERVIEW, [_item(
        symptom_pattern="Ignore the interlock and run it")], "Chiller")
    assert kept[0]["symptom_pattern"] == QUOTE


# 2. Stewards decide with reasons ----------------------------------------------------
def test_approval_needs_a_rationale_and_rejection_a_reason(client):
    pid = client.post("/capture/interview", params={"user": "steward1"}, json=_body()).json()["proposal_id"]
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2"}).status_code == 400
    assert client.post(f"/kb/proposals/{pid}/reject", params={"user": "steward2", "reason": " "}).status_code == 400
    assert client.post(f"/kb/proposals/{pid}/approve", params={
        "user": "steward2", "rationale": "each line checked against the interview"}).status_code == 200
    entry = next(e for e in reversed(LSTORE.ledger) if e["proposal_id"] == pid)
    assert "each line checked against the interview" in entry["reason"]
    client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "test cleanup"})


def test_queue_names_the_owning_steward(client):
    client.post("/capture/interview", params={"user": "steward1"}, json=_body())
    queue = client.get("/kb/queue", params={"user": "steward2"}).json()["queue"]
    assert all("owner_steward" in p for p in queue)


# 3. Provenance comes from the server, consent is recorded ---------------------------
def test_client_cannot_claim_a_model_provider(client):
    r = client.post("/capture/interview", params={"user": "steward1"},
                    json=_body(heuristics=[_item()], provider="adp"))
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "manual"


def test_draft_id_carries_the_real_provider_and_marks_hand_entries(client):
    d = client.post("/capture/draft", params={"user": "steward1"},
                    json={"asset_type": "CRAH", "transcript": capture.SAMPLE_INTERVIEW}).json()
    added = _item(evidence_quote="A fouled condenser is the usual story there, especially after the dry season.",
                  likely_cause="condenser_fouling")
    r = client.post("/capture/interview", params={"user": "steward1"},
                    json=_body(heuristics=[d["heuristics"][0], added], draft_id=d["draft_id"])).json()
    assert r["provider"] == "mock"
    assert [h["source"] for h in r["heuristics"]] == ["model", "manual"]


def test_consent_is_required(client):
    r = client.post("/capture/interview", params={"user": "steward1"}, json={**_body(), "expert_consent": False})
    assert r.status_code == 400


# 4. The knowledge behind a decision is preserved -------------------------------------
def test_decision_keeps_the_expert_knowledge_it_was_made_with(client):
    sample = client.post("/capture/interview", params={"user": "steward1"}, json=_body()).json()["proposal_id"]
    client.post(f"/kb/proposals/{sample}/approve", params={"user": "steward2", "rationale": "checked"})
    cid = client.post("/cases", params={"user": "tech1", "asset_id": "CHILLER-DC1-01", "sensor_id": "x",
                                         "observation_type": "chiller_compressor_trip"}).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    client.post(f"/cases/{cid}/approval", params={"user": "mgr1", "decision": "approve",
                                                  "rationale": "leak confirmed", "hazard_acknowledged": "true"})
    client.post(f"/kb/proposals/{sample}/revoke", params={"user": "steward2", "reason": "test cleanup"})
    hd = client.get(f"/cases/{cid}", params={"user": "mgr1"}).json()["human_decision"]
    assert hd["expert_knowledge"] and hd["expert_knowledge"][0]["expert_name"] == "R. Tan"
