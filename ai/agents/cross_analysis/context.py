"""What the Análisis Cruzado agent receives and the shape it must answer in.

Serialization only: each SQP query's action, its market and account figures, INV-11's marks and each ASIN's totals were
computed by the module (core/cross_analysis/). The AI judges which of those actions the AM takes first.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ROW_PREFIX = "X"
MAX_QUERIES = 60
MAX_ASINS = 30
MAX_OPINIONS = 15
VERDICTS = ("ACTUAR", "ESPERAR", "INVESTIGAR")
_QUERY_CAP = ("Viajaron todas las queries del plan: {total}.",
              "De {total} queries del plan viajaron {sent}; las {left} restantes no existen para vos.")
_ASIN_CAP = ("Viajaron todos los ASINs: {total}.",
             "De {total} ASINs viajaron {sent}; los {left} restantes no existen para vos.")


@dataclass
class CrossData:
    account: str  # the Amazon Ads account and country of the search terms, or the Bulk File's name
    period: str  # the search terms' window; a Bulk File does not state it
    currency: str  # "" when the account declares none
    brand: str  # the brand the SQP names or the AM typed, "" when none
    exact_source: str  # where the already-exact mark comes from, or why it is unknown
    asin_source: str  # where each term's ASIN comes from as shares of spend, "" when there is nothing to say
    parameters: dict  # the AM's inputs on screen
    counts: dict  # the module's figures over the whole plan, not only the rows below
    queries: list  # records, the ones the AM can export first
    asins: list  # records, most ad spend first
    idioma: str = "es"
    from_bulk_file: bool = False  # the search terms and the exact keywords come from a Bulk File uploaded by hand


# razon before veredicto on purpose: autoregressive generation conditions the verdict on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "consultas": {
            "type": "array",
            "maxItems": MAX_OPINIONS,
            "description": "el orden del array ES la prioridad: consultas[0] es lo primero que el AM hace. Vacío es "
                           "una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string", "description": "id exacto de la query en el documento"},
                    "razon": {"type": "string",
                              "description": "una oración: por qué esta acción del módulo va en esta posición, "
                                             "citando la cifra del documento que lo sostiene"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "qué hacer con la acción que ya calculó el módulo: tomarla ahora, "
                                                 "esperar o investigar antes"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón como algo a verificar"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de actuar, o null"},
                },
                "required": ["row_id", "razon", "veredicto", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: qué dice el cruce entre lo que busca el mercado y lo "
                                             "que capturan las campañas, anclado en una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                 "description": "acciones de esta semana: verbo + row_ids + una cifra + qué se "
                                                "decide"},
                "mid_term": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                             "description": "oportunidades de 2 a 4 semanas"},
                "risks": {
                    "type": "array",
                    "maxItems": 4,
                    "description": "solo riesgos que se sostengan con una fila concreta del documento",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "detail": {"type": "string"},
                            "urgency": {"enum": ["alta", "media", "baja"]},
                        },
                        "required": ["type", "detail", "urgency"],
                        "additionalProperties": False,
                    },
                },
                "executive_summary": {"type": "string",
                                      "description": "2 oraciones copiables a Slack: cifras primero, cero adjetivos "
                                                     "sin número"},
            },
            "required": ["situation", "week_actions", "mid_term", "risks", "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["consultas", "synthesis"],
    "additionalProperties": False,
}


def records_of(d: CrossData) -> list:
    """The queries the documents carry, in row_id order."""
    return d.queries[:MAX_QUERIES]


def build_context(d: CrossData) -> tuple[str, list, dict]:
    queries, asins = d.queries[:MAX_QUERIES], d.asins[:MAX_ASINS]
    parameters = "\n".join(f"- {label}: {value}" for label, value in d.parameters.items())
    counts = "\n".join(f"- {label}: {_number(value)}" for label, value in d.counts.items())
    params = (
        _source_lines(d)
        + f"Moneda: {d.currency or 'no declarada'}\n"
        f"Marca del SQP: {d.brand or 'no detectada'}\n"
        f"Keywords Exact de la cuenta: {d.exact_source}\n"
        + (f"ASIN de cada search term: {d.asin_source}\n" if d.asin_source else "")
        + f"Parámetros en pantalla:\n{parameters}\n"
        f"Cifras del módulo sobre todo el plan:\n{counts}\n"
        + _cap_line(_QUERY_CAP, len(d.queries), len(queries))
        + _cap_line(_ASIN_CAP, len(d.asins), len(asins))
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Plan de Acción ({len(queries)} filas)",
         "content": _csv(queries, make_ids(ROW_PREFIX, len(queries)))},
    ]
    if asins:
        docs.append({"title": f"ASINs ({len(asins)} filas)", "content": _csv(asins)})
    input_text = (
        "Analizá el plan según tu rol: decidí qué acciones del módulo toma el AM primero, dictá el veredicto sobre lo "
        "que ya calculó el módulo y cerrá con la síntesis ejecutiva. Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _source_lines(d: CrossData) -> str:
    if d.from_bulk_file:
        return (f"Search terms: Bulk File subido a mano «{d.account}», no una cuenta de Amazon Ads conectada\n"
                "Período de los search terms: no informado, el Bulk File no dice qué días cubre\n"
                "Atribución de ventas y órdenes: el Bulk File no la dice; se leen como de 7 días\n")
    return f"Cuenta de Amazon Ads de los search terms: {d.account}\nPeríodo de los search terms: {d.period}\n"


def _cap_line(sentences: tuple[str, str], total: int, sent: int) -> str:
    everything, some = sentences
    if total <= sent:
        return everything.format(total=total) + "\n"
    return some.format(total=total, sent=sent, left=total - sent) + "\n"


def _csv(rows: list, row_ids: list | None = None) -> str:
    frame = pd.DataFrame(rows)
    if row_ids is not None:
        frame.insert(0, "row_id", row_ids)
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return frame.to_csv(index=False, lineterminator="\n")


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
