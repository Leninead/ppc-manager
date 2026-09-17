"""A few loose figures read at a glance: the state of an account or a campaign."""
from core.chat_components.base import (INK, LINE, MUTED, SURFACE, TONE_COLOR, TONE_SCHEMA, Component, items_of,
                                       one_line, text_value, tone_of)

_ITEM = {"type": "object", "additionalProperties": False, "required": ["label", "value", "detail", "tone"],
         "properties": {"label": {"type": "string"}, "value": {"type": "string"},
                        "detail": {"type": "string"}, "tone": TONE_SCHEMA}}


def _clean(block: dict) -> dict | None:
    items = [{"label": text_value(item.get("label")), "value": text_value(item.get("value")),
              "detail": text_value(item.get("detail")), "tone": tone_of(item.get("tone"))}
             for item in items_of(block)]
    items = [item for item in items if item["value"]]
    return {"kind": "kpis", "items": items} if items else None


def _render(block: dict) -> str:
    cards = "".join(
        f'<div style="background:{SURFACE};border:1px solid {LINE};border-radius:10px;padding:8px 10px;min-width:0">'
        f'<div style="font-size:12px;line-height:1.3;color:{MUTED}">{one_line(item["label"])}</div>'
        f'<div style="font-size:20px;line-height:1.3;font-weight:600;color:{TONE_COLOR.get(item["tone"], INK)}">'
        f'{one_line(item["value"])}</div>'
        + (f'<div style="font-size:12px;line-height:1.3;color:{MUTED}">{one_line(item["detail"])}</div>'
           if item["detail"] else "")
        + "</div>" for item in block["items"])
    columns = min(len(block["items"]), 2)
    return (f'<div style="display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));gap:8px;'
            f'margin:2px 0 10px 0">{cards}</div>')


def _plain(block: dict) -> str:
    return "\n".join(f'{item["label"]}: {item["value"]}' + (f' ({item["detail"]})' if item["detail"] else "")
                     for item in block["items"])


def _strings(block: dict, apply) -> dict:
    return {**block, "items": [{**item, "label": apply(item["label"]), "value": apply(item["value"]),
                                "detail": apply(item["detail"])} for item in block["items"]]}


COMPONENT = Component(
    kind="kpis",
    fields={"items": {"type": "array", "minItems": 1, "items": _ITEM}},
    purpose="Dos a cuatro cifras sueltas que se leen de un vistazo: el estado de una cuenta o de una campaña.",
    looks=("tarjetas de a dos por fila: arriba la etiqueta chica en gris, al medio la cifra grande, abajo un "
           "detalle chico en gris; tone colorea la cifra."),
    limits=('de 2 a 4 tarjetas; etiqueta de hasta tres palabras ("ACoS", "Gasto sin ventas"); la cifra con su '
            'unidad y nada más; detalle de hasta cinco palabras ("target 30%") o vacío; no va cuando la pregunta '
            "pide un solo dato: ese dato se contesta en el text."),
    prose=False,
    clean=_clean,
    render=_render,
    plain=_plain,
    strings=_strings,
    example={"kind": "kpis", "items": [
        {"label": "ACoS", "value": "48.8%", "detail": "target 30%", "tone": "bad"},
        {"label": "Órdenes", "value": "198", "detail": "", "tone": "neutral"}]},
)
