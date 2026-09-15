"""How ai/client.py names a provider failure, so the message sends people to the right place."""
import pytest
import requests

from ai import client


def _ask():
    return client.ask(system="s", input_text="i", context=[], model="m", timeout_s=3660)


def test_a_provider_that_took_too_long_is_not_reported_as_a_stopped_container(monkeypatch):
    def slow(*args, **kwargs):
        raise requests.exceptions.ReadTimeout("read timed out")
    monkeypatch.setattr(client.requests, "post", slow)

    with pytest.raises(client.ProviderDown) as error:
        _ask()

    assert str(error.value) == "El AI provider no respondió en 3660 s y el pedido se cortó."


def test_an_unreachable_provider_still_says_so(monkeypatch):
    def refused(*args, **kwargs):
        raise requests.exceptions.ConnectionError("connection refused")
    monkeypatch.setattr(client.requests, "post", refused)

    with pytest.raises(client.ProviderDown) as error:
        _ask()

    assert "No se pudo contactar al AI provider" in str(error.value)
