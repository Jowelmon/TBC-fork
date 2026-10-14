# Demo script

**Short version (6 minutes, 6 beats):** 2 capture → 4 self-approval blocked
→ 5 second steward approves and the pump case clears 55% → 6 the next
diagnosis quotes the expert → 8 the AOM approves → 10 rollback. Everything
else below is optional depth for questions.

Before presenting, warm the AI up once (draft any interview on Capture):
Tencent Cloud ADP takes 10–15 s per call. If it fails, the screen says so,
and the offline path (`TBC_LLM_PROVIDER=mock`) runs the same script.

## Logins (demo PINs, the app's passwords)

| User | Role | PIN |
|---|---|---|
| `tech1` | Technician | **1111** |
| `mgr1` | Asset Ops Manager | **2222** |
| `steward1` | Knowledge Steward (owns CRAH, UPS) | **3333** |
| `steward2` | Knowledge Steward (owns Chiller, Pump) | **4444** |
| `auditor1` | Auditor | **5555** |
| `admin1` | Admin | **9999** |

These are demo defaults; set `TBC_LOGIN_PINS="tech1:....,mgr1:...."` to
replace them on any real deployment.

## Setup

Before you start: `make reset && make serve`, open http://localhost:8000/ui.
The server seeds six demo cases (recorded as `demo-seed`). The app opens
as `mgr1 (Asset Ops Manager)` and asks for that user's PIN; switch roles
with the "Acting as" dropdown in the top bar. Each switch is a real login
(PIN checked, signed session cookie), not a URL trick, which is itself part
of the story below. A PIN is asked for the first time you switch to a role;
switching back to it later needs no PIN. Five wrong PINs lock that user out
for five minutes.

Every beat below is something you click, not something you claim.

## 1. The problem (30s)

**Say:** "An experienced technician's judgement about what a fault means
is tribal knowledge. When they're unavailable, that knowledge doesn't
exist for anyone else."

**Do:** On the Dashboard, open **How this pill works** below the case table and point
at the strip: Tencent Cloud ADP supplies the AI, TBC governs what that AI may do (grounding,
safety screen, guardrails, RBAC, sentinel), the decision tree diagnoses,
and a person approves. In the same card, open **Illustrative value** and change the numbers.
It is labelled "Illustrative scenario — not Keppel actuals": every figure
is an input, and the formula is shown.

## 2. Capture an expert interview (45s)

**Say:** "Here's how undocumented expertise gets captured."

**Do:** Switch role to **steward1** (PIN 3333): steward1 is the capturer
from here to step 4. Go to **Capture**. Click **Load sample interview**, then
**Draft knowledge with AI**. Point at the step tracker — this is an AI
draft, clearly labelled, nothing live yet.

**Say:** "And when the AI makes something up?"

**Do:** Point at the **Grounding check** card. With Tencent Cloud ADP it
usually shows lines the model reworded, marked ✗ "reworded: the expert
said …" next to the expert's real sentence, or lines it added, marked ✗ "no
source found in the transcript". Then use **Try to slip in a line the expert never
said**: "Tighten the terminal to 12 Nm." is rejected. The same check runs
again on the server when the draft is sent, so it cannot become knowledge.

## 3. Review before it's sent (45s)

**Say:** "The AI drafts; a human reviews every item before it goes
anywhere."

**Do:** Walk through the reviewed heuristics — you can toggle one off, but keep the
pump "shaft misalignment" and CRAH "sensor hardware failure" ones (beats 5 and 6
reuse them) — note the
cause-correction dropdown and the "Files under" pill chip. Every check,
"never" and "escalate when" line is the expert's own words from the same
answer; anything else, or anything telling someone to bypass a safety
device, is dropped with a note. Tick the consent box (the expert agreed to
their words being reused) and click **Send for steward approval**. What is
stored is exactly what is on screen: if the server's re-check would change
any wording, nothing is sent and the re-checked text comes back to review.
The sent card says so: "exactly what the steward will see".

## 4. Self-approval is blocked (30s)

**Say:** "Whoever captured it can't be the one who approves it."

**Do:** Still as **steward1** (the capturer), go to **Governance**: it opens
on **Approval queue**. Find the new proposal: its **Approve** button is
disabled, with the note "You sent this. A different steward must decide."

## 5. A second steward approves (30s)

**Say:** "A different knowledge steward has to sign off."

**Do:** Switch role to **steward2** (PIN 4444). The queue shows every line of every
heuristic, exactly as the AOM will see it. Knowledge is decided pill by
pill: steward2 owns Chiller and Pump, and stands in for CRAH because its
owner, steward1, proposed it, so steward2 can approve the whole interview.
(Had **mgr1** captured it, steward1 would sign off CRAH and the proposal
would stay pending, showing "Chiller · waiting for steward2", until
steward2 signed the rest.) Click **Approve…** and say why
it is sound (recorded in the ledger). Try to confirm without ticking the
safety review: it is refused, because every check an expert gives is an
action on equipment and a person must confirm none of them defeats a
protection. Tick it and confirm. The chiller answer mentions a trip, so its
card says **Protective device or work on equipment**: that heuristic goes
live as guidance only and never raises confidence. Point at the version bump in
the toast and in the nav footer: the interview covers CRAH, Chiller and
Pump, so those three pills move and UPS does not. In **Re-run Diagnosis on
Similar Open Cases**, re-run the seeded **PUMP-DC1-01** case: 49% becomes
about 60%, past the 55% recommendation threshold, because R. Tan's pump
answer is now approved knowledge and the case's evidence shows what he
described. The figure is the knowledge's effect alone: every other term is
held as it was when the case was scored, and any ageing of the readings is
shown separately. (Optional: as **mgr1** on AOM Decision, **Request more
evidence** on that escalated pump case; it is re-diagnosed at once and goes
to Awaiting approval.)

## 6. Diagnosis reuses that knowledge (45s)

**Say:** "That knowledge is now live — the next matching diagnosis finds
it automatically."

**Do:** Switch role to **tech1** (PIN 1111). Click **New Case**: it opens on
CRAH-DC1-01 with sensor SA-TEMP-01 (the sensor list only offers that
asset's own sensors). Click **Create Case**; the new case opens on
**Diagnosis**. Click **Advance Agent** (sensor hardware failure, the cause just
approved). Each case screen shows one group of cards
at a time, in tabs. **Summary** gives the cause, confidence, AI view,
recommendation and abnormal readings; **Evidence**, **AI second opinion**,
**Expert knowledge** and **Scoring** hold the detail. Open the **Expert
knowledge** tab — point out it names the expert, quotes
them verbatim, and that the deterministic tree stays authoritative
either way.

## 7. The AI second opinion is advisory only (45s)

**Say:** "A second, independent read on this diagnosis — it never
decides anything."

**Do:** On the same Diagnosis screen, open the **AI second opinion** tab.
Point at the "Advisory only — does not affect routing" tag, the
agree/disagree badge, and that it's grounded only in evidence actually
shown above it. Then open the seeded **UPS-DC1-01** case. The evidence
genuinely conflicts: the bank is past its five-year design life, so the
rules say battery end of life (replace the bank), but the charger has
failed with no charge current, which on its own explains a low battery.
Read out what the second opinion says. The offline mock says "charger
failure"; on Tencent Cloud ADP it usually agrees with the rules, so point
at the evidence it lists as conflicting and what it says would help,
rather than promise a disagreement. When it does disagree, that is recorded as **G9** and the
case still goes to the AOM: the AI informs the decision, it never makes or
blocks it. The AOM can **Modify** the action by picking another of the procedures this fault's tree can recommend; no typed text reaches the work order.

For contrast, open **UPS-DC1-02**: cells at 41 °C and still rising. Safety
comes first in the rules, not the AI: the tree diagnoses thermal runaway
risk, **G2** escalates it to a person (isolate the bank, keep people clear),
and **G2b** names the hazard. No work order can be approved from it.
Cloudy, the cloud in the navigation rail, shows the AI's state on every
screen (worried on this case, smiling when Tencent Cloud ADP is
answering). Click it for the assistant panel: the live model, what the AI
does on this screen and what it may not do, and shortcuts. Drag it
anywhere.

## 8. The AOM approves (45s)

**Say:** "A human — not the AI, not the decision tree — makes the call."

**Do:** Switch role to **mgr1**. Go to **AOM Decision**. Point at what
the AOM sees before deciding: the diagnosed cause, confidence, the
readings behind it, the AI's advisory view, and the approved expert's
checks and cautions. Click **Approve**: a rationale is required. On the
chiller case the safety-hazard banner also needs an explicit
acknowledgement before approval goes through. The Dashboard's Action column
gives the AOM a **Decide** button on each case waiting for them.

## 9. Outcome and feedback (30s)

**Say:** "The loop closes: the fix gets recorded, and feeds back into
governance."

**Do:** Still as **mgr1**, go to **Outcome** and raise the work order. The
outcome form is not offered to mgr1: whoever approved the work cannot also
certify that it worked. Switch to **tech1**: record the outcome as resolved
(the verifier is your signed-in identity, not a text box), then under
**What did you find?** send feedback to the stewards. Note this creates
another pending proposal — same governance loop as step 4. Once the case closes, the feedback form disappears: feedback
is accepted exactly once.

**Optional (escalations teach too):** open the ESCALATED CRAH-DC1-02 case
on **AOM Decision**, enter a resolution (e.g. "BMS vendor replaced
CTL-02"), pick the confirmed cause, and close it. The resolution lands in
the stewards' queue as an *Escalation resolution* proposal.

## 10. Rollback (30s)

**Say:** "If approved knowledge turns out wrong, it's reversible — not
a one-way door."

**Do:** Switch to **admin1**. On **Governance** → **Approved & versions**, the **Rollback** panel
works one pill at a time: pick **CRAH** and it shows every CRAH version
(current, live and rolled back). Rolling CRAH back leaves the Chiller, UPS
and Pump knowledge exactly as it was; the footer shows each pill's version. Show **Approved Knowledge**: any single proposal can be revoked with a
reason, without touching the rest. Then pick an earlier version, type a
reason, click **Ask for rollback…** and confirm. Nothing changes yet: the
CRAH steward (**steward1**) sees the request with what it would remove, and
countersigns it. Only then is the ledger entry written with both names. Open a case that was scored with
the withdrawn knowledge: AOM Decision now blocks approval until it is
re-scored. Point at the new
**Knowledge Governance Ledger** row (actor, reason, and which pill moved from which version to which), and
note that the next approval gets a brand-new label: labels are never
reused.

## 11. Audit (30s)

**Say:** "Every step, and every knowledge decision, is in a keyed,
tamper-evident hash chain."

**Do:** On Governance → **Audit & sentinel**, point at **Ledger verified** and the **Case Audit
Trace**. Changing any past entry breaks every hash after it, and
re-hashing the whole chain does not help without the audit key
(`tests/test_governance_integrity.py`). A case whose chain fails is frozen,
its controls are hidden, and a red banner appears on the Dashboard for
everyone. Switch to **auditor1**: Governance shows **Integrity Review**,
where the auditor accepts a record as genuine or quarantines a case, with a
reason that is written to the chain and the ledger.

**Say:** "Who watches the system that's making these decisions?"

**Do:** As **admin1**, on Governance click **Run a sentinel drill** in the
**Sentinel** card. It creates a case and plays a defective tool that cites
evidence the case never gathered. The sentinel stops the case, writes why
on its audit trail, keeps what it saw, and raises the Dashboard alert. The
case's controls are gone. Switch to **auditor1** to release or quarantine
it with a reason.

---

**If asked "is any of this real?"** — `make test` (pytest, currently 571
tests), `make eval` (13 labelled acceptance evals, pass/fail table), and
`make demo` (console walkthrough of the same scenarios, deterministic
output) all run with zero configuration. Nothing in this script requires
the Tencent Cloud ADP key; the default `mock` provider runs the same
flow offline, labelled as such in the UI.
