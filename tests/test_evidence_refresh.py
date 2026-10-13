"""Re-reading the evidence sources: the same reading taken again is the same
evidence (no duplicates, so seeded scores don't move), and it is refreshed
rather than kept, so a re-diagnosis doesn't age with the clock."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from technical_services_pill import store
from technical_services_pill.agent_state import evidence_key
from technical_services_pill.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _bus_fault_case(client) -> str:
    cid = client.post("/cases", params={
        "asset_id": "CRAH-DC1-02", "sensor_id": "SA-TEMP-02", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def test_a_reading_read_again_is_not_new_evidence(client):
    state = store.STORE.get(_bus_fault_case(client))
    keys = [evidence_key(e) for e in state.evidence]
    assert len(keys) == len(set(keys)), "the same reading was stored twice"
    assert state.current_state.value == "ESCALATED"
    assert round(state.confidence * 100, 1) == 36.6


def test_request_more_evidence_scores_todays_readings_not_the_first_ones(client, monkeypatch):
    from datetime import datetime as real_datetime

    from technical_services_pill import confidence, tools

    cid = _bus_fault_case(client)
    state = store.STORE.get(cid)
    before, count = state.confidence, len(state.evidence)

    class Later(real_datetime):  # the presenter runs 40 minutes late
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(minutes=40)

    monkeypatch.setattr(confidence, "datetime", Later)
    monkeypatch.setattr(tools, "datetime", Later)
    monkeypatch.setattr(tools, "_now", lambda: Later.now(confidence.timezone.utc))
    r = client.post(f"/cases/{cid}/escalation/evidence", params={"user": "mgr1", "reason": "re-check"})
    assert r.status_code == 200, r.text
    assert len(state.evidence) == count
    assert state.confidence == pytest.approx(before)
