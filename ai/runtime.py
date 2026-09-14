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
from core import chat_skills

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


AMAZON_ADS_TOOLS = "amazon_ads"

# Tool calls one chat turn may chain before the provider gives up. Hitting it is
# a 502 and the AM loses the whole answer, text included — which is what
# happened to "dame todas las campañas activas" and "listame los portfolios" in
# the end-to-end run at 8: since the chat started returning complete listings,
# a paginated read plus a report plus the account lookup no longer fits.
# 20 is bounded by the 600s timeout below, not by this number.
_MAX_TOOL_TURNS = 20


def agent_tools(slug: str) -> list:
    """Provider tool profiles declared in the agent's frontmatter (`tools:`)."""
    meta = _agent(slug)["meta"]
    return [t.strip() for t in str(meta.get("tools") or "").split(",") if t.strip()]


def usable_tools(slug: str, ads_scope: dict | None) -> list:
    """The agent's tool profiles that can actually run in this turn.

    Two things leave a profile out, and both exist so the provider is never sent
    a request it must refuse. Amazon Ads tools need a client account resolved;
    without one the profile is dropped. And a profile the provider has not
    configured is dropped too: it answers 503 for the WHOLE turn, so DataDive
    without its key was taking down a DataDive chat that could still have talked
    about the analysis on screen.

    `available_tools()` returning None means the provider could not be asked. We
    send what we have: the turn is about to fail on its own, with a better
    message than anything we could invent here.
    """
    served = client.available_tools()
    return [t for t in agent_tools(slug)
            if (t != AMAZON_ADS_TOOLS or ads_scope)
            and (served is None or t in served)]


def ask_followup(slug: str, session_id: str | None, question: str,
                 ads_scope: dict | None = None) -> tuple[str, str]:
    """One chat turn. Synchronous.

    session_id=None opens a fresh conversation instead of resuming one, so a
    tool-capable agent can answer before its analysis exists.

    An agent whose prompt frontmatter declares `tools:` gets those provider
    tool profiles on chat turns only — the analysis itself stays deterministic.
    `ads_scope` ({account_id, profile_id, requested_by}) is the client's
    Amazon Ads account the chat is pinned to, when the AM picked one.
    """
    agent = _agent(slug)
    system = agent["system"] + ("\n\n" + _CHAT_RULES if _CHAT_RULES else "")
    tools = usable_tools(slug, ads_scope) or None
    session_id = _session_to_resume(session_id, bool(tools))
    # Uploaded from Sistema, not from the repo. A broken registry costs a skill,
    # never the turn — see core.chat_skills.enabled_payload.
    skills = chat_skills.enabled_payload()
    resp = client.ask(system=system, input_text=question, context=[],
                      model=agent["meta"].get("model", "opus"),
                      effort=agent["meta"].get("effort") or None,
                      session_id=session_id, timeout_s=600,
                      max_turns=_MAX_TOOL_TURNS if tools else 1, tools=tools,
                      ads_scope=ads_scope if tools and AMAZON_ADS_TOOLS in tools else None,
                      skills=skills or None,
                      tag=f"{slug}-chat")
    new_session = resp.get("session_id") or session_id
    if new_session:
        _TOOLED_TURNS[new_session] = bool(tools)
    return resp.get("text", ""), new_session


# session_id -> whether that turn ran with tools. Bounded because a Streamlit
# process holds a handful of chats, not a queue.
_TOOLED_TURNS: dict[str, bool] = {}
_TOOLED_TURNS_MAX = 256


def _session_to_resume(session_id: str | None, has_tools: bool) -> str | None:
    """The session to continue, or None to start fresh.

    A turn that runs without tools answers, correctly, that it cannot do the
    thing. Resuming that same conversation once tools arrive puts the model's
    own refusal in its history, and it follows the thread instead of re-reading
    its toolbox: observed in production on 2026-09-10, where the second turn
    opened with "Sigo sin poder traerlo" while holding all 17 tools.

    So the first tooled turn of a thread starts a new conversation. The AM loses
    nothing they can see — the panel keeps every message — and the model stops
    arguing with a version of itself that was right at the time.
    """
    if not session_id or not has_tools:
        return session_id
    if _TOOLED_TURNS.get(session_id, True):
        return session_id
    _TOOLED_TURNS.pop(session_id, None)
    if len(_TOOLED_TURNS) > _TOOLED_TURNS_MAX:
        _TOOLED_TURNS.clear()
    return None


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
