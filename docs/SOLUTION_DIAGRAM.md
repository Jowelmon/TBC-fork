# Technical Services Intelligence Pill: Solution Diagram & Challenge-Statement Map

**Track:** Real Estate — Keppel · **Challenge:** AI HARVEST — Turning Expert
Know-How into Reusable Intelligence
**Chosen case study / pill:** **Technical Services** (fault diagnosis for CRAH
units, chillers, UPS and pumps). One of the six suggested pills; the other five
are the scale path (see *Point 7* below).

This document does two jobs: it is the **solution diagram** the challenge asks
for, and it is a line-by-line map from each required question to the exact
screen, endpoint, test or demo step that answers it.

---

## 1. The diagram

```
 ┌────────────────────────────── HARVEST (knowledge in) ──────────────────────────────┐
 │                                                                                    │
 │  Experienced technician ──interview──▶ Capture screen (POST /capture/draft)        │
 │  (undocumented know-how)                     │                                     │
 │                                              ▼                                     │
 │                          AI drafts structured heuristics  ◀── llm.py (ADP or       │
 │                          [AI DRAFT — clearly labelled]       offline mock)         │
 │                                              │                                     │
 │                          grounding check: quote must exist verbatim,               │
 │                          otherwise the item is DROPPED (capture.py)                │
 │                                              ▼                                     │
 │                          Capturer reviews: untick / correct cause                  │
 │                          (cannot add words)                                        │
 │                                              ▼                                     │
 │                          Knowledge steward #1 — CANNOT approve own capture         │
 │                                              ▼                                     │
 │                          Knowledge steward #2 approves ──▶ KB version bump         │
 │                                                                  │ rollback-able   │
 └──────────────────────────────────────────────────────────────────┼────────────────┘
                                                                    ▼
 ┌─────────────────────────── OPERATE (decision support) ─────────────────────────────┐
 │                                                                                    │
 │  Technician creates case ──▶ evidence gather (mock BMS/sensors, tools.py)           │
 │                                              ▼                                     │
 │                          Deterministic decision tree ──▶ candidate causes          │
 │                          [DETERMINISTIC — same input, same output]                 │
 │                                              ▼                                     │
 │                          Confidence score (W1-W5: coverage, peers, KB match,       │
 │                          staleness, conflict)                                     │
 │                                              ▼                                     │
 │                          Guardrails G1-G9 ── block / escalate / force approval     │
 │                          [DETERMINISTIC SAFETY LAYER]                              │
 │                                              ▼                                     │
 │                          AI second opinion (advisory; disagreement = G9 flag,      │
 │                          never changes routing)  [AI HYPOTHESIS]                   │
 │                                              ▼                                     │
 │                          Asset Ops Manager: approve / reject / modify + rationale  │
 │                          [HUMAN DECISION — the only way anything executes]         │
 │                                              ▼                                     │
 │                          Work order ──▶ maintenance outcome recorded               │
 └──────────────────────────────────────────────────────────┬─────────────────────────┘
                                                            ▼
 ┌────────────────────────────── LEARN (knowledge out) ───────────────────────────────┐
 │                                                                                    │
 │  Technician / AOM submits feedback ──▶ pending proposal (never a direct KB write)  │
 │                                              ▼                                     │
 │                          Steward reviews ── approve / reject                       │
 │                                              ▼                                     │
 │                          KB version bump + rollback (admin asks, steward countersigns)│
 │                                              ▼                                     │
 │                          Next matching diagnosis retrieves it (Jaccard RAG),       │
 │                          confidence rises — proven in tests/test_confidence_uplift │
 │                                              │                                     │
 │                          Every transition appended to a SHA-256 hash chain         │
 │                          (GET /audit/trace, tamper detection on load)              │
 └────────────────────────────────────────────────────────────────────────────────────┘
```

**The one-line version:** expert → AI draft → human review → second-steward
approval → governed pill → deterministic diagnosis + advisory AI → human
approval → outcome → validated feedback → next diagnosis reuses it faster —
all hash-chained and rollback-able.

---

## 2. The 8 required questions, answered

| # | The challenge asks | Where it lives (verifiable) |
|---|---|---|
| 1 | **The specific business problem** | README § *The pitch*; in-app **Dashboard → "Why this exists"** panel (problem / users / value, with the value claim explicitly marked as an assumption). The problem: fault-diagnosis judgement sits in a few senior technicians' heads and leaves with them. |
| 2 | **Whose expertise is captured, and how undocumented knowledge is obtained** | Capture screen: a structured **interview** with an experienced technician (transcript pasted or loaded from sample), not a document upload — that is the mechanism for knowledge that was never written down. `POST /capture/draft` → `capture.py`. Four visible steps: Interview → AI draft → You review → Second steward approves. |
| 3 | **How captured expertise becomes reusable, not a one-off answer** | Approved heuristics enter the versioned KB (`learning.py`); the next diagnosis with matching **asset type + cause** surfaces them under **Expert Knowledge Reused** with expert name, knowledge ID, KB version and verbatim quote. Confidence W3 (`kb_match`) rises measurably: `tests/test_confidence_uplift.py`, `make demo` CASE 3. |
| 4 | **How an AOM uses, supervises, verifies, and sees when escalation is required** | **AOM Decision** screen: recommendation with confidence breakdown, G2b hazard banner next to Approve/Reject, approve/reject/modify with rationale (the only path to a work order). Escalation is explicit: G3 cross-pill routing, G4 low confidence, G5 unknown asset, G2 safety-critical — visible as **Resolve Escalation** with a reason box. `POST /cases/{id}/approval`, RBAC `approve_reject_modify`. |
| 5 | **Why this is more than a chatbot / retrieval tool** | Three structural reasons: (a) **deterministic decision trees + 9 guardrails** run *before* any human sees a recommendation — a chatbot has no refusal logic; (b) **governance** — no knowledge goes live without a second steward, every version rollback-able; (c) **accountability** — RBAC, signed session cookies, and a SHA-256 hash chain where AI explicitly *cannot* approve, execute or publish (G8 rejects ungrounded output). The AI layer is deliberately bounded to drafting and advice. |
| 6 | **How feedback is reviewed, validated, versioned and approved before incorporation** | `POST /cases/{id}/feedback` → pending proposal (never a direct write) → `/kb/queue` → steward approves → KB version bump → `/kb/rollback/{version}` restores exactly. Tests: `test_f2_proposals.py`, `test_confidence_uplift.py`, EVAL-07/09. |
| 7 | **How it extends from one asset to multiple assets / business units** | Pill-by-pill design: **4 asset classes already implemented** behind one dispatcher (`_FAULT_EVALUATORS` — add a new class by writing one evaluator function); `GET /pills` Pill Registry shows owner steward, KB version and approval rate per pill; cross-domain issues route out via guardrail **G3**. Scale path for multi-site KB partitioning: `docs/IMPLEMENTATION_PATH.md` Stage 3. |
| 8 | **A credible path to implementation with current/near-term technology** | `docs/IMPLEMENTATION_PATH.md`: Stage 1 pilot (what is real vs stubbed today, named seams to swap), Stage 2 production on Tencent Cloud (existing Dockerfile, managed DB, secret manager, CMMS integration), Stage 3 scale. Container runs today: `docker compose up --build`. |

---

## 3. "The Solution Should Be" — where each quality shows

| Quality | Where it shows |
|---|---|
| **Human-supervised** | G6 forces `AWAITING_APPROVAL` for *every* action; AOM is the only role with `approve_reject_modify`; AI second opinion is advisory-only (G9 never routes). |
| **Transparent** | Every card is layer-labelled: `DETERMINISTIC`, `AI hypothesis`, `Deterministic guardrails`, `HUMAN DECISION`; confidence W1–W5 factor bars; knowledge reuse shows the expert's verbatim quote. |
| **Accountable** | 5-role RBAC, named demo users, session-cookie identity (spoofing tested), every state transition recorded with actor + timestamp in the audit chain. |
| **Reliable** | 342 pytest + 13 acceptance evals; deterministic diagnosis (same input → same output); confidence thresholds are named constants, not magic numbers. |
| **Reusable** | Validated cases stored as KB knowledge, retrieved by similarity on the next matching fault — reuse is shown on screen, not claimed. |
| **Scalable** | 4 asset types already behind one dispatcher; Pill Registry for per-pill ownership; documented multi-site path. |
| **Governed** | Proposal → second-steward approval → version bump → rollback; self-approval returns 403 server-side. |
| **Portable** | Plain Python knowledge (data, not prompts), no vendor lock: `llm.py` provider seam (`mock`/`adp`), SQLite→Postgres seam documented; organisation owns the KB export. |
| **Version-controlled** | `/kb/versions` lists every version with a displayed label; `/kb/rollback/{version}` asks for a rollback, which the pill's steward countersigns at `/kb/rollback-requests/{id}/countersign`. Exact and tested. |
| **Secure** | Signed session cookies, RBAC on every endpoint, `.env` gitignored, AppKey never committed, G7 sanitises prompt-injection patterns before any model sees metadata. |
| **Clearly bounded** | Banned-action regex (G1: setpoint/interlock/firmware) blocks + escalates; unknown cause IDs rejected; AI cannot invent evidence refs (G8) or introduce causes outside the registry. |

## 4. "What the Solution Should Solve" — coverage

| Requirement | Coverage |
|---|---|
| Capture expert know-how | Capture screen, four-step review flow, verbatim grounding check. |
| Turn know-how into governed intelligence | Versioned KB with ownership (Pill Registry), decision logic, guardrails, approval requirements. |
| Apply specialist AI support | AI capture drafter + advisory second opinion (`ai_reasoning.py`); pills and agents are deliberately *not* 1:1. |
| Coordinate across domains | Guardrail **G3**: a cause owned by another pill is cross-referenced and escalated to that pill's owner ("Who to call" shown), demoable in the ESCALATED case. |
| Keep people in control | G6 + RBAC + AOM rationale; AI never approves, executes or publishes. |
| Learn through governed feedback | Feedback → proposal → steward approval → KB write-back → confidence uplift, all tested. |
