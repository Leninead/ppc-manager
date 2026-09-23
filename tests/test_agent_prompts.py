"""Contract of the shared reading rules across the AI agents' prompts.

The <lectura> block (how a synthesis must read for a junior AM) is copied
verbatim into every agent prompt because the runtime only appends
_shared/chat.md. This test keeps the three copies identical so the rule
cannot drift silently in one agent, and pins the SQP situation spec that
used to force seven rollup figures into three sentences.
"""
import re
from pathlib import Path

import pytest

_AGENTS = Path("ai/agents")
_SLUGS = ["str", "sqp", "datadive", "bulk_campaigns", "ppc_insights", "funnel"]


def _block(slug: str) -> str:
    text = (_AGENTS / slug / "prompt.md").read_text(encoding="utf-8")
    found = re.findall(r"<lectura>\n(.*?)\n</lectura>", text, flags=re.S)
    assert len(found) == 1, f"{slug}: expected exactly one <lectura> block"
    return found[0]


def test_reading_rules_identical_across_agents():
    blocks = {slug: _block(slug) for slug in _SLUGS}
    assert len(set(blocks.values())) == 1


@pytest.mark.parametrize("slug", _SLUGS)
def test_reading_rules_cover_the_known_jargon(slug):
    block = _block(slug)
    for term in ("shares ponderados", "etapa dominante de fuga", "cobertura",
                 "materialidad", "rollup"):
        assert term in block
    assert "sin cifras" in block and "Slack" in block


def test_every_agent_chat_narrows_an_answer_that_came_only_counted_instead_of_asking_the_am():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "**Si una herramienta te devuelve sólo cuántos son, el recorte lo elegís vos.**" in rules
    assert "siempre dentro de la cuenta y el período que ya están en juego" in rules


def test_a_paged_answer_is_still_listed_not_narrowed():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "Si la respuesta trajo filas, aunque avise que hay más, esta regla no aplica" in rules


def test_sqp_situation_spec_no_longer_enumerates_the_rollup():
    text = (_AGENTS / "sqp" / "prompt.md").read_text(encoding="utf-8")
    spec = next(line for line in text.splitlines()
                if line.startswith("- situation:"))
    assert "ancladas en los shares ponderados" not in spec
    assert "sin cifras" in spec and "exposición" in spec
    exec_spec = next(line for line in text.splitlines()
                     if line.startswith("- executive_summary:"))
    assert "no aplica a la situación" in exec_spec
