"""Mock extractor precision: no mis-tagged causes, no under-suppressed denials.

Covers the two behaviours that sentence-wide keyword matching cannot get
right, and that the previous (sentence-scoped) negation fix traded between:

1. Collision mis-tags: one clause can match two causes ("batteries are at end
   of life" must draft `battery_eol`, not a generic sensor failure) -- even
   though "end of life" used to be a sensor keyword too.
2. Under-suppression: a denial in ONE clause must not swallow a real,
   separately-named cause in the sentence ("not the bus, but the thermistor is
   open-circuit" must still draft the sensor heuristic) -- the reason the
   extractor evaluates per clause.
3. Exoneration: "every tag on that bus was reporting fine" rules the bus out
   even with no negation word in the clause.
"""
from __future__ import annotations

from technical_services_pill import llm


def _causes(transcript: str) -> set[str]:
    return {h["likely_cause"] for h in llm._mock_extract(transcript)["heuristics"]}


def test_battery_transcript_does_not_leak_a_sensor_cause():
    """Two causes used to collide on 'end of life'; the domain-specific
    battery cause must be the only thing drafted now."""
    out = _causes(
        "Technician: The UPS batteries are at end of life. They only hold "
        "five minutes of runtime at full load now. I'd replace the string."
    )
    assert out == {"battery_eol"}, out


def test_positive_sentence_with_a_denial_clause_still_drafts_the_cause():
    """'not the bus, but the thermistor is open-circuit' names a real cause in
    one clause and denies one in another -- both halves must be respected."""
    out = _causes(
        "Technician: Not the bus, not the controller. The thermistor is "
        "open-circuit, we replaced it and the reading came straight back."
    )
    assert out == {"sensor_hardware_failure"}, out


def test_exoneration_rules_a_cause_out_without_a_negation_word():
    """'reporting fine' denies the bus without a single 'not' -- presence of
    the keyword must not equal the fault, as long as the exoneration shares
    the clause."""
    out = _causes(
        "Technician: Every one of the two hundred tags on that bus was "
        "reporting fine, with no alarms outstanding."
    )
    assert "comm_bus_failure" not in out, out
    assert out == set(), out


def test_exonerated_terminal_does_not_draft_loose_wiring():
    """'the terminal was seated properly' exonerates the terminal even though
    the paragraph also mentions wiring while denying it."""
    out = _causes(
        "Technician: The wiring was not loose either, we pulled the terminal "
        "and it was seated properly, no moisture under the boot."
    )
    assert "loose_wiring" not in out, out


def test_keyword_sets_are_disjoint_across_causes():
    """A keyword string must belong to exactly one cause, so no sentence can
    name two causes from the same word (the 'end of life' collision)."""
    seen: dict[str, str] = {}
    for cause, keywords in llm._CAUSE_KEYWORDS:
        for kw in keywords:
            assert kw not in seen, (
                f"keyword {kw!r} is owned by both {seen[kw]!r} and {cause!r}"
            )
            seen[kw] = cause


def test_open_circuit_sensor_elsewhere_still_drafts_one_sensor_cause():
    out = _causes(
        "Technician: The probe was stuck reading and held a flat line for "
        "six hours, replaced it and the value settled immediately."
    )
    assert out == {"sensor_hardware_failure"}, out