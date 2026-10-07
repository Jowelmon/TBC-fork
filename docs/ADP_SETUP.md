# Tencent ADP setup for Technical Services Fault Diagnosis

## Agent configuration

- Agent name: Technical Services Fault Diagnosis Agent
- Model: use the enterprise model provisioned for the tenant; no repository-specific hardcoded value is required.
- Knowledge base: the validated technical-services KB and active case history used by the pilot.
- System instructions: use approved technical-services knowledge only, generate bounded hypotheses, explain evidence, identify missing/conflicting evidence, and never directly execute equipment actions.
- Input format: structured JSON with asset metadata, observations, evidence, candidate causes, and validated knowledge (see `technical_services_pill/llm.py: DIAGNOSIS_SYSTEM_PROMPT` / `SYSTEM_PROMPT`).
- Output format: machine-readable JSON with `hypothesis`, `agrees_with_rules`, `summary`, `supporting_evidence`, `conflicting_evidence`, `missing_evidence`, and `recommended_next_check`.
- Guardrails: no direct equipment control, no knowledge publication, no human approval override, and no unsupported certainty claims. The AI second opinion on a diagnosis is advisory only — it never changes `current_state` (see `ai_reasoning.py`).
- App publication requirement: publish the ADP app in the tenant workspace before runtime credentials are used.
- AppKey configuration: set `ADP_APP_KEY` in the environment (from the ADP console: your app > Publish > Service status > API management). Optionally override `ADP_ENDPOINT` (defaults to the international v2 endpoint) and `TBC_LLM_PROVIDER=adp` to opt in (default is `mock`, which runs fully offline).

## How to test the agent

1. Set `ADP_APP_KEY` (and `TBC_LLM_PROVIDER=adp`) in the environment.
2. Run the application in a shell that loads the same environment: `make serve`.
3. Trigger a diagnosis for a known asset such as CRAH-DC1-01 and open its case in `/ui`.
4. Confirm the "AI Second Opinion" card on the Diagnosis screen shows structured output, and that it falls back to "AI offline" safely if the endpoint is unavailable (the deterministic diagnosis is never blocked).
