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
                              │  G1-G8            │
                              └───────────────────┘
```

**Request flow:** observation → trigger → gather evidence → decision tree →
confidence score → guardrails (G1-G8) → recommendation → human approval →
work order → outcome → feedback → **validated case written back to KB**
(closed-loop learning).

## Module Responsibilities

| Module | Lines | Responsibility |
|---|---|---|
| `models.py` | ~260 | Pydantic v2 data models, enums, threshold constants. Core 8 agent-state fields: `asset_id`, `observation`, `evidence`, `diagnosis`, `confidence`, `recommendation`, `human_decision`, `outcome`. |
| `agent_state.py` | ~444 | Deterministic state machine (11 states, 16 transitions), hash-chain audit history, lifecycle helpers (`trigger`, `add_evidence`, `complete_diagnosis`, `propose_recommendation`, `record_human_decision`, `record_outcome`, `queue_feedback`, `close`, `escalate`). |
| `guardrails.py` | ~162 | LLM-independent guardrail engine G1-G8. Runs *before* any recommendation reaches a human or any work order is created. |
| `decision_tree.py` | ~351 | Executable causal decision tree Q1-Q7 for "temperature measurement missing" on a CRAH unit. Produces 8 candidate causes. |
| `confidence.py` | ~40 | Confidence scorer: `w1·coverage + w2·peer + w3·kb_match − w4·staleness − w5·conflict`. |
| `tools.py` | ~470 | Agent tool layer: evidence gatherer, diagnosis orchestrator, guardrail checker, recommendation proposer, work-order creator, feedback submitter. |
| `rbac.py` | ~117 | 5-role RBAC matrix (technician, asset_ops_manager, knowledge_steward, auditor, admin). Permission checks via `can()` / `require()`. |
| `store.py` | ~104 | SQLite-backed `CaseStore` with a memory cache and hash-chain audit trace. |
| `learning.py` | ~120 | `LearningStore`: validated-case KB, Jaccard similarity retrieval, `kb_match_score()`, feedback → validated-case write-back. |
| `audit.py` | ~48 | `canonical_json`, SHA-256 `compute_hash`, `GENESIS_HASH` for hash-chain integrity. |
| `mock_registry.py` | ~363 | Demo data: 2 CRAH assets, seed KB (3 validated cases), maintenance history, sensor metadata, BMS status. |
| `app.py` | — | FastAPI app with RBAC, persistence lifecycle, and the agent-loop driver. |
| `demo.py` | — | End-to-end lifecycle, multi-asset routing, and AI HARVEST capture-to-reuse demo. |

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
pip install -r requirements.txt
make serve          # = PYTHONPATH=. uvicorn frontend.serve:app --port 8000
```

Open `http://localhost:8000/ui`, then click **Seed Demo Cases** to populate
the dashboard with one CLOSED, one ESCALATED, and one AWAITING_APPROVAL
example. Cases are not seeded automatically. Use the role switcher (top
right) to see RBAC in action. See `frontend/README.md` for details.

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
| `POST` | `/cases/{id}/approval` | Submit human decision (approve / reject / modify) |
| `GET` | `/cases/{id}/work-order` | Retrieve work order status |
| `POST` | `/cases/{id}/work-order` | Create + acknowledge work order (requires prior approval) |
| `POST` | `/cases/{id}/outcome` | Record observed outcome |
| `POST` | `/cases/{id}/feedback` | Submit feedback → creates pending proposal (F2) |
| `GET` | `/kb/stats` | Knowledge-base statistics (case count, cause priors, pending proposals) |
| `GET` | `/kb/queue` | List pending knowledge proposals (steward/admin only) |
| `POST` | `/kb/proposals/{id}/approve` | Approve a proposal → ingests into KB, bumps version (steward/admin) |
| `POST` | `/kb/proposals/{id}/reject` | Reject a proposal (steward/admin) |
| `POST` | `/kb/rollback/{version}` | Roll back KB to a target version (admin only) |
| `GET` | `/audit/trace` | Full hash-chain audit trail with tamper detection |

> Interactive Swagger docs at `/docs`, ReDoc at `/redoc` once the server is running.

## Guardrail Engine (G1-G8)

All guardrails are **pure Python, deterministic, and LLM-independent**. They run
*before* any recommendation reaches a human and *before* any work order is
created (spec §4.4, Layer 4).

| Rule | Trigger | Action |
|---|---|---|
| **G1** | Recommendation implies a BMS setpoint / interlock / safety-system / firmware change | Block + escalate |
| **G2** | Fault classified safety-critical (cooling lost **AND** temperature rising) | Must escalate |
| **G2b** | Cause involves environmental/pressure hazard (e.g. refrigerant leak) | Force `AWAITING_APPROVAL` with safety flag (does NOT auto-escalate) |
| **G3** | Root cause maps to another pill's domain (chiller, power, BMS bus, leasing, tenant) | Coordinate + escalate |
| **G4** | `confidence < ESCALATE_CONFIDENCE` (0.35) | Escalate, do not recommend |
| **G5** | Asset not in registry / unknown asset | Escalate (short-circuit, no diagnosis) |
| **G6** | Any recommended action | Force `AWAITING_APPROVAL` — no auto-execute |
| **G7** | Sensor metadata / tag name contains prompt-injection patterns | Sanitize before LLM sees it |
| **G8** | Recommendation not grounded in `kb_refs` **and** `evidence_refs` | Reject as ungrounded (anti-hallucination) |

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

| Cause ID | Label | Default Action |
|---|---|---|
| `comm_bus_failure` | Communication bus / controller failure | `controller_inspection` → escalate to BMS vendor |
| `config_drift` | Configuration drift (tag missing/renamed) | `config_remap` → HITL |
| `loose_wiring` | Loose wiring / connection disturbed during service | `onsite_inspection` → HITL |
| `sensor_hardware_failure` | Sensor hardware failure (RTD/thermistor dead) | `sensor_replacement` → HITL |
| `data_path_drop` | Data-path drop (telemetry transport) | `path_restore` → cross-coordinate with IT/Ops |
| `intermittent_fault` | Intermittent sensor fault / borderline failure | `onsite_inspection` → HITL (lower confidence) |
| `sensor_drift` | Sensor drift | `sensor_recalibration` → HITL |
| `sensor_fault_noise` | Sensor fault or electrical noise | `sensor_inspection` → HITL |

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
| W2 | 0.20 | `peer_agreement` | do peer sensors / adjacent assets corroborate? (1.0 = full corroboration) |
| W3 | 0.25 | `kb_match` | Jaccard similarity to validated past cases in the KB (RAG) |
| W4 | 0.10 | `data_staleness` | penalty: telemetry older than freshness SLA |
| W5 | 0.15 | `conflict_penalty` | penalty: contradictions in evidence |

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
5. An admin can **roll back** the KB to a prior version via `/kb/rollback/{version}`,
   removing all cases added after that version.

**Demo proof:** the learning-loop case shows `kb_match` rising from **0.73 →
1.00** and confidence from **0.63 → 0.70** after one approved feedback cycle.

**Separation of actors:** whoever proposes a change can never approve it.
`approve_proposal` returns 403 if the approver is the proposer, and the
proposer is always the authenticated caller (a client-supplied
`submitted_by` is ignored). Demo users `steward1` and `steward2` exist so
the second-reviewer rule can be shown live.

## Expert Knowledge Capture (LLM drafts, steward approves)

The challenge's hardest requirement is capturing know-how that was never
written down. The **Capture** screen (`POST /capture/interview`) takes an
interview with an experienced technician and runs:

```
interview transcript
   │  G7: instruction-like text redacted before any model sees it
   ▼
LLM extraction (llm.py)  ──▶  symptom, likely cause, checks, never-do,
   │                          escalate-when, verbatim evidence quote
   ▼
grounding check: any item whose quote is not in the transcript is DROPPED
cause check:     causes outside the known universe are flagged "new:<slug>"
   ▼
pending proposal ──▶ a DIFFERENT knowledge steward approves ──▶ live KB
                                                     (version bump, rollback-able)
```

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
| `mock` (default) | Deterministic offline extractor, so the demo runs without keys. Labelled "Offline mock model" in the UI. |
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

## RBAC Roles

| Role | Key Permissions |
|---|---|
| `technician` | Create cases, gather evidence, read diagnosis |
| `asset_ops_manager` | Approve/reject/modify recommendations, create work orders, record outcomes, capture expert interviews |
| `knowledge_steward` | Submit feedback, capture expert interviews, approve another steward's proposals |
| `auditor` | Read audit trace, all cases (read-only) |
| `admin` | All permissions |

## Testing

```bash
make test        # = PYTHONPATH=. python3 -m pytest tests/ -q
```

**50 tests** (verified with `make test`) cover spec §8 cases, F1-F7
acceptance, governance, persistence, and expert capture:

| Test | Spec | Verifies |
|---|---|---|
| `test_tc1_happy_path` | TC1 | Full lifecycle: trigger → diagnose → approve → work order → outcome → closed |
| `test_tc2_bus_dead_escalates` | TC2 | Bus failure triggers G3 cross-domain escalation |
| `test_tc5_safety_critical` | TC5 | G2 safety-critical forces escalation |
| `test_tc6_low_confidence` | TC6 | G4 low-confidence blocks recommendation |
| `test_tc7_modify_keeps_originals` | TC7 | Modified approval preserves original recommendation |
| `test_tc11_ungrounded` | TC11 | G8 rejects ungrounded recommendation |
| `test_g1_banned_action` | — | G1 blocks BMS setpoint / interlock / firmware actions |
| `test_g5_unknown_asset` | — | G5 short-circuits on unknown asset |
| `test_g7_sanitize_metadata` | — | G7 redacts prompt-injection patterns |
| `test_illegal_transition` | — | State machine rejects illegal transitions |
| `test_reject_closes` | — | Rejection transitions to CLOSED |
| `test_full_lifecycle` | — | Complete 9-state traversal with hash-chain integrity |
| `test_audit_tamper_detected` | — | Tampering with audit history breaks the SHA-256 chain |
| `test_learning_loop` | §7 | Closed-loop: feedback → proposal → approve → KB write-back |
| `test_multi_asset_decision_trees` | §4.2 | Chiller/UPS/pump trees resolve all 15 cause branches deterministically |
| `test_multi_asset_branch_isolation` | §4.2 | Branch isolation across fault types |
| `test_f1_escalation_via_api` | F1 | CRAH-DC1-02 reaches ESCALATED with G3 via real API path |
| `test_f1_no_hardcoded_confidence` | F1 | Confidence is real (not hardcoded 0.8) |
| `test_f2_feedback_creates_pending_proposal` | F2 | Feedback creates a pending proposal, not direct KB write |
| `test_f2_approve_proposal_ingests_into_kb` | F2 | Steward approval ingests case + bumps KB version |
| `test_f2_reject_proposal_does_not_enter_kb` | F2 | Rejected proposals never enter the KB |
| `test_f2_rollback_removes_approved_cases` | F2 | Rollback removes cases added after target version |
| `test_f2_rbac_kb_queue_requires_steward` | F2 | Only steward/admin can view the queue |
| `test_f2_rbac_rollback_requires_steward` | F2 | Only admin can rollback |
| `test_fastapi_runtime_restores_and_saves_state` | Persistence | FastAPI restores at startup and snapshots successful mutations |
| `test_case_surfaces_approved_expert_knowledge_for_matching_diagnosis` | AI HARVEST | Diagnosis exposes approved heuristics matching cause + asset type |
| `test_f3_refrigerant_leak_routes_to_awaiting_approval` | F3 | Chiller refrigerant leak → AWAITING_APPROVAL (not ESCALATED) |
| `test_f3_guardrail_names_g2b` | F3 | G2b in rule_ids, requires_approval=True, must_escalate=False |
| `test_enforced_capabilities_are_declared` | RBAC | Declared capabilities match enforced set |
| `test_core_capabilities_enforced` | RBAC | Core capability enforcement works |
| `test_phantom_capabilities_are_known_demo_scope` | RBAC | Phantom caps are documented demo scope |

## Audit Integrity

Every state transition appends a record to a **SHA-256 hash chain** (spec §6):

```
record_n.prev_hash = SHA-256(canonical_json(record_{n-1}))
```

- `GENESIS_HASH` anchors the chain head.
- `verify_audit_chain()` recomputes the chain and detects any tampering.
- RBAC ensures only authorized roles can advance states; all actions are
  recorded with actor, timestamp, and transition name.

## Project Structure

```
technical_services_pill/
├── models.py            # Pydantic v2 models, enums, thresholds
├── agent_state.py       # State machine + hash-chain audit
├── guardrails.py        # G1-G8 deterministic engine
├── decision_tree.py     # Q1-Q7 causal tree, 8 causes
├── confidence.py        # W1-W5 scoring formula
├── tools.py            # Agent tool layer
├── rbac.py             # 5-role RBAC matrix
├── store.py            # SQLite-backed CaseStore + in-memory cache
├── learning.py         # LearningStore (validated KB + Jaccard RAG)
├── audit.py             # SHA-256 hash-chain primitives
├── mock_registry.py     # Demo data: assets, seed KB, telemetry
├── persistence.py       # FastAPI lifecycle snapshots for cases, KB, proposals, audit
├── app.py               # FastAPI routes, RBAC, persistence lifecycle
├── demo.py              # End-to-end demo, including AI HARVEST
└── __init__.py          # Public API exports

tests/
├── test_agent_state.py     # 16 core tests (spec TC1-TC11 + lifecycle + audit)
├── test_f1_escalation_api.py  # F1: G3 escalation via real API path
├── test_f2_proposals.py    # F2: Proposal workflow (approve/reject/rollback/RBAC)
├── test_f3_refrigerant_leak.py  # F3: G2b safety-approval guardrail
└── test_rbac_caps.py       # RBAC capability enforcement

api_preview.html          # Self-contained API explorer (open in browser)
requirements.txt          # Runtime dependencies
Dockerfile                # python:3.11-slim, exposes :8000
docker-compose.yml        # API + demo services
Makefile                  # test / demo / serve / docker-up / lint / clean
```

---

*Built for the Keppel AI HARVEST hackathon. All cause heuristics and thresholds
are illustrative and require SME validation before production deployment.*