"""Prose: the component every answer starts with."""
from core.chat.components.base import Component, prose_html, text_value


def _clean(block: dict) -> dict | None:
    text = text_value(block.get("text"))
    return {"kind": "text", "text": text} if text else None


COMPONENT = Component(
    kind="text",
    fields={"text": {"type": "string"}},
    purpose="La prosa: contestar, explicar, listar nombres sin cifras.",
    looks='párrafos; lo que va entre ** sale en negrita y una línea que empieza con "- " es una viñeta.',
    limits="",
    prose=True,
    clean=_clean,
    render=lambda block: prose_html(block["text"]),
    plain=lambda block: block["text"],
    strings=lambda block, apply: {**block, "text": apply(block["text"])},
    example={"kind": "text", "text": "La cuenta corre a **ACoS 48.8%** contra un target de 30%.\n- Campaña A\n- Campaña B"},
)
