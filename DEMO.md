# 6-minute demo script

Before you start: `make reset && make serve`, open http://localhost:8000/ui.
The app opens as `mgr1 (Asset Ops Manager)`; switch roles with the "Acting
as" dropdown in the top bar — that's a real login (a signed session
cookie), not a URL trick, which is itself part of the story below.

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
cause-correction dropdown and the "Files under" pill chip. Click
**Submit for approval**.

## 4. Self-approval is blocked (30s)

**Say:** "Whoever captured it can't be the one who approves it."

**Do:** Switch role to **steward1** (the capturer), go to **Governance**.
Find the new proposal — its **Approve** button is disabled, with a note
explaining why.

## 5. A second steward approves (30s)

**Say:** "A different knowledge steward has to sign off."

**Do:** Switch role to **steward2**. Click **Approve**. Point at the KB
version bump in the toast and in the nav footer.

## 6. Diagnosis reuses that knowledge (45s)

**Say:** "That knowledge is now live — the next matching diagnosis finds
it automatically."

**Do:** Switch role to **tech1**. Seed or open a case whose diagnosed
cause matches what was just approved (the CRAH sensor-hardware-failure
case from Seed Demo Cases works). Open **Diagnosis**, scroll to
**Expert Knowledge Reused** — point out it names the expert, quotes
them verbatim, and that the deterministic tree stays authoritative
either way.

## 7. The AI second opinion is advisory only (45s)

**Say:** "A second, independent read on this diagnosis — it never
decides anything."

**Do:** On the same Diagnosis screen, scroll to **AI Second Opinion**.
Point at the "Advisory only — does not affect routing" tag, the
agree/disagree badge, and that it's grounded only in evidence actually
shown above it. If it ever disagrees, point at the G9 guardrail entry
further down and note the routing didn't change.

## 8. The AOM approves (45s)

**Say:** "A human — not the AI, not the decision tree — makes the call."

**Do:** Switch role to **mgr1**. Go to **AOM Decision**. Walk through
the recommendation, click **Approve** with a rationale.

## 9. Outcome and feedback (30s)

**Say:** "The loop closes: the fix gets recorded, and feeds back into
governance."

**Do:** Go to **Outcome**. Raise the work order, record the outcome as
resolved, submit feedback. Note this creates another pending proposal —
same governance loop as step 4.

## 10. Rollback (30s)

**Say:** "If approved knowledge turns out wrong, it's reversible — not
a one-way door."

**Do:** On **Governance**, note the current KB version, then (as
`admin1`) call `POST /kb/rollback/<version>` via the Pill Registry or
API docs at `/docs`, or just narrate: "every version is addressable;
rolling back removes exactly what was added after it, confidence
included — see `tests/test_confidence_uplift.py`."

## 11. Audit (30s)

**Say:** "Every step is in a tamper-evident hash chain."

**Do:** Scroll to **SHA-256 Audit Trace** on Governance. Click **Copy**
on a hash, point at **Audit Chain Valid**. Mention that changing any
past entry breaks every hash after it (`tests/test_no_contradictions.py`
and `EVAL-10` in `make eval` check this directly).

---

**If asked "is any of this real?"** — `make test` (pytest, currently 115
tests), `make eval` (12 labelled acceptance evals, pass/fail table), and
`make demo` (console walkthrough of the same scenarios, deterministic
output) all run with zero configuration. Nothing in this script requires
the Tencent Cloud ADP key; the default `mock` provider runs the same
flow offline, labelled as such in the UI.
