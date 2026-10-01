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
    return _templates.TemplateResponse("index.html", {
        "request": request,
        "users": _DEMO_USERS,
    })


@app.get("/kb/queue")
async def kb_queue(user: str):
    """Stub endpoint for the knowledge approval queue.

    Pending backend implementation (takeover.md gap 1). Returns an empty
    queue so the frontend panel renders gracefully.
    """
    from technical_services_pill.app import _need
    _need(user, "approve_knowledge_version")
    return {"queue": [], "pending_count": 0, "note": "pending backend implementation"}
