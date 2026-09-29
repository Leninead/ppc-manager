"""The Account Pulse agent's answer as text for the app chat.

The figures stay in the agent's own documents; this text carries the reading of each topic.
"""
from ai.agents.account_pulse.context import TOPICS
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict) -> str:
    lines = [synthesis_text(result.get("synthesis") or {})]
    readings = [item for item in result.get("lecturas") or [] if item.get("tema") in TOPICS]
    if readings:
        lines += ["", "Lectura de cada tema del módulo (tema → veredicto):"]
        lines += [_reading_line(item) for item in readings]
    return "\n".join(lines)


def _reading_line(item: dict) -> str:
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    return f"{TOPICS[item['tema']]} → {item.get('veredicto', '')}: {item.get('razon', '')}{warning}"
