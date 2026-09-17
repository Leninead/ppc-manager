"""What the Bid Optimizer agent receives and the shape it must answer in.

Serialization only: the bid, the CVR, the price and the ACoS were already computed by the
module. The AI judges whether each suggested bid is worth executing; the module keeps the math.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ASIN_PREFIX = "A"
MAX_ASINS = 60
MAX_CAMPAIGNS = 40


@dataclass
class BidData:
    account_label: str      # profile or uploaded file the data came from
    period_label: str       # date range on screen, or "" for a manual file
    currency_code: str      # "" when the source did not declare one
    target_acos: int        # the tab's slider
    price_source: str       # "Inventory Report" | "STR"
    asin_source: str        # how the ASIN was resolved, for the agent to weigh
    total_asins: int        # rows before the MAX_ASINS cap
    asins: list             # capped records: asin, clicks, orders, cvr, price,
                            # acos, bid_base, estado
    campaigns: list         # records: campaign, tipo, tos, pdp, spend, sales, acos, orders
    has_previous: bool = False   # las filas traen *_previo del tramo anterior del mismo largo
    idioma: str = "es"


# razon before veredicto on purpose: autoregressive generation conditions the
# verdict on the reasoning already written.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "bids": {
            "type": "array",
            "maxItems": 12,
            "description": "el orden del array ES la prioridad: bids[0] es lo que el AM toca "
                           "primero. Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string",
                               "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: por qué este bid merece esta acción, "
                                             "citando la cifra del documento que la sostiene"},
                    "veredicto": {"enum": ["SUBIR", "MANTENER", "BAJAR", "PAUSAR"],
                                  "description": "acción sobre el bid sugerido que ya calculó el "
                                                 "módulo, no un bid nuevo"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón como algo a "
                                                 "verificar, nunca como un hecho"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de ejecutar, o null"},
                },
                "required": ["row_id", "razon", "veredicto", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: dónde está parada la cuenta en "
                                             "eficiencia de bids, anclado en una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                 "description": "acciones de esta semana: verbo + row_ids + una "
                                                "cifra + qué se decide"},
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
                                      "description": "2 oraciones copiables a Slack: cifras "
                                                     "primero, cero adjetivos sin número"},
            },
            "required": ["situation", "week_actions", "mid_term", "risks", "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["bids", "synthesis"],
    "additionalProperties": False,
}


def clicks_median(records: list) -> int:
    """La mediana de clicks del propio documento: el ancla contra la que se mide "poca muestra".

    Sin ella, "confianza" es un juicio a ojo y 3 clicks pesan igual que 300.
    """
    clicks = sorted(int(record.get("clicks", 0)) for record in records)
    if not clicks:
        return 0
    middle = len(clicks) // 2
    return clicks[middle] if len(clicks) % 2 else (clicks[middle - 1] + clicks[middle]) // 2


def build_context(d: BidData) -> tuple[str, list, dict]:
    records = d.asins[:MAX_ASINS]
    campaigns = d.campaigns[:MAX_CAMPAIGNS]
    params = (
        f"Cuenta: {d.account_label}\n"
        f"Período: {d.period_label or 'no informado'}\n"
        f"Moneda: {d.currency_code or 'no declarada'}\n"
        f"Target ACoS del tab: {d.target_acos}%\n"
        f"Origen del precio: {d.price_source}\n"
        f"Origen del ASIN: {d.asin_source}\n"
        f"ASINs tras agrupar: {d.total_asins}; el documento trae {len(records)}, "
        "los de mayor spend.\n"
        + ("Sin truncamiento: viajaron todas las filas.\n" if d.total_asins <= len(records) else
           f"Quedaron {d.total_asins - len(records)} filas fuera del documento; no existen para vos.\n")
        + f"Campañas en el documento: {len(campaigns)}\n"
        f"Mediana de clicks entre las filas del documento: {clicks_median(records)}\n"
        + ("Cada fila trae además columnas *_previo: el mismo tramo de días inmediatamente anterior, "
           "para leer qué cambió.\n" if d.has_previous else
           "SIN PERÍODO ANTERIOR: no hay columnas *_previo, así que no se puede saber si algo mejoró "
           "o empeoró. No lo insinúes.\n")
        + ("" if any("pct_spend_validado" in record for record in records) else
           "SIN MATCH TYPE: no viene pct_spend_validado, así que no se sabe cuánto del gasto corre "
           "sobre targeting ya probado.\n")
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Bids sugeridos por ASIN ({len(records)} filas, top por spend)",
         "content": _asins_csv(records)},
    ]
    if campaigns:
        docs.append({"title": f"Placements sugeridos por campaña ({len(campaigns)} filas)",
                     "content": pd.DataFrame(campaigns).to_csv(index=False)})
    input_text = (
        "Analizá los bids sugeridos según tu rol: priorizá sobre qué ASINs actuar, dictá el "
        "veredicto sobre cada bid ya calculado y cerrá con la síntesis ejecutiva. "
        "Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _asins_csv(records: list) -> str:
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame.insert(0, "row_id", make_ids(ASIN_PREFIX, len(frame)))
    return frame.to_csv(index=False)
