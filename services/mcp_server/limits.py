"""Respuestas acotadas: ninguna herramienta puede devolver algo de tamaño desconocido.

Un servidor MCP existe para que el modelo consulte en vez de recibir todo pegado. Si una
herramienta contesta con 177.000 filas —el tamaño real de una cuenta grande en este sistema—
vuelve el mismo problema que vino a resolver, pero ahora sin presupuesto que lo contenga: el
cliente se come la respuesta entera antes de poder decidir nada.

Por eso todo resultado se corta acá y el corte se declara. Un modelo que sabe que hay 177.000
filas y está viendo 200 puede pedir otra página o acotar la pregunta; uno que recibe 200 sin
saberlo, responde como si fueran todas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# Un turno de chat suele encadenar varias llamadas: el techo es por respuesta, no por conversación.
MAX_ROWS = 200
MAX_TEXT_CHARS = 20_000
# The AI provider cuts a tool result at 20000 characters; what rows leave is for the page's context.
MAX_ROWS_CHARS = 14_000


@dataclass(frozen=True)
class Page:
    """Un tramo de filas que sabe cuántas quedaron afuera."""

    rows: list
    total: int
    offset: int = 0

    @property
    def truncated(self) -> bool:
        return self.offset + len(self.rows) < self.total

    def as_payload(self, *, what: str) -> dict:
        payload = {"total": self.total, "showing": len(self.rows), "offset": self.offset}
        if self.truncated:
            payload["note"] = (
                f"Hay {self.total} {what} y esta respuesta trae {len(self.rows)}, desde la posición "
                f"{self.offset}. Pedí la página siguiente con offset={self.offset + len(self.rows)}, "
                "o acotá la consulta. No respondas como si estas fueran todas.")
        payload["rows"] = self.rows
        return payload


def page(rows: list, *, offset: int = 0, limit: int = MAX_ROWS) -> Page:
    """Un tramo seguro de `rows`. El límite pedido nunca supera el techo del servidor, y las filas
    nunca pasan de MAX_ROWS_CHARS caracteres: si una sola los pasa, va sola."""
    total = len(rows)
    start = max(0, int(offset))
    size = max(1, min(int(limit), MAX_ROWS))
    return Page(rows=_within_budget(rows[start:start + size]), total=total, offset=start)


def _within_budget(rows: list) -> list:
    kept, used = [], 0
    for row in rows:
        used += _serialized_size(row)
        if kept and used > MAX_ROWS_CHARS:
            break
        kept.append(row)
    return kept


def _serialized_size(row) -> int:
    # Nested and indented the way the MCP SDK writes a tool result, so the count matches what the provider cuts.
    return len(json.dumps({"rows": [row]}, ensure_ascii=False, indent=2, default=str))


def clip_text(text: str, *, what: str = "texto") -> str:
    """Texto largo cortado en un borde visible, nunca en silencio."""
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return (text[:MAX_TEXT_CHARS]
            + f"\n\n[…cortado: el {what} completo tiene {len(text)} caracteres y acá van "
              f"{MAX_TEXT_CHARS}.]")


@dataclass
class ToolRegistry:
    """Las herramientas del servidor, para que sumar un dominio sea agregar un módulo y no tocar el arranque."""

    tools: list = field(default_factory=list)

    def add(self, fn):
        self.tools.append(fn)
        return fn
