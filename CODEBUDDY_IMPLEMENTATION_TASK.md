# TBC — CodeBuddy Implementation Task
## PR2 Improvement + Tencent ADP AI Integration

**Repository:** TBC  
**Primary role:** CodeBuddy / S — implementation, integration, testing and review  
**Reference:** `TBC_JUDGMENT_PR2.md`  
**Objective:** Convert the current PR2 prototype into a credible AI Harvest implementation while preserving its existing governance, guardrails, human approval and knowledge-versioning behavior.

---

# 1. Execution Mode

You are acting as the **implementation engineer**, not as a documentation assistant.

Do the following in the repository:

1. Inspect the existing codebase before changing anything.
2. Read the existing architecture, tests and `takeover.md`.
3. Treat the current implementation as the baseline.
4. Implement the changes in this document incrementally.
5. Run the full test suite after each major phase.
6. Do not remove working functionality merely to simplify the implementation.
7. Preserve existing APIs unless a change is necessary.
8. If an implementation detail is uncertain, inspect the repository and existing patterns first.
9. Do not claim a feature is implemented until there is executable code and a test or demonstrable verification for it.
10. At the end, provide files changed, tests run, test result, remaining limitations, and exact commands used to run the application.

# 2. Current Problems To Fix

The PR2 review identified these remaining implementation gaps:

### Critical

1. **No genuine AI/LLM interaction**
   - Current diagnosis is deterministic `if/else`.
   - UI labels parts of the result as AI-generated even though no AI call exists.
   - Guardrail G7 references an LLM but no LLM is currently present.

2. **No persistence**
   - Cases, feedback, proposals and knowledge/version history are currently in-memory.
   - Restarting the application loses state.

3. **Cause-ID mismatch**
   - Decision-tree cause ID and knowledge-base cause ID do not consistently match.
   - Example identified by the review: `comm_bus_failure` vs `communication_bus_controller_failure`.

### Important

4. **Unknown asset can become stuck**
   - Unknown assets may not collect the required evidence count.
   - `begin_diagnosing()` can raise a `ValueError`.
   - The case should instead reach the appropriate escalation path.

5. **UI contains static knowledge-base version information**
   - The UI should display the actual current KB version.

6. **UI needs basic robustness**
   - Loading states, error states, responsive behavior and keyboard accessibility where practical.

# 3. Target Architecture

Do NOT replace the existing deterministic diagnosis system with an uncontrolled LLM.

```text
BMS / Sensor Data
       |
       v
Evidence Tools
       |
       v
Deterministic Decision Tree
       |
       +---- candidate causes
       |
       v
Validated Knowledge Base
       |
       v
Tencent Cloud ADP / LLM
       |
       +---- evidence synthesis
       +---- diagnosis hypothesis
       +---- explanation
       |
       v
Confidence + Guardrails
       |
       v
Human Approval / Rejection / Modification
       |
       v
Maintenance Outcome
       |
       v
Feedback / Knowledge Proposal
       |
       v
Steward Approval
       |
       v
New KB Version
```

### Responsibility boundaries

**Deterministic layer**
- Detect anomalies.
- Gather required evidence.
- Apply known safety rules.
- Produce candidate causes.
- Enforce minimum evidence requirements.

**AI layer**
- Summarise evidence.
- Explain the evidence in natural language.
- Generate a bounded diagnostic hypothesis from supplied evidence.
- Identify supporting and conflicting evidence.
- Never directly control equipment.

**Guardrail layer**
- Validate AI output.
- Prevent unsupported claims.
- Prevent unsafe recommendations.
- Enforce human approval.
- Enforce escalation.
- Prevent AI from publishing knowledge.

**Human layer**
- Approve.
- Reject.
- Modify.
- Confirm maintenance outcome.
- Steward knowledge proposals.

**Knowledge governance layer**
- Store validated outcomes.
- Create pending proposals.
- Require steward approval.
- Version knowledge.
- Support rollback.

# 4. Phase 0 — Repository Inspection

Before editing, inspect at minimum:

```text
decision_tree.py
agent_state.py
guardrails.py
learning.py
store.py
app.py
mock_registry.py
demo.py
tests/
frontend/
takeover.md
requirements.txt / pyproject.toml
```

Also search for:

```text
CAUSE_
root_cause
kb_match
LLM
AI
G7
G5
CaseStore
LearningStore
KB
version
```

Create a short internal implementation plan based on the actual repository structure. Do not create duplicate abstractions if an existing module already provides the required behavior.

# 5. Phase 1 — Canonical Cause Registry

Create a single canonical source of truth for cause IDs, e.g. `cause_registry.py`.

Example structure:

```python
CAUSE_SENSOR_FAULT = "sensor_fault"
CAUSE_COMM_BUS_FAILURE = "communication_bus_controller_failure"
CAUSE_CONTROL_VALVE_FAILURE = "control_valve_failure"
CAUSE_EVAPORATOR_FAN_FAILURE = "evaporator_fan_failure"
CAUSE_REFRIGERANT_LEAK = "refrigerant_leak"
```

The exact IDs must be based on the existing repository and existing KB data.

Update decision tree, KB seed data, guardrails, learning/retrieval, demo cases, tests and frontend labels where applicable so they use the same canonical IDs.

### Acceptance criteria

- No duplicate semantic cause IDs remain.
- Existing demo cases still work.
- KB matching works for the communication-bus scenario.
- Add a regression test proving the cause ID matches across decision tree, KB and learning/retrieval.

# 6. Phase 2 — Unknown Asset Escalation

Fix the current failure where an unknown asset can become stuck because insufficient evidence is available.

Required behavior:

```text
Unknown asset
    |
    v
Attempt available evidence collection
    |
    v
Insufficient evidence
    |
    v
Do NOT crash
    |
    v
Escalate through existing G5 / appropriate escalation mechanism
```

Do not bypass safety requirements merely to obtain a diagnosis.

Represent an appropriate escalation state such as:

```text
status = ESCALATED
reason = INSUFFICIENT_EVIDENCE
```

Use the repository's existing equivalent if one exists.

### Acceptance criteria

Create a regression test:

```text
unknown asset
→ advance()
→ no ValueError
→ escalation reached
→ escalation reason recorded
→ audit event recorded
```

# 7. Phase 3 — Real AI Integration

## 7.1 Goal

Add a genuine LLM interaction through **Tencent Cloud ADP**, while keeping deterministic logic and guardrails authoritative.

The AI must not replace the existing decision tree.

The first implementation should use the LLM for:

1. evidence synthesis
2. diagnostic hypothesis
3. explanation of why the hypothesis is supported
4. identification of missing/conflicting evidence

The LLM must receive structured evidence rather than arbitrary raw application state.

# 8. ADP Integration Boundary

Create an isolated adapter, for example:

```text
ai_reasoning.py
```

or:

```text
llm.py
```

The exact filename should follow the existing architecture.

The rest of the application should call a stable internal interface such as:

```python
result = generate_diagnostic_hypothesis(
    asset=asset,
    observations=observations,
    evidence=evidence,
    candidate_causes=candidate_causes,
    knowledge=validated_knowledge,
)
```

Do not scatter Tencent-specific API calls throughout the application.

# 9. AI Input Contract

Send only the minimum information required.

Conceptual input:

```json
{
  "asset": {
    "asset_id": "CRAH-03",
    "asset_type": "CRAH"
  },
  "observations": {
    "temperature": null,
    "heartbeat": "ACTIVE",
    "power": "NORMAL"
  },
  "evidence": [
    {
      "source": "get_sensor_history",
      "finding": "Temperature readings stopped after 12:55"
    },
    {
      "source": "get_connection_status",
      "finding": "Communication active at 13:07"
    }
  ],
  "candidate_causes": [
    "sensor_fault",
    "communication_bus_controller_failure"
  ],
  "validated_knowledge": []
}
```

Do not send secrets, API keys, internal credentials or unnecessary metadata.

# 10. AI Output Contract

Require structured JSON rather than free-form text.

Target shape:

```json
{
  "hypothesis": "sensor_fault",
  "confidence": 0.78,
  "summary": "The sensor is communicating and powered, but temperature measurement is failing.",
  "supporting_evidence": [
    "Communication remains active",
    "Power is normal",
    "Temperature measurement failed"
  ],
  "conflicting_evidence": [],
  "missing_evidence": [
    "Physical sensor inspection"
  ],
  "recommended_next_check": "Physically inspect and test the temperature sensor and wiring."
}
```

The implementation may use a different exact schema if the existing application has a stronger model, but it must remain machine-validated.

# 11. AI Safety Rules

The LLM must NOT be allowed to:

- approve its own recommendation
- modify the KB directly
- publish a knowledge proposal directly
- bypass guardrails
- bypass evidence requirements
- directly control equipment
- create a maintenance completion event
- override a human rejection
- claim certainty unsupported by evidence
- invent sensor readings
- invent maintenance outcomes
- treat historical cases as proof of the current diagnosis

The AI output is a **hypothesis**, not an authoritative diagnosis.

# 12. AI Failure Behavior

The application must remain functional if ADP/LLM is unavailable.

Required behavior:

```text
ADP available
    → AI hypothesis displayed

ADP timeout/error/unavailable
    → deterministic diagnosis remains available
    → AI status = unavailable
    → human approval still required where applicable
    → audit event records AI failure
```

Do not make the entire incident workflow dependent on a successful LLM call.

Add tests for LLM timeout, malformed response and unavailable service.

# 13. Credentials and Configuration

Never hardcode AppKey, API Secret, credentials or tokens.

Use environment variables, e.g.:

```text
TENCENT_ADP_APP_KEY
TENCENT_ADP_API_SECRET
TENCENT_ADP_ENDPOINT
```

Use the exact naming convention appropriate to the existing project.

Provide `.env.example` with placeholders only. Never commit actual credentials.

# 14. ADP Configuration Expectations

The ADP-side agent should be configured as:

```text
Technical Services Fault Diagnosis Agent
```

Its role:

- receive structured evidence
- use approved knowledge
- synthesize evidence
- generate bounded hypotheses
- explain reasoning
- identify missing evidence

Its role is NOT:

- direct equipment control
- autonomous maintenance execution
- KB publishing
- human approval

If ADP configuration cannot be automated from the repository, document the required manual configuration in:

```text
docs/ADP_SETUP.md
```

Include:

1. Agent name
2. Model
3. Knowledge base
4. System instructions
5. Input format
6. Output format
7. Guardrails
8. App publication requirement
9. AppKey configuration
10. How to test the agent

# 15. Phase 4 — Persistence

Replace the current in-memory-only persistence with SQLite first unless the repository already has a suitable database abstraction.

Recommended module:

```text
database.py
```

Persist at minimum:

```text
cases
case_events
audit_events
feedback
knowledge_proposals
validated_cases
kb_versions
```

Preserve existing store interfaces where possible.

The application should support:

```text
start
→ create case
→ record diagnosis
→ approve/reject
→ record outcome
→ create proposal
→ approve proposal
→ restart
→ recover all persistent state
```

### Acceptance test

A test must create state, restart/reinitialize the store, then verify that the state still exists.

# 16. Phase 5 — Governance Integrity

Preserve the current successful governance behavior.

Required lifecycle:

```text
AI recommendation
      |
      v
AWAITING_APPROVAL
      |
      +---- REJECTED
      |
      +---- APPROVED
      |       |
      |       v
      |   Maintenance
      |       |
      |       v
      |   Technician outcome
      |
      v
Feedback
      |
      v
Pending knowledge proposal
      |
      v
Steward review
      |
      +---- REJECT
      |
      +---- APPROVE
                |
                v
           KB version++
```

The LLM must not alter this lifecycle.

# 17. Phase 6 — UI Changes

Preserve the existing five-screen SPA.

Update the Diagnosis screen so it clearly separates:

### FACTS
Observed sensor/system data.

### DETERMINISTIC ANALYSIS
Rules and candidate causes generated by the deterministic layer.

### AI HYPOTHESIS
Clearly labelled as AI-generated. Display hypothesis, confidence, supporting evidence, conflicting evidence, missing evidence and model/agent status.

### GUARDRAILS
Show guardrails evaluated, blocked actions, escalation state and whether human approval is required.

### HUMAN DECISION
Show pending / approved / rejected / modified, decision maker and timestamp.

Do not present the AI hypothesis as a confirmed diagnosis.

# 18. Dynamic Knowledge Version

Remove hardcoded UI text such as `KB v1.3.0`.

The UI must fetch and display the actual current KB version from the backend.

Acceptance test:

```text
approve proposal
→ KB version changes
→ UI reflects new version
```

# 19. UI Robustness

Add where practical:

- loading state
- API error state
- empty state
- retry action
- responsive layout
- keyboard-focus states
- accessible labels for interactive controls

Do not redesign the entire application. The goal is reliability and clarity, not a visual rewrite.

# 20. Evaluation Suite

Create or extend:

```text
tests/evals/
```

Add tests for:

### EVAL-01 — Genuine AI call
Valid evidence → ADP adapter invoked → structured AI result returned.

### EVAL-02 — AI cannot bypass human approval
AI recommendation → `AWAITING_APPROVAL`, not direct maintenance completion.

### EVAL-03 — AI failure
LLM unavailable → deterministic workflow survives and failure is logged.

### EVAL-04 — Unknown asset
Insufficient evidence → escalation.

### EVAL-05 — Cause IDs
Decision-tree ID equals KB ID for every registered cause.

### EVAL-06 — Persistence
Write → restart → read; state remains.

### EVAL-07 — Feedback governance
Feedback → pending proposal; KB unchanged before steward approval.

### EVAL-08 — Knowledge approval
Approve proposal → KB version increments and validated case is added.

### EVAL-09 — Rollback
Approve → version increases → rollback → target KB state restored.

### EVAL-10 — Audit integrity
Existing SHA-256 audit-chain behavior continues to work.

### EVAL-11 — RBAC
Technician cannot perform steward/AOM-only actions.

### EVAL-12 — No invented evidence
AI output must not introduce sensor values or maintenance facts absent from supplied evidence.

# 21. CRAH-03 Demonstration Case

Ensure the existing CRAH-03 scenario demonstrates the complete architecture.

Expected conceptual flow:

```text
CRAH-03
 temperature = NULL
 heartbeat = ACTIVE
 power = NORMAL
 communication = ACTIVE
 temperature measurement = FAILED

        ↓

Evidence tools

        ↓

Deterministic analysis

Candidate:
- sensor fault
- communication/wiring issue

        ↓

ADP

AI hypothesis:
sensor fault

Supporting evidence:
- sensor powered
- communication active
- temperature measurement failed

Missing evidence:
physical inspection

        ↓

Guardrails

Human approval required

        ↓

AOM approves

        ↓

Maintenance request

        ↓

Technician finds:
sensor faulty
wiring intact

        ↓

Outcome recorded

        ↓

Feedback

        ↓

Pending knowledge proposal

        ↓

Steward approves

        ↓

New KB version
```

The system must not automatically replace the sensor merely because the AI hypothesised a sensor fault.

# 22. Do Not Break These Existing Capabilities

Before declaring completion, verify that these still work:

- RBAC
- AOM approval/rejection/modification
- technician restrictions
- G1-G8 guardrails
- G2b safety approval behavior
- G3 escalation
- escalation close/re-evidence
- feedback proposal workflow
- steward approval/rejection
- KB version increment
- rollback
- SHA-256 audit chain
- five-screen SPA
- demo cases
- existing tests

# 23. Recommended Implementation Order

```text
1. Inspect repository
        ↓
2. Canonical cause registry
        ↓
3. Unknown-asset escalation
        ↓
4. ADP adapter interface
        ↓
5. Structured AI response validation
        ↓
6. AI failure fallback
        ↓
7. Integrate AI into diagnosis flow
        ↓
8. SQLite persistence
        ↓
9. Dynamic KB version in UI
        ↓
10. UI AI/facts/guardrails separation
        ↓
11. Accessibility + error/loading states
        ↓
12. Evaluation suite
        ↓
13. Full regression test
        ↓
14. Demo verification
```

# 24. Definition of Done

### AI

- [ ] A real ADP/LLM call exists.
- [ ] AI output is structured and validated.
- [ ] AI is used for evidence synthesis/hypothesis/explanation.
- [ ] AI cannot directly execute maintenance.
- [ ] AI cannot publish KB changes.
- [ ] AI failure has a safe fallback.

### Diagnosis

- [ ] Deterministic decision tree remains operational.
- [ ] Candidate causes are canonical.
- [ ] AI hypothesis is clearly separated from deterministic findings.
- [ ] Unsupported AI claims are rejected or flagged.

### Governance

- [ ] Human approval remains mandatory for actionable recommendations.
- [ ] Feedback remains pending until steward approval.
- [ ] KB versioning remains functional.
- [ ] Rollback remains functional.
- [ ] Audit chain remains functional.

### Persistence

- [ ] Cases persist.
- [ ] Audit events persist.
- [ ] Feedback persists.
- [ ] Proposals persist.
- [ ] KB versions persist.
- [ ] Restart does not erase state.

### Escalation

- [ ] Unknown assets do not crash the workflow.
- [ ] Insufficient evidence produces escalation.
- [ ] Escalation is visible in UI.

### UI

- [ ] No static KB version.
- [ ] AI hypothesis is visibly labelled as AI-generated.
- [ ] Facts/deterministic analysis/AI/guardrails/human decision are visually distinct.
- [ ] Error/loading states exist.
- [ ] Basic keyboard accessibility works.

### Tests

- [ ] Existing tests pass.
- [ ] New AI tests pass.
- [ ] Persistence tests pass.
- [ ] Cause-ID regression test passes.
- [ ] Unknown-asset regression test passes.
- [ ] Governance tests pass.
- [ ] RBAC tests pass.
- [ ] Audit tests pass.

# 25. Final CodeBuddy Report

After implementation, output exactly:

```text
## IMPLEMENTATION COMPLETE

### 1. Summary
<what was implemented>

### 2. Files Added
- ...

### 3. Files Modified
- ...

### 4. AI Integration
- ADP adapter:
- AI input:
- AI output:
- Failure fallback:

### 5. Persistence
- Database:
- Tables:
- Restart verification:

### 6. Governance
- Human approval:
- Feedback proposal:
- KB versioning:
- Rollback:
- Audit:

### 7. Tests
- Existing tests:
- New tests:
- Total:
- Result:

### 8. Demo Flow
<exact commands and steps>

### 9. Environment Variables
<names only; never print secret values>

### 10. Remaining Limitations
<only genuine remaining limitations>
```

# 26. Important Engineering Rule

Do not make the system *look* more intelligent than it is.

The final product must make this distinction explicit:

```text
DETERMINISTIC RULES
= safety, evidence requirements and bounded logic

AI / ADP
= evidence synthesis, hypothesis and explanation

GUARDRAILS
= prevent unsafe or unsupported behavior

HUMAN
= accountable decision

KNOWLEDGE GOVERNANCE
= validated organisational learning
```

The purpose is not simply to add an LLM. The purpose is to make the existing **Technical Services Fault Diagnosis Intelligence Pill** genuinely AI-enabled while preserving the governance and human-supervision architecture already implemented in PR2.