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

# Verbs that defeat a protection, in any inflection (bypassed, jumpering...).
_ACTION = (
    r"by-?pass(?:es|ed|ing)?|overrid(?:e|es|den|ing)|overrode|defeat(?:s|ed|ing)?|"
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
    r"hp\s+(?:switch|cut-?out)|lp\s+(?:switch|cut-?out)|protections?|cut-?outs?|relief\s+valves?|"
    r"limit\s+switch(?:es)?|overloads?(?:\s+relays?)?|"
    r"(?:high|low)-?\s?temp(?:erature)?\s+(?:cut-?out|trip|limit|switch|interlock|protection|alarm)|"
    r"(?:leak|smoke|fire|gas|water)[- ]?detect(?:ion|ors?)?(?:\s+(?:fuse|circuit|system))?|"
    r"e-?stops?|emergency\s+stops?|"
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
               rf"turn(?:s|ed|ing)?|switch(?:es|ed|ing)?|knock(?:s|ed|ing)?|tak(?:e|es|en|ing)|took)"
               rf"\b[^.;]{{0,30}}?\b(?:{_DEVICE})\b[^.;]{{0,20}}?\b(?:out|off|down|over)\b", re.IGNORECASE),
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
    # resetting a protection until it stays in: "I keep resetting the compressor trip"
    re.compile(r"\b(?:keep|keeps|kept|keeping)\s+(?:on\s+)?re-?sett?ing\b", re.IGNORECASE),
    re.compile(r"\bre-?set(?:s|ting)?\b[^.;]{0,40}?\b(?:again\s+and\s+again|over\s+and\s+over|"
               r"repeatedly|every\s+time|until\s+it\s+(?:holds|stays|sticks))\b", re.IGNORECASE),
]
# Deny by default: anything that names a protective device or the
# monitoring that feeds one is held for a person to review.
_PROTECTION = re.compile(
    r"\b(?:alarm\w*|trip(?:s|ped|ping)?|cut-?outs?|interlocks?|relays?|overloads?|fuses?|"
    r"breakers?|protect(?:ion|ions|ive)|relief\s+valves?|e-?stops?|emergency\s+stops?|"
    r"(?:pressure|hp|lp|flow|float|level|limit|door|thermal|safety)\s+switch(?:es)?|"
    r"(?:leak|smoke|fire|gas|water)[- ]?detect\w*|set\s?points?|"
    r"(?:high|low|temperature|temp|pressure|current)\s+limits?|safety\s+(?:device|valve|circuit|chain|"
    r"relay|system|interlock)|shut-?(?:down|off)s?|"
    r"contactors?|thermostats?|buzzers?|sounders?|horns?|beacons?|sirens?|probes?|thermistors?|"
    r"leak\s+ropes?|reed\s+switch(?:es)?|reeds?|flow\s+sensors?|float\w*|magnets?|"
    r"terminal\s+\d+|(?:hand|manual|override|bypass)\s+mode|"
    r"(?:lift\w*|unplug\w*|disconnect\w*|clip\w*)\s+(?:the\s+|a\s+)?(?:\w+\s+){0,2}?(?:wire|lead|cable|plug)s?|"
    # taking something out of monitoring (calling "the BMS vendor" is not)
    r"(?:off|out\s+of|from)\s+(?:the\s+)?(?:bms|scada|monitoring))\b",
    re.IGNORECASE,
)
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


def defeats_safety(text: str) -> bool:
    """True if any clause of the text instructs someone to defeat a
    protective device. A clause that is a prohibition is fine, and so is
    one continuing it ("never bypass the trip or silence the alarm")."""
    return any(p.search(part) for part in _open_clauses(text) for p in _INSTRUCTION)


def touches_protection(text: str) -> bool:
    """True if the text names a protective device or its monitoring outside
    a prohibition. Such knowledge needs an explicit safety review."""
    return any(_PROTECTION.search(part) for part in _open_clauses(text))


def said_as_prohibition(line: str, answer: str) -> bool:
    """True if the expert said ``line`` as something never to do: the line
    is itself a prohibition, or the words right before it in the answer
    are ("Never just tighten the base bolts" stored as "just tighten...")."""
    if _PROHIBITION.match(line):
        return True
    low_answer, low_line = " ".join(answer.lower().split()), " ".join(line.lower().split())
    at = low_answer.find(low_line)
    return at > 0 and bool(re.search(r"(?:never|don'?t|do\s+not|must\s+not)\s*$", low_answer[:at]))
