"""Frontend server for the Technical Services Intelligence Pill.

Loads ``.env`` (existing environment variables win), imports the backend
FastAPI app and adds the UI to it: static assets under ``/static`` and the
single-page shell at ``/ui``. Persistence is the backend app's own.

Run with:
    PYTHONPATH=. uvicorn frontend.serve:app --port 8000

Then open http://localhost:8000/ui
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from technical_services_pill.app import app
from technical_services_pill.rbac import DEMO_USERS

_BASE = Path(__file__).resolve().parent


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
