# Frontend

Plain HTML, CSS and ES-module JavaScript served by the backend FastAPI app.
No build step.

```bash
make serve      # from the repo root; open http://localhost:8000/ui
```

`serve.py` loads `.env`, imports `technical_services_pill.app`, mounts
`static/` and serves `templates/index.html` at `/ui`. Persistence and
seeding are the backend's (see the main README).

## Layout

```
frontend/
  serve.py              .env loader, static mount, /ui route
  templates/index.html  single-page shell: nav rail, top bar, role switcher
  static/css/app.css    light theme by default, dark via the top-bar toggle
  static/js/api.js      fetch wrapper: session cookie, readable error messages
  static/js/app.js      navigation, login and role switching, toasts, helpers
  static/js/screens.js  the six screens
  static/js/guide.js    the "Demo guide" walkthrough panel
  static/js/cloud.js    the draggable AI cloud (reports the AI's state only)
```

## Screens

| Screen | Main endpoints |
|---|---|
| Dashboard | `GET /cases`, `GET /cases/{id}`, `POST /cases`, `POST /cases/{id}/advance` |
| Diagnosis | `GET /cases/{id}`, `GET /cases/{id}/expert-knowledge` |
| AOM Decision | `POST /cases/{id}/approval`, `POST /cases/{id}/rescore`, escalation close |
| Outcome | `POST /cases/{id}/work-order`, `/outcome`, `/feedback` |
| Governance | `/kb/queue`, `/kb/proposals`, `/kb/versions?pill=`, `/kb/rollback/{v}?pill=`, `/kb/ledger`, `/pills`, `/audit/trace`, `/audit/status`, `/audit/review`, `/sentinel`, `/sentinel/review`, `/sentinel/drill` |
| Capture | `/capture/sample`, `/capture/draft`, `/capture/check`, `/capture/interview` |

Identity is a signed session cookie set by `POST /login` (PIN in the body);
screens gate controls on the capabilities `/login` returns, and the server
enforces them regardless. Demo PINs are in `DEMO.md`.

Cache-busting: bump the `?v=` query on a module's imports (in `index.html`,
`app.js` and `screens.js`) whenever that file changes.
