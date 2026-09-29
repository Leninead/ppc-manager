"""The Weekly Client Report agent's answer as text: its reading for the app chat and the message for the client.

The figures stay in the agent's own documents; these texts carry the verdict on each topic and the client's summary.
"""
from ai.agents.synthesis_text import synthesis_text
from ai.agents.weekly_report.context import TOPICS

# (title, situation, highlights, attention, next steps), with the emoji each section had in the message sent before.
_CLIENT_HEADINGS = {
    "es": ("📊 RESUMEN SEMANAL", "📍 SITUACIÓN GENERAL", "📈 HIGHLIGHTS", "⚠️ ATENCIÓN", "🎯 PRÓXIMOS PASOS"),
    "en": ("📊 WEEKLY SUMMARY", "📍 OVERVIEW", "📈 HIGHLIGHTS", "⚠️ ATTENTION", "🎯 NEXT STEPS"),
}


def reading_text(result: dict, *, client: str = "", lang: str = "es") -> str:
    lines = [synthesis_text(result.get("synthesis") or {})]
    readings = [item for item in result.get("lecturas") or [] if item.get("tema") in TOPICS]
    if readings:
        lines += ["", "Lectura de cada tema del módulo (tema → veredicto):"]
        lines += [_reading_line(item) for item in readings]
    if result.get("resumen_cliente"):
        lines += ["", "Resumen para el cliente, tal como el AM lo copia:", client_message(result, client, lang)]
    return "\n".join(lines)


def client_message(result: dict, client: str, lang: str) -> str:
    """The summary for the client as the AM pastes it in Slack or an email."""
    summary = result.get("resumen_cliente") or {}
    title, situation, highlights, attention, next_steps = _CLIENT_HEADINGS.get(lang, _CLIENT_HEADINGS["es"])
    blocks = [f"{title} — {client}" if client else title, f"{situation}\n{summary.get('situacion', '')}"]
    for heading, key in ((highlights, "highlights"), (attention, "atencion"), (next_steps, "proximos_pasos")):
        items = [item for item in summary.get(key) or [] if item]
        if items:
            blocks.append("\n".join([heading, *(f"• {item}" for item in items)]))
    return "\n\n".join(blocks)


def _reading_line(item: dict) -> str:
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    return f"{TOPICS[item['tema']]} → {item.get('veredicto', '')}: {item.get('razon', '')}{warning}"
