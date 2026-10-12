"""Which evidence readings are abnormal, for highlighting on screen.

One source of truth for the UI's red highlights, using the same thresholds
the decision trees diagnose with, so a reading that drives a diagnosis is
the one that looks abnormal (and a healthy one does not).
"""
from __future__ import annotations

from typing import Any

from .decision_tree import (
    _PUMP_AXIAL_HIGH_MM_S,
    _PUMP_BEARING_TEMP_HIGH_C,
    _PUMP_NPSH_LOW,
    _UPS_AGE_MONTHS_EOL,
    _UPS_SOH_FLOOR,
    _UPS_THERMAL_ESCALATE_C,
)

# Chiller thresholds the chiller tree uses inline (decision_tree.py).
_CHILLER_LOW_CHARGE_PCT = 70
_CHILLER_HIGH_APPROACH_C = 3.0

# Flags where True is the fault signal.
BAD_WHEN_TRUE = frozenset({
    "low_pressure_switch", "high_pressure_switch", "leak_detected", "motor_overcurrent",
    "temp_rising", "greasing_overdue", "soft_foot_detected", "directional_dominant",
    "on_battery", "calibration_overdue", "past_eol", "recent_disturbance", "recent_change",
    "tag_remap", "bearing_freq_present",
})
# Flags where False is the fault signal.
BAD_WHEN_FALSE = frozenset({
    "balance_ok", "charger_ok", "starter_ok", "contactor_ok", "bus_alive",
    "other_tags_reporting", "gateway_healthy", "scada_link_healthy", "fans_running",
})
# field -> predicate on the value that means "abnormal".
THRESHOLDS: dict[str, Any] = {
    "charge_pct": lambda v: v < _CHILLER_LOW_CHARGE_PCT,
    "approach_temp": lambda v: v >= _CHILLER_HIGH_APPROACH_C,
    "soh_pct": lambda v: v < _UPS_SOH_FLOOR,
    "age_months": lambda v: v >= _UPS_AGE_MONTHS_EOL,
    "battery_temp_c": lambda v: v >= _UPS_THERMAL_ESCALATE_C,
    "axial_mm_s": lambda v: v > _PUMP_AXIAL_HIGH_MM_S,
    "npsh_margin": lambda v: v < _PUMP_NPSH_LOW,
    "temp_c": lambda v: v > _PUMP_BEARING_TEMP_HIGH_C,
    "dominant_order": lambda v: v in ("2x", "1x", "broadband"),
}


# Plain-English names for evidence fields: the one source for every label on
# screen (the case snapshot sends them with each evidence item) and in the
# AI second opinion's evidence lines.
FIELD_LABELS = {
    "soh_pct": "State of health (%)",
    "age_months": "Age (months)",
    "battery_temp_c": "Battery temp (°C)",
    "temp_c": "Temp (°C)",
    "charge_pct": "Refrigerant charge (%)",
    "approach_temp": "Approach temp (°C)",
    "axial_mm_s": "Axial vibration (mm/s)",
    "npsh_margin": "NPSH margin",
    "load_pct": "Load (%)",
    "flow_pct": "Flow (%)",
    "float_voltage": "Float voltage (V)",
    "battery_voltage": "Battery voltage (V)",
    "past_eol": "Past end of life",
    "is_past_calibration": "Past calibration date",
    "calibration_overdue": "Calibration overdue",
    "calibration_interval_days": "Calibration interval (days)",
    "last_calibrated_at": "Last calibrated",
    "npsh_margin_m": "NPSH margin",
    "scada_link": "SCADA link",
    "scada_link_healthy": "SCADA link healthy",
    "bus_id": "Bus",
    "bus_alive": "Bus alive",
    "bus_reachable": "Bus reachable",
    "controller_id": "Controller",
    "tags_alive": "Tags reporting",
    "tags_dead": "Tags silent",
    "other_tags_reporting": "Other tags on the bus reporting",
    "tag_remap": "Tag renamed or remapped",
    "ts": "Time",
    "last_good_ts": "Last good reading at",
    "last_good_value": "Last good value",
    "soh": "State of health",
    "soft_foot_detected": "Soft foot detected",
    "dominant_order": "Dominant vibration order",
    "directional_dominant": "Directional vibration dominant",
    "bearing_freq_present": "Bearing defect frequency present",
    "rpm": "Speed (rpm)",
    "oil_level": "Oil level",
    "superheat": "Superheat (K)",
    "subcooling": "Subcooling (K)",
    "winding_resistance": "Winding resistance (MΩ)",
    "motor_overcurrent": "Motor overcurrent",
    "fouling_factor": "Fouling factor",
    "cooling_capacity_kw": "Cooling capacity (kW)",
    "design_supply_temp_c": "Design supply temp (°C)",
    "design_return_temp_c": "Design return temp (°C)",
    "charge_current": "Charge current (A)",
    "on_battery": "Running on battery",
    "ups_id": "UPS",
    "parent_system_id": "Parent system",
    "site_id": "Site",
    "commissioned_at": "Commissioned",
}


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key) or key.replace("_", " ").capitalize()


def abnormal_fields(payload: Any) -> list[str]:
    """Names of the fields in one evidence payload that signal a fault."""
    if not isinstance(payload, dict):
        return []
    out = []
    for key, value in payload.items():
        bad_flag = (value is True and key in BAD_WHEN_TRUE) or (value is False and key in BAD_WHEN_FALSE)
        if bad_flag or (key == "alarms" and isinstance(value, list) and value):
            out.append(key)
        elif key in THRESHOLDS and isinstance(value, (int, float, str)) and not isinstance(value, bool):
            try:
                if THRESHOLDS[key](value):
                    out.append(key)
            except TypeError:
                pass
    return out
