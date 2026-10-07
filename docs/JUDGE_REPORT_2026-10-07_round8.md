## Independent judge report: AI HARVEST, Keppel challenge (round 8)

**Total: 70/100.** That is one point above round 7. The governance holes from last round are mostly closed. But an approved expert instruction to defeat a safety interlock still reaches the AOM screen as "steward-approved".

### How I tested
- **Tests and evals:** `make test` passed 189 tests. `make eval` passed 12/12. `make demo` printed DEMO PASSED, including the pump going from ESCALATED at 0.49 to AWAITING_APPROVAL at 0.65 once expert knowledge was approved.
- **UI:** I drove the app at :8000 with headless Playwright (Python) at 1280×900 and 1024×768, switching roles with the top-bar picker and real PINs. The server was using the real Tencent Cloud ADP.
- **Destructive probes:** for AI-offline, dangerous knowledge, rollback and tampering I ran a second server on :8011. It used a scratchpad database and audit key, with ADP pointed at a dead endpoint.
- **Side effects:** no tracked files were changed. `git status` is clean apart from the existing `Claude outputs/` folder. The :8000 demo state now holds my test cases and proposals. admin1 was briefly locked out on :8000 by the five-wrong-PIN test.

### Probe results
| Probe | Result |
|---|---|
| Case to CLOSED, UI only | **Pass.** As tech1 I created a CRAH-DC1-01 case and advanced it. Without a refresh the UI kept saying "the agent is diagnosing" while the server was already AWAITING_APPROVAL at 60% (the ADP call takes 10–25 s). mgr1 was blocked without a rationale ("Rationale is required"), then approved. mgr1 raised the work order, tech1 recorded the outcome (the verifier is the signed-in user), mgr1 submitted feedback, and the case went to CLOSED with the chain valid. **Flaw:** Record Outcome is shown before a work order exists and returns a raw internal error ("record_outcome only valid in MONITORING_OUTCOME"). |
| ESCALATED then resolved, UI only | **Pass.** On CRAH-DC1-02 (G3, routed to the BMS pill), tech1 sees "requires the Asset Ops Manager role". mgr1 with an empty resolution is blocked. With a resolution and confirmed cause the case closes and proposal PROP-1A595487 is queued. |
| Technician tries to approve | **Pass.** The UI shows "Approval Blocked … tech1 (Technician)" with no buttons. The API returns 403 "role 'technician' lacks capability". Adding `&user=mgr1` is ignored. |
| Steward approves own proposal | **Pass for approve.** The UI button is disabled with "You sent this", and the API returns 403. **Fail for reject:** `POST /kb/proposals/{id}/reject` has no self-check and no pill-owner check. steward1 rejected their own PROP-780215E2 through the API, and the ledger records "Rejected steward1 … nah". |
| Interview to later diagnosis | **Pass, with real ADP** (draft in about 6–7 s). I wrote my own M. Lee interview; ADP drafted one grounded heuristic. Sending without ticking consent is blocked. steward2 approved it with a rationale and the KB went v1.3.0 → v1.4.0. A new CRAH-DC1-01 case showed "Expert Knowledge Reused: M. Lee … KB-EXP-B0420164-1". KB match went 0.40 → 1.00 and confidence 60% → 75%, and the AOM screen shows the expert's checks, never and escalate-when lines. **Flaw:** the "Matched pattern" text is cut off mid-sentence at 300 characters. |
| Approve, version bump, rollback | **Pass.** Rollback requires admin, a reason and a "Yes, roll back" confirmation. It went v1.4.0 → v1.3.0 ("1 item removed"), the ledger entry was written, and `/kb/versions` marks 1.4.0 as rolled_back (labels are not reused). |
| AI unavailable | **Pass.** The chip shows "AI offline (Tencent Cloud ADP)". The second-opinion card says the rule-based diagnosis remains authoritative, and diagnosis still reaches 60%. Capture shows "Draft failed" with a "Write heuristics by hand" fallback. |
| Audit tampering | **Detected:** I edited a case approval reason and a ledger reason in the snapshot database, then restarted. `/audit/status` showed `broken_cases:[…]` and `ledger_valid:false`, the dashboard showed an integrity banner, the case was frozen (409), and the case timeline said "Audit Chain Tampered!". **Not contained:** with the ledger known to be broken, steward1 could still approve PROP-3DAD7518, so the KB keeps changing on a compromised ledger. The UI also still shows "Raise Work Order" on the frozen case. |
| Unknown asset | **Pass.** `AHU-DC9-77<script>…` goes straight to ESCALATED with "[G5] asset not in registry". The text is escaped, so there is no XSS. There is no format check on the asset ID, and the fault dropdown stays on "chiller compressor trip". |
| URL identity spoofing | **Pass.** `/ui?user=admin1#user=admin1` changes nothing. `/me?user=admin1` returns tech1. A forged cookie, or a real cookie with the user name swapped, gets 401. Five wrong PINs lock the user for 300 s, but anyone can lock out admin this way. |
| Projector readability | **Mostly pass.** Text is 13–16 px and the light and dark themes are both clear. At 1024×768 the role badge disappears, the floating cloud mascot covers table and card content, and the Diagnosis page is 5,300 px tall because the evidence timeline dumps raw specs and JSON. |

### Critical finding (Responsible AI)
README item 9 and DEMO step 3 claim that "lines that would defeat a safety device are dropped". In practice the filter is a keyword regex (`technical_services_pill/capture.py` `_UNSAFE`), and the quote itself is never screened.

What I did:
1. As steward1 I submitted, through the API, a transcript containing "bridge out the high-temp interlock with a link wire so it keeps running till morning". I filed it under `sensor_hardware_failure`, with that text as the check.
2. It was accepted with zero warnings.
3. steward2 approved it with the rationale "looks fine".
4. The AOM Decision screen then showed **"EXPERT KNOWLEDGE TO APPLY (STEWARD-APPROVED) … Check before acting: bridge out the high-temp interlock with a link wire"**.

G1 (interlock/safety block) runs only on the recommendation, never on expert text displayed beside it. There is also no check that the heuristic is relevant to the cause it is filed under.

A smaller grounding gap: "same answer" is found by splitting on blank lines, so a transcript without blank lines makes the whole transcript one answer, and lines can be borrowed from other answers.

### Other problems
- `docs/JUDGE_REPORT_*` (eight files, including round 7) are still committed, along with `CODEBUDDY_IMPLEMENTATION_TASK.md`, `takeover.md`, `api_preview.html`, `chatgpt_share_preview.png` and `miora/`. A real judge would see this as iterate-against-the-grader clutter.
- After AOM approval the decision screen still has the heading "Recommendation Under Review".
- Scaling is still partial. The Governance screen says "All four pills currently share one knowledge base … no independent per-pill KB". It is one site with 8 mock assets and static telemetry. Pill ownership is a fixed two-steward roster.
- PIN lockout is per user only, not tied to the client, so anyone can lock out admin1.

### Scores
| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 7 | Every brief verb works end to end (capture → reuse with confidence 60→75% → AOM → versioned governance), but on mock telemetry and one site. |
| Human-Centered Design | 7 | Role-aware blocked states, required rationales, consent, full heuristic shown to the approving steward; but the screen goes stale during the ADP wait, actions are offered that the server then refuses, and the outcome form appears before a work order exists. |
| AI Interaction | 7 | Real ADP draft and advisory second opinion, clean offline fallback, server-held provenance ("entered by hand" vs ADP); but there is no relevance or safety check of AI or hand content against its cause. |
| Technical Execution | 8 | 189 tests and 12/12 evals; keyed hash chains detect case and ledger tampering; rollback, re-score and freeze all work. KB writes continue on a broken ledger, and reject is ungated. |
| Feasibility | 6 | SQLite, demo PINs, a static registry, one shared KB, a local key file; the scale path exists only in a document. |
| Demo & Storytelling | 8 | Five seeded scenarios, in-app guide, every DEMO beat reproducible by clicking; the README "dropped safety lines" claim fails under probing, and judge reports ship in `docs/`. |
| Innovation & Creativity | 6 | Verbatim grounding, re-score after rollback or revocation, G9 disagreement flag, and the decision-time knowledge snapshot are good; the core is still a rules engine plus an approval workflow. |
| UX & Accessibility | 7 | Contrast test, dark theme, keyboard support, clear toasts; 5,300 px diagnosis page, raw JSON dumps, hidden role badge at 1024 px, mascot covering content. |
| Responsible AI & Ethics | 7 | Better than round 7 (approved content matches what was reviewed, rationales and consent recorded, provenance from the server); but an interlock bypass still reaches the AOM labelled steward-approved, and self-rejection is possible. |
| Overall Quality | 7 | Mature and heavily tested; a few sharp governance and safety gaps and some repo clutter. |
| **Total** | **70/100** | |

### The 5 changes that would most raise the score, ranked
1. **Screen every line of expert knowledge with a safety check, at capture and again when it is displayed.**
   - In `technical_services_pill/capture.py` `_validate_items`, screen the quote and symptom too, and broaden the unsafe-action check beyond the current word list (bridge, link out, jumper, wedge, tape over, raise the setpoint…).
   - Run G1/G2 over approved heuristics before the AOM Decision screen renders them (`frontend/static/js/screens.js`, decision render; `/cases/{id}/expert-knowledge` in `app.py`), and hide or flag any that hit.
   - Flag a heuristic whose quote does not mention the cause it is filed under.
2. **Make rejection follow the same separation-of-duties rules as approval, and freeze the KB when the ledger fails.** In `app.py` `reject_proposal` (and `learning.py`), add the proposer and pill-owner checks. In `approve_proposal`, `rollback` and `revoke`, refuse writes while `/audit/status` reports `ledger_valid:false`.
3. **Fix UI state honesty.**
   - Poll or refresh after Advance until the server state changes (dashboard and Diagnosis screen).
   - Hide Record Outcome until a work order exists, and replace the raw internal error message (Outcome screen).
   - Hide action buttons on frozen cases.
   - Change the "Recommendation Under Review" heading after a decision (AOM Decision screen).
4. **Clean up the submission.** Remove `docs/JUDGE_REPORT_*`, `CODEBUDDY_IMPLEMENTATION_TASK.md`, `takeover.md`, `api_preview.html`, `chatgpt_share_preview.png` and `miora/`. Reword README item 9 and DEMO step 3 to match what the safety filter actually does.
5. **Make scaling real and the screens projector-friendly.**
   - Give each pill or site its own KB version and ledger, as the Governance screen itself admits is missing (`learning.py`, `/pills`).
   - Collapse the evidence timeline into a summary of abnormal readings, with raw data behind a toggle (Diagnosis screen).
   - Keep the role badge visible at 1024 px, and stop the mascot from covering content (`frontend/static/css/app.css`, `cloud.js`).
