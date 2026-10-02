"""One turn, several answers: the schema the model answers a batch with, built from the app's own components."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.chat import components

ASSISTANT_NAME = "Capybaras Assistant"

RULES = f"""<lote_slack>
Te llamás {ASSISTANT_NAME}: es tu nombre en Slack y en el chat de la app, y así te presentás cuando te preguntan quién sos o cómo te llamás.
Esta vez contestás en Slack, en un hilo donde escriben varias personas del equipo. Recibís los mensajes desde tu última respuesta; los que empiezan con un id (q1, q2…) te mencionan y son las preguntas, los demás son la conversación entre ellos. Tu salida es `answers`: una entrada por respuesta, con los ids de las preguntas que contesta en `questions` y sus componentes en `blocks`. Todo lo de <componentes> vale para cada respuesta por separado: cada una arranca con un text que contesta su pregunta.
- Contestá todas las preguntas, en el orden en que llegaron.
- Dos preguntas que piden lo mismo, o una que corrige a otra ("perdón, era M&B"), van en una sola respuesta con los dos ids: contestá la versión corregida.
- Una pregunta que sigue a otra ("¿y contra la semana anterior?") se contesta sobre la cuenta y el período de la anterior, sin repetir lo que esa respuesta ya dijo.
- Un mensaje que te menciona pero no te pregunta nada —un saludo, una mención al pasar, algo dirigido a otra persona— va en `skipped` con su id y una razón corta, nunca en `answers`.
- No nombres a quien pregunta ni lo saludes: Slack ya marca a quién va cada respuesta.
- Los adjuntos no los podés abrir: si una pregunta depende de uno, decilo en una línea.
</lote_slack>"""

GUIDE = components.GUIDE + "\n\n" + RULES

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["answers", "skipped"],
    "properties": {
        "answers": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["questions", "blocks"],
            "properties": {
                "questions": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "blocks": {"type": "array", "minItems": 1,
                           "items": {"anyOf": [component.schema() for component in components.CATALOG]}}}}},
        "skipped": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "reason"],
            "properties": {"question": {"type": "string"}, "reason": {"type": "string"}}}},
    },
}


@dataclass(frozen=True)
class BatchAnswer:
    question_ids: tuple[str, ...]
    blocks: list[dict]


@dataclass(frozen=True)
class BatchReply:
    answers: tuple[BatchAnswer, ...] = ()
    skipped: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


def read_reply(structured: object, question_ids: list[str], fallback_text: str = "") -> BatchReply:
    """The drawable answers, which questions each covers, and which ones nobody answered.

    Lenient like the app's `normalize`: an answer whose blocks cannot be drawn is dropped and its questions count
    as unanswered, and a reply that came as prose instead of the schema answers every question at once.
    """
    known = set(question_ids)
    answers: list[BatchAnswer] = []
    raw_answers = structured.get("answers") if isinstance(structured, dict) else None
    for raw in raw_answers if isinstance(raw_answers, list) else ():
        if not isinstance(raw, dict):
            continue
        blocks = components.normalize({"blocks": raw.get("blocks")})
        if not blocks:
            continue
        ids = tuple(dict.fromkeys(str(i) for i in raw.get("questions") or () if str(i) in known))
        answers.append(BatchAnswer(ids, blocks))
    if not answers and not isinstance(raw_answers, list) and fallback_text.strip():
        answers.append(BatchAnswer(tuple(question_ids), [{"kind": "text", "text": fallback_text.strip()}]))

    answered = {i for answer in answers for i in answer.question_ids}
    skipped: dict[str, str] = {}
    raw_skipped = structured.get("skipped") if isinstance(structured, dict) else None
    for raw in raw_skipped if isinstance(raw_skipped, list) else ():
        ident = str(raw.get("question") or "") if isinstance(raw, dict) else ""
        if ident in known and ident not in answered:
            skipped[ident] = str(raw.get("reason") or "").strip()
    missing = tuple(i for i in question_ids if i not in answered and i not in skipped)
    order = {ident: index for index, ident in enumerate(question_ids)}
    answers.sort(key=lambda answer: min((order[i] for i in answer.question_ids), default=len(order)))
    return BatchReply(tuple(answers), skipped, missing)
