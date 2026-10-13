# Judge report 5: Technical Services Intelligence Pill (Keppel "AI HARVEST")

Branch `judge-fixes-v4` @ 2c99885. I judged the live app at http://localhost:8000/ui, which was freshly reset and running **Tencent Cloud ADP**. At first `/system/info` returned `llm_provider: adp, ai_status: ready, "no AI call yet"`. After my first ADP draft it reported online, and every ADP call I made succeeded.

I also started three scratch servers, each with its own `TBC_DB_PATH` and audit key under `scratchpad/judge5/`:
- :8011 used the mock provider, for the Modify, revoke and unsafe-capture probes.
- :8012 used the mock provider, for the tamper and restore probes.
- :8013 used ADP pointed at a dead endpoint, for the AI-offline check.

All three are stopped now. My scripts (`s01–s11.js`, `*.py`) and 26 screenshots are in `scratchpad/judge5/`. I modified no tracked file: `git status` lists the same four untracked judge reports before and after, plus this file.

**State I left :8000 in:**
- CHILLER-DC1-01 is CLOSED.
- Pump was rolled back to v1.3.0, so PUMP-DC1-01 has been re-scored and is ESCALATED at 46%.
- CRAH is at v1.5.0 (R. Tan's interview plus the seeded outcome feedback are approved).
- A sentinel-drill case is held, so the red Dashboard banner is showing.
- There is an extra tech1 CRAH case and a pending feedback proposal.

Run `make reset && make serve` before demoing.

## What I verified

| Probe | Result |
|---|---|
| `make test` | **387 passed**. README says 387; DEMO.md (L238) and HANDOFF.md still say 374. |
| `make eval` | **13/13 PASS** |
| `make demo` | **DEMO PASSED**, 5/5 scenarios, pump 0.49 → 0.60. `data/tbc.sqlite` had the same SHA-1 before and after, and no `tbc.tampered.*` files appeared, so the demo no longer touches the live DB. |
| DEMO.md beat 2 (capture, live ADP) | steward1 → Load sample → Draft: ADP returned a draft. The grounding card kept 9 lines and rejected "look at the calibration sticker" as "said in a different answer". "Tighten the terminal to 12 Nm." was rejected. With consent ticked, it was sent as PROP-B6A73A58 (5 heuristics: CRAH, Chiller, Pump). |
| Beat 4 (self-approval) | steward1's Approve is disabled: "You sent this. A different steward must decide." |
| Beat 5 (second steward) | steward2 tried Confirm without the safety tick and was refused ("Confirm the safety review…"). With the tick: "now live as CRAH v1.4.0, Chiller v1.4.0, Pump v1.4.0". UPS stayed at v1.3.0. Re-run: PUMP **49.0% → 60.5%** "now clears the 55%"; CRAH-DC1-02 and Chiller were unchanged. The age effect is shown separately ("readings have also aged 7.3 points" after about 12 minutes). |
| Beat 6 (reuse) | tech1 → New Case defaults to CRAH-DC1-01/SA-TEMP-01. Advance gave 67%. The Expert knowledge tab shows R. Tan, a verbatim quote, KB-EXP-B6A73A58-2, CRAH v1.4.0 and "steward2 (safety-reviewed)". The tab label reads "Evidence 1 abnormal" (**fix verified**). |
| Beat 7 (AI second opinion, live) | UPS-DC1-01 on ADP: `battery_eol, agrees_with_rules=true`. The guide (`guide.js` L8) now says "may disagree" (**fix verified**). DEMO.md L150 still says ADP "has a real reason to say the same" as the mock's "charger failure", but it didn't. The mock server *does* disagree (G9). |
| Request more evidence (live pump) | The button changes to "Gathering and re-diagnosing… (~15 s)" with `aria-busy=true` (**fix verified**). The case came back AWAITING_APPROVAL at **58%**, not 60.5%, because W4 staleness was 0.28 (see defect 3). The audit reason reads "mgr1 … more evidence requested: …" (**fix verified**). |
| Beat 8–9 (AOM, outcome) | Chiller approve was refused until the hazard was acknowledged, then approved. mgr1 raised WO-20261013-0646A9 and was told "You approved the work… Switch to tech1". tech1 recorded the outcome and sent feedback, and the case is CLOSED. |
| Rollback → blocked approval | admin1 rolled Pump back to v1.3.0. Approving or modifying the 58% pump case then returned 409 "Pump KB v1.4.0 was rolled back… re-score". After a re-score it was ESCALATED at 46%. |
| Sentinel drill (live) | Held in 11.7 s ("cites evidence the case does not have: vendor_portal_reading"). A technician's approval of the case returns 403. |
| Identity | `/me?user=mgr1` with no cookie returns 401. tech1's cookie plus `X-User: mgr1` plus `?user=mgr1` is still tech1. An admin approving knowledge gets 403. |
| AI offline (:8013) | Chip reads `offline`, "could not reach Tencent Cloud ADP (network error)". The second opinion reads "unavailable; the rule-based diagnosis remains authoritative". `/capture/draft` returns 502 with a plain message. Diagnosis was unaffected (UPS 58%). |
| **AOM Modify vs G1 (:8011)** | The report 4 phrasing ("Bypass the… interlock and raise the charger setpoint") is now **400 [G1]** (**fix verified**). "maintenance bypass and change the cells while the string is still energised" also returns 400. Six paraphrases went through to **EXECUTING** (see defect 1). One of them ("Put the high temperature cut out in override") then got **work order WO-20261013-877BBD**. |
| Modify kb_refs | Action-level `kb_refs=[]` (**fix partly verified**), but the recommendation-level `kb_refs` is still `['kb:…ups_tree:v1:Q2','KB-UPS1']` on every modified case (defect 1). |
| Modify inputs | `<label for=mod-type/mod-target/mod-detail>` are present (**fix verified**). |
| Revoke scope (:8011) | mgr1 captured the sample. steward1 signed CRAH, a second steward1 attempt was refused, and steward2 completed it. Revoke by steward1 → 403 "also covers Chiller, Pump"; by steward2 → 403 "also covers CRAH"; by admin with no reason → 409 "needs a reason" (**fix verified**). |
| Ledger restore (:8012), scenario A | I edited a pump heuristic's checks offline to "tie the vibration trip relay out…". On restart the ledger fails ("changed outside the governance flow after entry #5") and the red banner shows. auditor1 → **Restore last verified** in the UI asks for a reason, and the toast reads "ledger restored". The heuristic is back to the laser-alignment line and the ledger verifies with entry #6 recorded (**fix verified**). |
| Restore, scenario B (both snapshots edited) | 409 "the last verified knowledge snapshot no longer verifies either; accept or restore from an offline backup". Correct, but the only in-app option left is Accept, which re-signs the forgery. |
| Restore, scenarios C/D (replay an older signed snapshot) | **Not detected / silently truncates history** (defect 2). |
| Safety screen, report 4's misses | All five now return `defeats_safety=True` (**fix verified**). 15 of 29 paraphrases I tried still pass the hard screen (defect 4). |
| Layout | Body text is 16px. No page-level horizontal scroll at 1280, 1024 or 390. At 1024 the header takes 158 px (three rows), and the Dashboard ACTION column (Decide/Resolve) is clipped inside a scrolling table wrapper. |

## Defects and contradictions found (most serious first)

1. **AOM Modify's G1 is a keyword list that a paraphrase defeats, and the record then certifies "passed G1".** `app.py` L849–863 checks only `_is_banned_action` (`guardrails.py` L52: `setpoint|interlock|safety override|firmware|bms config`) plus `defeats_safety()`. It never calls `touches_protection()`, which the knowledge path uses as its deny-by-default backstop.
   - These went to EXECUTING on :8011:
     - "Raise the charger float voltage **set point** to 440 V" (the two-word "set point" doesn't match `\bsetpoint\b`)
     - "Inhibit the battery temperature alarm on the BMS until the new bank arrives" (also done through the UI, screenshot `08_modify_inhibit_alarm.png`)
     - "Change the battery breaker trip setting from 400 A to 630 A"
     - "Replace jars without isolating the string"
     - "Put the high temperature cut out in override", which produced work order WO-20261013-877BBD
     - "Acknowledge and suppress the battery temperature alarm"
   - Each one writes the audit note "written by the AOM, not from approved knowledge; **passed G1**" (L905). That is false assurance on exactly the actions G1 exists to stop.
   - The "cites no knowledge" claim (HANDOFF.md L32) is also only half true. L898–902 copies the original `Recommendation.kb_refs`/`evidence_refs` onto the modified recommendation ("preserving G8 grounding metadata"). The case record still says the AOM's hand-written action is grounded in `KB-UPS1`, and that is also why the sentinel's grounding check passes it.
2. **Ledger replay: an older *signed* knowledge snapshot is accepted as genuine, and "Restore" can be made to erase governance history.** The ledger seal covers only length and head, and it lives in the same `learning` blob (`learning.py` L252–261), so any older blob that verified on its own still verifies.
   - Scenario C (:8012): I replaced the `learning` key (and `learning_verified`) with the seed-time blob from a copy taken 30 s earlier. The server restarted with `audit/status ok: true`. The ledger went from 5 entries to 2, the approved interview vanished, the pills were back to v1.3.0, and there was **no banner and no integrity event**.
   - Scenario D: I forged the live heuristic and planted that older blob as `learning_verified`. Restore succeeded and silently dropped ledger entries #3–#5 (capture, sign-off, approval) and all approved heuristics. It also reset `_version_seq`, so labels will be reused, which contradicts "labels are never reused".
   - README L248–250 ("editing it too gains nothing") is true for *editing* but not for *replaying*. The Restore UI gives no preview of what will be discarded, such as how many ledger entries or proposals.
   - The fix: anchor the ledger head and length in the separately sealed `seals` key, or in each case's chain (cases already store `ledger_seq`), and show a diff before restoring (`persistence.py` L227–243, `app.py` L1845–1852).
3. **Re-anchoring the mock feed to "now" changed the seeded scores and duplicates evidence (a regression from 2e2d210).** `tools._as_live` gives every re-query a new `ts`, so the dedupe in `_advance` (`app.py` L536–547, keyed on `repr(payload)`) treats an identical reading as "new evidence".
   - CRAH-DC1-02 now holds **3 copies of the same absent SA-TEMP-02 reading** (7 items, "re-gathered 1 new evidence items" twice).
   - Its confidence rose from **36.6% to 41.6%**. I reproduced both numbers by seeding the code at 0e10864 and at HEAD side by side, so the commit message's "seeded scores are unchanged" is false.
   - Each phantom round is also one more ADP second-opinion call.
4. **Stale evidence is never refreshed, so the pump beat is time-bombed while the re-run card keeps promising 60%.** "Request more evidence" re-diagnoses with the evidence the case already holds and only adds items that differ (`app.py` L1938, L536). Pump evidence has no `ts`, so it ages against `retrieved_at` with a 60-minute SLA.
   - Live, 16 minutes after reset, the pump came back at 58% (staleness 0.28), not the 60.5% the card shows.
   - With the clock patched 40 minutes ahead (`stale_pump2.py`), the card still reads "49% → 60.5%… now clears the 55%; Request more evidence re-diagnoses it with this knowledge". Request more evidence then returns **ESCALATED at 53.8%** (staleness 0.67).
   - So if a presenter reaches DEMO.md beat 5's optional step more than about 35 minutes after `make reset`, it fails, and the card's advice is wrong.
5. **The hard safety screen still misses everyday paraphrases.** `safety.defeats_safety` returns False for:
   - "leave the ELR switched off until the vendor comes"
   - "isolate the VESDA detector so it stops going off"
   - "put the fire panel into disable mode for the shift"
   - "cover the smoke head with a bag while you work"
   - "weigh the float down with a brick"
   - "changing out the battery cells while the string is still energised"
   - "swap cells with the UPS still on line"
   - "set the high temp alarm to 60 C so it stops nagging"
   - "change the HP cutout setting from 26 bar to 30 bar"
   - "inhibit the alarm on the BMS"
   - "short pins 3 and 4"
   - "tell the BMS to ignore SA-TEMP-01"

   Some of these aren't caught by `touches_protection` either: "cover the smoke head with a bag", "tell the BMS to ignore SA-TEMP-01", "leave the ELR switched off", "fire panel into disable mode", "changing out the battery cells while… energised". End to end on :8011, a capture with "Cover the smoke head with a bag…" and "Tell the BMS to ignore SA-TEMP-01…" got `safety_review: []`. After one steward ticked the blanket safety box, it went live **not** as guidance only (`guidance_only: false`) and **raised** a new CRAH case from 60% to 67% (kb_match 0.40 → 0.68). The human tick is a real control, but it is a single blanket checkbox. The heuristic was not flagged, so the "never raises confidence" protection does not apply.
6. **No steward can withdraw a bad line from a mixed proposal.** Revoke is correctly scoped now, but for a CRAH+Chiller+Pump proposal both owners get 403. The message "its owning steward or an admin revokes it" (`app.py` L1553) is wrong, because the owning steward was just refused. Only admin1, whose role "cannot decide on knowledge", can act. There is no per-pill or per-heuristic revoke and no two-steward revoke.
7. **Ledger restore only covers part of the recovery.** When both snapshots are bad, the only in-app path is Accept, which re-signs the forgery as genuine. The 409 text tells the auditor to do exactly that or to use "an offline backup" that the app never makes. There is no hint about which fields changed.
8. Smaller issues:
   - The ledger table shows the raw `proposal_signed_off` action, because it is missing from `actionLabel` (`screens.js` L2060).
   - At 1024 px the Dashboard's Decide/Resolve buttons are clipped (the table is 771 px inside a 734 px wrapper), and the header wraps to three rows.
   - The capture card says "the expert's own sentence is used: 'If every tag on the bus…'", but the WHEN shown drops the "If".
   - The Expert-knowledge "Seen in this case's readings" match accepts the word "past".
   - The AOM hint "approve, reject or modify sends the case to execution" is wrong for Reject.
   - The seed docstring (`app.py` L1649) and DEMO.md L150 still promise a disagreement that live ADP does not give.
   - The KB digest still omits `proposed_cause` (known), and also `asset_id`, `corrected` and `confidence` on validated cases (`learning.py` L226–229).
   - DEMO.md and HANDOFF.md test counts are stale.

## Scores

| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | **8** | The full harvest loop works live on ADP: capture → grounded draft → per-pill second-steward approval → verbatim reuse with provenance → AOM decision → verified closure → rollback across 4 asset classes. It is still one mock site with static telemetry. |
| Human-Centered Design | **8** | Role-aware hints, reasons on every refusal, a busy state on slow ADP calls, an approver lock-out on verification, and hazard acknowledgement. Deductions: a misleading re-run card after time passes, a wrong revoke hint, and Reject described as "execution". |
| AI Interaction | **7** | Live ADP drafting with a visible grounding check (caught "said in a different answer") and clean offline degradation. On live ADP the second opinion agreed on all 7 diagnoses I saw, so G9 never fires in the real demo. |
| Technical Execution | **7** | 387 tests, 13/13 evals, the demo is now isolated from the live DB, and the restore and revoke fixes work. New regressions: duplicated evidence that inflates CRAH-DC1-02 by 5 points, evidence that never refreshes so outcomes drift with wall-clock time, ledger replay not detected, and Modify still copying kb_refs. |
| Feasibility | **7** | Clear seams (`tools.py` gatherers, ADP client, `/login`), and the keyed chains are a sound base. But state is SQLite JSON snapshots with in-blob seals, telemetry is mocked and re-timestamped, and safety relies on regex. |
| Demo & Storytelling | **8** | Every core DEMO.md beat reproduced in the UI on live ADP, and the guide no longer over-promises. The pump beat is time-sensitive (fails after about 35 minutes), and DEMO.md beat 7 still implies ADP sides with the charger. |
| Innovation & Creativity | **7** | Per-pill sign-off with stand-ins, "said in a different answer" grounding, withdrawn-knowledge blocking, a non-AI sentinel, and auditor restore. These are strong governance ideas; the AI's own role is modest. |
| UX & Accessibility | **7** | 16px base, labelled Modify inputs, aria-busy, no page-level horizontal scroll down to 390 px, and a dark theme. The Action column is clipped and the header takes three rows at 1024, the ledger shows a raw action label, and copy is dense. |
| Responsible AI & Ethics | **7** | Consent, grounding, blanket safety review, per-pill sign-off, scoped revoke, restore, and AI-offline honesty all work. Paraphrased interlock, alarm and trip changes still reach a work order through Modify, stamped "passed G1". Some protection-defeat lines aren't even flagged for review and can raise confidence. Ledger history can be rolled back by replay. |
| Overall Quality | **8** | Most claimed fixes hold when tested adversarially, and the build is coherent end to end. But two fix claims are overstated: "seeded scores unchanged" and "cites no knowledge". |

**Total: 74 / 100**

## The 5 changes that would most raise the score (ranked)

1. **Make Modify deny by default, and stop copying grounding onto it.** In `app.py` `post_approval` L849–905, run `touches_protection()` (and `_PROTECTION`) on the modified type, target and detail. Any hit should be refused, or routed to an escalation that a second person (steward or engineer) must clear. Normalise "set point", "set_point", "trip setting", "cut out", "inhibit", "suppress" and "override" in `guardrails._BANNED_PATTERN` (L52). Set `Recommendation.kb_refs=[]` for AOM-authored actions, and teach G8 and the sentinel that an `aom_authored` recommendation is grounded by the decision record, not by the KB. Change the note from "passed G1" to the specific checks that ran.
2. **Anchor the knowledge ledger outside its own blob.** In `persistence.py` (`seals` key, `save_state`, `load_state`), store the ledger length and head in the separately keyed `seals` record and cross-check them against the max `ledger_seq` referenced by cases. Restore should refuse a snapshot older than the anchored head, and the UI should preview what it would discard (entries, proposals, versions) (`app.py` L1845, Governance → Integrity Review in `screens.js`). Keep `_version_seq` monotonic across a restore.
3. **Fix the evidence-freshness regression.** In `tools._as_live` and the `_advance` dedupe (`app.py` L536–547), compare readings by their content without `ts`, and *replace* an older reading of the same source and type instead of appending it. Make "Request more evidence" re-gather before diagnosing (`app.py` L1938). That restores CRAH-DC1-02 to 36.6%, stops the phantom ADP calls, and makes the pump beat independent of how long the presenter talks. Add a test that seeds twice and asserts the evidence count and score.
4. **Second, independent safety layer on knowledge lines.** In `safety.py`, plus the approval queue in `screens.js` ~L1863: flag any line naming fire, VESDA, smoke, ELR/RCD, alarm, BMS "ignore", or live battery work for per-line review rather than one blanket checkbox. Never let an unflagged line containing those nouns raise `kb_match`. Optionally add a model pass that can only *add* flags. Add my 15 misses to `tests/test_safety_screen.py`.
5. **Give stewards a precise withdraw, and polish the demo path.** In `app.py` `revoke_proposal` L1532–1558 and `learning.revoke_proposal`, allow per-pill or per-heuristic revoke by that pill's owner, and fix the "owning steward" message. In `screens.js` L2060, label `proposal_signed_off`, and keep the Dashboard Action column visible at 1024 (pin it or move it left). Update DEMO.md L150/L238 and the seed docstring so the live-ADP second-opinion beat and the test counts match what a judge will see.
