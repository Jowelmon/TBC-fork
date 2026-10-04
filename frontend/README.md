# Frontend - Technical Services Intelligence Pill

## Quick Start

```bash
# From the repo root:
pip install -r requirements.txt jinja2
PYTHONPATH=. uvicorn frontend.serve:app --port 8000

# Open http://localhost:8000/ui in your browser
```

The frontend server imports the FastAPI app from
`technical_services_pill.app` and mounts the UI assets. Persistence is
configured by the backend app itself, so API and UI launches share the same
startup restore and successful-write snapshots.

## Demo Walkthrough

1. Open `http://localhost:8000/ui`
2. Click **Seed Demo Cases** on the dashboard to load the sample
   diagnosis, escalation, and approval workflows.
3. Click a case row to view the diagnosis (Screen 2). If approved expert
   heuristics match the asset type and diagnosed cause, **Expert Knowledge
   Reused** shows their provenance, KB version, quote, and checks.
4. Use the role switcher (top right) to change roles and see
   RBAC in action:
   - **Technician (tech1)**: can view cases and record outcomes,
     but approval is blocked (403)
   - **Asset Operations Manager (mgr1)**: can approve, reject,
     modify, create work orders, and submit feedback
   - **Knowledge Steward (steward1)**: can submit feedback and
     view audit trail, but cannot approve decisions
5. For an AWAITING_APPROVAL case, switch to AOM and
   approve/reject/modify the recommendation
6. Use the **Expert Knowledge Capture** screen to draft a grounded interview
   proposal; approve it from the governance queue as a different steward.
7. View the audit hash chain on the Outcome screen and the Pill Summary screen

## Screens

| # | Screen | API Endpoints |
|---|--------|--------------|
| 1 | Asset and Fault Dashboard | `GET /cases`, `GET /cases/{id}` |
| 2 | Diagnosis and Recommendation + Expert Knowledge Reused | `GET /cases/{id}`, `GET /cases/{id}/expert-knowledge` |
| 3 | AOM Decision | `POST /cases/{id}/approval` |
| 4 | Outcome and Feedback | `POST /cases/{id}/work-order`, `POST /cases/{id}/outcome`, `POST /cases/{id}/feedback` |
| 5 | Pill Summary and Governance | `GET /kb/stats`, `GET /audit/trace`, `GET /kb/queue`, approve/reject/rollback proposal endpoints |

## Role Switcher

Every API call appends `?user=<role_id>`. The role switcher sets
the active user:

| User | Role | Key Capabilities |
|------|------|-------------------|
| tech1 | technician | view_case, record_outcome |
| mgr1 | asset_ops_manager | view_case, approve_reject_modify, record_outcome, submit_feedback |
| steward1 | knowledge_steward | view_case, submit_feedback, approve_knowledge_version, read_audit_trail |
| auditor1 | auditor | view_case, read_audit_trail |
| admin1 | admin | all capabilities |

## Architecture

```
frontend/
  serve.py           imports backend app, mounts StaticFiles, serves /ui
                     (persistence lifecycle lives in backend app)
  __init__.py        package marker
  templates/
    index.html       single-page shell with nav rail + role switcher
  static/
    css/app.css      dark theme, large font, semantic colours
    js/api.js        API client (wraps all endpoints with ?user= param)
    js/app.js        app controller (navigation, role, toasts, helpers)
    js/screens.js    renderers for all 5 screens + demo seeder
```

## Persistence and demo

By default, the FastAPI app restores cases, learning state, proposals, and
tool audit data at startup, then snapshots successful write requests. Audit
chains are re-verified during restore. Set `TBC_PERSIST=0` to disable these
snapshots. The console `make demo` also walks through expert interview
extraction, second-steward approval, diagnosis reuse, and outcome validation.

No frontend build step is required. Plain HTML, CSS, and ES module JavaScript
are served by FastAPI StaticFiles.
