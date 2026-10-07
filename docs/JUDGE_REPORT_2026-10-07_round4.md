## Independent judge report: Technical Services Fault Diagnosis Intelligence Pill (branch score-push-v5, commit 52b90a6)

**Total: 62/100**

### What I ran
- `make test`: 142 passed. `make eval`: 12/12 passed. `make demo` (with `TBC_PERSIST=0`): DEMO PASSED. The learning loop moves confidence from 0.43 to 0.50, but that case stays escalated.
- The UI at :8000 through Playwright, 18 scripted flows, with screenshots saved to the session scratchpad (not in the repo).
- A second, isolated server on :8011 with its state in the scratchpad, used to test AI-down behaviour and tampering after a restart.
- I modified no tracked files. **Side effect:** my probes left cases, proposals and a KB rollback (back to v1.3.0) in the live :8000 state. That state is in gitignored `data/tbc.sqlite`; `make reset` clears it.

### Probe results
| Probe | Result |
|---|---|
| Case to CLOSED, UI only | PASS. tech1 creates and advances; mgr1 approves (empty rationale refused) and raises the work order; tech1 records the outcome; mgr1 gives feedback; case CLOSED. Full keyed audit timeline shown. |
| ESCALATED then resolved, UI only | PASS. On the G3 case, mgr1 closes with a resolution and a confirmed cause, which creates proposal PROP-BAA541CB. **But** a case escalated by low confidence or the evidence-loop cap shows "No guardrail reason was recorded for this escalation", so the AOM is not told why. |
| Technician tries to approve | Blocked in the UI ("Approval Blocked"). The API returns 403, including with `?user=mgr1` appended. |
| Steward approves own proposal | The UI button is disabled. The API returns 403 even with `?user=steward2` spoofed. A second steward approved it. |
| Interview to later diagnosis | **Strongest beat.** steward1 captured a custom pump interview. G7 removed my injected "ignore previous instructions" line. steward2 approved; KB went 1.3.0 → 1.4.0. A new PUMP-DC1-01 case went from **49%, ESCALATED** to **55.1%, AWAITING_APPROVAL**, with "Expert Knowledge Reused" quoting K. Lim word for word. Captured know-how changed the routing. |
| Approve → version bump → rollback | PASS. admin1 rolled back to v1.3.0 (reason required, confirm step, ledger entry) and the next case is back to 49%. **But** the case diagnosed at v1.5.0 still shows "55% Recommendable" with active Approve buttons and no stale-knowledge warning, even though the knowledge that pushed it over 0.55 is gone. Rollback is also all-or-nothing by version: I could not revoke the pump heuristic without also dropping an unrelated CRAH feedback item. |
| AI unavailable | Degrades gracefully. The diagnosis continues and the AI card says "AI offline"; capture offers "Write heuristics by hand". **But** the raw ADP error JSON (code 4505004, TraceId) is shown to users, and the top-bar chip still says "Tencent Cloud ADP" while every call fails. The ADP endpoint is real and reachable: it returned "App key invalid". |
| Tampering with the audit trail | **Mixed.** Editing a chained entry is caught after restart: Dashboard banner, HTTP 423 freeze. **Not caught:** <br>• Cutting the last N history entries. I removed RECOMMENDING and AWAITING_APPROVAL from a case; the chain stayed "valid" and I could still approve it. <br>• Editing `human_decision.decided_by` or `diagnosis.top_cause_id`, which are not hashed (`models.py` `_payload_for_hash` covers only from/to/at/actor/reason). <br>• Dropping the last ledger entry. <br>• Editing KB contents or proposal records. <br>Also, state is persisted with `pickle` (code execution on load), and `data/audit.key` sits next to the DB. |
| Unknown asset | G5 escalates at once with 0 evidence. The Diagnosis screen then contradicts itself: "The agent is gathering sensor readings… Click 'Advance Agent'", but there is no such button. A mismatched fault type (UPS fault on a pump) is accepted and escalates with confidence 0 and no reason. |
| URL identity spoofing | PASS. `?user=` gets 401 without a cookie and is ignored with one; a forged cookie gets 401. **But** there is no rate limit or lockout on the 4-digit PIN: 51 wrong guesses, then the right one, succeeded. PINs travel in the URL query string and sit in plain text in `sessionStorage`. |
| Projector readability | Acceptable. Light theme by default, 15px body text, contrast covered by tests, no horizontal scroll at 1024×768. At 1024 the top bar wraps to two rows, the case table is mostly below the fold, and Diagnosis shows the raw `shaft_misalignment` ID in large blue text plus monospace KB refs and raw JSON evidence. |

### Other verified defects and contradictions
- The AOM Decision screen says "Readings behind this diagnosis: no abnormal reading flagged" on a case whose trigger is an **absent** reading.
- The AI Second Opinion "Supporting" list prints raw Python dict reprs (`{'id': 'CRAH-DC1-01', ...}`).
- The mock second opinion repeats the rule result: it agrees unless a line is tagged `[conflict]` (`llm.py` `_mock_second_opinion`). In the default demo the "AI" adds nothing independent. Mock capture is keyword matching.
- When a feedback proposal is approved, the stored ValidatedCase records `validated_by = submitted_by` (the proposer), not the approver (`learning.py`, about line 425).
- "Owner steward" per pill is display only: any steward approves any pill (steward2 approved a CRAH item owned by steward1).
- Expert-knowledge reuse matches on cause and asset type only. The expert's condition ("axial higher than radial") is never checked against evidence. One unvalidated interview counts as a "resolved" validated case and was enough to tip a case over the 0.55 threshold (0.551).
- README contradictions:
  - The cause count is "23" in one place and "24 causes" in the project tree.
  - README says every on-screen label uses the canonical ID with a plain-English label, but the Diagnosis "Root Cause" line shows the bare ID.
  - "Editing an entry breaks it" is true, but the README is silent that truncation and unhashed fields are not covered.
- The front end gates roles by hardcoded user IDs (`['mgr1','admin1'].includes(role)`), not by role. The server is still authoritative.

### Scores
| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 7 | Hits the brief squarely: interview → steward approval → reuse that flips a live case from escalated to approvable. Telemetry and value numbers are labelled mocks/assumptions. |
| Human-Centered Design | 6 | Clear step tracker, "what happens next" hints, rationale and hazard gates. But escalations without a reason, contradictory empty states and raw IDs undercut the AOM. |
| AI Interaction | 4 | Default "AI" is keyword extraction plus a second opinion that echoes the rules. ADP is wired and reachable but not shown working; failure shows raw error JSON. |
| Technical Execution | 7 | 142 tests, 12 evals and the demo all pass; server-side RBAC and separation of duties hold. The audit chain misses truncation and unhashed decision fields; pickle persistence. |
| Feasibility | 6 | Deterministic core, Docker, a stated pilot path. Shared single KB, display-only pill ownership, mock registry, no auth hardening. |
| Demo & Storytelling | 7 | The 8-step guide and DEMO.md are coherent, and the capture-to-reuse uplift is real and visible. The console learning loop never changes an outcome. |
| Innovation & Creativity | 6 | Grounded quote-or-drop capture, G9 advisory flag and never-reused version labels are thoughtful. Retrieval is Jaccard on cause tokens. |
| UX & Accessibility | 6 | Skip link, contrast tests, light default. Dense raw evidence, raw cause IDs, wrapping top bar at 1024, dict dumps in the AI card. |
| Responsible AI & Ethics | 7 | AI never routes, injection is redacted, ungrounded items are dropped, a hazard needs acknowledgement, self-approval is blocked. But rolled-back knowledge silently keeps backing an approvable recommendation, and one interview counts as "validated". |
| Overall Quality | 6 | Solid governance core with visible seams the probes exposed in a few minutes. |
| **Total** | **62/100** | |

### The 5 changes that would most raise the score
1. **Handle stale knowledge after rollback** (`learning.py` `rollback`, `app.py` `post_approval`, AOM Decision screen in `screens.js`). Flag every open case whose `kb_version_used` was rolled back, require a re-run before approval, and allow revoking a single proposal instead of a whole version.
2. **Close the audit-integrity gaps** (`models.py` `HistoryEntry._payload_for_hash`, `agent_state.py`, `learning.py` ledger, `persistence.py`).
   - Hash the decision, diagnosis and outcome payloads.
   - Anchor the chain head and length in a signed checkpoint so truncation is caught.
   - Chain KB contents and proposal records.
   - Replace pickle with JSON or a schema.
3. **Make the AI real and independent** (`llm.py`, `ai_reasoning.py`, Diagnosis "AI Second Opinion" card). Demo with a working ADP key. Give the second opinion its own reasoning, and show a seeded case where it disagrees (G9). Replace raw error JSON and dict reprs with plain-language text, and make the model chip show failure.
4. **Explain every escalation and remove on-screen contradictions** (`app.py` `_advance`, `renderDiagnosis` and `renderDecision` in `screens.js`).
   - Record a G4/loop-cap reason on every escalation.
   - Fix the unknown-asset "click Advance Agent" text and the "no abnormal reading" line on an absent reading.
   - Show plain-English cause labels and readable evidence.
   - Reject fault types that don't match the asset.
5. **Make governance and reuse more than cosmetic** (`learning.py` `approve_proposal` and heuristic matching, `app.py` `/pills` and `/login`, `auth.py`).
   - Enforce the owning steward per pill; fix `validated_by`.
   - Check a heuristic's stated conditions against evidence before counting it as support.
   - Add PIN rate limiting/lockout and stop putting PINs in URLs and `sessionStorage`.
