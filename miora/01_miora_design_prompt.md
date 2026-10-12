# PROMPT — paste into Miora (UI/UX design agent)

Act as a senior UI/UX designer working on an enterprise AI-powered facility
operations platform for Keppel.

Design the user interface for our project, **Technical Services Fault
Diagnosis**, an AI Intelligence Pill that detects abnormal conditions in
Computer Room Air Handler (CRAH) units and recommends maintenance actions
under human supervision.

Our **backend and agent workflow have already been specified and
implemented.** Your task is strictly UI/UX design — not backend development,
not diagnostic logic, not knowledge management. A separate developer (S) will
connect your designs to the existing APIs, so every field you show must map
to a real backend field (a field map is provided at the end).

---

## Design five screens

1. **Asset & Error Dashboard**
2. **AI Diagnosis & Recommendation**
3. **Human Decision (Approve / Reject / Modify)**
4. **Maintenance Findings & Verification**
5. **Intelligence Pill Summary & Knowledge Governance**

## Use this incident as the worked example

```
Asset:        CRAH-03  (CRAH-DC1-01, sensor SA-TEMP-01)
Issue:        No temperature detected (reading absent > 5 min)
Severity:     HIGH
Evidence:
  - temperature readings missing since 13:00
  - heartbeat ACTIVE
  - sensor power NORMAL
  - communication ACTIVE
  - no comm errors logged
  - temperature measurement FAILED
Diagnosis:    sensor_hardware_failure  (likely sensor/measurement fault)
Confidence:   MEDIUM  (numeric 0.72; threshold for recommendable = 0.55)
Recommendation: onsite_inspection — physically inspect sensor at
                CRAH-DC1-01 / SA-TEMP-01   (kb_ref: kb:technical_services:crah_tree:v1)
Human decision: Approved  (by asset_ops_manager, with rationale)
Work order:   WO-...  raised after approval
Technician finding: sensor faulty, wiring intact
Outcome:      resolved — sensor replaced, temperature restored
              root_cause_confirmed = sensor_hardware_failure
```

## Design requirements

- Create a **coherent enterprise dashboard** with a clear information hierarchy.
- Use **tables, status cards, evidence panels, and timelines**.
- **Semantic colour:**
  - Red = critical issue / rejected
  - Green = approved / verified / resolved
  - Yellow = medium confidence
  - Neutral/grey = pending / background
- Clearly **distinguish** four tiers of information:
  1. Sensor observations (facts)
  2. AI diagnosis + confidence (AI-generated)
  3. Recommended action (AI-generated)
  4. Human decision + outcome (human-validated)
- Demonstrate the workflow from issue detection → verified maintenance outcome.
- Include **reusable components** and consistent navigation (persistent left
  rail or top bar across all five screens).
- Make the design suitable for a **live demonstration and competition
  presentation**.
- **Accessibility:** consistent contrast, readable labels, icons always
  accompanied by text.

## Interaction states to map

- **Approve** → green confirmation, advances workflow to "Work order raised".
- **Reject** → red, **rationale is required** (backend enforces this), case escalates.
- **Modify** → **modified action fields are required** (action_type, target,
  detail); the **original recommendation is preserved** alongside the modified
  one for governance.
- **Verification** → technician records outcome; resolved (green) or unresolved
  (red).
- Low confidence (< 0.35) → system shows **escalated, no recommendation**
  rather than an approve/reject panel.

## Produce

1. High-fidelity mockups for all five screens.
2. A reusable component + colour system spec.
3. Consistent navigation / page hierarchy.
4. Interaction-state diagrams for approve / reject / modify / verification.
5. A clickable prototype or equivalent visual walkthrough if supported.
6. Presentation-ready visuals for the competition slides.

Ensure the designs can be implemented by a separate developer using an
existing backend — do not invent backend behaviour that does not exist.

---

## Appendix — backend field map (for design accuracy, not for Miora to implement)

Every label below maps to a real field returned by the existing API. Design
the screens around these; do not invent new fields.

### Screen 1 — Asset & Error Dashboard (endpoint: `GET /cases`)
- `case_id`, `asset_id`, `observation.type`, `observation.reading_status`
- `current_state` (state machine: GATHERING_EVIDENCE → DIAGNOSING →
  AWAITING_APPROVAL → EXECUTING → AWAITING_FEEDBACK → CLOSED / ESCALATED)
- `confidence` (0.0–1.0), severity derived from state + confidence
- Row click → Screen 2

### Screen 2 — AI Diagnosis & Recommendation (endpoint: `GET /cases/{id}`)
- `evidence[]` → each: `at`, `source` (bms/sensor/history/config/case_memory),
  `type` (reading/metadata/status/log), `value`
- `diagnosis.top_cause_id`, `diagnosis.cause_label`, `diagnosis.candidate_causes[]`
  (each: `cause_id`, `cause_label`, `evidence_refs`)
- `confidence` (numeric) + band: `<0.35` escalation / `0.35–0.55` medium /
  `≥0.55` recommendable
- `recommendation.actions[]` → each: `type`, `target`, `detail`, `kb_refs`
- `recommendation.evidence_refs`, `recommendation.kb_refs`
- Guardrail indicators (G1–G8) when fired — show as badges/banners

### Screen 3 — Human Decision (endpoint: `POST /cases/{id}/approval`)
- Shows recommendation + supporting evidence (read-only)
- Decision control: `approve` / `reject` / `modify`
- `rationale` (required for reject/modify)
- On modify: `modified_action_type`, `modified_action_target`,
  `modified_action_detail` → builds `modified_actions`; `original_actions`
  preserved
- Captures `decided_by`, timestamp
- RBAC: only `asset_ops_manager` / `admin` may act (show role context)

### Screen 4 — Maintenance Findings & Verification
- Work order: `POST /cases/{id}/work-order` (only after approval, else 409)
  → returns `work_order_id`
- Outcome: `POST /cases/{id}/outcome`
  - `result`: resolved / unresolved
  - `root_cause_confirmed`: must be a known cause id (validated → 400 if unknown)
  - `verified_by`, `notes`
- Timeline: recommendation → approval → work order → outcome (audit-chain backed)

### Screen 5 — Intelligence Pill Summary & Knowledge Governance
- KB stats: `GET /kb/stats` → validated case count, KB version (1.3.0),
  causes covered
- Audit trace: `GET /audit/trace` → hash-linked entries (actor, action,
  timestamp, prev_hash)
- Candidate knowledge (from feedback): `POST /cases/{id}/feedback` writes a
  candidate ValidatedCase — show as **pending steward review**, NOT auto-applied
- Governance gate visual: AI proposes → steward reviews → validated → version
  bump → reusable