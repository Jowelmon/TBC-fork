"""ADP v2 SSE client, exercised against a simulated event stream."""
import json

import httpx
import pytest

from technical_services_pill import capture, llm

GOOD_JSON = json.dumps({"heuristics": [{
    "symptom_pattern": "approach temperature creeping up",
    "likely_cause": "condenser_fouling",
    "checks": ["look at the condenser first"], "do_not": [], "escalate_when": [],
    "evidence_quote": "A fouled condenser is the usual story there",
}]})


def _sse(events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events).encode()


def _transport(events, status=200, seen=None):
    def handler(request: httpx.Request):
        if seen is not None:
            seen["body"] = json.loads(request.content)
            seen["url"] = str(request.url)
        return httpx.Response(status, content=_sse(events) if status == 200 else b"bad key",
                              headers={"Content-Type": "text/event-stream"})
    return httpx.MockTransport(handler)


def _stream(reply_text, thought="Let me think about the condenser..."):
    half = len(reply_text) // 2
    return [
        {"Type": "response.created", "Response": {}},
        {"Type": "message.added", "Message": {"MessageId": "t1", "Type": "thought"}},
        {"Type": "text.delta", "MessageId": "t1", "ContentIndex": 0, "Text": thought},
        {"Type": "message.added", "Message": {"MessageId": "r1", "Type": "reply"}},
        {"Type": "text.delta", "MessageId": "r1", "ContentIndex": 0, "Text": reply_text[:half]},
        {"Type": "text.delta", "MessageId": "r1", "ContentIndex": 0, "Text": reply_text[half:]},
        {"Type": "message.done", "Message": {"MessageId": "r1", "Type": "reply"}},
        {"Type": "response.completed", "Response": {}},
    ]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("ADP_APP_KEY", "test-key-not-real")


def test_reply_deltas_are_joined_and_thoughts_dropped():
    seen = {}
    out = llm._call_adp("SYS", "USER", transport=_transport(_stream(GOOD_JSON), seen=seen))
    assert out == GOOD_JSON
    assert seen["url"] == llm.ADP_DEFAULT_ENDPOINT
    body = seen["body"]
    assert body["AppKey"] == "test-key-not-real" and body["Stream"] == "enable"
    assert body["Contents"][0]["Text"].startswith("SYS")


def test_http_error_raises():
    with pytest.raises(llm.LLMError, match="HTTP 401"):
        llm._call_adp("S", "U", transport=_transport([], status=401))


def test_error_event_raises():
    with pytest.raises(llm.LLMError, match="error event"):
        llm._call_adp("S", "U", transport=_transport([{"Type": "error", "Error": {"Code": 460}}]))


def test_empty_reply_raises():
    with pytest.raises(llm.LLMError, match="empty"):
        llm._call_adp("S", "U", transport=_transport([{"Type": "response.completed", "Response": {}}]))


def test_full_capture_path_through_adp(monkeypatch):
    """Model output with preamble still parses, and still faces the grounding check."""
    monkeypatch.setenv("TBC_LLM_PROVIDER", "adp")
    wrapped = "Here is the extraction:\n```json\n" + GOOD_JSON + "\n```"
    real = llm._call_adp
    monkeypatch.setattr(llm, "_call_adp",
                        lambda s, u: real(s, u, transport=_transport(_stream(wrapped))))
    draft = capture.draft_from_transcript(capture.SAMPLE_INTERVIEW, "Chiller")
    assert draft["provider"] == "adp"
    assert [h["likely_cause"] for h in draft["heuristics"]] == ["condenser_fouling"]
