"""Executable causal decision tree for the "temperature measurement missing"
fault on a CRAH unit (spec §4.2).

The tree walks the Q1-Q7 heuristic encoded in the spec and turns retrieved
evidence into one or more ``DecisionResult`` candidate causes. It is
deterministic and LLM-independent: given the same observation + evidence it
always returns the same candidates, so it is auditable and unit-testable.

【ASSUMPTION】 Every cause, branch predicate, and threshold below is an
illustrative expert heuristic. Per spec §4.2 and Appendix A #5 these MUST be
validated with Keppel technical-services SMEs before deployment. They are
written as plain, configurable Python (not prompt text) so they can be
versioned, reviewed, and rolled back via the governance pipeline (§7).

Evidence payload contracts (【ASSUMPTION】, keyed by ``source``/``type``):
  - ("bms", "status")    -> query_bms_status():
       {
         "bus_alive": bool,               # whole bus reporting?
         "other_tags_reporting": bool,    # peer tags on same bus alive?
         "controller_reachable": bool,
         "gateway_healthy": bool,         # gateway/SCADA path (Q6)
         "scada_link_healthy": bool,
       }
  - ("config", "log")    -> get_config_change_log():
       {
         "recent_change": bool,
         "changes": [ {"type": "tag_renamed"|"tag_removed"|..., "tag": str} ],
       }
  - ("history", "log")   -> get_maintenance_history():
       { "recent_disturbance": bool, "last_service_date": "..." }
  - ("sensor", "metadata") -> get_sensor_metadata():
       {
         "past_eol": bool,
         "calibration_overdue": bool,
         "last_calibrated_at": "...",
         "calibration_interval_days": int,
         "tag": str,
       }
  - ("sensor", "reading") -> get_sensor_readings():
       {
         "deviation_pattern": "gradual"|"spike"|None,   # Q7 pattern signal
         "sudden_jump": bool,
         "gradual_drift": bool,
         "values": [float, ...],
       }

All ``payload`` accesses use ``.get()`` defensively; missing evidence simply
makes a branch unresolvable and the tree falls through to the next question
(or returns an empty list at the leaves).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# Candidate cause IDs (spec §4.2): one source of truth in cause_registry.
from .cause_registry import (
    CAUSE_BATTERY_EOL,
    CAUSE_BEARING_WEAR,
    CAUSE_CAVITATION,
    CAUSE_CHARGER_FAILURE,
    CAUSE_CHILLER_ELECTRICAL_FAULT,
    CAUSE_COMM_BUS_FAILURE,
    CAUSE_COMPRESSOR_MOTOR_FAULT,
    CAUSE_CONDENSER_FOULING,
    CAUSE_CONFIG_DRIFT,
    CAUSE_DATA_PATH_DROP,
    CAUSE_FOUNDATION_LOOSENESS,
    CAUSE_GROUND_FAULT,
    CAUSE_IMPELLER_IMBALANCE,
    CAUSE_INTERMITTENT_FAULT,
    CAUSE_INVERTER_FAULT,
    CAUSE_LOOSE_WIRING,
    CAUSE_LOW_REFRIGERANT_CHARGE,
    CAUSE_REFRIGERANT_LEAK,
    CAUSE_SENSOR_DRIFT,
    CAUSE_SENSOR_FAULT_NOISE,
    CAUSE_SENSOR_HARDWARE_FAILURE,
    CAUSE_SHAFT_MISALIGNMENT,
    CAUSE_THERMAL_RUNAWAY_RISK,
)
from .models import EvidenceItem, Observation, ReadingStatus, RecommendationAction

# --- 【ASSUMPTION】 Q7 thresholds -----------------------------------------
# |raw_value| >= this (or a sentinel) is treated as a sudden out-of-range
# spike -> sensor fault / electrical noise. Values just outside the INVALID
# bounds (e.g. 152 C) reached over time are treated as gradual drift.
_SUDDEN_SPIKE_ABS_THRESHOLD = 200.0
_SENTINEL_VALUES = frozenset({-9999.0, 9999.0, -32768.0, 32767.0})

# Canonical KB reference for the decision-tree artifact itself. Individual
# results also merge in kb_refs from the evidence that supported the branch
# (supports the G8 anti-hallucination grounding rule).
_KB_REF_TREE = "kb:technical_services:causal_tree:v1"


class DecisionResult(BaseModel):
    """One candidate cause emitted by the decision tree.

    ``action`` is the draft recommendation action (still gated on human approval); it
    always carries the same ``kb_refs`` as the result so the recommendation
    is grounded (spec §4.4 G8).
    """

    cause_id: str
    cause_label: str
    action: RecommendationAction
    kb_refs: list[str] = Field(default_factory=list)


# --- Evidence lookup helper -----------------------------------------------
def find_evidence(
    evidence: list[EvidenceItem], source: str, type: str
) -> EvidenceItem | None:
    """Return the first evidence item matching ``source`` and ``type``.

    Returns ``None`` when no such item exists. Callers ``.get()`` the payload
    defensively.
    """
    for item in evidence:
        if item.source == source and item.type == type:
            return item
    return None


def _merge_kb_refs(base: str, supporting: list[EvidenceItem]) -> list[str]:
    """Union of a base ref and all kb_refs on the supporting evidence items."""
    refs: list[str] = [base]
    for ev in supporting:
        for ref in ev.kb_refs or []:
            if ref not in refs:
                refs.append(ref)
    return refs


def _make_result(
    cause_id: str,
    cause_label: str,
    action_type: str,
    action_target: str,
    action_detail: str,
    branch_ref: str,
    supporting: list[EvidenceItem] | None = None,
) -> DecisionResult:
    kb_refs = _merge_kb_refs(branch_ref, supporting or [])
    action = RecommendationAction(
        type=action_type,
        target=action_target,
        detail=action_detail,
        kb_refs=list(kb_refs),
    )
    return DecisionResult(
        cause_id=cause_id,
        cause_label=cause_label,
        action=action,
        kb_refs=kb_refs,
    )


# --- Branch terminal constructors -----------------------------------------
def _comm_bus_failure(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_COMM_BUS_FAILURE,
        "Communication bus / controller failure",
        "controller_inspection",
        "bms_controller",
        "Inspect controller + bus; escalate to BMS vendor.",
        f"{_KB_REF_TREE}:Q2",
        supporting,
    )


def _config_drift(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_CONFIG_DRIFT,
        "Configuration drift (tag missing/renamed)",
        "config_remap",
        "bms_tag_mapping",
        "Restore/re-map tag (draft work order).",
        f"{_KB_REF_TREE}:Q3",
        supporting,
    )


def _loose_wiring(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_LOOSE_WIRING,
        "Loose wiring / connection disturbed during service",
        "onsite_inspection",
        "sensor_wiring",
        "Onsite re-seat/inspect wiring.",
        f"{_KB_REF_TREE}:Q4",
        supporting,
    )


def _sensor_hardware_failure(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_SENSOR_HARDWARE_FAILURE,
        "Sensor hardware failure (RTD/thermistor dead)",
        "sensor_replacement",
        "sensor",
        "Replace sensor.",
        f"{_KB_REF_TREE}:Q5",
        supporting,
    )


def _data_path_drop(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_DATA_PATH_DROP,
        "Data-path drop (telemetry transport)",
        "path_restore",
        "gateway_scada_link",
        "Restore gateway/link; cross-coordinate with IT/Ops pill.",
        f"{_KB_REF_TREE}:Q6",
        supporting,
    )


def _intermittent_fault(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_INTERMITTENT_FAULT,
        "Intermittent sensor fault / borderline failure",
        "onsite_diagnostic",
        "sensor",
        "Onsite diagnostic + monitor (lower confidence).",
        f"{_KB_REF_TREE}:Q6",
        supporting,
    )


def _sensor_drift(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_SENSOR_DRIFT,
        "Sensor drift",
        "sensor_recalibration",
        "sensor",
        "Recalibrate sensor.",
        f"{_KB_REF_TREE}:Q7",
        supporting,
    )


def _sensor_fault_noise(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_SENSOR_FAULT_NOISE,
        "Sensor fault or electrical noise",
        "sensor_inspection",
        "sensor",
        "Inspect + replace sensor; request peer-sensor evidence.",
        f"{_KB_REF_TREE}:Q7",
        supporting,
    )


# --- Q7 (INVALID branch) ---------------------------------------------------
def _evaluate_q7(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Q7: drift vs fault/noise for an INVALID reading (spec §4.2).

    Signals (all 【ASSUMPTION】):
      - Sudden spike: sentinel value, |raw| >= 200, or readings payload reports
        ``sudden_jump`` / ``deviation_pattern == "spike"``  -> fault/noise.
      - Gradual drift: readings payload reports ``gradual_drift`` /
        ``deviation_pattern == "gradual"``, and/or calibration overdue -> drift.
      - Ambiguous (no pattern + no calibration info): no candidate returned.
    """
    metadata = find_evidence(evidence, "sensor", "metadata")
    calibration_overdue = False
    if metadata is not None:
        calibration_overdue = bool((metadata.payload or {}).get("calibration_overdue", False))

    readings = find_evidence(evidence, "sensor", "reading")
    sudden_jump = False
    gradual = False
    if readings is not None:
        p = readings.payload or {}
        pattern = p.get("deviation_pattern")
        if pattern == "spike" or p.get("sudden_jump") is True:
            sudden_jump = True
        elif pattern == "gradual" or p.get("gradual_drift") is True:
            gradual = True

    raw = observation.raw_value
    if raw is not None:
        if raw in _SENTINEL_VALUES or abs(raw) >= _SUDDEN_SPIKE_ABS_THRESHOLD:
            sudden_jump = True

    supporting = [ev for ev in (metadata, readings) if ev is not None]

    if sudden_jump:
        return [_sensor_fault_noise(supporting)]
    if gradual or calibration_overdue:
        return [_sensor_drift(supporting)]
    # Invalid reading but neither pattern nor calibration info available:
    # cannot resolve drift vs fault/noise -> no candidate (request evidence).
    return []


# --- CRAH "temperature measurement missing" (Q1-Q7, spec §4.2) -------------
def _eval_crah_temp_missing(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Walk the Q1-Q7 causal tree for CRAH temperature-sensor faults."""
    # Q1: INVALID -> Q7 branch; ABSENT -> Q2.
    if observation.reading_status == ReadingStatus.INVALID:
        return _evaluate_q7(observation, evidence)

    # --- ABSENT branch ---
    bms_status = find_evidence(evidence, "bms", "status")

    # Q2: are other tags on the same bus reporting?
    if bms_status is not None:
        p = bms_status.payload or {}
        bus_alive = p.get("bus_alive", True)
        other_reporting = p.get("other_tags_reporting", True)
        if bus_alive is False or other_reporting is False:
            # Whole bus dead -> communication bus / controller failure (escalate).
            return [_comm_bus_failure([bms_status])]

    # Q3: tag present in config / controller reachable?
    config_log = find_evidence(evidence, "config", "log")
    if config_log is not None:
        p = config_log.payload or {}
        tag_changed = bool(p.get("recent_change", False))
        if not tag_changed:
            for change in p.get("changes", []) or []:
                if isinstance(change, dict) and change.get("type") in (
                    "tag_renamed",
                    "tag_removed",
                ):
                    tag_changed = True
                    break
        if tag_changed:
            return [_config_drift([config_log])]

    # Q4: recent maintenance disturbance?
    maint = find_evidence(evidence, "history", "log")
    if maint is not None:
        p = maint.payload or {}
        if p.get("recent_disturbance") is True:
            return [_loose_wiring([maint])]

    # Q5: sensor past end-of-life / calibration interval?
    metadata = find_evidence(evidence, "sensor", "metadata")
    if metadata is not None:
        p = metadata.payload or {}
        if p.get("past_eol") is True or p.get("calibration_overdue") is True:
            return [_sensor_hardware_failure([metadata])]

    # Q6: gateway/SCADA path healthy?
    if bms_status is not None:
        p = bms_status.payload or {}
        gateway_healthy = p.get("gateway_healthy", True)
        scada_healthy = p.get("scada_link_healthy", True)
        if gateway_healthy is False or scada_healthy is False:
            return [_data_path_drop([bms_status])]
        # Path healthy and no earlier branch matched -> intermittent fault.
        return [_intermittent_fault([bms_status])]

    # No evidence to resolve Q6 (and none of Q2-Q5 triggered): cannot diagnose.
    return []


# --- Chiller "compressor trip" (spec §4.2 — multi-asset) -----------------
# 【ASSUMPTION】 Illustrative expert heuristics for a chiller compressor
# safety trip. MUST be validated with Keppel mechanical SMEs before deploy.
#
# Evidence payload contracts:
#   ("chiller", "status") -> {"low_pressure_switch": bool,  # tripped?
#                             "high_pressure_switch": bool, "motor_overcurrent": bool,
#                             "compressor_running": bool, "oil_level": str}
#   ("chiller", "refrigerant") -> {"charge_pct": float, "leak_detected": bool,
#                                  "superheat": float, "subcooling": float}
#   ("chiller", "condenser") -> {"approach_temp": float, "fans_running": bool,
#                                "fouling_factor": float}
#   ("chiller", "electrical") -> {"starter_ok": bool, "contactor_ok": bool,
#                                 "winding_resistance": float|None}
# (cause ids declared at the top of the module)

_KB_REF_CHILLER = "kb:technical_services:chiller_tree:v1"


def _refrigerant_leak(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_REFRIGERANT_LEAK, "Refrigerant leak (low-pressure safety trip)",
        "leak_inspection_repair", "refrigerant_circuit",
        "Locate + repair leak, pressure-test, recharge.",
        f"{_KB_REF_CHILLER}:Q1", supporting,
    )


def _low_refrigerant_charge(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_LOW_REFRIGERANT_CHARGE, "Low refrigerant charge (chronic undercharge)",
        "refrigerant_topup", "refrigerant_circuit",
        "Top up charge; verify superheat/subcooling.",
        f"{_KB_REF_CHILLER}:Q1", supporting,
    )


def _condenser_fouling(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_CONDENSER_FOULING, "Condenser fouling (high head pressure)",
        "condenser_cleaning", "condenser",
        "Chemical clean condenser tubes/coils.",
        f"{_KB_REF_CHILLER}:Q2", supporting,
    )


def _compressor_motor_fault(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_COMPRESSOR_MOTOR_FAULT, "Compressor motor fault (overcurrent / winding)",
        "compressor_overhaul", "compressor_motor",
        "Megger test + motor rewind/replacement (high cost).",
        f"{_KB_REF_CHILLER}:Q3", supporting,
    )


def _chiller_electrical_fault(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_CHILLER_ELECTRICAL_FAULT, "Starter / contactor electrical fault",
        "starter_replacement", "compressor_starter",
        "Inspect + replace starter/contactor.",
        f"{_KB_REF_CHILLER}:Q4", supporting,
    )


def _eval_chiller_compressor_trip(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Walk the chiller compressor-trip causal tree.

    Q1 low-pressure switch tripped? (leak vs undercharge)
    Q2 high-pressure / high approach? (condenser fouling)
    Q3 motor overcurrent / winding? (motor fault)
    Q4 starter / contactor? (electrical fault)
    """
    status = find_evidence(evidence, "chiller", "status")
    refr = find_evidence(evidence, "chiller", "refrigerant")
    cond = find_evidence(evidence, "chiller", "condenser")
    elec = find_evidence(evidence, "chiller", "electrical")

    # Q1: low-pressure safety switch tripped?
    if status is not None and refr is not None:
        sp = status.payload or {}
        rp = refr.payload or {}
        if sp.get("low_pressure_switch") is True:
            if rp.get("leak_detected") is True:
                return [_refrigerant_leak([status, refr])]
            if (rp.get("charge_pct") or 100) < 70:
                return [_low_refrigerant_charge([status, refr])]

    # Q2: high head pressure / condenser fouling?
    if cond is not None:
        cp = cond.payload or {}
        fans_ok = cp.get("fans_running", True)
        high_head = (status.payload or {}).get("high_pressure_switch") is True
        high_approach = (cp.get("approach_temp") or 0) >= 3.0
        if (high_head or high_approach) and fans_ok:
            return [_condenser_fouling([cond])]

    # Q3: motor overcurrent / winding fault?
    if status is not None or elec is not None:
        sp = (status.payload or {}) if status is not None else {}
        ep = (elec.payload or {}) if elec is not None else {}
        overcurrent = sp.get("motor_overcurrent") is True
        wr = ep.get("winding_resistance")
        winding_bad = wr is not None and wr < 0.5
        if overcurrent or winding_bad:
            supporting = [ev for ev in (status, elec) if ev is not None]
            return [_compressor_motor_fault(supporting)]

    # Q4: starter / contactor fault?
    if elec is not None:
        ep = elec.payload or {}
        if ep.get("starter_ok") is False or ep.get("contactor_ok") is False:
            return [_chiller_electrical_fault([elec])]

    # Insufficient evidence to resolve.
    return []


# --- UPS "battery fault" (spec §4.2 — multi-asset) ------------------------
# 【ASSUMPTION】 Illustrative heuristics for a UPS battery alarm. Validate
# with Keppel electrical SMEs before deploy.
#
# Evidence payload contracts:
#   ("ups", "status")  -> {"battery_voltage": float, "load_pct": float,
#                          "on_battery": bool, "alarms": [str]}
#   ("ups", "battery") -> {"soh_pct": float, "age_months": int,
#                          "float_voltage": float, "balance_ok": bool}
#   ("ups", "charger") -> {"charge_current": float, "charger_ok": bool}
#   ("ups", "thermal")  -> {"battery_temp_c": float, "temp_rising": bool}
# (cause ids declared at the top of the module)

_KB_REF_UPS = "kb:technical_services:ups_tree:v1"
_UPS_THERMAL_ESCALATE_C = 45  # 【ASSUMPTION】 cell temp threshold for runaway risk
_UPS_SOH_FLOOR = 60  # 【ASSUMPTION】 state-of-health % below which = EoL
_UPS_AGE_MONTHS_EOL = 60  # 【ASSUMPTION】 5-year design life


def _thermal_runaway_risk(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_THERMAL_RUNAWAY_RISK, "Thermal runaway risk (cell temp high + rising)",
        "thermal_shutdown_inspect", "battery_bank",
        "Reduce float voltage, force-ventilate, isolate bank; safety-critical, do not attempt alone.",
        f"{_KB_REF_UPS}:Q1", supporting,
    )


def _battery_eol(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_BATTERY_EOL, "Battery end-of-life (low SoH / past design life)",
        "battery_replacement", "battery_bank",
        "Replace battery bank; impedance-test cells.",
        f"{_KB_REF_UPS}:Q2", supporting,
    )


def _charger_failure(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_CHARGER_FAILURE, "Charger module failure (no charge current)",
        "charger_repair", "ups_charger",
        "Inspect/repair charger rectifier module.",
        f"{_KB_REF_UPS}:Q3", supporting,
    )


def _ground_fault(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_GROUND_FAULT, "Ground fault / insulation breakdown",
        "ground_fault_locate", "battery_bank",
        "Isolate + megger test battery rack to ground.",
        f"{_KB_REF_UPS}:Q4", supporting,
    )


def _inverter_fault(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_INVERTER_FAULT, "Inverter section fault",
        "inverter_repair", "ups_inverter",
        "Diagnose inverter IGBT/driver board.",
        f"{_KB_REF_UPS}:Q5", supporting,
    )


def _eval_ups_battery_fault(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Walk the UPS battery-fault causal tree.

    Safety-first ordering: thermal runaway risk is checked FIRST (escalate).
    Q1 thermal runaway risk? (temp high + rising)
    Q2 battery end-of-life? (low SoH / past design life)
    Q3 charger failure? (no charge current)
    Q4 ground fault? (insulation breakdown)
    Q5 inverter fault?
    """
    status = find_evidence(evidence, "ups", "status")
    battery = find_evidence(evidence, "ups", "battery")
    charger = find_evidence(evidence, "ups", "charger")
    thermal = find_evidence(evidence, "ups", "thermal")

    # Q1: thermal runaway risk — HIGHEST priority (safety).
    if thermal is not None:
        tp = thermal.payload or {}
        temp = tp.get("battery_temp_c") or 0
        if tp.get("temp_rising") is True and temp >= _UPS_THERMAL_ESCALATE_C:
            return [_thermal_runaway_risk([thermal])]

    # Q2: battery end-of-life.
    if battery is not None:
        bp = battery.payload or {}
        soh = bp.get("soh_pct") or 100
        age = bp.get("age_months") or 0
        if soh < _UPS_SOH_FLOOR or age >= _UPS_AGE_MONTHS_EOL:
            return [_battery_eol([battery])]

    # Q3: charger failure.
    if charger is not None:
        cp = charger.payload or {}
        if cp.get("charger_ok") is False or (cp.get("charge_current") or 0) <= 0:
            return [_charger_failure([charger])]

    # Q4: ground fault.
    if status is not None:
        sp = status.payload or {}
        alarms = [str(a).lower() for a in (sp.get("alarms") or [])]
        if "ground_fault" in alarms:
            return [_ground_fault([status])]

    # Q5: inverter fault.
    if status is not None:
        sp = status.payload or {}
        alarms = [str(a).lower() for a in (sp.get("alarms") or [])]
        if "inverter_fault" in alarms:
            return [_inverter_fault([status])]

    # Insufficient evidence to resolve.
    return []


# --- Pump "vibration high" (spec §4.2 — multi-asset) ----------------------
# 【ASSUMPTION】 Illustrative heuristics based on vibration-spectrum analysis.
# Validate with Keppel rotating-equipment SMEs before deploy.
#
# Evidence payload contracts:
#   ("pump", "status")    -> {"running": bool, "rpm": int, "flow_pct": float,
#                             "npsh_margin": float}
#   ("pump", "vibration") -> {"dominant_order": "1x"|"2x"|"broadband"|"subharmonic",
#                             "axial_mm_s": float, "bearing_freq_present": bool}
#   ("pump", "bearing")   -> {"temp_c": float, "greasing_overdue": bool}
#   ("pump", "base")      -> {"soft_foot_detected": bool, "directional_dominant": bool}
# (cause ids declared at the top of the module)

_KB_REF_PUMP = "kb:technical_services:pump_tree:v1"
_PUMP_AXIAL_HIGH_MM_S = 4.5  # 【ASSUMPTION】 axial vibration threshold for misalignment
_PUMP_NPSH_LOW = 0.3  # 【ASSUMPTION】 NPSH margin below this -> cavitation risk
_PUMP_BEARING_TEMP_HIGH_C = 75  # 【ASSUMPTION】 bearing temp threshold


def _cavitation(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_CAVITATION, "Cavitation (low NPSH / flow instability)",
        "npsh_review_throttle", "suction_sump",
        "Increase suction head / throttle discharge; inspect impeller pitting.",
        f"{_KB_REF_PUMP}:Q1", supporting,
    )


def _shaft_misalignment(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_SHAFT_MISALIGNMENT, "Shaft misalignment (2x + high axial)",
        "laser_realign", "coupling",
        "Laser-align pump-to-motor coupling.",
        f"{_KB_REF_PUMP}:Q2", supporting,
    )


def _foundation_looseness(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_FOUNDATION_LOOSENESS, "Foundation looseness / soft foot",
        "grouting_retorque", "pump_base",
        "Retorque hold-down bolts, fix soft foot, regrout base.",
        f"{_KB_REF_PUMP}:Q3", supporting,
    )


def _bearing_wear(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_BEARING_WEAR, "Bearing wear (defect freq / high temp)",
        "bearing_replacement", "pump_bearings",
        "Replace bearings; analyse oil sample.",
        f"{_KB_REF_PUMP}:Q4", supporting,
    )


def _impeller_imbalance(supporting: list[EvidenceItem]) -> DecisionResult:
    return _make_result(
        CAUSE_IMPELLER_IMBALANCE, "Impeller imbalance (1x dominant)",
        "impeller_balance_clean", "impeller",
        "Clean/balance impeller; inspect for erosion.",
        f"{_KB_REF_PUMP}:Q5", supporting,
    )


def _eval_pump_vibration_high(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Walk the pump high-vibration causal tree (spectrum-driven).

    Q1 cavitation? (broadband + low NPSH margin)
    Q2 shaft misalignment? (2x + high axial)
    Q3 foundation looseness? (subharmonic / soft foot / directional)
    Q4 bearing wear? (defect freq / high temp / greasing overdue)
    Q5 impeller imbalance? (1x dominant, no other symptoms)
    """
    status = find_evidence(evidence, "pump", "status")
    vib = find_evidence(evidence, "pump", "vibration")
    bearing = find_evidence(evidence, "pump", "bearing")
    base = find_evidence(evidence, "pump", "base")

    dominant = (vib.payload or {}).get("dominant_order") if vib is not None else None

    # Q1: cavitation — broadband vibration + insufficient NPSH margin.
    if vib is not None and status is not None:
        npsh = (status.payload or {}).get("npsh_margin", 1.0)
        if dominant == "broadband" and npsh < _PUMP_NPSH_LOW:
            return [_cavitation([vib, status])]

    # Q2: shaft misalignment — 2x dominant + high axial.
    if vib is not None:
        vp = vib.payload or {}
        if dominant == "2x" and (vp.get("axial_mm_s") or 0) >= _PUMP_AXIAL_HIGH_MM_S:
            return [_shaft_misalignment([vib])]

    # Q3: foundation looseness — subharmonic / soft foot / directional.
    if (dominant == "subharmonic") or (base is not None and (
        (base.payload or {}).get("soft_foot_detected") is True
        or (base.payload or {}).get("directional_dominant") is True
    )):
        supporting = [ev for ev in (vib, base) if ev is not None]
        return [_foundation_looseness(supporting)]

    # Q4: bearing wear — defect frequencies / high temp / greasing overdue.
    if vib is not None or bearing is not None:
        vp = (vib.payload or {}) if vib is not None else {}
        bp = (bearing.payload or {}) if bearing is not None else {}
        if (vp.get("bearing_freq_present") is True
                or (bp.get("temp_c") or 0) >= _PUMP_BEARING_TEMP_HIGH_C
                or bp.get("greasing_overdue") is True):
            supporting = [ev for ev in (vib, bearing) if ev is not None]
            return [_bearing_wear(supporting)]

    # Q5: impeller imbalance — 1x dominant with no other symptoms.
    if dominant == "1x":
        return [_impeller_imbalance([vib])]

    # Insufficient evidence to resolve.
    return []


# --- Fault-type registry (spec §4.2 — multi-asset generalization) ----------
# Each fault type maps to a dedicated evaluator. Unknown types yield [] so the
# agent escalates (spec §2). Adding a new asset/fault class = add a function +
# register it here; no changes to the caller (app.py / demo.py).
_FAULT_EVALUATORS: dict[str, object] = {
    "temperature_measurement_missing": _eval_crah_temp_missing,
    "chiller_compressor_trip": _eval_chiller_compressor_trip,
    "ups_battery_fault": _eval_ups_battery_fault,
    "pump_vibration_high": _eval_pump_vibration_high,
}


# --- Main entry point ------------------------------------------------------
# Known fault types — public registry mirroring ``_FAULT_EVALUATORS``.
# Consumed by app.py ``create_case`` to validate the observation type up front
# (400 on unknown) instead of silently building an observation the tree cannot
# route. Adding a new asset/fault class = add a function + register it here.
KNOWN_FAULT_TYPES: tuple[str, ...] = tuple(_FAULT_EVALUATORS.keys())

# Expected number of resolvable branches per fault tree (spec §4.3 coverage
# denominator). CRAH Q1-Q7 ≈ 6 resolvable questions; the chiller tree Q1-Q4,
# UPS Q1-Q5, pump Q1-Q5. Used by the confidence scorer so a 4-evidence chiller
# case is not penalised against a CRAH-6 denominator. 【ASSUMPTION】 tunable.
FAULT_BRANCH_COUNTS: dict[str, int] = {
    "temperature_measurement_missing": 6,
    "chiller_compressor_trip": 4,
    "ups_battery_fault": 5,
    "pump_vibration_high": 5,
}

# All candidate cause ids the decision trees can emit across every asset/fault
# tree (spec §4.2). Consumed by app.py post_outcome to validate that an
# ``Outcome.root_cause_confirmed`` actually corresponds to a cause the system
# can diagnose — keeping free-text typos out of the knowledge base. The
# ``unresolvable`` sentinel is allowed (emitted by /advance when the tree
# returns no candidate). 【ASSUMPTION】 extend the set when a new tree is added.
KNOWN_CAUSE_IDS: frozenset[str] = frozenset({
    CAUSE_COMM_BUS_FAILURE, CAUSE_CONFIG_DRIFT, CAUSE_LOOSE_WIRING,
    CAUSE_SENSOR_HARDWARE_FAILURE, CAUSE_DATA_PATH_DROP,
    CAUSE_INTERMITTENT_FAULT, CAUSE_SENSOR_DRIFT, CAUSE_SENSOR_FAULT_NOISE,
    CAUSE_REFRIGERANT_LEAK, CAUSE_LOW_REFRIGERANT_CHARGE, CAUSE_CONDENSER_FOULING,
    CAUSE_COMPRESSOR_MOTOR_FAULT, CAUSE_CHILLER_ELECTRICAL_FAULT,
    CAUSE_THERMAL_RUNAWAY_RISK, CAUSE_BATTERY_EOL, CAUSE_CHARGER_FAILURE,
    CAUSE_GROUND_FAULT, CAUSE_INVERTER_FAULT,
    CAUSE_CAVITATION, CAUSE_SHAFT_MISALIGNMENT, CAUSE_FOUNDATION_LOOSENESS,
    CAUSE_BEARING_WEAR, CAUSE_IMPELLER_IMBALANCE,
    "unresolvable",
})


def evaluate_decision_tree(
    observation: Observation, evidence: list[EvidenceItem]
) -> list[DecisionResult]:
    """Dispatch to the asset/fault-specific causal tree and return candidates.

    Routes by ``observation.type`` to the matching evaluator. Each evaluator is
    deterministic and LLM-independent. Returns an empty list when the fault
    type is unknown or the retrieved evidence is insufficient to resolve any
    terminal branch (the agent should then gather more evidence or escalate,
    per spec §2 transition rules).
    """
    evaluator = _FAULT_EVALUATORS.get(observation.type)
    if evaluator is None:
        return []
    return evaluator(observation, evidence)