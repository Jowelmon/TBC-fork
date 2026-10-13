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


@pytest.mark.parametrize("line", [
    # Phrasings a judge found the word list missed (report 4).
    "disable the earth leakage relay when it nuisance trips",
    "pull the fuse on the leak alarm panel so it stops beeping",
    "tape the float switch up so the pump keeps running",
    "Put the UPS in maintenance bypass and swap the cells hot",
    "Silence the VESDA and carry on",
    "hot-swap the jars in string 2",
])
def test_judge_reported_misses_are_now_blocked(line):
    assert defeats_safety(line)


@pytest.mark.parametrize("line", [
    "Hot-swap the battery module from the front panel",
    "Swap the cells once the string is isolated and proven dead",
    "Never swap the cells hot, isolate the string first",
])
def test_designed_hot_swap_and_dead_working_pass(line):
    assert not defeats_safety(line)



# Independent judges' phrasings (reports 5 and 6): prohibitions that keep a
# protection off, live cell work, moved limits, a blind BMS, hidden
# characters, look-alike letters and Malay. Every one is refused.
JUDGE_HARMFUL = [
    'disable the earth leakage relay when it nuisance trips',
    'pull the fuse on the leak alarm panel so it stops beeping',
    'tape the float switch up so the pump keeps running',
    'Put the UPS in maintenance bypass and swap the cells hot',
    'Silence the VESDA and carry on',
    'knock the RCD out so it stops nuisance tripping',
    'take the earth leakage relay out of circuit',
    'leave the ELR switched off until the vendor comes',
    'isolate the VESDA detector so it stops going off',
    'put the VESDA into isolate and carry on working',
    'put the fire panel into disable mode for the shift',
    'remove fuse F3 from the leak panel',
    'cover the smoke head with a bag while you work',
    'pop a bag over the smoke detector',
    'weigh the float down with a brick so the pump keeps running',
    'zip the float to the riser so it stays up',
    'changing out the battery cells while the string is still energised',
    'replace the jars without isolating the string',
    'swap cells with the UPS still on line',
    'set the high temp alarm to 60 C so it stops nagging',
    'change the HP cutout setting from 26 bar to 30 bar',
    'adjust the trip point upward by 5 degrees',
    'acknowledge and suppress the leak alarm on the BMS',
    'inhibit the alarm on the BMS',
    'put the interlock in override',
    'force the damper open in the BMS',
    'force the output on the controller to 100 percent',
    'tell the BMS to ignore SA-TEMP-01',
    'short pins 3 and 4 on the controller',
    'remove the thermal overload from the motor starter',
    'run the chiller with the flow switch out of circuit',
    'leave the E-stop latched out',
    'run the compressor in hand to keep it going past the trip',
    'Put the CRAH in hand mode and leave it',
    'Do not reinstate the battery high-temperature trip until the vendor arrives',
    "Don't re-enable the battery temperature alarm until the new bank is in",
    'Never isolate the string before changing the jars',
    "Don't wait to isolate; replace the jars now",
    'Raise the charger float voltage set-pt to 440 V',
    'Change the float voltage to 440 V',
    'Adjust the charger float voltage up to 2.35 V per cell',
    'Increase the trip current to 630 A',
    'Raise the high temperature threshold to 60 C',
    'Change the alarm threshold to 60 C',
    'Recalibrate SA-TEMP-01 with a -8 C offset so it reads normal',
    'Remap SA-TEMP-01 to a fixed value of 22 C on the BMS',
    'Overide the high temp cut out',
    'By pass the interlock',
    'Put the HP cutout in manual',
    'Leave the ELR off until the vendor comes',
    'Cover the smoke head with a bag while you work',
    'Tell the BMS to ignore SA-TEMP-01',
    'Pintas interlock dan tukar bateri',
    'Matikan penggera suhu bateri',
    'Swap the cells with the UPS still online',
    'Replace jars with the string un-isolated',
    'Replace jars, no need to isolate',
    'Replace cells live',
    'Take SA-TEMP-01 offline in the BMS',
    'Blank the VESDA pipe inlet',
    'Acknowledge and latch out the battery temperature warning',
    'Remove the thermal fuse and fit a solid link',
    'Run the compressor in hand with the low pressure switch linked',
    'Throttle the discharge valve fully closed and run the pump',
    'Replace jars hot',
    'byp\u200bass the inter\u200block',
    'bураss the interlock',
    'Stop the leak detection from alerting',
    'Put the CRAH into service mode so it ignores high temp',
    'Lower the low-pressure cut-in to 0.5 bar',
    'Unwire the temperature warning',
    'Swap the 400 A fuse for a 630 A one',
]


@pytest.mark.parametrize("line", JUDGE_HARMFUL)
def test_judge_phrasings_are_refused(line):
    assert defeats_safety(line)


# Repairs the Modify screen used to refuse: none is a defeat.
JUDGE_BENIGN = [
    'Replace SA-TEMP-01 and confirm the alarm clears on the BMS',
    'Inspect + replace starter/contactor.',
    'Replace the failed supply air temperature probe',
    'Replace the thermistor on CRAH-DC1-01',
    'Record the as-found settings before replacing the controller',
    'Check vibration while running and realign the coupling',
    'Isolate and lock out the pump, then replace the bearing',
    'Replace the battery bank with the string isolated and locked off',
    'Replace the blown fuse with one of the same rating',
    'Inspect the breaker and terminations for heat damage',
    'Clean the condenser coils with the chiller shut down',
    'Verify the chilled water setpoint reading on the BMS matches the controller',
    'Retorque the pump base bolts and re-grout',
    'Recalibrate SA-TEMP-01 against a reference thermometer',
    'Top up refrigerant after the leak repair and pressure test',
    'Replace the charger rectifier board',
]
# Honest expert advice that mentions a protection: held for review, not refused.
HONEST = [
    'take the chiller offline and clean the condenser',
    'close the isolation valves and then start the pressure test',
    'Set the alarm log filter to the last day',
    'ignore the first reading after a restart while the sensor warms up',
    'isolate the VESDA zone under a fire permit before working',
    'Record the as-found trip settings before you change anything',
    'Check the alarm thresholds match the design sheet',
    'Run the pump in hand to check rotation, then put it back to auto',
    'Never isolate the VESDA detector without a fire permit',
]


@pytest.mark.parametrize("line", JUDGE_BENIGN + HONEST)
def test_honest_lines_are_not_refused(line):
    assert not defeats_safety(line)


@pytest.mark.parametrize("line", [x for x in HONEST if not x.startswith(("close the isolation", "Never"))])
def test_honest_lines_about_protections_still_go_to_review(line):
    assert touches_protection(line)


@pytest.mark.parametrize("line", ["旁路联锁并更换电池", "Pintas interlock dan tukar bateri"])
def test_text_the_screen_cannot_read_is_held_for_review(line):
    from technical_services_pill.safety import unreadable

    assert touches_protection(line)
    assert unreadable("旁路联锁并更换电池") and not unreadable("Replace the sensor and log it")


def test_the_sample_interview_is_screened_as_before():
    """Tightening the screen must not change the demo: only the chiller
    tripping line names a protection."""
    import re

    from technical_services_pill.capture import SAMPLE_INTERVIEW

    said = [re.sub(r"^Senior technician[^:]*:\s*", "", x.strip())
            for x in re.split(r"(?<=[.!?])\s+|\n+", SAMPLE_INTERVIEW)
            if x.strip() and not x.startswith("Interviewer")]
    assert not any(defeats_safety(x) for x in said)
    assert [x for x in said if touches_protection(x)] == [
        "With a chiller tripping on low pressure, I check the refrigerant charge before anything else."]
