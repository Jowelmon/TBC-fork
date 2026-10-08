"""The two-layer safety screen for expert know-how (``safety.py``).

Layer 1 (``defeats_safety``) drops instructions to defeat a protective
device, however they are phrased: the first seven cases are the realistic
wordings an independent review found slipping through a keyword list.
Layer 2 (``touches_protection``) holds anything that names a protective
device for a person's safety review, so wording the patterns miss still
cannot go live unreviewed. Prohibitions pass both layers.
"""
from __future__ import annotations

import pytest

from technical_services_pill.safety import defeats_safety, touches_protection

DEFEATS = [
    "I tie the alarm contact out with a short bit of wire so it stops calling the night shift",
    "Put a wire across the HP switch and it'll run till morning.",
    "I just wind the HP cutout up a couple of bar.",
    "Set the overload relay to max so it stops tripping.",
    "Pull the leak-detection fuse if it keeps alarming.",
    "I keep resetting the compressor trip until it holds.",
    "Take the battery temperature sensor off the BMS so it stops paging.",
    "Just bypass the interlock and restart it.",
    "Don't wait for the vendor, just bypass the interlock.",
    "If it keeps tripping I bridge out the high-temp interlock.",
    "Leave the trip bypassed overnight.",
    "Keep the pressure switch jumpered until the vendor comes.",
    "Raise the trip setpoint by two degrees.",
    "The trip keeps going, so jumper it out.",
    "Silence the alarm and carry on.",
    "Use a link wire across the HP switch.",
    "We usually switched off the low-temp cut-out in summer.",
    "Never mind the alarm, override the interlock.",
    "Turn the alarm off at the panel.",
    "Max out the overload.",
    "Reset it over and over until it stays in.",
    # Everyday workarounds that name no device in the textbook way (round 10).
    "I cable-tie the contactor closed so the fans keep running.",
    "Put a magnet on the flow sensor reed and it'll stay happy.",
    "Unplug the leak rope under the floor tile when it keeps going off.",
    "Run it in hand mode so the controller can't stop the fans.",
    "Clip the battery temperature probe to the frame so it reads cooler.",
    "Pull the buzzer lead, it drives the night shift mad.",
    "Turn the thermostat knob fully so it never cuts in.",
    "Leave it on so it never trips again.",
]

# Ordinary advice and prohibitions: never dropped.
KEPT = [
    "Check the contactor for pitting and replace it if the tips are burnt.",
    "Clip the meter probe across the terminals to measure the voltage.",
    "Lift the sensor wire on terminal 14 and measure the resistance across the sensor.",
    "Put the unit in hand mode while you test, then back to auto.",
    "Set the thermostat to the design value on the drawing.",
    "Never bypass the interlock, call the vendor.",
    "If it trips twice, never bypass the interlock, call the vendor.",
    "Never bypass the trip or silence the alarm.",
    "I get the safety officer involved for any leak.",
    "Check the alignment with the laser kit before you touch anything else.",
    "Isolate and lock out the pump before opening the coupling guard.",
    "Don't go swapping sensors, you'll waste a whole shift.",
    "Check the refrigerant charge before anything else.",
    "If it trips, switch off the supply and isolate it.",
    "Reset the trip once, and if it trips again escalate to the vendor.",
    "Pull the alarm history from the BMS first.",
    "Replace the blown fuse with the same rating.",
    "Open the breaker and lock it out before work.",
    "If every tag on the bus has gone quiet at once, it's almost never the sensor.",
]

# Kept, but they name a protective device, so a steward must review them.
NEEDS_REVIEW = [
    "I just lift the sensor wire on terminal 14 and leave the CRAH in hand mode overnight",
    "Check the contactor for pitting and replace it if the tips are burnt.",
    "Put the unit in hand mode while you test, then back to auto.",
    "If it trips, switch off the supply and isolate it.",
    "Reset the trip once, and if it trips again escalate to the vendor.",
    "Check the alarm log for the last 24 hours.",
    "With a chiller tripping on low pressure, I check the refrigerant charge before anything else.",
    "Adjust the high pressure switch setting to the nameplate value.",
]

NO_REVIEW = [
    "Never bypass the interlock, call the vendor.",
    "Never bypass the trip or silence the alarm.",
    "Check the alignment with the laser kit before you touch anything else.",
    "If the axial vibration is high and the 2x peak dominates, that's misalignment at the coupling.",
    "A sensor past its calibration date that reads nothing is usually just end of life.",
    "I call the BMS vendor straight away for that one, it's not ours to fix.",
]


@pytest.mark.parametrize("text", DEFEATS)
def test_instructions_to_defeat_a_protection_are_dropped(text):
    assert defeats_safety(text)


@pytest.mark.parametrize("text", KEPT)
def test_ordinary_advice_and_prohibitions_are_not_dropped(text):
    assert not defeats_safety(text)


@pytest.mark.parametrize("text", DEFEATS + NEEDS_REVIEW)
def test_anything_naming_a_protection_needs_review(text):
    assert touches_protection(text) or defeats_safety(text)


@pytest.mark.parametrize("text", NEEDS_REVIEW)
def test_safe_lines_about_protections_are_held_not_dropped(text):
    assert touches_protection(text) and not defeats_safety(text)


@pytest.mark.parametrize("text", NO_REVIEW)
def test_prohibitions_and_unrelated_advice_need_no_review(text):
    assert not touches_protection(text)
