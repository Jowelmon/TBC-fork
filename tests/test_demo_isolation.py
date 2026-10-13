"""`make demo` must never write the running server's database: a shared
file made the server log false "snapshot changed on disk" integrity events."""
import os
import subprocess
import sys


def test_demo_runs_without_persisting_to_the_live_database():
    env = {k: v for k, v in os.environ.items() if k not in ("TBC_PERSIST", "TBC_DB_PATH")}
    out = subprocess.run(
        [sys.executable, "-c",
         "import os, technical_services_pill.demo; print(os.environ['TBC_PERSIST'], os.environ['TBC_DB_PATH'])"],
        env={**env, "PYTHONPATH": "."}, capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == "0"
    assert not out[1].startswith("data")
