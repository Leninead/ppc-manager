"""The PPC Forecast agent's answer as text for the app chat.

The figures stay in the agent's own documents; this text carries the judgement on each of them.
"""
from ai.agents.ppc_forecast.context import TOPICS
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict) -> str:
    lines = [synthesis_text(result.get("synthesis") or {})]
    readings = [item for item in result.get("lecturas") or [] if item.get("tema") in TOPICS]
    if readings:
        lines += ["", "Lectura de las cifras del módulo (cifra → confianza):"]
        lines += [_reading_line(item) for item in readings]
    return "\n".join(lines)


def _reading_line(item: dict) -> str:
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    return f"{TOPICS[item['tema']]} → {item.get('confianza', '')}: {item.get('razon', '')}{warning}"
