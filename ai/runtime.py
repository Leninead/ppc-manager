"""analyze(slug, data) -> Analysis. Background execution + idempotent registry.

The call never runs in the Streamlit script thread: a module-level pool
survives reruns, and identical data (same digest) is never paid twice —
two AMs uploading the same file share one run. Failures are terminal:
only a human retry() relaunches.
"""
import hashlib
import json
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ai import agent_call, client
from core.chat import components as chat_components
from core.chat import skills as chat_skills

_AGENTS_DIR = agent_call.AGENTS_DIR
_TTL_S = 24 * 3600
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ai")
_registry: dict[tuple[str, str], "Analysis"] = {}
_lock = threading.Lock()
_agents: dict[str, dict] = agent_call._agents


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


_parse_front_matter = agent_call.parse_front_matter
_agent = agent_call.agent


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
    built = agent_call.build_agent_call(slug, data)
    call = built.call
    return call, _digest(slug, call["system"], call["input_text"], call["context"], call["model"],
                         call["effort"]), call["output_schema"]


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
_CHAT_RULES = agent_call.CHAT_RULES


AMAZON_ADS_TOOLS = "amazon_ads"

# Tool calls one chat turn may chain before the provider gives up. Hitting it is
# a 502 and the AM loses the whole answer, text included — which is what
# happened to "dame todas las campañas activas" and "listame los portfolios" in
# the end-to-end run at 8: since the chat started returning complete listings,
# a paginated read plus a report plus the account lookup no longer fits.
# 20 is bounded by the agent's timeout_s, not by this number.
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
                 ads_scope: dict | None = None,
                 context_docs: list | None = None,
                 note: str | None = None,
                 thread: list | None = None) -> tuple[str, str]:
    """One chat turn. Synchronous.

    session_id=None opens a fresh conversation instead of resuming one, so a
    tool-capable agent can answer before its analysis exists.

    An agent whose prompt frontmatter declares `tools:` gets those provider
    tool profiles on chat turns only — the analysis itself stays deterministic.
    `ads_scope` ({account_id, profile_id, requested_by}) is the client's
    Amazon Ads account the chat is pinned to, when the AM picked one.
    `context_docs` are the analyses the chat talks about; they go with every
    turn that opens a session, and a resumed session already has them.
    `note` is app state the model must know on every turn (the page the AM is
    on); it precedes the question and is never shown in the thread.
    `thread` is the visible conversation so far: a turn that opens a new
    session carries it, so the model does not forget what was already said.
    """
    call = _followup_call(slug, session_id, question, ads_scope, context_docs, note, thread)
    resp = client.ask(**call)
    return resp.get("text", ""), _remember_session(call, resp)


@dataclass(frozen=True)
class ChatReply:
    """One chat answer: the components the panel draws and the text everything else reads.

    `blocks` is None when the answer did not come in components; `text` is then the
    model's prose, which the panel shows the way it showed every answer before."""

    text: str
    blocks: list[dict] | None
    tool_calls: tuple[str, ...]
    session_id: str | None
    # One entry per call that failed; empty when the provider does not report outcomes.
    failed_tools: tuple[str, ...] = ()
    # The model asked for: the streamed result does not say which one answered.
    model: str | None = None
    cost_usd: float | None = None


def stream_followup(slug: str, session_id: str | None, question: str,
                    ads_scope: dict | None = None,
                    context_docs: list | None = None,
                    note: str | None = None,
                    thread: list | None = None) -> Iterator[dict]:
    """The same turn as `ask_followup`, streamed and answered in components.

    The model reads the catalog of what the panel can draw and is held to its
    schema; which components to use, and in what order, is its call.
    Yields {"type": "tool", "name": ...} for each tool the model asks for while it
    works, {"type": "tool_result", "name": ..., "ok": ...} when that call comes back,
    then one {"type": "reply", "reply": ChatReply}. Raises what
    `ask_followup` raises."""
    call = _followup_call(slug, session_id, question, ads_scope, context_docs, note, thread,
                          guide=chat_components.GUIDE, output_schema=chat_components.SCHEMA)
    for event in client.ask_stream(**call):
        if event.get("type") == "tool":
            yield {"type": "tool", "name": str(event.get("name") or "")}
        elif event.get("type") == "tool_result":
            yield {"type": "tool_result", "name": str(event.get("name") or ""), "ok": event.get("ok") is not False}
        elif event.get("type") == "result":
            blocks = chat_components.normalize(event.get("structured_output"))
            text = chat_components.plain_text(blocks) if blocks else str(event.get("text") or "")
            yield {"type": "reply", "reply": ChatReply(
                text=text, blocks=blocks, tool_calls=tuple(event.get("tool_calls") or ()),
                session_id=_remember_session(call, event),
                failed_tools=tuple(event.get("failed_tools") or ()),
                model=call["model"], cost_usd=event.get("total_cost_usd"))}


def _followup_call(slug: str, session_id: str | None, question: str, ads_scope: dict | None,
                   context_docs: list | None, note: str | None, thread: list | None,
                   guide: str = "", output_schema: dict | None = None) -> dict:
    agent = _agent(slug)
    system = agent["system"] + ("\n\n" + _CHAT_RULES if _CHAT_RULES else "") + ("\n\n" + guide if guide else "")
    tools = usable_tools(slug, ads_scope) or None
    session_id = _session_to_resume(session_id, bool(tools))
    # Uploaded from Sistema, not from the repo. A broken registry costs a skill,
    # never the turn — see core.chat.skills.enabled_payload.
    skills = chat_skills.enabled_payload()
    context = [] if session_id else _opening_context(context_docs, thread)
    input_text = f"{note}\n\n{question}" if note else question
    return dict(system=system, input_text=input_text, context=context,
                model=agent["meta"].get("model", "opus"),
                effort=agent["meta"].get("effort") or None,
                session_id=session_id, timeout_s=int(agent["meta"].get("timeout_s", 3600)),
                output_schema=output_schema,
                # A schema turn spends turns on the StructuredOutput call, with or without tools.
                max_turns=_MAX_TOOL_TURNS if tools or output_schema else 1,
                tools=tools,
                ads_scope=ads_scope if tools and AMAZON_ADS_TOOLS in tools else None,
                skills=skills or None,
                tag=f"{slug}-chat")


def _remember_session(call: dict, resp: dict) -> str | None:
    new_session = resp.get("session_id") or call["session_id"]
    if new_session:
        _TOOLED_TURNS[new_session] = bool(call["tools"])
    return new_session


CONVERSATION_TITLE = "Conversación previa de este chat, tal como la ve el AM en su panel"
_CONVERSATION_TURNS = 12
_CONVERSATION_CHARS = 12_000


def conversation_document(thread: list | None) -> dict | None:
    """The last turns of the visible thread, for a session that has to start over.

    A new session opens whenever the documents change, and without this the
    model answers the next question as if nothing had been said. Answers go as
    the AM saw them, with the item behind each row id: the new documents may
    give those ids to other rows. Failed turns stay out, and turns are dropped
    whole, oldest first, so the last question is never cut in half.
    """
    turns = [turn for turn in (thread or []) if turn.get("text") and not turn.get("error")]
    lines = [("AM: " if turn["role"] == "user" else "Asistente: ") + str(turn.get("shown") or turn["text"])
             for turn in turns[-_CONVERSATION_TURNS:]]
    kept, used = [], 0
    for line in reversed(lines):
        if kept and used + len(line) > _CONVERSATION_CHARS:
            break
        kept.append(line[:_CONVERSATION_CHARS])
        used += len(line) + 2
    if not kept:
        return None
    return {"title": CONVERSATION_TITLE, "content": "\n\n".join(reversed(kept))}


def _opening_context(context_docs: list | None, thread: list | None) -> list:
    context = list(context_docs or [])
    conversation = conversation_document(thread)
    if conversation:
        context.append(conversation)
    return context


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
