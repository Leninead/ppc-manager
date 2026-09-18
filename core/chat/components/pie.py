"""How a total splits into its parts."""
from core.chat.components import bars
from core.chat.components.base import INK, MUTED, Component, items_of, number, one_line, text_value

# Six is as many slices as the eye tells apart by color; past that the parts go in bars.
SLICE_COLORS = ("#E84000", "#F0A04B", "#5F5B53", "#9C978C", "#CFC6B4", "#E6E1D8")
MAX_SLICES = len(SLICE_COLORS)
# The ring is drawn with the classic dash trick: a circle whose circumference is 100 units, so a
# share in percent is its dash length, and a quarter turn back (25) starts it at twelve o'clock.
_RADIUS = 15.9155
_GAP = 0.8
_ITEM = {"type": "object", "additionalProperties": False, "required": ["label", "value", "display"],
         "properties": {"label": {"type": "string"}, "value": {"type": "number"}, "display": {"type": "string"}}}


def _clean(block: dict) -> dict | None:
    """A slice needs a positive number; one slice is a sentence, and too many to tell apart are bars."""
    metric = text_value(block.get("metric"))
    items = []
    for item in items_of(block):
        value = number(item.get("value"))
        label = text_value(item.get("label"))
        if value is None or value <= 0 or not label:
            continue
        items.append({"label": label, "value": value, "display": text_value(item.get("display")) or f"{value:g}"})
    if not items:
        return None
    if len(items) == 1:
        said = f'{items[0]["label"]} {items[0]["display"]}'
        return {"kind": "text", "text": f"{metric}: {said}" if metric else said}
    if len(items) > MAX_SLICES:
        return bars.COMPONENT.clean({"metric": metric, "items": [{**item, "tone": "neutral"} for item in items]})
    return {"kind": "pie", "metric": metric, "items": items}


def _shares(items: list[dict]) -> list[float]:
    total = sum(item["value"] for item in items)
    return [round(item["value"] / total * 100, 1) for item in items]


def _arcs(items: list[dict]) -> list[tuple[float, float]]:
    """(dash offset, dash length) of each slice, clockwise from twelve o'clock, with a thin gap between them."""
    total = sum(item["value"] for item in items)
    arcs, before = [], 0.0
    for item in items:
        share = item["value"] / total * 100
        arcs.append((round((25 - before) % 100, 2), round(share - _GAP if share > 2 * _GAP else share, 2)))
        before += share
    return arcs


def _render(block: dict) -> str:
    items = block["items"]
    rings = "".join(
        f'<circle cx="21" cy="21" r="{_RADIUS}" fill="none" stroke="{SLICE_COLORS[i]}" stroke-width="6" '
        f'stroke-dasharray="{dash} {round(100 - dash, 2)}" stroke-dashoffset="{offset}"/>'
        for i, (offset, dash) in enumerate(_arcs(items)))
    chart = (f'<svg viewBox="0 0 42 42" width="96" height="96" style="display:block;flex:none" role="img" '
             f'aria-label="{one_line(block["metric"])}">{rings}</svg>')
    legend = "".join(
        '<div style="display:flex;align-items:center;gap:8px;font-size:14px;line-height:1.35;margin:0 0 5px 0">'
        f'<span style="width:10px;height:10px;border-radius:2px;background:{SLICE_COLORS[i]};flex:none"></span>'
        f'<span style="color:{INK};min-width:0;flex:1">{one_line(item["label"])}</span>'
        f'<span style="color:{INK};white-space:nowrap">{one_line(item["display"])}</span>'
        f'<span style="color:{MUTED};white-space:nowrap;min-width:46px;text-align:right">{share:.1f}%</span></div>'
        for i, (item, share) in enumerate(zip(items, _shares(items))))
    metric = (f'<div style="font-size:12.5px;font-weight:600;color:{MUTED};margin-bottom:6px">'
              f'{one_line(block["metric"])}</div>') if block["metric"] else ""
    return (f'<div style="margin:2px 0 10px 0">{metric}'
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px">'
            f'{chart}<div style="flex:1;min-width:180px">{legend}</div></div></div>')


def _plain(block: dict) -> str:
    lines = [block["metric"]] if block["metric"] else []
    return "\n".join(lines + [f'{item["label"]}: {item["display"]} ({share:.1f}%)'
                              for item, share in zip(block["items"], _shares(block["items"]))])


def _strings(block: dict, apply) -> dict:
    return {**block, "metric": apply(block["metric"]),
            "items": [{**item, "label": apply(item["label"]), "display": apply(item["display"])}
                      for item in block["items"]]}


COMPONENT = Component(
    kind="pie",
    fields={"metric": {"type": "string"},
            "items": {"type": "array", "minItems": 2, "maxItems": MAX_SLICES, "items": _ITEM}},
    purpose=("Cómo se reparte un total entre sus partes: qué parte del gasto se lleva cada ASIN, cada campaña o "
             "cada tipo de match."),
    looks=("un anillo partido en porciones proporcionales y, al costado, una fila por parte con su color, su "
           "nombre, su cifra y el porcentaje del total, que calcula el panel."),
    limits=(f"de 2 a {MAX_SLICES} partes de un mismo total y de una sola métrica, de la más grande a la más chica; "
            "metric dice de qué total son las partes; value es el número sin unidad, mayor que cero, y display la "
            'cifra como la lee el AM ("$32.24"); el porcentaje no lo escribas: lo calcula el panel; si son más '
            "partes, va bars; no va cuando el AM pidió el total: el total se contesta en el text."),
    prose=False,
    clean=_clean,
    render=_render,
    plain=_plain,
    strings=_strings,
    example={"kind": "pie", "metric": "Gasto por campaña", "items": [
        {"label": "Campaña A", "value": 120.0, "display": "$120.00"},
        {"label": "Campaña B", "value": 60.0, "display": "$60.00"},
        {"label": "Campaña C", "value": 20.0, "display": "$20.00"}]},
)
