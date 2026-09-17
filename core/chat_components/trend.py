"""The shape of one series over time."""
import math

from core.chat_components.base import (INK, LINE, MUTED, TONE_COLOR, TONE_SCHEMA, Component, list_of, number,
                                       one_line, text_value, tone_of)

_NEUTRAL_LINE = "#5F5B53"
# The drawing box. The SVG keeps its aspect ratio, so the last point stays round.
_W, _H, _PAD = 300.0, 56.0, 6.0


def _clean(block: dict) -> dict | None:
    """Fewer than two numbers draw no line; what the block still says is kept as text."""
    label, display = text_value(block.get("label")), text_value(block.get("display"))
    points = [value for value in (number(p) for p in list_of(block.get("points"))) if value is not None]
    if len(points) < 2:
        said = ": ".join(part for part in (label, display) if part)
        return {"kind": "text", "text": said} if said else None
    return {"kind": "trend", "label": label, "display": display, "points": points,
            "start": text_value(block.get("start")), "end": text_value(block.get("end")),
            "tone": tone_of(block.get("tone"))}


def _coordinates(points: list[float]) -> list[tuple[float, float]]:
    low, high = min(points), max(points)
    span = high - low
    flat = span == 0 or not math.isfinite(span)  # a span that overflows cannot be scaled, so it draws flat
    step = (_W - 2 * _PAD) / (len(points) - 1)
    return [(round(_PAD + i * step, 1),
             round(_H / 2 if flat else _H - _PAD - (value - low) / span * (_H - 2 * _PAD), 1))
            for i, value in enumerate(points)]


def _render(block: dict) -> str:
    color = TONE_COLOR.get(block["tone"], _NEUTRAL_LINE)
    coordinates = _coordinates(block["points"])
    line = " ".join(f"{x},{y}" for x, y in coordinates)
    last_x, last_y = coordinates[-1]
    header = ('<div style="display:flex;justify-content:space-between;gap:12px;font-size:14px;line-height:1.35">'
              f'<span style="color:{INK}">{one_line(block["label"])}</span>'
              f'<span style="color:{TONE_COLOR.get(block["tone"], INK)};font-weight:600;white-space:nowrap">'
              f'{one_line(block["display"])}</span></div>')
    chart = (f'<svg viewBox="0 0 {_W:g} {_H:g}" width="100%" style="display:block;margin:4px 0 2px 0" '
             f'role="img" aria-label="{one_line(block["label"])}">'
             f'<line x1="0" y1="{_H - 1:g}" x2="{_W:g}" y2="{_H - 1:g}" stroke="{LINE}" stroke-width="1"/>'
             f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
             'stroke-linejoin="round" stroke-linecap="round"/>'
             f'<circle cx="{last_x}" cy="{last_y}" r="3.5" fill="{color}"/></svg>')
    footer = ('<div style="display:flex;justify-content:space-between;font-size:12px;'
              f'color:{MUTED}"><span>{one_line(block["start"])}</span><span>{one_line(block["end"])}</span></div>'
              if block["start"] or block["end"] else "")
    return f'<div style="margin:2px 0 10px 0">{header}{chart}{footer}</div>'


def _plain(block: dict) -> str:
    points = " → ".join(f"{value:g}" for value in block["points"])
    ends = [end for end in (block["start"], block["end"]) if end]
    period = f" ({' a '.join(ends)})" if ends else ""
    head = ": ".join(part for part in (block["label"], block["display"]) if part)
    return f"{head}\n{points}{period}"


def _strings(block: dict, apply) -> dict:
    return {**block, "label": apply(block["label"]), "display": apply(block["display"]),
            "start": apply(block["start"]), "end": apply(block["end"])}


COMPONENT = Component(
    kind="trend",
    fields={"label": {"type": "string"}, "display": {"type": "string"},
            "points": {"type": "array", "minItems": 2, "items": {"type": "number"}},
            "start": {"type": "string"}, "end": {"type": "string"}, "tone": TONE_SCHEMA},
    purpose=("La forma de una serie en el tiempo —si sube, baja o se estanca— cuando la fuente trae al menos "
             "tres valores en orden."),
    looks=("arriba la etiqueta a la izquierda y la cifra en negrita a la derecha; debajo una línea de ancho "
           "completo, sin ejes, con el último punto marcado; abajo el primer y el último período en gris; tone "
           "colorea la línea y la cifra."),
    limits=("una serie por componente; de 3 a 60 puntos, en orden cronológico y solo valores que trae la fuente; "
            'display es el valor final o el resumen ("25 órdenes el domingo"); start y end, los períodos de las '
            'puntas ("lun", "dom") o vacíos.'),
    prose=False,
    clean=_clean,
    render=_render,
    plain=_plain,
    strings=_strings,
    example={"kind": "trend", "label": "Órdenes diarias", "display": "25 el domingo",
             "points": [42, 45, 39, 51, 30, 28, 25], "start": "lun", "end": "dom", "tone": "bad"},
)
