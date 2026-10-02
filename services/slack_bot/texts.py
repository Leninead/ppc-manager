"""What the bot says in its own voice, apart from the answers: statuses, refusals and failures."""
from __future__ import annotations

import math

from services.slack_bot import slack_text

THINKING = "está pensando…"
# The panel's own wait lines: they describe the wait, never estimate it.
LOADING = ["Buscando los datos…", "Sigue trabajando. Puede tardar unos minutos."]
IDEAS_INTRO = "Preguntame por los clientes de la agencia y sus cuentas. Algunas ideas:"
CHANNEL_NOT_ALLOWED = ("No estoy habilitado en este canal. Pedile a quien administra el bot que lo agregue, "
                       "o escribime por mensaje directo.")
CHANNEL_SHARED = ("No respondo en canales compartidos con otras organizaciones: leo datos de todos los clientes "
                  "de la agencia.")
NOT_A_MEMBER = "Solo respondo a miembros del equipo de la agencia."
DIRECT_DISABLED = "Los mensajes directos están desactivados: mencioname en un canal habilitado."


def keep_going(direct: bool) -> str:
    return "Para seguir, escribime en este hilo." if direct else "Para seguir, mencioname en este hilo."


def reading(labels: list[str]) -> str:
    return f"está leyendo: {', '.join(labels)}" if labels else THINKING


def queued(ahead: int, running: int) -> str:
    if ahead <= 0:
        return f"Estoy respondiendo en {_conversations(running)}; sigo con esta apenas termine una."
    waiting = f"hay {_conversations(ahead)} esperando antes que esta; las respondo en orden."
    if running <= 0:
        return waiting[0].upper() + waiting[1:]
    return f"Estoy respondiendo en {_conversations(running)} y {waiting}"


def _conversations(count: int) -> str:
    return f"{count} conversación" if count == 1 else f"{count} conversaciones"


def limit_reached(limit: int) -> str:
    return (f"Llegaste al tope de {limit} preguntas en 24 horas. Se libera a medida que pasan las 24 horas "
            "de cada pregunta.")


def more_than_fit(left: int) -> str:
    noun = "pregunta" if left == 1 else "preguntas"
    return f"Llegaron más preguntas de las que entran en una respuesta: sigo enseguida con {left} {noun} más."


def quota_retry(retry_after_s: int) -> str:
    when = f"{retry_after_s} s" if retry_after_s < 60 else f"{math.ceil(retry_after_s / 60)} min"
    return f"Llegamos al límite de uso de la IA. Reintento en {when}."


def failure_retry(error: str, delay_s: int) -> str:
    return f"No pude responder ({error}). Reintento en {delay_s} s."


def gave_up(error: str) -> str:
    return f"No pude responder estas preguntas: {error}. Mencioname de nuevo para reintentar."


def not_answered(question: str) -> str:
    return (f"No llegué a responder «{slack_text.shortened(question, 120)}». Mencioname de nuevo si todavía "
            "lo necesitás.")


def answer_header(mentions: list[str], questions: list[str]) -> str:
    """Who the answer is for and what they asked, so a busy thread reads like a list of replies."""
    who = _joined(mentions)
    shown = [f"«{slack_text.escape(slack_text.shortened(question, 90))}»" for question in questions[:2]]
    rest = f" y {len(questions) - 2} más" if len(questions) > 2 else ""
    asked = f" · {' · '.join(shown)}{rest}" if shown else ""
    return f"Para {who}{asked}" if who else asked.removeprefix(" · ")


def sources(labels: list[str], failed: list[str]) -> str:
    if not labels:
        return ""
    shown = [f"{label} (falló)" if label in failed else label for label in labels]
    return f"Leyó: {', '.join(slack_text.escape(label) for label in shown)}"


def asked_for(user_id: str, question: str) -> str:
    return f"<@{user_id}> preguntó: {slack_text.escape(question)}"


def _joined(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"
