# Judge report: Technical Services Intelligence Pill (TBC-fork, branch `ui-nav-header-table` @ f70763a)

Keppel challenge "AI HARVEST". Evaluated 2026-10-13 against the running app at :8000 (live provider: **Tencent Cloud ADP**, `/system/info` → `ai_status: online`), plus two isolated scratch servers I started myself: :8001 with ADP pointed at a dead endpoint, and :8002 on a tampered *copy* of the DB. Nothing tracked in the repo was changed. `git status` is clean.

Verified by running: `make test` → **342 passed** (matches README). `make eval` → **13/13 PASS**. `make demo` → **DEMO PASSED** (exit 0). Everything else was done in the UI with Playwright (22 scripts, about 40 screenshots in `judge/shots/`) or with curl using real session cookies.

## 1. Scores

| Dimension | Score | One-line evidence |
|---|---|---|
| Impact & Relevance | 8 | Hits all of capture → reuse → AOM supervision → steward governance → versioning across 4 asset types and 8 assets. Verified: R. Tan's interview became KB-EXP-592C2D1D-2 and showed on a new CRAH diagnosis with expert, quote, version and approver. |
| Human-Centered Design | 7 | Every screen has a "What happens next" line, plus role-gated controls with plain reasons ("You sent this. A different steward must decide."). But DEMO.md's role choreography is wrong, and the dashboard's Action column is "-" on cases waiting for the AOM. |
| AI Interaction | 7 | The live ADP draft took about 14 s, and the grounding check visibly rejected an invented line ("look for an oil stain near the joints"). The second opinion is advisory and degrades cleanly when offline. But the capturer-reviewed WHEN/quote text differs from what the steward approves. |
| Technical Execution | 7 | 342 tests, 13 evals, keyed hash chains, and server-side RBAC that held on every bypass I tried. Deductions: `make demo` writes into the live server's DB and creates false tamper events; re-run deltas mix wall-clock staleness with knowledge changes; unvalidated sensor IDs. |
| Feasibility | 6 | Plain FastAPI, SQLite, Docker, a documented ADP seam and an IMPLEMENTATION_PATH doc. But telemetry and CMMS are mocks, identity is PIN-only (6 hardcoded users), and the pill roster is env-configured. Heuristics are self-declared "illustrative". |
| Demo & Storytelling | 6 | The guide panel, seeded scenarios, Cloudy and the console demo are strong. But following DEMO.md literally breaks at steps 4, 5 and 6 (wrong capturer/approver; New Case defaults to CHILLER, not CRAH). |
| Innovation & Creativity | 7 | Verbatim-grounding with a "slip in a line" test box, per-pill knowledge filing, safety-reviewed "guidance only" heuristics, an independent sentinel, and knowledge-withdrawn → re-score blocking are all above the usual hackathon level. |
| UX & Accessibility | 6 | Readable at 1280×720 (15px body, 14px badges), dark theme, skip link, ARIA tabs, no horizontal scroll at 390px. Deductions: the dashboard shows "59% · escalated" in red for a resolved, approved case; the governance tab is remembered and hides the queue; the mobile KB footer is mangled; tabs are dense. |
| Responsible AI & Ethics | 8 | Consent is required (400 without it), self-approval is blocked on the server, admins can't decide knowledge, hazard ack is enforced (G2b, 400 without it), tamper detection freezes cases, and AI-offline is labelled. Deductions: a single steward approves other pills' knowledge in a mixed interview; a hot, rising UPS battery gets no hazard gate when ADP agrees. |
| Overall Quality | 7 | An unusually complete, governed system. Losses come from demo-script drift and a few correctness bugs a judge will hit in the first 10 minutes. |
| **Total** | **69 / 100** | |

## 2. Why points were deducted

- **Impact & Relevance (−2):** Cause trees and thresholds are self-described as illustrative, with no SME validation. "Scales beyond one asset" is shown across 4 types and 8 assets in one mock registry, with no import path for a real asset register. Scaling is per-type, not per-site.
- **Human-Centered Design (−3):**
  - DEMO.md tells the presenter the wrong role at the governance beats.
  - The dashboard Action column only ever shows "Advance", so mgr1 gets no "Decide" shortcut on Action-required rows.
  - "Request more evidence" leaves the case in *Awaiting diagnosis*, so the user must find Diagnosis → Advance Agent. The re-run hint says it "re-diagnoses it", which it does not do on its own.
  - The feedback toast says "Feedback submitted (KB: 8 cases)" while it is still only a pending proposal.
- **AI Interaction (−3):**
  - What the capturer reviews isn't what the steward approves. On the capture screen, the bus-failure heuristic's WHEN was "If every tag on the bus has gone quiet at once…". In the queue (`/kb/queue`) the stored WHEN and quote start "First thing, I check if it's just that one sensor…".
  - Rejection reasons are misleading. "look for an oil stain near the joints" is flagged "no source found in the transcript", yet the transcript literally contains "there's an oil stain near the joints". It is a paraphrase, not an invention.
  - "Never: go swapping sensors" shows as a green ✓ line "go swapping sensors" in the grounding list, which out of context reads like an instruction.
  - No duplicate detection: the same sample interview can be submitted twice (PROP-47B05CE7).
- **Technical Execution (−3):**
  - (a) `make demo` uses `TestClient(app)` with the default `TBC_PERSIST=1`. Every POST saves to `data/tbc.sqlite`, the live server's DB. The running server then logged 4 "Snapshot changed on disk between saves" integrity events and archived 4 `data/tbc.tampered.*.sqlite` files. These are false positives caused only by running the documented `make demo` (Governance → Audit → Integrity Events). After a restart, the server would load the demo's cases instead of the seed.
  - (b) `/cases/{id}/confidence-preview` compares the stored score (staleness 0 at creation) with a fresh score that includes wall-clock staleness. Right after approving R. Tan's interview, the re-run card showed CRAH-DC1-02 **36.6% → 32.7%** (now below the 35% escalate line) and the awaiting-approval chiller **55.0% → 54.0%** (now below the 55% recommend line), with `kb_match` unchanged. The change was pure time decay, presented as the knowledge's effect. The headline pump result (49 → 59.6%) also degrades the longer the server runs.
  - (c) `POST /cases?asset_id=CRAH-DC1-01&sensor_id=BOGUS-99` succeeds and attaches SA-TEMP-01's reading and metadata as evidence for BOGUS-99.
- **Feasibility (−4):** Mock telemetry and CMMS; PIN login with published defaults; a fixed `DEMO_USERS` dict, so you can't add a user without code. Any `view_case` role, including the auditor, can create and advance cases (auditor created CASE-8f787edc on :8001). Pill ownership is one steward per pill from env.
- **Demo & Storytelling (−4):** See section 6. Three of eleven script beats don't match the screen when followed literally. The sentinel drill takes about 10.7 s on ADP with only a spinner. The console demo is good but pollutes UI state (above).
- **Innovation (−3):** The core diagnosis is a hand-written decision tree, and learning is a kb_match term. That's sound governance but modest "intelligence". The AI's role is drafting and a second opinion only.
- **UX & Accessibility (−4):**
  - `screens.js:559-560`: `wasEscalated` makes any once-escalated case render a red "NN% · escalated" chip forever. PUMP-DC1-01 is shown **Resolved + "59% · escalated"** after being re-diagnosed at 59%, approved and closed.
  - The Governance screen remembers the last tab, so a steward returning to approve lands on "Approved & versions" with the queue hidden (my automation hit this).
  - At 390px the collapsed rail wraps the KB footer one word per line.
  - The 401 on first load is logged to the console on every page load.
  - The new-case form doesn't navigate to the created case.
- **Responsible AI (−2):**
  - `_require_pill_owner` (`app.py:1349-1365`) checks only the proposal's *main* asset_type. Approving the CRAH-tagged interview let steward1 (CRAH/UPS owner) push **Chiller v1.4.0 and Pump v1.4.0** live, pills owned by steward2, who was blocked.
  - Revoke needs only `approve_knowledge_version` (`app.py:1400-1410`). One steward can revoke any approved knowledge alone, with no owner or second-person check.
  - UPS-DC1-02 shows "battery temp high" and "Temp rising: Yes" but is routed as routine "battery end of life" with no G2/G2b hazard acknowledgement. With ADP live the second opinion agreed, so nothing flags thermal-runaway risk at all.
- **Overall (−3):** All of the above. None of it is fatal, but a judge finds most of it by following the team's own script.

## 3. What was done well

- **Server-side enforcement held under every bypass I tried:**
  - technician/auditor approve → 403
  - mgr1 approves knowledge → 403
  - admin approves knowledge → 403 "only a knowledge steward…"
  - non-owner steward → 403
  - JS-forced self-approval by steward1 → 403 "steward1 proposed PROP-47B05CE7 and cannot also approve it"
  - approval without the safety review → 400
  - case approval without a rationale or hazard ack → 400
- **URL spoofing is closed.** `/me?user=admin1` with no cookie → 401. With tech1's cookie plus `?user=admin1` → still tech1.
- **Tamper evidence is real.** On a DB copy I edited one case-history reason and one ledger reason. On restart: the case was frozen (rescore → 423), a red Dashboard banner appeared, knowledge-withdrawn chips showed on dependent cases, and Integrity Review pinpointed "ledger entry #8 (rollback by admin1) was altered". Accept/Quarantine require a reason.
- **Rollback and versioning are excellent.** CRAH v1.5.0 → v1.3.0 left the other pills alone. The open case CASE-bb108df3 had Approve/Modify removed with "Knowledge withdrawn…" until it was re-scored (67% → 60%). The next approval was labelled **v1.6.0**, so labels were not reused. The ledger shows actor, reason and version deltas.
- **AI-offline behaviour is honest.** The chip reads "AI offline (Tencent Cloud ADP)". The second opinion says "unavailable; the rule-based diagnosis remains authoritative (could not reach Tencent Cloud ADP (network error))". Capture says "nothing was drafted… capture this interview by hand". Diagnosis is unaffected.
- **Unknown asset** NOPE-999 → G5 immediate escalation with 0 evidence, and a resolution UI that explains there is no data source.
- **Full lifecycle via UI only:**
  - PUMP-DC1-01: escalated at 49% → interview approved → request more evidence → advance → 59% → AOM approve → work order → tech1 outcome → mgr1 feedback → **CLOSED**.
  - CRAH-DC1-02: ESCALATED → closed with resolution + confirmed cause → PROP-9F299D16 → steward1 approved → CRAH v1.5.0.
- **Expert knowledge reuse shows provenance.** "R. Tan — Senior M&E Technician, 22 years · KB-EXP-592C2D1D-2 · CRAH v1.4.0 · Approved by steward1 (safety-reviewed)", with a verbatim quote and the matched signals ("calibration past").
- **Projector readability is good** at 1280×720: 15px body, high-contrast badges, sensible dark theme.

## 4. What can be done better

- Isolate `make demo` persistence by setting `TBC_PERSIST=0` or a temp `TBC_DB_PATH` in `demo.py`/Makefile, as the evals already do.
- Freeze `observed_at` for staleness, or compute before and after at the same instant, so re-run deltas show only the knowledge effect.
- Enforce per-heuristic pill ownership. Either split a multi-pill interview into per-pill approvals, or require each owning steward.
- Show the capturer exactly what will be stored. Run `reviewed_draft` server-side and diff it before submission.
- Rewrite DEMO.md steps 2–6 for the real role and default-asset behaviour, and add a CI check that walks DEMO.md with Playwright.
- Fix the escalated chip, add a "Decide" action for AOMs, and auto-advance after "Request more evidence".
- Validate sensor_id against the asset. Restrict case creation and advance to technician/AOM roles.
- Add a UPS thermal hazard rule (temp high + rising → G2b).

## 5. Reported errors and findings

| # | Severity | Finding | Where |
|---|---|---|---|
| 1 | High | `make demo` writes to the live `data/tbc.sqlite`. The running server recorded 4 false "snapshot changed on disk" integrity events and archived 4 `data/tbc.tampered.20261013-135706-*.sqlite`. A server restart after `make demo` would load the demo's state. | `technical_services_pill/demo.py:183,446` (TestClient without TBC_PERSIST=0); `app.py` `_snapshot_after_write`; `persistence.py:37` default path |
| 2 | High (governance) | The owner check uses only the proposal's main asset_type. steward1 approved Chiller and Pump knowledge owned by steward2 (ledger #4: "CRAH v1.3.0→v1.4.0, Chiller v1.3.0→v1.4.0, Pump v1.3.0→v1.4.0", actor steward1). | `app.py:1349-1365` `_require_pill_owner` |
| 3 | Medium | The re-run preview mixes wall-clock staleness with knowledge effect. Shown: CRAH-DC1-02 36.6→32.7%, CHILLER 55.0→54.0% (kb_match unchanged, staleness 0→0.40/0.10). | `app.py:682-697` `preview_confidence`; `confidence.derive_confidence_signals` |
| 4 | Medium | Capture fidelity: the WHEN and quote reviewed on the Capture screen differ from the stored proposal shown to the steward (bus-failure heuristic). | `app.py:1116-1160` → `capture.reviewed_draft`; Capture vs Governance → Approval queue |
| 5 | Medium | Any steward can revoke any approved proposal alone. | `app.py:1400-1410` |
| 6 | Medium | Sensor ID isn't validated. BOGUS-99 on CRAH-DC1-01 gets SA-TEMP-01's readings and metadata as evidence. | `app.py:328-401` `_new_case` → `tools.gather_evidence_for_fault` |
| 7 | Low/Med | Auditor (view_case only) can create and advance cases. | `app.py:343` `_need(user, "view_case")`, `/advance` |
| 8 | Low | The dashboard shows "NN% · escalated" (red) for any case ever escalated, even after re-diagnosis, approval and closure (PUMP-DC1-01). | `frontend/static/js/screens.js:559-560` |
| 9 | Low | The grounding rejection reason is wrong for paraphrases ("no source found in the transcript" for a phrase present in the transcript). | `capture.py` check_draft reasons |
| 10 | Low | The feedback toast "Feedback submitted (KB: 8 cases)" implies it's live while it is only a pending proposal. | Outcome screen |
| 11 | Low | 401 console error on every first page load (pre-login `/me`). | `app.js` boot |
| 12 | Low | UPS with "battery temp high + temp rising" routes as routine EOL with no hazard gate. G9 only fires with the mock, not with live ADP. | `guardrails.py` G2/G2b; seeded UPS-DC1-02 |
| 13 | Info | Duplicate interviews are accepted with no warning. | `/capture/interview` |
| 14 | Info | Sentinel drill takes about 10.7 s on live ADP. A 3 s wait showed an empty toast and "Nothing stopped" until refresh. | Governance → Audit & sentinel |

There were no test or eval failures: 342/342 tests and 13/13 evals pass, with one DeprecationWarning (starlette/anyio). README claims checked: the test count, the per-pill versions, the rollback isolation, the never-reused labels, ?user= being disabled, the frozen tampered case, the hazard ack, the AI-offline label, and G5 all match behaviour. The README contradiction is in finding 2: "the pill's owning steward decides" is only true for the main pill of a multi-pill proposal.

## 6. Broken parts of the demo (DEMO.md)

- **Steps 2–5 (capture → self-approval → second steward):** The app opens as mgr1 and step 2 doesn't say to switch roles, so mgr1 is the capturer. At step 4, steward1's Approve is **enabled**, not disabled; steward1 is the CRAH owner and not the submitter. At step 5, steward2's Approve is **disabled**: "CRAH knowledge is owned by steward1; they decide." The script only works if the presenter captures as steward1, which the script never says.
- **Step 5 (re-run PUMP):** "49% becomes about 60%" happened (49.0 → 59.6%). But the same card showed two other cases *dropping* (36.6→32.7%, 55.0→54.0%) right after "approving knowledge". The pump figure also falls as the server ages (staleness).
- **Step 5 → ESCALATED pump:** The hint says "Request more evidence re-diagnoses it". In fact the case goes to Awaiting diagnosis and needs Diagnosis → Advance Agent.
- **Step 6 ("New Case, keep CRAH-DC1-01"):** The form defaults to **CHILLER-DC1-01** with a made-up sensor "CHILLER-DC1-01-SENSOR", and the created case stays on the Dashboard. Followed literally, this creates a chiller case, and the R. Tan sensor heuristic never appears.
- **Step 7 (UPS second opinion):** With live ADP it "agrees". The script admits this. The "one to watch" beat delivers nothing on the configured provider.
- **Step 11 (sentinel drill):** It works, but takes about 11 s on ADP before the toast and banner appear.
- **`make demo`:** It passes, but silently overwrites the UI's persisted state and triggers 4 integrity-event false positives in the running server. A presenter who runs `make demo` mid-demo will show the judges "tampered snapshot" alerts.

## 7. Top 5 changes, ranked

1. **Fix DEMO.md steps 2–6 to match the app.** Capture as steward1 (or default the capturer to steward1), so steward1 is blocked and steward2 approves. Default New Case to CRAH-DC1-01 / SA-TEMP-01. Add an "Advance" step after "Request more evidence". Back it with a Playwright walk-through in CI. (`DEMO.md`; `frontend/static/js/screens.js` new-case form ~line 316; `frontend/static/js/guide.js`)
2. **Isolate `make demo` persistence** (`TBC_PERSIST=0` or a temp `TBC_DB_PATH`), so it never writes `data/tbc.sqlite` or causes false tamper events. (`technical_services_pill/demo.py`, `Makefile` demo target)
3. **Per-pill approval for multi-pill proposals.** Each owning steward approves their pill's heuristics, or the proposal is split by pill. Add an owner or second-person check to revoke. (`technical_services_pill/app.py:1349-1410`, `learning.py` approve_proposal/revoke_proposal)
4. **Make the re-run delta knowledge-only.** Score before and after at the same timestamp, or show the staleness separately. Never show a "drop" caused by elapsed time as the result of an approval. (`app.py:682-697`, `confidence.py`; Governance → Re-run card)
5. **Fix capture fidelity and UI truthfulness.** Show the capturer the exact server-normalised WHEN and quote before submission. Fix the "· escalated" chip for closed cases (`screens.js:559-560`). Validate sensor_id per asset (`app.py` `_new_case`). Add a UPS thermal hazard gate (`guardrails.py`).
