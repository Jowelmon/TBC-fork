# Technical Services Fault Diagnosis Intelligence Pill

A deterministic, audit-ready agent for diagnosing technical-services faults on
critical data-center assets (CRAH units, chillers, pumps, UPS). Built for the
Keppel **AI HARVEST** hackathon.

> **Design principle:** the agent is *LLM-independent and fully deterministic*.
> Given the same observation + evidence it always reaches the same diagnosis,
> the same recommendation, and the same guardrail verdict — so every run is
> auditable and unit-testable. The LLM is an optional narrative layer; the
> safety-critical logic never depends on it.

---

## Architecture

```
                         ┌──────────────────────────────────┐
                         │           FastAPI App             │
                         │   (14 endpoints, RBAC-enforced)   │
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
| `store.py` | ~104 | In-memory `CaseStore` with hash-chain snapshot / audit trace. |
| `learning.py` | ~120 | `LearningStore`: validated-case KB, Jaccard similarity retrieval, `kb_match_score()`, feedback → validated-case write-back. |
| `audit.py` | ~48 | `canonical_json`, SHA-256 `compute_hash`, `GENESIS_HASH` for hash-chain integrity. |
| `mock_registry.py` | ~363 | Demo data: 2 CRAH assets, seed KB (3 validated cases), maintenance history, sensor metadata, BMS status. |
| `app.py` | ~310 | FastAPI app with 14 endpoints, RBAC enforcement, agent-loop driver. |
| `demo.py` | ~212 | 3-case end-to-end demo: happy path → CLOSED, bus failure → ESCALATED, learning loop (kb_match 0.24 → 1.00). |

## Quick Start

### Option A — Docker (recommended)

```bash
# Build and start the API server on :8000
docker compose up --build -d

# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
# Health check at http://localhost:8000/kb/stats

# Run the 3-case demo inside a container
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

# Run the 3-case demo
make demo

# Start the API server with hot reload
make serve
```

### Makefile Targets

| Command | Description |
|---|---|
| `make test` | Run the 62-assertion unit test suite |
| `make demo` | Run the 3-case end-to-end demo |
| `make serve` | Start FastAPI on `localhost:8000` with `--reload` |
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
| `POST` | `/cases/{id}/advance` | Drive the agent loop one transition forward |
| `GET` | `/cases/{id}/evidence` | Retrieve gathered evidence |
| `GET` | `/cases/{id}/diagnosis` | Retrieve diagnosis + candidate causes |
| `GET` | `/cases/{id}/recommendation` | Retrieve draft recommendation |
| `POST` | `/cases/{id}/approval` | Submit human decision (approve / reject / modify) |
| `GET` | `/cases/{id}/work-order` | Retrieve work order status |
| `POST` | `/cases/{id}/work-order` | Create + acknowledge work order (requires prior approval) |
| `POST` | `/cases/{id}/outcome` | Record observed outcome |
| `POST` | `/cases/{id}/feedback` | Submit feedback → writes validated case back to KB |
| `GET` | `/kb/stats` | Knowledge-base statistics (case count, cause distribution) |
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

## Closed-Loop Learning

The system improves itself through a feedback → validation → KB write-back loop
(spec §7):

```
  diagnosis ──▶ human feedback ──▶ ValidatedCase ──▶ LearningStore (KB)
                      │                                      │
                      ▼                                      ▼
                 recorded as                              next diagnosis
                 FeedbackRecord                        retrieves via Jaccard
                                                       similarity → kb_match ↑
                                                       → confidence ↑
```

1. After a case closes, `submit_feedback` records the human-confirmed (or
   corrected) root cause.
2. The feedback becomes a `ValidatedCase` written into `LearningStore`.
3. On the **next** diagnosis, `get_similar()` retrieves matching cases and
   `kb_match_score()` returns a similarity in `[0, 1]`.
4. A higher `kb_match` feeds into the W3 term, raising `confidence` — so
   recurring faults are diagnosed faster and with more confidence.

**Demo proof:** the learning-loop case shows `kb_match` rising from **0.24 →
1.00** and confidence from **0.51 → 0.70** after one feedback cycle.

## RBAC Roles

| Role | Key Permissions |
|---|---|
| `technician` | Create cases, gather evidence, read diagnosis |
| `asset_ops_manager` | Approve/reject/modify recommendations, create work orders, record outcomes |
| `knowledge_steward` | Submit feedback, manage KB |
| `auditor` | Read audit trace, all cases (read-only) |
| `admin` | All permissions |

## Testing

```bash
# Standalone runner (no pytest needed)
make test

# Or with pytest
PYTHONPATH=. python3.11 -m pytest tests/test_agent_state.py -q
```

**62 assertions across 16 test functions**, mapping to spec §8 test cases:

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
| `test_learning_loop` | §7 | Closed-loop: feedback → KB write-back → kb_match 0.24 → 1.00 |
| `test_multi_asset_decision_trees` | §4.2 | Chiller/UPS/pump trees resolve all 15 cause branches deterministically |
| `test_multi_asset_e2e_gather` | §4.2 | `gather_evidence_for_fault` → decision tree end-to-end for 3 asset types |

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
├── store.py            # CaseStore (in-memory)
├── learning.py         # LearningStore (validated KB + Jaccard RAG)
├── audit.py             # SHA-256 hash-chain primitives
├── mock_registry.py     # Demo data: assets, seed KB, telemetry
├── app.py               # FastAPI: 14 endpoints
├── demo.py              # 3-case end-to-end demo
└── __init__.py          # Public API exports

tests/
└── test_agent_state.py  # 16 tests, 62 assertions

api_preview.html          # Self-contained API explorer (open in browser)
requirements.txt          # Runtime dependencies
Dockerfile                # python:3.11-slim, exposes :8000
docker-compose.yml        # API + demo services
Makefile                  # test / demo / serve / docker-up / lint / clean
```

---

*Built for the Keppel AI HARVEST hackathon. All cause heuristics and thresholds
are illustrative and require SME validation before production deployment.*