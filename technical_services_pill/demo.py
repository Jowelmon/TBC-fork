"""End-to-end demo of the Technical Services Fault Diagnosis lifecycle.

Runs the core lifecycle, learning loop, multi-asset route, and an AI HARVEST
expert-capture-to-reuse scenario:

  * CRAH-DC1-01 / SA-TEMP-01  — happy path: sensor_hardware_failure ->
      recommendation (replace sensor) -> manager APPROVE -> work order ->
      outcome resolved -> feedback -> CLOSED.
  * CRAH-DC1-02 / SA-TEMP-02  — escalation: comm_bus_failure -> guardrail
      G3 escalates -> expert closes.
  * AI HARVEST                 — grounded interview -> second-steward approval
      -> matching expert heuristic reused by a new diagnosis -> validated outcome.

Deterministic, prints a readable trace. Run:

    PYTHONPATH=/workspace python3.11 -m technical_services_pill.demo

or

    PYTHONPATH=/workspace python3.11 technical_services_pill/demo.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from .agent_state import AgentState
from .confidence import peer_agreement_from_registry, score_confidence, evidence_coverage_score
from .decision_tree import evaluate_decision_tree
from .learning import kb_version_label
from .models import (
    AgentStateName,
    CandidateCause,
    Diagnosis,
    HumanDecision,
    HumanDecisionRecord,
    Observation,
    Outcome,
    OutcomeResult,
    Recommendation,
    ReadingStatus,
)
from .tools import (
    create_work_order_for_state,
    gather_evidence_for_case,
    gather_evidence_for_fault,
    get_similar_cases,
    submit_feedback,
)


def _hr(label: str) -> str:
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


def _login(client, user_id: str):
    """Authenticate `client` as `user_id` via the real /login flow.

    Identity is a signed session cookie (auth.py), not a ?user= param, so
    every TestClient-driven scenario below logs in before acting — the same
    thing the top-bar role switcher does in /ui.
    """
    from .auth import _pins

    resp = client.post("/login", json={"user_id": user_id, "pin": _pins()[user_id]})
    resp.raise_for_status()
    return client


def _run_happy_path() -> str:
    """Spec TC1: CRAH-DC1-01 sensor_hardware_failure -> full lifecycle."""
    _hr("CASE 1 — CRAH-DC1-01 / SA-TEMP-01 (happy path)")

    obs = ReadingStatus.ABSENT
    from .models import Observation

    observation = Observation(
        type="temperature_measurement_missing",
        sensor_id="SA-TEMP-01",
        detected_at=datetime.now(timezone.utc),
        reading_status=obs,
        asset_id="CRAH-DC1-01",
    )
    state = AgentState(asset_id="CRAH-DC1-01", observation=observation)
    print(f"triggered -> {state.current_state.value}")

    # GATHERING_EVIDENCE
    evidence = gather_evidence_for_case("CRAH-DC1-01", "SA-TEMP-01")
    for ev in evidence:
        state.add_evidence(ev, actor="agent")
    print(f"gathered {len(state.evidence)} evidence items")

    # DIAGNOSING
    state.begin_diagnosing(actor="agent")
    results = evaluate_decision_tree(observation, state.evidence)
    top = results[0]
    candidates = [
        CandidateCause(
            id=r.cause_id,
            label=r.cause_label,
            likelihood=0.9 if r is top else 0.3,
            evidence_refs=r.kb_refs,
        )
        for r in results
    ]
    diagnosis = Diagnosis(
        candidate_causes=candidates,
        top_cause_id=top.cause_id,
        reasoning_trace=f"decision tree Q-branch resolved to {top.cause_id}",
        kb_refs=top.kb_refs,
    )
    coverage = evidence_coverage_score(state.evidence, 6)
    cases = get_similar_cases("supply_air_temp_absent", "CRAH", 1)
    confidence = score_confidence(
        evidence_coverage=coverage,
        peer_agreement=peer_agreement_from_registry("CRAH-DC1-01", "SA-TEMP-01"),
        kb_match=0.9 if cases else 0.0,
    )
    new_state = state.complete_diagnosis(diagnosis, confidence, actor="agent")
    print(f"diagnosis: {top.cause_id} | confidence={confidence:.2f} -> {new_state.value}")

    # RECOMMENDING -> AWAITING_APPROVAL (guardrail)
    rec = Recommendation(
        actions=[top.action],
        kb_refs=top.kb_refs,
        evidence_refs=[ev.type for ev in state.evidence],
    )
    gr = state.propose_recommendation(rec, actor="agent")
    print(f"guardrail G1-G9 -> allowed={gr.allowed} escalate={gr.must_escalate} -> {state.current_state.value}")

    # AWAITING_APPROVAL -> manager APPROVE -> EXECUTING
    approval = HumanDecisionRecord(
        decision=HumanDecision.APPROVE,
        decided_by="mgr1",
        rationale="sensor past calibration interval; replacement authorized",
    )
    state.record_human_decision(approval, actor="mgr1")
    print(f"manager APPROVED -> {state.current_state.value}")

    # EXECUTING -> create WO -> MONITORING_OUTCOME
    wo_id = create_work_order_for_state(state, top.action)
    print(f"work order {wo_id} acknowledged -> {state.current_state.value}")

    # MONITORING_OUTCOME -> record outcome -> FEEDBACK_QUEUED
    outcome = Outcome(
        result=OutcomeResult.RESOLVED,
        root_cause_confirmed=top.cause_id,
        actual_actions_taken=["sensor replaced", "calibration reset"],
        verified_by="tech1",
        notes="supply-air temp reading restored after RTD swap",
    )
    state.record_outcome(outcome)
    print(f"outcome {outcome.result.value} -> {state.current_state.value}")

    # FEEDBACK_QUEUED -> submit feedback -> CLOSED
    fb_id = submit_feedback(
        getattr(state, "case_id", "") or "demo",
        {"confirmed": True, "lesson": "cal overdue + absent -> replace"},
        state=state,
    )
    state.queue_feedback(fb_id, actor="steward1")
    print(f"feedback {fb_id} -> {state.current_state.value}")

    print(f"audit chain valid: {state.verify_audit_chain()}  entries: {len(state.history)}")
    return state.current_state.value


def _run_escalation() -> str:
    """Spec TC2: CRAH-DC1-02 comm_bus_failure -> guardrail G3 escalate.

    Drives the case through the same API path (TestClient) as a real caller.
    No hardcoded confidence: the decision tree resolves comm_bus_failure,
    the real confidence scorer runs, and guardrail G3 escalates via the
    post-G4 guardrail evaluation in ``advance_case``.
    """
    _hr("CASE 2 — CRAH-DC1-02 / SA-TEMP-02 (bus failure escalation)")

    from fastapi.testclient import TestClient

    from .app import app

    client = TestClient(app)
    _login(client, "tech1")

    # Create the case through the API (same path as real callers).
    resp = client.post("/cases", params={
        "asset_id": "CRAH-DC1-02",
        "sensor_id": "SA-TEMP-02",
        "observation_type": "temperature_measurement_missing",
        "reading_status": "absent",
    })
    resp.raise_for_status()
    body = resp.json()
    case_id = body["case_id"]
    print(f"case created -> {case_id}  state={body['current_state']}  evidence={body['evidence_count']}")

    # Advance through the real agent loop (no hardcoded confidence).
    resp = client.post(f"/cases/{case_id}/advance")
    resp.raise_for_status()
    adv = resp.json()
    final_state = adv["current_state"]
    confidence = adv["confidence"]
    print(f"advance -> {final_state}  confidence={confidence:.2f}")

    # Verify guardrail G3 fired and names the target domain.
    resp = client.get(f"/cases/{case_id}/recommendation")
    resp.raise_for_status()
    gr = resp.json().get("guardrail_result")
    if gr:
        print(f"guardrail rules: {gr.get('rule_ids')}")
        for reason in gr.get("reasons", []):
            print(f"  {reason}")
    else:
        print("guardrail_result: None (G3 did not fire)")

    # Audit chain check.
    snap = client.get(f"/cases/{case_id}").json()
    print(f"audit chain valid: {snap.get('audit_chain_valid')}  entries: {len(snap.get('history', []))}")
    return final_state


def _run_learning_loop() -> tuple[str, float, float]:
    """Case 3 — closed learning loop: feedback raises future confidence.

    1) Diagnose a fresh case, record baseline confidence + kb_match.
    2) Submit feedback confirming the cause -> promoted to a ValidatedCase.
    3) Re-diagnose an identical-signature case -> kb_match rises,
       confidence rises. Demonstrates the pill getting smarter.
    """
    from .learning import STORE as _LSTORE
    from .models import Observation

    _hr("CASE 3 — CRAH-DC1-02 / SA-TEMP-02 (learning loop)")
    sig = "supply_air_temp_absent all_tags_dead bus_unreachable controller_down"

    def _diagnose_asset(label: str) -> tuple[float, float]:
        observation = Observation(
            type="temperature_measurement_missing", sensor_id="SA-TEMP-02",
            detected_at=datetime.now(timezone.utc),
            reading_status=ReadingStatus.ABSENT, asset_id="CRAH-DC1-02",
        )
        st = AgentState(asset_id="CRAH-DC1-02", observation=observation)
        if not getattr(st, "case_id", None):
            st.case_id = f"CASE-LEARN-{label.split('#')[1].strip()[:1]}"
        evidence = gather_evidence_for_case("CRAH-DC1-02", "SA-TEMP-02")
        for ev in evidence:
            st.add_evidence(ev, actor="agent")
        st.begin_diagnosing(actor="agent")
        results = evaluate_decision_tree(observation, st.evidence)
        top = results[0]
        candidates = [
            CandidateCause(id=r.cause_id, label=r.cause_label,
                            likelihood=0.9 if r is top else 0.3, evidence_refs=r.kb_refs)
            for r in results
        ]
        diagnosis = Diagnosis(
            candidate_causes=candidates, top_cause_id=top.cause_id,
            reasoning_trace=f"decision tree -> {top.cause_id}", kb_refs=top.kb_refs,
        )
        coverage = evidence_coverage_score(st.evidence, 6)
        kb_match = _LSTORE.kb_match_score(sig, top.cause_id, "CRAH")
        confidence = score_confidence(
            evidence_coverage=coverage,
            peer_agreement=peer_agreement_from_registry("CRAH-DC1-02", "SA-TEMP-02"),
            kb_match=kb_match,
        )
        st.complete_diagnosis(diagnosis, confidence, actor="agent")
        print(f"{label}: cause={top.cause_id} | kb_match={kb_match:.3f} | confidence={confidence:.3f}")
        return st, confidence, kb_match

    # baseline (before any feedback this run)
    st1, conf1, kbm1 = _diagnose_asset("diagnose #1 (before feedback)")
    # Governance gate: feedback requires a validated outcome. The bus-failure
    # case escalated, so we record the expert's resolved outcome before
    # submitting feedback (brief: "validated outcomes can inform").
    if st1.outcome is None:
        from .models import Outcome, OutcomeResult
        st1.outcome = Outcome(
            result=OutcomeResult.RESOLVED,
            root_cause_confirmed="comm_bus_failure",
            verified_by="expert1", notes="bus controller replaced",
        )
    # submit feedback confirming the cause -> creates a pending proposal (F2)
    fb_id = submit_feedback(
        st1.case_id,
        {"confirmed_cause": "comm_bus_failure", "fault_signature": sig,
         "submitted_by": "steward1", "outcome": "resolved"},
        state=st1,
    )
    # F2: steward approves the proposal to ingest it into the live KB
    _LSTORE.approve_by_feedback_id(fb_id, decided_by="steward2")
    print(f"feedback {fb_id} proposal approved -> promoted to KB")
    print(f"  KB now: {_LSTORE.stats()['total_validated_cases']} cases, feedback_added={_LSTORE.stats()['feedback_added']}, KB {_LSTORE.label_of('CRAH')}")
    # re-diagnose identical signature -> should reuse the new validated case
    _diagnose_asset("diagnose #2 (after  feedback)")
    st2, conf2, kbm2 = _diagnose_asset("diagnose #3 (after  feedback)")
    delta = conf2 - conf1
    print(f"confidence {conf1:.3f} -> {conf2:.3f} (delta {delta:+.3f}) | kb_match {kbm1:.3f} -> {kbm2:.3f}")
    learned = delta > 0
    print(f"LEARNING LOOP {'PASSED' if learned else 'NO GAIN'}")
    return "LEARNED" if learned else "NOGAIN", conf1, conf2


def _run_multi_asset() -> bool:
    """Multi-asset generalisation: the same pill diagnoses chiller / UPS /
    pump faults by routing ``observation.type`` to a dedicated causal tree.

    Two stages:
      (1) Quick tree-routing check — every asset type resolves to a cause.
      (2) Full agent loop on one multi-asset case (chiller refrigerant_leak):
          guardrails -> HITL approve -> work order -> outcome -> feedback ->
          CLOSED, with audit-chain verification. This proves the guardrails,
          RBAC-gated workflow and tamper-evident audit apply identically across
          asset classes — not just the CRAH tree.
    """
    _hr("CASE 4 — multi-asset generalisation (chiller / UPS / pump)")
    scenarios = [
        ("CHILLER-DC1-01", "chiller_compressor_trip", "chiller"),
        ("UPS-DC1-01", "ups_battery_fault", "ups"),
        ("PUMP-DC1-01", "pump_vibration_high", "pump"),
    ]
    ok = True
    # (1) routing check
    for asset_id, fault_type, label in scenarios:
        ev = gather_evidence_for_fault(asset_id, fault_type)
        obs = Observation(
            type=fault_type, sensor_id=asset_id + "-s",
            detected_at=datetime.now(timezone.utc),
            reading_status=ReadingStatus.ABSENT, asset_id=asset_id,
        )
        results = evaluate_decision_tree(obs, ev)
        if results:
            cause = results[0].cause_id
            action = results[0].action.type
            kb = results[0].action.kb_refs[0] if results[0].action.kb_refs else "-"
            print(f"  {label:<8} [{fault_type:<22}] -> {cause:<24} action={action}  kb={kb}")
        else:
            ok = False
            print(f"  {label:<8} [{fault_type}] -> UNRESOLVED")
    print(f"  routing check: {'PASSED' if ok else 'FAILED'}")

    # (2) full agent loop on the chiller case (refrigerant_leak: non-safety,
    #     confidence-bearing — exercises guardrails G1/G6/G8 + HITL + audit).
    _hr("CASE 4b — chiller full lifecycle (guardrails / HITL / audit)")
    asset_id, fault_type, label = "CHILLER-DC1-01", "chiller_compressor_trip", "chiller"
    obs = Observation(
        type=fault_type, sensor_id="CHILLER-DC1-01-s",
        detected_at=datetime.now(timezone.utc),
        reading_status=ReadingStatus.ABSENT, asset_id=asset_id,
    )
    st = AgentState(asset_id=asset_id, observation=obs)
    print(f"triggered -> {st.current_state.value}")
    for ev in gather_evidence_for_fault(asset_id, fault_type):
        st.add_evidence(ev, actor="agent")
    print(f"gathered {len(st.evidence)} evidence items")

    st.begin_diagnosing(actor="agent")
    results = evaluate_decision_tree(obs, st.evidence)
    if not results:
        print("  chiller full-loop: UNRESOLVED (no candidate)")
        return False
    top = results[0]
    candidates = [
        CandidateCause(id=r.cause_id, label=r.cause_label,
                        likelihood=0.9 if r is top else 0.3, evidence_refs=r.kb_refs)
        for r in results
    ]
    diagnosis = Diagnosis(
        candidate_causes=candidates, top_cause_id=top.cause_id,
        reasoning_trace=f"decision tree -> {top.cause_id}", kb_refs=top.kb_refs,
    )
    from .decision_tree import FAULT_BRANCH_COUNTS
    from .learning import STORE as _LSTORE
    coverage = evidence_coverage_score(st.evidence, FAULT_BRANCH_COUNTS.get(fault_type, 6))
    sig = " ".join([fault_type.replace("_", " "), top.cause_id.replace("_", " ")])
    kb_match = _LSTORE.kb_match_score(sig, top.cause_id, "Chiller")
    confidence = score_confidence(
        evidence_coverage=coverage,
        peer_agreement=peer_agreement_from_registry(asset_id, obs.sensor_id),
        kb_match=kb_match,
    )
    new_st = st.complete_diagnosis(diagnosis, confidence, actor="agent")
    print(f"diagnosis: {top.cause_id} | confidence={confidence:.2f} -> {new_st.value}")
    if new_st != AgentStateName.RECOMMENDING:
        print(f"  chiller full-loop: did not reach RECOMMENDING ({new_st.value})")
        return False

    # guardrails -> AWAITING_APPROVAL
    rec = Recommendation(
        actions=[top.action], kb_refs=top.kb_refs,
        evidence_refs=[ev.type for ev in st.evidence],
    )
    gr = st.propose_recommendation(rec, actor="agent")
    print(f"guardrail G1-G9 -> allowed={gr.allowed} escalate={gr.must_escalate} -> {st.current_state.value}")
    if st.current_state != AgentStateName.AWAITING_APPROVAL:
        print(f"  chiller full-loop: guardrail did not route to AWAITING_APPROVAL ({st.current_state.value})")
        return False

    # HITL approve -> EXECUTING
    st.record_human_decision(
        HumanDecisionRecord(
            decision=HumanDecision.APPROVE, decided_by="mgr1",
            rationale="refrigerant leak confirmed; repair authorised",
        ), actor="mgr1")
    print(f"manager APPROVED -> {st.current_state.value}")

    # work order -> MONITORING_OUTCOME
    wo_id = create_work_order_for_state(st, top.action)
    print(f"work order {wo_id} acknowledged -> {st.current_state.value}")

    # outcome -> FEEDBACK_QUEUED
    st.record_outcome(
        Outcome(
            result=OutcomeResult.RESOLVED, root_cause_confirmed=top.cause_id,
            actual_actions_taken=["leak located", "circuit repaired", "recharged"],
            verified_by="tech1", notes="head pressure restored after repair",
        )
    )
    print(f"outcome resolved -> {st.current_state.value}")

    # feedback -> CLOSED (requires validated outcome, now present)
    fb_id = submit_feedback(
        getattr(st, "case_id", "") or "chiller-demo",
        {"confirmed_cause": top.cause_id,
         "fault_signature": "chiller compressor trip low pressure leak",
         "asset_type": "Chiller", "submitted_by": "steward1", "outcome": "resolved"},
        state=st,
    )
    st.queue_feedback(fb_id, actor="steward1")
    print(f"feedback {fb_id} -> {st.current_state.value}")
    print(f"audit chain valid: {st.verify_audit_chain()}  entries: {len(st.history)}")

    loop_ok = (st.current_state == AgentStateName.CLOSED
               and st.verify_audit_chain())
    print(f"CHILLER FULL LIFECYCLE {'PASSED' if loop_ok else 'FAILED'}")
    return ok and loop_ok


def _run_expert_harvest() -> bool:
    """Demonstrate expert capture, steward approval, reuse, and feedback."""
    from fastapi.testclient import TestClient

    from .app import app
    from .capture import SAMPLE_INTERVIEW

    _hr("CASE 5 — AI HARVEST: expert interview to reused knowledge")
    client = TestClient(app)

    _login(client, "steward1")
    response = client.post(
        "/capture/interview",
        json={
            "expert_name": "R. Tan",
            "expert_role": "Senior M&E Technician",
            "asset_type": "CRAH",
            "transcript": SAMPLE_INTERVIEW,
            "expert_consent": True,
        },
    )
    response.raise_for_status()
    draft = response.json()
    print(
        f"1. Interview extracted by {draft['provider']}: "
        f"{len(draft['heuristics'])} grounded heuristics, "
        f"{draft['dropped']} dropped"
    )
    for heuristic in draft["heuristics"]:
        print(f"   {heuristic['likely_cause']}: {heuristic['evidence_quote']}")

    def pump_case() -> tuple[str, float]:
        _login(client, "tech1")
        cid = client.post("/cases", params={
            "asset_id": "PUMP-DC1-01", "sensor_id": "PUMP-DC1-01-VIB",
            "observation_type": "pump_vibration_high", "reading_status": "invalid",
        }).json()["case_id"]
        r = client.post(f"/cases/{cid}/advance").json()
        return r["current_state"], r["confidence"]

    pump_before = pump_case()

    _login(client, "steward2")  # a DIFFERENT steward must approve
    approval = client.post(f"/kb/proposals/{draft['proposal_id']}/approve",
                           params={"rationale": "quotes checked against the interview"})
    approval.raise_for_status()
    print(
        f"2. Different steward approved {draft['proposal_id']}; "
        f"KB {', '.join(f'{p} v{kb_version_label(v)}' for p, v in approval.json()['kb_versions'].items())}"
    )
    pump_after = pump_case()
    print(
        f"   Same pump alarm before vs after: {pump_before[0]} at {pump_before[1]:.2f} -> "
        f"{pump_after[0]} at {pump_after[1]:.2f} (captured know-how changed the routing)"
    )
    if not (pump_before[0] == "ESCALATED" and pump_after[0] == "AWAITING_APPROVAL"):
        print("   expected the approved interview to move the pump case to approval; demo failed")
        return False

    _login(client, "tech1")
    created = client.post("/cases", params={
        "asset_id": "CRAH-DC1-01",
        "sensor_id": "SA-TEMP-01",
        "reading_status": "absent",
    })
    created.raise_for_status()
    case_id = created.json()["case_id"]
    advanced = client.post(f"/cases/{case_id}/advance")
    advanced.raise_for_status()
    case = client.get(f"/cases/{case_id}")
    case.raise_for_status()
    cause_id = case.json()["diagnosis"]["top_cause_id"]

    reused = client.get(f"/cases/{case_id}/expert-knowledge")
    reused.raise_for_status()
    matches = reused.json()["matches"]
    if not matches:
        print(f"3. No approved expert heuristic matched {cause_id}; demo failed")
        return False
    match = matches[0]
    print(
        f"3. New incident diagnosed as {cause_id}; reused {match['knowledge_id']} "
        f"from {match['expert_name']} ({match['kb_version_label']})"
    )

    _login(client, "mgr1")
    decision = client.post(
        f"/cases/{case_id}/approval",
        params={"decision": "approve",
                "rationale": "Approved after reviewing expert context and guardrails"},
    )
    decision.raise_for_status()
    work_order = client.post(f"/cases/{case_id}/work-order")
    work_order.raise_for_status()

    _login(client, "tech1")
    outcome = client.post(
        f"/cases/{case_id}/outcome",
        params={"result": "resolved",
                "root_cause_confirmed": cause_id,
                "notes": "Reading restored after the recommended maintenance check"},
    )
    outcome.raise_for_status()

    _login(client, "mgr1")
    feedback = client.post(f"/cases/{case_id}/feedback")
    feedback.raise_for_status()
    print(
        f"4. Human approved, work order {work_order.json()['work_order_id']} "
        f"resolved; feedback {feedback.json()['feedback_id']} queued"
    )

    _login(client, "steward1")
    queue = client.get("/kb/queue")
    queue.raise_for_status()
    feedback_proposal = next(
        (item for item in queue.json()["queue"]
         if item.get("feedback_id") == feedback.json()["feedback_id"]),
        None,
    )
    if feedback_proposal is None:
        print("5. Feedback proposal missing from steward queue; demo failed")
        return False
    learned = client.post(f"/kb/proposals/{feedback_proposal['proposal_id']}/approve",
                          params={"rationale": "outcome confirmed by the work order"})
    learned.raise_for_status()
    print(f"5. Steward validated outcome; KB is now "
          f"{', '.join(f'{p} v{kb_version_label(v)}' for p, v in learned.json()['kb_versions'].items())}")
    return True


def main() -> None:
    c1 = _run_happy_path()
    c2 = _run_escalation()
    c3, conf1, conf2 = _run_learning_loop()
    c4 = _run_multi_asset()
    c5 = _run_expert_harvest()
    _hr("SUMMARY")
    print(f"Case 1 final state: {c1}  (expected CLOSED)")
    print(f"Case 2 final state: {c2}  (expected ESCALATED)")
    print(f"Case 3 learning:    {c3}  (confidence {conf1:.2f} -> {conf2:.2f})")
    print(f"Case 4 multi-asset: {'PASSED' if c4 else 'FAILED'}")
    print(f"Case 5 AI HARVEST:  {'PASSED' if c5 else 'FAILED'}")
    ok = (c1 == AgentStateName.CLOSED.value
          and c2 == AgentStateName.ESCALATED.value
          and c3 == "LEARNED" and c4 and c5)
    print(f"DEMO {'PASSED' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()