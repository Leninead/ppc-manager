"""Floating AI chat, pinned to the bottom-right of the page.

The app mounts one, for every page, through core.app_chat:

    from core.ai_chat import floating_chat
    floating_chat(chat_id="app", agent="orchestrator",
                  session_key=key_of_the_analyses, turn=what_a_question_is_sent_with)

History is kept per chat_id in session_state; every answer resumes the same
provider session until the documents change. Mount it OUTSIDE st.tabs so the
bubble shows on every tab.
"""
import html
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import streamlit as st
import streamlit.components.v1 as components

from ai import runtime
from ai.client import AIError
from core import chat_components
from core.chat_components.base import ACCENT, esc, prose_html


@dataclass(frozen=True)
class ChatTurn:
    """What a question is sent with, built only when the AM sends one.

    documents open a session (a new session_key starts another one, and that
    turn carries the visible thread). note is app state sent ahead of the
    question and never shown. ads_scope is the Amazon Ads account the tools use.
    annotate is applied once to the answer when it arrives, e.g. to append the
    item behind the row ids it cites."""

    documents: list = field(default_factory=list)
    note: str | None = None
    ads_scope: dict | None = None
    annotate: Callable[[str], str] | None = None

_ACCENT = ACCENT

_L = {
    "es": {"title": "Capybaras Copilot",
           "empty": "Preguntá por un análisis de la app, una cuenta de "
                    "Amazon Ads o un niche de DataDive.",
           "placeholder": "Escribí tu pregunta...", "send": "Enviar",
           "send_hint": "Enter envía · Shift+Enter agrega una línea",
           "copy": "Copiar chat", "copied": "Copiado",
           "copy_fail": "No se pudo copiar",
           "close": "Cerrar",
           "error": "No se pudo responder",
           # Aparecen solas, por CSS, a los 8 y a los 25 segundos.
           "wait_tools": "Buscando los datos…",
           "tool_failed": "falló",
           "wait_long": "Sigue trabajando. Puede tardar unos minutos.",
           "src_amazon_ads": "Amazon Ads", "src_datadive": "DataDive", "src_ppc_manager": "Agency OS",
           "reads": {"reports": "Reportes", "ad_groups": "Ad groups", "targets": "Targets",
                     "budgets": "Presupuestos", "portfolios": "Portfolios", "campaigns": "Campañas",
                     "accounts": "Cuentas", "competitors": "Competidores", "keywords": "Keywords",
                     "rank_radar": "Rank Radar", "niches": "Niches", "analyses": "Análisis",
                     "search_terms": "Search terms", "daily": "Serie diaria",
                     "breakdown": "Desglose"}},
    "en": {"title": "Capybaras Copilot",
           "empty": "Ask about an analysis in the app, an Amazon Ads "
                    "account or a DataDive niche.",
           "placeholder": "Type your question...", "send": "Send",
           "send_hint": "Enter sends · Shift+Enter adds a line",
           "copy": "Copy chat", "copied": "Copied",
           "copy_fail": "Copy failed",
           "close": "Close",
           "error": "Could not answer",
           "wait_tools": "Looking up the data…",
           "tool_failed": "failed",
           "wait_long": "Still working. This can take a few minutes.",
           "src_amazon_ads": "Amazon Ads", "src_datadive": "DataDive", "src_ppc_manager": "Agency OS",
           "reads": {"reports": "Reports", "ad_groups": "Ad groups", "targets": "Targets",
                     "budgets": "Budgets", "portfolios": "Portfolios", "campaigns": "Campaigns",
                     "accounts": "Accounts", "competitors": "Competitors", "keywords": "Keywords",
                     "rank_radar": "Rank Radar", "niches": "Niches", "analyses": "Analyses",
                     "search_terms": "Search terms", "daily": "Daily series",
                     "breakdown": "Breakdown"}},
}


def _user_bubble(text: str) -> str:
    safe = esc(text).replace("\n", "<br>")
    return ('<div style="display:flex;justify-content:flex-end;margin:5px 0">'
            f'<div style="background:{_ACCENT};color:#fff;max-width:82%;'
            'border-radius:16px 16px 4px 16px;padding:10px 14px;'
            f'font-size:16px;line-height:1.5">{safe}</div></div>')


def _assistant_bubble(text: str, blocks: list[dict] | None = None) -> str:
    """An answer in components is drawn by them; an answer without, from its prose."""
    body = (chat_components.render(blocks) if blocks else prose_html(text)) or "<p style='margin:0'>…</p>"
    return ('<div style="display:flex;justify-content:flex-start;margin:5px 0">'
            '<div style="background:#FFFFFF;border:1px solid #E0DCD4;'
            'color:#1F1F1F;width:100%;border-radius:16px 16px 16px 4px;'
            f'padding:10px 14px;font-size:15px;line-height:1.6">{body}</div></div>')


_TOOL_SOURCES = (
    ("mcp__amazon_ads__", "src_amazon_ads",
     # Matched against the operation, first hit wins: "campaign_management-query_ad_group"
     # reads ad groups, and "create_campaign_report" is a report.
     (("report", "reports"), ("ad_group", "ad_groups"), ("target", "targets"),
      ("keyword", "targets"), ("budget", "budgets"), ("portfolio", "portfolios"),
      ("campaign", "campaigns"), ("account", "accounts"), ("profile", "accounts"))),
    ("mcp__datadive__", "src_datadive",
     (("quota", None), ("competitor", "competitors"), ("keyword", "keywords"),
      ("rank_radar", "rank_radar"), ("niche", "niches"))),
    ("mcp__ppc_manager__", "src_ppc_manager",
     (("analys", "analyses"), ("search_term", "search_terms"), ("daily", "daily"), ("breakdown", "breakdown"),
      ("account", "accounts"))),
)


def _tool_label(name: str, labels: dict) -> str | None:
    """What a tool read, in the AM's words, or None for one that reads nothing of theirs.

    The raw name is the model's vocabulary ("mcp__amazon_ads__campaign_management-
    query_campaign"): showing it is the column-name problem the AI outputs already had."""
    for prefix, source, reads in _TOOL_SOURCES:
        if not name.startswith(prefix):
            continue
        operation = name[len(prefix):].split("-", 1)[-1]
        for word, key in reads:
            if word in operation:
                return f'{labels["reads"][key]} · {labels[source]}' if key else None
        return labels[source]
    return None  # Skill, Read and the SDK's own tools are machinery, not sources


def _tool_labels(names, labels: dict) -> list[str]:
    seen: list[str] = []
    for name in names:
        label = _tool_label(str(name), labels)
        if label and label not in seen:
            seen.append(label)
    return seen


def _failed_labels(asked, failed, labels: dict) -> list[str]:
    """The sources every call to which failed: one that answered even once did reach the answer."""
    tally: dict[str, list[int]] = {}
    for name in asked:
        label = _tool_label(str(name), labels)
        if label:
            tally.setdefault(label, [0, 0])[0] += 1
    for name in failed:
        label = _tool_label(str(name), labels)
        if label in tally:
            tally[label][1] += 1
    return [label for label, (calls, failures) in tally.items() if failures >= calls]


_CHIP = "font-size:12px;line-height:1.5;border-radius:6px;white-space:nowrap;"


def _tools_row(tool_labels: list[str], failed=(), failed_note: str = "") -> str:
    if not tool_labels:
        return ""
    chips = "".join(
        f'<span style="{_CHIP}color:#8A867C;border:1px dashed #CFC6B4;padding:0 7px">'
        f'{html.escape(label + (" · " + failed_note if failed_note else ""))}</span>'
        if label in failed else
        f'<span style="{_CHIP}color:#5F5B53;background:#EFEBE4;padding:1px 8px">{html.escape(label)}</span>'
        for label in tool_labels)
    return f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 0 2px">{chips}</div>'


def _assistant_turn(turn: dict, failed_note: str = "") -> str:
    """Chips and bubble inside one element: the thread lays its children out in reverse."""
    return ("<div>" + _tools_row(turn.get("tools") or [], turn.get("tools_failed") or (), failed_note)
            + _assistant_bubble(turn.get("shown", turn["text"]), turn.get("blocks")) + "</div>")


def _typing(labels: dict) -> str:
    """Dots, then a line saying the wait is normal, then one saying it is long.

    Both lines ship in the markup and surface on a CSS delay. Python repaints the
    wait only when the provider reports a tool, so a turn that reads nothing, or
    one tool that runs long, would otherwise show the same three dots whether it
    took three seconds, a minute, or had died. Measured before this existed, on a
    faster model at low effort: 32.8s median wait, 60.1s worst.
    """
    return ('<div class="ia-dots" style="padding:6px 4px">'
            '<span></span><span></span><span></span></div>'
            '<div class="ia-wait">'
            f'<span>{html.escape(labels["wait_tools"])}</span>'
            f'<span>{html.escape(labels["wait_long"])}</span>'
            '</div>')


_CLIP_SVG = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
             'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" '
             'rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 '
             '0 1 2 2v1"/></svg>')
_CHECK_SVG = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>')

_X_SVG = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
          'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
          'stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>')


def _chat_header(title: str, copy_text: str, copy_title: str,
                 close_title: str) -> None:
    """Orange header with icon-only copy and close buttons (they need JS, so
    the whole header lives in one component iframe)."""
    icon = ""
    if copy_text:
        icon = (f'<button id="cp" title="{html.escape(copy_title)}" '
                f'aria-label="{html.escape(copy_title)}" '
                'style="margin-left:auto;background:transparent;border:none;'
                'color:#FADFD3;cursor:pointer;padding:8px;border-radius:8px;'
                f'display:flex;align-items:center">{_CLIP_SVG}</button>')
    close_margin = "" if copy_text else "margin-left:auto;"
    close_btn = (f'<button id="cl" title="{html.escape(close_title)}" '
                 f'aria-label="{html.escape(close_title)}" '
                 f'style="{close_margin}background:transparent;border:none;'
                 'color:#FADFD3;cursor:pointer;padding:8px;border-radius:8px;'
                 f'display:flex;align-items:center">{_X_SVG}</button>')
    # "</" would close the <script> early: keep it out of the JSON literal.
    safe_copy = json.dumps(copy_text).replace("</", "<\/")
    components.html(f"""
<div style="display:flex;align-items:center;gap:10px;background:{_ACCENT};
  border-radius:12px;padding:10px 14px;margin:0;
  font-family:'Segoe UI',system-ui,sans-serif">
  <span style="width:30px;height:30px;border-radius:99px;flex:none;
    background:rgba(255,255,255,.25);color:#fff;display:flex;
    align-items:center;justify-content:center;font-size:12px;
    font-weight:600">AI</span>
  <span style="font-size:14px;font-weight:600;color:#fff">{html.escape(title)}</span>
  {icon}
  {close_btn}
</div>
<script>
// st.popover has no programmatic close: the X synthesizes the two gestures
// BaseWeb already listens for (Escape, then an outside mousedown).
const x = document.getElementById('cl');
if (x) {{
  x.addEventListener('mouseenter', () => x.style.color = '#fff');
  x.addEventListener('mouseleave', () => x.style.color = '#FADFD3');
  x.addEventListener('click', () => {{
    const doc = window.parent.document;
    doc.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape',
      code: 'Escape', keyCode: 27, which: 27, bubbles: true}}));
    for (const ev of ['mousedown', 'mouseup', 'click']) {{
      doc.body.dispatchEvent(new MouseEvent(ev, {{bubbles: true}}));
    }}
  }});
}}
const b = document.getElementById('cp');
if (b) {{
  const t = {safe_copy};
  const clip = {json.dumps(_CLIP_SVG)};
  const check = {json.dumps(_CHECK_SVG)};
  b.addEventListener('mouseenter', () => b.style.color = '#fff');
  b.addEventListener('mouseleave', () => b.style.color = '#FADFD3');
  b.addEventListener('click', async () => {{
    let ok = false;
    try {{ await navigator.clipboard.writeText(t); ok = true; }} catch (e) {{}}
    if (!ok) {{
      // iOS-safe fallback: explicit range, 16px font stops zoom-on-focus.
      const ta = document.createElement('textarea');
      ta.value = t;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      ta.style.fontSize = '16px';
      ta.setAttribute('readonly', '');
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      ta.setSelectionRange(0, t.length);
      try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
      ta.remove();
    }}
    if (ok) {{
      b.innerHTML = check; b.style.color = '#fff';
      setTimeout(() => {{ b.innerHTML = clip; b.style.color = '#FADFD3'; }}, 1500);
    }}
  }});
}}
</script>""", height=66)


def _enter_sends_script(panel: str) -> str:
    """Enter sends, Shift+Enter adds a line.

    Streamlit ties a form's text area to Ctrl+Enter and offers no way to rebind it, so the
    panel's own box is bound here; the click is the same path as the send button."""
    selector = json.dumps(f".st-key-{panel} textarea")
    return f"""
const doc = window.parent.document;
const bind = () => {{
  const box = doc.querySelector({selector});
  if (!box || box.dataset.entersends) return;
  box.dataset.entersends = '1';
  box.addEventListener('keydown', (e) => {{
    // keyCode 229 is a composing IME on the browsers that leave isComposing unset.
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (!box.value.trim()) return;
    // help= makes Streamlit render the button twice, one copy per breakpoint.
    const buttons = box.closest('[data-testid="stForm"]')
                       ?.querySelectorAll('[data-testid="stFormSubmitButton"] button') ?? [];
    const send = [...buttons].find((b) => b.offsetParent !== null) ?? buttons[0];
    if (send) send.click();
  }});
}};
bind();
// Every answer replaces the box with a fresh element while this frame stays put.
new MutationObserver(bind).observe(doc.body, {{childList: true, subtree: true}});
"""


def _enter_sends(panel: str) -> None:
    with st.container(key=f"{panel}_enter"):
        components.html(f"<script>{_enter_sends_script(panel)}</script>", height=0)


def floating_chat(*, chat_id: str, agent: str, session_key: Callable[[], str | None],
                  turn: Callable[[], ChatTurn], title: str | None = None, lang: str = "es") -> None:
    """Every question is answered by the provider; the first one opens the session.

    `session_key` runs on every render of every page, so it stays cheap; a new
    key opens a new session. `turn` runs only when a question is sent, because
    that is when its documents are needed and because the chat body reruns
    alone: what the page computed on its last full run can be stale by then
    (an analysis that finished in the background).
    History keeps each answer's raw text for the model and its annotated text
    for the bubbles and the transcript."""
    L = _L.get(lang, _L["es"])
    title = title or L["title"]
    anchor = f"aichat_{chat_id}_anchor"
    panel = f"aichat_{chat_id}_panel"
    hist_key = f"aichat_{chat_id}_hist"
    sid_key = f"aichat_{chat_id}_sid"
    context_key_key = f"aichat_{chat_id}_context"
    history = st.session_state.setdefault(hist_key, [])

    def _sync_session() -> None:
        key = session_key()
        if st.session_state.get(context_key_key) != key:
            st.session_state[context_key_key] = key
            st.session_state[sid_key] = None

    _sync_session()
    st.session_state.setdefault(sid_key, None)

    st.markdown(
        f"""<style>
        .st-key-{anchor} {{position: fixed; right: 1.4rem; bottom: 1.4rem;
                           width: auto; z-index: 1000;}}
        .st-key-{anchor} button {{
            border-radius: 999px; width: 54px; height: 54px;
            background: {_ACCENT}; color: #fff; border: none;
            font-size: 24px; box-shadow: 0 2px 10px rgba(0,0,0,.25);}}
        .st-key-{anchor} button:hover {{background: #C63600; color: #fff;}}
        .st-key-{anchor} button svg {{display: none;}}
        .st-key-{anchor} button p {{font-size: 24px; margin: 0; line-height: 1;}}
        /* The panel is exactly as tall as its three parts and never scrolls
           itself: the thread box owns the only scrollbar. Streamlit gives the
           popover body a max-height and an overflow of its own, which produced
           a second bar spanning the whole panel and fought the thread's drag
           handle — a box cannot be resized past a parent that clips it.
           The body is portaled away from the anchor, so it is matched by the
           panel it holds: every other popover of the app keeps its own look. */
        [data-testid="stPopoverBody"]:has(.st-key-{panel}) {{
                                        min-width: min(420px, 92vw);
                                        max-width: min(460px, 94vw);
                                        border-radius: 16px;
                                        padding: 10px !important;
                                        max-height: none !important;
                                        overflow: visible !important;}}
        /* The header is an iframe and Streamlit's block wrapper zeroes the
           padding around it, so it sat flush against the frame while the input
           below had room. Same 10px on all four sides. */
        [data-testid="stPopoverBody"]:has(.st-key-{panel}) > div {{padding: 0 !important;}}
        .st-key-{panel} iframe {{display: block;}}
        .st-key-{panel} [data-testid="stForm"] {{border: none; padding: 0;}}
        .st-key-{panel}_enter {{display: none;}}
        .ia-dots span {{width:7px; height:7px; border-radius:99px;
            background:#B4B2A9; display:inline-block; margin-right:4px;
            animation: iaDot 1s infinite;}}
        .ia-dots span:nth-child(2) {{animation-delay:.15s;}}
        .ia-dots span:nth-child(3) {{animation-delay:.3s;}}
        @keyframes iaDot {{0%,60%,100%{{opacity:.25}} 30%{{opacity:1}}}}
        .ia-wait {{position:relative; height:17px; margin:-2px 0 4px 4px;}}
        .ia-wait span {{position:absolute; left:0; top:0; opacity:0;
            font-size:12.5px; color:#8A867C; white-space:nowrap;}}
        .ia-wait span:nth-child(1) {{animation: iaFadeIn .4s 8s forwards,
                                                iaFadeOut .4s 25s forwards;}}
        .ia-wait span:nth-child(2) {{animation: iaFadeIn .4s 25.2s forwards;}}
        @keyframes iaFadeIn {{to {{opacity:1}}}}
        @keyframes iaFadeOut {{to {{opacity:0}}}}
        </style>""",
        unsafe_allow_html=True,
    )

    with st.container(key=anchor):
        with st.popover("💬", help=title):

            # Fragment scope: answering re-renders only the chat, so the
            # panel stays open through the round trip.
            @st.fragment
            def _chat_body():
                user_lbl = (st.session_state.get("name")
                            or st.session_state.get("username") or "AM")
                plain = (title + "\n\n" + "\n\n".join(
                    (f"{user_lbl}: " + t["text"]) if t["role"] == "user"
                    else ("Capybaras AI: " + t.get("shown", t["text"]))
                    for t in history)) if history else ""
                _chat_header(title, plain, L["copy"], L["close"])
                if history:
                    # Newest first in the DOM, `column-reverse` in the CSS: the
                    # pair puts the latest message at the visual bottom AND
                    # starts the box scrolled there, which a plain `column` box
                    # does not. Measured on this panel before the change: the
                    # last answer was never fully visible, a median of 26% of it
                    # showed, and in 9 of 48 conversations none of it did — the
                    # AM waited half a minute and got their own old question.
                    # The closing question is the last line of nearly every
                    # answer, so it was the first thing to fall below the fold.
                    # Streamlit strips <script> from st.markdown even with
                    # unsafe_allow_html, so scrolling it from JS is not on the
                    # table here; this does it in CSS.
                    thread = "".join(
                        _user_bubble(t["text"]) if t["role"] == "user" else _assistant_turn(t, L["tool_failed"])
                        for t in reversed(history))
                    # `resize` gives the AM the drag handle they asked for: a
                    # long answer about a dozen campaigns does not fit in half a
                    # viewport, and until now the box was a fixed 480px with no
                    # way out. `height` rather than `max-height` because a box
                    # only resizes from a height it already has, and `min-height`
                    # keeps a drag from collapsing it to nothing.
                    st.markdown(
                        '<div style="display:flex;flex-direction:column-reverse;'
                        'height:min(52vh, 480px);min-height:140px;'
                        'max-height:88vh;resize:vertical;overflow-y:auto;'
                        'background:#FAF8F4;border-radius:12px;'
                        f'padding:10px">{thread}</div>',
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div style="color:#1F1F1F;font-size:15px;'
                        f'line-height:1.5;padding:2px 4px 8px 4px">'
                        f'{html.escape(L["empty"])}</div>',
                        unsafe_allow_html=True)

                # Declared before the input so the in-flight exchange renders
                # ABOVE it: the question is visible while the answer arrives.
                live = st.container()
                # A form, not st.chat_input. Inside a popover that also holds a
                # fragment, chat_input renders and accepts text but its submit
                # never arrives — typed or pasted, the box keeps the text and
                # nothing happens. Reproduced in isolation: chat_input works on
                # its own, inside a popover, and inside a fragment, and fails on
                # the two together; a form submits in all four. The text area is
                # also draggable, which is the other thing the panel was missing.
                # Keyed by turn AND cleared on submit, which only work together: the clear
                # empties the box in the browser once the question is already on the wire,
                # the only thing that can do it while this thread blocks on the answer; the
                # stale value it leaves behind goes with the widget id the next turn retires.
                # enter_to_submit=False takes Streamlit's English Ctrl+Enter hint off the box.
                with st.form(f"aichat_{chat_id}_form", border=False,
                             enter_to_submit=False, clear_on_submit=True):
                    question = st.text_area(
                        L["placeholder"], key=f"aichat_{chat_id}_q_{len(history)}",
                        placeholder=L["placeholder"], height=72,
                        label_visibility="collapsed")
                    sent = st.form_submit_button(L["send"], use_container_width=True,
                                                 type="primary", help=L["send_hint"])
                _enter_sends(panel)
                question = (question or "").strip() if sent else ""
                if question:
                    _sync_session()
                    sending = turn()
                    sid = st.session_state.get(sid_key)
                    with live:
                        # One element rewritten on every tool the provider reports,
                        # while the answer is still being worked out.
                        waiting = st.empty()
                        asked: list[str] = []
                        failed_calls: list[str] = []
                        reading: tuple[list[str], list[str]] = ([], [])
                        waiting.markdown(_user_bubble(question) + _typing(L),
                                         unsafe_allow_html=True)
                        try:
                            reply = None
                            for event in runtime.stream_followup(
                                    agent, sid, question, ads_scope=sending.ads_scope,
                                    context_docs=sending.documents, note=sending.note,
                                    thread=list(history)):
                                if event["type"] == "reply":
                                    reply = event["reply"]
                                    continue
                                if event["type"] == "tool_result":
                                    if not event["ok"]:
                                        failed_calls.append(event["name"])
                                else:
                                    asked.append(event["name"])
                                chips = (_tool_labels(asked, L), _failed_labels(asked, failed_calls, L))
                                if chips != reading:
                                    reading = chips
                                    waiting.markdown(
                                        _user_bubble(question) + _tools_row(*reading, L["tool_failed"])
                                        + _typing(L), unsafe_allow_html=True)
                            if reply is None:
                                raise AIError("el provider no devolvió la respuesta")
                            st.session_state[sid_key] = reply.session_id
                            # Annotated once, against the analyses it was answered
                            # from: the page shown later may reuse the same row ids.
                            blocks = reply.blocks
                            if blocks and sending.annotate:
                                blocks = chat_components.map_strings(blocks, sending.annotate)
                            if blocks:
                                shown = chat_components.plain_text(blocks)
                            else:
                                shown = sending.annotate(reply.text) if sending.annotate else reply.text
                            answer = {"role": "assistant", "text": reply.text, "shown": shown,
                                      "blocks": blocks, "tools": _tool_labels(reply.tool_calls, L),
                                      "tools_failed": _failed_labels(reply.tool_calls, reply.failed_tools, L)}
                        except AIError as e:
                            failure = f"{L['error']}: {e}"
                            answer = {"role": "assistant", "text": failure, "shown": failure,
                                      "error": True}
                    history.append({"role": "user", "text": question})
                    history.append(answer)
                    st.rerun(scope="fragment")

            with st.container(key=panel):
                _chat_body()
