"""Judge 7 capture fixes: unused answers are shown, a line the expert said in
another answer can be re-entered as its own item, and a negation in one
sentence no longer denies a cause named in the next."""
from fastapi.testclient import TestClient

from technical_services_pill import capture
from technical_services_pill.app import app


def test_negation_does_not_cross_a_sentence_break():
    # "does not leak" is about the seal, not the cavitation in the next sentence.
    assert not capture._rules_out("The pump does not leak. That's cavitation.", "cavitation")
    assert not capture._rules_out("It’s not a seal. That’s cavitation.", "cavitation")


def test_negation_within_the_same_clause_still_denies():
    assert capture._rules_out("It is not cavitation, check the seal.", "cavitation")


def test_expert_answers_skip_interviewer_and_keep_follow_on_paragraphs():
    answers = capture._expert_answers(capture.SAMPLE_INTERVIEW)
    assert answers and not any(a.lower().startswith("interviewer") for a in answers)
    # The paragraph after a blank line belongs to the same expert answer.
    assert any("calibration sticker" in a for a in answers)


def test_answer_with_no_kept_heuristic_is_reported():
    transcript = (
        "Senior technician: If the bus has gone quiet, check the controller first and call the vendor "
        "before touching the sensor wiring.\n\n"
        "Senior technician: Jumper the alarm circuit so the batteries keep charging while you work.\n"
    )
    first_only = [{"evidence_quote": "If the bus has gone quiet, check the controller first and call the vendor "
                                     "before touching the sensor wiring."}]
    unused = capture._unused_answers(transcript, first_only)
    assert len(unused) == 1
    assert "Jumper the alarm" in unused[0]["excerpt"]
    assert "no knowledge was drafted" in unused[0]["reason"]


def test_short_answers_are_not_reported_as_missed():
    transcript = "Senior technician: Yes.\n"
    assert capture._unused_answers(transcript, []) == []


def test_draft_response_reports_answers_the_draft_passed_over(monkeypatch):
    quote = ("If every tag on the bus has gone quiet at once, it's almost never the sensor. "
             "That's the controller or the bus.")
    heuristic = {"symptom_pattern": "every tag on the bus has gone quiet at once",
                 "likely_cause": "communication_bus_controller_failure",
                 "checks": [], "do_not": [], "escalate_when": [], "evidence_quote": quote}
    monkeypatch.setattr(capture.llm, "complete_json", lambda *a, **k: {"heuristics": [heuristic]})
    r = TestClient(app).post("/capture/draft", params={"user": "steward1"},
                             json={"asset_type": "CRAH", "transcript": capture.SAMPLE_INTERVIEW})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["heuristics"]) == 1
    # The chiller and pump answers have no knowledge drafted from them, so they are reported.
    excerpts = " ".join(u["excerpt"] for u in body["unused_answers"])
    assert "refrigerant" in excerpts and "axial vibration" in excerpts
    assert "calibration sticker" not in excerpts  # that paragraph is part of the CRAH answer
