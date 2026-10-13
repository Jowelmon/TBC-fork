"""The integrity review tells the auditor where to look."""
from __future__ import annotations

from fastapi.testclient import TestClient

from technical_services_pill import store
from technical_services_pill.app import app


def _case(client):
    cid = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01", "sensor_id": "SA-TEMP-01", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent"}).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    return cid


def test_an_edited_entry_is_named():
    client = TestClient(app)
    cid = _case(client)
    state = store.STORE.get(cid)
    original = state.history[1].reason
    state.history[1].reason = "forged"
    try:
        problem = client.get("/audit/status", params={"user": "auditor1"}).json()["case_problems"][cid]
        assert problem.startswith("entry #2") and "changed after it was signed" in problem
    finally:
        state.history[1].reason = original
    assert state.chain_problem() is None


def test_edited_case_data_is_told_apart_from_an_edited_entry():
    client = TestClient(app)
    cid = _case(client)
    state = store.STORE.get(cid)
    before = state.confidence
    state.confidence = 0.99
    try:
        assert "edited directly" in state.chain_problem()
    finally:
        state.confidence = before


def test_a_deleted_case_is_named():
    client = TestClient(app)
    cid = _case(client)
    state = store.STORE._cases.pop(cid)
    try:
        st = client.get("/audit/status", params={"user": "auditor1"}).json()
        assert st["registry_valid"] is False
        assert cid in st["missing_cases"]
    finally:
        store.STORE._cases[cid] = state
