## Judge report (round 6): AI HARVEST Technical Services Pill: **70/100**

This is a real improvement on round 5 (63). Three things carry it:
- **Captured know-how changes routing again.** I saw it in the UI: the pump case went from Escalated at 49% to Action required at 65%.
- **A real Tencent Cloud ADP model is live.** It drafts knowledge from interviews and gives grounded second opinions.
- **Audit coverage held up against almost every edit I tried.**

Points are lost to four things:
- a dead end in the UI after a re-score;
- inverted red "abnormal" highlights on the evidence;
- a "Never" list shown as "Expert cautions" with the "do not" stripped;
- one unhashed input that moves confidence.

### What I ran
- `make test`: **165 passed**, matching the README.
- `make eval`: **12/12 passed**.
- `make demo`: **DEMO PASSED**. The pump case goes from ESCALATED at 0.49 to AWAITING_APPROVAL at 0.65.
- About 23 Playwright scripts against `http://localhost:8000/ui`, switching roles with the top-bar picker.
- AI-down and tamper tests against a copy of the repo in my scratchpad, served on port 8011. These used a fake app key and copies of `data/tbc.sqlite`.
- I never printed or copied the real `.env` key.

### Probe results
| Probe | Result |
|---|---|
| Case to CLOSED, UI only | **Pass.**<ul><li>tech1 created and advanced CRAH-DC1-01: Sensor hardware failure, 60%, ADP agrees.</li><li>mgr1's empty rationale was refused ("Rationale is required"); with a rationale, Approve worked.</li><li>mgr1 raised the work order. tech1 recorded the outcome, with "Verified by: tech1" taken from the session.</li><li>tech1 saw "Feedback Blocked". mgr1 submitted feedback, the case closed, and the chain shows valid.</li></ul> |
| ESCALATED then resolved, UI only | **Pass.**<ul><li>The G3 case now shows "What the pill found": cause, 37%, the AI view and the readings, plus "Who to call: BMS pill".</li><li>Closing without a resolution is refused.</li><li>Closing with a confirmed cause created PROP-C3DCE41F.</li></ul> |
| Technician tries to approve | **Pass.** The UI shows "Approval Blocked" with no Approve button. The API returns 403 even with `?user=mgr1` and an `X-User: mgr1` header. |
| Steward approves own proposal | **Pass.**<ul><li>The UI button is disabled with "You sent this. A different steward must decide."</li><li>The API returns 403 ("Chiller knowledge is owned by steward2").</li><li>Note: admin1 can approve any steward's proposal; this is documented ("or an admin").</li></ul> |
| Interview to later diagnosis | **Pass, strongly.**<ul><li>I wrote my own interview (M. Wong, chiller and pump) with an injection line. ADP drafted 2 grounded heuristics in 7 seconds. The G7 banner said the injection was removed, and the pump item was filed under the Pump pill.</li><li>A new CHILLER-DC1-02 case showed "Expert Knowledge Reused" from M. Wong and R. Tan, with verbatim quotes and the matched signals. Confidence was 71%, against a 55% baseline before capture.</li><li>Using the sample interview, steward2 approved it in the UI, and the version went from 1.4.0 to 1.5.0 (toast and footer).</li><li>On the pump case, "Request more evidence" then Advance moved it from **Escalated 49% to Action required 65%**.</li></ul> |
| Approve, version bump, rollback | **Pass, with a bug.**<ul><li>Rollback needs admin, a reason and a confirm step, and writes a ledger row (#9, admin1, v1.5.0 → v1.4.0). The label v1.5.0 is kept as "rolled back".</li><li>The stale pump case blocks approval and Approve is now hidden. The API returns 409 for the other stale case.</li><li>**Bug:** after "Re-score against current knowledge" re-escalates the case to 50%, AOM Decision shows "Recommendation Under Review" with an action (laser realign). It has no resolve or more-evidence controls, while the hint says "resolve the escalation below". This is a UI dead end, and an escalated case still carries an actionable recommendation (`screens.js` around line 796: the branch that has a recommendation runs before the ESCALATED branch).</li></ul> |
| AI unavailable | **Pass.** With a fake ADP key:<ul><li>The chip shows "AI offline (Tencent Cloud ADP)" with the reason on hover.</li><li>The diagnosis still completes in about 1 second, and the AI card says the rules remain authoritative.</li><li>Capture shows a plain-language error and offers "Write heuristics by hand".</li></ul> |
| Tampering with the audit trail | **Mostly pass.** 15 edits tried:<ul><li>**Caught:** an expert's checks, name or approver; a validated case's cause; un-rolling-back a version; a decision rationale; an evidence value; a history reason; deleting a case; truncating the tool log; dropping a ledger entry; changing the `kb_version` stamp. The last one freezes the case (423 on approve).</li><li>**Not caught:** `learning._cause_stats` (cause priors). Changing battery_eol to 1/40 dropped a new UPS case from 0.58 to 0.48, below the recommend threshold, and `/audit/status` still reported ok:true.</li><li>The README's own documented limit still applies: the key file sits on the same host as the database.</li></ul> |
| Unknown asset | **Pass.**<ul><li>G5 escalated it with 0 evidence and a clear explanation. "Request more evidence" is now removed and replaced with "register the asset" guidance.</li><li>The dashboard says "Not yet diagnosed" while the detail view says "0% · escalated".</li></ul> |
| URL identity spoofing | **Pass.**<ul><li>`/ui?user=admin1` with no cookie gets a PIN dialog for mgr1, and a wrong PIN is rejected.</li><li>Swapping the user in a signed cookie gets 401.</li><li>A cookie plus `?user=admin1` still resolves to tech1.</li><li>The cookie now has an issued-at time and a nonce, and a reused cookie after logout gets 401.</li><li>Lockout is per user and IP.</li></ul> |
| Projector readability | **Acceptable, with defects.**<ul><li>Light theme by default, no horizontal scroll at 1024px, smallest text 13px.</li><li>At 1024px the top bar is still 169px tall and the role picker wraps.</li><li>**The red "abnormal" highlight is inverted on the evidence (see below).**</li></ul> |

### Other defects and contradictions
- **Inverted abnormal thresholds** in `screens.js` `_ABNORMAL_THRESHOLDS` (around line 147):
  - `charge_pct` max 70 paints a healthy 95% refrigerant charge red;
  - `soh_pct` max 60 leaves an end-of-life 58% state of health unflagged;
  - `approach_temp` min 3 leaves a fouled 4.2°C unflagged.

  On the screen the AOM reads, normal readings look alarming and the actual fault signals look normal.
- **The "Never" list is shown as "Expert cautions" on Diagnosis.** It reads "Expert cautions: touch the refrigerant / vent refrigerant to check the charge", with the "do not" removed. AOM Decision correctly labels the same list "Never:". This is a safety-relevant wording bug.
- **ADP capture mislabelled one item.** The sample's "it's almost never the sensor. That's the controller or the bus" quote was filed as *Sensor hardware failure*, and the comm-bus heuristic was lost. A human reviewer could catch this, but the demo path approves it as-is.
- **"Disagrees: Unknown cause".** When ADP returned no cause on the re-run pump case, the AOM card said "Disagrees: Unknown cause" and G9 fired. "No opinion" is being shown as disagreement.
- **The README contradicts the app on the guide.** The README says the guide is an "eight-step tour"; the guide shows "STEP 1 OF 9".
- **The Pill Registry undercounts.** Pump shows `proposals_submitted: 0` while holding 2 knowledge items, because a mixed-pill interview is credited only to its main asset type.
- **"Re-run Diagnosis on Similar Open Cases" disappears.** It only fills in right after an approval in the same page session; after a reload it is empty.
- **Stale knowledge isn't flagged outside AOM Decision.** A rolled-back case still shows "71% Recommendable" and "move to AOM Decision to approve" on Diagnosis and the Dashboard.
- **Raw IDs leak through.** "condenser_cleaning" appears as the Tier 3 action, and long `kb:technical_services:…` refs show on Diagnosis.

### Scores
| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 8 | The full harvest loop works: interview → steward approval → reuse → AOM decision → versioned rollback, across 4 pills. Captured know-how now visibly changes routing (49% → 65%). |
| Human-Centered Design | 7 | Rationale, hazard acknowledgement, "who to call", escalation facts and stale-knowledge blocking all help. The post-re-score dead end and "Expert cautions" wording hurt. |
| AI Interaction | 7 | Real ADP drafting in about 7s with quote-or-drop grounding and injection removal, and a real second opinion with readable citations and G9. One mislabelled heuristic, and "unknown" is shown as disagreement. |
| Technical Execution | 7 | 165 tests and 12 evals pass, server-side RBAC holds, and 14 of 15 tamper edits are caught. Cause priors are unhashed, and the re-score path leaves a recommendation on an escalated case. |
| Feasibility | 6 | Deterministic core, Docker, owner-steward enforcement, cookie expiry. Still one shared KB, a mock registry and PIN auth. |
| Demo & Storytelling | 7 | DEMO.md beats reproduce, including the pump flip and the UPS G9 disagreement. The re-run list vanishes after reload, and 8 vs 9 steps don't match. |
| Innovation & Creativity | 7 | Grounded capture with pill filing, the advisory G9 flag, never-reused version labels, freezing a stale or tampered case, harvesting escalation resolutions. |
| UX & Accessibility | 6 | Readable, light theme for projectors, 13px minimum. The inverted red highlights are actively misleading, the 1024px top bar wraps, and raw IDs leak. |
| Responsible AI & Ethics | 8 | The AI never routes, safety gates hold, separation of duties holds, withdrawn knowledge blocks approval, and the offline fallback is honest. Minus the "cautions" wording and the priors tamper gap. |
| Overall Quality | 7 | A mature governance core where most claims are verified. A few sharp UI bugs remain on the exact screens a judge looks at. |
| **Total** | **70/100** | |

### The 5 changes that would most raise the score
1. **Fix the post-re-score dead end.**
   - Where: `technical_services_pill/app.py` (`/cases/{id}/rescore`) and `renderDecision` in `frontend/static/js/screens.js` (around lines 796–849).
   - Clear `recommendation` when a case escalates.
   - Check `ESCALATED` before the "has recommendation" branch, so Resolve and Request-more-evidence always render.
   - Add a test.
2. **Fix the inverted abnormal thresholds.**
   - Where: `screens.js` `_ABNORMAL_THRESHOLDS` (Diagnosis evidence timeline).
   - `charge_pct` and `soh_pct` should flag below the threshold; `approach_temp` should flag above it.
   - Add a test against the seeded fault signatures.
3. **Label expert "do not" items as "Never".**
   - Where: the Expert Knowledge Reused card in `screens.js`.
   - Use "Never:" with the original negation, as AOM Decision already does.
   - Show "AI: no opinion" instead of "Disagrees: Unknown cause"; that change goes in `ai_reasoning.py` (where G9 fires) and the AOM decision summary.
4. **Seal the cause priors.**
   - Where: `learning.py` `_kb_digest`.
   - Hash `_cause_stats`, or better, rebuild it from `validated` on load.
   - Add the tamper case to `tests/test_judge_round5_fixes.py`-style tests.
5. **Tighten capture quality and the story's loose ends.**
   - Where: the ADP prompt in `llm.py`/`capture.py`. Penalise a cause label that the quote itself contradicts ("almost never the sensor").
   - Where: the Governance screen. Make the re-run list persistent (`screens.js` around line 1409).
   - Where: `/pills`. Credit each heuristic's own pill.
   - Where: README. Fix "eight-step" to 9.
   - Where: Diagnosis and Dashboard. Show the stale-knowledge banner there too.

My probes left extra cases, approvals and a rollback (KB now v1.4.0, v1.5.0 rolled back) in the running app's untracked state. Run `make reset` before any live demo. No tracked files were changed. Screenshots and scripts are in the session scratchpad.
