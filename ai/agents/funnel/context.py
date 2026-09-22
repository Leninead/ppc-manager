"""What the Análisis de Funnel agent receives and the shape it must answer in.

Serialization only: the cross of search terms with campaigns, the harvest match type and the suggested campaign
names were already computed by the module (core/funnel/coverage.py). The AI judges what to act on first.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ROW_PREFIX = "F"
MAX_HARVEST = 40
MAX_GAPS = 40
MAX_IDLE = 30
VERDICTS = ("ACTUAR", "ESPERAR", "INVESTIGAR")


@dataclass
class FunnelData:
    account_label: str      # profile or uploaded file the data came from
    period_label: str       # date range on screen, or "" for a manual file
    currency_code: str      # "" when the source did not declare one
    attribution_days: int   # 7 for sellers, 14 for vendors
    matched_by: str         # how terms met their campaign: "Campaign ID" or "nombre de campaña"
    min_orders: int         # the harvest minimum on screen
    match_type: str         # the match type the suggested campaign names carry
    counts: dict            # the page's figures over the whole account, not only the rows below
    harvest: list           # capped records, most orders first
    gaps: list              # capped records, most spend first
    idle: list              # capped records, largest budget first
    idioma: str = "es"


# razon before veredicto on purpose: autoregressive generation conditions the verdict on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filas": {
            "type": "array",
            "maxItems": 12,
            "description": "el orden del array ES la prioridad: filas[0] es lo que el AM mira primero. "
                           "Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string", "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: qué pasa con esta fila y por qué importa, citando la "
                                             "cifra del documento que lo sostiene"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "qué hacer con lo que ya calculó el módulo: actuar ahora, esperar "
                                                 "o investigar antes"},
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
                              "description": "2-3 oraciones: cómo está el funnel de la cuenta, anclado en una "
                                             "cifra del documento"},
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
    "required": ["filas", "synthesis"],
    "additionalProperties": False,
}


def records_of(d: FunnelData) -> list:
    """Every row the documents carry, in row_id order: harvest, then gaps, then idle campaigns."""
    return d.harvest[:MAX_HARVEST] + d.gaps[:MAX_GAPS] + d.idle[:MAX_IDLE]


def build_context(d: FunnelData) -> tuple[str, list, dict]:
    harvest, gaps, idle = d.harvest[:MAX_HARVEST], d.gaps[:MAX_GAPS], d.idle[:MAX_IDLE]
    ids = make_ids(ROW_PREFIX, len(harvest) + len(gaps) + len(idle))
    harvest_ids, gap_ids, idle_ids = (ids[:len(harvest)], ids[len(harvest):len(harvest) + len(gaps)],
                                      ids[len(harvest) + len(gaps):])
    counts = "\n".join(f"- {label}: {_number(value)}" for label, value in d.counts.items())
    params = (
        f"Cuenta: {d.account_label}\n"
        f"Período: {d.period_label or 'no informado'}\n"
        f"Moneda: {d.currency_code or 'no declarada'}\n"
        f"Atribución de ventas y órdenes: {d.attribution_days} días\n"
        f"Cruce de search terms con campañas: por {d.matched_by}\n"
        f"Mínimo de órdenes para harvest: {d.min_orders}\n"
        f"Match type de las campañas sugeridas: {d.match_type}\n"
        f"Cifras del módulo sobre toda la cuenta:\n{counts}\n"
        + _cap_line("candidatos a harvest", len(d.harvest), len(harvest))
        + _cap_line("términos de campañas pausadas o inexistentes", len(d.gaps), len(gaps))
        + _cap_line("campañas activas sin search terms", len(d.idle), len(idle))
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [{"title": "Parámetros", "content": params}]
    for title, rows, row_ids in (("Candidatos a harvest", harvest, harvest_ids),
                                 ("Términos de campañas pausadas o inexistentes", gaps, gap_ids),
                                 ("Campañas activas sin search terms", idle, idle_ids)):
        if rows:
            docs.append({"title": f"{title} ({len(rows)} filas)", "content": _csv(rows, row_ids)})
    input_text = (
        "Analizá el funnel según tu rol: priorizá sobre qué filas actuar, dictá el veredicto sobre lo que ya "
        "calculó el módulo y cerrá con la síntesis ejecutiva. Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _cap_line(what: str, total: int, sent: int) -> str:
    if total <= sent:
        return f"Viajaron todos los {what}: {total}.\n"
    return f"De {total} {what} viajaron {sent}; los {total - sent} restantes no existen para vos.\n"


def _csv(rows: list, row_ids: list) -> str:
    # Each document is one group already: the column would repeat its title on every row.
    frame = pd.DataFrame(rows).drop(columns=["grupo"], errors="ignore")
    frame.insert(0, "row_id", row_ids)
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return frame.to_csv(index=False, lineterminator="\n")


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
