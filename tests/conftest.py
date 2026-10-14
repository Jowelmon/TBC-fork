"""Keep the test suite off the demo databases.

Tests used to write cases and knowledge proposals into the same SQLite files
the demo server loads, so the UI opened with stale cases and duplicate
pending proposals. Point persistence at a throwaway directory before any
application module is imported.
"""
import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="tbc-tests-")
os.environ.setdefault("TBC_DB_PATH", os.path.join(_TMP, "tbc.sqlite"))
os.environ.setdefault("TBC_AUDIT_KEY_FILE", os.path.join(_TMP, "audit.key"))

# Most of this suite predates the signed-session login flow (auth.py) and
# drives the API with plain ?user= params as shorthand for "acting as this
# role" — a legitimate use of the TBC_DEMO_INSECURE escape hatch, not a
# gap in it. Tests that exercise the login/cookie mechanism itself
# (tests/test_identity.py) override this per-test.
os.environ.setdefault("TBC_DEMO_INSECURE", "1")
os.environ.setdefault("TBC_AUTO_SEED", "0")

# Tests never call a live model, even when a developer's .env (loaded by
# frontend.serve) configures Tencent Cloud ADP. Existing env vars win over
# .env, so pinning them here keeps the suite offline and deterministic.
os.environ["TBC_LLM_PROVIDER"] = "mock"
os.environ["ADP_APP_KEY"] = ""


# The steward who decides each pill (app.PILL_OWNERS defaults), who must
# countersign an admin's rollback.
_PILL_STEWARD = {"CRAH": "steward1", "UPS": "steward1", "Chiller": "steward2", "Pump": "steward2"}


@pytest.fixture()
def rollback():
    """Roll a pill back the two-person way: an admin asks, the pill's steward
    countersigns. Returns the countersign response (the rollback's result)."""
    from fastapi.testclient import TestClient

    from technical_services_pill.app import app

    def _rollback(pill: str, version: int, reason: str = "test rollback") -> dict:
        client = TestClient(app)
        asked = client.post(f"/kb/rollback/{version}",
                            params={"user": "admin1", "pill": pill, "reason": reason})
        assert asked.status_code == 200, asked.text
        request_id = asked.json()["request"]["request_id"]
        done = client.post(f"/kb/rollback-requests/{request_id}/countersign",
                           params={"user": _PILL_STEWARD[pill], "reason": "agreed"})
        assert done.status_code == 200, done.text
        return done.json()

    return _rollback
