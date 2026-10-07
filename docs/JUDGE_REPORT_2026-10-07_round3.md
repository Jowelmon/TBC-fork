# Independent Judge Report: Technical Services Fault Diagnosis Intelligence Pill (Keppel AI HARVEST)

**Method:** I read the source (`technical_services_pill/*`, `frontend/static/js/*`). I ran `make test`, `make demo` and `make eval`. I drove `http://localhost:8000/ui` with Playwright (Chromium) across all six roles, at 1440×900, 1280×720 and 1024×768, in both themes. I checked each UI result against the raw API with curl. For the AI-offline and tamper probes I started a separate instance on :8001 with its own scratchpad DBs, so the user's server state on :8000 was not restarted or tampered. No tracked files were modified; `git status` is unchanged apart from the existing untracked `Claude outputs/`. I treated the two earlier judge reports in `docs/` as claims to check, not as evidence.

**Reproduction note:** `make test` fails out of the box (`/bin/sh: python: command not found`). The Makefile calls `python` for tests but `python3` for demo and eval, and nothing tells you to activate `.venv`. With `.venv/bin` on PATH: **124/124 tests pass, 12/12 evals pass, `make demo` passes**. The README says "120 tests".

## Scores

| Dimension | Score | Evidence (one line) |
|---|---|---|
| Impact & Relevance | 7 | All four parts of the brief exist end to end: capture, reuse, AOM supervision, versioned governance. But an escalation's expert resolution (e.g. "BMS vendor replaced CTL-02") is never harvested into the KB. That is the most valuable know-how in the system, and it is thrown away. |
| Human-Centered Design | 6 | Role-blocked messages are clear. But the AOM Decision screen shows only "sensor_replacement / Target: sensor / Detail: Replace sensor.": no cause, confidence, evidence or expert heuristic. Approve is one click with no rationale, even under the G2b hazard banner. |
| AI Interaction | 4 | Default "AI" capture is a 9-cause keyword matcher (`llm.py:_CAUSE_KEYWORDS`). A realistic pump interview (misalignment plus cavitation) drafted **nothing** (HTTP 422). The new negation regex also kills real advice ("check the strainer is **not** clogged"). Reused expert knowledge is shown next to the diagnosis but never changes the recommendation. No live LLM was demonstrable. |
| Technical Execution | 6 | Tests are green, but I reproduced real integrity bugs. A feedback POST rejected with 409 still creates a pending proposal. Version labels are reused after rollback. The hash chain is unkeyed, so it can be recomputed. |
| Feasibility | 7 | Runs locally with SQLite snapshot and restore, Docker files and a clean ADP provider hook. But identity is a passwordless `POST /login?user_id=admin1`, state is persisted as `pickle` blobs, and decision trees are hand-coded Python per asset type. |
| Demo & Storytelling | 7 | The 8-step role-aware Demo guide and auto-seeded CLOSED/ESCALATED/AWAITING cases work. `make demo` tells the full capture-to-reuse story in the console. |
| Innovation & Creativity | 6 | G2/G2b split, advisory-only AI second opinion (G9) and a hash-chained state machine are thoughtful. Otherwise it is a conventional rules engine plus Jaccard retrieval. |
| UX & Accessibility | 5 | The role picker, the control the whole demo depends on, is clipped off-screen at 1280×720 and 1024×768. On Governance: "Approval rate **100% (1/5)**", and the Pill Registry showed v1.4.0 while the header showed v1.5.0 right after an approval. A closed case still shows a "Submit Feedback" form, which returns the raw error "queue_feedback only valid in FEEDBACK_QUEUED". |
| Responsible AI & Ethics | 6 | AI sandboxing is real: advisory only, soft-fails when offline, grounding enforced. But KB approvals and rollbacks are not in the tamper-evident trail, the UI writes forged "approved by mgr1" audit entries, and the audit trail records false facts. |
| Overall Quality | 6 | Prior-round fixes landed: G2b banner, G5 path in the UI, form scroll, closed-state hint. But the governance layer, which this challenge is about, breaks under adversarial probing in ways two earlier judge rounds missed. |

## **Total: 60/100**

## Probe results

**Case driven to CLOSED, UI only (CASE-c7d06f47): passed.**
- Flow: tech1 created via New Case → Advance → mgr1 Approve → Raise Work Order → tech1 Record Outcome → mgr1 Submit Feedback. Server state `CLOSED`.
- The "Verified By" text box is ignored: I typed `mgr1` and the server recorded `tech1`. The server is right, but the field is misleading.

**ESCALATED then resolved, UI only (CASE-3c270698): works, with defects.**
- The Decision screen shows the G3 reason and "Who to call: BMS pill". Close is refused with an empty reason and succeeds with one → `CLOSED`.
- The audit trail gives a different escalation reason: "low confidence and max gathering loops (2) exhausted", not G3.
- The "gather more evidence" loop re-ran identical 5-item evidence three times. It is theatre, not new data.
- After closing, the Decision screen says "No recommendation to review yet" and prints "Current state: CLOSED" twice. It does not show the resolution.

**Technician tries to approve: correctly blocked.**
- The UI shows an "Approval Blocked" banner.
- Raw `POST /approval` as tech1 → 403, and adding `&user=mgr1` → still 403.

**Steward approving their own proposal: correctly blocked.**
- The button is disabled ("You sent this. A different steward must decide."). A forced click does nothing.
- Raw API → 403 "steward1 proposed PROP-B725CF39 and cannot also approve it".

**Expert interview capture → later diagnosis: works only for the canned sample.**
- Sample interview → 4 grounded heuristics → steward2 approved → KB v1.5.0.
- A new CRAH-DC1-01 case then shows "Expert Knowledge Reused, R. Tan, KB-EXP-B725CF39-4" with the verbatim quote.
- But confidence only moved from 60% to 60.5%, and the recommended action stayed "Replace sensor." The expert's checks never reach the AOM Decision screen.
- My own pump transcript produced "no grounded heuristics could be extracted".

**Approve → version bump → rollback: works, with real problems.**
- v1.3.0 → v1.4.0 → v1.5.0, then admin rollback to version 0 removed 5 cases, and the expert knowledge vanished from the case.
- Problems:
  - Rollback is a single click with no confirmation and no reason.
  - The rollback is recorded nowhere in the audit trail. The audit actors are only {system, agent, mgr1, cmms, tech1}, and there are no steward or admin entries at all.
  - Roll-forward is impossible.
  - The next approval re-used the label **v1.4.0** for different content. Any case stamped "KB version used: 1.4.0" is now ambiguous.

**AI unavailable (`TBC_LLM_PROVIDER=adp`, no key): handled.**
- The chip honestly shows "Tencent Cloud ADP (key missing)". The second opinion card shows "AI offline" and the diagnosis is unaffected.
- Capture fails hard with no manual-entry fallback, so the harvest stops entirely. The hint "Check the transcript has the expert's own answers" is wrong advice for a missing key.
- The audit entry says "agrees_with_rules=False" when the AI was simply unavailable.

**Tampering with the audit trail (on :8001): partly protected.**
- A naive edit of a history `reason` was detected on restart: a log line plus red FAIL rows in the Governance table. Nothing shows on the Dashboard, and the tampered case stays fully operable.
- A **recomputed chain** (rewrote every `agent` actor to `TAMPERED-agent`, then re-hashed with `compute_hash`) shows `chain_valid: true` everywhere. The chain is unkeyed and unanchored, so README line 534 ("detects any tampering") is false.
- `human_decision`, `outcome`, evidence and the whole KB are outside the chain.

**Unknown asset (NOPE-999 via the new "Other" option): G5 escalation works, but the record is wrong.**
- G5 escalation is reachable in the UI.
- The first audit entry still reads "fault alert validated against asset registry", a false statement in the audit trail.
- The evidence panel shows made-up facts for an asset it knows nothing about ("Controller Reachable: No", "Gateway Healthy: No").
- The case sits at "0% Escalate / Awaiting diagnosis" until someone clicks Advance.

**URL identity spoofing: the URL is blocked, but identity is self-asserted.**
- `?user=` is blocked: the cookie wins and the parameter is off by default.
- But `curl -X POST /login?user_id=admin1` returns an admin session to anyone. There is no credential, so the "HMAC-signed cookie" proves nothing about who is acting.
- Worse, the UI forges attribution itself. As **tech1** I clicked "Seed Demo Cases". The audit trail then contains `CASE-23691224 "approved by mgr1"` and an mgr1 feedback submission that no manager made. `seedDemoCases` silently logs in as mgr1 and steward users.

**Governance poisoning (new finding).**
- `POST /cases/{closed}/feedback` with `{"confirmed_cause":"aliens_did_it","asset_type":"UPS"}` returns 409, yet it **still creates a pending proposal**.
- `submit_feedback` runs before the state check in `app.py:post_feedback`, and `confirmed_cause` / `asset_type` are not validated.
- steward2 approved it, and "aliens did it" became a validated KB case at v1.4.0, visible in Cause Distribution and counted under the UPS pill.
- The UI path does the same thing: re-submitting from the stale form on a closed case queued a "Refrigerant leak" proposal on a CRAH sensor case.

**Projector readability: weak.**
- Light theme contrast is fine and body text is 14px, which is small for a projector.
- At 1280×720 and 1024×768 the top bar overflows: the "Acting as" select is cut off, and at 1024 the Demo guide button is too.

## The 5 changes that would most raise the score (ranked)

1. **Fix the feedback poisoning hole.**
   - Validate case state, and `confirmed_cause` against `KNOWN_CAUSE_IDS`, *before* creating the proposal.
   - Ignore client-supplied `asset_type` and `fault_signature`.
   - Hide the feedback form once the case is CLOSED.
   - Files: `technical_services_pill/app.py` (`post_feedback`), `technical_services_pill/tools.py` (`submit_feedback`), Outcome screen in `frontend/static/js/screens.js`.

2. **Put governance in the tamper-evident trail and anchor it.**
   - Write proposal approve/reject and rollback (with actor, required reason and before/after version) into a global hash chain.
   - Key it with an HMAC or an external anchor so a recomputed chain fails.
   - Make version labels immutable: never reuse 1.4.0 after a rollback.
   - Add a confirm-plus-reason step to Rollback, and a Dashboard banner when any chain fails.
   - Files: `technical_services_pill/learning.py` (`rollback`, approve), `technical_services_pill/audit.py`, Governance screen in `screens.js`.

3. **Stop the UI forging identities, and make identity non-self-asserted.**
   - Move "Seed Demo Cases" server-side under an explicit `system/seed` actor, admin only.
   - Add at least a demo PIN or password to `/login`.
   - Fix the false "validated against asset registry" audit reason for unknown assets.
   - Files: `frontend/static/js/screens.js` (`seedDemoCases` / `apiAs`), `technical_services_pill/auth.py` / `app.py` `/login`, `technical_services_pill/agent_state.py` (trigger reason).

4. **Make harvested knowledge actually reach the decision.**
   - Show the cause, confidence, evidence summary and the matched expert checks/do-nots/escalate-when on the AOM Decision screen.
   - Require a rationale on approval, and an explicit acknowledgement when the G2b banner is present.
   - Let a closed escalation's resolution be captured as a knowledge proposal.
   - Files: `renderDecision` in `frontend/static/js/screens.js`, `close_escalation` in `technical_services_pill/app.py`.

5. **Make capture credible beyond the canned sample.**
   - Replace the keyword or negation heuristics with an LLM path that actually runs in the demo, or cover all 23 causes and use sentence-scoped negation.
   - Add a manual heuristic-entry fallback when the AI is offline.
   - Fix the misleading failure hint.
   - Fix the projector-width top bar (role picker clipped at ≤1280px) and the "100% (1/5)" / stale pill-table contradictions while there.
   - Files: `technical_services_pill/llm.py` (`_mock_extract`, `_NEGATION_PATTERN`), `renderCapture` in `screens.js`, `frontend/static/css/app.css` (`#topbar` / `#role-switcher`), Pill Registry in `screens.js`.

**Artifacts:** screenshots and Playwright scripts were left in the session scratchpad (`pw/`), not in the repo.

**Side effects on the live :8000 demo DB (untracked):** it now holds extra cases, a rolled-back KB at v1.4.0, and a few junk proposals I injected. `make reset` clears them.
