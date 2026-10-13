"""An AOM's Modify is a hand-written work-order action with no reviewer
after it, so it is screened deny-by-default: the kind of work comes from
the agent's own catalogue, and any wording touching a protection, alarm,
setpoint or control setting, or live working, is refused. The modified
action cites no knowledge."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import store
from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _awaiting(client) -> str:
    cid = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    assert store.STORE.get(cid).current_state.value == "AWAITING_APPROVAL"
    return cid


def _modify(client, cid, type_, detail, target="CRAH-DC1-01"):
    return client.post(f"/cases/{cid}/approval", params={
        "user": "mgr1", "decision": "modify", "rationale": "site knowledge",
        "modified_action_type": type_, "modified_action_target": target,
        "modified_action_detail": detail})


@pytest.mark.parametrize("detail", [
    # Paraphrases a judge got through the keyword check (report 5).
    "raise the charger float voltage set point",
    "inhibit the battery temperature alarm on the BMS",
    "change the breaker trip setting",
    "replace jars without isolating the string",
    "acknowledge and suppress the battery temperature alarm",
    "put the high temperature cut out in override",
    "change the cells while the string is energised",
])
def test_protection_and_control_changes_are_refused(client, detail):
    cid = _awaiting(client)
    r = _modify(client, cid, "battery_replacement", detail)
    assert r.status_code == 400 and "[G1]" in r.json()["detail"], r.text
    assert store.STORE.get(cid).current_state.value == "AWAITING_APPROVAL"


def test_the_kind_of_work_must_come_from_the_agents_catalogue(client):
    r = _modify(client, _awaiting(client), "bms_setpoint_change", "tidy up")
    assert r.status_code == 400 and "not an action the agent can recommend" in r.json()["detail"]
    types = client.get("/actions/types", params={"user": "mgr1"}).json()["action_types"]
    assert "sensor_replacement" in types and "bms_setpoint_change" not in types


@pytest.mark.parametrize("type_,detail", [
    ("sensor_replacement", "Replace the supply-air RTD with the spare from stores"),
    ("sensor_inspection", "Check the sensor connector for corrosion before replacing anything"),
    ("onsite_inspection", "Inspect the filter bank and clean the coil; do not disable anything"),
])
def test_ordinary_modifications_go_through_and_cite_no_knowledge(client, type_, detail):
    cid = _awaiting(client)
    r = _modify(client, cid, type_, detail)
    assert r.status_code == 200, r.text
    state = store.STORE.get(cid)
    assert state.recommendation.kb_refs == []
    assert all(a.kb_refs == [] for a in state.recommendation.actions)
    assert state.human_decision.original_actions  # the agent's actions, with their citations, kept
    wo = client.post(f"/cases/{cid}/work-order", params={"user": "mgr1"})
    assert wo.status_code == 200, wo.text


def test_every_action_the_agent_recommends_is_in_the_catalogue():
    import glob
    import re

    from technical_services_pill.decision_tree import ACTION_TYPES

    used = set()
    for f in glob.glob("technical_services_pill/*.py"):
        used |= set(re.findall(r'_make_result\(\s*[^,]+,\s*"[^"]*",\s*"([a-z_]+)"', open(f).read()))
    assert used and used <= set(ACTION_TYPES)


def test_the_sentinel_rechecks_an_aom_written_action_on_its_own(client):
    """If a protection change reached the record some other way, the
    sentinel finds it independently of the approval endpoint."""
    from technical_services_pill import sentinel

    cid = _awaiting(client)
    assert _modify(client, cid, "sensor_replacement", "Replace the RTD").status_code == 200
    state = store.STORE.get(cid)
    assert sentinel.inspect(state) == []
    forged = state.recommendation.actions[0].model_copy(update={"detail": "and put the cut out in override"})
    state.recommendation.actions[0] = forged
    state.human_decision.modified_actions[0] = forged
    try:
        assert any("engineering change process" in f for f in sentinel.inspect(state))
        forged.kb_refs.append("KB-UPS1")
        assert any("cites knowledge it was not drawn from" in f for f in sentinel.inspect(state))
    finally:
        state.recommendation.actions[0] = state.human_decision.modified_actions[0] = \
            forged.model_copy(update={"detail": "Replace the RTD", "kb_refs": []})
