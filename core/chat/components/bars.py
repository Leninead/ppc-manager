"""The relative weight of one metric across entities."""
from core.chat.components.base import (INK, LINE, MUTED, TONE_COLOR, TONE_SCHEMA, Component, items_of, number,
                                       one_line, text_value, tone_of)

_NEUTRAL_BAR = "#B4B2A9"
_ITEM = {"type": "object", "additionalProperties": False, "required": ["label", "value", "display", "tone"],
         "properties": {"label": {"type": "string"}, "value": {"type": "number"},
                        "display": {"type": "string"}, "tone": TONE_SCHEMA}}


def _clean(block: dict) -> dict | None:
    """A bar needs a length: an item without a usable number is dropped, a negative one draws empty."""
    items = []
    for item in items_of(block):
        value = number(item.get("value"))
        label = text_value(item.get("label"))
        if value is None or not label:
            continue
        items.append({"label": label, "value": max(value, 0.0),
                      "display": text_value(item.get("display")) or f"{value:g}", "tone": tone_of(item.get("tone"))})
    if not items:
        return None
    return {"kind": "bars", "metric": text_value(block.get("metric")), "items": items}


def _render(block: dict) -> str:
    top = max(item["value"] for item in block["items"])
    metric = (f'<div style="font-size:12.5px;font-weight:600;color:{MUTED};margin-bottom:4px">'
              f'{one_line(block["metric"])}</div>') if block["metric"] else ""
    rows = "".join(
        '<div style="margin:0 0 7px 0">'
        '<div style="display:flex;justify-content:space-between;gap:12px;font-size:14px;line-height:1.35">'
        f'<span style="color:{INK};min-width:0">{one_line(item["label"])}</span>'
        f'<span style="color:{TONE_COLOR.get(item["tone"], INK)};white-space:nowrap">{one_line(item["display"])}</span>'
        '</div>'
        f'<div style="height:6px;border-radius:3px;background:{LINE};margin-top:3px">'
        f'<div style="height:6px;border-radius:3px;width:{_width(item["value"], top)}%;'
        f'background:{TONE_COLOR.get(item["tone"], _NEUTRAL_BAR)}"></div></div></div>'
        for item in block["items"])
    return f'<div style="margin:2px 0 10px 0">{metric}{rows}</div>'


def _width(value: float, top: float) -> float:
    if top <= 0 or value <= 0:
        return 0
    return round(max(value / top * 100, 1.5), 1)  # a real value never draws as nothing


def _plain(block: dict) -> str:
    lines = [block["metric"]] if block["metric"] else []
    return "\n".join(lines + [f'{item["label"]}: {item["display"]}' for item in block["items"]])


def _strings(block: dict, apply) -> dict:
    return {**block, "metric": apply(block["metric"]),
            "items": [{**item, "label": apply(item["label"]), "display": apply(item["display"])}
                      for item in block["items"]]}


COMPONENT = Component(
    kind="bars",
    fields={"metric": {"type": "string"}, "items": {"type": "array", "minItems": 1, "items": _ITEM}},
    purpose=("El peso relativo de una sola métrica entre entidades: quién gasta más, qué keyword tiene más "
             "volumen, qué cuenta tiene el ACoS más alto."),
    looks=("arriba el nombre de la métrica en gris; una fila por entidad con el nombre a la izquierda y la cifra "
           "a la derecha, y debajo una barra cuyo largo es proporcional al valor más alto; tone colorea la barra "
           "y la cifra (la barra es gris si es neutral)."),
    limits=("una sola métrica por componente; hasta 15 filas, en el orden en que se tienen que leer, y si son más "
            "entidades va una table; value es el número sin unidad y nunca negativo; display, la cifra como la lee "
            'el AM ("$32.24"); no muestra el detalle de un total que el AM pidió sumar.'),
    prose=False,
    clean=_clean,
    render=_render,
    plain=_plain,
    strings=_strings,
    example={"kind": "bars", "metric": "Gasto sin ventas", "items": [
        {"label": "Campaña A", "value": 203.8, "display": "$203.80", "tone": "bad"},
        {"label": "Campaña B", "value": 24.66, "display": "$24.66", "tone": "neutral"}]},
)
