# AI HARVEST Hackathon — Independent Judge Evaluation
**Team repo:** Technical Services Fault Diagnosis Intelligence Pill (Keppel AI HARVEST, Real Estate track)
**Method:** read source, `make test` (115/115 pass), `make eval` (12/12 pass), live UI via Playwright/Chrome at `localhost:8000/ui` with role-switching, and direct API probing (curl) to cross-check every UI-level claim at the backend, including DB-level audit-tamper injection and raw cookie/query-param spoofing.

## Scores (0–10, one line of evidence each)

| Dimension | Score | Evidence |
|---|---|---|
| Impact & Relevance | 8 | Maps directly onto the brief's four asks (capture → reuse → AOM supervision → post-deploy governance → multi-pill scale); value claims are explicitly hedged as "assumption" rather than invented ROI (`frontend/static/js/screens.js:161`). |
| Human-Centered Design | 8 | Every screen has a "what happens next" hint, wrong-role attempts get a specific corrective message ("Switch to Asset Operations Manager (mgr1)") rather than a bare 403, verified live on AOM Decision as tech1 and steward1. |
| AI Interaction | 9 | Deterministic tree is authoritative; AI second opinion is a visually separate card labeled "advisory only — does not affect routing," and a live capture test caught the offline mock model mis-tagging a heuristic ("Communication bus or controller failure" drafted from a transcript that said the bus was fine) — the required human-review step is not decorative, it's load-bearing. |
| Technical Execution | 8 | 115/115 pytest + 12/12 EVAL pass; DB-level audit tamper (direct pickle edit) was correctly detected on reload (`audit_chain_failures: ["CASE-810c198e"]`); self-approval blocked with HTTP 403 at the API, not just hidden in UI. Docked: `POST /kb/rollback/{version}` works perfectly via API but has **zero UI control** — `grep -rn rollback frontend/` finds it only in prose, never wired in `frontend/static/js/screens.js`. |
| Feasibility | 8 | `make test`/`make eval`/`make serve`/Docker all work out of the box; SQLite snapshot + restart-time chain re-verification is real, not aspirational. |
| Demo & Storytelling | 8 | In-app 8-step guided tour (say/notice script) plus `DEMO.md`; dashboard auto-seeds one CLOSED/one ESCALATED/one AWAITING_APPROVAL case matching the README's claim exactly. |
| Innovation & Creativity | 7 | The G2 (must-escalate) vs. G2b (force-approval-with-safety-flag) split for "safety-critical but still human-actionable" causes (e.g. refrigerant leak) is a genuinely thoughtful guardrail distinction, verified live; the rest is solid but conventional RAG + rules-engine architecture. |
| UX & Accessibility | 8 | `tests/test_contrast.py` (28/28, WCAG 4.5:1 parsed from real CSS tokens) backed up by visual check in both themes; dark/light toggle instant and consistent; the "New Case" form renders below the fold with no scroll-into-view, a minor friction point I hit myself. |
| Responsible AI & Ethics | 9 | Grounding is enforced, not claimed: capture drops any heuristic whose quote isn't verbatim, G7 redacts injection patterns before any LLM call, G8 rejects ungrounded recommendations, and capture failures return HTTP 502 (never a silent fabricated draft) while the advisory second-opinion fails soft — verified both paths directly against `ai_reasoning.py`/`capture.py` with `TBC_LLM_PROVIDER=adp` and no key set. |
| Overall Quality | 8 | Almost every README claim survived adversarial probing (tamper, spoofing, self-approval, unknown asset, RBAC bypass); the gaps found (no rollback UI, pump-cavitation knowledge unreachable in the shipped demo data) are real but narrow. |

## Total: 81/100

## Key probe results (all performed live, not assumed)
- **CLOSED via UI only:** created CASE-736f65ae → advanced → approved (mgr1) → work order → outcome → feedback → CLOSED, entirely through clicks.
- **ESCALATED → resolved via UI only:** CASE-31dd52a4 (comm-bus failure, G3) resolved via the "Resolve Escalation" reason box → CLOSED.
- **Technician tries to approve:** UI shows "Approval Blocked... Role tech1 does not have the approve_reject_modify capability"; confirmed the backend independently rejects it (`role 'technician' lacks capability 'approve_reject_modify'`), including with a `?user=mgr1` spoof layered on top of a technician session cookie.
- **Steward self-approval:** UI greys the Approve button and shows "You sent this. A different steward must decide."; API returns 403 `"steward1 proposed PROP-... and cannot also approve it"`.
- **Capture → reuse:** captured an R. Tan/CRAH interview, steward2 approved it (KB v1.6.0→1.7.0), a brand-new case then showed it under "Expert Knowledge Reused" with correct attribution and quote.
- **Approve → version bump → rollback:** v1.3.0→1.4.0→1.5.0 via two approvals; `POST /kb/rollback/1` correctly reverted to v1.4.0 and removed the associated validated case — API-only, no UI button exists for this.
- **AI unavailable:** forced `TBC_LLM_PROVIDER=adp` with no key — second opinion returns a labeled "unavailable" fallback without blocking diagnosis; capture correctly raises `LLMError`→HTTP 502 instead.
- **Audit tampering:** edited a persisted history record's `reason` directly in `data/tbc.sqlite`; reload correctly flagged `audit_chain_failures`.
- **Unknown asset:** `NOPE-999` escalates via G5 with confidence 0.0, never fabricates a diagnosis.
- **URL identity spoofing:** `?user=admin1` with no cookie is rejected by default (`TBC_DEMO_INSECURE` unset); a valid cookie always wins over `?user=`.
- **Projector readability:** `test_contrast.py` passes 28/28; light theme visually crisp at both normal and dark-mode toggle.

## Top 5 changes to raise the score (ranked)
1. **Wire the rollback button into the UI.** `POST /kb/rollback/{version}` is fully correct but has no control anywhere in `frontend/static/js/screens.js`'s Governance screen, even though `frontend/static/js/guide.js:27` tells the demo audience "Rollback restores any earlier version" during the tour — a judge following only the UI will never find it.
2. **Make captured non-CRAH knowledge demonstrable.** `technical_services_pill/mock_registry.py`'s `TELEMETRY` dict has exactly one fixed fixture per asset (`PUMP-DC1-01` always resolves to `shaft_misalignment`), so an expert interview filed under "Pump cavitation" can never actually be reused live in the shipped demo — add a second pump/chiller/UPS fixture or a sensor-keyed variant.
3. **Reconcile the KB "version" integer vs. the displayed semver label.** `POST /kb/rollback/{version}` takes a raw int (e.g. `1`) while every screen shows `v1.4.0` — an operator trying to roll back to what they see on screen will guess wrong. Fix in `technical_services_pill/learning.py` / the rollback route in `app.py`.
4. **Tighten the offline mock capture extractor's cause-tagging.** It mis-tagged a CRAH transcript as "Communication bus or controller failure" purely from the words "bus and config" appearing (even though the transcript said they were fine) — the human-review step caught it in my test, but a rushed reviewer wouldn't. File: `technical_services_pill/capture.py`/`llm.py` mock path.
5. **Surface the G2b safety flag on the AOM Decision screen itself**, not only in the Diagnosis screen's guardrail-grid text — an approver deciding whether to approve a refrigerant-leak repair should see "environmental/pressure hazard" right next to the Approve button. File: `frontend/static/js/screens.js` (`renderDecision`).
