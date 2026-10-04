"""Frontend server for the Technical Services Intelligence Pill.

Imports the existing FastAPI app from technical_services_pill.app and
mounts StaticFiles + Jinja2Templates on it. Does NOT modify any
backend files (except the app.py bug fix already applied).

Run with:
    PYTHONPATH=. uvicorn frontend.serve:app --port 8000

Then open http://localhost:8000/ui
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import logging
import os


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not os.path.exists(path):
        return
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from technical_services_pill import persistence
from technical_services_pill.app import app
from technical_services_pill.rbac import DEMO_USERS

_log = logging.getLogger("tbc.persistence")

_BASE = Path(__file__).resolve().parent

# --- persistence: restore on boot, snapshot after every state change -------
# Disable with TBC_PERSIST=0 (e.g. for a throwaway demo run).
_PERSIST = os.environ.get("TBC_PERSIST", "1") != "0"

if _PERSIST:
    _restore = persistence.load_state()
    _log.warning("persistence restore: %s", _restore)

    @app.middleware("http")
    async def _snapshot_after_write(request: Request, call_next):
        response = await call_next(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
            persistence.save_state()
        return response


# --- mount static files on the existing app ---------------------------------
app.mount("/static", StaticFiles(directory=_BASE / "static"), name="frontend-static")

# --- templates ---------------------------------------------------------------
_templates = Jinja2Templates(directory=_BASE / "templates")

_DEMO_USERS = [
    {"id": uid, "role": u.role.value} for uid, u in DEMO_USERS.items()
]


@app.get("/ui", response_class=HTMLResponse)
async def ui(request: Request):
    """Serve the single-page frontend shell."""
    return _templates.TemplateResponse(request, "index.html", {
        "users": _DEMO_USERS,
    })
