# Technical Services Fault Diagnosis Intelligence Pill

An audit-ready agent that diagnoses faults on critical data-centre assets
(CRAH units, chillers, UPS, pumps) and captures the know-how of experienced
technicians so it outlives them. Built for the Keppel **AI HARVEST** hackathon.

> **AI in the harvest, determinism in the execution.** A model turns expert
> interviews into draft knowledge and gives an advisory second opinion, but
> nothing it drafts goes live until a second knowledge steward approves it.
> Diagnosis itself is deterministic: the same observation and evidence always
> give the same diagnosis, recommendation and guardrail verdict.

## Quick start

```bash
make install    # creates .venv and installs requirements (Python 3.11+)
make serve      # API + UI on http://localhost:8000/ui
```

Sign in with a demo PIN (replace them with `TBC_LOGIN_PINS` on any real
deployment):

| User | Role | PIN |
|---|---|---|
| `tech1` | Technician | 1111 |
| `mgr1` | Asset Ops Manager | 2222 |
| `steward1` | Knowledge Steward (owns CRAH, UPS) | 3333 |
| `steward2` | Knowledge Steward (owns Chiller, Pump) | 4444 |
| `auditor1` | Auditor | 5555 |
| `admin1` | Admin | 9999 |

On first start the server seeds five scenarios (attributed to `demo-seed`):
a closed case, a bus fault escalated to the BMS pill, a chiller awaiting
approval, a UPS where the AI second opinion disagrees with the rules, and a
pump escalated at 49% that clears the 55% threshold once the sample expert
interview is approved. Click **Demo guide** in the top bar for a guided tour,
or follow [`DEMO.md`](DEMO.md) for a 6-minute scripted run.

No key is needed: the default `mock` provider runs offline. To use Tencent
Cloud ADP, `cp .env.example .env`, set `TBC_LLM_PROVIDER=adp` and paste your
AppKey into `ADP_APP_KEY` (see [`docs/ADP_SETUP.md`](docs/ADP_SETUP.md)).

| Command | What it does |
|---|---|
| `make test` | pytest suite (314 tests) |
| `make eval` | 12 labelled acceptance evals as a pass/fail table |
| `make demo` | console walkthrough of the same scenarios, including capture → approval → reuse |
| `make reset` | stop the server and wipe saved state for a clean demo |
| `make docker-up` / `make docker-down` | run the app in Docker on `:8000` |

State is saved to `data/tbc.sqlite` after every change and restored on
start, with every audit chain re-verified on load (`TBC_PERSIST=0` keeps it
in memory). Swagger docs are at `/docs`.

## How it works

```
observation ─▶ gather evidence ─▶ decision tree ─▶ confidence (W1-W5)
            ─▶ guardrails (G1-G9) ─▶ recommendation ─▶ human approval
            ─▶ work order ─▶ outcome ─▶ feedback ─▶ steward-approved knowledge
                                                    └─▶ next diagnosis (kb_match ↑)

expert interview ─▶ AI draft ─▶ capturer review ─▶ second steward approves ─┘
```

**Decision trees.** Each fault type routes to its own deterministic causal
tree (`decision_tree.py`), 23 causes in all:

| Fault | Asset | Causes |
|---|---|---|
| `temperature_measurement_missing` | CRAH | bus/controller, config drift, loose wiring, sensor failure, data-path drop, intermittent, drift, noise |
| `chiller_compressor_trip` | Chiller | refrigerant leak, low charge, condenser fouling, motor fault, electrical fault |
| `ups_battery_fault` | UPS | thermal runaway risk, end of life, charger, ground fault, inverter |
| `pump_vibration_high` | Pump | cavitation, misalignment, looseness, bearing wear, imbalance |

Cause labels, branches and thresholds are illustrative expert heuristics
and need validation by Keppel SMEs before deployment.

**Confidence.**
`0.30·evidence_coverage + 0.20·peer_agreement + 0.25·kb_match − 0.10·staleness − 0.15·conflict`.
Peer agreement comes from neighbouring sensors, `kb_match` from similar
validated cases, staleness from each evidence item's real age against its
source's freshness SLA, and conflict from contradictory evidence. Below 0.35
the case escalates; 0.55 is needed to recommend. The Diagnosis screen shows
the breakdown and the pill knowledge version it was scored against.

**Guardrails** (`guardrails.py`, pure Python, run before anything reaches a
person or a work order):

| Rule | Trigger | Action |
|---|---|---|
| G1 | Recommendation touches a BMS setpoint, interlock, safety system or firmware | Block and escalate |
| G2 | Safety-critical fault (cooling lost and temperature rising) | Escalate |
| G2b | Environmental/pressure hazard (e.g. refrigerant leak) | Approval with a hazard acknowledgement |
| G3 | Cause belongs to another pill's domain | Coordinate and escalate |
| G4 | Confidence too low | Escalate, no recommendation |
| G5 | Unknown asset | Escalate without diagnosing |
| G6 | Any recommended action | Human approval, never auto-execute |
| G7 | Instruction-like text in sensor metadata or a transcript | Redact before any model sees it |
| G8 | Recommendation not grounded in knowledge and evidence | Reject |
| G9 | AI second opinion disagrees with the rules | Flag for the manager; routing unchanged |

## Expert knowledge capture

The **Capture** screen turns an interview with an experienced technician
into governed knowledge in four visible steps: interview, AI draft, capturer
review, second-steward approval.

- **Grounded.** Every heuristic must quote the transcript word for word, and
  every check, "never" and "escalate when" line must come from the same
  answer as the quote; anything else is dropped. The capturer can untick
  items or correct a cause but cannot add words. Drafts are re-checked on
  the server when submitted.
- **Safety-screened, with a person in the loop.** A word list cannot
  recognise every workaround, so `safety.py` and the approval step work
  together, at capture and again whenever knowledge is shown:
  - **Dropped:** any line that tells someone to defeat a protective device,
    in textbook or everyday words. Examples: bypass, jumper, wire across,
    wind up the cut-out, set the overload to max, cable-tie the contactor
    closed, a magnet on the flow reed, unplug the leak rope, clip the probe
    to the frame, "so it never cuts in". A prohibition ("never bypass the
    interlock") is kept.
  - **Safety-reviewed:** every check is an action on equipment, so approving
    any expert knowledge needs the steward to tick "safety reviewed".
    Without the tick it does not go live, and a check that was never
    reviewed is withheld from display.
  - **Guidance only:** a line that names a protective device or describes
    work on one (alarm, trip, contactor, probe, hand mode, lifting a wire)
    is labelled as such and never raises a diagnosis's confidence.

- **Flagged for review.** A quote whose own words rule out its cause, or
  that never names the cause it is filed under, is flagged to the steward.
- **Filed by pill.** Each heuristic goes to the pill that owns its cause, so
  chiller know-how from a CRAH interview lands under Chiller.
- **Reused with provenance.** On Diagnosis, **Expert Knowledge Reused** shows
  approved heuristics for the same asset type and cause, with the expert,
  quote, version and approving steward. Expert knowledge raises confidence
  only when the case's trigger or abnormal readings (the decision trees' own
  thresholds) show the signals the expert described. Healthy readings never
  count. One heuristic alone can lift the knowledge match only part of the
  way, and expert knowledge never overrides the decision tree.

Providers (`TBC_LLM_PROVIDER`): `mock` (default) uses offline models, a
fault-phrase extractor and an evidence-weighting second opinion, labelled as
such in the UI. `adp` calls Tencent Cloud ADP (v2 Chat API over SSE); a
failure is reported in plain language, never silently replaced.

## Governance

- **Two people per change, stewards only.** A proposal (outcome feedback, an
  escalation resolution, or an expert interview) is decided by the pill's
  owning steward; if they proposed it, the other steward decides. Nobody
  approves or rejects their own proposal, and an admin cannot decide on
  knowledge at all (admins can revoke and roll back). Approval needs a
  rationale, rejection a reason, and expert interviews need recorded
  consent. The roster is configurable (`TBC_PILL_OWNERS`).
- **Per-pill versions.** Each pill versions its own knowledge (`CRAH v1.4.0`).
  Approving moves only the pills a proposal files knowledge under.
- **Reversible.** An admin can roll one pill back to an earlier live version
  (other pills untouched), or revoke a single approved proposal. Version
  labels are never reused. A case scored against withdrawn knowledge cannot
  be approved until it is re-scored.
- **Ledgered.** Every proposal, decision, revoke and rollback is written to a
  keyed, hash-chained ledger with actor, reason and the versions it changed.
  While the ledger fails verification:
  - nothing new is written to it, including reviews of other records
  - knowledge changes are refused (423)
  - expert knowledge is withheld from diagnoses
  - case approvals wait for an auditor's review
- **Decisions keep their context.** Each manager decision stores the expert
  knowledge it was made with, so a later rollback doesn't rewrite history.

## AI second opinion

`ai_reasoning.py` gives an independent, advisory opinion on a completed
diagnosis. Inputs are G7-sanitised; a hypothesis outside the asset's causes
is rejected and citations not present in the evidence are dropped. It never
approves, executes or changes the case: a disagreement is recorded as G9 for
the manager to see, and a timeout falls back to a labelled "AI offline" state
recorded in the audit trail. Seeded case **UPS-DC1-02** shows a real
disagreement (the rules say end of life; the second opinion flags thermal
runaway risk).

The small draggable cloud on every screen shows the AI's state (thinking,
offline, worried when it disagrees). It only reports; it never acts.

## Identity and audit

- **Login.** `POST /login` checks the PIN (in the body, never the URL) and
  sets an HMAC-signed session cookie that expires and is revoked on logout.
  Five wrong PINs lock that user out from that client for five minutes (the
  server ignores `X-Forwarded-For`, so a client cannot pick its address).
  `?user=` works only as a test fallback under `TBC_DEMO_INSECURE=1`, with a
  banner shown in the UI. Set `TBC_SECRET` outside a demo.
- **Roles.** Technician, Asset Ops Manager, Knowledge Steward, Auditor,
  Admin (`rbac.py`). The UI gates controls on capabilities; the server
  enforces them regardless.
- **Tamper evidence.** Case histories, the knowledge ledger and the tool log
  are keyed HMAC-SHA256 hash chains, each sealed over length and head. Case
  entries carry a digest of the case's state, and ledger entries a digest of
  the knowledge base, so edits, truncation or deleted cases are detected. A
  case whose chain fails is frozen (423) and shown read-only; any failure
  raises a red banner on the Dashboard.
- **Integrity review.** On Governance, an auditor records a decision for
  each failed chain (`POST /audit/review`):
  - **Accept:** the record is genuine as it stands, so it is re-signed.
  - **Quarantine** (cases only): the case is closed and the work redone as a
    new case.

  A reason is required. The review is written to the reviewed chain and to
  the ledger, with the head hash that had failed. The ledger is reviewed
  first, and the auditor sees what failed, e.g. "the knowledge base was
  changed outside the governance flow after entry #12".
- **Key handling.** The key comes from `TBC_AUDIT_KEY` or a generated
  `~/.tbc/audit.key` (mode 0600). Anyone holding both the database and the
  key can re-sign the chains, so in production the key belongs in a secrets
  manager. Snapshots are JSON, never pickle.

## Project layout

```
technical_services_pill/
  app.py             FastAPI routes, RBAC, the agent-loop driver, persistence hooks
  agent_state.py     state machine and hash-chained case history
  decision_tree.py   the four causal trees
  confidence.py      W1-W5 scoring
  guardrails.py      G1-G9
  learning.py        knowledge base, per-pill versions, proposals, ledger
  capture.py         interview → grounded draft knowledge
  safety.py          safety screen for expert know-how
  llm.py             provider seam (mock / Tencent Cloud ADP)
  ai_reasoning.py    advisory second opinion
  auth.py, rbac.py   login, sessions, roles
  audit.py           keyed hash-chain primitives
  persistence.py     JSON snapshots to SQLite
  store.py           in-memory case store
  tools.py           evidence-gathering and work-order tools
  cause_registry.py  canonical cause ids, labels, owning pill
  evidence_flags.py  which readings are abnormal (shared with the UI)
  mock_registry.py   demo assets, telemetry and seed knowledge
  demo.py            console demo
frontend/            plain HTML/CSS/JS UI served at /ui (see frontend/README.md)
tests/               pytest suite and tests/evals/run_evals.py
docs/                ADP setup; pilot → production path and what is stubbed
```

`docs/IMPLEMENTATION_PATH.md` lists what is real and what is simulated (asset
telemetry and the CMMS are mocks) and the path to production.

---

*All cause heuristics and thresholds are illustrative and require SME
validation before production use.*
