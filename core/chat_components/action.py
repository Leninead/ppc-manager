"""The next concrete step on the account, set apart at the end of an answer."""
from core.chat_components.base import ACCENT, Component, esc, md_bold, text_value


def _clean(block: dict) -> dict | None:
    text = text_value(block.get("text"))
    return {"kind": "action", "text": text} if text else None


def _render(block: dict) -> str:
    safe = md_bold(esc(block["text"])).replace("\n", "<br>")
    return (f'<div style="border-left:3px solid {ACCENT};padding:1px 0 1px 10px;'
            f'margin:4px 0 4px 0;font-weight:600">{safe}</div>')


COMPONENT = Component(
    kind="action",
    fields={"text": {"type": "string"}},
    purpose="El siguiente paso concreto sobre la cuenta, cuando lo hay: pausar, bajar un bid, revisar una campaña.",
    looks="una o dos oraciones en negrita con un borde naranja a la izquierda.",
    limits=("uno por respuesta y siempre al final; nombra la entidad y la cifra que lo justifica, en modo "
            'sugerencia ("pausar X liberaría $412; revisalo contra Y"), nunca como orden; nunca es una '
            "pregunta, una oferta de traer más datos ni un pedido al AM; si el AM te pidió hacer un cambio en la "
            "cuenta, no va action: el text dice que desde acá no se hace y en qué se apoya la decisión."),
    prose=True,
    clean=_clean,
    render=_render,
    plain=lambda block: block["text"],
    strings=lambda block, apply: {**block, "text": apply(block["text"])},
    example={"kind": "action", "text": "Pausar **Campaña A** liberaría $24.66 por semana; revisalo contra su historial."},
)
