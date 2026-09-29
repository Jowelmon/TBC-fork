"""End-to-end demo of the Technical Services Fault Diagnosis lifecycle.

Runs the full agent loop for both demo CRAH units:

  * CRAH-DC1-01 / SA-TEMP-01  — happy path: sensor_hardware_failure ->
      recommendation (replace sensor) -> manager APPROVE -> work order ->
      outcome resolved -> feedback -> CLOSED.
  * CRAH-DC1-02 / SA-TEMP-02  — escalation: comm_bus_failure -> guardrail
      G3 escalates -> expert closes.

Deterministic, prints a readable trace. Run:

    PYTHONPATH=/workspace python3.11 -m technical_services_pill.demo

or

    PYTHONPATH=/workspace python3.11 technical_services_pill/demo.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from .agent_state import AgentState
from .confidence import score_confidence, evidence_coverage_score
from .decision_tree import evaluate_decision_tree
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
    RecommendationAction,
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
        peer_agreement=1.0,
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
    print(f"guardrail G1-G8 -> allowed={gr.allowed} escalate={gr.must_escalate} -> {state.current_state.value}")

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
    """Spec TC2: CRAH-DC1-02 comm_bus_failure -> guardrail G3 escalate."""
    _hr("CASE 2 — CRAH-DC1-02 / SA-TEMP-02 (bus failure escalation)")

    from .models import Observation

    observation = Observation(
        type="temperature_measurement_missing",
        sensor_id="SA-TEMP-02",
        detected_at=datetime.now(timezone.utc),
        reading_status=ReadingStatus.ABSENT,
        asset_id="CRAH-DC1-02",
    )
    state = AgentState(asset_id="CRAH-DC1-02", observation=observation)
    print(f"triggered -> {state.current_state.value}")

    evidence = gather_evidence_for_case("CRAH-DC1-02", "SA-TEMP-02")
    for ev in evidence:
        state.add_evidence(ev, actor="agent")
    print(f"gathered {len(state.evidence)} evidence items")

    state.begin_diagnosing(actor="agent")
    results = evaluate_decision_tree(observation, state.evidence)
    top = results[0]
    candidates = [
        CandidateCause(id=r.cause_id, label=r.cause_label, likelihood=0.9 if r is top else 0.3)
        for r in results
    ]
    diagnosis = Diagnosis(
        candidate_causes=candidates,
        top_cause_id=top.cause_id,
        reasoning_trace=f"decision tree -> {top.cause_id}; all tags dead",
        kb_refs=top.kb_refs,
    )
    confidence = 0.8
    new_state = state.complete_diagnosis(diagnosis, confidence, actor="agent")
    print(f"diagnosis: {top.cause_id} | confidence={confidence:.2f} -> {new_state.value}")

    # RECOMMENDING -> guardrail G3 (cross-domain BMS) must escalate
    rec = Recommendation(
        actions=[top.action],
        kb_refs=top.kb_refs,
        evidence_refs=[ev.type for ev in state.evidence],
    )
    state.propose_recommendation(rec, actor="agent")
    print(f"guardrail G3 (BMS cross-domain) -> MUST ESCALATE -> {state.current_state.value}")
    print(f"audit chain valid: {state.verify_audit_chain()}  entries: {len(state.history)}")
    return state.current_state.value


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
        confidence = score_confidence(evidence_coverage=coverage, peer_agreement=1.0, kb_match=kb_match)
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
    # submit feedback confirming the cause -> promoted into the KB
    fb_id = submit_feedback(
        st1.case_id,
        {"confirmed_cause": "comm_bus_failure", "fault_signature": sig,
         "submitted_by": "steward1", "outcome": "resolved"},
        state=st1,
    )
    print(f"feedback {fb_id} confirmed comm_bus_failure -> promoted to KB")
    print(f"  KB now: {_LSTORE.stats()['total_validated_cases']} cases, feedback_added={_LSTORE.stats()['feedback_added']}")
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
    from .confidence import evidence_coverage_score, score_confidence
    from .decision_tree import FAULT_BRANCH_COUNTS
    from .learning import STORE as _LSTORE
    coverage = evidence_coverage_score(st.evidence, FAULT_BRANCH_COUNTS.get(fault_type, 6))
    sig = " ".join([fault_type.replace("_", " "), top.cause_id.replace("_", " ")])
    kb_match = _LSTORE.kb_match_score(sig, top.cause_id, "Chiller")
    confidence = score_confidence(evidence_coverage=coverage, peer_agreement=1.0, kb_match=kb_match)
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
    print(f"guardrail G1-G8 -> allowed={gr.allowed} escalate={gr.must_escalate} -> {st.current_state.value}")
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


def main() -> None:
    c1 = _run_happy_path()
    c2 = _run_escalation()
    c3, conf1, conf2 = _run_learning_loop()
    c4 = _run_multi_asset()
    _hr("SUMMARY")
    print(f"Case 1 final state: {c1}  (expected CLOSED)")
    print(f"Case 2 final state: {c2}  (expected ESCALATED)")
    print(f"Case 3 learning:    {c3}  (confidence {conf1:.2f} -> {conf2:.2f})")
    print(f"Case 4 multi-asset: {'PASSED' if c4 else 'FAILED'}")
    ok = (c1 == AgentStateName.CLOSED.value
          and c2 == AgentStateName.ESCALATED.value
          and c3 == "LEARNED" and c4)
    print(f"DEMO {'PASSED' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()