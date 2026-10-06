"""Keep the test suite off the demo databases.

Tests used to write cases and knowledge proposals into the same SQLite files
the demo server loads, so the UI opened with stale cases and duplicate
pending proposals. Point both stores at a throwaway directory before any
application module is imported.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="tbc-tests-")
os.environ.setdefault("TBC_DB_PATH", os.path.join(_TMP, "tbc.sqlite"))
os.environ.setdefault("TBC_CASE_DB_PATH", os.path.join(_TMP, "cases.sqlite3"))

# Most of this suite predates the signed-session login flow (auth.py) and
# drives the API with plain ?user= params as shorthand for "acting as this
# role" — a legitimate use of the TBC_DEMO_INSECURE escape hatch, not a
# gap in it. Tests that exercise the login/cookie mechanism itself
# (tests/test_identity.py) override this per-test.
os.environ.setdefault("TBC_DEMO_INSECURE", "1")
