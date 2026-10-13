# Judge report: Technical Services Intelligence Pill (Keppel AI HARVEST)

Evaluated on branch `judge-fixes-v4` with a working tree that has uncommitted changes. I used the live app at :8000 (Tencent Cloud ADP live), plus two scratch servers: :8011 with ADP pointed at a dead endpoint, then mock, for the AI-down and tampering tests, and :8012 on a fresh mock database. I drove the UI with Playwright and switched roles through the top-bar picker. Everything below is something I reproduced; screenshots are in `judge3/shots/`.

## What I verified

| Probe | Result |
|---|---|
| `make test` | 366 passed (matches README) |
| `make eval` | 13/13 PASS |
| `make demo` | DEMO PASSED; pump 0.49 ESCALATED → 0.60 AWAITING_APPROVAL after capture |
| Case to CLOSED, UI only | CHILLER-DC1-01. mgr1 Approve was refused without a rationale ("Rationale is required") and without the hazard tick ("Acknowledge the hazard"). Then: approved → raise WO → mgr1 is blocked from recording the outcome ("You approved the work… Switch to tech1") → tech1 records the outcome and sends feedback → Resolved, feedback becomes PROP-30131C98 |
| ESCALATED then resolved, UI only | CRAH-DC1-02 (G3, BMS pill). An empty resolution is refused. Closing with a confirmed cause gives "Escalation closed; resolution sent to stewards as PROP-80BB943B" |
| Escalated then re-diagnosed | PUMP-DC1-01. After the capture was approved, "Request more evidence" re-diagnosed it at 59% → AWAITING_APPROVAL |
| Technician tries to approve | UI: "Approval Blocked… that role cannot approve". API: `role 'technician' lacks capability 'approve_reject_modify'`. Auditor, admin and steward are also refused |
| Hazard ack bypass through the API | Refused: "acknowledge it (hazard_acknowledged=true) before approving" |
| Steward approves own proposal | UI: Approve/Reject disabled, "You sent this. A different steward must decide." API approve and reject both return 403. Admin approve is refused ("only a knowledge steward can approve knowledge"). steward1 approving a Chiller item is refused (pill ownership) |
| Interview → later diagnosis | steward1 drafted the sample with live ADP in 14 s: 10 lines kept, 1 rejected ("reworded"). Slipped-in lines were all rejected, including "check the refrigerant charge", rejected as "said in a different answer". steward2 approval is refused without the safety tick, then accepted: "now live as CRAH v1.4.0, Chiller v1.4.0, Pump v1.4.0" (UPS untouched). A new tech1 CRAH case scored 67% (60% before), and its Expert knowledge tab shows R. Tan, the verbatim quote, KB-EXP-702FEAF2-2, "CRAH v1.4.0", "approved by steward2 (safety-reviewed)". The Governance re-run gives "49.0% → 60.5%" |
| Approve → version bump → rollback | admin1 rolled CRAH back to v1.3.0 (a reason is required; there is a confirm step). Chiller and Pump stayed at v1.4.0. The case scored on v1.4.0 then showed "Knowledge withdrawn… approval is blocked until re-scored", with Approve and Modify hidden and Reject still allowed. Re-score gave 59%, and Approve came back. The next CRAH approval was labelled **v1.5.0**, so labels are not reused. The ledger rows carry actor, reason and version deltas |
| AI unavailable | Chip shows "AI offline (Tencent Cloud ADP)". Diagnosis still completes in 1 s; the AI tab reads "AI offline… rule-based diagnosis remains authoritative", and the audit trail records it. Capture says "Draft failed… could not reach Tencent Cloud ADP" and offers "Write heuristics by hand" |
| Audit tampering at runtime | DB edited while the server was running. At shutdown the tampered copy was archived as `tbc.tampered.*.sqlite`, integrity events were logged, and the genuine state was restored |
| Audit tampering offline | I changed one actor, one confidence (to 95%), one ledger reason, and deleted one case. All four were found and located precisely: "entry #1 … was changed after it was signed", "current data … edited directly", "ledger entry #2 … altered", "Missing: CASE-21cbc08d (opened according to the signed tool log)". A red banner appeared, the case was frozen, and the auditor had to review the ledger first (a case quarantine attempted before that is refused with 409). Accept and quarantine are both written to the ledger |
| Unknown asset | API only; the UI dropdown offers registered assets only. `AHU-DC9-99` → ESCALATED, G5, no evidence, no diagnosis. The UI tells you to "register the asset". A fault type that doesn't match the asset, and an injected sensor id, are both rejected with 400 |
| URL identity spoofing | `?user=mgr1` with no cookie → "?user= is disabled". With a tech cookie plus `?user=mgr1` → still technician. `X-User` header and a forged `tbc_session=mgr1` cookie → no session. Cookies are HttpOnly, SameSite=Lax and HMAC-signed. 5 wrong PINs → 429 lock, and `X-Forwarded-For` doesn't get round it. A no-PIN switch to a user this browser hasn't unlocked is refused |
| Sentinel drill | "the sentinel stopped CASE-a9c1ad8c: the recommendation cites evidence the case does not have: vendor_portal_reading" |
| UPS G9 claim | True on mock (AI says thermal_runaway_risk, so G2b + G6 + G9). With live ADP the AI **agreed** on every seeded case, so G9 never appeared in my live run (DEMO.md says this honestly) |
| Projector readability | Light default; minimum 14 px text; 1280×720 dashboard is clean. **But:** when the table shows 8 columns, the Action column ("Decide", "Resolve") is clipped at 1440 px and pushed past 1024 px. You have to scroll the table sideways to reach the main call-to-action |

## Defects and contradictions found

1. **Quarantined case shows as "Resolved · 95% Recommendable"** (green) on the Dashboard. 95% is the tampered value, and it can't actually be reached: the weights cap the score at 0.75. Before review, a frozen case still shows a "Decide" button in the table.
2. **The approval queue misstates who must sign.** For PROP-702FEAF2 it showed "CRAH · waiting for steward1", yet steward1 was the proposer and cannot sign, and steward2 approved CRAH as stand-in. DEMO.md describes the stand-in correctly; the UI label does not.
3. **The safety word screen has holes, and the README examples over-sell it.**
   - Flagged for review but not dropped: "Pull the plug off the pressure switch and touch the two pins together", "Tape over the buzzer", "Swap the fuse for a 32 amp one".
   - Not flagged at all: "Hold the reset button down with a cable tie". An unflagged line is not "guidance only", so once approved it can raise confidence.
   - The human safety tick is the real control. It does hold: approval is refused without it.
4. **Provenance gap at capture.** Grounding only proves a heuristic is in the text the capturer pasted. The capturer types the transcript and ticks "expert consent" on the expert's behalf. The expert never confirms their own words.
5. Minor issues:
   - The outcome feedback placeholder on a chiller case says "e.g. RTD open circuit".
   - Engineer jargon is shown to managers: "TIER 3/TIER 4", "Causal tree v1, Q5, KB-H3".
   - "Confidence" is a weighted score (max 0.75) drawn on a 0–100% bar, not a calibrated probability.
   - Cloudy is a static help panel, not an assistant.

## Scores

| Criterion | Score | Evidence (one line) |
|---|---|---|
| Impact & Relevance | **8** | The full harvest loop runs on Keppel-relevant DC assets: interview → grounded draft → second steward → reuse lifts PUMP-DC1-01 from 49% (escalated) to 60% (recommendable). But telemetry is mock data, there are 8 hardcoded assets and one site, and the value figures are illustrative. |
| Human-Centered Design | **7** | Each role has its own screen with a "What happens next" strip, plain-language refusals ("You approved the work… Switch to tech1") and a consent step. It falls short on field use (cramped on a phone) and on jargon, and the misleading "waiting for steward1" label confused the sign-off story. |
| AI Interaction | **6** | The AI drafts knowledge from a transcript, and a visible grounding check rejected 1 reworded line out of 11 live. The second opinion is advisory with citations. But live ADP agreed on every case, so it added nothing visible; there is no voice capture and no conversational Q&A; Cloudy is decoration. |
| Technical Execution | **9** | 366 tests, 13/13 evals and the demo all pass. RBAC, hazard ack, SoD and identity are enforced server-side (every API bypass I tried failed). Keyed hash chains pinpoint the exact altered entry and name the deleted case. Persistence is JSON blobs in SQLite on a single process, and `screens.js` is 2.4k lines. |
| Feasibility | **7** | `docs/IMPLEMENTATION_PATH.md` is honest about what is a stub (BMS, CMMS, SSO) and names the seams. But each asset class is a hand-coded Python tree (23 causes), so scaling to new equipment needs developers, not stewards. |
| Demo & Storytelling | **8** | DEMO.md beats reproduced almost to the number (49→60.5%, rejected slipped-in line, disabled self-approval, version toast, rollback block). There is an in-app 9-step guide. The UPS "AI disagrees" beat doesn't fire on live ADP, and the 11-beat script is long. |
| Innovation & Creativity | **8** | Strong ideas: grounding with "reworded / said in a different answer / meaning reversed", per-pill sign-off with an owner stand-in, approval blocked on withdrawn knowledge with re-score, a non-AI sentinel, and an auditor forensic review that must clear the ledger first. |
| UX & Accessibility | **7** | Clean light default, skip link, ARIA tabs, keyboard-focusable rows, `test_contrast.py`. The primary Action column is clipped at 1024 and 1440 px; text goes down to 14 px; the phone view is passable but not field-ready. |
| Responsible AI & Ethics | **9** | Consent is required (400 without it). The AI never routes; "AI offline" is labelled and logged; hazards are server-enforced; every check needs a human safety tick. Weak points: the self-attested consent/transcript provenance gap, and the word-list misses ("cable tie on the reset button" passes unflagged). |
| Overall Quality | **8** | Unusually rigorous governance that holds up when attacked. What's left is polish (integrity status display, table layout, labels) and the thin, mostly invisible AI layer. |

**Total: 77 / 100**

## The 5 changes that would most raise the score (ranked)

1. **Close the capture provenance gap, and make capture sound like the field (Capture screen; `capture.py`, `app.py` `/capture/interview`).**
   - Accept an audio recording and transcribe it with ADP.
   - Keep a hash of the audio with the proposal.
   - Add an "expert confirms" step: the expert signs off their own transcript and consent, instead of the capturer ticking it for them.

   This is the core of the challenge, and today any capturer can type a "transcript". It lifts AI Interaction, Impact and Responsible AI.
2. **Show scale beyond one asset without code (`decision_tree.py`, `mock_registry.py`, Governance → Overview).**
   - Move the causal trees and thresholds into versioned data that a steward edits through the same proposal → approval → rollback flow.
   - Add a second site, or a new asset class, live in the demo.

   This lifts Feasibility and Impact, and it is the "scales beyond one asset" ask stated outright.
3. **Show integrity state honestly (Dashboard table and AOM Decision; `screens.js` `renderDashboard`, `app.js` `statePill`/`confBand`).**
   - Quarantined and frozen cases get their own red status.
   - Hide "Decide" on a frozen case.
   - Never show a score from a failed chain as "Recommendable", and flag a score above the 0.75 maximum as impossible.

   Right now a judge who tampers sees the tampered 95% shown as a green "Resolved" case.
4. **Projector layout and wording (Dashboard table, Governance queue; `app.css`, `screens.js` `renderGovernance`).**
   - Pin the Action column, or drop Sensor/Reading below 1600 px.
   - Raise the body text minimum to 16 px.
   - Replace "TIER 3/4" and "Q5, KB-H3" with plain words.
   - Fix "CRAH · waiting for steward1" to read "steward2 signs for CRAH (owner proposed)".
5. **Harden the safety screen and make the AI second opinion visible (`safety.py`; Diagnosis → AI second opinion tab, `ai_reasoning.py`).**
   - Flag any expert line that names a control element (reset, fuse rating, switch pins, buzzer).
   - Treat all expert checks as guidance-only until N field outcomes confirm them.
   - Add one seeded case where the evidence genuinely conflicts, so live ADP shows G9.
   - Turn the AI's "Would help" evidence requests into one-click "request this evidence" actions.

## Housekeeping

My probes changed the live :8000 state:
- Closed CHILLER-DC1-01 and CRAH-DC1-02.
- Approved PROP-702FEAF2 and PROP-80BB943B.
- Rolled CRAH back, then approved to v1.5.0.
- Added cases CASE-66c35275, CASE-f9a079cb and CASE-f5f093dc.

Run `make reset && make serve` before presenting. I didn't modify any tracked file (`git status` matches the starting snapshot). The scratch servers on :8011 and :8012 are stopped, and their data is under `judge3/scratch*/`.
