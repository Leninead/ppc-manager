"""What the Bulk Campañas agent receives and the shape it must answer in.

Serialization only: the diagnosis, the signals and every figure were already computed by the
module (core/amazon_ads/campaign_analyzer.py). The AI judges which campaigns to act on first and
why; it never reclassifies one.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

CAMPAIGN_PREFIX = "C"
MAX_CAMPAIGNS = 60
# The traffic light's names, in the order the module shows them.
DIAGNOSIS_NAMES = ("FANTASMA", "PAUSAR", "REVISAR", "ESCALAR", "OK")
CAUSES = ("SIN_ENTREGA", "SIN_CONVERSION", "COSTO_ALTO", "RELEVANCIA_BAJA", "TOPE_DE_PRESUPUESTO",
          "BAJA_VISIBILIDAD", "EN_APRENDIZAJE", "RENTABLE", "POCA_MUESTRA")
VERDICTS = ("ACTUAR", "ESPERAR", "INVESTIGAR")


@dataclass
class CampaignData:
    account_label: str          # profile the campaigns came from
    period_label: str           # date range on screen
    currency_code: str          # "" when the source did not declare one
    attribution_days: int       # 7 for sellers, 14 for vendors
    target_acos: float          # the analyzer's inputs, exactly as on screen
    spend_to_pause: float
    min_orders_to_scale: int
    enabled_campaigns: int      # enabled campaigns before the MAX_CAMPAIGNS cap
    counts: dict                # diagnosis name -> campaigns, over every enabled campaign
    pause_spend: float          # spend of the PAUSAR campaigns: spent without orders in the period
    provisional_days: list      # ISO days of the period whose attributed sales can still grow
    has_impressions: bool
    has_signals: bool           # budget per day, top-of-search share and start dates are present
    campaigns: list             # capped records, flagged first and then by spend
    idioma: str = "es"


# razon before causa and veredicto on purpose: autoregressive generation conditions the verdict
# on the reasoning already written.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "campaigns": {
            "type": "array",
            "maxItems": 12,
            "description": "el orden del array ES la prioridad: campaigns[0] es lo que el AM mira primero. "
                           "Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string", "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: qué pasa con esta campaña y por qué importa, citando "
                                             "la cifra del documento que lo sostiene"},
                    "causa": {"enum": list(CAUSES),
                              "description": "la causa más probable según las cifras de la fila"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "qué hacer con el diagnóstico que ya calculó el módulo: "
                                                 "actuar ahora, esperar o investigar antes"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón como algo a verificar"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de actuar, o null"},
                },
                "required": ["row_id", "razon", "causa", "veredicto", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: cómo está la cuenta a nivel campaña, anclado en una "
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
    "required": ["campaigns", "synthesis"],
    "additionalProperties": False,
}


def median_of(records: list, key: str) -> float:
    """The document's own median of `key`: the yardstick for "little evidence"."""
    values = sorted(float(record.get(key) or 0) for record in records)
    if not values:
        return 0.0
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def build_context(d: CampaignData) -> tuple[str, list, dict]:
    records = d.campaigns[:MAX_CAMPAIGNS]
    currency = d.currency_code or "no declarada"
    counts = ", ".join(f"{name} {int(d.counts.get(name, 0))}" for name in DIAGNOSIS_NAMES)
    params = (
        f"Cuenta: {d.account_label}\n"
        f"Período: {d.period_label or 'no informado'}\n"
        f"Moneda: {currency}\n"
        f"Atribución de ventas y órdenes: {d.attribution_days} días\n"
        + (f"Días provisorios: {', '.join(d.provisional_days)} — sus ventas atribuidas todavía pueden subir.\n"
           if d.provisional_days else "")
        + f"Target ACoS: {_number(d.target_acos)}%\n"
        f"Gasto mínimo para PAUSAR: {_number(d.spend_to_pause)}\n"
        f"Órdenes mínimas para ESCALAR: {d.min_orders_to_scale}\n"
        f"Campañas habilitadas: {d.enabled_campaigns}; por diagnóstico: {counts}.\n"
        f"Gasto de las campañas en PAUSAR (sin órdenes en el período): {_number(d.pause_spend)}\n"
        f"El documento trae {len(records)} campañas: primero las que tienen un diagnóstico distinto de OK o "
        "alguna señal, después las de mayor gasto.\n"
        + ("Sin truncamiento: viajaron todas las campañas habilitadas.\n" if d.enabled_campaigns <= len(records) else
           f"Quedaron {d.enabled_campaigns - len(records)} campañas fuera del documento; no existen para vos.\n")
        + f"Mediana de gasto entre las filas del documento: {_number(median_of(records, 'spend'))}; "
        f"mediana de clicks: {_number(median_of(records, 'clicks'))}.\n"
        + ("" if d.has_signals else
           "SIN SEÑALES: no hay presupuesto por día, share de top of search ni fecha de inicio de las campañas. "
           "No afirmes nada sobre presupuesto agotado, visibilidad ni antigüedad.\n")
        + ("" if d.has_impressions else
           "SIN IMPRESIONES: FANTASMA se calculó con clicks y no hay CTR.\n")
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Campañas habilitadas ({len(records)} filas)", "content": _campaigns_csv(records)},
    ]
    input_text = (
        "Analizá las campañas según tu rol: priorizá sobre cuáles actuar, dictá el veredicto sobre el "
        "diagnóstico que ya calculó el módulo y cerrá con la síntesis ejecutiva. Citá row_ids exactos del "
        "documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _campaigns_csv(records: list) -> str:
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame.insert(0, "row_id", make_ids(CAMPAIGN_PREFIX, len(frame)))
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return frame.to_csv(index=False, lineterminator="\n")


def _number(value) -> str:
    """12.0 -> "12", 12.5 -> "12.5": the same text on every machine for the same number."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
