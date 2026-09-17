"""The provider call an agent makes for a payload, and the two fingerprints that identify it.

No thread pool, no chat skills and no Streamlit: the analysis worker builds calls here too.

- input_digest: what the model reads (input text and documents). Same data, same digest.
- agent_version: how it reads it (prompt, shared chat rules, output schema, model, effort, turns).
"""
from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path

AGENTS_DIR = Path(__file__).parent / "agents"
_CHAT_RULES_PATH = AGENTS_DIR / "_shared" / "chat.md"
CHAT_RULES = _CHAT_RULES_PATH.read_text(encoding="utf-8") if _CHAT_RULES_PATH.exists() else ""

_agents: dict[str, dict] = {}


@dataclass(frozen=True)
class AgentCall:
    slug: str
    call: dict
    input_digest: str
    agent_version: str

    @property
    def model(self) -> str:
        return self.call["model"]


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Flat `key: value` frontmatter between --- markers; body untouched."""
    if not text.startswith("---"):
        return {}, text
    head, sep, body = text[3:].partition("\n---")
    if not sep:
        return {}, text
    meta = {}
    for line in head.strip().splitlines():
        key, colon, value = line.partition(":")
        if colon:
            meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def agent(slug: str) -> dict:
    if slug not in _agents:
        prompt_path = AGENTS_DIR / slug / "prompt.md"
        meta, body = parse_front_matter(prompt_path.read_text(encoding="utf-8"))
        module_path = "ai.agents." + slug.replace("/", ".") + ".context"
        _agents[slug] = {"meta": meta, "system": body, "context": importlib.import_module(module_path)}
    return _agents[slug]


def system_prompt(slug: str) -> str:
    # Same system prefix on analysis and chat turns keeps the provider-side prompt cache warm.
    return agent(slug)["system"] + ("\n\n" + CHAT_RULES if CHAT_RULES else "")


def build_agent_call(slug: str, data) -> AgentCall:
    spec = agent(slug)
    input_text, docs, schema = spec["context"].build_context(data)
    meta = spec["meta"]
    model = meta.get("model", "opus")
    effort = meta.get("effort") or None
    system = system_prompt(slug)
    # Structured output is emitted through an internal tool call, which costs turns beyond the answer.
    max_turns = 4 if schema else 1
    call = dict(system=system, input_text=input_text, context=docs, model=model, effort=effort,
                output_schema=schema, max_turns=max_turns, timeout_s=int(meta.get("timeout_s", 3600)), tag=slug)
    return AgentCall(
        slug=slug,
        call=call,
        input_digest=_sha256([slug, input_text, docs]),
        agent_version=_sha256([slug, system, schema, model, effort, max_turns]),
    )


def _sha256(value) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
