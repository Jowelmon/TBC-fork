# Judge report 6: Technical Services Intelligence Pill (Keppel "AI HARVEST")

Branch `main` @ d08724b, the final check before the demo video. I judged the live app at http://localhost:8000/ui, which was freshly reset (server started 22:57) and running **Tencent Cloud ADP**. `/system/info` returned `llm_provider: adp, ai_status: online, "Tencent Cloud ADP replied"`, and every ADP call I made succeeded.

I also started three scratch servers. Each had its own `TBC_DB_PATH` and its own `TBC_AUDIT_KEY_FILE` under `scratchpad/judge6/`, so their anchors never touched `~/.tbc`:
- :8011 used the mock provider, for the Modify end-to-end probes and the CRAH re-read check.
- :8012 used the mock provider, for the anchor, replay, restore, crash and path-alias probes.
- :8013 used ADP pointed at a dead endpoint, for the AI-offline check.

All three are stopped now. My scripts, DB snapshots and screenshots are in `scratchpad/judge6/`. I modified no tracked file: `git status` shows the same five untracked judge reports, plus this file.

**State I left :8000 in.** I didn't reset it, so run `make reset && make serve` before recording.
- PROP-E9DC1FD8 (R. Tan) is approved: Chiller and Pump are at v1.4.0. admin1 then rolled CRAH back to v1.3.0.
- CHILLER-DC1-01 is CLOSED, with WO-20261013-789BF6 and pending feedback PROP-C26BC0CD.
- PUMP-DC1-01 is AWAITING_APPROVAL at 60.5%.
- There are three extra cases:
  - a tech1 CRAH case, CASE-b196a242. Its approval is blocked because its knowledge was withdrawn.
  - a tour pump case, CASE-f18bf746, at 60.5%.
  - a sentinel-drill case, CASE-a00cdf5a, which is held, so the red Dashboard banner is showing.

## What I verified

| Probe | Result |
|---|---|
| `make test` | **405 passed** (1 warning). README, DEMO.md L239 and HANDOFF.md all say 405 now (**fix verified**). |
| `make eval` | **13/13 PASS** |
| `make demo` | **DEMO PASSED**, 5/5 scenarios, pump 0.49 → 0.60. `data/tbc.sqlite` had the same SHA-1 before and after `make eval` and `make demo` (388803…), so the live DB is untouched. |
| Seed scores (claim 1) | After the fresh reset, CRAH-DC1-02 was at **36.6% with 5 evidence items**. Three "Request more evidence" calls on :8011 kept it at 36.6% / 5 items (**fix verified**; it was 41.6% with duplicate items in report 5). |
| Pump beat vs the clock (claim 1) | I patched the clock in every module (`stale_pump.py`). The re-run card still says 49% → 60.5%. **Request more evidence** gives **60.5% AWAITING_APPROVAL at +0, +40 min, +2 h and +24 h**: re-reading resets staleness from 0.67 to 0. Live on ADP, 6 minutes after reset, it was also 60.5%, with no duplicate evidence (**fix verified**). |
| Beat 1 | The Dashboard as mgr1 shows 6 seeded cases, and the AI chip reads "Tencent Cloud ADP". |
| Beat 2 (capture, live ADP) | The draft took **13.9 s**, with a "Drafting…" busy label. The grounding check kept 10 lines and rejected 1 ("look for an oil stain…" → "reworded: the expert said…"). The slip-in line "Tighten the terminal to 12 Nm." was rejected. It was sent as PROP-E9DC1FD8 with 5 heuristics. |
| Beats 4–5 | steward1 sees "You sent this. A different steward must decide." For steward2, Confirm without the tick is refused ("Confirm the safety review…"). With the tick: "now live as CRAH v1.4.0, Chiller v1.4.0, Pump v1.4.0", and UPS stays at v1.3.0. Re-run: **PUMP 49.0% → 60.5%** "now clears the 55%". CRAH-DC1-02 and Chiller are unchanged, and the ageing is shown separately. |
| Beat 6 | tech1 → New Case defaults to CRAH-DC1-01/SA-TEMP-01. Advance took 13.6 s with a busy label, and the case is at **67%**. The Expert knowledge tab shows R. Tan, a verbatim quote, KB-EXP-E9DC1FD8-2, CRAH v1.4.0 and "steward2 (safety-reviewed)". |
| Beat 7 (live ADP) | UPS-DC1-01: `battery_eol`, `agrees_with_rules=true`, with the charger listed as conflicting evidence. DEMO.md L151–156 now says ADP "usually agrees… rather than promise a disagreement" (**fix verified**). |
| Beats 8–9 | Chiller approve was refused until the hazard was acknowledged, then approved. mgr1 raised WO-20261013-789BF6 and was told "You approved the work… Switch to tech1". tech1 recorded the outcome and sent feedback, and the case is CLOSED. |
| Beat 10 | admin1 rolled CRAH back to v1.3.0 with a reason ("2 item(s) removed"). The footer updated, and the ledger shows entry #6. CASE-b196a242 then showed "Knowledge withdrawn… approval is blocked until the case is re-scored", with only Reject left. |
| Beat 11 | The sentinel drill took 10.6 s with a busy label: "stopped CASE-a00cdf5a… cites evidence the case does not have: vendor_portal_reading". The red Dashboard banner appeared, and auditor1 sees Release/Quarantine. |
| Ledger label (claim 4) | `proposal_signed_off` → "Signed off (one pill)" (`screens.js` L2063). On :8012, mgr1 captured and steward1 signed CRAH: status `awaiting_signoff`, with Chiller and Pump waiting for steward2 (**fix verified**). |
| Guided tour, 9 steps, literally | Steps 1–8 land correctly, with PIN prompts per role. Step 5 raises a fresh pump case at **61%** (ADP). **Step 9 shows the "Pill Summary and Governance" title but the previous step's AOM Decision content** (reproduced 2 of 2 times, with and without the PIN prompt; see defect 4). |
| Modify: type from catalogue (claim 2) | `#mod-type` is a `<select>` with 23 options. A type outside the catalogue (`alarm_management`) returns 400 [G1] (**verified**). |
| Modify: cites no knowledge (claim 2) | A modified case has `kb_refs=[]` on both the recommendation and the action (**fix verified**). The audit note still reads "…; **passed G1**" (`app.py` L908). |
| Modify: deny by default (claim 2) | **Partly true.** End to end on :8011, **9 harmful actions got work orders**, and the sentinel held none of them (defect 1). Live on :8000 the screen also refused an ordinary sensor replacement (defect 2). |
| Anchor: older DB replayed (claim 3) | On :8012 I put back a copy with ledger length 2 while the anchor said 5. Result: `ledger_problem: "an older copy… last recorded 5 ledger entries and the one loaded has 2"`, the red banner, and Integrity Review offers Accept or Restore. Restore returns **409** (**fix verified**). |
| Anchor: Restore after a live forge | Scenario A (forged heuristic): Restore works. Scenario D (forged live copy plus an older copy planted as `learning_verified`): **409, refused** (**fix verified**; this was silent truncation in report 5). |
| Anchor: auditor Accept, restarts, crash | Accept → ok. The anchor was rewritten (length 3), and the next restart was ok. Two plain restarts gave no events. A `kill -9` right after a capture, then restart: ok, no false alarm. `make reset` followed by start: no false alarm (the live server). |
| Anchor: replaying a case without changing the ledger | **Not detected** (defect 3). |
| Anchor: path alias | I started the same DB through a case-variant path (`…/JUDGE6/…` on case-insensitive APFS). A second anchor file appeared. Status `ok: true`, with only an `anchor_missing` integrity event and no banner. |
| AI offline (:8013) | The chip reads `offline`, "could not reach Tencent Cloud ADP (network error)". Every second opinion reads "unavailable; the rule-based diagnosis remains authoritative". `/capture/draft` returns 502 with a plain message. Scores are unchanged (CRAH-DC1-02 36.6%, pump 49%). |
| Safety screen, capture path | Known open. `defeats_safety` still passes the same paraphrases as report 5 ("leave the ELR switched off…", "cover the smoke head with a bag…", "tell the BMS to ignore SA-TEMP-01", "swap cells with the UPS still on line", …). |
| Layout | Body text is 16px. No page-level horizontal scroll at 1280, 1024 or 390. At 1024 the header is 158 px tall, and the Dashboard table is 788 px inside a 734 px wrapper, so Decide/Resolve is clipped (known). |

## Defects and contradictions found (most serious first)

1. **Modify's "deny by default" is still a keyword screen, and it treats any clause that starts like a prohibition as safe.**
   - `post_approval` (`app.py` L859–865) and the sentinel's "independent" re-check (`sentinel.py` L108–120) both call the same `needs_change_process` (`safety.py` L247). That function is `defeats_safety`, `touches_protection` and `_CONTROL_CHANGE`, each run over `_open_clauses`. `_open_clauses` (L188) **skips any clause matching `_PROHIBITION`** (L179): never, don't, do not.
   - On a work order, "Do not reinstate the trip" is not a prohibition. It is an instruction to leave a protection defeated.
   - These got **work orders** on :8011 (case → MONITORING_OUTCOME, `sentinel_hold=False`, note "passed G1"):
     - target `UPS-DC1-01.`, detail "Do not reinstate the battery high-temperature trip until the vendor arrives" → WO-20261013-720307. The full stop at the end of the target starts a new sentence, which then reads as a prohibition.
     - "Don't re-enable the battery temperature alarm until the new bank is in" → WO-…9679DD
     - "Don't isolate the string first; replace the jars now" → WO-…BD8B05
     - "Never isolate the string before changing the jars" → WO-…48BC98
     - "Swap the cells with the UPS still online" → WO-…857E3B
     - `sensor_recalibration` "Recalibrate with a -8 C offset so it reads normal" → WO-…599DDE
     - `config_remap` "Remap the battery temperature point to a fixed value of 22 C" → WO-…E3523C
     - Malay "Matikan penggera suhu bateri" ("turn off the battery temperature alarm") → WO-…37D04D
     - zero-width-space "byp​ass the inter​lock" → WO-…CB1437
   - Offline with the same function (`modify_probe.py`), **22 of 39** harmful wordings pass. Besides the above, these pass: "Raise the high temperature threshold to 60 C", "Lower the low-pressure cut-in to 0.5 bar", "Take SA-TEMP-01 offline in the BMS", "Throttle the discharge valve fully closed and run the pump", "Put the CRAH into service mode so it ignores high temp", and Chinese "旁路联锁并更换电池" ("bypass the interlock and replace the battery").
   - The catalogue is also global, not per asset: a UPS case can be modified to `laser_realign` or `refrigerant_topup` (`decision_tree.py` L128).
   - HANDOFF.md L35 says "Modify = … deny-by-default screen", and the commit says "citing nothing… deny by default". The second half is true. The first is a broader blocklist, not deny-by-default.
2. **The same screen over-blocks ordinary maintenance, including the agent's own wording.**
   - It refuses **9 of 16** benign actions (`modify_probe.py`):
     - "Inspect + replace starter/contactor." This is the decision tree's own `starter_replacement` text; refused with 400 on :8011.
     - "Replace the failed supply air temperature probe and confirm the alarm clears on the BMS". Refused **live on :8000 in the UI** on the hero CRAH case (screenshot `d08_modify_overblock.png`).
     - "Replace the thermistor…"
     - "Record the as-found settings…"
     - "Check vibration while running…"
     - "Replace the blown fuse with one of the same rating"
     - "Inspect the breaker…"
     - "Verify the chilled water setpoint reading…"
   - The refusal then tells the AOM to "Reject the recommendation and raise it through the site's engineering change process", for a like-for-like sensor swap.
   - So the regex is wrong in both directions: harmful wordings pass and benign ones are refused. A better design is a short allow-list of action templates per asset (type + target picked from the asset's components, free text only as a note), plus a refusal path that routes to a second approver rather than to "Reject".
3. **The anchor stops ledger and case-set rollback, but not rolling back a single case.**
   - `_write_anchor` (`persistence.py` L246) records only the ledger head and length plus the *set* of case ids, not each case's chain head.
   - On :8012 I copied the DB, then had mgr1 **reject** UPS-DC1-01 (CLOSED, 8 history entries), and then put the earlier copy back. After a restart the case is back at **AWAITING_APPROVAL with 7 entries**: `audit/status ok: true`, no integrity events, no banner. The rejection is gone, and the case can now be approved.
   - The same works for undoing a quarantine, an outcome, or a sentinel release that doesn't touch the ledger.
   - The claim "replaying an older signed DB fails verification" holds only when the ledger or the case set changed. The fix is to add `{case_id: chain_head, length}` to the anchor; cases already keep `chain_seal`.
   - Lesser issue: the anchor is keyed by the DB path string (`anchor_path` L220). A case-variant or moved path silently starts a new anchor, with only an `anchor_missing` event: the UI shows it in amber, worded as "tampered snapshot was archived", and status stays ok.
4. **Guided tour step 9 shows the wrong screen on camera.** `guide.js` L130 runs `await setRole(...)`, and `setRole` (`app.js` L258–269) calls `renderScreen()` for the *old* screen without waiting for it. `navigate('governance')` then starts its own render. The slower AOM Decision render (as auditor1) finishes last and overwrites `#content`. The result is a Governance title and nav highlight above the CHILLER AOM Decision card. Reproduced 2 of 2 times.
5. **Known items still open.**
   - The capture safety screen misses the same paraphrases. Some, such as "cover the smoke head", "tell the BMS to ignore…" and "leave the ELR switched off", aren't flagged for review at all, so they can raise confidence after one blanket tick.
   - No steward can withdraw a single line from a mixed-pill proposal.
   - When both snapshots are bad, Accept re-signs a forgery, and the 409 points to an "offline backup" the app never makes.
   - `proposed_cause` is missing from the KB digest.
6. Smaller issues:
   - The AOM hint "approve, reject or modify sends the case to execution" (`screens.js` L1062) still shows above "Knowledge withdrawn… Approve and Modify return once the case is re-scored". It is also wrong for Reject.
   - The capture card says "the expert's own sentence is used: 'If every tag…'" but shows WHEN without the "If".
   - The "Seen in this case's readings" match still counts the word "past".
   - The Modify audit note still says "passed G1" (`app.py` L908).
   - DEMO.md beat 3 and tour step 2 tell the presenter to "toggle one off"/"untick one heuristic". If that one is the pump or CRAH-sensor heuristic, beats 5–6 fail without explanation.
   - Tour step 5 waits on ADP (create + advance) with no busy indication on the guide button.

## Scores

| Criterion | Score | Evidence |
|---|---|---|
| Impact & Relevance | **8** | The full harvest loop works live on ADP: interview → grounded draft → second steward per pill → verbatim reuse with provenance → AOM decision → verified closure → rollback, across 4 asset classes. It is still one mock site with static telemetry. |
| Human-Centered Design | **8** | Busy labels on every slow ADP action (draft, advance, more evidence, drill). Reasons on every refusal, approver lock-out on verification, hazard acknowledgement. Deductions: the AOM can't write an ordinary sensor or contactor replacement and is told to use an engineering change process; the stale "sends to execution" hint. |
| AI Interaction | **7** | Live ADP drafting with a visible, convincing grounding check (rewording caught), and clean offline degradation. On live ADP the second opinion agreed every time, so the G9 story is only told, not shown. |
| Technical Execution | **8** | 405 tests, 13/13 evals, demo isolated. Both report-5 regressions are really fixed: seed scores back, and the pump beat is stable to +24 h. Ledger replay and planted-restore are detected, with no false alarms on restart, crash or reset. Gaps: replaying a single case is undetected, and the anchor is keyed by path. |
| Feasibility | **7** | Clean seams (`tools.py` gatherers, ADP client, `/login`) and an anchor outside the DB. But state is SQLite JSON snapshots, telemetry is mocked, and both safety layers and the "independent" sentinel share one regex. |
| Demo & Storytelling | **8** | Every DEMO.md beat reproduced on live ADP in about 10 minutes. The pump beat no longer depends on when it's run, and DEMO.md is honest about ADP agreeing. Tour step 9 shows the wrong screen, and the "untick one" advice is a trap. |
| Innovation & Creativity | **7** | Per-pill sign-off with stand-ins, "said in a different answer" grounding, withdrawn-knowledge blocking, a non-AI sentinel, and a signed anchor outside the DB. These are strong governance ideas; the AI's own role is modest. |
| UX & Accessibility | **7** | 16px base, a labelled Modify `<select>`, aria-busy, no page-level horizontal scroll down to 390 px. The Action column is still clipped and the header takes three rows at 1024. Copy is dense, and the tour has a render race. |
| Responsible AI & Ethics | **7** | Consent, grounding, the hard capture screen plus per-pill review, scoped revoke, restore, rollback protection, and AI-offline honesty all work. But "Do not reinstate the battery high-temperature trip", Malay or zero-width wording, and live jar swaps still reach a work order stamped "passed G1", while legitimate repairs are refused. |
| Overall Quality | **8** | Claims 1, 3 (ledger part) and 4 hold under adversarial testing. Claim 2 is half true: it cites no knowledge, but it is not deny-by-default. The build is coherent end to end on live ADP. |

**Total: 75 / 100**

## The 5 changes that would most raise the score (ranked)

1. **Replace Modify's free text with structured, per-asset templates.** In `app.py` `post_approval` L838–875 and the Decision screen `screens.js` (`#mod-*`):
   - pick type → target from the asset's own components (from `mock_registry`) → a template detail;
   - keep free text as a note that never reaches the work order;
   - filter `ACTION_TYPES` by asset.
   If free text stays, at minimum stop `_open_clauses` from exempting "prohibitions" for work-order text (a WO line is never a prohibition), normalise Unicode (NFKC plus stripping zero-width characters), and refuse non-ASCII-only text or send it to a second approver. Change "passed G1" to name the checks that ran.
2. **Anchor each case's chain head.** In `persistence._write_anchor` L246 and `load_state` L343, store `{case_id: [len(history), chain_seal]}` and flag any case that is shorter than, or diverges from, its anchored head, the same way as the ledger. Key the anchor by a DB identity stored inside the DB (a random id written at seed time), not by the path string.
3. **Fix the tour render race.** In `app.js` `setRole` L258, return without re-rendering when the caller is about to navigate (for example `setRole(role, {render:false})` from `guide.js` L130), or have `renderScreen` drop stale renders with a sequence token. Add a busy state to the guide button while step 5 raises and advances its case.
4. **Make the AOM's refusal useful.** When Modify is refused, offer "Send to a second approver (engineer/steward)" instead of "Reject…". Fix the false positives (probe, thermistor, contactor, same-rating fuse, "as-found settings", "while running") with tests in `tests/test_modify_change_process.py`.
5. **Close the known knowledge-path gaps.** Add report 5's 15 capture misses to `tests/test_safety_screen.py` and flag the nouns (smoke, VESDA, ELR, fire panel, BMS "ignore", live cells) for per-line review. Allow a revoke per pill or per heuristic by that pill's owner. Pin the Dashboard Action column at 1024.

## Demo recording checklist

- **Reset first:** `make reset && make serve`. My probes left :8000 with a held sentinel case (red banner), CRAH rolled back, and Pump/Chiller at v1.4.0.
- **Warm ADP once** (draft any interview, then reset or ignore it). Expect about 14 s for a draft, about 14 s for Advance, about 10 s for the drill, and a few seconds for Request more evidence. All of them show busy labels, so narrate over them.
- **At capture, don't untick the pump (Shaft misalignment) or CRAH Sensor-hardware heuristic.** Beats 5–6 depend on them. If you show the toggle, untick "Condenser fouling" and tick it back, or leave all five on.
- The capture card's "expert's own sentence: 'If every tag…'" sits above a WHEN without the "If". Don't zoom in on it.
- Beat 5: re-run PUMP-DC1-01 and point at **49.0% → 60.5%**. The optional "Request more evidence" lands at **60.5%** whenever you run it. Type a reason in "Reason or resolution" first, or you'll get a toast.
- Beat 7: ADP will **agree** (battery end of life). Point at the charger as conflicting evidence, as DEMO.md now says. Don't promise a G9 disagreement.
- **Don't demo Modify with realistic repair wording.** "Replace the … probe" or "… contactor" is refused with "use the engineering change process". If you show Modify, use plain text such as type `sensor_replacement`, target "SA-TEMP-01", detail "Replace sensor and log it". Or show the refusal of "bypass the interlock" instead.
- **Guided tour step 9 shows stale content.** After clicking Next to step 9, click **Governance** in the nav (or "Go to this step" again) before talking. Step 8 lands on a closed chiller case if you already did DEMO.md beat 8.
- Record at **≥1280 px wide**. At 1024 the Dashboard Decide/Resolve column is clipped and the header wraps to three rows.
- Do the sentinel drill **last** (or release it as auditor1). It leaves a red banner on every screen afterwards.
- The AOM Decision hint "approve, reject or modify sends the case to execution" also appears on the knowledge-withdrawn case in beat 10. Read the withdrawn banner, not the hint.
