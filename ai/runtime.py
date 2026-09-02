"""analyze(slug, data) -> Analysis. Background execution + idempotent registry.

The call never runs in the Streamlit script thread: a module-level pool
survives reruns, and identical data (same digest) is never paid twice —
two AMs uploading the same file share one run. Failures are terminal:
only a human retry() relaunches.
"""
import hashlib
import importlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ai import client

_AGENTS_DIR = Path(__file__).parent / "agents"
_TTL_S = 24 * 3600
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ai")
_registry: dict[tuple[str, str], "Analysis"] = {}
_lock = threading.Lock()
_agents: dict[str, dict] = {}


class Analysis:
    def __init__(self, slug: str, digest: str):
        self.slug = slug
        self.digest = digest
        self.state = "running"
        self.result: dict | None = None
        self.error: str | None = None
        self.session_id: str | None = None
        self.request_id: str | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None
        self._call: dict = {}

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def done(self) -> bool:
        return self.state == "done"

    @property
    def failed(self) -> bool:
        return self.state == "failed"

    @property
    def elapsed(self) -> int:
        return int((self.finished_at or time.time()) - self.started_at)

    def retry(self) -> None:
        """Human-only relaunch of a failed run, same data."""
        with _lock:  # two near-simultaneous clicks must launch ONE run
            if not self.failed:
                return
            self.state = "running"
            self.error = None
            self.started_at = time.time()
            self.finished_at = None
        _pool.submit(_run, self)


def _parse_front_matter(text: str) -> tuple[dict, str]:
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


def _agent(slug: str) -> dict:
    if slug not in _agents:
        prompt_path = _AGENTS_DIR / slug / "prompt.md"
        meta, body = _parse_front_matter(prompt_path.read_text(encoding="utf-8"))
        module_path = "ai.agents." + slug.replace("/", ".") + ".context"
        ctx = importlib.import_module(module_path)
        _agents[slug] = {"meta": meta, "system": body, "context": ctx}
    return _agents[slug]


# Fail fast at import: a broken agent should stop the app at startup,
# not silently at first use.
for _p in sorted(_AGENTS_DIR.iterdir()):
    if _p.is_dir() and (_p / "prompt.md").exists():
        _agent(_p.name)


def _digest(slug: str, system: str, input_text: str, docs: list,
            model: str, effort: str | None) -> str:
    blob = json.dumps([slug, system, input_text, docs, model, effort],
                      ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _build(slug: str, data) -> tuple[dict, str, dict]:
    agent = _agent(slug)
    input_text, docs, schema = agent["context"].build_context(data)
    meta = agent["meta"]
    model = meta.get("model", "opus")
    effort = meta.get("effort") or None
    # Same system prefix on analysis and chat turns keeps the provider-side
    # prompt cache warm across the whole thread.
    system = agent["system"] + ("\n\n" + _CHAT_RULES if _CHAT_RULES else "")
    # Structured output is emitted through an internal tool call, which
    # costs extra turns beyond the single answer turn.
    call = dict(system=system, input_text=input_text, context=docs,
                model=model, effort=effort, output_schema=schema,
                max_turns=4 if schema else 1,
                timeout_s=int(meta.get("timeout_s", 900)), tag=slug)
    return call, _digest(slug, system, input_text, docs, model, effort), schema


def peek(slug: str, data) -> "Analysis | None":
    """The Analysis for exactly this data, if it exists. Never starts one."""
    _, digest, _ = _build(slug, data)
    with _lock:
        _evict()
        return _registry.get((slug, digest))


def get(slug: str, digest: str) -> "Analysis | None":
    with _lock:
        _evict()
        return _registry.get((slug, digest))


def analyze(slug: str, data) -> Analysis:
    """Idempotent: returns the existing Analysis for this data, or starts one."""
    call, digest, _ = _build(slug, data)
    key = (slug, digest)
    with _lock:
        _evict()
        found = _registry.get(key)
        if found:
            return found
        analysis = Analysis(slug, digest)
        analysis._call = call
        _registry[key] = analysis
    _pool.submit(_run, analysis)
    return analysis


# Shared chat-format contract, appended to any agent's system on follow-ups
# so every module's chat behaves the same without duplicating the text.
_CHAT_RULES_PATH = _AGENTS_DIR / "_shared" / "chat.md"
_CHAT_RULES = (_CHAT_RULES_PATH.read_text(encoding="utf-8")
               if _CHAT_RULES_PATH.exists() else "")


def agent_tools(slug: str) -> list:
    """Provider tool profiles declared in the agent's frontmatter (`tools:`)."""
    meta = _agent(slug)["meta"]
    return [t.strip() for t in str(meta.get("tools") or "").split(",") if t.strip()]


def ask_followup(slug: str, session_id: str | None,
                 question: str) -> tuple[str, str]:
    """One chat turn. Synchronous.

    session_id=None opens a fresh conversation instead of resuming one, so a
    tool-capable agent can answer before its analysis exists.

    An agent whose prompt frontmatter declares `tools:` gets those provider
    tool profiles on chat turns only — the analysis itself stays deterministic.
    """
    agent = _agent(slug)
    system = agent["system"] + ("\n\n" + _CHAT_RULES if _CHAT_RULES else "")
    tools = agent_tools(slug) or None
    resp = client.ask(system=system, input_text=question, context=[],
                      model=agent["meta"].get("model", "opus"),
                      effort=agent["meta"].get("effort") or None,
                      session_id=session_id, timeout_s=600,
                      max_turns=8 if tools else 1, tools=tools,
                      tag=f"{slug}-chat")
    return resp.get("text", ""), resp.get("session_id") or session_id


def _run(analysis: Analysis) -> None:
    try:
        resp = client.ask(**analysis._call)
        analysis.session_id = resp.get("session_id")
        analysis.request_id = resp.get("request_id")
        analysis.result = resp.get("structured_output")
        if analysis.result is None:
            analysis.error = "La IA no devolvió el formato pactado."
            analysis.state = "failed"
        else:
            analysis.state = "done"
            analysis._call = {}  # docs no longer needed; only retry (failed) needs them
    except client.AIError as e:
        analysis.error = str(e)
        analysis.state = "failed"
    except Exception as e:  # a worker must never die silently
        analysis.error = f"{type(e).__name__}: {e}"
        analysis.state = "failed"
    finally:
        analysis.finished_at = time.time()


def _evict() -> None:
    # Never evict a running Analysis: it would orphan the in-flight run and
    # let a later analyze() double-spend on the same digest.
    cutoff = time.time() - _TTL_S
    stale = [k for k, a in _registry.items()
             if not a.running and (a.finished_at or a.started_at) < cutoff]
    for k in stale:
        del _registry[k]
