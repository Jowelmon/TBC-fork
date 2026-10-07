"""Agent function-calling tools for the Technical Services Fault Diagnosis pill.

Implements spec §3. Tools fall into four groups:

1. Evidence-gathering   — read mock BMS / sensor / history / config
2. Knowledge             — RAG over validated cases + heuristics
3. Reasoning             — causal hypothesis scoring
4. Output / action       — recommendation, work order, outcome, feedback,
                            escalate, cross-pill coordination

Every tool call appends a record to ``TOOL_AUDIT_LOG`` so the trace is
reconstructable. Output/action tools integrate with ``AgentState``; in
particular ``create_work_order_for_state`` enforces the spec §3 guardrail
that a work order may NOT be raised without a prior approve/modify
``human_decision``; the bare internal helper is private.

Deterministic, in-memory only — no network, no LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .mock_registry import (
    ASSETS,
    BMS_STATUS,
    CONFIG_CHANGE_LOG,
    LIVE_READINGS,
    MAINTENANCE_HISTORY,
    SENSORS,
    TELEMETRY,
    KNOWLEDGE_BASE,
    KNOWLEDGE_VERSION,
    _is_past_calibration,
    get_registry,
)
from .models import (
    ESCALATE_CONFIDENCE,
    MIN_RECO_CONFIDENCE,
    AgentStateName,
    EvidenceItem,
    GuardrailContext,
    GuardrailResult,
    HumanDecision,
    HumanDecisionRecord,
    Outcome,
    OutcomeResult,
    Recommendation,
    RecommendationAction,
)

# Avoid a hard import cycle: AgentState imports nothing from this module, so a
# local import inside the action tools is safe and keeps the module loadable
# even before agent_state.py is present (used by unit tests of read-tools).


# --- Tool audit log (spec §6 trace reconstructability) --------------------
# Keyed hash chain with a seal over length and head, like the case and
# knowledge chains, so wiping or editing the log is detectable.
TOOL_AUDIT_LOG: list[dict] = []
TOOL_LOG_SEAL: dict[str, str | None] = {"seal": None}
_TOOL_FIELDS = ("tool", "inputs", "output_type", "timestamp", "actor")


def _seal_tool_log() -> None:
    from .audit import compute_hash

    head = TOOL_AUDIT_LOG[-1]["hash"] if TOOL_AUDIT_LOG else ""
    TOOL_LOG_SEAL["seal"] = compute_hash("seal", {"length": len(TOOL_AUDIT_LOG), "head": head})


def verify_tool_log() -> bool:
    from .audit import compute_hash, verify_chain

    if not verify_chain(TOOL_AUDIT_LOG, _TOOL_FIELDS):
        return False
    head = TOOL_AUDIT_LOG[-1]["hash"] if TOOL_AUDIT_LOG else ""
    return TOOL_LOG_SEAL["seal"] == compute_hash("seal", {"length": len(TOOL_AUDIT_LOG), "head": head})


def _log(tool: str, inputs: dict, output: Any) -> None:
    import json

    from .audit import GENESIS_HASH, compute_hash

    entry = {
        "tool": tool,
        # Stored as it will be after a JSON round trip, so the hash survives a restart.
        "inputs": json.loads(json.dumps(inputs, default=str)),
        "output_type": type(output).__name__,
        "timestamp": datetime.now().isoformat(),
        "actor": "agent",
        "prev_hash": TOOL_AUDIT_LOG[-1]["hash"] if TOOL_AUDIT_LOG else GENESIS_HASH,
    }
    entry["hash"] = compute_hash(entry["prev_hash"], {f: entry[f] for f in _TOOL_FIELDS})
    TOOL_AUDIT_LOG.append(entry)
    _seal_tool_log()


def _now() -> datetime:
    return datetime.now()


# ========================================================================== #
# 1. Evidence-gathering tools (read from mock_registry)
# ========================================================================== #
def get_asset_profile(asset_id: str) -> dict | None:
    profile = ASSETS.get(asset_id)
    if profile is not None:
        profile = dict(profile)  # defensive copy
    _log("get_asset_profile", {"asset_id": asset_id}, profile)
    return profile


def get_sensor_readings(asset_id: str, sensor_id: str, window: str = "1h") -> dict:
    reading = dict(LIVE_READINGS.get(sensor_id, {}))
    reading.setdefault("sensor_id", sensor_id)
    reading["window"] = window
    _log("get_sensor_readings", {"asset_id": asset_id, "sensor_id": sensor_id, "window": window}, reading)
    return reading


def get_sensor_metadata(sensor_id: str) -> dict | None:
    meta = SENSORS.get(sensor_id)
    if meta is not None:
        meta = dict(meta)
        meta["is_past_calibration"] = _is_past_calibration(meta)
    _log("get_sensor_metadata", {"sensor_id": sensor_id}, meta)
    return meta


def query_bms_status(asset_id: str) -> dict:
    status = dict(BMS_STATUS.get(asset_id, {"asset_id": asset_id, "controller_reachable": False, "bus_reachable": False}))
    _log("query_bms_status", {"asset_id": asset_id}, status)
    return status


def get_maintenance_history(asset_id: str) -> list:
    history = [dict(h) for h in MAINTENANCE_HISTORY.get(asset_id, [])]
    _log("get_maintenance_history", {"asset_id": asset_id}, history)
    return history


def get_config_change_log(asset_id: str, window: str = "30d") -> list:
    log = [dict(c) for c in CONFIG_CHANGE_LOG.get(asset_id, [])]
    _log("get_config_change_log", {"asset_id": asset_id, "window": window}, log)
    return log


def gather_evidence_for_case(asset_id: str, sensor_id: str) -> list[EvidenceItem]:
    """Call every evidence-gathering tool and return assembled EvidenceItem list.

    This is the function the agent loop calls during GATHERING_EVIDENCE.
    """
    gathered: list[EvidenceItem] = []

    asset = get_asset_profile(asset_id)
    if asset is not None:
        gathered.append(EvidenceItem(
            source="bms", type="asset_profile", payload=asset,
            retrieved_at=_now(), tool="get_asset_profile", kb_refs=[],
        ))

    reading = get_sensor_readings(asset_id, sensor_id)
    gathered.append(EvidenceItem(
        source="sensor", type="reading", payload=reading,
        retrieved_at=_now(), tool="get_sensor_readings", kb_refs=[],
    ))

    meta = get_sensor_metadata(sensor_id)
    if meta is not None:
        calibration_overdue = bool(meta.get("is_past_calibration", False))
        # Decision tree (Q5) reads `past_eol` / `calibration_overdue`.
        tree_meta = dict(meta)
        tree_meta["calibration_overdue"] = calibration_overdue
        tree_meta["past_eol"] = calibration_overdue  # approximate EOL by overdue calibration
        gathered.append(EvidenceItem(
            source="sensor", type="metadata", payload=tree_meta,
            retrieved_at=_now(), tool="get_sensor_metadata",
            kb_refs=["KB-H3"] if calibration_overdue else [],
        ))

    bms = query_bms_status(asset_id)
    bus_dead = not bms.get("bus_reachable", True) or not bms.get("tags_alive")
    other_reporting = bool(bms.get("tags_alive"))
    # Decision tree (Q2/Q6) reads `bus_alive` / `other_tags_reporting` /
    # `gateway_healthy` / `scada_link_healthy`.
    tree_bms = dict(bms)
    tree_bms["bus_alive"] = bool(bms.get("bus_reachable", False))
    tree_bms["other_tags_reporting"] = other_reporting
    tree_bms["gateway_healthy"] = bms.get("gateway_heartbeat") == "ok"
    tree_bms["scada_link_healthy"] = bms.get("scada_link") == "ok"
    kb = ["KB-H2"] if bus_dead else ["KB-H1"]
    gathered.append(EvidenceItem(
        source="bms", type="status", payload=tree_bms,
        retrieved_at=_now(), tool="query_bms_status", kb_refs=kb,
    ))

    hist = get_maintenance_history(asset_id)
    if hist:
        # Only maintenance that physically disturbed the sensor/wiring counts
        # as a "recent disturbance" for Q4 (loose_wiring). Filter swaps and
        # routine inspections do NOT.
        disturb_types = ("sensor_replacement", "wiring_inspection", "sensor_calibration")
        recent_disturbance = any(
            h.get("type") in disturb_types for h in hist
        )
        # Decision tree (Q4) reads `recent_disturbance`.
        gathered.append(EvidenceItem(
            source="history", type="log", payload={"records": hist, "recent_disturbance": recent_disturbance},
            retrieved_at=_now(), tool="get_maintenance_history",
            kb_refs=["KB-H5"] if recent_disturbance else [],
        ))

    cfg = get_config_change_log(asset_id)
    if cfg:
        tag_remap = any(
            "tag" in str(c.get("change", "")).lower() or c.get("affected_tags")
            for c in cfg
        )
        # Decision tree (Q3) reads `recent_change` and a `changes` list whose
        # entries may have type `tag_renamed` / `tag_removed`.
        changes = [
            {"type": "tag_renamed" if "tag" in str(c.get("change", "")).lower() else c.get("change", "other"),
             "at": c.get("at"), "by": c.get("by")}
            for c in cfg
        ]
        gathered.append(EvidenceItem(
            source="config", type="log",
            payload={"records": cfg, "tag_remap": tag_remap,
                     "recent_change": tag_remap, "changes": changes},
            retrieved_at=_now(), tool="get_config_change_log",
            kb_refs=["KB-H4"] if tag_remap else [],
        ))

    _log("gather_evidence_for_case", {"asset_id": asset_id, "sensor_id": sensor_id},
         f"{len(gathered)} evidence items")
    return gathered


def gather_evidence_for_fault(asset_id: str, fault_type: str) -> list[EvidenceItem]:
    """Asset/fault-aware evidence gatherer (multi-asset generalisation).

    Routes by ``fault_type`` to the matching evidence contract. CRAH
    temperature-sensor faults delegate to the original ``gather_evidence_for_case``
    (which reads SENSORS / BMS_STATUS / etc.). Chiller / UPS / pump faults read
    from the ``TELEMETRY`` registry. Returns [] for unknown fault types so the
    agent escalates.
    """
    # CRAH tree reuses the sensor-centric gatherer.
    if fault_type == "temperature_measurement_missing":
        sensor_id = ""
        for sid, s in SENSORS.items():
            if s.get("asset_id") == asset_id:
                sensor_id = sid
                break
        return gather_evidence_for_case(asset_id, sensor_id)

    records = TELEMETRY.get(asset_id)
    if not records:
        _log("gather_evidence_for_fault",
             {"asset_id": asset_id, "fault_type": fault_type}, "no telemetry")
        return []

    gathered: list[EvidenceItem] = []
    now = _now()
    for source, etype, payload, kb_refs in records:
        gathered.append(EvidenceItem(
            source=source, type=etype, payload=payload,
            retrieved_at=now, tool="asset_telemetry", kb_refs=list(kb_refs),
        ))
    _log("gather_evidence_for_fault",
         {"asset_id": asset_id, "fault_type": fault_type},
         f"{len(gathered)} evidence items")
    return gathered


# ========================================================================== #
# 2. Knowledge tools (RAG over validated heuristics + cases)
# ========================================================================== #
def _current_kb_version_label() -> str:
    """Live KB version; falls back to the seed label if the store is unavailable."""
    try:
        from .learning import STORE as _LSTORE
        return _LSTORE.get_kb_version_label()
    except ImportError:  # pragma: no cover
        return KNOWLEDGE_VERSION


def query_knowledge_base(pill: str, query: str) -> dict:
    """Return matching heuristics + causal models for ``query``.

    ``pill`` is the pill identifier (e.g. "technical_services"). Matching is
    a simple keyword scan — deterministic stand-in for an embedding RAG.
    """
    q = (query or "").lower()
    heuristics = [
        h for h in KNOWLEDGE_BASE["heuristics"]
        if any(tok in q for tok in (h["rule"], h["description"].lower()))
        or not q
    ]
    causal = [
        c for c in KNOWLEDGE_BASE["causal_models"]
        if any(tok in q for tok in (c["cause"].lower(), c["description"].lower()))
        or not q
    ]
    out = {
        "pill": pill,
        "version": _current_kb_version_label(),
        "heuristics": heuristics,
        "causal_models": causal,
        "kb_refs": [h["id"] for h in heuristics] + [c["id"] for c in causal],
    }
    _log("query_knowledge_base", {"pill": pill, "query": query}, out)
    return out


def get_similar_cases(fault_signature: str, asset_type: str = "CRAH", k: int = 3) -> list:
    """Return up to ``k`` validated past cases similar to ``fault_signature``.

    Queries the LearningStore (which grows as feedback is submitted) merged
    with the seed registry cases — deterministic RAG stand-in that reflects
    the closed learning loop.
    """
    from .learning import STORE as _LSTORE

    learning_hits = _LSTORE.get_similar(fault_signature, asset_type, k=k)
    # also keep raw registry hits as a baseline pool
    sig_tokens = set((fault_signature or "").lower().split())

    def _score(case: dict) -> int:
        case_tokens = set(case.get("fault_signature", "").lower().split())
        return len(sig_tokens & case_tokens) + (2 if case.get("asset_type") == asset_type else 0)

    registry_top = sorted(KNOWLEDGE_BASE["cases"], key=_score, reverse=True)[:max(0, k)]
    seen: set[str] = set()
    out: list = []
    for vc in learning_hits:
        if vc.id in seen:
            continue
        seen.add(vc.id)
        out.append({
            "id": vc.id, "case_id": vc.case_id, "asset_type": vc.asset_type,
            "fault_signature": vc.fault_signature, "root_cause": vc.confirmed_cause,
            "action_taken": vc.action_taken, "outcome": vc.outcome,
            "validated": True, "corrected": vc.corrected, "source": "learning_store",
        })
    for c in registry_top:
        cid = c.get("kb_ref", c.get("id", ""))
        if cid in seen:
            continue
        seen.add(cid)
        out.append(dict(c, source="registry"))
        if len(out) >= k:
            break
    _log("get_similar_cases",
         {"fault_signature": fault_signature, "asset_type": asset_type, "k": k},
         out)
    return out


# ========================================================================== #
# 3. Reasoning tools
# ========================================================================== #
# The causal-hypothesis scoring tool (``evaluate_causal_hypothesis``) was
# removed during code review — the deterministic decision tree in
# ``decision_tree.py`` is the single source of truth for cause scoring, and
# the standalone heuristic scorer was never called by the agent loop, demo,
# or tests. Keeping one scoring path avoids divergence between two
# independent scoring heuristics.


# ========================================================================== #
# 4. Output / action tools (integrate with AgentState)
# ========================================================================== #
def request_human_approval(
    state: "AgentStateLike",
    recommendation: Recommendation,
    *,
    guardrail_ctx: GuardrailContext | None = None,
) -> GuardrailResult:
    """Propose a recommendation; the state machine routes to APPROVAL/ESCALATED."""
    result = state.propose_recommendation(
        recommendation, guardrail_ctx=guardrail_ctx, actor="agent"
    )
    return result


def _create_work_order(action: RecommendationAction, asset_id: str, case_id: str) -> str:
    """Raise a CMMS work order id (internal helper, no guardrail check).

    Spec §3 guardrail (also enforced by ``AgentState.acknowledge_work_order``
    precondition): a WO may only be created AFTER an approve/modify decision.
    This thin helper intentionally performs NO guardrail check — callers MUST
    go through the state-aware ``create_work_order_for_state`` (the only
    sanctioned public entry point) which enforces the precondition explicitly.
    """
    wo_id = f"WO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    _log("_create_work_order",
         {"action_type": action.type, "asset_id": asset_id, "case_id": case_id}, wo_id)
    return wo_id


def create_work_order_for_state(
    state: "AgentStateLike", action: RecommendationAction
) -> str:
    """State-aware WO creator: refuses if no approve/modify decision exists.

    Implements the spec §3 tool guardrail explicitly (defense in depth with
    the ``acknowledge_work_order`` state precondition).
    """
    hd = getattr(state, "human_decision", None)
    if hd is None or hd.decision == HumanDecision.REJECT:
        raise ValueError(
            "work order refused: no approve/modify human_decision recorded for "
            f"case {getattr(state, 'case_id', '?')}"
        )
    wo_id = _create_work_order(action, state.asset_id, getattr(state, "case_id", "") or "")
    state.acknowledge_work_order(wo_id, actor="cmms")
    return wo_id


def record_outcome_for_state(state: "AgentStateLike", outcome: Outcome) -> None:
    """Record a maintenance outcome against the state machine."""
    state.record_outcome(outcome)


def build_fault_signature(observation_type: str, top_cause_id: str | None, kb_refs: list[str] | None) -> str:
    """Deterministic, asset-agnostic fault signature for KB retrieval.

    Built from the observation type, resolved cause and grounding kb_refs —
    the SAME way at diagnosis time (``app._fault_signature``) and at
    feedback time (``submit_feedback``), so a case validated through
    feedback actually matches the next identical fault's query signature
    (Phase 3: confidence the KB can move). A signature built one way and
    queried another never matches, which silently caps ``kb_match`` no
    matter how much validated feedback is approved.
    """
    parts = [observation_type.replace("_", " "), (top_cause_id or "").replace("_", " ")]
    parts.extend(r.replace(":", " ").replace("_", " ") for r in (kb_refs or []))
    return " ".join(parts)


def submit_feedback(case_id: str, corrections: dict,
                    *, state=None) -> str:
    """Submit feedback and promote it into the KB via the learning loop.

    If ``state`` (an ``AgentState``) is supplied, the feedback is promoted to a
    ``ValidatedCase`` in ``LearningStore`` so future diagnoses of similar
    fault signatures retrieve it (raising ``kb_match`` and confidence).

    Governance gate (spec §7 / brief constraint #4): only *validated* cases —
    those with a recorded maintenance outcome — may feed the KB. Passing a
    ``state`` that has no outcome raises ``ValueError`` so unverified feedback
    cannot silently corrupt the knowledge base.
    ``corrections`` may carry: ``confirmed_cause``, ``fault_signature``,
    ``asset_type``, ``action_taken``, ``outcome``, ``notes``.
    """
    from .learning import STORE as _LSTORE
    from .models import FeedbackRecord

    fb_id = f"FB-{uuid.uuid4().hex[:8].upper()}"
    proposed_cause = None
    asset_id = ""
    asset_type = "CRAH"
    confidence = 0.8
    action_taken = ""
    derived_signature = ""
    if state is not None:
        asset_id = getattr(state, "asset_id", "") or ""
        asset_type = ASSETS.get(asset_id, {}).get("type") or asset_type
        if getattr(state, "diagnosis", None) is not None:
            proposed_cause = state.diagnosis.top_cause_id or None
            derived_signature = build_fault_signature(
                state.observation.type, state.diagnosis.top_cause_id, state.diagnosis.kb_refs,
            )
        confidence = float(getattr(state, "confidence", 0.8) or 0.8)
        rec = getattr(state, "recommendation", None)
        if rec is not None and rec.actions:
            action_taken = rec.actions[0].type or ""
        # Governance gate: require a validated outcome before the feedback can
        # enter the KB (brief: "validated outcomes can inform future knowledge").
        if getattr(state, "outcome", None) is None:
            raise ValueError(
                f"feedback refused: case {case_id} has no validated outcome; "
                "record_outcome must be called before submit_feedback"
            )
    from .cause_registry import canonicalize_cause_id
    from .decision_tree import KNOWN_CAUSE_IDS

    confirmed_cause = canonicalize_cause_id(
        corrections.get("confirmed_cause") or proposed_cause or ""
    )
    if confirmed_cause not in KNOWN_CAUSE_IDS:
        raise ValueError(f"feedback refused: unknown confirmed_cause {confirmed_cause!r}")
    # A registered asset's type always comes from the registry; a caller
    # cannot file feedback under another pill.
    if asset_id not in ASSETS:
        asset_type = corrections.get("asset_type", asset_type)
    # The caller may override the signature explicitly; otherwise use the
    # one actually diagnosed, so the validated case this produces matches
    # the next identical fault's query signature.
    corrections.setdefault("fault_signature", derived_signature)
    fb = FeedbackRecord(
        feedback_id=fb_id,
        case_id=case_id,
        asset_id=asset_id,
        asset_type=asset_type,
        proposed_cause=proposed_cause,
        confirmed_cause=confirmed_cause,
        corrections=corrections,
        submitted_by=corrections.get("submitted_by", "steward1"),
        submitted_at=datetime.now(),
    )
    proposal = _LSTORE.record_feedback(fb, confidence=confidence, action_taken=action_taken)
    _log("submit_feedback",
         {"case_id": case_id, "corrections": corrections},
         {"feedback_id": fb_id, "proposal_id": proposal["proposal_id"],
          "status": proposal["status"]})
    return fb_id