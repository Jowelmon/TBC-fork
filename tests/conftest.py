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
