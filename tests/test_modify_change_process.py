"""An AOM's Modify picks another of the procedures this fault's decision
tree can recommend, unchanged. No free text reaches a work order, so no
wording (a "do not reinstate the trip", another language, hidden
characters) can turn a Modify into an instruction to defeat a protection,
and no honest wording is refused by a word list either. The modified
action cites no knowledge, and the sentinel re-checks it independently."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import store
from technical_services_pill.app import app
from technical_services_pill.decision_tree import action_templates


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


def _modify(client, cid, type_, target=None, detail=None):
    params = {"user": "mgr1", "decision": "modify", "rationale": "site knowledge",
              "modified_action_type": type_}
    if target is not None:
        params["modified_action_target"] = target
    if detail is not None:
        params["modified_action_detail"] = detail
    return client.post(f"/cases/{cid}/approval", params=params)


# Harmful wordings an independent judge got past the old text screen
# (reports 5 and 6), including prohibitions-as-instructions, Malay, Chinese,
# zero-width spaces and Cyrillic look-alikes.
HARMFUL = [
    'Do not reinstate the battery high-temperature trip until the vendor arrives',
    "Don't re-enable the battery temperature alarm until the new bank is in",
    'Never isolate the string before changing the jars',
    "Don't wait to isolate; replace the jars now",
    'Raise the charger float voltage set-pt to 440 V',
    'Change the float voltage to 440 V',
    'Adjust the charger float voltage up to 2.35 V per cell',
    'Increase the trip current to 630 A',
    'Raise the high temperature threshold to 60 C',
    'Change the alarm threshold to 60 C',
    'Recalibrate SA-TEMP-01 with a -8 C offset so it reads normal',
    'Remap SA-TEMP-01 to a fixed value of 22 C on the BMS',
    'Overide the high temp cut out',
    'By pass the interlock',
    'Put the HP cutout in manual',
    'Leave the ELR off until the vendor comes',
    'Cover the smoke head with a bag while you work',
    'Tell the BMS to ignore SA-TEMP-01',
    '旁路联锁并更换电池',
    'Pintas interlock dan tukar bateri',
    'Matikan penggera suhu bateri',
    'Swap the cells with the UPS still online',
    'Replace jars with the string un-isolated',
    'Replace jars, no need to isolate',
    'Replace cells live',
    'Take SA-TEMP-01 offline in the BMS',
    'Blank the VESDA pipe inlet',
    'Acknowledge and latch out the battery temperature warning',
    'Remove the thermal fuse and fit a solid link',
    'Run the compressor in hand with the low pressure switch linked',
    'Throttle the discharge valve fully closed and run the pump',
    'Replace jars hot',
    'byp\u200bass the inter\u200block',
    'bураss the interlock',
    'Stop the leak detection from alerting',
    'Put the CRAH into service mode so it ignores high temp',
    'Lower the low-pressure cut-in to 0.5 bar',
    'Unwire the temperature warning',
    'Swap the 400 A fuse for a 630 A one',
]
# Ordinary repairs the old screen refused.
BENIGN_TEXT = [
    'Replace SA-TEMP-01 and confirm the alarm clears on the BMS',
    'Inspect + replace starter/contactor.',
    'Replace the failed supply air temperature probe',
    'Replace the thermistor on CRAH-DC1-01',
    'Record the as-found settings before replacing the controller',
    'Check vibration while running and realign the coupling',
    'Isolate and lock out the pump, then replace the bearing',
    'Replace the battery bank with the string isolated and locked off',
    'Replace the blown fuse with one of the same rating',
    'Inspect the breaker and terminations for heat damage',
    'Clean the condenser coils with the chiller shut down',
    'Verify the chilled water setpoint reading on the BMS matches the controller',
    'Retorque the pump base bolts and re-grout',
    'Recalibrate SA-TEMP-01 against a reference thermometer',
    'Top up refrigerant after the leak repair and pressure test',
    'Replace the charger rectifier board',
]


@pytest.mark.parametrize("detail", HARMFUL + BENIGN_TEXT)
def test_free_text_never_reaches_a_work_order(client, detail):
    cid = _awaiting(client)
    r = _modify(client, cid, "sensor_inspection", "sensor", detail)
    assert r.status_code == 400 and "[G1]" in r.json()["detail"], r.text
    assert store.STORE.get(cid).current_state.value == "AWAITING_APPROVAL"


def test_another_faults_procedure_is_refused(client):
    r = _modify(client, _awaiting(client), "laser_realign")
    assert r.status_code == 400 and "this fault's decision tree" in r.json()["detail"]


@pytest.mark.parametrize("template", action_templates("temperature_measurement_missing"))
def test_every_procedure_of_the_fault_can_be_chosen_and_reaches_a_work_order(client, template):
    cid = _awaiting(client)
    r = _modify(client, cid, template["type"], template["target"], template["detail"])
    assert r.status_code == 200, r.text
    state = store.STORE.get(cid)
    a = state.recommendation.actions[0]
    assert (a.type, a.target, a.detail) == (template["type"], template["target"], template["detail"])
    assert state.recommendation.kb_refs == [] and a.kb_refs == []
    assert state.human_decision.original_actions  # the agent's actions, with their citations, kept
    assert "passed G1" not in state.history[-1].reason
    assert client.post(f"/cases/{cid}/work-order", params={"user": "mgr1"}).status_code == 200


def test_the_type_alone_picks_its_procedure(client):
    cid = _awaiting(client)
    assert _modify(client, cid, "config_remap").status_code == 200
    assert store.STORE.get(cid).recommendation.actions[0].detail == "Restore/re-map tag (draft work order)."


def test_the_templates_endpoint_lists_this_cases_procedures(client):
    cid = _awaiting(client)
    got = client.get(f"/cases/{cid}/action-templates", params={"user": "mgr1"}).json()["templates"]
    assert got == action_templates("temperature_measurement_missing")
    assert all(t["type"] != "laser_realign" for t in got)


def test_the_sentinel_rechecks_an_aom_chosen_action_on_its_own(client):
    """If free text reached the record some other way, the sentinel finds it
    independently of the approval endpoint."""
    from technical_services_pill import sentinel

    cid = _awaiting(client)
    assert _modify(client, cid, "onsite_inspection").status_code == 200
    state = store.STORE.get(cid)
    assert sentinel.inspect(state) == []
    good = state.recommendation.actions[0]
    for forged in (good.model_copy(update={"detail": "Do not reinstate the trip"}),
                   good.model_copy(update={"kb_refs": ["KB-UPS1"]})):
        state.recommendation.actions[0] = state.human_decision.modified_actions[0] = forged
        try:
            assert sentinel.inspect(state), forged
        finally:
            state.recommendation.actions[0] = state.human_decision.modified_actions[0] = good
    assert sentinel.inspect(state) == []
