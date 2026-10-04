"""Engine state survives a restart via the SQLite snapshot."""
from fastapi.testclient import TestClient

from technical_services_pill import learning, persistence, store
from technical_services_pill.app import app


def test_state_survives_restart(tmp_path):
    db = tmp_path / "tbc.sqlite"
    client = TestClient(app)
    cid = client.post("/cases", params={
        "user": "tech1", "asset_id": "CRAH-DC1-02", "sensor_id": "SA-TEMP-02",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    }).json()["case_id"]
    client.post(f"/cases/{cid}/advance", params={"user": "tech1"})
    before = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
    version_before = learning.STORE.get_kb_version_label()

    persistence.save_state(db)

    # Simulate a restart: wipe the in-memory singletons.
    store.STORE._cases.clear()
    learning.STORE.__init__()
    assert client.get(f"/cases/{cid}", params={"user": "tech1"}).status_code == 404

    summary = persistence.load_state(db)
    assert summary["restored"] is True
    assert summary["audit_chain_failures"] == []

    after = client.get(f"/cases/{cid}", params={"user": "tech1"}).json()
    assert after["current_state"] == before["current_state"]
    assert after["history"] == before["history"]
    assert after["audit_chain_valid"] is True
    assert learning.STORE.get_kb_version_label() == version_before


def test_missing_database_starts_from_seed(tmp_path):
    summary = persistence.load_state(tmp_path / "nope.sqlite")
    assert summary["restored"] is False
