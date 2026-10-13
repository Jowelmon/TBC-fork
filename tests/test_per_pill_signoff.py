"""Knowledge that touches several pills needs each pill's steward.

The sample interview is filed under CRAH, but its heuristics land on CRAH,
Chiller and Pump. steward1 owns CRAH and UPS; steward2 owns Chiller and
Pump. Approving as steward1 must not push steward2's pills live, and
revoking is limited to a steward who decides one of the proposal's pills.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import app as app_module
from technical_services_pill.app import app
from technical_services_pill.learning import STORE as LSTORE
from technical_services_pill.learning import proposal_pills

OK = {"rationale": "checked against the transcript", "safety_reviewed": "true"}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _capture_as(client, user):
    sample = client.get("/capture/sample", params={"user": user}).json()
    r = client.post("/capture/interview", params={"user": user}, json={
        **{k: sample[k] for k in ("expert_name", "expert_role", "asset_type", "transcript")},
        "expert_consent": True})
    assert r.status_code == 200, r.text
    return r.json()["proposal_id"]


def test_one_steward_cannot_push_another_stewards_pills_live(client):
    pid = _capture_as(client, "mgr1")
    pills = proposal_pills(LSTORE.find_proposal(pid))
    assert {"CRAH", "Chiller", "Pump"} <= set(pills)
    before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_versions"]

    r = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1", **OK})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awaiting_signoff"
    assert body["signed_for"] == ["CRAH"]
    assert {w["pill"] for w in body["awaiting_signoff"]} == {"Chiller", "Pump"}
    # Nothing is live until every pill has signed off.
    assert LSTORE.find_proposal(pid)["status"] == "pending"
    assert client.get("/kb/stats", params={"user": "tech1"}).json()["kb_versions"] == before

    # steward1 has nothing left to sign.
    again = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1", **OK})
    assert again.status_code == 403

    r = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", **OK})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    after = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_versions"]
    for pill in pills:
        assert after[pill] > before[pill]
    assert LSTORE.verify_ledger()
    actions = [e["action"] for e in LSTORE.ledger if e["proposal_id"] == pid]
    assert "proposal_signed_off" in actions and "proposal_approved" in actions
    client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "test cleanup"})


def test_queue_shows_who_still_has_to_sign(client):
    pid = _capture_as(client, "mgr1")
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1", **OK})
    queue = client.get("/kb/queue", params={"user": "steward2"}).json()["queue"]
    row = next(p for p in queue if p["proposal_id"] == pid)
    assert row["signoffs"]["CRAH"]["by"] == "steward1"
    assert {w["owner"] for w in row["awaiting_signoff"]} == {"steward2"}
    client.post(f"/kb/proposals/{pid}/reject", params={"user": "steward2", "reason": "test cleanup"})


def test_revoke_needs_a_steward_who_decides_one_of_its_pills(client, monkeypatch):
    pid = _capture_as(client, "steward1")
    assert client.post(f"/kb/proposals/{pid}/approve",
                       params={"user": "steward2", **OK}).json()["status"] == "approved"
    # Hand every pill to steward2: steward1 now decides none of them.
    monkeypatch.setattr(app_module, "PILL_OWNERS",
                        {p: "steward2" for p in ("CRAH", "Chiller", "UPS", "Pump")})
    r = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward1", "reason": "mine now"})
    assert r.status_code == 403
    assert client.post(f"/kb/proposals/{pid}/revoke", params={"user": "tech1", "reason": "x"}).status_code == 403
    r = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "test cleanup"})
    assert r.status_code == 200, r.text


def test_queue_names_a_stand_in_not_the_owner_who_proposed_it(client):
    pid = _capture_as(client, "steward1")
    row = next(p for p in client.get("/kb/queue", params={"user": "steward2"}).json()["queue"]
               if p["proposal_id"] == pid)
    crah = next(w for w in row["awaiting_signoff"] if w["pill"] == "CRAH")
    assert crah["owner"] is None and crah["stand_in"] is True
    client.post(f"/kb/proposals/{pid}/reject", params={"user": "steward2", "reason": "test cleanup"})


def test_a_steward_cannot_revoke_pills_another_steward_signed(client):
    pid = _capture_as(client, "mgr1")
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1", **OK})
    assert client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2", **OK}).json()["status"] == "approved"
    for steward in ("steward1", "steward2"):
        r = client.post(f"/kb/proposals/{pid}/revoke", params={"user": steward, "reason": "x"})
        assert r.status_code == 403, r.text
    assert client.post(f"/kb/proposals/{pid}/revoke",
                       params={"user": "admin1", "reason": "test cleanup"}).status_code == 200


def test_each_steward_withdraws_their_own_part_of_a_mixed_proposal(client):
    """Judge 6: on a proposal filed under several pills, no steward could
    withdraw a bad line (only admin). Each steward now withdraws the part
    they decide; the proposal is revoked once every part is withdrawn."""
    pid = _capture_as(client, "mgr1")
    for user in ("steward1", "steward2"):
        assert client.post(f"/kb/proposals/{pid}/approve", params={"user": user, **OK}).status_code == 200
    pills = set(proposal_pills(LSTORE.find_proposal(pid)))
    crah_before = [h for h in LSTORE.expert_heuristics if h.get("proposal_id") == pid and h["asset_type"] == "CRAH"]
    assert crah_before

    whole = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward1", "reason": "bad line"})
    assert whole.status_code == 403 and "withdraw your part: CRAH" in whole.json()["detail"]
    not_mine = client.post(f"/kb/proposals/{pid}/revoke",
                           params={"user": "steward1", "reason": "bad line", "pills": "Chiller"})
    assert not_mine.status_code == 403

    r = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward1", "reason": "bad line", "pills": "CRAH"})
    assert r.status_code == 200, r.text
    p = LSTORE.find_proposal(pid)
    assert p["status"] == "approved" and p["revoked_pills"] == ["CRAH"]
    left = {h["asset_type"] for h in LSTORE.expert_heuristics if h.get("proposal_id") == pid}
    assert left == pills - {"CRAH"}
    assert LSTORE.verify_ledger() and "CRAH part only" in LSTORE.ledger[-1]["reason"]
    again = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward1", "reason": "x", "pills": "CRAH"})
    assert again.status_code == 409  # already withdrawn

    rest = ",".join(sorted(pills - {"CRAH"}))
    r = client.post(f"/kb/proposals/{pid}/revoke", params={"user": "steward2", "reason": "whole interview", "pills": rest})
    assert r.status_code == 200, r.text
    assert LSTORE.find_proposal(pid)["status"] == "revoked"
    assert not [h for h in LSTORE.expert_heuristics if h.get("proposal_id") == pid]
