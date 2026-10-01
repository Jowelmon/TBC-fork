# Takeover Notes — Review Fixes F1-F7

Branch: `fixes-review-1` (from `frontend/`)

## What was done

### F1: Fix escalation path through real API
- `advance_case` now loops internally through GATHERING_EVIDENCE → DIAGNOSING cycles until a terminal state is reached (was single-pass before).
- After G4 escalation (low confidence / max gathering loops), guardrails are evaluated anyway to populate `guardrail_result` so G3 cross-domain attribution is not lost.
- `demo.py` case 2 rewritten to use `TestClient` instead of direct `AgentState` manipulation.
- Tests: `tests/test_f1_escalation_api.py` (2 tests).

### F2: Feedback governance via proposals
- `LearningStore.record_feedback` now creates a **pending proposal** (dict) instead of directly ingesting into the KB.
- New methods: `approve_proposal`, `approve_by_feedback_id`, `reject_proposal`, `rollback`, `list_pending_proposals`, `list_all_proposals`, `get_kb_version`.
- New API endpoints: `GET /kb/queue`, `POST /kb/proposals/{id}/approve`, `POST /kb/proposals/{id}/reject`, `POST /kb/rollback/{version}`.
- `ValidatedCase` model gained `kb_version` field (0 = seed, 1+ = approved proposal).
- RBAC: steward/admin can approve/reject; only admin can rollback.
- Frontend: `/kb/queue` renders real proposal cards with Approve/Reject buttons.
- Tests: `tests/test_f2_proposals.py` (6 tests).

### F3: Refrigerant leak safety escalation (G2b)
- New `SAFETY_APPROVAL_REQUIRED_CAUSE_IDS = frozenset({"refrigerant_leak"})` in `guardrails.py`.
- G2b check in `check_guardrails()` matches "refrigerant leak" in `top_cause_label` and sets `require_approval=True` with a safety reason — but does NOT set `must_escalate` (the human can still approve the repair).
- Distinguishes from G2 (safety-critical → must escalate) and G3 (cross-domain → must escalate).
- Tests: `tests/test_f3_refrigerant_leak.py` (2 tests: AWAITING_APPROVAL state + G2b in rule_ids).

### F4: Remove hardcoded "Likelihood 90%"
- Removed the per-candidate-cause `Likelihood: X%` display (was hardcoded 0.9/0.3 in backend).
- Replaced with actual evidence references per cause.
- W1-W5 confidence breakdown already present (static weights + formula + meter).

### F5: Evidence as plain English with abnormal highlighting + raw toggle
- `renderEvidencePlain(payload)` converts JSON keys to human-readable labels (e.g. `low_pressure_switch` → "Low Pressure Switch").
- Abnormal values highlighted in red (booleans like `leak_detected=true`, numeric thresholds like `charge_pct < 70`).
- Toggle button in Evidence Timeline header switches between plain English and raw JSON.
- CSS: `.evidence-plain`, `.evidence-field`, `.evidence-abnormal`, `.evidence-toggle` classes added.

### F6: Fix governance contradiction
- Frontend was looking for `stats.cause_distribution || stats.causes` but backend returns `cause_priors` (dict of cause → {confirmed, total, rate}).
- Added fallback: if `cause_distribution` is empty, extract counts from `cause_priors` using `info.total`.
- Now the cause distribution chart shows real data instead of "No validated cases yet".

### F7: Auto-seed demo cases on first dashboard load
- `_autoSeeded` module-level flag prevents duplicate seeding.
- On first dashboard load with 0 cases, `seedDemoCases(h)` is called automatically.
- Seeds 3 cases: CRAH-DC1-01 → CLOSED, CRAH-DC1-02 → ESCALATED (G3), CHILLER-DC1-01 → AWAITING_APPROVAL (G2b).

## Test count
- 29 tests across 20 test functions (was 27 before F3, 16 originally).
- All pass in ~0.5s.

## Key architectural decisions
1. **Post-G4 guardrail evaluation**: when a case escalates via max gathering loops (G4), guardrails are run anyway to surface G3 cross-domain attribution. This was needed because the normal path (RECOMMENDING → propose_recommendation → guardrails) is never reached when confidence < 0.55.
2. **G2b vs G2**: G2 (safety_critical flag) forces `must_escalate=True` → ESCALATED. G2b (refrigerant_leak cause match) forces `require_approval=True` → AWAITING_APPROVAL. The distinction: thermal runaway is too dangerous to recommend; refrigerant leak is actionable by a human with precautions.
3. **Proposal workflow**: feedback never directly enters the KB — it goes through a steward approval gate with version tracking and rollback capability.

## Files changed (from F1-F7)
- `technical_services_pill/app.py` — advance_case loop, post-G4 guardrail eval, F2 endpoints
- `technical_services_pill/guardrails.py` — G2b check, SAFETY_APPROVAL_REQUIRED_CAUSE_IDS
- `technical_services_pill/learning.py` — proposal workflow, rollback, version tracking
- `technical_services_pill/models.py` — kb_version field on ValidatedCase
- `technical_services_pill/tools.py` — submit_feedback handles proposal return
- `technical_services_pill/demo.py` — TestClient for case 2, approve in learning loop
- `frontend/static/js/screens.js` — F4 evidence refs, F5 plain English, F6 cause_priors, F7 auto-seed
- `frontend/static/css/app.css` — evidence field styles
- `frontend/serve.py` — removed stub /kb/queue (now in app.py)
- `tests/test_f1_escalation_api.py` — new
- `tests/test_f2_proposals.py` — new
- `tests/test_f3_refrigerant_leak.py` — new
- `README.md` — updated for G2b, F2 endpoints, 29 tests, auto-seed
