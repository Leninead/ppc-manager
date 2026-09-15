"""The provider call an agent makes (ai/agent_call.py) and its two fingerprints."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai import agent_call, runtime
from ai.agents.str.context import StrData


def _data(**overrides):
    values = dict(cliente="no declarado", brand_terms=[], target_acos=30.0, precio=30.0, cvr=10.0, umbral_clicks=20,
                  umbral_spend=15.0, harvest_target_acos=30.0, harvest_precio=30.0, kpis={"Total Spend": "$10.00"},
                  campanas=[], negativos=[{"Search Term": "toy box", "Clicks": 40, "Impressions": 900}],
                  harvest=[], idioma="es", cost_detected=True, currency_code="USD")
    values.update(overrides)
    return StrData(**values)


def test_input_digest_follows_what_the_model_reads():
    base = agent_call.build_agent_call("str", _data())

    assert agent_call.build_agent_call("str", _data()).input_digest == base.input_digest
    assert agent_call.build_agent_call("str", _data(idioma="en")).input_digest != base.input_digest
    assert agent_call.build_agent_call("str", _data(umbral_clicks=21)).input_digest != base.input_digest


def test_input_digest_is_the_same_on_windows_and_linux(monkeypatch):
    data = _data(campanas=[{"Campaign": "LK", "Spend": 10.0}, {"Campaign": "LK 2", "Spend": 5.0}])
    calls = {}
    for system, separator in (("linux", "\n"), ("windows", "\r\n")):
        monkeypatch.setattr(os, "linesep", separator)
        calls[system] = agent_call.build_agent_call("str", data)

    assert calls["windows"].input_digest == calls["linux"].input_digest
    assert not any("\r" in document["content"] for document in calls["windows"].call["context"])


def test_agent_version_follows_how_the_model_reads_it_not_the_data(monkeypatch):
    base = agent_call.build_agent_call("str", _data())
    assert agent_call.build_agent_call("str", _data(idioma="en")).agent_version == base.agent_version

    spec = dict(agent_call.agent("str"))
    monkeypatch.setitem(agent_call._agents, "str", {**spec, "meta": {**spec["meta"], "model": "claude-sonnet-5"}})
    changed_model = agent_call.build_agent_call("str", _data())

    assert changed_model.agent_version != base.agent_version
    assert changed_model.input_digest == base.input_digest


def test_the_runtime_keeps_its_registry_digest_and_its_call():
    call, digest, schema = runtime._build("str", _data())
    built = agent_call.build_agent_call("str", _data())

    assert call == built.call
    assert schema == built.call["output_schema"]
    assert digest == runtime._digest("str", call["system"], call["input_text"], call["context"], call["model"],
                                     call["effort"])


def test_the_analysis_worker_imports_without_streamlit_or_the_chat_runtime():
    # A fresh interpreter: this test session already imported Streamlit through other tests.
    probe = ("import sys; sys.modules['streamlit'] = None; import core.ai_analysis.worker; "
             "leaked = [m for m in sys.modules if m.startswith(('ai.runtime', 'core.chat_skills'))]; "
             "print('leaked', leaked)")
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                               cwd=Path(__file__).resolve().parents[1])

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "leaked []"


@pytest.mark.parametrize("text, expected", [
    ("---\nmodel: opus\n---\nbody", ({"model": "opus"}, "body")),
    ("no frontmatter", ({}, "no frontmatter")),
])
def test_front_matter_is_parsed_flat(text, expected):
    assert agent_call.parse_front_matter(text) == expected
