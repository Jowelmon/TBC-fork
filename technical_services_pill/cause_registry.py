"""Canonical cause IDs for the Technical Services fault-diagnosis pill.

This registry centralises IDs so decision-tree output, KB data, learning
retrieval, and UI labels all use the same semantic keys. Historical aliases are
kept intentionally to preserve compatibility with older rule sets.
"""
from __future__ import annotations

CAUSE_SENSOR_FAULT = "sensor_hardware_failure"
CAUSE_SENSOR_HARDWARE_FAILURE = "sensor_hardware_failure"
CAUSE_SENSOR_FAULT_NOISE = "sensor_fault_noise"
CAUSE_SENSOR_DRIFT = "sensor_drift"

CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE = "communication_bus_controller_failure"
CAUSE_COMM_BUS_FAILURE = CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE

CAUSE_CONFIG_DRIFT = "configuration_drift"
CAUSE_LOOSE_WIRING_AFTER_SERVICE = "loose_wiring_after_service"
CAUSE_LOOSE_WIRING = CAUSE_LOOSE_WIRING_AFTER_SERVICE

CAUSE_DATA_PATH_DROP = "data_path_drop"
CAUSE_INTERMITTENT_FAULT = "intermittent_fault"

CAUSE_REFRIGERANT_LEAK = "refrigerant_leak"
CAUSE_LOW_REFRIGERANT_CHARGE = "low_refrigerant_charge"
CAUSE_CONDENSER_FOULING = "condenser_fouling"
CAUSE_COMPRESSOR_MOTOR_FAULT = "compressor_motor_fault"
CAUSE_CHILLER_ELECTRICAL_FAULT = "chiller_electrical_fault"

CAUSE_THERMAL_RUNAWAY_RISK = "thermal_runaway_risk"
CAUSE_BATTERY_EOL = "battery_eol"
CAUSE_CHARGER_FAILURE = "charger_failure"
CAUSE_GROUND_FAULT = "ground_fault"
CAUSE_INVERTER_FAULT = "inverter_fault"

CAUSE_CAVITATION = "cavitation"
CAUSE_SHAFT_MISALIGNMENT = "shaft_misalignment"
CAUSE_FOUNDATION_LOOSENESS = "foundation_looseness"
CAUSE_BEARING_WEAR = "bearing_wear"
CAUSE_IMPELLER_IMBALANCE = "impeller_imbalance"

_CANONICAL = {
    "sensor_fault": CAUSE_SENSOR_FAULT,
    "sensor_hardware_failure": CAUSE_SENSOR_HARDWARE_FAILURE,
    "sensor_fault_noise": CAUSE_SENSOR_FAULT_NOISE,
    "sensor_drift": CAUSE_SENSOR_DRIFT,
    "communication_bus_controller_failure": CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE,
    "comm_bus_failure": CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE,
    "configuration_drift": CAUSE_CONFIG_DRIFT,
    "loose_wiring_after_service": CAUSE_LOOSE_WIRING_AFTER_SERVICE,
    "loose_wiring": CAUSE_LOOSE_WIRING_AFTER_SERVICE,
    "data_path_drop": CAUSE_DATA_PATH_DROP,
    "intermittent_fault": CAUSE_INTERMITTENT_FAULT,
    "refrigerant_leak": CAUSE_REFRIGERANT_LEAK,
    "low_refrigerant_charge": CAUSE_LOW_REFRIGERANT_CHARGE,
    "condenser_fouling": CAUSE_CONDENSER_FOULING,
    "compressor_motor_fault": CAUSE_COMPRESSOR_MOTOR_FAULT,
    "chiller_electrical_fault": CAUSE_CHILLER_ELECTRICAL_FAULT,
    "thermal_runaway_risk": CAUSE_THERMAL_RUNAWAY_RISK,
    "battery_eol": CAUSE_BATTERY_EOL,
    "charger_failure": CAUSE_CHARGER_FAILURE,
    "ground_fault": CAUSE_GROUND_FAULT,
    "inverter_fault": CAUSE_INVERTER_FAULT,
    "cavitation": CAUSE_CAVITATION,
    "shaft_misalignment": CAUSE_SHAFT_MISALIGNMENT,
    "foundation_looseness": CAUSE_FOUNDATION_LOOSENESS,
    "bearing_wear": CAUSE_BEARING_WEAR,
    "impeller_imbalance": CAUSE_IMPELLER_IMBALANCE,
}

CANONICAL_CAUSE_IDS = frozenset(_CANONICAL.values())


def canonicalize_cause_id(cause_id: str | None) -> str | None:
    if cause_id is None:
        return None
    return _CANONICAL.get(cause_id, cause_id)


# Human-readable labels and the asset type whose decision tree can emit each
# cause. The UI shows labels, never raw IDs; capture uses the asset type to
# file a heuristic under the right pill even when one interview covers
# several kinds of equipment.
CAUSE_INFO: dict[str, tuple[str, str]] = {
    CAUSE_SENSOR_HARDWARE_FAILURE: ("Sensor hardware failure", "CRAH"),
    CAUSE_SENSOR_FAULT_NOISE: ("Noisy sensor signal", "CRAH"),
    CAUSE_SENSOR_DRIFT: ("Sensor calibration drift", "CRAH"),
    CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE: ("Communication bus or controller failure", "CRAH"),
    CAUSE_CONFIG_DRIFT: ("BMS configuration drift", "CRAH"),
    CAUSE_LOOSE_WIRING_AFTER_SERVICE: ("Loose wiring after servicing", "CRAH"),
    CAUSE_DATA_PATH_DROP: ("Data path drop (gateway or SCADA)", "CRAH"),
    CAUSE_INTERMITTENT_FAULT: ("Intermittent fault", "CRAH"),
    CAUSE_REFRIGERANT_LEAK: ("Refrigerant leak", "Chiller"),
    CAUSE_LOW_REFRIGERANT_CHARGE: ("Low refrigerant charge", "Chiller"),
    CAUSE_CONDENSER_FOULING: ("Condenser fouling", "Chiller"),
    CAUSE_COMPRESSOR_MOTOR_FAULT: ("Compressor motor fault", "Chiller"),
    CAUSE_CHILLER_ELECTRICAL_FAULT: ("Chiller electrical fault", "Chiller"),
    CAUSE_THERMAL_RUNAWAY_RISK: ("Battery thermal runaway risk", "UPS"),
    CAUSE_BATTERY_EOL: ("Battery end of life", "UPS"),
    CAUSE_CHARGER_FAILURE: ("Charger failure", "UPS"),
    CAUSE_GROUND_FAULT: ("Ground fault", "UPS"),
    CAUSE_INVERTER_FAULT: ("Inverter fault", "UPS"),
    CAUSE_CAVITATION: ("Pump cavitation", "Pump"),
    CAUSE_SHAFT_MISALIGNMENT: ("Shaft misalignment", "Pump"),
    CAUSE_FOUNDATION_LOOSENESS: ("Loose foundation or mounting", "Pump"),
    CAUSE_BEARING_WEAR: ("Bearing wear", "Pump"),
    CAUSE_IMPELLER_IMBALANCE: ("Impeller imbalance", "Pump"),
}


def cause_label(cause_id: str | None) -> str:
    """Plain-English label for a cause ID; new causes are shown as proposed."""
    if not cause_id:
        return "Unknown cause"
    if cause_id.startswith("new:"):
        return "Proposed new cause: " + cause_id[4:].replace("_", " ")
    canon = canonicalize_cause_id(cause_id)
    if canon in CAUSE_INFO:
        return CAUSE_INFO[canon][0]
    return cause_id.replace("_", " ").capitalize()


def cause_asset_type(cause_id: str | None) -> str | None:
    """Asset type whose decision tree emits this cause, or None if unknown."""
    canon = canonicalize_cause_id(cause_id) if cause_id else None
    return CAUSE_INFO[canon][1] if canon in CAUSE_INFO else None


def list_causes() -> list[dict[str, str]]:
    return [{"id": cid, "label": lbl, "asset_type": at}
            for cid, (lbl, at) in CAUSE_INFO.items()]


__all__ = [
    "CANONICAL_CAUSE_IDS",
    "CAUSE_BATTERY_EOL",
    "CAUSE_BEARING_WEAR",
    "CAUSE_CAVITATION",
    "CAUSE_CHARGER_FAILURE",
    "CAUSE_CHILLER_ELECTRICAL_FAULT",
    "CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE",
    "CAUSE_COMM_BUS_FAILURE",
    "CAUSE_COMPRESSOR_MOTOR_FAULT",
    "CAUSE_CONDENSER_FOULING",
    "CAUSE_CONFIG_DRIFT",
    "CAUSE_DATA_PATH_DROP",
    "CAUSE_FOUNDATION_LOOSENESS",
    "CAUSE_GROUND_FAULT",
    "CAUSE_IMPELLER_IMBALANCE",
    "CAUSE_INFO",
    "CAUSE_INTERMITTENT_FAULT",
    "CAUSE_INVERTER_FAULT",
    "CAUSE_LOOSE_WIRING",
    "CAUSE_LOOSE_WIRING_AFTER_SERVICE",
    "CAUSE_LOW_REFRIGERANT_CHARGE",
    "CAUSE_REFRIGERANT_LEAK",
    "CAUSE_SENSOR_DRIFT",
    "CAUSE_SENSOR_FAULT",
    "CAUSE_SENSOR_FAULT_NOISE",
    "CAUSE_SENSOR_HARDWARE_FAILURE",
    "CAUSE_SHAFT_MISALIGNMENT",
    "CAUSE_THERMAL_RUNAWAY_RISK",
    "canonicalize_cause_id",
    "cause_asset_type",
    "cause_label",
    "list_causes",
]
