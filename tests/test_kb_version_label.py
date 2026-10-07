"""KB version shown to users must come from the live store, not a constant."""
from fastapi.testclient import TestClient

from technical_services_pill.app import app
from technical_services_pill.learning import kb_version_label


def test_label_mapping():
    assert kb_version_label(0) == "1.3.0"
    assert kb_version_label(1) == "1.4.0"


def test_stats_exposes_label_matching_counter():
    client = TestClient(app)
    stats = client.get("/kb/stats", params={"user": "mgr1"}).json()
    for pill, version in stats["kb_versions"].items():
        assert stats["kb_version_labels"][pill] == f"{pill} v{kb_version_label(version)}"
