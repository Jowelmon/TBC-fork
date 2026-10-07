# 6-minute demo script

Before you start: `make reset && make serve`, open http://localhost:8000/ui.
The server seeds five demo cases (recorded as `demo-seed`). The app opens
as `mgr1 (Asset Ops Manager)` and asks for that user's PIN; switch roles
with the "Acting as" dropdown in the top bar. Each switch is a real login
(PIN checked, signed session cookie), not a URL trick, which is itself part
of the story below. A PIN is asked for the first time you switch to a role;
switching back to it later needs no PIN. Five wrong PINs lock that user out
for five minutes.

**Demo PINs** (replace with `TBC_LOGIN_PINS` on any real deployment):

| User | Role | PIN |
|---|---|---|
| tech1 | Technician | 1111 |
| mgr1 | Asset Ops Manager | 2222 |
| steward1 | Knowledge Steward | 3333 |
| steward2 | Knowledge Steward | 4444 |
| auditor1 | Auditor | 5555 |
| admin1 | Admin | 9999 |

Every beat below is something you click, not something you claim.

## 1. The problem (30s)

**Say:** "An experienced technician's judgement about what a fault means
is tribal knowledge. When they're unavailable, that knowledge doesn't
exist for anyone else."

**Do:** On the Dashboard, open the **Why this exists** panel. Point at
the *problem* and *users* lines — and at the explicitly labelled
*assumption* in the value line: nothing here is presented as Keppel data
that isn't.

## 2. Capture an expert interview (45s)

**Say:** "Here's how undocumented expertise gets captured."

**Do:** Go to **Capture**. Click **Load sample interview**, then
**Draft knowledge with AI**. Point at the step tracker — this is an AI
draft, clearly labelled, nothing live yet.

## 3. Review before it's sent (45s)

**Say:** "The AI drafts; a human reviews every item before it goes
anywhere."

**Do:** Walk through the reviewed heuristics — toggle one off, note the
cause-correction dropdown and the "Files under" pill chip. Every check,
"never" and "escalate when" line is the expert's own words from the same
answer; anything else, or anything telling someone to bypass a safety
device, is dropped with a note. Tick the consent box (the expert agreed to
their words being reused) and click **Send for steward approval**.

## 4. Self-approval is blocked (30s)

**Say:** "Whoever captured it can't be the one who approves it."

**Do:** Switch role to **steward1** (the capturer), go to **Governance**.
Find the new proposal — its **Approve** button is disabled, with a note
explaining why.

## 5. A second steward approves (30s)

**Say:** "A different knowledge steward has to sign off."

**Do:** Switch role to **steward2**. The queue shows every line of every
heuristic, exactly as the AOM will see it. Click **Approve…**, say why it is
sound (recorded in the ledger), and confirm. Point at the KB
version bump in the toast and in the nav footer. In **Re-run Diagnosis on
Similar Open Cases**, re-run the seeded **PUMP-DC1-01** case: 49% becomes
about 65%, past the 55% recommendation threshold, because R. Tan's pump
answer is now approved knowledge and the case's evidence shows what he
described.

## 6. Diagnosis reuses that knowledge (45s)

**Say:** "That knowledge is now live — the next matching diagnosis finds
it automatically."

**Do:** Switch role to **tech1**. Click **New Case**, keep CRAH-DC1-01,
**Create Case**, then **Advance** (sensor hardware failure, the cause just
approved). Open **Diagnosis**, scroll to
**Expert Knowledge Reused** — point out it names the expert, quotes
them verbatim, and that the deterministic tree stays authoritative
either way.

## 7. The AI second opinion is advisory only (45s)

**Say:** "A second, independent read on this diagnosis — it never
decides anything."

**Do:** On the same Diagnosis screen, scroll to **AI Second Opinion**.
Point at the "Advisory only — does not affect routing" tag, the
agree/disagree badge, and that it's grounded only in evidence actually
shown above it. Then open the seeded **UPS-DC1-02** case: the rules say
battery end of life, the AI flags thermal runaway risk (41°C and rising),
and G9 records the disagreement. The case still goes to the AOM for
approval: the AI informs the decision, it never makes or blocks it. The
cloud in the corner shows the AI's state on every screen: it is worried on
this case, smiles when Tencent Cloud ADP is answering, and can be dragged
out of the way.

## 8. The AOM approves (45s)

**Say:** "A human — not the AI, not the decision tree — makes the call."

**Do:** Switch role to **mgr1**. Go to **AOM Decision**. Point at what
the AOM sees before deciding: the diagnosed cause, confidence, the
readings behind it, the AI's advisory view, and the approved expert's
checks and cautions. Click **Approve**: a rationale is required. On the
chiller case the safety-hazard banner also needs an explicit
acknowledgement before approval goes through.

## 9. Outcome and feedback (30s)

**Say:** "The loop closes: the fix gets recorded, and feeds back into
governance."

**Do:** Go to **Outcome**. Raise the work order, record the outcome as
resolved (the verifier is your signed-in identity, not a text box), submit
feedback. Note this creates another pending proposal — same governance
loop as step 4. Once the case closes, the feedback form disappears: feedback
is accepted exactly once.

**Optional (escalations teach too):** open the ESCALATED CRAH-DC1-02 case
on **AOM Decision**, enter a resolution (e.g. "BMS vendor replaced
CTL-02"), pick the confirmed cause, and close it. The resolution lands in
the stewards' queue as an *Escalation resolution* proposal.

## 10. Rollback (30s)

**Say:** "If approved knowledge turns out wrong, it's reversible — not
a one-way door."

**Do:** Switch to **admin1**. On **Governance**, the **Rollback** panel
shows every version: current, live, and rolled back. Show **Approved Knowledge**: any single proposal can be revoked with a
reason, without touching the rest. Then pick an earlier version, type a
reason, click **Roll back…** and confirm. Open a case that was scored with
the withdrawn knowledge: AOM Decision now blocks approval until it is
re-scored. Point at the new
**Knowledge Governance Ledger** row (actor, reason, version from → to), and
note that the next approval gets a brand-new label: labels are never
reused.

## 11. Audit (30s)

**Say:** "Every step, and every knowledge decision, is in a keyed,
tamper-evident hash chain."

**Do:** On Governance, point at **Ledger verified** and the **Case Audit
Trace**. Changing any past entry breaks every hash after it, and
re-hashing the whole chain does not help without the audit key
(`tests/test_judge_round3_fixes.py`). A case whose chain fails is frozen
and a red banner appears on the Dashboard for everyone.

---

**If asked "is any of this real?"** — `make test` (pytest, currently 189
tests), `make eval` (12 labelled acceptance evals, pass/fail table), and
`make demo` (console walkthrough of the same scenarios, deterministic
output) all run with zero configuration. Nothing in this script requires
the Tencent Cloud ADP key; the default `mock` provider runs the same
flow offline, labelled as such in the UI.
