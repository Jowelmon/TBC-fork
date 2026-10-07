#!/usr/bin/env python3
"""EVAL-01 .. EVAL-12: acceptance evals for the submission, run via `make eval`.

Each eval is a self-contained scenario check (not a copy of the pytest
suite) exercised against a freshly isolated store, printed as a pass/fail
table. Exits non-zero if anything fails, so it can gate CI the same way
`make test` does.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

# Isolate from any real demo/test database before importing the app.
_TMP = tempfile.mkdtemp(prefix="tbc-evals-")
os.environ["TBC_DB_PATH"] = os.path.join(_TMP, "tbc.sqlite")
os.environ["TBC_CASE_DB_PATH"] = os.path.join(_TMP, "cases.sqlite3")
os.environ["TBC_PERSIST"] = "1"
os.environ.setdefault("TBC_DEMO_INSECURE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient  # noqa: E402

from technical_services_pill.app import app  # noqa: E402

RESULTS: list[tuple[str, str, bool, str]] = []  # (id, title, passed, detail)


def eval_(eval_id: str, title: str):
    def decorator(fn):
        def wrapper():
            client = TestClient(app)
            try:
                detail = fn(client) or "ok"
                RESULTS.append((eval_id, title, True, detail))
            except AssertionError as exc:
                RESULTS.append((eval_id, title, False, str(exc)))
            except Exception as exc:  # noqa: BLE001 -- an eval erroring is a failure, not a crash
                RESULTS.append((eval_id, title, False, f"{type(exc).__name__}: {exc}"))
        return wrapper
    return decorator


def _create_and_advance(client: TestClient, asset_id="CRAH-DC1-01", sensor_id="SA-TEMP-01",
                         observation_type="temperature_measurement_missing", reading_status="absent") -> dict:
    resp = client.post("/cases", params={
        "asset_id": asset_id, "sensor_id": sensor_id, "user": "tech1",
        "observation_type": observation_type, "reading_status": reading_status,
    })
    assert resp.status_code == 200, f"create failed: {resp.text}"
    case_id = resp.json()["case_id"]
    resp = client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    assert resp.status_code == 200, f"advance failed: {resp.text}"
    return client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()


# --------------------------------------------------------------------------- #
@eval_("EVAL-01", "ADP call: second opinion routes through the real provider seam")
def eval_01(client):
    from technical_services_pill import ai_reasoning, llm
    assert llm.provider_name() in ("mock", "adp")
    result = ai_reasoning.generate_diagnostic_hypothesis(
        asset={"asset_id": "CRAH-DC1-01", "asset_type": "CRAH"},
        observations={"type": "x", "sensor_id": "SA-1", "reading_status": "absent"},
        evidence=[], candidate_causes=["sensor_hardware_failure"],
        rule_top_cause="sensor_hardware_failure",
    )
    for key in ("status", "hypothesis", "agrees_with_rules", "summary"):
        assert key in result, f"missing {key!r} in hypothesis shape"
    return f"provider={llm.provider_name()}, status={result['status']}"


@eval_("EVAL-02", "AI cannot bypass approval: disagreement never auto-changes state")
def eval_02(client):
    from technical_services_pill import app as app_module

    def fake_hyp(**kw):
        other = next((c for c in kw["candidate_causes"] if c != kw["rule_top_cause"]), None)
        return {"status": "ok", "hypothesis": other, "agrees_with_rules": False,
                "summary": "", "supporting_evidence": [], "conflicting_evidence": [],
                "missing_evidence": [], "recommended_next_check": ""}

    orig = app_module.generate_diagnostic_hypothesis
    app_module.generate_diagnostic_hypothesis = fake_hyp
    try:
        snap = _create_and_advance(client)
    finally:
        app_module.generate_diagnostic_hypothesis = orig
    assert snap["current_state"] == "AWAITING_APPROVAL", "AI disagreement must not change routing"
    gr = snap["guardrail_result"]
    assert "G9" in gr["rule_ids"], "disagreement must still be flagged (G9)"
    resp = client.post(f"/cases/{snap['case_id']}/approval", params={
        "user": "tech1", "decision": "approve", "rationale": "x",
    })
    assert resp.status_code == 403, "a technician must still be refused, regardless of AI opinion"
    return "G9 flagged, routing unchanged, technician still refused"


@eval_("EVAL-03", "AI failure: timeout/malformed reply falls back, diagnosis unaffected")
def eval_03(client):
    from technical_services_pill import ai_reasoning, llm

    def boom(**kw):
        raise llm.LLMError("simulated timeout")

    orig = ai_reasoning.diagnostic_second_opinion
    ai_reasoning.diagnostic_second_opinion = boom
    try:
        snap = _create_and_advance(client)
    finally:
        ai_reasoning.diagnostic_second_opinion = orig
    assert snap["ai_hypothesis"]["status"] == "unavailable"
    assert snap["diagnosis"] is not None, "rule-based diagnosis must proceed despite AI failure"
    assert snap["current_state"] == "AWAITING_APPROVAL"
    return "deterministic diagnosis unaffected by AI failure"


@eval_("EVAL-04", "Unknown asset escalates (G5), never silently diagnosed")
def eval_04(client):
    resp = client.post("/cases", params={
        "asset_id": "NOT-A-REAL-ASSET", "sensor_id": "X", "user": "tech1",
        "observation_type": "temperature_measurement_missing", "reading_status": "absent",
    })
    case_id = resp.json()["case_id"]
    client.post(f"/cases/{case_id}/advance", params={"user": "tech1"})
    snap = client.get(f"/cases/{case_id}", params={"user": "tech1"}).json()
    assert snap["current_state"] == "ESCALATED"
    assert "G5" in snap["guardrail_result"]["rule_ids"]
    return "unknown asset escalated via G5"


@eval_("EVAL-05", "Cause IDs are canonical everywhere -- no short aliases emitted")
def eval_05(client):
    from technical_services_pill.cause_registry import CANONICAL_CAUSE_IDS
    from technical_services_pill.decision_tree import KNOWN_CAUSE_IDS
    # "unresolvable" is a documented sentinel (decision_tree.py), not a
    # cause -- emitted only when the tree resolves nothing, and explicitly
    # allowed so Outcome.root_cause_confirmed can record "no cause found".
    non_canonical = (KNOWN_CAUSE_IDS - CANONICAL_CAUSE_IDS) - {"unresolvable"}
    assert not non_canonical, f"non-canonical cause ids in decision tree: {non_canonical}"
    snap = _create_and_advance(client)
    top = snap["diagnosis"]["top_cause_id"]
    assert top in CANONICAL_CAUSE_IDS, f"{top!r} is not a canonical cause id"
    real_causes = KNOWN_CAUSE_IDS - {"unresolvable"}
    return f"{len(real_causes)} decision-tree causes all canonical (+ 1 documented sentinel)"


@eval_("EVAL-06", "Persistence: case state survives a process restart")
def eval_06(client):
    from technical_services_pill.store import CaseStore
    snap = _create_and_advance(client)
    case_id = snap["case_id"]
    # Simulate a restart: a brand new CaseStore reading the same DB file.
    reloaded = CaseStore(os.environ["TBC_CASE_DB_PATH"])
    restored = reloaded.snapshot(case_id)
    assert restored is not None, "case not found after simulated restart"
    assert restored["current_state"] == snap["current_state"]
    assert restored["confidence"] == snap["confidence"]
    return f"{case_id} restored with identical state after reload"


@eval_("EVAL-07", "Feedback governance: proposal only, self-approval blocked")
def eval_07(client):
    snap = _create_and_advance(client)
    case_id = snap["case_id"]
    client.post(f"/cases/{case_id}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "x"})
    client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure",
    })
    version_before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    fb = client.post(f"/cases/{case_id}/feedback", params={"user": "steward1"}).json()
    assert fb["proposal_status"] == "pending", "feedback must not enter the KB directly"
    version_after_submit = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    assert version_after_submit == version_before, "KB version must not move before approval"
    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    pid = next(p["proposal_id"] for p in queue if p["feedback_id"] == fb["feedback_id"])
    resp = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward1"})
    assert resp.status_code == 403, "the proposer must not be able to approve their own proposal"
    resp = client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2"})
    assert resp.status_code == 200, "a different steward must be able to approve"
    return "pending proposal, self-approval blocked, second steward approved"


@eval_("EVAL-08", "Approval: only approve_reject_modify roles may decide")
def eval_08(client):
    snap = _create_and_advance(client)
    case_id = snap["case_id"]
    for role, expect_ok in (("tech1", False), ("auditor1", False), ("mgr1", True)):
        client2 = TestClient(app)
        # fresh case per role so a prior approval doesn't block the next check
        if role != "mgr1":
            resp = client2.post(f"/cases/{case_id}/approval", params={
                "user": role, "decision": "approve", "rationale": "x",
            })
            assert (resp.status_code == 200) == expect_ok, f"{role}: expected ok={expect_ok}, got {resp.status_code}"
    resp = client.post(f"/cases/{case_id}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "x"})
    assert resp.status_code == 200
    return "technician/auditor refused, manager approved"


@eval_("EVAL-09", "Rollback: KB version reverts and confidence is restored exactly")
def eval_09(client):
    baseline = _create_and_advance(client)
    confidence_before = baseline["confidence"]
    version_before = client.get("/kb/stats", params={"user": "tech1"}).json()["kb_version"]
    case_id = baseline["case_id"]
    client.post(f"/cases/{case_id}/approval", params={"user": "mgr1", "decision": "approve", "rationale": "x"})
    client.post(f"/cases/{case_id}/work-order", params={"user": "mgr1"})
    client.post(f"/cases/{case_id}/outcome", params={
        "user": "tech1", "result": "resolved", "root_cause_confirmed": "sensor_hardware_failure",
    })
    fb = client.post(f"/cases/{case_id}/feedback", params={"user": "steward1"}).json()
    queue = client.get("/kb/queue", params={"user": "steward1"}).json()["queue"]
    pid = next(p["proposal_id"] for p in queue if p["feedback_id"] == fb["feedback_id"])
    client.post(f"/kb/proposals/{pid}/approve", params={"user": "steward2"})

    resp = client.post(f"/kb/rollback/{version_before}", params={"user": "admin1", "reason": "test rollback"})
    assert resp.status_code == 200, resp.text
    restored = _create_and_advance(client)
    assert restored["confidence"] == confidence_before, (
        f"rollback did not restore confidence exactly: {restored['confidence']} != {confidence_before}"
    )
    return f"confidence restored to {confidence_before} after rollback"


@eval_("EVAL-10", "Audit: hash chain verifies, and tampering is detectable")
def eval_10(client):
    snap = _create_and_advance(client)
    assert snap["audit_chain_valid"] is True
    assert len(snap["history"]) >= 2
    # Tamper with one entry's reason and confirm verification would catch it
    # (verified via the same algorithm store.py/agent_state.py use).
    from technical_services_pill.audit import compute_hash
    entry = dict(snap["history"][0])
    entry["reason"] = "TAMPERED"
    recomputed = compute_hash(entry["prev_hash"], {
        "from_state": entry["from_state"], "to_state": entry["to_state"],
        "at": entry["at"], "actor": entry["actor"], "reason": entry["reason"],
    })
    assert recomputed != entry["hash"], "a tampered reason must change the hash"
    return "chain valid; a tampered entry's hash provably differs"


@eval_("EVAL-11", "RBAC: capability matrix matches the spec for every role")
def eval_11(client):
    from technical_services_pill.rbac import DEMO_USERS, can
    expectations = {
        "tech1": {"view_case": True, "record_outcome": True, "approve_reject_modify": False},
        "mgr1": {"view_case": True, "approve_reject_modify": True, "submit_feedback": True},
        "steward1": {"approve_knowledge_version": True, "approve_reject_modify": False},
        "auditor1": {"read_audit_trail": True, "approve_reject_modify": False},
        "admin1": {"approve_reject_modify": True, "approve_knowledge_version": True, "read_audit_trail": True},
    }
    for user_id, caps in expectations.items():
        role = DEMO_USERS[user_id].role
        for cap, expected in caps.items():
            assert can(role, cap) == expected, f"{user_id}/{role.value}: {cap} expected {expected}"
    return f"{sum(len(c) for c in expectations.values())} capability checks across {len(expectations)} roles"


@eval_("EVAL-12", "No invented evidence: capture drops ungrounded heuristics")
def eval_12(client):
    from technical_services_pill import capture
    transcript = "Interviewer: What do you check?\n\nTechnician: I always check the obvious thing first."
    try:
        draft = capture.draft_from_transcript(transcript, "CRAH")
        assert draft["heuristics"] == [], "a transcript naming no known fault pattern should yield nothing"
    except capture.CaptureError:
        pass  # also acceptable: no grounded heuristic at all
    # Directly probe the grounding gate with a fabricated quote.
    kept, warnings = capture._validate_items(
        capture._sanitize(transcript)[0],
        [{"symptom_pattern": "x", "likely_cause": "sensor_hardware_failure",
          "evidence_quote": "this exact sentence is not in the transcript"}],
        "CRAH",
    )
    assert kept == [], "an ungrounded quote must be dropped, not trusted"
    assert warnings, "dropping an ungrounded item must be explained"
    return "ungrounded heuristic dropped with a warning, nothing fabricated survives"


EVALS = [eval_01, eval_02, eval_03, eval_04, eval_05, eval_06, eval_07, eval_08, eval_09, eval_10, eval_11, eval_12]


def main() -> int:
    for fn in EVALS:
        fn()

    width = max(len(title) for _, title, _, _ in RESULTS)
    print(f"{'ID':9s}  {'EVAL':{width}s}  RESULT")
    print("-" * (9 + 2 + width + 2 + 10))
    failures = 0
    for eid, title, passed, detail in RESULTS:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failures += 1
        print(f"{eid:9s}  {title:{width}s}  {status}")
        print(f"{'':9s}  {'':{width}s}  -> {detail}")
    print("-" * (9 + 2 + width + 2 + 10))
    print(f"{len(RESULTS) - failures}/{len(RESULTS)} evals passed")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
