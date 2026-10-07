"""Safety screen for expert know-how: G1 applied to knowledge, not only to
recommendations.

The guardrail engine stops the *agent* recommending a BMS setpoint,
interlock or safety change (G1). Expert knowledge is shown to the AOM next
to that recommendation, so the same rule applies to it: an instruction to
defeat a protective device is never stored, and is withheld again when
knowledge is displayed. A prohibition ("never bypass the interlock") is the
opposite of an instruction and is kept.

Text is judged clause by clause, so "Don't wait for the vendor, just
bypass the interlock" is caught (the second clause is an instruction), and
"If it trips twice, never bypass the interlock, call the vendor" is not
(the clause naming the bypass is a prohibition).

This is a pattern screen, so it has limits: it catches the usual ways of
phrasing it (bypass, bridge out, jumper, link out, override, silence, raise
the trip setpoint, in any tense), not every possible wording. Review by a
second steward remains the main control.
"""
from __future__ import annotations

import re

# Verbs that defeat a protection, in any inflection (bypassed, jumpering...).
_ACTION = (
    r"by-?pass(?:es|ed|ing)?|overrid(?:e|es|den|ing)|overrode|defeat(?:s|ed|ing)?|"
    r"disabl(?:e|es|ed|ing)|deactivat(?:e|es|ed|ing)|jumper(?:s|ed|ing)?|"
    r"bridg(?:e|es|ed|ing)(?:\s+(?:it|them))?(?:\s+out)?|link(?:s|ed|ing)?(?:\s+(?:it|them))?\s+out|"
    r"short(?:s|ed|ing)?(?:\s+(?:it|them))?\s+out|wedg(?:e|es|ed|ing)|tap(?:e|es|ed|ing)\s+over|"
    r"ti(?:e|es|ed|ing)\s+(?:down|up|back)|pin(?:s|ned|ning)?\s+(?:open|closed|shut)|"
    r"gag(?:s|ged|ging)?|silenc(?:e|es|ed|ing)|mut(?:e|es|ed|ing)|ignor(?:e|es|ed|ing)|"
    r"(?:switch(?:es|ed|ing)?|turn(?:s|ed|ing)?)\s+off|cheat(?:s|ed|ing)?"
)
# Protective devices. Deliberately narrow: "safety officer", an isolator or
# a lockout are things people should use, not defeat.
_DEVICE = (
    r"interlocks?|alarms?|trips?|trip\s+(?:switch|setting|circuit)|pressure\s+switch(?:es)?|"
    r"hp\s+switch|lp\s+switch|protections?|cut-?outs?|relief\s+valves?|limit\s+switch(?:es)?|"
    r"(?:high|low)-?\s?temp(?:erature)?\s+(?:cut-?out|trip|limit|switch|interlock|protection)|"
    r"e-?stops?|emergency\s+stops?|safety\s+(?:device|interlock|valve|circuit|chain|relay|switch|system)"
)
_INSTRUCTION = [
    # verb ... device: "bridge out the high-temp interlock", "leave the trip bypassed"
    re.compile(rf"\b(?:{_ACTION})\b[^.;]{{0,40}}?\b(?:{_DEVICE})\b", re.IGNORECASE),
    # device ... verb: "keep the pressure switch jumpered"
    re.compile(rf"\b(?:{_DEVICE})\b[^.;]{{0,30}}?\b(?:{_ACTION})\b", re.IGNORECASE),
    # raising a protective limit: "raise the trip setpoint", "bump the HP limit up"
    re.compile(r"\b(?:raise|raising|increase|increasing|bump|bumping|lift|widen)\s+(?:the\s+)?"
               r"(?:[a-z-]+\s+){0,2}?(?:trip\s+point|trip\s+setting|setpoint|set\s+point|cut-?out|"
               r"high\s+limit|pressure\s+limit|temperature\s+limit)\b", re.IGNORECASE),
    # the tools of defeating a protection
    re.compile(r"\b(?:link|jumper|cheater|bridging)\s+(?:wire|lead|cable)s?\b", re.IGNORECASE),
]
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


def defeats_safety(text: str) -> bool:
    """True if any clause of the text instructs someone to defeat a
    protective device. A clause that is a prohibition is fine, and so is
    one continuing it ("never bypass the trip or silence the alarm")."""
    if not text:
        return False
    for sentence in _SENTENCES.split(text):
        clauses = _CLAUSES.split(sentence)
        # No prohibition anywhere: judge the sentence whole, so a device and
        # its verb in different clauses ("the trip keeps going, so jumper
        # it out") are still caught.
        if not any(_PROHIBITION.match(c) for c in clauses) and any(p.search(sentence) for p in _INSTRUCTION):
            return True
        prohibited = False
        for clause in clauses:
            if _PROHIBITION.match(clause):
                prohibited = True
            elif not (prohibited and _CONTINUES.match(clause)) or _NEW_INSTRUCTION.match(clause):
                prohibited = False
            if not prohibited and any(p.search(clause) for p in _INSTRUCTION):
                return True
    return False


def said_as_prohibition(line: str, answer: str) -> bool:
    """True if the expert said ``line`` as something never to do: the line
    is itself a prohibition, or the words right before it in the answer
    are ("Never just tighten the base bolts" stored as "just tighten...")."""
    if _PROHIBITION.match(line):
        return True
    low_answer, low_line = " ".join(answer.lower().split()), " ".join(line.lower().split())
    at = low_answer.find(low_line)
    return at > 0 and bool(re.search(r"(?:never|don'?t|do\s+not|must\s+not)\s*$", low_answer[:at]))
