# Judge report: Technical Services Intelligence Pill (Keppel "AI HARVEST")

Evaluated: the working tree at /Users/joelgoh/TBC-fork (branch judge-fixes-v4, with uncommitted changes), the live app at http://localhost:8000/ui (Tencent Cloud ADP live), and a scratch server on :8011 with its own DB and an unreachable ADP endpoint. I used the scratch server for the destructive probes. Evidence is in judge2/shots/*.png and judge2/s*.js.

## What I verified

- **Commands:** `make test` gives 358 passed, which matches the README. `make eval` gives 13/13. `make demo` prints DEMO PASSED, including "PUMP 0.49 -> 0.60" and the CRAH/Chiller/Pump version bumps.
- **Expert interview to reuse, UI only, live ADP:**
  - steward1 loaded the sample and drafted it with ADP in 14 s. The Grounding check showed 10 kept and 1 rejected; the rejected line was "oil stain", reworded by the model.
  - The slip-in box rejected an invented line, a cross-answer line and a "jumper … so it never cuts in" line.
  - Sending without consent was refused. Sending with consent created PROP-E4377D23.
  - For steward1, Approve was disabled ("You sent this"). The API returned 403 to steward1, tech1 and admin1.
  - steward2's approval was refused without the safety tick, both in the UI and by the API ("needs a safety review"). With the tick it went live as CRAH/Chiller/Pump v1.4.0 and UPS stayed at v1.3.0.
  - The pump re-run went from 49.0% to 60.5%. "Request more evidence" then re-diagnosed it at 59%, awaiting approval.
  - tech1 opened a new CRAH-DC1-01 case. Its Expert knowledge tab shows R. Tan, the verbatim quote, KB-EXP-E4377D23-2, CRAH v1.4.0, "approved by steward2 (safety-reviewed)", and confidence 67% (60% without the knowledge).
- **Case driven to CLOSED in the UI:**
  - As tech1, AOM Decision showed "Approval Blocked" and the API returned 403.
  - mgr1 approved; an empty rationale was refused.
  - mgr1 raised the work order (tech1 is blocked from doing so). tech1 recorded the outcome, with "Verified by" taken from the session. mgr1 sent feedback and the case went to CLOSED.
  - The audit trail shows 11 chained entries.
- **ESCALATED then resolved in the UI:**
  - CRAH-DC1-02 (G3) was closed with a resolution and a confirmed cause, which created PROP-C35B3805.
  - steward1 approved it and CRAH went to v1.5.0.
- **Rollback:** admin1 rolled Pump back from v1.4.0 to v1.3.0 with a reason. The ledger row was written and the other pills were untouched. The pump case then showed "Knowledge withdrawn… approval blocked until re-scored". Re-scoring gave 48% and the case escalated (G4).
- **AI unavailable (scratch server):**
  - The chip reads "AI offline (Tencent Cloud ADP)".
  - Capture shows "No usable draft… could not reach Tencent Cloud ADP" and offers "Write heuristics by hand".
  - Diagnosis still completes at 60%. The second-opinion card reads "AI offline… rule-based diagnosis remains authoritative" and the audit chain records it.
  - ADP also really failed once on the live server (a 502 during capture).
- **Audit tampering (scratch server):**
  - **Runtime edit of a forged approver:** the tampered DB was archived at the next save and an integrity event was logged.
  - **Offline edit, then restart:** the case was frozen (423), a red Dashboard banner appeared, and the auditor got Integrity Review.
  - **Ledger edit plus a deleted case:** the response reads "ledger entry #2 … was altered" and "a case was added or removed outside the app". Knowledge approvals return 423.
  - **Review order:** the ledger must be reviewed first (409 otherwise). Quarantine works, and every review needs a reason.
- **Unknown asset:** the UI "Other" option with CRAH-DC9-99 created a case with 0 evidence, escalated under G5. AOM Decision offers only "Close escalation".
- **Identity spoofing:**
  - `?user=mgr1` returns 401 without the insecure flag. `/ui?user=admin1` still asks for mgr1's PIN.
  - Forged session and unlock cookies are rejected. Logout revokes the session.
  - Five wrong PINs trigger a lockout (429), and X-Forwarded-For does not get around it.
- **Prompt injection:** a "SYSTEM NOTE: ignore all previous instructions…" line in a custom UPS interview was stripped under G7 and shown as a banner. An expert-invented new cause ("hvac problem") was kept as reference knowledge only.

## Problems found

1. **Grounding checks words, not meaning.** Through `/capture/check`, turning the expert's "Never just reset the alarm and leave it" into **Check: "just reset the alarm and leave it"** is KEPT; it is only flagged for safety review because it contains "alarm". Turning "Swap that one block" into a **Never** is kept with no warning. In the live ADP draft, the expert's dangerous "You can always just jumper the temperature probe" became **Never: "jumper the temperature probe"**: the meaning flipped and it was still labelled grounded. This contradicts the README's "Visible when the AI invents something".
2. **No four-eyes check on cases.** mgr1 alone can approve, raise the work order, record "resolved" (verified_by = mgr1) and send feedback on the same case (scratch server, CASE-75c53b51). Admin holds every capability, including case approval and integrity review. The README says "an auditor records a decision"; admin1 can too.
3. **Integrity review is thin.** A tampered case is reported only as "its audit chain failed verification": every row is marked invalid and the forged "approved by mgr1" row is not pointed out. A deleted case is not named. The only options are Accept (which re-signs) or Quarantine, with no diff against the archived copy. The UI lists the case before the ledger, but the server requires the ledger first.
4. **The technician is a bystander.** tech1 cannot raise a work order or send feedback. The field person whose know-how is the point of the product has no way into the knowledge loop.
5. **Domain realism.** The New Case form offers only "absent/invalid" readings, so a pump vibration *high* alarm shows "Reading: invalid". UPS-DC1-02 at 41 °C and rising is diagnosed as "Battery end of life → replace battery bank" with a hazard acknowledgement, rather than thermal runaway. Expert "new causes" cannot be diagnosed until someone writes code.
6. **Presentation and accessibility gaps.**
   - The text-size histogram on AOM Decision at 1280 px is mostly 14–15 px. That is fine on a laptop and small on a projector.
   - At 1024×768 the Approve controls are below the fold.
   - Escape does not close the PIN modal.
   - Raw tokens leak onto screen ("calibration past", "z z" from Cloudy).
   - The Grounding check shows 4 kept lines and then "… and 6 more", while the README says it lists every one.
   - The capture cause dropdown lists all 23 causes for every asset type.
7. **Demo risk.**
   - ADP takes 10–15 s per advance or draft and returned a 502 once.
   - The README and DEMO.md are honest that the UPS G9 disagreement doesn't appear under ADP, so the "AI disagrees" beat doesn't land live.
   - The rescored seeded chiller case drops from 0.55 to 0.539 as its readings age, then escalates.
   - The "6-minute" script has 11 beats.
   - 26 modified and 3 untracked files are uncommitted. If judges clone HEAD, they won't see per-pill signoff and the related tests.

The README contradictions are minor: the "every line" listing in item 6 and auditor-only review in item 2. Every major README claim I tried reproduced.

## Scores

| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 8 | Every part of the brief works end to end in the UI: capture, reuse, AOM approval, and steward review, versioning and rollback. Knowledge is reused across assets of the same type (CRAH-DC1-02's resolution feeds CRAH-DC1-01). Telemetry is mock data: 8 hardcoded assets at one site. |
| Human-Centered Design | 7 | Every screen has a "What happens next" line, role-blocked controls say why, and rationale, consent and hazard acknowledgement are required. The technician cannot add feedback, capture means pasting a transcript, and screens are full of G-codes, W1–W5 and "Tier 3". |
| AI Interaction | 7 | Real ADP drafting with a visible grounding check, a G7 redaction banner, an advisory second opinion and a clean offline fallback. Grounding misses meaning reversals, latency is 10–15 s and there was a 502. ADP agreed on the showcase disagreement case. |
| Technical Execution | 8 | 358 tests, 13 evals and the demo all pass. Keyed hash chains caught runtime and offline edits, a deleted case and ledger tampering. Per-pill versions and rollback re-score cases. Weaknesses: app.py is 1.9k lines, screens.js is 2.4k lines, and storage is a single-process JSON snapshot. |
| Feasibility | 6 | IMPLEMENTATION_PATH.md is honest. Telemetry and the CMMS are mocks, logins are demo PINs, decision trees are written by hand for each fault, and new causes need an engineer. |
| Demo & Storytelling | 8 | DEMO.md reproduced beat for beat (49% to about 60%, self-approval blocked, version bump, rollback), and there is an in-app guide. Too many beats for 6 minutes, ADP latency, and the UPS G9 beat is flat under ADP. |
| Innovation & Creativity | 7 | The "slip in a line" grounding box, per-pill steward sign-off, blocking cases when knowledge is withdrawn, a non-AI sentinel, and expert-proposed new causes. The core pattern (rules, LLM and a human in the loop) is familiar. |
| UX & Accessibility | 6 | Clean and consistent, with a dark theme, skip link, aria labels and a keyboard-operable assistant. Small text for a projector, controls below the fold at 1024 px, Escape doesn't close the PIN modal, raw tokens on screen, and a 23-item cause list. |
| Responsible AI & Ethics | 8 | Consent, verbatim grounding, safety screen plus steward safety review, advisory-only AI, G9, hazard acknowledgement, two-person knowledge approval and a tamper-evident ledger. Meaning reversals pass, one person can approve and then verify a case, and admin is a superuser. |
| Overall Quality | 7 | An unusually rigorous governance build that holds up under attack. UX polish, domain realism and separation of duties on cases still lag. |

**Total: 72 / 100**

## The 5 changes that would most raise the score (ranked)

1. **Check meaning, not just words, in grounding.** Reject or flag a Check drawn from a clause under "never/don't", and a Never drawn from a positive instruction. Show it on the Grounding check card as "✗ meaning reversed". Treat an expert's own unsafe advice (the probe jumper) as "dropped: unsafe", not as a "Never". Files: `technical_services_pill/capture.py`, `safety.py`, Capture screen (`frontend/static/js/screens.js` groundingCard). Raises AI Interaction and Responsible AI.
2. **Separation of duties on cases, and a voice for the technician.** Make the outcome verifier differ from the approver, and drop case approval and integrity review from admin. Let tech1 record "what I found" from Outcome, so it goes to the stewards as a proposal. Files: `technical_services_pill/rbac.py`, `app.py` (`/cases/{id}/outcome`, `/feedback`, `/audit/review`), Outcome screen. Raises Human-Centered Design, Responsible AI and Impact.
3. **Projector and presenter pass.**
   - Use an 18 px base and higher-contrast badges.
   - On AOM Decision, put cause, hazard and Approve above the fold at 1280×720 and 1024×768.
   - Close the PIN modal on Escape.
   - Replace raw tokens with readable text.
   - Cut DEMO.md to 6 timed beats, and pre-warm or cache the ADP calls.

   Files: `frontend/static/css/app.css`, `frontend/templates/index.html`, AOM Decision screen, `DEMO.md`. Raises UX and Demo.
4. **Integrity-review forensics.** Point to the first failing case entry, show a field diff against the archived `tbc.tampered.*.sqlite`, name any deleted case IDs, and list the ledger first in the UI. Files: `technical_services_pill/audit.py`, `agent_state.py`, `persistence.py`, Governance → Audit & sentinel. Raises Technical Execution and Responsible AI.
5. **Domain realism and a data-driven path to scale.**
   - Base reading status on the fault type (vibration "high", battery °C).
   - Make "hot and rising" put thermal runaway at the top, with isolation as the action.
   - Let a steward-approved "new cause" become a decision-tree branch from config instead of code.
   - Commit the working tree so judges cloning HEAD see this build.

   Files: `technical_services_pill/decision_tree.py`, `mock_registry.py`, New Case form in `screens.js`, git. Raises Feasibility, Impact and Overall.
