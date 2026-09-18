"""What the AM has to know before using the answer."""
from core.chat.components.base import Component, INK, esc, md_bold, text_value

LEVELS = ("info", "warning", "critical")
_STYLE = {"info": ("#F4F2EE", "#8A867C"), "warning": ("#FFF4E0", "#D98A00"),
          "critical": ("#FFEBEE", "#B71C1C")}


def _clean(block: dict) -> dict | None:
    text = text_value(block.get("text"))
    if not text:
        return None
    level = block.get("level") if block.get("level") in LEVELS else "info"
    return {"kind": "alert", "level": level, "text": text}


def _render(block: dict) -> str:
    background, border = _STYLE[block["level"]]
    safe = md_bold(esc(block["text"])).replace("\n", "<br>")
    return (f'<div style="background:{background};border-left:3px solid {border};border-radius:6px;'
            f'padding:7px 10px;margin:4px 0 10px 0;color:{INK};font-size:14px;line-height:1.5">{safe}</div>')


COMPONENT = Component(
    kind="alert",
    fields={"level": {"enum": list(LEVELS)}, "text": {"type": "string"}},
    purpose=("Algo que el AM tiene que saber antes de usar la respuesta: datos incompletos o viejos, una "
             "advertencia del análisis, un límite de lo que se pudo leer."),
    looks=("una caja de fondo suave con un borde a la izquierda: gris para info, ámbar para warning, rojo para "
           "critical; el texto va normal, sin título."),
    limits=("una o dos oraciones; como mucho una por respuesta; avisa, no recomienda: el paso a seguir va en "
            "action; critical solo cuando usar la respuesta sin leerlo lleva a un error."),
    prose=True,
    clean=_clean,
    render=_render,
    plain=lambda block: block["text"],
    strings=lambda block, apply: {**block, "text": apply(block["text"])},
    example={"kind": "alert", "level": "warning",
             "text": "El análisis no tiene brand terms declarados: no separa marca propia de conquista."},
)
