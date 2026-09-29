# Screen field map — design element → backend reality

For the developer (S) who wires Miora's designs to the existing API. Every
screen below lists the endpoint that feeds it and the exact model fields to
bind. Do NOT invent fields not listed here.

All endpoints require `?user=<role_id>` (RBAC enforced). Base path: the
FastAPI app in `technical_services_pill/app.py` (14 endpoints).

---

## Screen 1 — Asset & Error Dashboard

**Endpoint:** `GET /cases` → list of case snapshots; `GET /cases/{id}` for detail.

| Design element | Backend field |
|----------------|---------------|
| Asset ID | `AgentState.asset_id` |
| Case ID | `case_id` |
| Issue / observation type | `observation.type` (e.g. `temperature_measurement_missing`) |
| Sensor | `observation.sensor_id` |
| Reading status | `observation.reading_status` (absent / invalid / implausible) |
| Workflow status | `current_state` (AgentStateName enum) |
| Confidence badge | `confidence` (float 0–1) |
| Detected at | `observation.detected_at` |
| Entry point (click row) | navigates to Screen 2 |

**State → status pill mapping:**
- `GATHERING_EVIDENCE` / `DIAGNOSING` → neutral "Awaiting diagnosis"
- `AWAITING_APPROVAL` → yellow "Action required"
- `EXECUTING` → blue "In maintenance"
- `AWAITING_FEEDBACK` → neutral "Awaiting feedback"
- `CLOSED` → green "Resolved"
- `ESCALATED` → red "Escalated"

---

## Screen 2 — AI Diagnosis & Recommendation

**Endpoint:** `GET /cases/{id}` → full `AgentState` snapshot.

| Design element | Backend field |
|----------------|---------------|
| Evidence timeline | `evidence[]`: each `EvidenceItem` has `at`, `source`, `type`, `value`, `asset_id` |
| Evidence source tag | `EvidenceItem.source` ∈ bms / sensor / history / config / case_memory |
| Evidence type tag | `EvidenceItem.type` ∈ reading / metadata / status / log |
| Top diagnosis | `diagnosis.top_cause_id`, `diagnosis.cause_label` |
| Candidate causes list | `diagnosis.candidate_causes[]`: `cause_id`, `cause_label`, `evidence_refs` |
| Confidence numeric | `confidence` |
| Confidence band | `confidence < 0.35` → escalate; `0.35–0.55` → medium; `≥ 0.55` → recommendable |
| Recommended action | `recommendation.actions[]`: each `RecommendationAction` = `type`, `target`, `detail`, `kb_refs` |
| Grounding refs | `recommendation.evidence_refs`, `recommendation.kb_refs` |
| Guardrail flags | G1–G8 fired indicators (from guardrail context) |

**Visual rule:** four tiers must be visually distinct — observations (facts),
AI diagnosis, recommendation, (human decision appears on Screen 3).

---

## Screen 3 — Human Decision (Approve / Reject / Modify)

**Endpoint:** `POST /cases/{id}/approval`

| Design element | Backend field / param |
|----------------|----------------------|
| Recommendation shown (read-only) | `recommendation.actions[]` |
| Decision buttons | `decision` ∈ approve / reject / modify |
| Rationale input | `rationale` (required for reject + modify; backend 422 if missing) |
| Modify: action type | `modified_action_type` |
| Modify: action target | `modified_action_target` |
| Modify: action detail | `modified_action_detail` |
| Original actions preserved | `HumanDecisionRecord.original_actions` (kept for governance diff) |
| Reviewer | `decided_by` (= `user`) |
| Timestamp | recorded in audit chain |

**Interaction rules:**
- `approve` → green confirm → advances to EXECUTING (Screen 4)
- `reject` → red, rationale mandatory → ESCALATED
- `modify` → open modified-action form (all three fields required) → EXECUTING with new actions; show side-by-side original vs modified
- If `confidence < 0.35` → no approve/reject panel; show "Escalated — no recommendation (G4)"
- RBAC: actor must hold `approve_reject_modify` capability (asset_ops_manager / admin), else 403

---

## Screen 4 — Maintenance Findings & Verification

**Endpoints:** `POST /cases/{id}/work-order`, `POST /cases/{id}/outcome`

| Design element | Backend field / param |
|----------------|----------------------|
| Work order ID | returned from `POST /work-order` (only valid post-approval, else 409) |
| Work order status | `GET /cases/{id}/work-order` |
| Outcome result | `result` ∈ resolved / unresolved |
| Root cause confirmed | `root_cause_confirmed` (must be a known cause id; backend 400 if unknown) |
| Verified by | `verified_by` (technician) |
| Notes | `notes` |
| Progress timeline | audit-chain entries: recommendation → approval → work-order → outcome |

**Visual:** resolved → green verified; unresolved → red, routes back to escalation.

---

## Screen 5 — Intelligence Pill Summary & Knowledge Governance

**Endpoints:** `GET /kb/stats`, `GET /audit/trace`, `POST /cases/{id}/feedback`

| Design element | Backend field |
|----------------|---------------|
| Pill name / purpose | static: "Technical Services Fault Diagnosis" |
| Diagnostic rules | 4 trees, 24 cause ids (from `KNOWN_FAULT_TYPES`, `KNOWN_CAUSE_IDS`) |
| KB version | `KNOWLEDGE_VERSION` = 1.3.0 |
| Validated case count | `GET /kb/stats` |
| Validated case library | `ValidatedCase`: `case_id`, `asset_id`, `fault_signature`, `confirmed_cause`, `confidence`, `kb_ref` |
| Audit trail (hash chain) | audit entries: `actor`, `action`, `at`, `prev_hash` (SHA-256) |
| Candidate knowledge | `FeedbackRecord` (case_id, confirmed_cause, corrections) → becomes candidate `ValidatedCase` |
| Governance status | candidate = "pending steward review"; NOT auto-applied; version unchanged until steward approves |

**Critical governance visual:** show the gate explicitly —
`AI proposes → steward reviews → validated → version bump (1.3.0 → 1.4.0) → reusable`.
A candidate must never appear as already-approved knowledge.

---

## Notes for the developer

- `user` is a required query param on every endpoint (no default). Use a
  role selector in the UI to pass the right principal.
- All state transitions are hash-chain audited — the timeline on Screens 4–5
  can be built straight from `GET /audit/trace?case_id=...`.
- Confidence thresholds: `MIN_RECO_CONFIDENCE = 0.55`, `ESCALATE_CONFIDENCE = 0.35`.
- RBAC roles: technician, asset_ops_manager, knowledge_steward, auditor, admin.