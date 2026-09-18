"""ai/client.py over the provider's event stream: what reaches the chat and how a failure is named."""
import json

import pytest
import requests

from ai import client


class _Response:
    def __init__(self, status=200, lines=(), body=None, headers=None, raise_after=None):
        self.status_code = status
        self._lines = list(lines)
        self._body = body or {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)
        self._raise_after = raise_after
        self.closed = False

    def iter_lines(self):
        for line in self._lines:
            yield line
        if self._raise_after is not None:
            raise self._raise_after

    def json(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True


def _data(event):
    return b"data: " + json.dumps(event, ensure_ascii=False).encode("utf-8")


def _stream(monkeypatch, response):
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return response

    monkeypatch.setattr(client.requests, "post", post)
    logged = []
    monkeypatch.setattr(client, "_log", logged.append)
    return seen, logged


def _call(**extra):
    return list(client.ask_stream(system="s", input_text="i", context=[], model="m", timeout_s=600, **extra))


def test_tool_events_arrive_before_the_result_and_the_rest_is_not_passed_on(monkeypatch):
    result = {"type": "result", "is_error": False, "text": "", "session_id": "s1",
              "structured_output": {"blocks": [{"kind": "text", "text": "Campañas: 3"}]}, "tool_calls": ["x"]}
    seen, logged = _stream(monkeypatch, _Response(lines=[
        b"", _data({"type": "init", "session_id": "s1"}), _data({"type": "delta", "text": "Cam"}),
        _data({"type": "tool", "name": "mcp__datadive__list_niches"}), b": keepalive", _data(result)]))

    events = _call(output_schema={"type": "object"})

    assert events == [{"type": "tool", "name": "mcp__datadive__list_niches"}, result]
    assert seen["url"].endswith("/v1/answer/stream") and seen["stream"] is True
    assert seen["json"]["output_schema"] == {"type": "object"}
    assert len(logged) == 1 and logged[0]["stream"] is True and logged[0]["status"] == 200


def test_accents_survive_the_stream(monkeypatch):
    _stream(monkeypatch, _Response(lines=[_data({"type": "result", "is_error": False,
                                                 "text": "Campañas sin órdenes"})]))
    assert _call()[-1]["text"] == "Campañas sin órdenes"


def test_a_refused_request_raises_before_any_event(monkeypatch):
    _stream(monkeypatch, _Response(status=429, body={"detail": "busy"}, headers={"Retry-After": "15"}))
    with pytest.raises(client.QuotaExceeded) as error:
        _call()
    assert error.value.retry_after == 15


def test_a_503_names_the_subsystem_like_ask_does(monkeypatch):
    _stream(monkeypatch, _Response(status=503, body={"detail": "could not open the Amazon Ads MCP session: x"}))
    with pytest.raises(client.ProviderDown) as error:
        _call()
    assert "Amazon Ads" in str(error.value)


@pytest.mark.parametrize("kind, error_type, words", [
    ("quota", client.QuotaExceeded, "Cuota"),
    ("auth", client.ProviderDown, "autenticado con Claude"),
    ("ads_unavailable", client.ProviderDown, "Amazon Ads"),
    ("upstream", client.UpstreamError, "no pudo terminar"),
    ("timeout", client.UpstreamError, "timeout after 600s"),
])
def test_a_result_that_reports_an_error_raises_it(monkeypatch, kind, error_type, words):
    detail = "timeout after 600s" if kind == "timeout" else "could not open the Amazon Ads MCP session"
    _stream(monkeypatch, _Response(lines=[_data({"type": "tool", "name": "t"}), _data(
        {"type": "result", "is_error": True, "error": detail, "error_kind": kind})]))
    with pytest.raises(error_type) as error:
        _call()
    assert words in str(error.value)


def test_a_stream_that_ends_without_a_result_is_an_error_not_an_empty_answer(monkeypatch):
    _stream(monkeypatch, _Response(lines=[_data({"type": "tool", "name": "t"})]))
    with pytest.raises(client.UpstreamError):
        _call()


def test_an_unreadable_event_is_an_error_the_chat_can_show_and_it_is_logged(monkeypatch):
    _, logged = _stream(monkeypatch, _Response(lines=[_data({"type": "tool", "name": "t"}), b'data: {"type": "res']))
    with pytest.raises(client.UpstreamError) as error:
        _call()
    assert "ilegible" in str(error.value)
    assert logged[-1]["status"] == "stream_error" and logged[-1]["stream"] is True


def test_an_unreachable_provider_says_so_and_the_log_says_it_was_a_stream(monkeypatch):
    def refused(url, **kwargs):
        raise requests.exceptions.ConnectionError("connection refused")
    monkeypatch.setattr(client.requests, "post", refused)
    logged = []
    monkeypatch.setattr(client, "_log", logged.append)
    with pytest.raises(client.ProviderDown) as error:
        _call()
    assert "No se pudo contactar al AI provider" in str(error.value)
    assert logged[0]["status"] == "provider_down" and logged[0]["stream"] is True


def test_a_silence_mid_stream_is_reported_as_a_timeout_not_as_a_stopped_container(monkeypatch):
    mid_stream = requests.exceptions.ConnectionError("HTTPConnectionPool: Read timed out.")
    _stream(monkeypatch, _Response(lines=[_data({"type": "tool", "name": "t"})], raise_after=mid_stream))
    with pytest.raises(client.ProviderDown) as error:
        _call()
    assert str(error.value) == "El AI provider no respondió en 600 s y el pedido se cortó."


def test_ask_still_posts_to_the_plain_endpoint(monkeypatch):
    seen = {}

    class _Plain:
        status_code = 200
        ok = True
        text = "{}"

        def json(self):
            return {"text": "ok", "session_id": "s1"}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return _Plain()

    monkeypatch.setattr(client.requests, "post", post)
    monkeypatch.setattr(client, "_log", lambda record: None)
    assert client.ask(system="s", input_text="i", context=[], model="m")["text"] == "ok"
    assert seen["url"].endswith("/v1/answer") and "stream" not in seen


def test_whether_each_tool_call_worked_reaches_the_chat_too(monkeypatch):
    result = {"type": "result", "is_error": False, "text": "", "session_id": "s1", "tool_calls": ["x"],
              "failed_tools": ["x"]}
    _stream(monkeypatch, _Response(lines=[
        _data({"type": "tool", "name": "x"}), _data({"type": "tool_result", "name": "x", "ok": False}),
        _data(result)]))

    assert _call() == [{"type": "tool", "name": "x"}, {"type": "tool_result", "name": "x", "ok": False}, result]
