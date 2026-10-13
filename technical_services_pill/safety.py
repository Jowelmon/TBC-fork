"""Safety screen for expert know-how: G1 applied to knowledge, not only to
recommendations.

The guardrail engine stops the *agent* recommending a BMS setpoint,
interlock or safety change (G1). Expert knowledge is shown to the AOM next
to that recommendation, so the same rule applies to it, in two layers:

1. ``defeats_safety`` — a hard screen. A line that tells someone to defeat
   a protective device (bypass, jumper, wire across, tie out, wind up the
   cut-out, set the overload to max, pull the detection fuse, take a sensor
   off the BMS, keep resetting a trip...) is never stored, and is withheld
   again when knowledge is displayed.
2. ``touches_protection`` — deny by default. Any line that mentions a
   protective device or the monitoring that feeds one (alarm, trip,
   cut-out, interlock, relay, overload, fuse, breaker, setpoint, limit,
   leak detection, BMS monitoring...) and is not said as a prohibition is
   held for the approving steward to tick "safety reviewed". Such knowledge
   is shown as guidance with who reviewed it, and never raises confidence.

A pattern screen cannot understand every wording, which is why the second
layer does not try to: it only needs to recognise the *device*, and then a
person decides. A prohibition ("never bypass the interlock") is the
opposite of an instruction and passes both layers.

Text is judged clause by clause, so "Don't wait for the vendor, just
bypass the interlock" is caught (the second clause is an instruction), and
"If it trips twice, never bypass the interlock, call the vendor" is not
caught by the hard screen (the clause naming the bypass is a prohibition).
"""
from __future__ import annotations

import re
import unicodedata

# Verbs that defeat a protection, in any inflection (bypassed, jumpering...).
_ACTION = (
    r"by[- ]?pass(?:es|ed|ing)?|over-?r?id(?:e|es|den|ing)|overrode|suppress(?:es|ed|ing)?|"
    r"inhibit(?:s|ed|ing)?|latch(?:es|ed|ing)?\s+(?:it\s+|them\s+)?out|unwir(?:e|es|ed|ing)|blank(?:s|ed|ing)?|defeat(?:s|ed|ing)?|"
    r"disabl(?:e|es|ed|ing)|deactivat(?:e|es|ed|ing)|jumper(?:s|ed|ing)?|"
    r"bridg(?:e|es|ed|ing)(?:\s+(?:it|them))?(?:\s+out)?|link(?:s|ed|ing)?(?:\s+(?:it|them))?\s+out|"
    r"short(?:s|ed|ing)?(?:\s+(?:it|them))?\s+out|wedg(?:e|es|ed|ing)|tap(?:e|es|ed|ing)\s+over|"
    r"ti(?:e|es|ed|ing)\s+(?:down|up|back|out)|pin(?:s|ned|ning)?\s+(?:open|closed|shut)|"
    r"gag(?:s|ged|ging)?|silenc(?:e|es|ed|ing)|mut(?:e|es|ed|ing)|ignor(?:e|es|ed|ing)|"
    r"(?:switch(?:es|ed|ing)?|turn(?:s|ed|ing)?)\s+off|cheat(?:s|ed|ing)?|"
    r"disconnect(?:s|ed|ing)?|unplug(?:s|ged|ging)?|max(?:es|ed|ing)?\s+out"
)
# Protective devices for the hard screen. Deliberately narrower than
# _PROTECTION below: "safety officer", an isolator, a lockout, or a breaker
# opened to isolate equipment are things people should use, not defeat.
_DEVICE = (
    r"interlocks?|alarms?(?:\s+(?:contacts?|relays?|circuits?|outputs?|points?))?|trips?|"
    r"trip\s+(?:switch|setting|circuit|relay)|pressure\s+switch(?:es)?|"
    r"hp\s+(?:switch|cut[- ]?out)|lp\s+(?:switch|cut[- ]?out)|protections?|cut[- ]?outs?|relief\s+valves?|"
    r"limit\s+switch(?:es)?|overloads?(?:\s+relays?)?|"
    r"(?:high|low)-?\s?temp(?:erature)?\s+(?:cut[- ]?out|trip|limit|switch|interlock|protection|alarm)|"
    r"(?:leak|smoke|fire|gas|water)[- ]?detect(?:ion|ors?)?(?:\s+(?:fuse|circuit|system))?|"
    r"e-?stops?|emergency\s+stops?|buzzers?|sounders?|horns?|beacons?|sirens?|vesda|"
    r"earth[- ]leakage\s+(?:relays?|protection|breakers?|trips?)|rcds?|elcbs?|rcbos?|elrs?|"
    r"(?:smoke|heat|fire)\s+(?:heads?|detectors?|panels?|alarms?)|detectors?|"
    r"(?:temperature|temp|battery)\s+(?:warnings?|alarms?)|warnings?|cut-?\s?ins?|"
    r"(?:float|flow|level|reed|door)\s+switch(?:es)?|"
    r"safety\s+(?:device|interlock|valve|circuit|chain|relay|switch|system)"
)
# The limits a protection acts at.
_LIMIT = (
    r"cut-?outs?|trips?|trip\s+points?|trip\s+settings?|set\s?points?|limits?|overloads?|"
    r"relays?|pressure\s+switch(?:es)?|hp\s+switch|lp\s+switch"
)
_INSTRUCTION = [
    # verb ... device: "bridge out the high-temp interlock", "leave the trip bypassed"
    re.compile(rf"\b(?:{_ACTION})\b[^.;]{{0,40}}?\b(?:{_DEVICE})\b", re.IGNORECASE),
    # device ... verb: "keep the pressure switch jumpered", "the trip keeps going, so
    # jumper it out". Not when the verb has an object of its own: "if it trips,
    # switch off the supply" is isolating equipment, not defeating the trip.
    re.compile(rf"\b(?:{_DEVICE})\b[^.;]{{0,30}}?\b(?:{_ACTION})\b"
               r"(?!\s+(?:the|a|an|this|its|their|power|supply|unit|pump|compressor|fan|chiller|"
               r"crah|ups|mains|isolator)\b)", re.IGNORECASE),
    # verb, device, particle: "tie the alarm contact out", "turn the alarm off"
    re.compile(rf"\b(?:ti(?:e|es|ed|ing)|wir(?:e|es|ed|ing)|link(?:s|ed|ing)?|short(?:s|ed|ing)?|"
               rf"turn(?:s|ed|ing)?|switch(?:es|ed|ing)?|knock(?:s|ed|ing)?|tak(?:e|es|en|ing)|took|"
               rf"tap(?:e|es|ed|ing)|strap(?:s|ped|ping)?|prop(?:s|ped|ping)?)"
               rf"\b[^.;]{{0,30}}?\b(?:{_DEVICE})\b[^.;]{{0,20}}?\b(?:out|off|down|over|up)\b", re.IGNORECASE),
    # raising a protective limit: "raise the trip setpoint", "wind the HP cut-out up",
    # "set the overload relay to max"
    re.compile(r"\b(?:raise|raising|increase|increasing|bump|bumping|lift|widen)\s+(?:the\s+)?"
               r"(?:[a-z-]+\s+){0,2}?(?:trip\s+point|trip\s+setting|setpoint|set\s+point|cut-?out|"
               r"high\s+limit|pressure\s+limit|temperature\s+limit|overload)\b", re.IGNORECASE),
    re.compile(rf"\b(?:wind|winds|wound|winding|turn(?:s|ed|ing)?|crank(?:s|ed|ing)?|dial(?:s|led|ling)?|"
               rf"push(?:es|ed|ing)?|knock(?:s|ed|ing)?)\b[^.;]{{0,30}}?\b(?:{_LIMIT})\b[^.;]{{0,15}}?\bup\b",
               re.IGNORECASE),
    re.compile(rf"\bset(?:s|ting)?\b[^.;]{{0,40}}?\b(?:{_LIMIT}|breakers?|protections?)\b[^.;]{{0,20}}?"
               rf"\bto\s+(?:the\s+)?(?:max(?:imum)?|highest|top|full|its\s+max(?:imum)?)\b", re.IGNORECASE),
    # the tools of defeating a protection: "a link wire", "put a wire across the HP switch"
    re.compile(r"\b(?:link|jumper|cheater|bridging)\s+(?:wire|lead|cable)s?\b", re.IGNORECASE),
    re.compile(r"\b(?:wire|lead|link|strap|piece\s+of\s+wire|bit\s+of\s+wire)\s+"
               r"(?:across|over|round|around|between)\b", re.IGNORECASE),
    # pulling the fuse of a detection or protection circuit
    re.compile(r"\b(?:pull(?:s|ed|ing)?|remov(?:e|es|ed|ing)|tak(?:e|es|en|ing)\s+out|took\s+out)\b"
               r"[^.;]{0,30}?\b(?:leak|smoke|fire|gas|water|alarm|detection|detector|protection|interlock|"
               r"safety)[- \w]{0,20}?fuses?\b", re.IGNORECASE),
    # taking something out of monitoring: "take the battery temperature sensor off the BMS"
    # ("pull the alarm history from the BMS" is reading it, so "pull" needs "off").
    re.compile(r"\b(?:tak(?:e|es|en|ing)|took|disconnect(?:s|ed|ing)?|unplug(?:s|ged|ging)?|"
               r"lift(?:s|ed|ing)?|remov(?:e|es|ed|ing)|drop(?:s|ped|ping)?)\b"
               r"[^.;]{0,50}?\b(?:off|out\s+of|from)\s+(?:the\s+)?(?:bms|scada|monitoring|alarm\s+list|"
               r"protection)\b", re.IGNORECASE),
    re.compile(r"\bpull(?:s|ed|ing)?\b[^.;]{0,50}?\b(?:off|out\s+of)\s+(?:the\s+)?"
               r"(?:bms|scada|monitoring|alarm\s+list|protection)\b", re.IGNORECASE),
    # everyday workarounds: "cable-tie the contactor closed", "a magnet on the
    # flow reed", "unplug the leak rope", "clip the probe to the frame",
    # "pull the buzzer lead", "turn the thermostat knob fully"
    re.compile(r"\b(?:cable-?ti(?:e|es|ed|ing)|zip-?ti(?:e|es|ed|ing)|ti(?:e|es|ed|ing)|wedg(?:e|es|ed|ing)|"
               r"jam(?:s|med|ming)?|strap(?:s|ped|ping)?|hold(?:s|ing)?|held|block(?:s|ed|ing)?)\b"
               r"[^.;]{0,30}?\bcontactors?\b[^.;]{0,20}?\b(?:in|closed|shut|on)\b", re.IGNORECASE),
    re.compile(r"\bmagnets?\b[^.;]{0,40}?\b(?:reed|flow|float|level|door|limit|switch|sensor)\w*", re.IGNORECASE),
    re.compile(r"\b(?:unplug\w*|disconnect\w*|pull\w*|remov\w*|cut(?:s|ting)?|lift\w*)\b[^.;]{0,30}?"
               r"\b(?:leak|water)[- ]?(?:detection\s+)?(?:rope|cable|tape|sensor|detector)s?\b", re.IGNORECASE),
    re.compile(r"\b(?:clip\w*|tap(?:e|es|ed|ing)|stick(?:s|ing)?|stuck|mov(?:e|es|ed|ing)|hang(?:s|ing)?|hung|"
               r"zip-?ti\w*|cable-?ti\w*)\b[^.;]{0,40}?\b(?:probes?|sensors?|thermistors?|rtds?)\b[^.;]{0,30}?"
               r"\b(?:to|on|onto|against|under|outside)\s+(?:the\s+)?(?:frame|chassis|casing|outside|floor|door|"
               r"cabinet|wall|pipe|ambient|cold\w*)\b", re.IGNORECASE),
    re.compile(r"\b(?:pull\w*|unplug\w*|disconnect\w*|cut(?:s|ting)?|lift\w*|remov\w*)\b[^.;]{0,30}?"
               r"\b(?:buzzers?|sounders?|horns?|beacons?|sirens?|strobes?|bells?)\b", re.IGNORECASE),
    re.compile(r"\bthermostats?\b[^.;]{0,40}?\b(?:fully|all\s+the\s+way|right|max\w*|full)\b", re.IGNORECASE),
    # the intent gives it away: "...so it never cuts in", "so the controller can't stop the fans"
    re.compile(r"\bso\s+(?:that\s+)?(?:it|they|the\s+\w+(?:\s+\w+)?)\s+(?:never|won'?t|doesn'?t|don'?t|"
               r"can'?t|cannot|stops?|isn'?t\s+able\s+to)\b[^.;]{0,30}?\b(?:cut\w*|trip\w*|alarm\w*|call\w*|"
               r"pag\w*|shut\w*|stop\w*|go(?:es)?\s+off|kick\w*|see\w*|sens\w*|detect\w*|warn\w*)\b",
               re.IGNORECASE),
    re.compile(r"\bstop(?:s|ped|ping)?\s+it\s+(?:from\s+)?(?:alarm|trip|call|pag|cutt?|shutt?|go)\w*\b",
               re.IGNORECASE),
    # joining contacts by hand: "touch the two pins together", "short the terminals"
    re.compile(r"\b(?:touch\w*|short\w*|join\w*|bridg\w*|connect\w*|link\w*)\b[^.;]{0,30}?"
               r"\b(?:pins?|terminals?|contacts?|leads?|wires?)\b[^.;]{0,15}?\btogether\b", re.IGNORECASE),
    # holding a control in: "hold the reset button down with a cable tie"
    re.compile(r"\b(?:hold\w*|held|ti(?:e|es|ed|ing)|cable-?ti\w*|zip-?ti\w*|tap(?:e|es|ed|ing)|wedg\w*|"
               r"jam\w*|weigh\w*|stick\w*|stuck)\b[^.;]{0,30}?\b(?:reset|test|override|start|mute|"
               r"silence|acknowledge)\s+(?:buttons?|switch(?:es)?|keys?|push(?:es)?)\b", re.IGNORECASE),
    # a fuse or breaker uprated: "swap the fuse for a bigger one"
    re.compile(r"\b(?:swap\w*|replac\w*|chang\w*|put\w*|fit\w*|up-?rat\w*|upgrad\w*)\b[^.;]{0,30}?"
               r"\b(?:fuses?|breakers?|mcbs?)\b[^.;]{0,30}?\b(?:bigger|larger|higher|heavier|up-?rated|"
               r"higher[- ]rated)\b", re.IGNORECASE),
    # the fuse feeding a detection or alarm circuit: "pull the fuse on the leak alarm"
    re.compile(r"\b(?:pull\w*|remov\w*|tak(?:e|es|en|ing)\s+out|took\s+out)\b[^.;]{0,20}?\bfuses?\b"
               r"[^.;]{0,30}?\b(?:leak|smoke|fire|gas|water|alarm|detection|detector|protection|interlock|"
               r"safety|vesda)\w*", re.IGNORECASE),
    # working on live battery cells: "swap the cells hot", "hot-swap the jars".
    # Battery *modules* built for hot-swap are a designed feature, so they pass.
    re.compile(r"\b(?:swap\w*|chang\w*|replac\w*|pull\w*|remov\w*|fit\w*)\b[^.;]{0,30}?"
               r"\b(?:cells?|jars?|battery\s+blocks?|monoblocs?|strings?)\b[^.;]{0,20}?"
               r"\b(?:hot|live|energi[sz]ed|under\s+load|on\s+load|while\s+(?:it'?s\s+)?(?:live|running|on\s+load))\b",
               re.IGNORECASE),
    re.compile(r"\b(?:hot|live)[- ]?swap\w*\b[^.;]{0,30}?\b(?:cells?|jars?|battery\s+blocks?|monoblocs?|strings?)\b",
               re.IGNORECASE),
    # leaving a protection off: "leave the ELR switched off", "keep the E-stop latched out"
    re.compile(rf"\b(?:leav(?:e|es|ing)|left|keep(?:s|ing)?|kept|run\w*)\b[^.;]{{0,30}}?\b(?:{_DEVICE})\b"
               r"[^.;]{0,25}?\b(?:off|out|disabled|isolated|bypassed|linked|latched|in\s+override|"
               r"out\s+of\s+circuit)\b", re.IGNORECASE),
    re.compile(r"\bout\s+of\s+circuit\b", re.IGNORECASE),
    # isolating or covering detection: "isolate the VESDA", "a bag over the smoke head"
    re.compile(r"\b(?:cover\w*|bag\w*|blank\w*|mask\w*|pop\w*|tap(?:e|es|ed|ing))\b"
               r"[^.;]{0,30}?\b(?:vesda|smoke|heat\s+detector|fire\s+(?:panel|alarm|detector)|detectors?|"
               r"sampling\s+(?:pipe|point|hole)s?|pipe\s+inlets?)\b", re.IGNORECASE),
    re.compile(r"\bisolat\w*\b[^.;]{0,30}?\b(?:vesda|smoke|detectors?|fire\s+(?:panel|alarm))\b[^.;]{0,30}?"
               r"\b(?:so\b|and\s+carry\s+on|carry\s+on|for\s+the\s+(?:shift|day|night)|until)", re.IGNORECASE),
    re.compile(r"\b(?:vesda|smoke\s+\w+|detector|fire\s+panel|alarm\s+panel)\b[^.;]{0,25}?"
               r"\b(?:into|in)\s+(?:isolat\w*|disable\w*|bypass|test)(?:\s+mode)?\b", re.IGNORECASE),
    re.compile(r"\b(?:into|in)\s+(?:disable|isolate|bypass)\s+mode\b", re.IGNORECASE),
    # weighing or tying a float: "weigh the float down with a brick"
    re.compile(r"\b(?:weigh\w*|zip\w*|ti(?:e|es|ed|ing)|wedg\w*|jam\w*|prop\w*|hold\w*|held|stick\w*|"
               r"strap\w*)\b[^.;]{0,30}?\bfloat\w*", re.IGNORECASE),
    # working on live battery cells, however said
    re.compile(r"\b(?:swap\w*|chang\w*|replac\w*|remov\w*|fit\w*|pull\w*)\b[^.;]{0,40}?"
               r"\b(?:cells?|jars?|battery\s+blocks?|monoblocs?|strings?|batter(?:y|ies))\b[^.;]{0,50}?"
               r"\b(?:energi[sz]ed|live|hot|on\s?-?line|un-?isolated|without\s+isolat\w*|"
               r"no\s+need\s+to\s+isolate|still\s+(?:running|on|connected|in\s+service))\b", re.IGNORECASE),
    re.compile(r"\b(?:don'?t|do\s+not|never|no\s+need\s+to)\s+(?:wait\s+to\s+|bother\s+to\s+)?isolat\w*"
               r"[^.;]{0,30}?\b(?:strings?|banks?|batter(?:y|ies)|jars?|cells?|supply|power)\b", re.IGNORECASE),
    re.compile(r"\b(?:don'?t|do\s+not)\s+wait\s+to\s+isolate\b", re.IGNORECASE),
    # keeping a protection off: "do not reinstate the trip until...", "don't re-enable the alarm"
    re.compile(r"\b(?:don'?t|do\s+not|never|no\s+need\s+to)\s+(?:re-?\s?instate|re-?\s?enable|re-?arm|"
               r"restore|put\s+back|turn\s+(?:it\s+|them\s+)?back\s+on|switch\s+(?:it\s+|them\s+)?back\s+on)\b",
               re.IGNORECASE),
    # moving a protective limit: "set the alarm to 60 C", "lower the cut-in to 0.5 bar"
    re.compile(r"\b(?:set|sets|setting|chang\w*|adjust\w*|rais\w*|lower\w*|increas\w*|decreas\w*|"
               r"mov(?:e|es|ed|ing)|bump\w*|alter\w*|widen\w*)\b[^.;]{0,40}?"
               r"\b(?:alarms?|trips?|trip\s+(?:point|current|setting)s?|cut-?\s?(?:out|in)s?|thresholds?|"
               r"limits?|set-?\s?p(?:oin)?ts?|overloads?|float\s+voltage)\b[^.;]{0,40}?"
               r"(?:\b(?:to|from|by)\b[^.;]{0,15}?\d|\b(?:up|upward|down|higher|lower)\b)", re.IGNORECASE),
    # making the BMS stop seeing a reading
    re.compile(r"\b(?:ignor\w*|disregard\w*)\b[^.;]{0,20}?\b(?:alarms?|points?|tags?|[a-z]{2}-temp-\d+)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:sensors?|points?|tags?|alarms?|[a-z]{2}-temp-\d+)\b[^.;]{0,15}?"
               r"\b(?:offline|off-line|out\s+of\s+scan)\b", re.IGNORECASE),
    re.compile(r"\b(?:bms|scada|controller)\b[^.;]{0,30}?\b(?:ignor\w*|disregard\w*)\b", re.IGNORECASE),
    re.compile(r"\b(?:offline|off-line|out\s+of\s+scan)\b[^.;]{0,10}?\b(?:in|on|from)\s+(?:the\s+)?"
               r"(?:bms|scada)\b", re.IGNORECASE),
    # faking a reading: "an offset so it reads normal", "remap it to a fixed value"
    re.compile(r"\boffset\b[^.;]{0,40}?\bso\b", re.IGNORECASE),
    re.compile(r"\bso\s+(?:it|they)\s+reads?\s+(?:normal|ok|okay|fine|right|good)\b", re.IGNORECASE),
    re.compile(r"\b(?:fixed|constant|hard-?coded?)\s+(?:value|reading|number)\b", re.IGNORECASE),
    # forcing outputs: "force the damper open in the BMS"
    re.compile(r"\bforc(?:e|es|ed|ing)\b[^.;]{0,30}?\b(?:open|closed|on|off|outputs?|points?|relays?|"
               r"dampers?|valves?|contactors?|\d+\s*(?:%|percent))\b", re.IGNORECASE),
    # running past a protection, or in hand and leaving it
    re.compile(r"\bpast\s+the\s+(?:trip|alarm|cut-?\s?out|limit|interlock|protection)\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:hand|manual|override)(?:\s+mode)?\b[^.;]{0,30}?\b(?:leave|keep|so|past|with)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:in|into)\s+(?:service|maintenance|test)\s+mode\s+so\b", re.IGNORECASE),
    re.compile(r"\b(?:hp|lp|high[- ]pressure|low[- ]pressure)\s+(?:cut-?\s?out|switch)\b[^.;]{0,15}?"
               r"\bin\s+(?:manual|hand|override)\b", re.IGNORECASE),
    # joining contacts and solid links: "short pins 3 and 4", "fit a solid link"
    re.compile(r"\bshort\w*\b[^.;]{0,20}?\b(?:pins?|terminals?|contacts?)\b", re.IGNORECASE),
    re.compile(r"\bsolid\s+link\b", re.IGNORECASE),
    re.compile(r"\b(?:remov\w*|pull\w*|tak(?:e|es|en|ing)\s+out)\b[^.;]{0,20}?\b(?:thermal\s+)?overloads?\b",
               re.IGNORECASE),
    # running a pump dead-headed: "throttle the discharge fully closed and run"
    re.compile(r"\b(?:discharge|outlet|delivery)\b[^.;]{0,30}?\bclos\w*\b[^.;]{0,30}?"
               r"\b(?:and|then|while)\s+(?:run|start|keep)\w*[^.;]{0,20}?\bpump", re.IGNORECASE),
    # stopping detection from doing its job: "stop the leak detection from alerting"
    re.compile(r"\bstop\w*\b[^.;]{0,40}?\b(?:detection|detectors?|alarms?|sensors?|trips?|warnings?)\b"
               r"[^.;]{0,15}?\bfrom\b", re.IGNORECASE),
    # so it stops nagging / ignores: intent
    re.compile(r"\bso\s+(?:that\s+)?(?:it|they)\s+(?:stops?|ignores?)\b[^.;]{0,20}?"
               r"\b(?:nag\w*|beep\w*|going\s+off|alarm\w*|high|trip\w*|call\w*)", re.IGNORECASE),
    # Malay / Indonesian: "matikan penggera" (turn off the alarm), "pintas interlock" (bypass)
    re.compile(r"\b(?:matikan|pintas\w*|lumpuhkan|abaikan|putuskan)\b", re.IGNORECASE),
    # resetting a protection until it stays in: "I keep resetting the compressor trip"
    re.compile(r"\b(?:keep|keeps|kept|keeping)\s+(?:on\s+)?re-?sett?ing\b", re.IGNORECASE),
    re.compile(r"\bre-?set(?:s|ting)?\b[^.;]{0,40}?\b(?:again\s+and\s+again|over\s+and\s+over|"
               r"repeatedly|every\s+time|until\s+it\s+(?:holds|stays|sticks))\b", re.IGNORECASE),
]
# Deny by default: anything that names a protective device or the
# monitoring that feeds one is held for a person to review.
_PROTECTION = re.compile(
    r"\b(?:alarm\w*|trip(?:s|ped|ping)?|cut[- ]?outs?|interlocks?|relays?|overloads?|fuses?|"
    r"breakers?|protect(?:ion|ions|ive)|relief\s+valves?|e-?stops?|emergency\s+stops?|"
    r"(?:pressure|hp|lp|flow|float|level|limit|door|thermal|safety)\s+switch(?:es)?|"
    r"(?:leak|smoke|fire|gas|water)[- ]?detect\w*|set\s?points?|"
    r"(?:high|low|temperature|temp|pressure|current)\s+limits?|safety\s+(?:device|valve|circuit|chain|"
    r"relay|system|interlock)|shut-?(?:down|off)s?|"
    r"contactors?|thermostats?|buzzers?|sounders?|horns?|beacons?|sirens?|probes?|thermistors?|"
    r"vesda|earth[- ]leakage|rcds?|elcbs?|rcbos?|elrs?|maintenance\s+bypass|"
    r"(?:smoke|heat|fire)\s+(?:heads?|detectors?|panels?)|detectors?|fire\s+panels?|warnings?|"
    r"thresholds?|cut-?\s?ins?|set-?\s?pts?|offsets?|fixed\s+values?|float\s+voltage|"
    r"ignor\w*|disregard\w*|offline|off-line|out\s+of\s+(?:circuit|scan|service)|"
    r"in\s+(?:hand|manual|override)|(?:service|test)\s+mode|"
    r"overrid\w*|overide\w*|by[- ]?pass\w*|inhibit\w*|suppress\w*|latch\w*|unwir\w*|forc(?:e|es|ed|ing)|"
    r"energi[sz]ed|live\s+(?:work\w*|cells?|jars?|strings?|bus)|un-?isolated|without\s+isolat\w*|"
    r"no\s+need\s+to\s+isolate|still\s+on\s?-?line|"
    r"matikan|pintas\w*|penggera|lumpuhkan|abaikan|"
    r"leak\s+ropes?|reed\s+switch(?:es)?|reeds?|flow\s+sensors?|float\w*|magnets?|"
    r"terminal\s+\d+|(?:hand|manual|override|bypass)\s+mode|pins?\s+together|"
    r"(?:reset|test|override|mute|silence)\s+(?:buttons?|switch(?:es)?|keys?)|"
    r"(?:lift\w*|unplug\w*|disconnect\w*|clip\w*)\s+(?:the\s+|a\s+)?(?:\w+\s+){0,2}?(?:wire|lead|cable|plug)s?|"
    # taking something out of monitoring (calling "the BMS vendor" is not)
    r"(?:off|out\s+of|from)\s+(?:the\s+)?(?:bms|scada|monitoring))\b",
    re.IGNORECASE,
)
# Instructions that start like a prohibition but keep a protection
# defeated or skip isolation ("Do not reinstate the trip until...",
# "Never isolate the string before..."): checked on the whole text, since
# the clause logic would otherwise read them as safe prohibitions.
_ALWAYS = [p for p in _INSTRUCTION if p.pattern.startswith(r"\b(?:don'?t|do\s+not")]
_SENTENCES = re.compile(r"[.;!?]")
# A clause boundary: a comma or colon, or a contrast that starts a new
# instruction ("..., just bypass it", "... but then silence it").
_CLAUSES = re.compile(r"[,:]|\b(?:but|then|instead|rather)\b", re.IGNORECASE)
_PROHIBITION = re.compile(
    r"^\s*(?:(?:you|i|we)\s+)?(?:never|don'?t|do\s+not|must\s+not|mustn'?t|should\s+never|"
    r"should\s+not|shouldn'?t|not\s+to)\b(?!\s+mind)",
    re.IGNORECASE,
)
_CONTINUES = re.compile(r"^\s*(?:or|nor|and)\b", re.IGNORECASE)
_NEW_INSTRUCTION = re.compile(r"^\s*just\b", re.IGNORECASE)


def _open_clauses(text: str):
    """Yield the parts of ``text`` that are not said as a prohibition: each
    such clause, plus each whole sentence that contains no prohibition (so
    a device and its verb in different clauses are judged together)."""
    for sentence in _SENTENCES.split(text or ""):
        clauses = _CLAUSES.split(sentence)
        if not any(_PROHIBITION.match(c) for c in clauses):
            yield sentence
        prohibited = False
        for clause in clauses:
            if _PROHIBITION.match(clause):
                prohibited = True
            elif not (prohibited and _CONTINUES.match(clause)) or _NEW_INSTRUCTION.match(clause):
                prohibited = False
            if not prohibited:
                yield clause


# Hidden characters and look-alike letters must not split or disguise a
# word: "byp\u200bass", "b\u0443\u0440ass" (Cyrillic) are read as "bypass".
_CONFUSABLES = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y",
    "\u0445": "x", "\u043a": "k", "\u043c": "m", "\u0442": "t", "\u043d": "h", "\u0432": "b",
    "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u0410": "A", "\u0415": "E", "\u041e": "O",
    "\u0420": "P", "\u0421": "C", "\u0423": "Y", "\u0425": "X", "\u041a": "K", "\u041c": "M",
    "\u0422": "T", "\u041d": "H", "\u0412": "B", "\u03bf": "o", "\u03b1": "a", "\u03b5": "e",
})


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_CONFUSABLES)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def unreadable(text: str) -> bool:
    """True if the screen cannot read the text: letters outside the Latin
    alphabet (another script, or look-alikes it has no mapping for). Such a
    line is held for a person's review, never trusted for passing."""
    return any(ch.isalpha() and not ("a" <= ch.lower() <= "z") for ch in _norm(text))


_FUSE_SWAP = re.compile(r"(\d+(?:\.\d+)?)\s*a\b[^.;]{0,15}?\b(?:fuses?|breakers?|mcbs?)\b[^.;]{0,30}?"
                        r"\b(\d+(?:\.\d+)?)\s*a\b", re.IGNORECASE)


def _uprates_protection(text: str) -> bool:
    """A fuse or breaker swapped for a higher rating: "the 400 A fuse for a 630 A one"."""
    return any(float(m.group(2)) > float(m.group(1)) for m in _FUSE_SWAP.finditer(text))


def defeats_safety(text: str) -> bool:
    """True if any clause of the text instructs someone to defeat a
    protective device. A clause that is a prohibition is fine, and so is
    one continuing it ("never bypass the trip or silence the alarm")."""
    text = _norm(text)
    return (any(p.search(part) for part in _open_clauses(text) for p in _INSTRUCTION)
            or any(p.search(text) for p in _ALWAYS) or _uprates_protection(text))


def touches_protection(text: str) -> bool:
    """True if the text names a protective device or its monitoring outside
    a prohibition. Such knowledge needs an explicit safety review."""
    text = _norm(text)
    return unreadable(text) or any(_PROTECTION.search(part) for part in _open_clauses(text))


def said_as_prohibition(line: str, answer: str) -> bool:
    """True if the expert said ``line`` as something never to do: the line
    is itself a prohibition, or the words right before it in the answer
    are ("Never just tighten the base bolts" stored as "just tighten...")."""
    if _PROHIBITION.match(line):
        return True
    low_answer, low_line = " ".join(answer.lower().split()), " ".join(line.lower().split())
    at = low_answer.find(low_line)
    # "Don't go swapping sensors" stored as "swapping sensors": up to three
    # words may sit between the prohibition and the line.
    return at > 0 and bool(re.search(r"\b(?:never|don'?t|do\s+not|must\s+not)(?:\s+[\w']+){0,3}\s*$",
                                     low_answer[:at]))

