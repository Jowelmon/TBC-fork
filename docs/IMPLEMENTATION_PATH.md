# Implementation path

Three stages from this repo to a real Keppel deployment. Each stage lists
what is **real** (implemented, tested, running today) versus **stubbed**
(mocked for the demo, with a clear seam to replace it) so nothing here
overstates where the build actually is.

## Stage 1 — Pilot (one asset class, one site)

**Real today:**
- Deterministic decision tree for CRAH, Chiller, UPS and Pump faults
  (`technical_services_pill/decision_tree.py`), with guardrails G1-G9
  (`guardrails.py`) and a confidence score computed from real peer-sensor
  and evidence signals (`confidence.py`).
- Full governance loop: expert interview → AI draft → capturer review →
  a *different* knowledge steward approves → reused in diagnosis
  (`capture.py`, `learning.py`). Self-approval is blocked; rollback
  restores a prior KB version exactly (`tests/test_confidence_uplift.py`).
- Signed-cookie session identity (`auth.py`) and RBAC for six roles
  (`rbac.py`).
- Tamper-evident, hash-chained audit trail on every state transition
  (`audit.py`).
- SQLite persistence that survives a restart (`database.py`, `TBC_PERSIST`).
- AI second opinion on a diagnosis, advisory only, never routes
  (`ai_reasoning.py`) — works offline (`TBC_LLM_PROVIDER=mock`, the
  default) or against the published Tencent Cloud ADP app
  (`TBC_LLM_PROVIDER=adp`, see `docs/ADP_SETUP.md`).

**Stubbed, with the seam to replace it:**
- `mock_registry.py` is five hardcoded assets with static telemetry, not
  a live BMS/SCADA feed. The gatherers in `tools.py`
  (`gather_evidence_for_case`, `gather_evidence_for_fault`) are the seam:
  point them at a real BMS/historian API and nothing else in the
  diagnosis path changes.
- `PILL_OWNERS` in `app.py` is a fixed two-steward assignment, not sourced
  from a roster system.
- The six demo users in `rbac.DEMO_USERS` are not a real identity
  provider; `auth.py`'s `/login` is the integration point for SSO.
- `TBC_SECRET` auto-generates per process if unset — fine for a pilot
  behind a single long-running instance, not for production (see Stage 2).

**What a pilot needs before go-live:** real telemetry wired into
`tools.py`'s gatherers for one asset class at one site; the assumed
thresholds in `confidence.py`, `models.py` and `decision_tree.py`
(marked `【ASSUMPTION】` throughout) validated against Keppel
technical-services SMEs; SSO in place of the demo user list.

## Stage 2 — Production on Tencent Cloud

- Containerised deploy via the existing `Dockerfile` /
  `docker-compose`-style `make docker-up`, onto Tencent Cloud compute.
- Replace SQLite (`database.py`) with a managed database (e.g. TencentDB
  for PostgreSQL) for concurrent write durability beyond a single
  instance — `database.py`'s `SQLiteStore` is the seam to swap.
- `ADP_APP_KEY` / `TBC_SECRET` move from `.env` to Tencent Cloud's secret
  manager; `auth.py`'s `_SECRET` resolution and `llm.py`'s
  `ADP_APP_KEY` read are both already environment-variable-driven, so
  this is a deployment change, not a code change.
- Real CMMS/work-order integration: `tools.py`'s
  `create_work_order_for_state` currently mints a local work order id;
  the seam is that one function.
- Monitoring on the audit chain (`verify_audit_chain`) and on guardrail
  firing rates (G1-G9), so a spike in escalations or G9 AI/rules
  disagreement is visible to ops, not just to whoever opens a case.

## Stage 3 — Scale beyond one asset / one site

- Today's "pill" is an asset *type* (CRAH/Chiller/UPS/Pump) sharing one
  knowledge base (`learning.LearningStore` is a single in-process
  singleton, `STORE`) — real multi-site scale needs either KB
  partitioning per site/business-unit or an explicit cross-site sharing
  policy, decided with Keppel governance stakeholders, not assumed here.
- Extend `decision_tree.py` and `mock_registry.py`'s asset model to
  additional equipment types and sites (`site_id`, currently hardcoded
  to `DC-SINGAPORE-1` for every asset).
- Replace the fixed `PILL_OWNERS` registry with real per-site/per-pill
  governance ownership, and extend RBAC (`rbac.py`) past the single-site
  six-role model if multiple sites need independent stewards.
- Aggregate confidence/`kb_match` signals across sites so a validated
  fix at one site can (with appropriate review) inform confidence at
  another, without silently trusting unvalidated cross-site data.

---

Every item under "real today" is reproducible by `make test`, `make
demo`, or `make eval`, or visible in `/ui` — see `README.md`.
