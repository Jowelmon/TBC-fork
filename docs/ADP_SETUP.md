# Tencent ADP setup for Technical Services Fault Diagnosis

## Agent configuration

- Agent name: Technical Services Fault Diagnosis Agent
- Model: use the enterprise model provisioned for the tenant; no repository-specific hardcoded value is required.
- Knowledge base: the validated technical-services KB and active case history used by the pilot.
- System instructions: use approved technical-services knowledge only, generate bounded hypotheses, explain evidence, identify missing/conflicting evidence, and never directly execute equipment actions.
- Input format: structured JSON with asset metadata, observations, evidence, candidate causes, and validated knowledge.
- Output format: machine-readable JSON with `hypothesis`, `confidence`, `summary`, `supporting_evidence`, `conflicting_evidence`, `missing_evidence`, and `recommended_next_check`.
- Guardrails: no direct equipment control, no knowledge publication, no human approval override, and no unsupported certainty claims.
- App publication requirement: publish the ADP app in the tenant workspace before runtime credentials are used.
- AppKey configuration: set `TENCENT_ADP_APP_KEY`, `TENCENT_ADP_API_SECRET`, and `TENCENT_ADP_ENDPOINT` in the environment.

## How to test the agent

1. Populate the environment variables.
2. Run the application in a shell that loads the same environment.
3. Trigger a diagnosis for a known asset such as CRAH-DC1-01.
4. Confirm the ADP response is structured JSON and that the system falls back safely if the endpoint is unavailable.
