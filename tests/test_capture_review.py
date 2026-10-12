"""Harvester review flow: draft, human review, re-grounded submit, correct filing."""
import pytest
from fastapi.testclient import TestClient

from technical_services_pill import capture
from technical_services_pill.app import app
from technical_services_pill.decision_tree import KNOWN_CAUSE_IDS
from technical_services_pill.learning import STORE as LSTORE


@pytest.fixture()
def client():
    return TestClient(app)


def _body(**extra):
    return {"expert_name": "R. Tan", "expert_role": "Senior M&E Technician",
            "asset_type": "CRAH", "transcript": capture.SAMPLE_INTERVIEW, "expert_consent": True, **extra}


def _draft(client):
    r = client.post("/capture/draft", params={"user": "steward1"},
                    json={"asset_type": "CRAH", "transcript": capture.SAMPLE_INTERVIEW})
    assert r.status_code == 200, r.text
    return r.json()


def test_draft_queues_nothing(client):
    pending = LSTORE.stats()["pending_proposals"]
    d = _draft(client)
    assert d["status"] == "draft" and d["heuristics"]
    assert LSTORE.stats()["pending_proposals"] == pending


def test_reviewed_subset_is_what_gets_queued(client):
    d = _draft(client)
    keep = d["heuristics"][:1]
    r = client.post("/capture/interview", params={"user": "steward1"},
                    json=_body(heuristics=keep, draft_id=d["draft_id"]))
    assert r.status_code == 200, r.text
    assert [h["evidence_quote"] for h in r.json()["heuristics"]] == [keep[0]["evidence_quote"]]


def test_reviewer_cannot_add_words_the_expert_did_not_say(client):
    d = _draft(client)
    forged = {**d["heuristics"][0], "evidence_quote": "Just replace every sensor on sight."}
    r = client.post("/capture/interview", params={"user": "steward1"},
                    json=_body(heuristics=[forged]))
    assert r.status_code == 422
    assert "ungrounded" in r.json()["detail"]


def test_reviewer_can_correct_a_cause(client):
    d = _draft(client)
    h = {**d["heuristics"][0], "likely_cause": "low_refrigerant_charge"}
    r = client.post("/capture/interview", params={"user": "steward1"},
                    json=_body(heuristics=[h]))
    assert r.status_code == 200, r.text
    out = r.json()["heuristics"][0]
    assert out["likely_cause"] == "low_refrigerant_charge"
    assert out["cause_label"] == "Low refrigerant charge"


def test_chiller_knowledge_from_a_crah_interview_is_filed_under_chiller(client):
    d = _draft(client)
    leak = next(h for h in d["heuristics"] if h["likely_cause"] == "refrigerant_leak")
    assert leak["asset_type"] == "Chiller"
    assert any("Chiller pill" in w for w in d["warnings"])


def test_alias_cause_from_model_still_matches_a_live_diagnosis(client):
    """Regression: the mock emits 'comm_bus_failure'; it must reach comm-bus cases."""
    r = client.post("/capture/interview", params={"user": "steward1"}, json=_body())
    assert r.status_code == 200, r.text
    ok = client.post(f"/kb/proposals/{r.json()['proposal_id']}/approve",
                     params={"user": "steward2", "rationale": "reviewed against the transcript",
                             "safety_reviewed": "true"})
    assert ok.status_code == 200, ok.text
    live = {h["likely_cause"] for h in LSTORE.expert_heuristics}
    assert "communication_bus_controller_failure" in live
    assert "comm_bus_failure" not in live


def test_causes_endpoint_labels_every_tree_cause(client):
    r = client.get("/causes", params={"user": "tech1"})
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["causes"]}
    assert set(KNOWN_CAUSE_IDS) - {"unresolvable"} <= ids
    assert all(c["label"] and "_" not in c["label"] for c in r.json()["causes"])
    crah = client.get("/causes", params={"user": "tech1", "asset_type": "Chiller"}).json()["causes"]
    assert crah and all(c["asset_type"] == "Chiller" for c in crah)
