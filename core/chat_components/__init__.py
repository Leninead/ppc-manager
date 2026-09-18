"""The components the chat can draw, and everything derived from that one list.

Each component is a module that declares what the model reads to choose it (what it
is for, how the panel draws it, its limits), the JSON schema its block must match,
and how a block is cleaned, drawn and read as plain text. From CATALOG come the
schema the provider holds the model to, the catalog the model reads, and the
panel's drawing: the model can only answer with what the panel can draw, and
adding a component is adding a module to CATALOG.
"""
from __future__ import annotations

from collections.abc import Callable

from core.chat_components import action, alert, bars, kpis, pie, table, text, trend
from core.chat_components.base import Component, list_of

CATALOG: tuple[Component, ...] = (text.COMPONENT, kpis.COMPONENT, table.COMPONENT, bars.COMPONENT,
                                  pie.COMPONENT, trend.COMPONENT, alert.COMPONENT, action.COMPONENT)
_BY_KIND = {component.kind: component for component in CATALOG}

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["blocks"],
    "properties": {"blocks": {"type": "array", "minItems": 1,
                              "items": {"anyOf": [component.schema() for component in CATALOG]}}},
}


def _guide() -> str:
    entries = "\n".join(
        f"- **{c.kind}**: {c.purpose} Se dibuja así: {c.looks}" + (f" Límites: {c.limits}" if c.limits else "")
        for c in CATALOG)
    data = ", ".join(c.kind for c in CATALOG if not c.prose)
    prose = ", ".join(c.kind for c in CATALOG if c.prose)
    return f"""<componentes>
Estás respondiendo en el chat de la app. Tu respuesta es una lista de componentes que el panel dibuja en orden, de arriba abajo, en un ancho de unos 420 px. Vos elegís cuáles, cuántos y en qué orden: el criterio es que el AM entienda la respuesta de un vistazo. Solo existen estos:

{entries}

Cómo elegir:
- Primero mirá qué pide la pregunta. Si pide un solo dato o un total —"¿cuál es el ACoS de X?", "¿cuánto suman los presupuestos de Y?"—, la respuesta es un único text de 1 a 3 oraciones con esa cifra adentro, y nada más: ni kpis que la muestren, ni table o bars con lo que se sumó, ni ese detalle escrito. Un dato comparado con su referencia —el ROAS contra su objetivo, el CPC contra el de la semana pasada— sigue siendo un solo dato: las dos cifras van en la oración. El detalle va solo si el AM lo pide.
- Si pide más que eso, antes de escribir decidí qué componentes van y qué cifras muestra cada uno: el text va arriba, pero se escribe sabiendo qué muestran los de abajo.
- Arrancá siempre con un text que conteste la pregunta en una o dos oraciones.
- Un componente se gana su lugar cuando muestra algo que una oración no muestra igual de claro.
- Cuando un gráfico muestra las cifras, va el gráfico y no una tabla: una sola métrica entre entidades va en bars; cómo se reparte un total entre sus partes, en pie; cómo se movió algo en el tiempo, en trend. La table queda para cuando cada entidad necesita dos o tres métricas a la vez. Un gráfico contesta la pregunta: si no tenés los datos que la contestan, decilo en el text y no dibujes otro gráfico en su lugar.
- Un listado va entero en un solo componente: todas las entidades que contestan la pregunta, también las que quedan un escalón más abajo, y nunca sigue en un text. Cuando las reglas del chat piden dar un listado entero, ese listado es el componente. Si no entra en los límites de uno, elegí otro que lo muestre completo.
- Si el AM pide una cantidad —"las 3 cuentas"—, el componente muestra exactamente esa cantidad. Si el text dice cuántas entidades muestra el componente, contalas en el componente antes de escribir el número.
- Una cifra que muestra un componente no aparece en ningún text ni alert: ni repetida, ni resumida en un rango ("entre $10.00 y $45.00"), ni como desglose de un total, ni siquiera la de la entidad que encabeza el listado. El text cuenta con palabras lo que esas cifras muestran: si las reglas del chat piden la cifra que sostiene una afirmación, esa cifra ya está a la vista en el componente. Mal: "el gasto sin ventas es 41.7% del total y el ACoS, 38.2% contra un target de 25%" arriba de tarjetas con esas cifras, o "la peor es X, con ACoS 91.4% contra un target de 25%, y le siguen Y (81.6%) y Z (57.9%)" arriba de la tabla que las lista. Bien: "la cuenta paga caro cada venta y más de la mitad del gasto no deja órdenes", con las cifras solo en las tarjetas, o "la peor es X, que se gasta en publicidad casi todo lo que vende", con las cifras solo en la tabla.
- Cuando el análisis trae una advertencia sobre lo que el AM pregunta, va en un alert, y el text contesta sin repetirla.
- Las cifras se copian textuales de la fuente, con su unidad. Una cuenta que la pregunta pide —un total, una diferencia— se hace, y se dice sobre qué se hizo ("suman $184.00 por día entre las 9 campañas activas"). En {prose} rige la negrita de las reglas del chat; en {data}, texto plano, sin ** ni guiones.
- tone, en los componentes que lo tienen: bad es el problema que señalás; good, lo sano o la oportunidad; neutral, todo lo demás, y es el valor por defecto: si todo tiene color, nada resalta. La dirección la da la métrica, no el signo: ACoS, CPC y gasto sin ventas son mejores cuanto más bajos; ventas, órdenes, ROAS, CVR y share, cuanto más altos.
</componentes>"""


GUIDE = _guide()


def normalize(structured: object) -> list[dict] | None:
    """The drawable blocks of a structured answer, in order, or None when nothing is drawable.

    Lenient on purpose: the provider already holds the answer to SCHEMA, and a block
    that still does not fit is cleaned or dropped here instead of failing the answer.
    A block of an unknown kind that carries text is kept as text."""
    if not isinstance(structured, dict):
        return None
    blocks: list[dict] = []
    for block in list_of(structured.get("blocks")):
        if not isinstance(block, dict):
            continue
        kind = block.get("kind")
        component = (_BY_KIND.get(kind) if isinstance(kind, str) else None) or text.COMPONENT
        cleaned = component.clean(block)
        if cleaned is not None:
            blocks.append(cleaned)
    return blocks or None


def render(blocks: list[dict]) -> str:
    return "".join(_BY_KIND[block["kind"]].render(block) for block in blocks)


def plain_text(blocks: list[dict]) -> str:
    """The answer as text, one paragraph per block: what copy and the carried conversation read."""
    return "\n\n".join(_BY_KIND[block["kind"]].plain(block) for block in blocks)


def map_strings(blocks: list[dict], apply: Callable[[str], str]) -> list[dict]:
    """The same blocks with `apply` run over every string the AM reads."""
    return [_BY_KIND[block["kind"]].strings(block, apply) for block in blocks]
