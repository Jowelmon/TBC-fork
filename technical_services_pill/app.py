"""FastAPI app for the Technical Services Fault Diagnosis pill (spec §5).

Endpoints:
    POST   /cases                         create a case (trigger diagnosis)
    GET    /cases                          list case ids
    GET    /cases/{id}                     full state snapshot
    GET    /cases/{id}/evidence            evidence bundle
    GET    /cases/{id}/diagnosis           ranked diagnosis
    GET    /cases/{id}/recommendation      recommendation + guardrail result
    POST   /cases/{id}/approval            HITL approve/reject/modify  (manager)
    GET    /cases/{id}/work-order          work order id
    POST   /cases/{id}/outcome             record maintenance outcome  (technician)
    POST   /cases/{id}/feedback            submit feedback             (steward)
    GET    /audit/trace                    tamper-evident audit trail   (auditor)

Identity via a signed session cookie set by ``POST /login`` (see ``auth.py``);
``?user=<demo_user_id>`` is a fallback only under ``TBC_DEMO_INSECURE=1``.
RBAC capabilities are mapped per role in ``rbac.DEMO_USERS``.
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .agent_state import AgentState
from .ai_reasoning import generate_diagnostic_hypothesis
from .auth import (
    check_pin,
    clear_cookie,
    demo_insecure,
    issue_cookie,
    issue_unlock,
    locked_for,
    record_pin_result,
    resolve_user,
    unlocked_users,
)
from .learning import LedgerBrokenError
from .models import (
    AgentStateName,
    HumanDecision,
    HumanDecisionRecord,
    Observation,
    Outcome,
    OutcomeResult,
    ReadingStatus,
    Recommendation,
)
from .rbac import DEMO_USERS, require
from .store import STORE

_log = logging.getLogger("tbc.persistence")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    from . import persistence

    persistent = os.environ.get("TBC_PERSIST", "1") != "0"
    if persistent:
        summary = persistence.load_state()
        _log.info("persistence restore: %s", summary)
        if summary.get("audit_chain_failures"):
            _log.error("invalid audit chains on restore: %s", summary["audit_chain_failures"])
    if not STORE.list() and os.environ.get("TBC_AUTO_SEED", "1") != "0":
        _log.info("empty store: seeded demo cases %s", seed_demo_cases())
        if persistent:
            persistence.save_state()
    try:
        yield
    finally:
        if persistent:
            persistence.save_state()


app = FastAPI(
    title="Technical Services Fault Diagnosis Pill",
    version="1.0.0",
    lifespan=_lifespan,
)


class _DecisionTextFromBody:
    """Free text that records a decision (rationales, reasons, resolutions,
    outcome notes) travels in a JSON body, not the URL, so it never lands in
    browser history or access logs. For the decision endpoints only, a JSON
    object body's scalar fields are handed to the route as its parameters;
    query parameters still work for scripts and tests."""

    _PATHS = re.compile(
        r"^/(?:cases/[^/]+/(?:approval|outcome|escalation/close|escalation/evidence)|"
        r"kb/proposals/[^/]+/(?:approve|reject|revoke)|kb/rollback/\d+|audit/review)$")

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or not self._PATHS.match(scope["path"])
                or b"application/json" not in dict(scope["headers"]).get(b"content-type", b"")):
            return await self.inner(scope, receive, send)
        body, more = b"", True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        try:
            fields = json.loads(body or b"{}")
        except ValueError:
            fields = None
        if isinstance(fields, dict):
            from urllib.parse import parse_qsl, urlencode

            query = dict(parse_qsl(scope["query_string"].decode(), keep_blank_values=True))
            query.update({k: ("true" if v is True else "" if v in (False, None) else str(v))
                          for k, v in fields.items() if not isinstance(v, (dict, list))})
            scope = {**scope, "query_string": urlencode(query).encode()}

        async def replay():
            return {"type": "http.request", "body": body, "more_body": False}

        return await self.inner(scope, replay, send)


app.add_middleware(_DecisionTextFromBody)


@app.exception_handler(LedgerBrokenError)
async def _ledger_broken(request: Request, exc: LedgerBrokenError):
    """Any write that would append to a ledger failing verification is
    refused, wherever it comes from (the routes also check up front)."""
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=423, content={"detail": str(exc)})


@app.middleware("http")
async def _snapshot_after_write(request, call_next):
    response = await call_next(request)
    if (
        os.environ.get("TBC_PERSIST", "1") != "0"
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and response.status_code < 400
    ):
        from . import persistence

        persistence.save_state()
    return response


# --- auth helper ----------------------------------------------------------
def _user(user_id: str):
    u = DEMO_USERS.get(user_id)
    if u is None:
        raise HTTPException(status_code=401, detail=f"unknown user {user_id!r}")
    return u


def _need(user_id: str, capability: str):
    u = _user(user_id)
    try:
        require(u.role, capability)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return u


def _get_case(case_id: str) -> AgentState:
    state = STORE.get(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return state


def _get_case_for_write(case_id: str) -> AgentState:
    """A case whose audit chain fails verification is frozen: it can be
    read and investigated, never advanced, approved or closed."""
    state = _get_case(case_id)
    if not state.verify_audit_chain():
        raise HTTPException(
            423, f"case {case_id} audit chain failed verification; frozen pending audit review")
    return state


def _evidence_terms(state: AgentState) -> set[str]:
    """Vocabulary of what is actually wrong in this case: the trigger, and
    the readings flagged abnormal by the decision trees' own thresholds
    (``evidence_flags.py``), with their values. Healthy readings and field
    names that merely exist are left out, so an expert's condition only
    counts as seen when the case shows it."""
    from .evidence_flags import abnormal_fields
    from .learning import _terms

    words: list[str] = [state.observation.type, state.observation.reading_status.value]
    for ev in state.evidence:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        for k in abnormal_fields(payload):
            words.append(k)
            v = payload[k]
            if isinstance(v, str):
                words.append(v)
            elif isinstance(v, list):
                words += [str(x) for x in v if not isinstance(x, dict)]
    return _terms(" ".join(w.replace("_", " ") for w in words))


FAULTS_BY_ASSET_TYPE: dict[str, set[str]] = {
    "CRAH": {"temperature_measurement_missing"},
    "Chiller": {"chiller_compressor_trip"},
    "UPS": {"ups_battery_fault"},
    "Pump": {"pump_vibration_high"},
}


def _pill_causes(asset_type: str) -> list[str]:
    from .cause_registry import CAUSE_INFO

    return [cid for cid, (_, at) in CAUSE_INFO.items() if at == asset_type]


def _asset_type(asset_id: str) -> str:
    """Asset type from the registry (e.g. "UPS"); "UNKNOWN" if unregistered."""
    from .mock_registry import ASSETS

    return ASSETS.get(asset_id, {}).get("type", "UNKNOWN")


def _fault_signature(state: AgentState, top_cause_id: str, kb_refs: list[str]) -> str:
    """Deterministic, asset-agnostic fault signature for KB retrieval.

    Delegates to ``tools.build_fault_signature`` so diagnosis time (here)
    and feedback time (``tools.submit_feedback``) build it identically —
    a validated case must match the next identical fault's query signature.
    """
    from .tools import build_fault_signature

    return build_fault_signature(state.observation.type, top_cause_id, kb_refs)


# ========================================================================== #
# Identity: a signed session cookie, not a spoofable ?user= param (see auth.py)
# ========================================================================== #
class LoginRequest(BaseModel):
    user_id: str
    pin: str | None = None


@app.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    """Check the user's PIN and set a signed session cookie for them.

    The PIN travels in the request body, never the URL. Five wrong PINs
    lock that user out for five minutes. A user whose PIN this browser has
    already proven can be switched back to without it.
    """
    u = _user(body.user_id)
    key = f"{u.user_id}@{request.client.host if request.client else '-'}"
    unlocked = unlocked_users(request)
    if body.pin is None:
        # A switch back to a user this browser already proved; asking without
        # a PIN is not a guess, so it never counts towards a lockout.
        if u.user_id not in unlocked:
            raise HTTPException(401, f"PIN required for {u.user_id}")
    else:
        wait = locked_for(key)
        if wait:
            raise HTTPException(429, f"too many wrong PINs for {u.user_id}; try again in {wait}s")
        ok = check_pin(u.user_id, body.pin)
        record_pin_result(key, ok)
        if not ok:
            raise HTTPException(401, f"wrong PIN for {u.user_id}")
        issue_unlock(response, unlocked | {u.user_id})
    issue_cookie(response, u.user_id)
    return _me(u.user_id)


def _me(user_id: str) -> dict:
    from .rbac import PERMISSIONS

    u = _user(user_id)
    return {"user": u.user_id, "role": u.role.value, "capabilities": sorted(PERMISSIONS[u.role])}


@app.get("/me")
def me(user: str = Depends(resolve_user)) -> dict:
    """Who the session is and what it may do, so screens gate on
    capabilities rather than on user names."""
    return _me(user)


@app.post("/logout")
def logout(request: Request, response: Response) -> dict:
    from .auth import SESSION_COOKIE, UNLOCK_COOKIE, revoke

    # Both cookies: a copied "switch back without a PIN" cookie must not
    # outlive the logout either.
    revoke(request.cookies.get(SESSION_COOKIE), request.cookies.get(UNLOCK_COOKIE))
    clear_cookie(response)
    return {"status": "logged out"}


# ========================================================================== #
# Case lifecycle
# ========================================================================== #
@app.post("/cases")
def create_case(
    asset_id: str,
    sensor_id: str,
    user: str = Depends(resolve_user),
    observation_type: str = "temperature_measurement_missing",
    reading_status: str = "absent",
    raw_value: float | None = None,
) -> dict:
    """Trigger a diagnosis case. Gathers evidence + runs the decision tree.

    ``observation_type`` routes the case to a fault-specific causal tree
    (CRAH temp-missing / chiller / UPS / pump). Unknown types are rejected
    with 400 so an un-routable observation is never built. ``raw_value`` is
    required semantics for an INVALID reading (spec §4.2 Q1).
    """
    _need(user, "view_case")
    from .decision_tree import KNOWN_FAULT_TYPES

    asset_id = asset_id.strip().upper()  # "crah-dc1-01" is CRAH-DC1-01, not an unknown asset
    if observation_type not in KNOWN_FAULT_TYPES:
        raise HTTPException(
            400,
            f"unknown observation_type {observation_type!r}; "
            f"expected one of {list(KNOWN_FAULT_TYPES)}",
        )
    try:
        rs = ReadingStatus(reading_status)
    except ValueError:
        raise HTTPException(400, f"invalid reading_status {reading_status!r}") from None
    asset_type = _asset_type(asset_id)
    allowed = FAULTS_BY_ASSET_TYPE.get(asset_type)
    if allowed is not None and observation_type not in allowed:
        raise HTTPException(
            400, f"{observation_type!r} is not a fault the {asset_type} pill diagnoses; "
                 f"expected one of {sorted(allowed)}")
    state = _new_case(asset_id, sensor_id, observation_type, rs, raw_value, actor=user)
    return {"case_id": state.case_id, "current_state": state.current_state.value,
            "evidence_count": len(state.evidence)}


def _new_case(asset_id: str, sensor_id: str, observation_type: str,
              reading_status: ReadingStatus, raw_value: float | None = None,
              *, actor: str) -> AgentState:
    from .mock_registry import ASSETS
    from .models import GuardrailResult
    from .tools import gather_evidence_for_fault

    observation = Observation(
        type=observation_type,
        sensor_id=sensor_id,
        detected_at=datetime.now(timezone.utc),
        reading_status=reading_status,
        raw_value=raw_value,
        asset_id=asset_id,
    )
    registered = asset_id in ASSETS
    state = AgentState(asset_id=asset_id, observation=observation, actor=actor,
                       asset_registered=registered)
    if registered:
        for ev in gather_evidence_for_fault(asset_id, observation_type):
            state.add_evidence(ev, actor="agent")
        state._record_note(actor="agent", reason=f"gathered {len(state.evidence)} evidence items")
    else:
        # G5: nothing is known about this asset, so nothing is gathered or
        # diagnosed; it escalates the moment it is raised.
        gr = GuardrailResult()
        gr.add("G5", "asset not in registry; cannot diagnose unknown asset",
               escalate=True, block=True)
        state.guardrail_result = gr
        state.escalate_for_evidence(actor="agent", reason="[G5] unknown asset; outside pill scope")
    STORE.create(state)
    return state


@app.get("/cases")
def list_cases(user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    return {"cases": STORE.list()}


@app.post("/cases/{case_id}/advance")
def advance_case(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Drive the agent loop to a terminal or waiting state in one call.

    Loops through GATHERING_EVIDENCE -> DIAGNOSING -> (RECOMMENDING |
    GATHERING_EVIDENCE | ESCALATED) until the state is no longer
    GATHERING_EVIDENCE. The state machine's ``_gathering_loops`` counter
    caps the loop at 2 iterations before forcing ESCALATED.

    When the case escalates via G4 (low confidence / max gathering loops)
    but a diagnosis with a top cause exists, guardrails are evaluated
    anyway so that G3 cross-domain escalation is surfaced with
    ``guardrail_result`` populated — the proximate cause of escalation is
    recorded, but the guardrail attribution is not lost.
    """
    _need(user, "view_case")
    state = _get_case_for_write(case_id)
    _advance(state)
    return {"case_id": case_id, "current_state": state.current_state.value,
            "confidence": state.confidence}


def _advance(state: AgentState) -> None:
    while state.current_state == AgentStateName.GATHERING_EVIDENCE:
        from .decision_tree import evaluate_decision_tree

        # G5: an asset outside the registry is out of this pill's scope.
        # Escalate before diagnosing instead of stalling in GATHERING_EVIDENCE.
        from .mock_registry import ASSETS
        from .models import CandidateCause, Diagnosis, GuardrailResult, Recommendation

        if state.asset_id not in ASSETS:
            gr = GuardrailResult()
            gr.add("G5", "asset not in registry; cannot diagnose unknown asset",
                   escalate=True, block=True)
            state.guardrail_result = gr
            state.escalate_for_evidence(
                actor="agent", reason="[G5] unknown asset; outside pill scope")
            break

        try:
            state.begin_diagnosing(actor="agent")
        except ValueError as exc:
            # Evidence can never reach the minimum: escalate, never stall.
            state.escalate_for_evidence(actor="agent", reason=str(exc))
            break
        results = evaluate_decision_tree(state.observation, state.evidence)
        if not results:
            from .models import CandidateCause, Diagnosis

            unknown = CandidateCause(
                id="unresolvable", label="No candidate cause resolved",
                likelihood=0.0, evidence_refs=[],
            )
            diag = Diagnosis(
                candidate_causes=[unknown], top_cause_id="unresolvable",
                reasoning_trace="decision tree returned no candidate cause",
                kb_refs=[],
            )
            state.complete_diagnosis(diag, 0.0, actor="agent")
            break

        top = results[0]
        candidates = [
            CandidateCause(id=r.cause_id, label=r.cause_label,
                           likelihood=0.9 if r is top else 0.3,
                           evidence_refs=r.kb_refs)
            for r in results
        ]
        diag = Diagnosis(
            candidate_causes=candidates, top_cause_id=top.cause_id,
            reasoning_trace=f"decision tree -> {top.cause_id}",
            kb_refs=top.kb_refs,
        )
        conf, breakdown = _confidence_for(state, top.cause_id, top.kb_refs)
        hypothesis = generate_diagnostic_hypothesis(
            asset={"asset_id": state.asset_id, "asset_type": _asset_type(state.asset_id)},
            observations={
                "type": state.observation.type,
                "sensor_id": state.observation.sensor_id,
                "reading_status": state.observation.reading_status.value,
            },
            evidence=[
                {
                    "source": ev.source, "finding": ev.type, "payload": ev.payload,
                    "conflict": isinstance(ev.payload, dict) and ev.payload.get("conflict") is True,
                }
                for ev in state.evidence
            ],
            # Any cause this pill knows, not only the tree's pick, so the
            # second opinion can genuinely disagree.
            candidate_causes=_pill_causes(_asset_type(state.asset_id)) or [r.cause_id for r in results],
            rule_top_cause=top.cause_id,
            knowledge=[{"cause": top.cause_id, "kb_ref": ref} for ref in top.kb_refs],
        )
        state.record_ai_second_opinion(hypothesis, actor="agent")
        new_st = state.complete_diagnosis(diag, conf, actor="agent", confidence_breakdown=breakdown)
        if new_st == AgentStateName.RECOMMENDING:
            rec = Recommendation(
                actions=[top.action], kb_refs=top.kb_refs,
                evidence_refs=[e.type for e in state.evidence],
            )
            state.propose_recommendation(rec, actor="agent")
            break
        if new_st == AgentStateName.GATHERING_EVIDENCE:
            # Low confidence: actually re-query the evidence sources. If they
            # return nothing new, another pass would only re-run the same
            # data, so hand the case to a human instead.
            from .tools import gather_evidence_for_fault

            seen = {(e.source, e.type, repr(e.payload)) for e in state.evidence}
            fresh = [ev for ev in gather_evidence_for_fault(state.asset_id, state.observation.type)
                     if (ev.source, ev.type, repr(ev.payload)) not in seen]
            if not fresh:
                state.escalate_for_evidence(
                    actor="agent",
                    reason=(f"confidence {conf:.2f} is below the recommendation threshold and "
                            "re-querying every evidence source returned nothing new; "
                            "needs a human"),
                )
                break
            for ev in fresh:
                state.add_evidence(ev, actor="agent")
            state._record_note(actor="agent", reason=f"re-gathered {len(fresh)} new evidence items")

    # If the case escalated via G4 (low confidence / max gathering loops)
    # but a diagnosis with a resolvable top cause exists, evaluate
    # guardrails anyway so G3 cross-domain escalation is surfaced with
    # guardrail_result populated (spec §4.4 edge case E5).
    if (
        state.current_state == AgentStateName.ESCALATED
        and state.guardrail_result is None
        and state.diagnosis
        and state.diagnosis.top_cause_id
        and state.diagnosis.top_cause_id != "unresolvable"
    ):
        from .guardrails import SAFETY_CRITICAL_CAUSE_IDS, check_guardrails
        from .models import GuardrailContext, Recommendation

        top_label = None
        for c in state.diagnosis.candidate_causes:
            if c.id == state.diagnosis.top_cause_id:
                top_label = c.label
                break
        ctx = GuardrailContext(asset_known=True)
        if state.diagnosis.top_cause_id in SAFETY_CRITICAL_CAUSE_IDS:
            ctx = ctx.model_copy(update={"safety_critical": True})
        rec = Recommendation(
            actions=[],
            kb_refs=list(state.diagnosis.kb_refs or []),
            evidence_refs=[e.type for e in state.evidence],
        )
        gr = check_guardrails(
            rec, ctx, confidence=state.confidence, top_cause_label=top_label,
        )
        if gr.must_escalate or not gr.allowed:
            state.guardrail_result = gr
            state.recommendation = rec
            state._record_note(
                actor="agent",
                reason="guardrail review of the escalated case: " + "; ".join(gr.reasons),
            )

    # Every escalation names its reason for the AOM. When no G1-G8 rule
    # fired, the cause was low confidence or no new evidence: record that
    # as G4 rather than leaving the Decision screen with no reason at all.
    if state.current_state == AgentStateName.ESCALATED and (
        state.guardrail_result is None or not state.guardrail_result.must_escalate
    ):
        from .models import GuardrailResult

        why = next((h.reason for h in reversed(state.history)
                    if h.to_state == AgentStateName.ESCALATED and h.from_state != h.to_state),
                   "low confidence")
        gr = state.guardrail_result or GuardrailResult()
        gr.add("G4", f"escalated for a human: {why}", escalate=True)
        state.guardrail_result = gr
        state._record_note(actor="agent", reason=f"[G4] escalated for a human: {why}")

    # G9: surface an AI/rules disagreement, if any, on whatever guardrail
    # result exists by now. Advisory only — never changes current_state.
    if state.guardrail_result is not None:
        from .guardrails import flag_ai_disagreement

        before = list(state.guardrail_result.rule_ids)
        flag_ai_disagreement(
            state.guardrail_result,
            ai_hypothesis=state.ai_hypothesis,
            rule_cause=state.diagnosis.top_cause_id if state.diagnosis else None,
        )
        if state.guardrail_result.rule_ids != before:
            state._record_note(actor="agent", reason=state.guardrail_result.reasons[-1])


@app.get("/cases/similar")
def list_similar_cases(
    cause: str, asset_type: str | None = None, user: str = Depends(resolve_user),
) -> dict:
    """Open (not CLOSED) cases currently diagnosed with ``cause`` — the
    candidates a steward can re-score after approving a proposal for that
    cause.

    Registered before ``/cases/{case_id}`` below: a literal path must be
    declared ahead of a param route with the same shape, or the param
    route shadows it and every call here 404s as case_id="similar".
    """
    _need(user, "view_case")
    matches = []
    for case_id in STORE.list():
        state = STORE.get(case_id)
        if state is None or state.current_state == AgentStateName.CLOSED:
            continue
        if not state.diagnosis or state.diagnosis.top_cause_id != cause:
            continue
        if asset_type and _asset_type(state.asset_id) != asset_type:
            continue
        matches.append({
            "case_id": case_id, "asset_id": state.asset_id,
            "current_state": state.current_state.value, "confidence": state.confidence,
        })
    return {"matches": matches}


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    snap = STORE.snapshot(case_id)
    if snap is None:
        raise HTTPException(404, "case not found")
    from .evidence_flags import abnormal_fields, field_label

    snap["asset_type"] = _asset_type(snap["asset_id"])
    for ev in snap["evidence"]:
        ev["abnormal"] = abnormal_fields(ev.get("payload"))
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        ev["labels"] = {k: field_label(k) for k in payload}
    state = STORE.get(case_id)
    snap["knowledge_withdrawn"] = (
        _knowledge_withdrawn(state) if state.current_state == AgentStateName.AWAITING_APPROVAL else None)
    from .learning import STORE as _LSTORE

    # A broken ledger is cleared by an auditor's review, not by re-scoring.
    snap["ledger_valid"] = _LSTORE.verify_ledger()
    return snap


@app.get("/cases/{case_id}/evidence")
def get_evidence(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"evidence": [e.model_dump(mode="json") for e in state.evidence]}


@app.get("/cases/{case_id}/diagnosis")
def get_diagnosis(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    diag = state.diagnosis
    return {"diagnosis": diag.model_dump(mode="json") if diag else None,
            "confidence": state.confidence}


@app.get("/cases/{case_id}/recommendation")
def get_recommendation(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    rec = state.recommendation
    gr = state.guardrail_result
    return {"recommendation": rec.model_dump(mode="json") if rec else None,
            "guardrail_result": gr.model_dump(mode="json") if gr else None,
            "guardrail_route_explanation": _route_explanation(state)}


@app.get("/cases/{case_id}/confidence-preview")
def preview_confidence(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Non-destructive: re-score this case's EXISTING evidence against the
    CURRENT KB and registry, without mutating the case.

    Lets Governance show a steward the before/after effect a just-approved
    proposal has on a similar still-open case ("Re-run diagnosis on similar
    open cases"). Nothing here changes ``current_state`` or ``confidence``
    on the stored case -- it's a preview, not a re-diagnosis.
    """
    _need(user, "view_case")
    state = _get_case(case_id)
    after, breakdown = _score_against_current_kb(state)
    return {"case_id": case_id, "before": state.confidence, "after": after,
            "delta": after - state.confidence, "breakdown": breakdown}


def _score_against_current_kb(state: AgentState) -> tuple[float, dict]:
    if not state.diagnosis or not state.diagnosis.top_cause_id or state.diagnosis.top_cause_id == "unresolvable":
        raise HTTPException(409, "case has no resolvable diagnosis to re-score")
    return _confidence_for(state, state.diagnosis.top_cause_id, state.diagnosis.kb_refs)


def _confidence_for(state: AgentState, cause_id: str, kb_refs: list[str]) -> tuple[float, dict]:
    """Confidence in ``cause_id`` for this case against the current KB, with
    its W1-W5 breakdown and the pill knowledge version it was scored with."""
    from .confidence import (
        derive_confidence_signals,
        evidence_coverage_score,
        score_confidence,
    )
    from .decision_tree import FAULT_BRANCH_COUNTS
    from .learning import STORE as _LSTORE

    pill = _asset_type(state.asset_id)
    coverage = evidence_coverage_score(state.evidence, FAULT_BRANCH_COUNTS.get(state.observation.type, 6))
    kb_match = _LSTORE.kb_match_score(_fault_signature(state, cause_id, kb_refs), cause_id, pill,
                                      evidence_terms=_evidence_terms(state))
    signals = derive_confidence_signals(
        state.evidence, asset_id=state.asset_id, sensor_id=state.observation.sensor_id,
    )
    conf = score_confidence(
        evidence_coverage=coverage,
        peer_agreement=signals["peer_agreement"],
        kb_match=kb_match,
        data_staleness=signals["data_staleness"],
        conflict_penalty=signals["conflict_penalty"],
    )
    return conf, {
        "evidence_coverage": coverage,
        "peer_agreement": signals["peer_agreement"],
        "kb_match": kb_match,
        "data_staleness": signals["data_staleness"],
        "conflict_penalty": signals["conflict_penalty"],
        "pill": pill,
        "kb_version": _LSTORE.version_of(pill),
        "kb_version_label": _LSTORE.label_of(pill),
        "ledger_seq": len(_LSTORE.ledger),
    }


def _knowledge_withdrawn(state: AgentState) -> str | None:
    from .learning import STORE as _LSTORE

    if not _LSTORE.verify_ledger():
        return ("the knowledge ledger failed verification, so no score that used the knowledge "
                "base can be trusted until an auditor reviews it on Governance")
    b = state.confidence_breakdown or {}
    return _LSTORE.withdrawn_reason(b.get("pill"), b.get("kb_version"), b.get("ledger_seq"))


@app.post("/cases/{case_id}/rescore")
def rescore_case(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Re-score a case awaiting approval against the current KB, e.g. after
    knowledge it relied on was rolled back or revoked."""
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    conf, breakdown = _score_against_current_kb(state)
    try:
        state.rescore(conf, breakdown, actor=user,
                      reason=f"re-scored against {breakdown['kb_version_label']} knowledge")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"case_id": case_id, "current_state": state.current_state.value, "confidence": conf}


@app.post("/cases/{case_id}/approval")
def post_approval(
    case_id: str,
    decision: str,
    user: str = Depends(resolve_user),
    rationale: str | None = None,
    modified_action_type: str | None = None,
    modified_action_target: str | None = None,
    modified_action_detail: str | None = None,
    hazard_acknowledged: bool = False,
) -> dict:
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    try:
        dec = HumanDecision(decision)
    except ValueError:
        raise HTTPException(400, f"invalid decision {decision!r}") from None
    if not (rationale or "").strip():
        raise HTTPException(400, f"a rationale is required to {dec.value}")
    withdrawn = _knowledge_withdrawn(state)
    if withdrawn and dec != HumanDecision.REJECT:
        raise HTTPException(409, f"{withdrawn}; re-score the case before approving or modifying")
    hazard = state.guardrail_result is not None and any(
        r.startswith(("[G2]", "[G2b]")) for r in state.guardrail_result.reasons)
    if hazard and dec != HumanDecision.REJECT and not hazard_acknowledged:
        raise HTTPException(
            400, "this recommendation carries a safety/environmental hazard; "
                 "acknowledge it (hazard_acknowledged=true) before approving or modifying")

    if hazard and dec != HumanDecision.REJECT:
        rationale = f"{rationale.strip()} [safety hazard acknowledged]"

    modified_actions = None
    original_actions = None
    if dec == HumanDecision.MODIFY:
        if not (modified_action_type and modified_action_target):
            raise HTTPException(
                400,
                "modify requires modified_action_type and modified_action_target",
            )
        from .models import RecommendationAction

        modified_actions = [
            RecommendationAction(
                type=modified_action_type,
                target=modified_action_target,
                detail=modified_action_detail or "",
                kb_refs=list(state.recommendation.actions[0].kb_refs)
                if state.recommendation and state.recommendation.actions
                else [],
            )
        ]
        if state.recommendation and state.recommendation.actions:
            original_actions = list(state.recommendation.actions)

    from pydantic import ValidationError as PydanticValidationError

    try:
        hd = HumanDecisionRecord(
            decision=dec, decided_by=user, rationale=rationale,
            modified_actions=modified_actions,
            original_actions=original_actions,
            expert_knowledge=[
                {k: m[k] for k in ("knowledge_id", "expert_name", "expert_role",
                                   "kb_version_label", "checks", "do_not", "escalate_when",
                                   "evidence_quote")}
                for m in _expert_matches(state)["matches"]],
        )
        state.record_human_decision(hd, actor=user)
    except PydanticValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if dec == HumanDecision.MODIFY:
        # apply the manager's modified action set while preserving G8
        # grounding metadata (kb_refs / evidence_refs) from the original
        # recommendation so the audit trail stays fully grounded.
        orig = state.recommendation
        state.recommendation = Recommendation(
            actions=modified_actions or [],
            kb_refs=list(orig.kb_refs) if orig and orig.kb_refs else [],
            evidence_refs=list(orig.evidence_refs) if orig and orig.evidence_refs else [],
        )
        state._record_note(actor=user, reason="modified action set applied to the recommendation")
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.get("/cases/{case_id}/work-order")
def get_work_order(case_id: str, user: str = Depends(resolve_user)) -> dict:
    _need(user, "view_case")
    state = _get_case(case_id)
    return {"work_order_id": state.work_order_id}


@app.post("/cases/{case_id}/work-order")
def create_work_order(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Raise + acknowledge the CMMS work order (EXECUTING -> MONITORING_OUTCOME).

    Spec §3 guardrail: refused unless an approve/modify decision is recorded.
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    if not state.recommendation or not state.recommendation.actions:
        raise HTTPException(409, "no recommendation to action")
    from .tools import create_work_order_for_state
    try:
        wo_id = create_work_order_for_state(state, state.recommendation.actions[0])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"case_id": case_id, "work_order_id": wo_id,
            "current_state": state.current_state.value}


@app.post("/cases/{case_id}/outcome")
def post_outcome(
    case_id: str,
    result: str,
    user: str = Depends(resolve_user),
    root_cause_confirmed: str | None = None,
    notes: str | None = None,
) -> dict:
    _need(user, "record_outcome")
    state = _get_case_for_write(case_id)
    try:
        res = OutcomeResult(result)
    except ValueError:
        raise HTTPException(400, f"invalid result {result!r}") from None
    # Validate root_cause_confirmed against the diagnosed cause universe so
    # free-text typos cannot flow into the KB via the feedback loop (spec §7).
    # None/blank stays allowed (outcome recorded without cause confirmation).
    from .decision_tree import KNOWN_CAUSE_IDS

    if root_cause_confirmed and root_cause_confirmed.strip():
        rcc = root_cause_confirmed.strip()
        if rcc not in KNOWN_CAUSE_IDS:
            raise HTTPException(
                400,
                f"unknown root_cause_confirmed {rcc!r}; expected one of "
                f"{sorted(KNOWN_CAUSE_IDS)} (or omit)",
            )
    outcome = Outcome(
        result=res, root_cause_confirmed=root_cause_confirmed,
        verified_by=user, notes=notes,
    )
    try:
        state.record_outcome(outcome)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.post("/cases/{case_id}/feedback")
def post_feedback(
    case_id: str,
    user: str = Depends(resolve_user),
    corrections: dict | None = None,
) -> dict:
    _need(user, "submit_feedback")
    state = _get_case_for_write(case_id)
    from .cause_registry import canonicalize_cause_id, cause_asset_type
    from .decision_tree import KNOWN_CAUSE_IDS
    from .tools import submit_feedback as _fb

    # Every check runs before a proposal exists: a rejected request must
    # leave nothing behind in the governance queue.
    if state.current_state != AgentStateName.FEEDBACK_QUEUED or state.outcome is None:
        raise HTTPException(
            409,
            f"feedback is only accepted once an outcome is recorded and before the "
            f"case closes (case is {state.current_state.value})",
        )
    supplied = corrections or {}
    raw_cause = (supplied.get("confirmed_cause") or "").strip()
    if not raw_cause:
        raw_cause = (state.outcome.root_cause_confirmed or "").strip()
    if not raw_cause and state.diagnosis:
        raw_cause = state.diagnosis.top_cause_id or ""
    confirmed = canonicalize_cause_id(raw_cause) if raw_cause else None
    if not confirmed or confirmed not in KNOWN_CAUSE_IDS:
        raise HTTPException(400, f"unknown confirmed_cause {raw_cause!r}")
    case_asset_type = _asset_type(state.asset_id)
    if cause_asset_type(confirmed) != case_asset_type:
        raise HTTPException(
            400,
            f"cause {confirmed!r} belongs to the {cause_asset_type(confirmed)} pill, "
            f"not this {case_asset_type} case",
        )
    # Only the cause and notes come from the client. Asset type and fault
    # signature are derived from the case itself, the outcome from the
    # recorded outcome, and the proposer is always the authenticated caller.
    clean = {
        "confirmed_cause": confirmed,
        "notes": str(supplied.get("notes") or "")[:2000],
        "outcome": state.outcome.result.value,
        "submitted_by": user,
    }
    _require_intact_ledger()
    fb_id = _fb(case_id, clean, state=state)
    state.queue_feedback(fb_id, actor=user)
    from .learning import STORE as _LSTORE
    stats = _LSTORE.stats()
    return {"case_id": case_id, "feedback_id": fb_id,
            "current_state": state.current_state.value,
            "proposal_status": "pending",
            "kb_cases_total": stats["total_validated_cases"],
            "kb_feedback_added": stats["feedback_added"],
            "pending_proposals": stats["pending_proposals"]}


# --------------------------------------------------------------------------- #
# Expert knowledge capture (LLM drafts, steward approves)
# --------------------------------------------------------------------------- #
from pydantic import BaseModel as _BaseModel
from pydantic import Field as _Field


class CaptureInterviewRequest(_BaseModel):
    expert_name: str = _Field(min_length=1, max_length=120)
    expert_role: str = _Field(min_length=1, max_length=120)
    asset_type: str = _Field(min_length=1, max_length=40)
    transcript: str = _Field(min_length=1)
    # Optional: the heuristics the capturer kept after reviewing a draft from
    # /capture/draft. They are re-grounded against the transcript server-side.
    heuristics: list[dict] | None = None
    # The draft this review came from (/capture/draft). Which model drafted
    # it is looked up server-side; a client cannot claim a provider.
    draft_id: str | None = None
    # The expert agreed to their words being recorded and reused.
    expert_consent: bool = False


class CaptureDraftRequest(_BaseModel):
    asset_type: str = _Field(min_length=1, max_length=40)
    transcript: str = _Field(min_length=1)


@app.get("/causes")
def get_causes(user: str = Depends(resolve_user), asset_type: str | None = None) -> dict:
    """Canonical causes with plain-English labels and owning asset type."""
    _need(user, "view_case")
    from .cause_registry import list_causes
    causes = list_causes()
    if asset_type:
        causes = [c for c in causes if c["asset_type"] == asset_type]
    return {"causes": causes}


# Which knowledge steward owns review for each pill (spec §7 governance).
# The demo's two stewards split the four pills; a deployment sets its own
# roster with TBC_PILL_OWNERS="CRAH:alice,Chiller:bob,UPS:alice,Pump:bob".
_DEFAULT_PILL_OWNERS = {"CRAH": "steward1", "Chiller": "steward2", "UPS": "steward1", "Pump": "steward2"}


def _pill_owners() -> dict[str, str]:
    raw = os.environ.get("TBC_PILL_OWNERS", "").strip()
    pairs = (item.split(":", 1) for item in raw.split(",") if ":" in item)
    return {**_DEFAULT_PILL_OWNERS, **{k.strip(): v.strip() for k, v in pairs}}


PILL_OWNERS: dict[str, str] = _pill_owners()


@app.get("/assets")
def list_assets(user: str = Depends(resolve_user)) -> dict:
    """Registered assets with the fault their pill diagnoses and a default
    sensor, so the New Case form is built from the registry itself."""
    _need(user, "view_case")
    from .mock_registry import ASSETS, SENSORS

    out = []
    for asset_id, a in sorted(ASSETS.items()):
        sensor = next((sid for sid, s in SENSORS.items() if s.get("asset_id") == asset_id),
                      f"{asset_id}-SENSOR")
        out.append({"asset_id": asset_id, "type": a.get("type"),
                    "fault_type": min(FAULTS_BY_ASSET_TYPE.get(a.get("type"), [])),
                    "default_sensor": sensor})
    return {"assets": out}


@app.get("/pills")
def list_pills(user: str = Depends(resolve_user)) -> dict:
    """Registry of the four Intelligence Pills: owner steward, each pill's
    own knowledge version, how much knowledge it holds, and its approvals."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    from .learning import proposal_pills

    all_proposals = _LSTORE.list_all_proposals()
    pills = []
    for asset_type, owner in PILL_OWNERS.items():
        knowledge_count = sum(1 for vc in _LSTORE.validated if vc.asset_type == asset_type)
        knowledge_count += sum(1 for h in _LSTORE.expert_heuristics if h.get("asset_type") == asset_type)
        # An interview touching several pills counts for each pill it files
        # knowledge under, not only for its main asset type.
        relevant = [p for p in all_proposals if asset_type in proposal_pills(p)]
        # A rolled-back or revoked proposal was still approved at the time.
        ever_approved = ("approved", "rolled_back", "revoked")
        decided = [p for p in relevant if p.get("status") in (*ever_approved, "rejected")]
        approved = [p for p in decided if p.get("status") in ever_approved]
        pills.append({
            "asset_type": asset_type,
            "owner_steward": owner,
            "kb_version": _LSTORE.version_of(asset_type),
            "kb_version_label": _LSTORE.label_of(asset_type),
            "knowledge_count": knowledge_count,
            "proposals_submitted": len(relevant),
            "proposals_decided": len(decided),
            "proposals_pending": sum(1 for p in relevant if p.get("status") == "pending"),
            "proposals_approved": len(approved),
            "approval_rate": round(len(approved) / len(decided), 3) if decided else None,
        })
    return {"pills": pills}


@app.get("/system/info")
def get_system_info(user: str = Depends(resolve_user)) -> dict:
    """Which model drafts expert knowledge, for the UI badge. Never returns secrets."""
    _need(user, "view_case")
    from . import llm
    provider = llm.provider_name()
    if provider == "adp":
        ok = llm.LAST_CALL["ok"]
        ai_status = ("offline" if not llm.adp_configured() or ok is False
                     else "online" if ok else "ready")
    else:
        ai_status = "offline-model"
    return {
        "llm_provider": provider,
        "llm_label": "Tencent Cloud ADP" if provider == "adp" else "Offline models (no LLM)",
        "adp_configured": llm.adp_configured(),
        "ai_status": ai_status,
        "ai_status_message": (llm.LAST_CALL["message"] if provider == "adp"
                              else "Offline keyword extractor and evidence-weighting second opinion; "
                                   "set TBC_LLM_PROVIDER=adp and ADP_APP_KEY for Tencent Cloud ADP"),
        "diagnosis": "deterministic decision tree",
        "demo_insecure": demo_insecure(),
    }


@app.get("/capture/sample")
def get_capture_sample(user: str = Depends(resolve_user)) -> dict:
    """A sample technician interview for the demo."""
    _need(user, "view_case")
    from .capture import SAMPLE_INTERVIEW
    return {"expert_name": "R. Tan", "expert_role": "Senior M&E Technician, 22 years",
            "asset_type": "CRAH", "transcript": SAMPLE_INTERVIEW}


@app.post("/capture/interview")
def post_capture_interview(body: CaptureInterviewRequest, user: str = Depends(resolve_user)) -> dict:
    """Turn an expert interview into a pending knowledge proposal.

    The LLM drafts structured heuristics; capture.py drops anything not
    quoted verbatim from the transcript; the result is queued for a
    different knowledge steward to approve. Nothing enters the KB here.
    """
    _need(user, "capture_expert_knowledge")
    from . import capture, llm
    from .learning import STORE as _LSTORE
    from .tools import _log

    if not body.expert_consent:
        raise HTTPException(400, "record the expert's consent to reuse their words before submitting")
    try:
        if body.heuristics is not None:
            source = _DRAFTS.get(body.draft_id or "")
            draft = capture.reviewed_draft(
                body.transcript, body.asset_type, body.heuristics,
                source["provider"] if source else "manual",
            )
            # Anything the reviewer added that the model did not draft is
            # marked as hand-entered, item by item.
            drafted = {h["evidence_quote"] for h in source["heuristics"]} if source else set()
            for h in draft["heuristics"]:
                h["source"] = "model" if h["evidence_quote"] in drafted else "manual"
        else:
            draft = capture.draft_from_transcript(body.transcript, body.asset_type)
    except capture.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(502, f"knowledge extraction failed: {exc}") from exc

    _require_intact_ledger()
    proposal = _LSTORE.record_expert_capture(
        draft=draft, submitted_by=user, expert_name=body.expert_name,
        expert_role=body.expert_role, asset_type=body.asset_type, expert_consent=True,
    )
    _log("capture_expert_knowledge",
         {"expert": body.expert_name, "asset_type": body.asset_type,
          "provider": draft["provider"], "submitted_by": user},
         proposal)
    return {"proposal_id": proposal["proposal_id"], "status": "pending",
            "provider": draft["provider"], "heuristics": draft["heuristics"],
            "warnings": draft["warnings"], "dropped": draft["dropped"]}


@app.post("/capture/draft")
def post_capture_draft(body: CaptureDraftRequest, user: str = Depends(resolve_user)) -> dict:
    """Draft heuristics for review WITHOUT queuing anything.

    The capturer reviews the draft (drop items, correct a cause) and then
    submits it to /capture/interview with ``heuristics`` set.
    """
    _need(user, "capture_expert_knowledge")
    from . import capture, llm
    try:
        draft = capture.draft_from_transcript(body.transcript, body.asset_type)
    except capture.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(502, f"knowledge extraction failed: {exc}") from exc
    import uuid

    draft_id = uuid.uuid4().hex
    _DRAFTS[draft_id] = draft
    while len(_DRAFTS) > 200:  # drafts are short-lived; keep the newest
        _DRAFTS.pop(next(iter(_DRAFTS)))
    return {"status": "draft", "draft_id": draft_id, **draft}


# Drafts this server produced, so a submitted review's provenance is the
# server's record of which model drafted it, not the browser's claim.
_DRAFTS: dict[str, dict] = {}


@app.get("/kb/expert-heuristics")
def get_expert_heuristics(user: str = Depends(resolve_user)) -> dict:
    """Approved, live expert heuristics with provenance."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return {"heuristics": _LSTORE.expert_heuristics}


@app.get("/cases/{case_id}/expert-knowledge")
def get_case_expert_knowledge(case_id: str, user: str = Depends(resolve_user)) -> dict:
    """Return approved expert heuristics matching this diagnosis and asset."""
    _need(user, "view_case")
    state = _get_case(case_id)
    return _expert_matches(state)


def _expert_matches(state: AgentState) -> dict:
    from .cause_registry import canonicalize_cause_id
    from .learning import STORE as _LSTORE
    from .learning import corroborating_terms, kb_version_label
    from .safety import defeats_safety, touches_protection

    terms = _evidence_terms(state)
    ledger_ok = _LSTORE.verify_ledger()
    diagnosis = state.diagnosis
    cause_id = canonicalize_cause_id(diagnosis.top_cause_id) if diagnosis else None
    asset_type = _asset_type(state.asset_id)
    matches, withheld = [], []
    if cause_id and cause_id != "unresolvable":
        for item in _LSTORE.expert_heuristics:
            if canonicalize_cause_id(item["likely_cause"]) != cause_id or item["asset_type"] != asset_type:
                continue
            # Screened again at display time (G1 for knowledge): whatever is
            # stored, an instruction to defeat a protection never reaches the
            # AOM, nor does unreviewed knowledge about one, nor anything while
            # the ledger that vouches for it fails verification.
            lines = (item["evidence_quote"], item["symptom_pattern"],
                     *item.get("checks", []), *item.get("escalate_when", []))
            reason = (
                "the knowledge ledger failed verification, so its knowledge cannot be trusted "
                "until an auditor reviews it" if not ledger_ok
                else "contains an instruction that would defeat a safety device (G1)"
                if any(defeats_safety(t) for t in lines)
                else "was not safety-reviewed when approved"
                if (item.get("checks") or any(touches_protection(t) for t in lines))
                and not item.get("safety_reviewed_by")
                else None)
            if reason:
                withheld.append({"knowledge_id": item["id"], "expert_name": item["expert_name"],
                                 "reason": reason})
                continue
            matches.append({
                "knowledge_id": item["id"],
                "expert_name": item["expert_name"],
                "expert_role": item["expert_role"],
                "asset_type": item["asset_type"],
                "likely_cause": item["likely_cause"],
                "symptom_pattern": item["symptom_pattern"],
                "checks": item.get("checks", []),
                "do_not": item.get("do_not", []),
                "escalate_when": item.get("escalate_when", []),
                "evidence_quote": item["evidence_quote"],
                "kb_version": item["kb_version"],
                "kb_version_label": f"{item['asset_type']} v{kb_version_label(item['kb_version'])}",
                "approved_by": item["approved_by"],
                "safety_reviewed_by": item.get("safety_reviewed_by"),
                # Lines about protective devices or work on equipment are for a
                # person to weigh; they never raise confidence (learning.py).
                "guidance_only": bool(item.get("safety_review")
                                      or any(touches_protection(t) for t in lines)),
                "matched_terms": corroborating_terms(item["symptom_pattern"], terms),
            })
    return {
        "matches": matches,
        "withheld": withheld,
        "match_basis": "exact asset type and diagnosed cause",
        "asset_type": asset_type,
        "cause_id": cause_id,
        "kb_version": (_LSTORE.label_of(asset_type)
                       if asset_type in _LSTORE.labels() else None),
    }


@app.get("/kb/stats")
def get_kb_stats(user: str = Depends(resolve_user)) -> dict:
    """Knowledge-base learning stats: validated cases, cause priors."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    return _LSTORE.stats()


@app.get("/kb/queue")
def get_kb_queue(user: str = Depends(resolve_user)) -> dict:
    """List pending knowledge proposals awaiting steward approval (F2).

    Requires ``approve_knowledge_version`` capability (knowledge steward
    or admin). Returns the list of pending proposals with their metadata.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    pending = [{**p, "owner_steward": PILL_OWNERS.get(p.get("asset_type") or "")}
               for p in _LSTORE.list_pending_proposals()]
    return {"queue": pending, "pending_count": len(pending)}


@app.post("/kb/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, rationale: str = "", safety_reviewed: bool = False,
                     user: str = Depends(resolve_user)) -> dict:
    """Approve a pending knowledge proposal and ingest it into the live KB (F2).

    Requires ``approve_knowledge_version`` capability. On approval the KB
    version increments and the proposal's feedback is promoted to a
    ValidatedCase retrievable by future diagnoses.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    from .learning import SelfApprovalError

    _require_intact_ledger()
    _require_pill_owner(proposal_id, user, "approve")
    try:
        proposal = _LSTORE.approve_proposal(proposal_id, decided_by=user, rationale=rationale,
                                            safety_reviewed=safety_reviewed)
    except SelfApprovalError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400 if "needs a" in str(exc) else 404, str(exc)) from exc
    return {"proposal_id": proposal_id, "status": "approved", "decided_by": user,
            "kb_versions": proposal["kb_versions"],
            "kb_version_labels": [f"{pill} v{_kb_label(v)}" for pill, v in proposal["kb_versions"].items()],
            "validated_case_id": proposal.get("validated_case_id")}


def _require_pill_owner(proposal_id: str, user: str, verb: str) -> None:
    """Knowledge is decided by a knowledge steward, never by an admin alone:
    the pill's owning steward decides, and if the owner proposed it, another
    steward stands in."""
    from .learning import STORE as _LSTORE
    from .rbac import Role

    if _user(user).role != Role.KNOWLEDGE_STEWARD:
        raise HTTPException(403, f"only a knowledge steward can {verb} knowledge; "
                                 f"{user} can view the queue but not decide")
    p = _LSTORE.find_proposal(proposal_id)
    if p is None:
        return
    owner = PILL_OWNERS.get(p.get("asset_type") or "")
    if owner and owner != user and owner != p.get("submitted_by"):
        raise HTTPException(
            403, f"{p.get('asset_type')} knowledge is owned by {owner}; only they can {verb} it "
                 "(another steward stands in only when the owner proposed it)")


def _require_intact_ledger() -> None:
    """No knowledge changes while the governance ledger fails verification:
    changing a KB whose history can't be trusted would bury the problem."""
    from .learning import STORE as _LSTORE

    if not _LSTORE.verify_ledger():
        raise HTTPException(423, "the knowledge ledger failed verification; knowledge changes are "
                                 "frozen until an auditor reviews it")


@app.post("/kb/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, reason: str, user: str = Depends(resolve_user)) -> dict:
    """Reject a pending knowledge proposal (F2).

    Requires ``approve_knowledge_version`` capability. The rejected
    proposal is retained in the audit trail but never ingested into the KB.
    """
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    from .learning import SelfApprovalError

    _require_intact_ledger()
    _require_pill_owner(proposal_id, user, "reject")
    try:
        _LSTORE.reject_proposal(proposal_id, decided_by=user, reason=reason)
    except SelfApprovalError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400 if "needs a" in str(exc) else 404, str(exc)) from exc
    return {"proposal_id": proposal_id, "status": "rejected",
            "decided_by": user, "reason": reason}


@app.post("/kb/proposals/{proposal_id}/revoke")
def revoke_proposal(proposal_id: str, reason: str = "", user: str = Depends(resolve_user)) -> dict:
    """Withdraw one approved proposal's knowledge, leaving everything else."""
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE

    _require_intact_ledger()
    try:
        return _LSTORE.revoke_proposal(proposal_id, actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/kb/proposals")
def list_proposals(user: str = Depends(resolve_user), status: str | None = None) -> dict:
    _need(user, "approve_knowledge_version")
    from .learning import STORE as _LSTORE
    from .learning import kb_version_label

    props = _LSTORE.list_all_proposals()
    if status:
        props = [p for p in props if p["status"] == status]
    return {"proposals": [
        {**p, "kb_version_labels": {pill: kb_version_label(v) for pill, v in (p.get("kb_versions") or {}).items()},
         "owner_steward": PILL_OWNERS.get(p.get("asset_type") or "")}
        for p in props]}


def _pill_param(pill: str) -> str:
    from .learning import PILLS

    if pill not in PILLS:
        raise HTTPException(400, f"unknown pill {pill!r}; expected one of {list(PILLS)}")
    return pill


@app.get("/kb/versions")
def list_kb_versions(pill: str, user: str = Depends(resolve_user)) -> dict:
    """One pill's knowledge versions: the number `/kb/rollback/{N}` takes,
    the label every screen shows, and whether it is live or rolled back."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE

    pill = _pill_param(pill)
    return {
        "pill": pill,
        "current_version": _LSTORE.version_of(pill),
        "current_label": _LSTORE.label_of(pill),
        "versions": [
            {"version": v["version"], "label": v["label"], "status": v["status"],
             "proposal_id": v["proposal_id"], "created_by": v["created_by"]}
            for v in _LSTORE.list_versions(pill)
        ],
    }


@app.post("/kb/rollback/{target_version}")
def rollback_kb(target_version: int, pill: str, reason: str = "",
                user: str = Depends(resolve_user)) -> dict:
    """Roll one pill's knowledge back to an earlier live version (admin only,
    reason required). Other pills are untouched; the rollback, its actor
    and reason go into the keyed governance ledger."""
    _need(user, "rollback_knowledge_version")
    from .learning import STORE as _LSTORE

    pill = _pill_param(pill)
    if not reason.strip():
        raise HTTPException(400, "a rollback needs a reason")
    _require_intact_ledger()
    try:
        return _LSTORE.rollback(pill, target_version, actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/kb/ledger")
def get_kb_ledger(user: str = Depends(resolve_user)) -> dict:
    """The keyed, hash-chained governance ledger: every proposal submitted,
    approved, rejected or revoked and every rollback, across all pills,
    with actor, reason and the pill versions it changed."""
    _need(user, "read_audit_trail")
    from .learning import STORE as _LSTORE

    entries = []
    for e in _LSTORE.ledger:
        changed = {p: v for p, v in e["versions_after"].items() if e["versions_before"].get(p) != v}
        entries.append({**e, "changes": ", ".join(
            f"{p} v{_kb_label(e['versions_before'].get(p, 0))} → v{_kb_label(v)}" for p, v in changed.items())})
    return {"entries": entries, "chain_valid": _LSTORE.verify_ledger()}


def _kb_label(version: int) -> str:
    from .learning import kb_version_label

    return kb_version_label(version)


SEED_ACTOR = "demo-seed"


def seed_demo_cases() -> list[str]:
    """Create the demo scenarios: one CLOSED, one ESCALATED (bus fault), one
    AWAITING_APPROVAL, a borderline UPS where the AI second opinion
    disagrees with the rules (G9), and a pump that escalates until expert
    knowledge about its fault is approved. Every step is attributed to ``demo-seed``, never to
    a real user, so the audit trail does not claim a manager approved it.
    """
    from .tools import create_work_order_for_state, submit_feedback

    closed = _new_case("CRAH-DC1-01", "SA-TEMP-01", "temperature_measurement_missing",
                       ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(closed)
    closed.record_human_decision(HumanDecisionRecord(
        decision=HumanDecision.APPROVE, decided_by=SEED_ACTOR,
        rationale="seeded demo scenario (not a real approval)",
    ), actor=SEED_ACTOR)
    create_work_order_for_state(closed, closed.recommendation.actions[0])
    closed.record_outcome(Outcome(
        result=OutcomeResult.RESOLVED, root_cause_confirmed="sensor_hardware_failure",
        verified_by=SEED_ACTOR, notes="seeded: sensor replaced, temperature restored",
    ))
    fb_id = submit_feedback(closed.case_id, {
        "confirmed_cause": "sensor_hardware_failure", "outcome": "resolved",
        "submitted_by": SEED_ACTOR,
    }, state=closed)
    closed.queue_feedback(fb_id, actor=SEED_ACTOR)

    escalated = _new_case("CRAH-DC1-02", "SA-TEMP-02", "temperature_measurement_missing",
                          ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(escalated)

    awaiting = _new_case("CHILLER-DC1-01", "CH-COMP-PRESSURE", "chiller_compressor_trip",
                         ReadingStatus.ABSENT, actor=SEED_ACTOR)
    _advance(awaiting)

    disagreement = _new_case("UPS-DC1-02", "UPS-DC1-02-BATT", "ups_battery_fault",
                             ReadingStatus.INVALID, actor=SEED_ACTOR)
    _advance(disagreement)

    # Escalates on low confidence until expert knowledge about pump
    # misalignment is captured and approved (the sample interview has it).
    pump = _new_case("PUMP-DC1-01", "PUMP-DC1-01-VIB", "pump_vibration_high",
                     ReadingStatus.INVALID, actor=SEED_ACTOR)
    _advance(pump)
    return [closed.case_id, escalated.case_id, awaiting.case_id, disagreement.case_id, pump.case_id]


@app.post("/demo/seed")
def post_demo_seed(user: str = Depends(resolve_user)) -> dict:
    """Admin only: add the demo scenarios, attributed to demo-seed."""
    from .rbac import Role

    if _user(user).role != Role.ADMIN:
        raise HTTPException(403, "seeding demo cases is limited to the admin role")
    return {"seeded": seed_demo_cases(), "actor": SEED_ACTOR}


@app.get("/health")
def health() -> dict:
    """Liveness for container health checks; needs no session and reveals nothing."""
    return {"ok": True}


@app.get("/audit/status")
def get_audit_status(user: str = Depends(resolve_user)) -> dict:
    """Integrity summary for the dashboard banner: any case chain or the
    governance ledger failing verification. Visible to every role."""
    _need(user, "view_case")
    from .learning import STORE as _LSTORE
    broken = [cid for cid in STORE.list()
              if (st := STORE.get(cid)) is not None and not st.verify_audit_chain()]
    from .tools import verify_tool_log

    ledger_ok = _LSTORE.verify_ledger()
    registry_ok = STORE.verify_registry()
    tool_log_ok = verify_tool_log()
    return {"broken_cases": broken, "ledger_valid": ledger_ok,
            "ledger_problem": None if ledger_ok else _LSTORE.ledger_problem(),
            "registry_valid": registry_ok,
            "tool_log_valid": tool_log_ok,
            "ok": not broken and ledger_ok and registry_ok and tool_log_ok}


@app.post("/audit/review")
def post_audit_review(target: str, decision: str, reason: str = "",
                      user: str = Depends(resolve_user)) -> dict:
    """An auditor's recorded disposition of a chain that failed verification,
    the only way out of "frozen until an auditor reviews it".

    ``target`` is ``case:<id>``, ``ledger``, ``registry`` or ``tool_log``.
    ``decision`` is ``accept`` (the record is genuine as it stands: re-sign
    it) or, for a case, ``quarantine`` (not trusted: close it, redo the work
    as a new case). A reason is required, and every review is written to
    the governance ledger as well as to the reviewed chain itself.
    """
    _need(user, "review_audit_integrity")
    from .learning import STORE as _LSTORE
    from .tools import review_broken_tool_log, verify_tool_log

    reason = reason.strip()
    if not reason:
        raise HTTPException(400, "an integrity review needs a reason")
    if decision not in ("accept", "quarantine"):
        raise HTTPException(400, "decision must be 'accept' or 'quarantine'")
    if decision == "quarantine" and not target.startswith("case:"):
        raise HTTPException(400, "only a case can be quarantined")
    verdict = "accepted" if decision == "accept" else "quarantined"
    # The ledger first: every review is recorded in it, and recording one in
    # a ledger that fails verification would re-sign whatever broke it.
    if target != "ledger" and not _LSTORE.verify_ledger():
        raise HTTPException(409, "review the knowledge ledger first: every integrity review is "
                                 "recorded in it, so it must verify before anything else is accepted")
    try:
        if target.startswith("case:"):
            cid = target[len("case:"):]
            _get_case(cid).review_broken_chain(actor=user, reason=reason,
                                              quarantine=decision == "quarantine")
            _LSTORE.record_integrity_review(actor=user, reason=f"case {cid} {verdict}: {reason}")
        elif target == "ledger":
            _LSTORE.review_broken_ledger(actor=user, reason=reason)
        elif target == "registry":
            if STORE.verify_registry():
                raise ValueError("the case registry verifies; there is nothing to review")
            STORE.reseal()
            _LSTORE.record_integrity_review(actor=user, reason=f"case registry accepted: {reason}")
        elif target == "tool_log":
            if verify_tool_log():
                raise ValueError("the tool log verifies; there is nothing to review")
            review_broken_tool_log()
            _LSTORE.record_integrity_review(actor=user, reason=f"tool log accepted: {reason}")
        else:
            raise HTTPException(400, "target must be case:<id>, ledger, registry or tool_log")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"target": target, "decision": decision, "reviewed_by": user, **get_audit_status(user)}


@app.post("/cases/{case_id}/escalation/close")
def close_escalation(
    case_id: str, reason: str, user: str = Depends(resolve_user),
    confirmed_cause: str | None = None,
) -> dict:
    """Close an escalated case (ESCALATED -> CLOSED) with the resolution.

    ``reason`` (the resolution) is required. If ``confirmed_cause`` is
    given, the resolution is also queued as a knowledge proposal for a
    knowledge steward, so what the expert worked out is not lost.
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    if not reason.strip():
        raise HTTPException(400, "closing an escalation needs the resolution")
    confirmed = None
    if confirmed_cause:
        from .cause_registry import canonicalize_cause_id, cause_asset_type
        from .decision_tree import KNOWN_CAUSE_IDS

        confirmed = canonicalize_cause_id(confirmed_cause.strip())
        if confirmed not in KNOWN_CAUSE_IDS:
            raise HTTPException(400, f"unknown confirmed_cause {confirmed_cause!r}")
        if cause_asset_type(confirmed) != _asset_type(state.asset_id):
            raise HTTPException(400, f"cause {confirmed!r} does not belong to this asset type")
    try:
        state.close_escalation(actor=user, reason=f"escalation resolved by {user}: {reason.strip()}")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    proposal_id = None
    if confirmed:
        from .learning import STORE as _LSTORE
        from .tools import build_fault_signature

        diag = state.diagnosis
        _require_intact_ledger()
        proposal = _LSTORE.record_escalation_resolution(
            case_id=case_id, asset_id=state.asset_id, asset_type=_asset_type(state.asset_id),
            confirmed_cause=confirmed,
            proposed_cause=diag.top_cause_id if diag and diag.top_cause_id != "unresolvable" else None,
            fault_signature=build_fault_signature(
                state.observation.type, confirmed, diag.kb_refs if diag else []),
            resolution=reason.strip(), confidence=state.confidence, submitted_by=user,
        )
        proposal_id = proposal["proposal_id"]
    return {"case_id": case_id, "current_state": state.current_state.value,
            "knowledge_proposal_id": proposal_id}


@app.post("/cases/{case_id}/escalation/evidence")
def request_more_evidence(case_id: str, reason: str, user: str = Depends(resolve_user)) -> dict:
    """Request more evidence on an escalated case (ESCALATED -> GATHERING_EVIDENCE).

    The only HTTP re-entry path from ESCALATED back into the diagnosis loop
    (spec §2 transition table). An expert who needs additional sensor data
    or telemetry calls this to send the case back to evidence gathering.
    ``reason`` is REQUIRED for auditability. Requires ``approve_reject_modify``
    capability (expert/manager role).
    """
    _need(user, "approve_reject_modify")
    state = _get_case_for_write(case_id)
    try:
        state.request_more_evidence(actor=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"case_id": case_id, "current_state": state.current_state.value}


@app.get("/audit/trace")
def get_audit_trace(
    user: str = Depends(resolve_user),
    actor: str | None = None,
    case_id: str | None = None,
) -> dict:
    _need(user, "read_audit_trail")
    return {"entries": STORE.all_audit_traces(actor=actor, case_id=case_id)}


# --- helpers ---------------------------------------------------------------
def _route_explanation(state: AgentState) -> str:
    gr = state.guardrail_result
    if gr is None:
        return "no guardrail run yet"
    if gr.must_escalate or not gr.allowed:
        return "escalated: " + "; ".join(gr.reasons)
    if gr.requires_approval:
        return "awaiting human approval (G6)"
    return "allowed"