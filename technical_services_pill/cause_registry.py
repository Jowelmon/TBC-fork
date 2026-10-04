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


__all__ = [
    "CAUSE_SENSOR_FAULT",
    "CAUSE_SENSOR_HARDWARE_FAILURE",
    "CAUSE_SENSOR_FAULT_NOISE",
    "CAUSE_SENSOR_DRIFT",
    "CAUSE_COMMUNICATION_BUS_CONTROLLER_FAILURE",
    "CAUSE_COMM_BUS_FAILURE",
    "CAUSE_CONFIG_DRIFT",
    "CAUSE_LOOSE_WIRING_AFTER_SERVICE",
    "CAUSE_LOOSE_WIRING",
    "CAUSE_DATA_PATH_DROP",
    "CAUSE_INTERMITTENT_FAULT",
    "CAUSE_REFRIGERANT_LEAK",
    "CAUSE_LOW_REFRIGERANT_CHARGE",
    "CAUSE_CONDENSER_FOULING",
    "CAUSE_COMPRESSOR_MOTOR_FAULT",
    "CAUSE_CHILLER_ELECTRICAL_FAULT",
    "CAUSE_THERMAL_RUNAWAY_RISK",
    "CAUSE_BATTERY_EOL",
    "CAUSE_CHARGER_FAILURE",
    "CAUSE_GROUND_FAULT",
    "CAUSE_INVERTER_FAULT",
    "CAUSE_CAVITATION",
    "CAUSE_SHAFT_MISALIGNMENT",
    "CAUSE_FOUNDATION_LOOSENESS",
    "CAUSE_BEARING_WEAR",
    "CAUSE_IMPELLER_IMBALANCE",
    "CANONICAL_CAUSE_IDS",
    "canonicalize_cause_id",
]
