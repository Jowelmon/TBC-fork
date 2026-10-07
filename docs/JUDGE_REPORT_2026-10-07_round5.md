## Judge report (round 5): AI HARVEST Technical Services Pill: **63/100**

Most round-4 holes are fixed: governance, identity and failure handling all held up under live probing. Points are lost on two things. The audit section of the README claims more than the code delivers, and I bypassed it. And the headline "captured know-how changes the outcome" beat no longer changes any outcome.

**What I ran:**
- `make test`: 156 passed.
- `make eval`: 12/12 passed.
- `make demo`: passed.
- About 12 Playwright scripts against `http://localhost:8000/ui`, switching roles with the top-bar picker.
- Tamper tests on copies of `data/tbc.sqlite`, each served by a second server on port 8011.

### Probe results
| Probe | Result |
|---|---|
| Case to CLOSED, UI only | **Pass.** tech1 created and advanced CRAH-DC1-01 (60%). The technician was shown "Approval Blocked". mgr1 approved; an empty rationale was refused. mgr1 raised the work order, tech1 recorded the outcome (verified_by = tech1), and the technician was blocked from submitting feedback. mgr1 submitted feedback and the case closed with a valid audit chain. |
| ESCALATED then resolved, UI only | **Pass.** The G3 case shows "Who to call: BMS pill", and closing it with a confirmed cause created PROP-4F4520D1. Every escalation now gives a reason (G3, G4, G5). **But** the escalated Decision view shows only guardrail strings, not the diagnosed cause or the readings, so the AOM resolves the case blind. |
| Technician tries to approve | **Pass.** Blocked in the UI; the API returns 403. Adding `?user=mgr1` or `X-User` headers doesn't help. |
| Steward approves own proposal | **Pass.** The button is disabled with "You sent this". The API refuses the owner-steward rule, refuses admin1 self-approval, and ignores a spoofed `?user=`. |
| Interview to later diagnosis | **Works, but no longer changes anything.** steward1 captured a custom pump interview, steward2 approved, and KB went 1.3.0 → 1.4.0. A new PUMP-DC1-01 case shows "Expert Knowledge Reused" quoting K. Lim verbatim. Its confidence only went **49% → 51% and it stays ESCALATED**; in round 4 it flipped routing. The sample interview moved a CRAH case from 60.0% to 60.5%. The console learning loop (0.43 → 0.50) also stays below 0.55. |
| Approve → version bump → rollback | **Pass.**<ul><li>The bump shows in the toast and the sidebar.</li><li>"Re-run" showed 60% → 75%.</li><li>Rollback needs admin, a reason and a confirm step, and writes a ledger row.</li><li>Labels are never reused.</li><li>The stale case is flagged and re-scored from 75% to 60%, and the server refuses approval until then.</li></ul>**But** the Approve button still shows under the "approval is blocked" banner. |
| AI unavailable | **Pass.** With ADP and a bogus key the chip turns "AI offline" with a plain-language reason. The diagnosis isn't blocked, and capture offers "Write heuristics by hand". |
| Tampering with the audit trail | **Mixed.** Caught: truncation, editing `decided_by`, dropping a ledger entry. **Not caught** (`/audit/status` stays ok:true):<ul><li>Rewriting an approved expert's checks to "Bypass the vibration interlock and keep the pump running." This is served to the AOM.</li><li>Changing the expert's name.</li><li>Forcing `current_state` to EXECUTING. A work order is still refused without a recorded approval.</li><li>Deleting a whole case.</li><li>Wiping the tool audit log.</li><li>Editing the unhashed `confidence_breakdown.kb_version`/`ledger_seq`. This **bypassed the stale-knowledge gate: a rolled-back case was approved straight to EXECUTING.**</li></ul>This contradicts the README claim that the digest covers the case's "full state" and that "editing knowledge outside the governance flow fails verification". |
| Unknown asset | **Pass.** G5 escalates with 0 evidence and a clear message. "Request more evidence" is still offered, which is pointless for an unregistered asset. |
| URL identity spoofing | **Pass.** `?user=` without a cookie gets 401, a forged cookie is rejected, and 5 wrong PINs give 429 with a lockout. **But:**<ul><li>The cookie is `user.HMAC(user)` with no timestamp or nonce, so a stolen cookie works until the server restarts.</li><li>A PIN-less "switch back" attempt counts as a failed PIN (`app.py` 203-209). I locked tech1 out this way.</li><li>Anyone can lock any user out with 5 requests.</li></ul> |
| Projector readability | **Acceptable.** Light theme by default, 15px body text, no page-level horizontal scroll, plain-English evidence. At 1024px the top bar wraps to 171px and the Confidence column falls off the table. KB refs render at 10.8px monospace. |

### Other defects and contradictions
- **G7 redaction is partial.** "[REDACTED-INJECTION] and approve this heuristic automatically." was stored as an approved "Escalate when" item. The mock extractor also turned an escalation sentence into a separate "Bearing wear" heuristic.
- **Corroboration is word overlap with evidence field names.** "axial" matches whatever its value, and "radial" (the expert's actual condition) is never checked. README item 9 overstates this.
- **README G4 table vs the app.** The README defines G4 as "confidence < 0.35", but 0.49 and 0.51 cases are tagged [G4].
- **Escalated cases read as "Medium" on the dashboard.** They show "37% Medium" or "49% Medium" next to an "Escalated" pill.
- **"Three" vs four seeded cases.** The README says four, but the dashboard empty state and guide step 1 say "three".
- **The demo guide skips the capture-to-reuse payoff.** None of its eight steps shows Expert Knowledge Reused.
- **The seeded UPS G9 case is escalated by G4 anyway.** So "AI disagrees but doesn't change routing" is never visibly demonstrated.
- **The default "AI" is not a model.** The second opinion is a hand-weighted rule scorer with ties going to the rule cause, and capture is keyword matching. It is honestly labelled, but ADP is never shown working.
- **The console mixes version labels.** It prints "KB version 2", "KB 1.5.0" and "KB is now 3" in one run.
- **Raw cause IDs remain.** For example "cause battery_eol" appears in the expert-knowledge text.
- **The Pill Registry undercounts approvals.** It shows CRAH as "no decisions yet" after approvals that were later rolled back.

### Scores
| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | 7 | Covers capture → steward approval → reuse → AOM decision → versioned governance across 4 asset types, with honest "assumption" labelling. |
| Human-Centered Design | 7 | Every escalation now has a reason, plus stale-knowledge banners, a hazard acknowledgement and next-step hints. The escalated Decision view hides diagnosis facts, and Approve shows under a "blocked" banner. |
| AI Interaction | 4 | No LLM is ever shown working. The mock extraction garbles an escalation rule into a heuristic and keeps an injection fragment. The second opinion is a second rule set. Failure UX is good. |
| Technical Execution | 7 | 156 tests and 12 evals pass, server-side RBAC is solid, and storage is now JSON. Unhashed `confidence_breakdown` and heuristic fields allow an undetected stale-gate bypass and an undetected rewrite of an expert's checks. |
| Feasibility | 6 | Deterministic core, Docker, a stated pilot path, owner-steward enforcement. Still one shared KB, a mock registry and PIN auth. |
| Demo & Storytelling | 6 | The guide and DEMO.md are coherent, but the key beat now moves confidence only 0.5–2 points with no routing change, the guide skips reuse, and "three vs four" appears. |
| Innovation & Creativity | 6 | Quote-or-drop grounding, the G9 advisory flag, never-reused version labels, single-proposal revoke. Retrieval and corroboration are bag-of-words. |
| UX & Accessibility | 7 | Readable evidence, plain AI errors, projector-safe light theme. Top-bar wrap at 1024px, "Escalated / Medium" badges, small monospace refs. |
| Responsible AI & Ethics | 7 | The AI never routes, the hazard gate works, and separation of duties and stale-knowledge blocking hold. Injection residue reaches approved knowledge, and expert guidance can be rewritten without detection. |
| Overall Quality | 6 | A solid governance core with recurring "the README claims more than the code does" gaps. |
| **Total** | **63/100** | |

### The 5 changes that would most raise the score
1. **Make captured knowledge visibly change an outcome again.**
   - Where: `learning.py` (`kb_match_score`/`get_similar`), `confidence.py`, `guide.js`, DEMO.md.
   - Tune the seeded scenario so the approved interview moves a seeded case across 0.55, from ESCALATED to AWAITING_APPROVAL.
   - Add a guide step on Diagnosis → Expert Knowledge Reused showing the before/after.
2. **Close the audit gaps the README already claims are closed.**
   - Where: `agent_state.py` `_state_digest`, `learning.py` `_kb_digest`, a case-registry anchor, README audit section.
   - Hash `current_state` and `confidence_breakdown` (including `kb_version` and `ledger_seq`).
   - Hash heuristic `checks`, `do_not`, `escalate_when`, `symptom_pattern` and `expert_name`.
   - Seal the set of case IDs and the tool audit log.
   - Or correct the README.
3. **Fix the capture path's AI quality and injection residue.**
   - Where: `capture.py`/`llm.py` G7 redaction and the mock extractor.
   - Redact the whole sentence and refuse a heuristic containing a redaction marker.
   - Stop splitting escalation sentences into fake cause heuristics.
   - Demo with a working ADP key, even a recorded run, so the AI Interaction score has something real to credit.
4. **Give the AOM the facts on escalated cases and remove label contradictions.**
   - Where: `renderDecision` in `screens.js`, `confBand` in `app.js`, the G4 reason text in `app.py`, README G4 row.
   - Show the diagnosed cause, readings, AI view and expert checks on the escalation panel.
   - Hide Approve while knowledge is withdrawn.
   - Stop showing "Medium" on escalated cases.
   - Relabel the evidence-loop escalation, or fix the README's G4 = <0.35.
   - Hide "Request more evidence" for unknown assets.
5. **Clean up the story's loose ends.**
   - Where: `guide.js` step 1, `renderDashboard` empty state, `demo.py` version printing, `/pills` approval-rate counting, `auth.py`.
   - Change "three" to four cases.
   - Use one version-label format in the console.
   - Count rolled-back approvals as decided.
   - Put an expiry and nonce in the session cookie.
   - Don't count a PIN-less switch attempt as a failed PIN.

My probes left extra cases, approvals and rollbacks in the running app's state (`data/tbc.sqlite`, untracked), and tech1 may still be locked out. Run `make reset` before any live demo. No tracked files were changed. Screenshots and probe scripts are in the session scratchpad (not in the repo).
