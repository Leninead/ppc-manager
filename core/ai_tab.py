"""Reusable integration layer between a module's deterministic pipeline and ai/.

It packages everything the STR and SQP AI tabs currently duplicate: the
analysis lifecycle (auto-fire, stale, pending, retry), the fragment polling,
the localized render kit and the floating-chat mount. A module never talks to
ai/runtime directly for its analysis tab — it talks to this layer.

Usage contract — what a consuming module provides:

    from core import ai_tab

    labels = ai_tab.ai_labels(lang, {"chat": "Análisis IA — SQP"})
    analysis = ai_tab.resolve_analysis(
        slug="sqp",                      # ai/agents/<slug>/ package
        payload=SqpData(...),            # the agent's build_context input
        file_signature=file_hash,        # hash of the uploaded bytes
        labels=labels,
    )
    if analysis is not None:
        ai_tab.render_analysis(
            analysis, slug="sqp", labels=labels,
            render_result=_render_sqp_result,   # module-owned tables
        )
    ai_tab.mount_analysis_chat("sqp", analysis, lang=lang, labels=labels)

What the layer resolves, so the module must NOT reimplement it:
- Session-state keys "<slug>_ai_last_digest/_seen/_file_sig" and widget keys
  "<slug>_ai_recalc/_retry" (one namespace per agent slug).
- Two-speed staleness: a NEW file (file_signature changed) re-fires on its
  own; a parameter change only shows the stale banner plus a Recalcular
  button. See decide_analysis_action for the exact decision table.
- Polling while running (st.fragment every 5s) and the one full rerun that
  stops it on completion; failed runs end in an error plus a human Retry.
- The chat mount gated on the analysis state: before completion questions
  are answered locally with labels["chat_wait"] / labels["chat_failed"].

render_result(result, analysis) receives the provider's structured_output
as-is; the module joins per-row opinions back to its own frames positionally
(ai/agents/<slug>/context.make_ids over the SAME frame it serialized) and
builds display rows for opinion_table_html. The canonical synthesis shape is
{situation, week_actions, mid_term, risks[{type, detail, urgency}],
executive_summary} — new agents must emit it; synthesis_html renders it.
"""
import html
import re
from enum import Enum

import streamlit as st

from ai import runtime as ai_runtime
from core.ai_chat import floating_chat

_BASE_LABELS = {
    "es": {"analyzing": "Analizando los datos por IA",
           "stale_title": "Los datos cambiaron",
           "stale_body": "Modificaste los parámetros después del último análisis. "
                         "Lo que se muestra abajo corresponde a la configuración "
                         "anterior.",
           "recalc": "Recalcular análisis",
           "pending_title": "Análisis pendiente",
           "pending_body": "Cambiaron los datos y no hay un análisis vigente para "
                           "esta configuración.",
           "run_btn": "Analizar con IA",
           "toast_done": "Análisis IA listo",
           "fail_prefix": "El análisis IA falló",
           "retry": "Reintentar",
           "warnings": "advertencias", "no_warnings": "Sin advertencias",
           "risks_title": "Riesgos",
           "actions_title": "Acciones sugeridas para esta semana",
           "actions_hint": "Corto plazo, en orden de prioridad. Son sugerencias "
                           "de la IA: el AM decide.",
           "mid_term_title": "Mediano plazo · 2 a 4 semanas",
           "mid_term_hint": "Oportunidades que no se resuelven esta semana: "
                            "gemas a re-validar, re-chequeos que confirman o "
                            "descartan hipótesis.",
           "col_item": "Ítem", "col_diag": "Diagnóstico", "col_read": "Lectura IA",
           "conf_label": "confianza", "copy_btn": "Copiar",
           "chat": "Análisis IA",
           "chat_wait": "El análisis todavía está corriendo — en cuanto termine "
                        "me podés repreguntar sobre cualquier fila o riesgo.",
           "chat_failed": "El análisis falló y no tengo resultados para responder. "
                          "Reintentalo desde el tab de análisis y volvé a "
                          "preguntarme."},
    "en": {"analyzing": "AI analyzing the data",
           "stale_title": "The data changed",
           "stale_body": "You modified the parameters after the last analysis. "
                         "What is shown below belongs to the previous "
                         "configuration.",
           "recalc": "Recalculate analysis",
           "pending_title": "Analysis pending",
           "pending_body": "The data changed and there is no current analysis "
                           "for this configuration.",
           "run_btn": "Analyze with AI",
           "toast_done": "AI analysis ready",
           "fail_prefix": "The AI analysis failed",
           "retry": "Retry",
           "warnings": "warnings", "no_warnings": "No warnings",
           "risks_title": "Risks",
           "actions_title": "Suggested actions for this week",
           "actions_hint": "Short term, in priority order. AI suggestions: "
                           "the AM decides.",
           "mid_term_title": "Mid term · 2 to 4 weeks",
           "mid_term_hint": "Opportunities that do not close this week: gems to "
                            "re-validate, re-checks that confirm or kill a "
                            "hypothesis.",
           "col_item": "Item", "col_diag": "Diagnosis", "col_read": "AI read",
           "conf_label": "confidence", "copy_btn": "Copy",
           "chat": "AI Analysis",
           "chat_wait": "The analysis is still running — as soon as it finishes "
                        "you can ask me about any row or risk here.",
           "chat_failed": "The analysis failed, so I have no results to answer "
                          "from. Retry it from the analysis tab and ask me "
                          "again."},
}

AI_CSS = """<style>
.ia-tbl {width:100%;border-collapse:collapse}
.ia-tbl th {text-align:left;padding:10px 16px;font-size:13px;color:#555555;
  font-weight:500;text-transform:uppercase;letter-spacing:.04em}
.ia-tbl td {padding:14px 16px;vertical-align:top;border-top:1px solid #EEE9E0}
.ia-tbl .c-item {width:32%}
.ia-tbl .c-diag {width:20%}
.ia-warn {background:#FAEEDA55}
@media (max-width: 768px) {
  .ia-tbl thead {display:none}
  .ia-tbl tr {display:block;border-top:1px solid #EEE9E0;padding:6px 0}
  .ia-tbl td {display:block;width:100% !important;border-top:none;
    padding:5px 14px}
}
</style>"""


def ai_labels(lang: str, overrides: dict | None = None) -> dict:
    base = _BASE_LABELS.get(lang, _BASE_LABELS["es"])
    return {**base, **(overrides or {})}


def escape_ai_text(text) -> str:
    """HTML-safe AI text; $ escaped so Streamlit never parses it as LaTeX."""
    return html.escape(str(text)).replace("$", "&#36;")


def humanize_fields(text, glossary: dict) -> str:
    """Deterministic safety net for AI prose: replaces leaked technical field
    names (imp_share, pur_t, is_invisible) with the human names a module
    declares in its glossary. Whole-token matches only, longest names first,
    so `imp_share` is never rewritten through `imp_b` or `share`."""
    if not text or not glossary:
        return str(text or "")
    names = sorted(glossary, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in names)
                         + r")(?!\w)")
    return pattern.sub(lambda m: glossary[m.group(1)], str(text))


def annotate_row_ids(text, labels_by_id: dict, max_len: int = 40) -> str:
    """Appends the item behind every row id the AI cites, so the prose reads
    without the table: "Frenar H59" -> "Frenar H59 (press on nails short)".
    Whole tokens only, first mention of each id per text. Skipped when the
    item already follows the id within a short window, which is how the model
    sometimes writes it itself."""
    if not text or not labels_by_id:
        return str(text or "")
    src = str(text)
    ids = sorted(labels_by_id, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(i) for i in ids)
                         + r")(?!\w)")
    seen = set()

    def _sub(match):
        rid = match.group(1)
        full = str(labels_by_id[rid]).strip()
        if not full or rid in seen:
            return rid
        seen.add(rid)
        window = src[match.end():match.end() + len(full) + 24].lower()
        if full.lower() in window:
            return rid
        shown = full if len(full) <= max_len else \
            full[:max_len - 1].rstrip() + "…"
        return f"{rid} ({shown})"

    return pattern.sub(_sub, src)


def map_synthesis_text(synthesis: dict, fn) -> dict:
    """Copy of the canonical synthesis with fn applied to every prose field
    (situation, week_actions, mid_term, risks[].detail, executive_summary).
    Structure and non-text values are untouched; the input is not mutated."""
    out = dict(synthesis or {})
    for key in ("situation", "executive_summary"):
        if isinstance(out.get(key), str):
            out[key] = fn(out[key])
    for key in ("week_actions", "mid_term"):
        if isinstance(out.get(key), list):
            out[key] = [fn(x) if isinstance(x, str) else x for x in out[key]]
    if isinstance(out.get("risks"), list):
        out["risks"] = [
            {**r, "detail": fn(r.get("detail", ""))} if isinstance(r, dict)
            else r for r in out["risks"]]
    return out


class AnalysisAction(Enum):
    USE = "use"
    AUTO_FIRE = "auto_fire"
    STALE = "stale"
    PENDING = "pending"


def decide_analysis_action(*, peeked_exists: bool, last_digest_exists: bool,
                           file_changed: bool,
                           previous_done: bool) -> AnalysisAction:
    """The whole lifecycle decision, pure and testable.

    USE       -> the registry already holds this exact payload.
    AUTO_FIRE -> first payload of the session, or a NEW file: fresh data must
                 not wait on a click.
    STALE     -> a parameter changed and the previous result is still shown:
                 banner + explicit Recalcular (no silent spend on widget churn).
    PENDING   -> the previous analysis is gone or unfinished: banner + button.
    """
    if peeked_exists:
        return AnalysisAction.USE
    if not last_digest_exists or file_changed:
        return AnalysisAction.AUTO_FIRE
    if previous_done:
        return AnalysisAction.STALE
    return AnalysisAction.PENDING


def resolve_analysis(*, slug: str, payload, file_signature: str, labels: dict):
    """Returns the analysis to render (running, failed or done), or None when
    the user must explicitly relaunch (pending state). Owns the layer's
    session keys for this slug."""
    last_key = f"{slug}_ai_last_digest"
    sig_key = f"{slug}_ai_file_sig"
    last_digest = st.session_state.get(last_key)

    peeked = ai_runtime.peek(slug, payload)
    previous = ai_runtime.get(slug, last_digest) if last_digest else None
    action = decide_analysis_action(
        peeked_exists=peeked is not None,
        last_digest_exists=last_digest is not None,
        file_changed=st.session_state.get(sig_key) != file_signature,
        previous_done=previous is not None and previous.done,
    )

    if action is AnalysisAction.USE:
        analysis = peeked
    elif action is AnalysisAction.AUTO_FIRE:
        analysis = ai_runtime.analyze(slug, payload)
    elif action is AnalysisAction.STALE:
        st.markdown(ai_notice_html(labels["stale_title"], labels["stale_body"]),
                    unsafe_allow_html=True)
        if st.button(labels["recalc"], key=f"{slug}_ai_recalc", type="primary"):
            ai_runtime.analyze(slug, payload)
            st.rerun()
        analysis = previous
    else:
        st.markdown(ai_notice_html(labels["pending_title"],
                                   labels["pending_body"]),
                    unsafe_allow_html=True)
        if st.button(labels["run_btn"], key=f"{slug}_ai_recalc", type="primary"):
            ai_runtime.analyze(slug, payload)
            st.rerun()
        analysis = None

    if analysis is not None:
        st.session_state[last_key] = analysis.digest
        st.session_state[sig_key] = file_signature
    return analysis


def render_analysis(analysis, *, slug: str, labels: dict, render_result) -> None:
    """Polls while running, surfaces failures with a human Retry, and hands the
    finished structured_output to the module's render_result(result, analysis)."""

    @st.fragment(run_every="5s" if analysis.running else None)
    def _poll(a=analysis):
        if a.running:
            st.status(f"{labels['analyzing']} — {a.elapsed}s", state="running")
            return
        # One full rerun on completion stops the 5s polling.
        seen_key = f"{slug}_ai_seen"
        if st.session_state.get(seen_key) != (a.digest, a.state):
            st.session_state[seen_key] = (a.digest, a.state)
            if a.done:
                st.toast(labels["toast_done"])
            st.rerun()
        if a.failed:
            st.error(f"{labels['fail_prefix']}: {a.error}")
            if st.button(labels["retry"], key=f"{slug}_ai_retry"):
                a.retry()
                st.rerun()
            return
        render_result(a.result, a)

    _poll()


def mount_analysis_chat(slug: str, analysis, *, lang: str,
                        labels: dict, annotate=None) -> None:
    """Mounts the floating chat as soon as an analysis exists. Call it at the
    END of render(), outside st.tabs.

    An agent with provider tools answers early questions for real (its tools do
    not need the analysis); one without them replies labels['chat_wait'] (or
    chat_failed) locally until the analysis session exists."""
    if analysis is None:
        return
    ready = analysis.done and analysis.session_id
    pending = labels["chat_failed"] if analysis.failed else labels["chat_wait"]
    floating_chat(chat_id=f"{slug}_{analysis.digest}", agent=slug,
                  session_id=analysis.session_id if ready else None,
                  title=labels["chat"], lang=lang,
                  pending_text=None if ready else pending,
                  standalone=bool(ai_runtime.agent_tools(slug)),
                  annotate=annotate)


def ai_notice_html(title: str, body: str) -> str:
    return (f'<div style="border:1px solid #F2C063;background:#FFF8EC;'
            f'border-radius:12px;padding:16px 18px;margin:6px 0 12px 0">'
            f'<div style="font-size:16px;font-weight:600;color:#7A4A00">'
            f'⚠ {title}</div>'
            f'<div style="font-size:15px;color:#1F1F1F;line-height:1.55;'
            f'margin-top:6px">{body}</div></div>')


def ai_chips_html(n_warnings: int, counts_text: str, elapsed_s: int,
                  labels: dict) -> str:
    """Result header chips: warning count + a module-provided counts summary."""
    if n_warnings:
        first = (f'<span style="background:#FAEEDA;color:#9C5700;'
                 f'border:1px solid #EF9F27;border-radius:99px;padding:4px 14px;'
                 f'font-size:15px;font-weight:500">⚠ {n_warnings} '
                 f'{labels["warnings"]}</span>')
    else:
        first = (f'<span style="background:#E8F5E9;color:#2E7D32;'
                 f'border:1px solid #A5D6A7;border-radius:99px;padding:4px 14px;'
                 f'font-size:15px;font-weight:500">{labels["no_warnings"]}</span>')
    return (f'<div style="display:flex;align-items:center;gap:12px;'
            f'flex-wrap:wrap;padding-top:4px">{first}'
            f'<span style="color:#1F1F1F;font-size:15px">'
            f'{escape_ai_text(counts_text)}</span>'
            f'<span style="color:#555555;font-size:14px">IA · {elapsed_s}s</span>'
            f'</div>')


def synthesis_section_title(text: str, hint: str = "") -> str:
    """Section heading shared by the synthesis blocks: small uppercase label
    over a hairline, clearly distinct from the 16-17px body text. The optional
    hint is a native tooltip, so the heading stays a label and not a caption."""
    safe_hint = escape_ai_text(hint).replace('"', "&quot;") if hint else ""
    title_attr = f' title="{safe_hint}"' if safe_hint else ""
    return (f'<div{title_attr} style="margin:18px 0 6px 0;padding-top:12px;'
            f'border-top:1px solid #EFEBE4;font-size:13px;font-weight:600;'
            f'letter-spacing:.06em;text-transform:uppercase;color:#6B6660">'
            f'{escape_ai_text(text)}</div>')


def synthesis_html(synthesis: dict, labels: dict) -> str:
    """Renders the canonical synthesis shape: situation, week_actions[],
    mid_term[], risks[{type, detail, urgency}]. Every list is introduced by
    a section heading, so the numbered actions read as the AI's suggestions
    for the week and never as a continuation of the situation paragraph."""
    situation = escape_ai_text(synthesis.get("situation", ""))
    actions = ""
    if synthesis.get("week_actions"):
        rows = "".join(
            f'<div style="display:flex;gap:12px;margin:11px 0;font-size:16px;'
            f'line-height:1.55;color:#1F1F1F">'
            f'<span style="background:#FAECE7;color:#993C1D;border-radius:8px;'
            f'min-width:26px;height:26px;display:flex;align-items:center;'
            f'justify-content:center;font-weight:500;font-size:14px">{i}</span>'
            f'<span>{escape_ai_text(a)}</span></div>'
            for i, a in enumerate(synthesis["week_actions"], 1))
        actions = synthesis_section_title(
            labels["actions_title"], labels.get("actions_hint", "")) + rows
    mid_term = ""
    if synthesis.get("mid_term"):
        items = "".join(f'<li style="margin:4px 0">{escape_ai_text(m)}</li>'
                        for m in synthesis["mid_term"])
        mid_term = (synthesis_section_title(labels["mid_term_title"],
                                            labels.get("mid_term_hint", ""))
                    + f'<ul style="margin:0 0 0 4px;font-size:15px;'
                      f'line-height:1.55;color:#1F1F1F">{items}</ul>')
    risks = ""
    if synthesis.get("risks"):
        cards = "".join(
            f'<div style="margin-top:8px;background:#FAEEDA;border-radius:10px;'
            f'padding:10px 14px;font-size:14px;line-height:1.5;color:#633806">'
            f'<span style="font-weight:600">{escape_ai_text(r.get("type", ""))}'
            f'{" · " + escape_ai_text(r["urgency"]) if r.get("urgency") else ""}:'
            f'</span> {escape_ai_text(r.get("detail", ""))}</div>'
            for r in synthesis["risks"])
        risks = synthesis_section_title(labels["risks_title"]) + cards
    return (f'<div style="padding:4px 2px 6px 2px">'
            f'<div style="font-size:17px;line-height:1.65;color:#1F1F1F">'
            f'{situation}</div>{actions}{mid_term}{risks}</div>')


def opinion_table_html(rows: list, title: str, labels: dict,
                       badge_colors: dict) -> str:
    """Custom table for per-row AI opinions: wrapping text, mobile stacking.

    Row contract: {row_id, item, type_tag, metrics[], badges[], confidence,
    warning, reasoning} — badges are looked up in badge_colors; row_id is
    optional and, when given, is printed ahead of the item.
    """
    header = (f'<thead><tr><th class="c-item">{labels["col_item"]}</th>'
              f'<th class="c-diag">{labels["col_diag"]}</th>'
              f'<th>{labels["col_read"]}</th></tr></thead>')
    default_badge = "background-color:#F5F5F5;color:#616161"
    body = []
    for r in rows:
        badges = "".join(
            f'<div style="margin-top:6px"><span style="'
            f'{badge_colors.get(b, default_badge)};border-radius:99px;'
            f'padding:4px 12px;font-size:13px;white-space:nowrap">'
            f'{escape_ai_text(b)}</span></div>'
            for b in r.get("badges", []) if b) or "—"
        if r.get("confidence") and r["confidence"] != "ALTA":
            conf_style = ("background-color:#FFEBEE;color:#9C0006"
                          if r["confidence"] == "BAJA"
                          else "background-color:#FFF8E1;color:#9C5700")
            badges += (f'<div style="margin-top:6px"><span style="{conf_style};'
                       f'border-radius:99px;padding:4px 12px;font-size:13px;'
                       f'white-space:nowrap">{labels["conf_label"]} '
                       f'{escape_ai_text(r["confidence"].lower())}</span></div>')
        read = ""
        if r.get("warning"):
            read += (f'<div style="color:#854F0B;font-weight:500;font-size:15px;'
                     f'line-height:1.5">⚠ {escape_ai_text(r["warning"])}</div>')
        if r.get("reasoning"):
            read += (f'<div style="color:#1F1F1F;font-size:14px;'
                     f'line-height:1.5;margin-top:4px">'
                     f'{escape_ai_text(r["reasoning"])}</div>')
        pills = "".join(
            f'<span style="border:1px solid #E6E1D8;background:#FAF9F6;'
            f'border-radius:6px;padding:2px 9px;font-family:monospace;'
            f'font-size:13px;color:#1F1F1F;white-space:nowrap">'
            f'{escape_ai_text(m)}</span>'
            for m in r.get("metrics", []))
        type_tag = (f'<span style="background:#F1EFE8;color:#5F5E5A;'
                    f'border-radius:6px;padding:2px 9px;font-size:12px;'
                    f'font-weight:500;white-space:nowrap">'
                    f'{escape_ai_text(r["type_tag"])}</span>'
                    if r.get("type_tag") else "")
        # The id the AI cites (N07, Q03, K12) printed ahead of the item, so
        # the AM can find a row named in the synthesis without counting.
        row_id = (f'<span style="font-family:monospace;font-size:13px;'
                  f'background:#F1EFE8;color:#444441;border-radius:6px;'
                  f'padding:2px 7px;margin-right:8px;white-space:nowrap;'
                  f'vertical-align:middle">{escape_ai_text(r["row_id"])}'
                  f'</span>' if r.get("row_id") else "")
        body.append(
            f'<tr><td class="c-item">'
            f'<div style="font-size:16px;font-weight:600;color:#1F1F1F">'
            f'{row_id}{escape_ai_text(r.get("item", ""))}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;'
            f'align-items:center">{type_tag}{pills}</div>'
            f'</td><td class="c-diag">{badges}</td>'
            f'<td class="{"ia-warn" if r.get("warning") else ""}">'
            f'{read or "—"}</td></tr>')
    return (f'<div style="font-weight:600;font-size:16px;margin:20px 0 8px">'
            f'{title}</div>'
            '<div style="border:1px solid #EEE9E0;border-radius:12px;'
            'overflow:hidden"><table class="ia-tbl">' + header + "<tbody>"
            + "".join(body) + "</tbody></table></div>")
