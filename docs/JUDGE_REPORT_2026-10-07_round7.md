## Independent judge report: TBC-fork (branch score-push-v5, commit 33e0735)

**Total: 69/100.** The governance and audit machinery is strong and almost all of it is real. The score is held down by one serious gap: the actionable parts of captured expert knowledge are not grounded, and the second steward never sees them.

### What I verified
- `make test`: 179 passed. `make eval`: 12/12 passed. `make demo`: DEMO PASSED, and the pump case goes from ESCALATED at 0.49 to AWAITING_APPROVAL at 0.65 after the interview is approved.
- I drove the UI at http://localhost:8000/ui with Playwright at 1280×720 and 1024×768, switching roles with the PIN picker.
- For the AI-offline and tamper probes I ran a second server on port 8011 with its database in scratchpad. No tracked files were changed; `git status` is clean apart from the existing `Claude outputs/` folder.

| Probe | Result |
|---|---|
| Case driven to CLOSED, UI only | **Pass.** As tech1 I created a CRAH-DC1-01 case and advanced it: 75%, AWAITING_APPROVAL. mgr1 tried to approve with no rationale and was blocked ("Rationale is required"), then approved with one and raised the work order. tech1 recorded the outcome (verifier is the signed-in user). mgr1 submitted feedback, the case went to CLOSED and the feedback form disappeared. The audit chain shows valid. |
| ESCALATED case resolved, UI only | **Pass.** On the CRAH-DC1-02 bus fault (G3 → BMS pill), mgr1 closed the escalation with a resolution and a confirmed cause, which became proposal PROP-BEE25B2F in the ledger. On the pump case, "Request more evidence" and then Advance gave 65% and Approve/Reject/Modify became available. |
| Technician tries to approve | **Pass.** The UI shows "Approval Blocked" with no buttons. The API returns 403 "lacks capability 'approve_reject_modify'". Adding `&user=mgr1` to the URL is ignored. |
| Steward approves own proposal | **Pass.** steward1's own interview proposal has its Approve button disabled. Flaw: steward2 sees an *enabled* Approve on PROP-BBF020B6 (CRAH, owned by steward1), and clicking it returns a 403 toast. |
| Interview → later diagnosis | **Pass, with real Tencent Cloud ADP** (about 14 s to draft). After steward2 approved, the KB went v1.3.0 → v1.4.0. A new CRAH case shows "Expert Knowledge Reused: R. Tan … KB-EXP-32F8E258-2", quoted word for word. |
| Approve → version bump → rollback | **Pass.** A steward gets no rollback control (and 403 from the API). Admin rollback requires a reason and a confirmation step, then v1.4.0 → v1.3.0 with "5 item(s) removed". The pump case that had used the withdrawn knowledge had Approve blocked until re-scored; the re-score gave 49% and escalated. Version labels are not reused. |
| AI unavailable | **Pass.** The chip shows "AI offline (Tencent Cloud ADP)". The second-opinion card says "unavailable; rule-based diagnosis remains authoritative". Capture shows "Draft failed" with a "Write heuristics by hand" fallback. |
| Audit tampering | **Pass.** I edited one history reason directly in the database: on restart the case was flagged "Audit Chain Tampered!" and frozen, with a dashboard banner. Deleting the last history entry was caught by the chain seal. Deleting a whole case set `registry_valid: false`. Caveat: the HMAC key sits in `data/audit.key` next to the database, so anyone with filesystem access could re-sign the chain. |
| Unknown asset | **Pass.** AHU-DC9-77 goes straight to ESCALATED with "[G5] asset not in registry", and its resolution form hides "request more evidence". Minor: the fault dropdown stays on "chiller compressor trip" for an AHU. |
| URL identity spoofing | **Pass.** `/ui?user=admin1` and `#user=admin1` change nothing. A forged cookie, or a real cookie with the user name swapped, gets 401. Five wrong PINs lock the user out for 300 s. Cancelling the PIN dialog leaves the role unchanged. |
| Projector readability | **Mostly pass.** Body text is 15px and badges 13px, and there is a contrast test. The light theme is clear at 1024×768. Pages are very long, the Evidence Timeline dumps raw JSON-like fields, and the role badge disappears at 1024px. |

### Critical finding (Responsible AI and governance)
Only the `evidence_quote` field is checked against the transcript (`technical_services_pill/capture.py` `_validate_items`). The fields people actually act on (`checks`, `never`, `escalate_when`, `symptom_pattern`) are passed through unchecked. The `provider` label is also taken from the client (`app.py` `CaptureInterviewRequest.provider`).

What I did:
1. As steward1, I posted a heuristic to `/capture/interview` with a genuine quote, `checks: ["bypass the low-pressure interlock and restart the compressor"]` and `provider: "adp"`. It was accepted.
2. The Governance queue showed steward2 only the cause and the quote, never the checks, and labelled it "drafted by Tencent Cloud ADP".
3. steward2 clicked Approve. No rationale was asked for.
4. On the chiller case, which carries a safety-hazard banner, the AOM Decision screen then showed **"EXPERT KNOWLEDGE TO APPLY (STEWARD-APPROVED) … Check before acting: bypass the low-pressure interlock and restart the compressor."**

The real ADP output showed the same weakness on the sample interview. It attached "look at the calibration sticker" to the bus-fault heuristic, which contradicts that heuristic's own quote ("Don't go swapping sensors").

### Other problems found
- A knowledge proposal can be rejected with an empty reason (`?reason=` was accepted).
- Approving a proposal records no reviewer rationale. The ledger just says "approved proposal from steward1".
- After rollback, the closed case's AOM screen says "No approved expert knowledge matches", while its own decision record cites R. Tan. What was shown at decision time is not preserved for viewing.
- Copy bug: the blocked-action banners say `Role "tech1"` but show a user name, not a role.
- The escalated case resolved at 37% is labelled "37% Medium" on the dashboard.
- **README contradicts the code:**
  - It says 7 assets with 1 UPS; the registry and New Case form have 8 assets, 2 of them UPS.
  - It says `make reset` leaves the per-case SQLite store intact; the Makefile deletes `technical_services_pill.sqlite3`.
- `docs/` ships six previous internal "JUDGE_REPORT" files, which a real judge would notice.
- Scaling past one asset is partial. There are 4 pills and 8 assets on one site, and the UI itself says "All four pills currently share one knowledge base … no independent per-pill KB". Telemetry is a static mock registry.

### Scores
| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 7 | Hits every brief verb (capture → reuse → AOM → governed versions), but on mock telemetry, one site and a self-labelled 90-minute baseline assumption. |
| Human-Centered Design | 7 | Role-aware screens, rationale required, hazard acknowledgement, "What happens next" hints; but the steward reviews without seeing checks, gets an Approve button that 403s, and sees the role/user copy bug. |
| AI Interaction | 7 | Real ADP draft and an advisory second opinion with G9 that leaves routing unchanged, and it degrades cleanly offline; but LLM-written checks are ungrounded and the provenance label can be spoofed. |
| Technical Execution | 8 | 179 tests, 12/12 evals, keyed hash chain plus seal and registry detection, withdrawn-knowledge approval block, all working; minor UI and state bugs. |
| Feasibility | 6 | Mock registry, SQLite, demo PINs, a fixed two-steward roster, audit key on local disk; the deployment path is honest but mostly future work. |
| Demo & Storytelling | 8 | Five seeded scenarios, an in-app 9-step guide, and every DEMO.md beat reproduced by clicking; let down by the README contradictions and the old judge reports in `docs/`. |
| Innovation & Creativity | 6 | Verbatim-quote grounding, re-scoring after rollback/revocation, and AI-disagreement flagging are nice; the core is a conventional rules engine plus approval workflow. |
| UX & Accessibility | 7 | Keyboard-operable rows, focus-visible styles, reduced-motion support, contrast test, dark theme; very long screens and raw evidence dumps. |
| Responsible AI & Ethics | 6 | Deterministic routing and human-in-the-loop are strong, but a dangerous ungrounded instruction reached the AOM as "steward-approved", empty-reason rejection is allowed, and approvals carry no rationale. |
| Overall Quality | 7 | Mature and well tested; one serious governance hole and several small inconsistencies. |
| **Total** | **69/100** | |

### The 5 changes that would raise the score most, ranked
1. **Ground every actionable field, not just the quote.** In `technical_services_pill/capture.py` `_validate_items`, require each `checks`, `never` and `escalate_when` entry to appear in the item's own quote, or drop or flag it. Also run G1/G2 (interlock/setpoint/safety terms) over approved expert text before it is shown on the AOM Decision screen (`screens.js`, decision render).
2. **Show stewards exactly what they are approving.** On the Governance queue (`frontend/static/js/screens.js`, Knowledge Approval Queue), render each heuristic's checks, never, escalate-when and symptom fields. Require an approval rationale and a non-empty rejection reason, enforced server-side in `app.py` `approve_proposal`/`reject_proposal` and `learning.py`, and record them in the ledger.
3. **Make provenance server-truthful.** Drop the client-supplied `provider` in `app.py` `CaptureInterviewRequest`. Record the provider from a server-held draft ID, mark hand-edited items as "manual", and record expert consent and identity alongside `expert_name`.
4. **Fix the UI/permission mismatches and preserve history.** Disable Approve for a non-owning steward, with the reason shown (Governance screen). Fix the `Role "tech1"` copy (decision/outcome banners). On closed cases, show the expert knowledge as it was at decision time, not the current KB (AOM Decision screen).
5. **Make scaling and the docs credible.** Give each pill or site its own KB version and governance, as the Governance screen itself admits is missing (`learning.py`, `/pills`). Correct the README asset count and the `make reset` description. Move the audit key out of `data/` (`audit.py`, env/KMS only). Remove the `docs/JUDGE_REPORT_*` files from the submission.
