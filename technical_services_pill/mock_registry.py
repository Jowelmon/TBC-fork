"""In-memory demo registry for the Technical Services Fault Diagnosis pill.

All data here is hackathon demo data (spec §0 ``【ASSUMPTION】`` domain
specifics). It models the CRAH "temperature measurement missing" scenario:

* ``CRAH-DC1-01`` — supply-air RTD ``SA-TEMP-01`` is PAST its calibration
  interval and its reading is absent, while return-air peer ``RA-TEMP-01`` is
  healthy. BMS bus/controller reachable. No recent tag-remapping config change.
  => happy-path diagnosis: ``sensor_hardware_failure`` (spec TC1).

* ``CRAH-DC1-02`` — the entire Modbus bus/controller is unreachable, so ALL
  tags (``SA-TEMP-02`` + ``RA-TEMP-02``) are dead.
  => escalation scenario: ``communication_bus_controller_failure`` (spec TC2).

No external I/O, no network — fully deterministic. ``get_registry()`` returns
the whole structure so tools can read it.
"""
from __future__ import annotations

from datetime import date


# --- Assets (spec §6 Asset) -----------------------------------------------
ASSETS: dict[str, dict] = {
    "CRAH-DC1-01": {
        "id": "CRAH-DC1-01",
        "type": "CRAH",
        "site_id": "DC-SINGAPORE-1",
        "location": "Data Hall A / Row 3",
        "criticality": "high",
        "parent_system_id": "CHW-LOOP-A",
        "commissioned_at": "2021-06-01",
        "specs": {
            "cooling_capacity_kw": 50,
            "fan_type": "EC_plug",
            "coil_type": "chilled_water",
            "design_supply_temp_c": 18.0,
            "design_return_temp_c": 25.0,
        },
    },
    "CRAH-DC1-02": {
        "id": "CRAH-DC1-02",
        "type": "CRAH",
        "site_id": "DC-SINGAPORE-1",
        "location": "Data Hall A / Row 4",
        "criticality": "high",
        "parent_system_id": "CHW-LOOP-A",
        "commissioned_at": "2022-03-15",
        "specs": {
            "cooling_capacity_kw": 50,
            "fan_type": "EC_plug",
            "coil_type": "chilled_water",
            "design_supply_temp_c": 18.0,
            "design_return_temp_c": 25.0,
        },
    },
    # --- Chiller (spec §4.2 multi-asset) ----------------------------------
    "CHILLER-DC1-01": {
        "id": "CHILLER-DC1-01",
        "type": "Chiller",
        "site_id": "DC-SINGAPORE-1",
        "location": "Plant Room A",
        "criticality": "high",
        "parent_system_id": "CHW-LOOP-A",
        "commissioned_at": "2020-01-15",
        "specs": {
            "cooling_capacity_kw": 800,
            "compressor_type": "centrifugal",
            "refrigerant": "R134a",
        },
    },
    # --- UPS (spec §4.2 multi-asset) -------------------------------------
    "UPS-DC1-01": {
        "id": "UPS-DC1-01",
        "type": "UPS",
        "site_id": "DC-SINGAPORE-1",
        "location": "Electrical Room 1",
        "criticality": "high",
        "parent_system_id": "POWER-BUS-A",
        "commissioned_at": "2021-03-01",
        "specs": {
            "rating_kva": 250,
            "battery_type": "VRLA",
            "cell_count": 120,
        },
    },
    # --- Pump (spec §4.2 multi-asset) -------------------------------------
    "PUMP-DC1-01": {
        "id": "PUMP-DC1-01",
        "type": "Pump",
        "site_id": "DC-SINGAPORE-1",
        "location": "Plant Room B",
        "criticality": "medium",
        "parent_system_id": "CHW-LOOP-B",
        "commissioned_at": "2022-06-20",
        "specs": {
            "flow_rate_m3h": 120,
            "head_m": 35,
            "rpm": 2950,
        },
    },
}

# --- Sensors (spec §6 Sensor) ---------------------------------------------
SENSORS: dict[str, dict] = {
    # CRAH-DC1-01: supply-air sensor past calibration interval (the fault).
    "SA-TEMP-01": {
        "id": "SA-TEMP-01",
        "asset_id": "CRAH-DC1-01",
        "type": "RTD",
        "unit": "°C",
        "location": "supply_air",
        "bus_id": "MDBUS-01",
        "controller_id": "CTL-01",
        "tag": "AI1",
        "last_calibrated_at": "2024-01-15",
        "calibration_interval_days": 365,
    },
    "RA-TEMP-01": {
        "id": "RA-TEMP-01",
        "asset_id": "CRAH-DC1-01",
        "type": "RTD",
        "unit": "°C",
        "location": "return_air",
        "bus_id": "MDBUS-01",
        "controller_id": "CTL-01",
        "tag": "AI2",
        "last_calibrated_at": "2026-06-10",
        "calibration_interval_days": 365,
    },
    # CRAH-DC1-02: all tags on this bus are dead (bus-failure scenario).
    "SA-TEMP-02": {
        "id": "SA-TEMP-02",
        "asset_id": "CRAH-DC1-02",
        "type": "RTD",
        "unit": "°C",
        "location": "supply_air",
        "bus_id": "MDBUS-02",
        "controller_id": "CTL-02",
        "tag": "AI1",
        "last_calibrated_at": "2026-01-10",
        "calibration_interval_days": 365,
    },
    "RA-TEMP-02": {
        "id": "RA-TEMP-02",
        "asset_id": "CRAH-DC1-02",
        "type": "RTD",
        "unit": "°C",
        "location": "return_air",
        "bus_id": "MDBUS-02",
        "controller_id": "CTL-02",
        "tag": "AI2",
        "last_calibrated_at": "2026-01-10",
        "calibration_interval_days": 365,
    },
}

# --- Live telemetry snapshot (supports get_sensor_readings) ---------------
# status: "ok" | "absent" | "invalid" (spec §4.2 Q1)
LIVE_READINGS: dict[str, dict] = {
    "SA-TEMP-01": {
        "sensor_id": "SA-TEMP-01",
        "value": None,
        "status": "absent",
        "ts": "2026-09-29T08:00:00+08:00",
        "last_good_value": 18.2,
        "last_good_ts": "2026-09-28T23:54:00+08:00",
    },
    "RA-TEMP-01": {
        "sensor_id": "RA-TEMP-01",
        "value": 24.1,
        "status": "ok",
        "ts": "2026-09-29T08:00:00+08:00",
        "last_good_value": 24.1,
        "last_good_ts": "2026-09-29T08:00:00+08:00",
    },
    # CRAH-DC1-02: bus dead → all readings absent.
    "SA-TEMP-02": {
        "sensor_id": "SA-TEMP-02",
        "value": None,
        "status": "absent",
        "ts": "2026-09-29T08:00:00+08:00",
        "last_good_value": 17.9,
        "last_good_ts": "2026-09-29T05:12:00+08:00",
    },
    "RA-TEMP-02": {
        "sensor_id": "RA-TEMP-02",
        "value": None,
        "status": "absent",
        "ts": "2026-09-29T08:00:00+08:00",
        "last_good_value": 23.8,
        "last_good_ts": "2026-09-29T05:12:00+08:00",
    },
}

# --- BMS / bus / controller status (supports query_bms_status) ---------
BMS_STATUS: dict[str, dict] = {
    "CRAH-DC1-01": {
        "asset_id": "CRAH-DC1-01",
        "controller_id": "CTL-01",
        "controller_reachable": True,
        "bus_id": "MDBUS-01",
        "bus_reachable": True,
        "protocol": "Modbus-RTU",
        "heartbeat": "ok",
        "tags_alive": ["RA-TEMP-01"],
        "tags_dead": ["SA-TEMP-01"],
        "scada_link": "ok",
        "gateway_heartbeat": "ok",
    },
    "CRAH-DC1-02": {
        "asset_id": "CRAH-DC1-02",
        "controller_id": "CTL-02",
        "controller_reachable": False,
        "bus_id": "MDBUS-02",
        "bus_reachable": False,
        "protocol": "Modbus-RTU",
        "heartbeat": "lost",
        "tags_alive": [],
        "tags_dead": ["SA-TEMP-02", "RA-TEMP-02"],
        "scada_link": "degraded",
        "gateway_heartbeat": "ok",
    },
}

# --- Maintenance history (spec §3 get_maintenance_history) ---------------
MAINTENANCE_HISTORY: dict[str, list[dict]] = {
    "CRAH-DC1-01": [
        {
            "wo_id": "WO-2025-118",
            "date": "2025-12-04",
            "type": "routine_inspection",
            "summary": "Quarterly inspection; filters cleaned; no sensor or "
                       "wiring disturbance",
            "technician": "T. Lim",
            "status": "done",
        },
        {
            "wo_id": "WO-2024-077",
            "date": "2024-08-21",
            "type": "filter_replacement",
            "summary": "Filter swap only.",
            "technician": "R. Goh",
            "status": "done",
        },
    ],
    "CRAH-DC1-02": [
        {
            "wo_id": "WO-2026-009",
            "date": "2026-02-11",
            "type": "controller_firmware_update",
            "summary": "BMS controller CTL-02 firmware patch applied; bus "
                       "re-initialized afterwards.",
            "technician": "T. Lim",
            "status": "done",
        },
    ],
}

# --- Config change log (spec §3 get_config_change_log) -------------------
CONFIG_CHANGE_LOG: dict[str, list[dict]] = {
    "CRAH-DC1-01": [
        {
            "change_id": "CC-2026-21",
            "at": "2026-09-12T14:22:00+08:00",
            "by": "BMS-Admin",
            "change": "fan_speed_setpoint_adjustment",
            "affected_tags": [],
            "note": "Setpoint tweak; no tag re-mapping.",
        },
    ],
    "CRAH-DC1-02": [],
}

# --- Multi-asset telemetry (spec §4.2 — chiller / UPS / pump) -------------
# Per-asset evidence payloads, keyed by asset_id. Each value is a list of
# (source, type, payload, kb_refs) tuples the generalised gatherer turns into
# EvidenceItem objects. Each asset is wired to a distinct, realistic fault
# signature so the demo exercises a different terminal branch per asset type.
TELEMETRY: dict[str, list[tuple]] = {
    # Chiller: low-pressure switch tripped + leak detected -> refrigerant_leak
    "CHILLER-DC1-01": [
        ("chiller", "status", {
            "compressor_running": False, "low_pressure_switch": True,
            "high_pressure_switch": False, "motor_overcurrent": False,
            "oil_level": "normal",
        }, ["KB-CH1"]),
        ("chiller", "refrigerant", {
            "charge_pct": 42, "leak_detected": True,
            "superheat": 11.0, "subcooling": 3.0,
        }, ["KB-CH1"]),
        ("chiller", "condenser", {
            "approach_temp": 1.5, "fans_running": True, "fouling_factor": 0.2,
        }, []),
        ("chiller", "electrical", {
            "starter_ok": True, "contactor_ok": True, "winding_resistance": 2.4,
        }, []),
    ],
    # UPS: low SoH + aged bank -> battery_eol
    "UPS-DC1-01": [
        ("ups", "battery", {
            "soh_pct": 48, "age_months": 64, "float_voltage": 432.0,
            "balance_ok": False,
        }, ["KB-UPS1"]),
        ("ups", "status", {
            "battery_voltage": 410.0, "load_pct": 35, "on_battery": False,
            "alarms": ["battery_low"],
        }, []),
        ("ups", "charger", {
            "charge_current": 8.0, "charger_ok": True,
        }, []),
        ("ups", "thermal", {
            "battery_temp_c": 28.0, "temp_rising": False,
        }, []),
    ],
    # Pump: 2x dominant + high axial -> shaft_misalignment
    "PUMP-DC1-01": [
        ("pump", "vibration", {
            "dominant_order": "2x", "axial_mm_s": 6.1,
            "bearing_freq_present": False,
        }, ["KB-PMP1"]),
        ("pump", "status", {
            "running": True, "rpm": 2950, "flow_pct": 88, "npsh_margin": 0.8,
        }, []),
        ("pump", "bearing", {
            "temp_c": 62.0, "greasing_overdue": False,
        }, []),
        ("pump", "base", {
            "soft_foot_detected": False, "directional_dominant": False,
        }, []),
    ],
}

# --- Knowledge base (spec §2 Knowledge Layer; versioned artifacts) -------
# heuristics / causal_models carry ``kb_ref`` ids used to ground recommendations
# (guardrail G8: a recommendation must cite kb_refs + evidence_refs).
KNOWLEDGE_BASE: dict[str, list[dict]] = {
    "heuristics": [
        {
            "id": "KB-H1",
            "rule": "single_sensor_absent_peer_ok",
            "description": "If one sensor reading is absent while peer sensors "
                           "on the same bus/controller report normally, suspect "
                           "the sensor or its wiring — not the bus.",
            "applies_to": ["CRAH", "CRAC", "AHU"],
        },
        {
            "id": "KB-H2",
            "rule": "all_tags_on_bus_dead",
            "description": "If all tags on a BMS bus/controller are dead, "
                           "suspect the controller or bus, not individual sensors.",
            "applies_to": ["CRAH", "CRAC", "AHU"],
        },
        {
            "id": "KB-H3",
            "rule": "past_calibration_interval_absent",
            "description": "A sensor past its calibration interval whose reading "
                           "goes absent likely suffered hardware failure "
                           "(RTD/thermistor dead). Replace sensor.",
            "applies_to": ["RTD", "thermistor"],
        },
        {
            "id": "KB-H4",
            "rule": "recent_tag_remap_config_drift",
            "description": "A recent config_change_log entry renaming/removing "
                           "a tag correlates with configuration drift.",
            "applies_to": ["CRAH", "CRAC", "AHU"],
        },
        {
            "id": "KB-H5",
            "rule": "recent_physical_disturbance_loose_wiring",
            "description": "Recent maintenance that physically disturbed a sensor "
                           "correlates with loose wiring / connection disturbance.",
            "applies_to": ["RTD", "thermistor"],
        },
    ],
    "causal_models": [
        {
            "id": "KB-CM1",
            "cause": "sensor_hardware_failure",
            "decision_tree_node": "Q5",
            "description": "Sensor past end-of-life / calibration interval, "
                           "reading absent, peers healthy.",
            "action_hint": "replace_sensor",
        },
        {
            "id": "KB-CM2",
            "cause": "communication_bus_controller_failure",
            "decision_tree_node": "Q2",
            "description": "All tags on the bus dead; controller unreachable.",
            "action_hint": "escalate_bms_vendor",
        },
        {
            "id": "KB-CM3",
            "cause": "configuration_drift",
            "decision_tree_node": "Q3",
            "description": "Tag missing/renamed in config + recent config change.",
            "action_hint": "restore_tag_mapping",
        },
        {
            "id": "KB-CM4",
            "cause": "loose_wiring_after_service",
            "decision_tree_node": "Q4",
            "description": "Recent physical service on sensor; reading absent.",
            "action_hint": "reseat_inspect_wiring",
        },
    ],
    "cases": [
        {
            "id": "KB-CASE-2024-011",
            "asset_type": "CRAH",
            "fault_signature": "supply_air_temp_absent past_calibration_interval "
                               "peer_ok controller_reachable",
            "root_cause": "sensor_hardware_failure",
            "action_taken": "sensor_replacement",
            "outcome": "resolved",
            "validated": True,
            "kb_ref": "KB-CASE-2024-011",
        },
        {
            "id": "KB-CASE-2025-033",
            "asset_type": "CRAH",
            "fault_signature": "all_tags_dead bus_unreachable "
                                "controller_unreachable",
            "root_cause": "communication_bus_controller_failure",
            "action_taken": "controller_swap_and_bus_re_init",
            "outcome": "resolved",
            "validated": True,
            "kb_ref": "KB-CASE-2025-033",
        },
        {
            "id": "KB-CASE-2025-041",
            "asset_type": "CRAH",
            "fault_signature": "tag_renamed recent_config_change "
                                "reading_absent",
            "root_cause": "configuration_drift",
            "action_taken": "tag_remap",
            "outcome": "resolved",
            "validated": True,
            "kb_ref": "KB-CASE-2025-041",
        },
    ],
}

# Current knowledge version (brief: "Version-controlled").
KNOWLEDGE_VERSION = "1.3.0"


def get_registry() -> dict:
    """Return the full in-memory demo registry (deterministic, no I/O)."""
    return {
        "ASSETS": ASSETS,
        "SENSORS": SENSORS,
        "LIVE_READINGS": LIVE_READINGS,
        "BMS_STATUS": BMS_STATUS,
        "MAINTENANCE_HISTORY": MAINTENANCE_HISTORY,
        "CONFIG_CHANGE_LOG": CONFIG_CHANGE_LOG,
        "KNOWLEDGE_BASE": KNOWLEDGE_BASE,
        "KNOWLEDGE_VERSION": KNOWLEDGE_VERSION,
    }


def _is_past_calibration(sensor: dict, today: date | None = None) -> bool:
    """Helper: is ``sensor`` past its calibration interval as of ``today``?"""
    today = today or date.today()
    last = date.fromisoformat(sensor["last_calibrated_at"])
    delta_days = (today - last).days
    return delta_days > sensor["calibration_interval_days"]