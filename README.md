# Technical Services Fault Diagnosis Intelligence Pill

A deterministic, audit-ready agent for diagnosing technical-services faults on
critical data-center assets (CRAH units, chillers, pumps, UPS). Built for the
Keppel **AI HARVEST** hackathon.

> **Design principle: AI in the harvest, determinism in the execution.**
> An LLM turns expert interviews into draft knowledge (see *Expert Knowledge
> Capture*), but nothing it drafts goes live until a second knowledge steward
> approves it. Diagnosis itself is deterministic: the same observation and
> evidence always yield the same diagnosis, recommendation and guardrail
> verdict, so every run is auditable and unit-testable.

---

## Architecture

```
                         ┌──────────────────────────────────┐
                         │           FastAPI App             │
                         │      (RBAC-enforced routes)       │
                         └───────────────┬──────────────────┘
                                         │ HTTP
         ┌───────────────────────────────┼───────────────────────────┐
         ▼                               ▼                           ▼
┌─────────────────┐          ┌─────────────────────┐      ┌──────────────────┐
│  AgentState     │◀────────▶│   Tool Layer        │      │   CaseStore      │
│  (state machine │          │  gather_evidence    │      │  (in-memory +    │
│   11 states,    │          │  diagnose_asset     │      │   hash-chain     │
│   16 transitions│          │  check_guardrails   │      │   audit log)     │
│   hash-chain    │          │  propose_recommend  │      └──────────────────┘
│   audit history)│          │  create_work_order  │
└────────┬────────┘          │  submit_feedback    │
         │                   └─────────┬───────────┘
         │                             │
         ▼                             ▼
┌─────────────────┐          ┌─────────────────────┐      ┌──────────────────┐
│ Confidence      │          │  Decision Tree      │      │  LearningStore   │
│ Scorer          │          │  (Q1-Q7, 8 causes) │      │  (validated KB,  │
│ W1-W5 formula   │          └─────────────────────┘      │   Jaccard RAG)   │
└─────────────────┘                    │                   └────────┬─────────┘
                                       │                            │
                              ┌────────▼─────────┐                  │
                              │  Guardrail Engine │◀─────────────────┘
                              │  G1-G9            │
                              └───────────────────┘
```

**Request flow:** observation → trigger → gather evidence → decision tree →
confidence score → guardrails (G1-G9) → recommendation → human approval →
work order → outcome → feedback → **validated case written back to KB**
(closed-loop learning).

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `models.py` | Pydantic v2 data models, enums, threshold constants. Core 8 agent-state fields: `asset_id`, `observation`, `evidence`, `diagnosis`, `confidence`, `recommendation`, `human_decision`, `outcome`. |
| `agent_state.py` | Deterministic state machine, hash-chain audit history, lifecycle helpers (`trigger`, `add_evidence`, `complete_diagnosis`, `propose_recommendation`, `record_human_decision`, `record_outcome`, `queue_feedback`, `close_escalation`, `request_more_evidence`). |
| `guardrails.py` | LLM-independent guardrail engine G1-G8, plus G9 (`flag_ai_disagreement`) which surfaces the AI second opinion to the AOM without ever changing routing. Runs *before* any recommendation reaches a human or any work order is created. |
| `decision_tree.py` | Executable causal decision trees for CRAH (Q1-Q7), chiller, UPS and pump faults. 23 candidate causes across all four asset types, plus the `unresolvable` sentinel for "the tree found nothing". |
| `confidence.py` | Confidence scorer: `w1·coverage + w2·peer + w3·kb_match − w4·staleness − w5·conflict`. `peer_agreement` comes from real peer sensors/sibling assets in `mock_registry`; `data_staleness`/`conflict_penalty` from real evidence age and contradictions. |
| `ai_reasoning.py` | Advisory AI second opinion on a completed diagnosis: G7-sanitises inputs, calls `llm.diagnostic_second_opinion`, grounds the response, never influences routing. |
| `llm.py` | Provider seam for both expert capture and the AI second opinion (`mock` offline / `adp` Tencent Cloud ADP). |
| `capture.py` | Expert interview → grounded draft knowledge. Every heuristic must quote the transcript verbatim or it's dropped. |
| `cause_registry.py` | Canonical cause IDs, plain-English labels, and which pill owns each cause. |
| `auth.py` | PIN-checked login and signed session cookie identity (`POST /login`); `?user=` only works as a fallback under `TBC_DEMO_INSECURE=1`. |
| `tools.py` | Agent tool layer: evidence gatherer, diagnosis orchestrator, guardrail checker, recommendation proposer, work-order creator, feedback submitter. |
| `rbac.py` | 5-role RBAC matrix (technician, asset_ops_manager, knowledge_steward, auditor, admin). Permission checks via `can()` / `require()`. |
| `store.py` / `database.py` | SQLite-backed `CaseStore` with a memory cache and hash-chain audit trace. |
| `learning.py` | `LearningStore`: validated-case KB, Jaccard similarity retrieval, `kb_match_score()`, feedback → validated-case write-back, proposal workflow. |
| `audit.py` | `canonical_json`, keyed HMAC-SHA256 `compute_hash`, `verify_chain`, `GENESIS_HASH`. |
| `mock_registry.py` | Demo data: 7 assets across 4 pills (2 CRAH, 2 chiller, 1 UPS, 2 pump -- each pill's second asset has a distinct fault signature so more than one captured cause per pill is reachable in a live diagnosis), seed KB, maintenance history, sensor metadata, BMS status. |
| `persistence.py` | FastAPI lifecycle snapshots for cases, KB, proposals, audit. |
| `app.py` | FastAPI app: RBAC-enforced routes, identity, persistence lifecycle, the agent-loop driver, and `/pills`. |
| `demo.py` | End-to-end lifecycle, multi-asset routing, and AI HARVEST capture-to-reuse demo. |

## Quick Start

### Option A — Docker (recommended)

```bash
# Build and start the API server on :8000
docker compose up --build -d

# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
# Health check at http://localhost:8000/kb/stats

# Run the end-to-end demo, including the AI HARVEST loop, inside a container
docker compose run --rm demo

# Teardown
docker compose down
```

### Option B — Local (Python 3.11+)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the test suite
make test

# Run the console demo, including expert capture → approval → reuse
make demo

# Start the API server with hot reload
make serve
```

### Option C - Frontend Demo UI (what judges should run)

```bash
make install        # creates .venv and installs requirements
make serve          # = .venv/bin/python -m uvicorn frontend.serve:app --port 8000
```

Open `http://localhost:8000/ui` and sign in with a demo PIN (`mgr1` = 2222;
all six are in `DEMO.md`). When the server starts with no cases it seeds
five demo scenarios: one CLOSED, a bus fault ESCALATED to the BMS pill, a
chiller AWAITING_APPROVAL, a borderline UPS awaiting approval where the AI
second opinion disagrees with the rules (G9, routing unchanged), and a pump
ESCALATED at 49% that clears 55% once the sample interview is approved,
recorded in the audit trail as `demo-seed`, never as a real user; an admin
can add more with **Seed Demo Cases**. The role switcher (top right) asks
for a user's PIN the first time you switch to them; after that this browser
can switch back without it (a signed httpOnly cookie, so no PIN is stored
in the page). It sets a real signed-in session, not a URL param — see *Identity and RBAC* below. A **Dark theme** toggle sits next to it; light is
the default (projector-safe, high-contrast — see `tests/test_contrast.py`).
Click **Demo guide** for a guided walkthrough, or follow `DEMO.md` for a
6-minute scripted run. See `frontend/README.md` for UI implementation
details.

The FastAPI app restores state at startup and snapshots successful mutations
to `data/tbc.sqlite` (cases, proposals, KB versions, tool audit log); audit
chains are re-verified on load. This applies to both the API and UI entry
points. `make reset` removes this snapshot database; the separate per-case
SQLite store remains intact. Set `TBC_PERSIST=0` to disable these app-level
snapshots.

### Makefile Targets

| Command | Description |
|---|---|
| `make install` | Install runtime and test dependencies |
| `make test` | Run the full pytest suite |
| `make eval` | Run EVAL-01..12 acceptance evals, print a pass/fail table |
| `make demo` | Run the end-to-end console demo |
| `make serve` | Start the API and UI on `localhost:8000` (open `/ui`) |
| `make reset` | Wipe persisted state for a clean demo |
| `make docker-up` | Build + start the API container in background |
| `make docker-demo` | Run the demo inside a container |
| `make docker-down` | Stop and remove containers |
| `make lint` | Syntax-check all modules via `py_compile` |
| `make clean` | Remove `__pycache__` directories |

## API Quick Reference

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/cases` | Create a new case from an observation (triggers agent) |
| `GET` | `/cases` | List all cases |
| `GET` | `/cases/{id}` | Get case snapshot (full agent state) |
| `GET` | `/cases/{id}/expert-knowledge` | Show approved interview heuristics matching the diagnosed cause and asset type |
| `POST` | `/cases/{id}/advance` | Drive the agent loop one transition forward |
| `GET` | `/cases/{id}/evidence` | Retrieve gathered evidence |
| `GET` | `/cases/{id}/diagnosis` | Retrieve diagnosis + candidate causes |
| `GET` | `/cases/{id}/recommendation` | Retrieve draft recommendation |
| `POST` | `/cases/{id}/approval` | Submit human decision (approve / reject / modify). A rationale is always required; a G2/G2b hazard also needs `hazard_acknowledged=true` |
| `GET` | `/cases/{id}/work-order` | Retrieve work order status |
| `POST` | `/cases/{id}/work-order` | Create + acknowledge work order (requires prior approval) |
| `POST` | `/cases/{id}/outcome` | Record observed outcome |
| `POST` | `/cases/{id}/feedback` | Submit feedback → creates pending proposal (F2). Accepted only in FEEDBACK_QUEUED; the cause must be a known cause of this asset type; asset type and fault signature come from the case, never the client |
| `POST` | `/cases/{id}/escalation/close` | Close an escalation with its resolution; with `confirmed_cause`, the resolution is also queued as a knowledge proposal |
| `GET` | `/kb/stats` | Knowledge-base statistics (case count, cause priors, pending proposals) |
| `GET` | `/kb/queue` | List pending knowledge proposals (steward/admin only) |
| `POST` | `/kb/proposals/{id}/approve` | Approve a proposal → ingests into KB, bumps version (steward/admin) |
| `POST` | `/kb/proposals/{id}/reject` | Reject a proposal (steward/admin) |
| `GET` | `/kb/versions` | Every KB version ever issued, its displayed label, and whether it is live or rolled back. Labels are never reused |
| `POST` | `/kb/rollback/{version}` | Roll back to an earlier live version (admin only, `reason` required, recorded in the ledger) |
| `GET` | `/kb/ledger` | Keyed, hash-chained governance ledger: every proposal, approval, rejection and rollback with actor and reason |
| `GET` | `/audit/status` | Integrity summary (any broken case chain or ledger), shown as a Dashboard banner |
| `POST` | `/demo/seed` | Admin only: add the demo scenarios, attributed to `demo-seed` |
| `POST` | `/cases/{id}/rescore` | Re-score a case awaiting approval against the current KB (required after the knowledge it used was rolled back or revoked) |
| `GET` | `/kb/proposals` | All proposals, filterable by `status` (stewards/admin) |
| `POST` | `/kb/proposals/{id}/revoke` | Withdraw one approved proposal's knowledge, `reason` required |
| `GET` | `/me` | The session's user, role and capabilities (the UI gates on capabilities, never user names) |
| `GET` | `/pills` | Pill Registry: owner steward, KB version, knowledge count, approval rate per pill |
| `GET` | `/audit/trace` | Full hash-chain audit trail with tamper detection |

> Interactive Swagger docs at `/docs`, ReDoc at `/redoc` once the server is running.

## Guardrail Engine (G1-G9)

G1-G8 are **pure Python, deterministic, and LLM-independent**. They run
*before* any recommendation reaches a human and *before* any work order is
created (spec §4.4, Layer 4). G9 is the one exception — it surfaces the
*advisory* AI second opinion, but it is still a pure function of its inputs
and never blocks, escalates, or requires approval.

| Rule | Trigger | Action |
|---|---|---|
| **G1** | Recommendation implies a BMS setpoint / interlock / safety-system / firmware change | Block + escalate |
| **G2** | Fault classified safety-critical (cooling lost **AND** temperature rising) | Must escalate |
| **G2b** | Cause involves environmental/pressure hazard (e.g. refrigerant leak) | Force `AWAITING_APPROVAL` with safety flag (does NOT auto-escalate) |
| **G3** | Root cause maps to another pill's domain (chiller, power, BMS bus, leasing, tenant) | Coordinate + escalate |
| **G4** | `confidence < ESCALATE_CONFIDENCE` (0.35); or below `MIN_RECO_CONFIDENCE` (0.55) when re-querying every evidence source returns nothing new; or re-scored below 0.55 after knowledge is withdrawn | Escalate to a human, do not recommend |
| **G5** | Asset not in registry / unknown asset | Escalate (short-circuit, no diagnosis) |
| **G6** | Any recommended action | Force `AWAITING_APPROVAL` — no auto-execute |
| **G7** | Sensor metadata / tag name contains prompt-injection patterns | Sanitize before any LLM sees it |
| **G8** | Recommendation not grounded in `kb_refs` **and** `evidence_refs` | Reject as ungrounded (anti-hallucination) |
| **G9** | The AI second opinion disagrees with the rule-based diagnosis | Flag for the AOM only — never changes routing |

## Decision Trees (multi-asset)

The pill routes by `observation.type` to a **fault-specific causal tree** via a
deterministic dispatcher (`_FAULT_EVALUATORS` in `decision_tree.py`). Adding a
new asset/fault class = write one evaluator function + register it — no caller
changes. Same observation + evidence → same candidates every run.

Currently **four fault types** across **four asset classes** are implemented:

| Fault type (`observation.type`) | Asset | Tree | Causes |
|---|---|---|---|
| `temperature_measurement_missing` | CRAH | Q1-Q7 | 8 (bus / config / wiring / sensor / data-path / intermittent / drift / noise) |
| `chiller_compressor_trip` | Chiller | Q1-Q4 | 5 (leak / undercharge / fouling / motor / electrical) |
| `ups_battery_fault` | UPS | Q1-Q5 | 5 (thermal-runaway / EoL / charger / ground-fault / inverter) |
| `pump_vibration_high` | Pump | Q1-Q5 | 5 (cavitation / misalignment / looseness / bearing / imbalance) |

### CRAH — "temperature measurement missing" (Q1-Q7)

```
Q1  Reading status?
│
├─ INVALID ──▶ Q7 (drift vs fault/noise)
│               ├─ sudden spike / sentinel → sensor_fault_noise
│               ├─ gradual drift / calibration overdue → sensor_drift
│               └─ ambiguous → (no candidate, request more evidence)
│
└─ ABSENT ───▶ Q2  Other tags on same bus reporting?
                ├─ No (bus dead) → comm_bus_failure        [ESCALATE]
                └─ Yes
                   └─▶ Q3  Tag present in config / controller?
                         ├─ Tag renamed/removed → config_drift
                         └─ No change
                            └─▶ Q4  Recent maintenance disturbance?
                                  ├─ sensor_replacement / wiring_inspection → loose_wiring
                                  └─ No disturbance
                                     └─▶ Q5  Sensor past EoL / calibration overdue?
                                           ├─ Yes → sensor_hardware_failure
                                           └─ No
                                              └─▶ Q6  Gateway / SCADA path healthy?
                                                    ├─ No → data_path_drop  [cross-coordinate]
                                                    └─ Yes → intermittent_fault
```

| Cause ID (canonical) | Label | Default Action |
|---|---|---|
| `communication_bus_controller_failure` | Communication bus / controller failure | `controller_inspection` → escalate to BMS vendor |
| `configuration_drift` | Configuration drift (tag missing/renamed) | `config_remap` (approval required, like every action — G6) |
| `loose_wiring_after_service` | Loose wiring / connection disturbed during service | `onsite_inspection` |
| `sensor_hardware_failure` | Sensor hardware failure (RTD/thermistor dead) | `sensor_replacement` |
| `data_path_drop` | Data-path drop (telemetry transport) | `path_restore` → cross-coordinate with IT/Ops |
| `intermittent_fault` | Intermittent sensor fault / borderline failure | `onsite_inspection` (lower confidence) |
| `sensor_drift` | Sensor drift | `sensor_recalibration` |
| `sensor_fault_noise` | Sensor fault or electrical noise | `sensor_inspection` |

> Cause IDs are the canonical long forms (`cause_registry.py`); short forms
> like `comm_bus_failure` or `loose_wiring` are aliases only and are never
> emitted — `GET /causes` and every dropdown/label on screen use the
> canonical form with a plain-English label.

> All cause labels, branch predicates, and thresholds are **illustrative
> expert heuristics** (spec §4.2, Appendix A #5) that must be validated with
> Keppel technical-services SMEs before deployment. They are plain configurable
> Python — versionable, reviewable, and rollback-able via the governance pipeline.

### Chiller — "compressor trip" (Q1-Q4)

| Q | Branch | → Cause |
|---|---|---|
| Q1 | Low-pressure switch tripped + leak detected | `refrigerant_leak` |
| Q1 | Low-pressure switch tripped + charge < 70% | `low_refrigerant_charge` |
| Q2 | High head pressure / high approach + fans running | `condenser_fouling` |
| Q3 | Motor overcurrent / winding resistance < 0.5 | `compressor_motor_fault` |
| Q4 | Starter / contactor fault | `chiller_electrical_fault` |

### UPS — "battery fault" (Q1-Q5, safety-first ordering)

| Q | Branch | → Cause |
|---|---|---|
| Q1 | Cell temp ≥ 45 °C **and** rising | `thermal_runaway_risk` (**ESCALATE**) |
| Q2 | SoH < 60% or age ≥ 60 months | `battery_eol` |
| Q3 | Charger fault / no charge current | `charger_failure` |
| Q4 | `ground_fault` alarm | `ground_fault` |
| Q5 | `inverter_fault` alarm | `inverter_fault` |

### Pump — "vibration high" (Q1-Q5, spectrum-driven)

| Q | Branch | → Cause |
|---|---|---|
| Q1 | Broadband dominant + NPSH margin < 0.3 | `cavitation` |
| Q2 | 2x dominant + axial ≥ 4.5 mm/s | `shaft_misalignment` |
| Q3 | Subharmonic / soft foot / directional | `foundation_looseness` |
| Q4 | Bearing-defect freq / temp ≥ 75 °C / greasing overdue | `bearing_wear` |
| Q5 | 1x dominant, no other symptoms | `impeller_imbalance` |

## Confidence Scoring

```
confidence = W1·evidence_coverage
           + W2·peer_agreement
           + W3·kb_match
           − W4·data_staleness
           − W5·conflict_penalty
```

| Weight | Value | Factor | Meaning |
|---|---|---|---|
| W1 | 0.30 | `evidence_coverage` | fraction of decision-tree branches resolvable with retrieved evidence |
| W2 | 0.20 | `peer_agreement` | real peer sensors / sibling assets in `mock_registry` (CRAH today); defaults to 0.5 only where a peer slot exists but is unpopulated, or 1.0 for asset types the registry has no sensor-level model for yet (Chiller/UPS/Pump) |
| W3 | 0.25 | `kb_match` | Jaccard similarity to validated past cases in the KB (RAG) |
| W4 | 0.10 | `data_staleness` | penalty: evidence age vs. a per-source freshness SLA (real evidence timestamps, not a flag) |
| W5 | 0.15 | `conflict_penalty` | penalty: contradictory boolean evidence fields across sources |

The factor bars and the KB version a diagnosis actually used are shown live
on the Diagnosis screen ("Confidence Breakdown"). On Governance, after a
proposal approves, **Re-run Diagnosis on Similar Open Cases** re-scores a
still-open case against the current KB — non-destructively — and shows the
before/after confidence.

**Thresholds** (from `models.py`):

| Constant | Value | Effect |
|---|---|---|
| `MIN_RECO_CONFIDENCE` | 0.55 | `DIAGNOSING → RECOMMENDING` requires `confidence ≥` this |
| `ESCALATE_CONFIDENCE` | 0.35 | `confidence <` this → `ESCALATED` (no recommendation, G4) |

## Closed-Loop Learning (F2: Proposal Workflow)

The system improves itself through a **feedback → proposal → steward approval → KB
write-back** loop (spec §7, enhanced in F2):

```
  diagnosis ──▶ human feedback ──▶ pending proposal ──▶ steward review
                      │                                        │
                      ▼                                   approve / reject
                 FeedbackRecord                               │
                                                      ┌───────┴───────┐
                                                      ▼               ▼
                                                 ValidatedCase    (discarded)
                                                 written to KB
                                                      │
                                                      ▼
                                                 next diagnosis
                                                 retrieves via Jaccard
                                                 similarity → kb_match ↑
                                                 → confidence ↑
```

1. After a case closes, `submit_feedback` records the human-confirmed (or
   corrected) root cause and creates a **pending proposal** (not directly
   ingested).
2. A knowledge steward reviews the proposal via `/kb/queue` and approves or
   rejects it. Approval ingests the case into the KB and increments the KB
   version.
3. On the **next** diagnosis, `get_similar()` retrieves matching cases and
   `kb_match_score()` returns a similarity in `[0, 1]`.
4. A higher `kb_match` feeds into the W3 term, raising `confidence` — so
   recurring faults are diagnosed faster and with more confidence.
5. An admin can **roll back** the KB to an earlier live version via
   `/kb/rollback/{version}?reason=...`, removing everything approved after
   it — reachable from the **Rollback** panel on Governance (admin role),
   which asks for a reason and a confirmation. Version numbers are never
   reused: after rolling back from v1.6.0 to v1.4.0, the next approval is
   v1.7.0, so a case stamped "KB version used: 1.5.0" always means one
   thing. Every approval, rejection and rollback is written to the keyed
   governance ledger (`/kb/ledger`, shown on Governance).
6. When an AOM closes an escalation and names the confirmed cause, the
   resolution itself becomes a knowledge proposal: the cases the pill could
   not solve are where the expert know-how is.
7. Withdrawn knowledge never silently backs a decision. Each case records
   the KB version it was scored against; if that version is rolled back, or
   a proposal it relied on is **revoked** (one proposal at a time, from
   Governance), the AOM Decision screen blocks approval until the case is
   re-scored against the current KB, which may send it back to a human.
8. Each pill's owning steward approves its knowledge (if the owner proposed
   it, the other steward stands in); the approver, not the proposer, is
   recorded as the validator.
9. An approved expert interview is guidance, not an observed outcome: it
   never moves a cause's confirmation rate. It raises confidence only on a
   case whose evidence names the signals the expert described: the
   distinctive words of the expert's condition are matched against the
   case's evidence field names, set flags and text values (three or more
   matches is full support), and the matched words are shown on screen.
   It checks that the same signals are present, not their thresholds: an
   expert's "axial higher than radial" matches "axial" but does not compare
   the two readings.

**Demo proof:** the learning-loop case shows `kb_match` rising from **0.73 →
1.00** and confidence from **0.43 → 0.50** after one approved feedback cycle
(`make demo`, CASE 3; the exact numbers move if `mock_registry`'s peer
sensors change, since `peer_agreement` is now computed from them live —
see "Confidence breakdown" below).

**Separation of actors:** whoever proposes a change can never approve it.
`approve_proposal` returns 403 if the approver is the proposer, and the
proposer is always the authenticated caller (a client-supplied
`submitted_by` is ignored). Demo users `steward1` and `steward2` exist so
the second-reviewer rule can be shown live.

## Expert Knowledge Capture (LLM drafts, steward approves)

The challenge's hardest requirement is capturing know-how that was never
written down. The **Capture** screen takes an interview with an experienced
technician and walks four visible steps: Interview, AI draft, You review,
Second steward approves.

```
interview transcript
   │  G7: instruction-like text redacted before any model sees it
   ▼
POST /capture/draft  (llm.py)  ──▶  symptom, likely cause, checks, never-do,
   │                                escalate-when, verbatim evidence quote
   ▼
grounding check: any item whose quote is not in the transcript is DROPPED
cause check:     causes stored as canonical IDs with plain-English labels;
                 causes outside the known universe are flagged "new:<slug>"
filing:          each heuristic is filed under the pill that owns its cause
                 (chiller know-how from a CRAH interview goes to Chiller)
   ▼
capturer reviews: untick wrong items, correct a cause (cannot add words)
   ▼
POST /capture/interview  (re-grounded server-side) ──▶ pending proposal
   ▼
a DIFFERENT knowledge steward approves ──▶ live KB (version bump, rollback-able)
```

Nothing is queued until the capturer sends the reviewed draft, so a
half-wrong draft never reaches the steward queue.

Approved heuristics on known causes enter the validated library, raising
that cause's empirical prior and so the confidence of future diagnoses.
Heuristics proposing a *new* cause stay as knowledge only: the engine cannot
diagnose a cause until an engineer adds a decision-tree branch for it.
On the diagnosis screen, **Expert Knowledge Reused** shows matching approved
heuristics with the source expert, knowledge ID, KB version, interview quote,
and checks. A match requires the same asset type and diagnosed cause; the
decision tree and guardrails remain authoritative.

**Providers** (`TBC_LLM_PROVIDER`):

| Value | Behaviour |
|---|---|
| `mock` (default) | Offline models, no LLM: a fault-phrase extractor for capture (all 23 causes, clause-scoped negation) and an evidence-weighting second opinion. Labelled "Offline models (no LLM)" in the UI. |
| `adp` | Tencent Cloud Agent Development Platform, v2 Chat API over HTTP SSE (`llm._call_adp()`). Failures return HTTP 502, never a silent fallback. |

To use ADP: `cp .env.example .env`, set `TBC_LLM_PROVIDER=adp` and paste your
AppKey (ADP console: your app > Publish > Service status > API management >
Copy) into `ADP_APP_KEY`. `.env` is gitignored. The top bar shows which model
is active.

**Demo guide:** the "Demo guide" button in the top bar walks an eight-step
tour of the whole loop, setting the role and screen for each step.

**Console AI HARVEST proof:** `make demo` also runs a complete interview-to-
reuse scenario: the offline mock extractor drafts grounded heuristics, a
different steward approves them, a new CRAH case reuses matching expert
knowledge, a manager approves the recommendation, and a steward validates
the maintenance outcome into the KB. Set `TBC_LLM_PROVIDER=adp` to use the
configured Tencent ADP provider instead of the default offline mock.

## AI Second Opinion (advisory, never routes)

The same provider seam (`llm.py`) that drafts expert knowledge also produces
an independent second opinion on a *completed* rule-based diagnosis
(`ai_reasoning.py`). It is explicitly advisory:

- Sensor metadata and evidence are G7-sanitised before the model sees them.
- A hypothesis naming a cause outside the candidates offered is rejected; an
  evidence citation not actually present in the supplied evidence is dropped.
- Offline, it is an **evidence-weighting model**: every cause the pill knows
  is scored on weighted evidence signals at once, a different method from
  the decision tree's first-match rule walk, so a borderline reading the
  tree's threshold ignores can still tip it. Seeded case **UPS-DC1-02**
  shows this: the tree says battery end of life (state of health 58%), the
  second opinion flags thermal runaway risk (cell temp 41°C and rising).
- It may name any cause of the asset's pill; a hypothesis outside that set
  is rejected. Evidence is passed as readable lines, and model errors are
  shown in plain language (raw provider responses stay in the server log).
- It never approves, executes, publishes, or changes `current_state`. When it
  disagrees with the rule-based diagnosis, that's logged as guardrail **G9**
  — visible to the AOM, changes nothing.
- A timeout or malformed reply falls back to a labelled "AI offline" state;
  the deterministic diagnosis is never blocked by it, and the fallback is
  itself recorded in the hash-chained audit trail.

Shown on the Diagnosis screen as its own card, clearly separate from the
"Rule-based diagnosis (expert decision tree)" card, and summarised on AOM
Decision. An animated AI avatar sits in the top bar on every screen (green:
answering; grey: offline models; dim: AI offline, with the reason on hover)
and on the Capture draft card.

## Pill Registry

`GET /pills` and the **Pill Registry** panel (Governance) list all four
pills — CRAH, Chiller, UPS, Pump — with their owner steward, current KB
version, knowledge-item count, and approval rate. All four currently share
one knowledge base, so the KB version is identical across rows; that's the
real current architecture, not an invented per-pill version (see
`docs/IMPLEMENTATION_PATH.md` for the scale path to per-pill isolation).

## Identity and RBAC

`POST /login` with `{"user_id": ..., "pin": ...}` in the body (never the
URL) checks that user's PIN; five wrong PINs lock that user out for five
minutes. It sets an
HMAC-signed session cookie (`TBC_SECRET`, auto-generated per process if
unset). Naming a user is not enough to act as them. Demo PINs are in
`DEMO.md`; set `TBC_LOGIN_PINS="tech1:....,mgr1:...."` to replace them. A
production deployment would put SSO here. Every endpoint
resolves its caller from that cookie, which always wins over a `?user=` query
param — `?user=` only works as a fallback when `TBC_DEMO_INSECURE=1` is set
(local demos/tests), and the UI shows a persistent amber banner whenever that
flag is in effect. The top-bar role switcher calls `/login`; it is not a
client-side-only toggle.

| Role | Key Permissions |
|---|---|
| `technician` | Create cases, gather evidence, read diagnosis, record outcomes |
| `asset_ops_manager` | Approve/reject/modify recommendations, create work orders, record outcomes, submit feedback, capture expert interviews |
| `knowledge_steward` | Submit feedback, capture expert interviews, approve another steward's proposals, read audit trace |
| `auditor` | Read audit trace, all cases (read-only) |
| `admin` | All permissions |

A session cookie beats a spoofed `?user=` even on write paths (approval,
outcome) — see `tests/test_identity.py`.

## Testing

```bash
make test        # = PYTHONPATH=. .venv/bin/python -m pytest -q tests
make eval         # = PYTHONPATH=. .venv/bin/python tests/evals/run_evals.py
```

The Makefile uses `.venv/bin/python` when it exists, so no activation is
needed after `make install`.

**165 tests** (verified with `make test`; this count is a snapshot — run the
command for the current number) across spec acceptance cases, F1-F3
governance, identity, confidence, contrast/accessibility, and no-contradiction
checks:

| File | Covers |
|---|---|
| `test_agent_state.py` | Core state-machine lifecycle, illegal transitions, guardrails G1/G5/G7/G8, audit tamper detection, multi-asset decision trees |
| `test_f1_escalation_api.py` | F1: G3 cross-domain escalation via the real API path |
| `test_f2_proposals.py` | F2: proposal workflow — pending → approve/reject → KB write-back → rollback, self-approval blocked, RBAC |
| `test_f3_refrigerant_leak.py` | F3: G2b forces `AWAITING_APPROVAL` (not escalate) for a safety-critical-but-actionable cause |
| `test_rbac_caps.py` | Declared vs. enforced RBAC capabilities |
| `test_capture.py`, `test_capture_review.py` | Expert capture: grounding, cause filing by owning pill, the four-step review flow |
| `test_adp_client.py` | ADP v2 SSE client against a simulated event stream |
| `test_kb_version_label.py`, `test_persistence.py` | KB version display; state survives a restart |
| `test_ai_second_opinion.py` | Phase 1: AI second opinion agree/disagree (G9), timeout/malformed fallback is audited, injected tag redaction, non-candidate cause rejection |
| `test_identity.py` | Phase 2: signed cookie beats a spoofed `?user=` (including on writes), tampered cookie rejected, insecure-mode fallback |
| `test_confidence_uplift.py`, `test_rerun_diagnosis.py` | Phase 3: approving validated feedback raises the next identical case's confidence by ≥0.05, rollback restores it exactly, non-destructive re-run preview |
| `test_no_contradictions.py` | Phase 4: no developer jargon ships, no diagnosis ≠ a confidence band, escalated cases never carry an actionable recommendation |
| `test_contrast.py` | Phase 5: every text/background pair ≥ 4.5:1 in both themes, parsed from the actual CSS tokens |
| `test_pill_registry.py` | Phase 6: `/pills` lists all four pills with the right owner and a real approval rate |
| `test_judge_fixes.py` | Rollback int/label reconciliation (`/kb/versions`), new condenser-fouling/cavitation assets reachable, rollback RBAC |
| `test_judge_round2_fixes.py` | Negation-aware capture, G2b reason reaches the Decision screen, G5 via API |
| `test_judge_round5_fixes.py` | Approved interview moves the pump case from escalated to approval; edits to the version stamp, state, an expert's checks or name detected; deleting a case or wiping the tool log detected; no injection fragment reaches a heuristic; escalation instructions are not cause heuristics; AI disagreement reaches the AOM with routing unchanged; PIN-less switches never count towards lockout; logout revokes the session |
| `test_judge_round4_fixes.py` | Truncation and unhashed-field edits detected; ledger truncation and KB edits detected; JSON snapshots; rolled-back knowledge blocks approval until re-scored; single-proposal revoke; validated_by is the approver; AI second opinion disagrees with readable citations; plain-language ADP errors; every escalation has a reason; fault/asset mismatch refused; owning steward enforced; expert corroboration; PIN lockout and unlock cookie |
| `test_judge_round3_fixes.py` | Rejected feedback leaves no proposal; cross-asset/unknown causes refused; ledger records approvals and rollbacks; labels never reused; a re-hashed chain without the key fails and freezes the case; login PIN; seeding never attributed to real users; rationale and hazard acknowledgement; escalation resolution harvested; pump/UPS capture; manual capture with AI offline |

**`make eval`** runs 12 labelled acceptance evals (`EVAL-01`..`EVAL-12`) as a
pass/fail table, independent of the pytest suite: ADP call shape, AI cannot
bypass approval, AI failure fallback, unknown asset, canonical cause IDs,
persistence across a simulated restart, feedback governance, RBAC approval,
rollback, audit tamper detection, the RBAC matrix, and no invented evidence
in capture. See `tests/evals/run_evals.py`.

## Audit Integrity

Every case state transition, and every knowledge governance action
(proposal, approval, rejection, rollback), is appended to a **keyed hash
chain** (spec §6):

```
hash_n = HMAC-SHA256(audit_key, canonical_json({prev_hash: hash_{n-1}, ...fields}))
```

- Each case entry also records a digest of the case's state at that point:
  current state, evidence, diagnosis, confidence and its breakdown
  (including the KB version it was scored against), recommendation,
  guardrail result, AI opinion, decision, outcome, work order and feedback
  ids. Editing any of these afterwards fails verification.
- Each ledger entry records a digest of the knowledge base: every validated
  case, every approved heuristic's full text (symptom, checks, cautions,
  escalation conditions, quote, expert name and role), every proposal's
  status and content, and the version history.
- Each chain carries a keyed **seal** over its length and head, so deleting
  the newest entries (truncation) is caught. The set of case ids and the
  tool audit log (itself a keyed chain) are sealed too, so deleting a whole
  case or wiping the tool log is caught.
- `/audit/status` reports all of these; any failure shows a red banner on
  the Dashboard for every role.
- `verify_audit_chain()` (cases) and `verify_ledger()` (knowledge) recompute
  all of this. Re-hashing a forged chain fails unless the editor also holds
  the audit key.
- State is saved as JSON, never `pickle`, so loading a snapshot cannot run
  code.
- The key comes from `TBC_AUDIT_KEY`, or a generated `data/audit.key` (mode
  0600) for local demos. **Limit:** someone with filesystem access to both
  the database and that key file can re-sign the chain; in production the
  key must live in a secrets manager off the database host.
- A case whose chain fails verification is frozen (HTTP 423 on every write)
  and a red banner appears on the Dashboard for every role.

## Project Structure

```
technical_services_pill/
├── models.py            # Pydantic v2 models, enums, thresholds
├── agent_state.py       # State machine + hash-chain audit
├── guardrails.py        # G1-G9 engine (G1-G8 deterministic, G9 AI-disagreement flag)
├── decision_tree.py     # CRAH/chiller/UPS/pump causal trees, 23 causes
├── confidence.py        # W1-W5 scoring formula, registry-backed peer_agreement
├── cause_registry.py    # Canonical cause IDs, labels, owning pill
├── ai_reasoning.py      # Advisory AI second opinion on a diagnosis
├── llm.py               # Provider seam (mock / Tencent Cloud ADP) for capture + second opinion
├── capture.py           # Expert interview -> grounded draft knowledge
├── auth.py              # PIN-checked login, signed session cookie identity
├── tools.py             # Agent tool layer
├── rbac.py              # 5-role RBAC matrix
├── store.py / database.py  # SQLite-backed CaseStore + in-memory cache
├── learning.py          # LearningStore (validated KB + Jaccard RAG + proposals)
├── audit.py             # Keyed (HMAC-SHA256) hash-chain primitives
├── mock_registry.py     # Demo data: assets, seed KB, telemetry
├── persistence.py       # FastAPI lifecycle snapshots for cases, KB, proposals, audit
├── app.py               # FastAPI routes, identity, RBAC, persistence lifecycle
├── demo.py              # End-to-end demo, including AI HARVEST
└── __init__.py          # Public API exports

tests/
├── test_agent_state.py          # Core lifecycle, guardrails, audit tamper detection
├── test_f1_escalation_api.py    # F1: G3 escalation via real API path
├── test_f2_proposals.py         # F2: proposal workflow (approve/reject/rollback/RBAC)
├── test_f3_refrigerant_leak.py  # F3: G2b safety-approval guardrail
├── test_rbac_caps.py            # RBAC capability enforcement
├── test_capture.py / test_capture_review.py  # Expert capture grounding + review flow
├── test_adp_client.py           # ADP v2 SSE client (simulated stream)
├── test_kb_version_label.py / test_persistence.py
├── test_ai_second_opinion.py    # Phase 1: AI second opinion, G9
├── test_identity.py             # Phase 2: signed-cookie identity
├── test_confidence_uplift.py / test_rerun_diagnosis.py  # Phase 3: confidence the KB can move
├── test_no_contradictions.py    # Phase 4: no on-screen contradictions
├── test_contrast.py             # Phase 5: WCAG contrast, both themes
├── test_pill_registry.py        # Phase 6: /pills
├── test_judge_fixes.py          # Rollback UI/label reconciliation, new asset fixtures
├── test_judge_round2_fixes.py   # Round 2 judge findings
├── test_judge_round3_fixes.py   # Round 3 judge findings (governance integrity, identity, capture)
├── test_judge_round4_fixes.py   # Round 4 judge findings (audit coverage, stale knowledge, AI, governance)
├── test_judge_round5_fixes.py   # Round 5 judge findings (reuse payoff, audit coverage, capture, identity)
└── evals/run_evals.py           # EVAL-01..12, `make eval`

docs/
├── ADP_SETUP.md             # Tencent ADP agent configuration
├── IMPLEMENTATION_PATH.md   # Pilot / production / scale, what's real vs. stubbed
└── JUDGE_REPORT_*.md        # Independent judge regrades (Part C), scores never edited

DEMO.md                   # 6-minute click-through script
api_preview.html          # Self-contained API explorer (open in browser)
requirements.txt          # Runtime dependencies
Dockerfile                # python:3.11-slim, exposes :8000
docker-compose.yml        # API + demo services
Makefile                  # test / eval / demo / serve / docker-up / lint / clean
```

---

*Built for the Keppel AI HARVEST hackathon. All cause heuristics and thresholds
are illustrative and require SME validation before production deployment.*