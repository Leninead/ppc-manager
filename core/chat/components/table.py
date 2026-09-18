"""Several entities of one kind, compared on the same metrics."""
from core.chat.components.base import (INK, LINE, MUTED, TONE_COLOR, TONE_SCHEMA, Component, list_of, one_line,
                                       text_value, tone_of)

_CELL = {"type": "object", "additionalProperties": False, "required": ["value", "tone"],
         "properties": {"value": {"type": "string"}, "tone": TONE_SCHEMA}}


def _cell(cell: object) -> dict:
    if isinstance(cell, dict):
        return {"value": text_value(cell.get("value")), "tone": tone_of(cell.get("tone"))}
    return {"value": text_value(cell), "tone": "neutral"}


def _clean(block: dict) -> dict | None:
    """Nothing is cut: a wider table than the limits say scrolls, it does not lose a column."""
    rows = []
    for row in list_of(block.get("rows")):
        if not isinstance(row, list):
            continue
        cells = [_cell(cell) for cell in row]
        if any(cell["value"] for cell in cells):
            rows.append(cells)
    if not rows:
        return None
    columns = [text_value(column) for column in list_of(block.get("columns"))]
    width = max(len(columns), *(len(row) for row in rows))
    columns += [""] * (width - len(columns))
    rows = [row + [{"value": "", "tone": "neutral"}] * (width - len(row)) for row in rows]
    return {"kind": "table", "columns": columns, "rows": rows}


def _render(block: dict) -> str:
    """Names left, figures right, color only where the model marked a judgment."""
    def cell(tag: str, index: int, value: str, tone: str = "neutral") -> str:
        head = tag == "th"
        color = TONE_COLOR.get(tone) or (MUTED if head else INK)
        return (f'<{tag} style="text-align:{"left" if index == 0 else "right"};'
                f'font-weight:{600 if head else 400};font-size:{"12.5px" if head else "14px"};'
                f'color:{color};{"" if index == 0 else "white-space:nowrap;"}'
                f'padding:5px 0 5px {0 if index == 0 else 12}px;border:none;'
                f'border-bottom:1px solid {"#E0DCD4" if head else LINE};'
                f'background:transparent;vertical-align:top">{one_line(value)}</{tag}>')

    row_style = 'style="border:none;background:transparent"'
    head = "".join(cell("th", i, column) for i, column in enumerate(block["columns"]))
    body = "".join(f"<tr {row_style}>"
                   + "".join(cell("td", i, c["value"], c["tone"]) for i, c in enumerate(row))
                   + "</tr>" for row in block["rows"])
    return ('<div style="overflow-x:auto;margin:2px 0 10px 0">'
            '<table style="width:100%;border-collapse:collapse;border:none;margin:0;'
            f'line-height:1.35"><thead><tr {row_style}>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def _plain(block: dict) -> str:
    lines = [" | ".join(block["columns"])]
    lines += [" | ".join(cell["value"] for cell in row) for row in block["rows"]]
    return "\n".join(lines)


def _strings(block: dict, apply) -> dict:
    return {**block, "columns": [apply(column) for column in block["columns"]],
            "rows": [[{**cell, "value": apply(cell["value"])} for cell in row] for row in block["rows"]]}


COMPONENT = Component(
    kind="table",
    fields={"columns": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "array", "items": _CELL}}},
    purpose="Comparar varias entidades del mismo tipo con las mismas métricas: términos, campañas, cuentas, keywords.",
    looks=("nombres a la izquierda, cifras alineadas a la derecha, encabezado chico en gris y líneas finas entre "
           "filas; tone colorea la cifra."),
    limits=("hasta 3 columnas; la primera es la entidad con su nombre exacto; cada columna es una sola métrica, la "
            "misma en todas las filas, y si de cada entidad tenés cifras distintas no es una tabla; una celda lleva "
            'una sola cifra, nunca dos juntas; una fila por entidad, sin repetirla; una celda sin dato lleva "—"; no '
            "muestra el detalle de un total que el AM pidió sumar."),
    prose=False,
    clean=_clean,
    render=_render,
    plain=_plain,
    strings=_strings,
    example={"kind": "table", "columns": ["Cuenta", "ACoS", "Target"], "rows": [
        [{"value": "Cuenta A", "tone": "neutral"}, {"value": "98.8%", "tone": "bad"}, {"value": "21%", "tone": "neutral"}],
        [{"value": "Cuenta B", "tone": "neutral"}, {"value": "15.8%", "tone": "good"}, {"value": "30%", "tone": "neutral"}]]},
)
