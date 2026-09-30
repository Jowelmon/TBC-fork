# Frontend - Technical Services Intelligence Pill

## Quick Start

```bash
# From the repo root:
pip install -r requirements.txt jinja2
PYTHONPATH=. uvicorn frontend.serve:app --port 8000

# Open http://localhost:8000/ui in your browser
```

The frontend server imports the existing FastAPI app from
`technical_services_pill.app` and mounts static assets. It does NOT
modify any backend files.

## Demo Walkthrough

1. Open `http://localhost:8000/ui`
2. Click **Seed Demo Cases** on the dashboard (creates 3 cases:
   one CLOSED, one ESCALATED, one AWAITING_APPROVAL)
3. Click any case row to view the diagnosis (Screen 2)
4. Use the role switcher (top right) to change roles and see
   RBAC in action:
   - **Technician (tech1)**: can view cases and record outcomes,
     but approval is blocked (403)
   - **Asset Operations Manager (mgr1)**: can approve, reject,
     modify, create work orders, and submit feedback
   - **Knowledge Steward (steward1)**: can submit feedback and
     view audit trail, but cannot approve decisions
5. For the AWAITING_APPROVAL case (chiller), switch to AOM and
   approve/reject/modify the recommendation
6. View the audit hash chain on the Outcome screen and the
   Pill Summary screen

## Screens

| # | Screen | API Endpoints |
|---|--------|--------------|
| 1 | Asset and Fault Dashboard | `GET /cases`, `GET /cases/{id}` |
| 2 | AI Diagnosis and Recommendation | `GET /cases/{id}` |
| 3 | AOM Decision | `POST /cases/{id}/approval` |
| 4 | Outcome and Feedback | `POST /cases/{id}/work-order`, `POST /cases/{id}/outcome`, `POST /cases/{id}/feedback` |
| 5 | Pill Summary and Governance | `GET /kb/stats`, `GET /audit/trace`, `GET /kb/queue` (stub) |

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
  __init__.py        package marker
  templates/
    index.html       single-page shell with nav rail + role switcher
  static/
    css/app.css      dark theme, large font, semantic colours
    js/api.js        API client (wraps all endpoints with ?user= param)
    js/app.js        app controller (navigation, role, toasts, helpers)
    js/screens.js    renderers for all 5 screens + demo seeder
```

## Notes

- The knowledge approval queue on Screen 5 is a **stub** (pending
  backend implementation by Sab, takeover.md gap 1). The
  `approve_knowledge_version` capability exists in `rbac.py` but no
  endpoint uses it yet.
- The backend uses in-memory storage. Restarting the server wipes
  all cases. Use the Seed button to repopulate.
- No build step. Plain HTML, CSS, and ES module JavaScript served
  by FastAPI StaticFiles.
