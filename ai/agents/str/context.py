"""What the STR agent receives and the shape it must answer in.

Serialization only: every number here was already computed by the module.
"""
from ai.agents import make_ids
from dataclasses import dataclass

import pandas as pd

from core.currency_format import currency_symbol, money

NEG_PREFIX = "N"
HARV_PREFIX = "H"
MAX_CAMPAIGNS = 40


@dataclass
class StrData:
    cliente: str
    brand_terms: list
    target_acos: float          # Negatives tab slider
    precio: float | None        # Negatives tab price input; None switches rule 3 off
    cvr: float                  # account CVR computed from the file
    umbral_clicks: int          # Negatives rule 2 threshold
    umbral_spend: float         # Negatives rule 3 threshold (inf without a price)
    harvest_target_acos: float  # Harvest tab slider
    harvest_precio: float | None  # Harvest tab price input; None leaves Bid Sugerido empty
    kpis: dict                  # label -> formatted value (module's kpi_dict)
    campanas: list              # per-campaign aggregate records
    negativos: list             # df_neg records, module columns as-is
    harvest: list               # df_harv records, module columns as-is
    idioma: str = "es"          # output language: "es" | "en"
    cost_detected: bool = True  # False when the STR cost column was not found
    currency_code: str = "USD"  # account currency; "" when the file did not say


# razon comes before categoria on purpose: autoregressive generation
# conditions the verdict on the reasoning already written.
_OPINION = {
    "type": "object",
    "properties": {
        "row_id": {"type": "string",
                   "description": "id exacto de la fila, tal como figura en el documento"},
        "razon": {"type": "string",
                  "description": "una sola oración: por qué el término es lo que es, "
                                 "citando cifras de su fila solo si fundamentan el juicio"},
        "categoria": {"enum": ["marca_propia", "competidor", "generico",
                               "atributo", "irrelevante"],
                      "description": "qué ES el término; precedencia marca_propia > "
                                     "competidor > atributo > generico"},
        "advertencia": {"type": ["string", "null"],
                        "description": "riesgo concreto que el AM debe mirar antes de "
                                       "ejecutar, o null (el default)"},
    },
    "required": ["row_id", "razon", "categoria", "advertencia"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "negativos": {"type": "array", "items": _OPINION},
        "harvest": {"type": "array", "items": _OPINION},
        "campanas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campaign": {"type": "string",
                                 "description": "nombre exacto como figura en el CSV"},
                    "diagnostico": {"type": "string",
                                    "description": "una o dos oraciones con el juicio y "
                                                   "la cifra de su fila que lo respalda"},
                },
                "required": ["campaign", "diagnostico"],
                "additionalProperties": False,
            },
        },
        # Canonical platform shape — core/ai_tab.synthesis_html renders it.
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: qué pasa con la cuenta en "
                                             "lenguaje llano y sin cifras; después la "
                                             "evidencia con una o dos cifras del "
                                             "documento KPIs contra el target ACoS; "
                                             "y qué tipo de problema es"},
                "week_actions": {"type": "array", "items": {"type": "string"},
                                 "description": "2 a 4 bullets, cada uno con una "
                                                "cifra ya existente en los "
                                                "documentos"},
                "mid_term": {"type": "array", "items": {"type": "string"},
                             "description": "0 a 2 bullets: re-chequeos o jugadas "
                                            "de 2-4 semanas; vacío es válido"},
                "risks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string",
                                     "description": "slug corto en mayúsculas del "
                                                    "riesgo (p.ej. DEFENSA_MARCA, "
                                                    "ATRIBUCION_DUPLICADA)"},
                            "detail": {"type": "string",
                                       "description": "1-2 oraciones con la cifra "
                                                      "que lo sostiene"},
                            "urgency": {"enum": ["ALTA", "MEDIA"]},
                        },
                        "required": ["type", "detail", "urgency"],
                        "additionalProperties": False,
                    },
                    "description": "1 a 3 riesgos, la exposición dominante primero",
                },
            },
            "required": ["situation", "week_actions", "mid_term", "risks"],
            "additionalProperties": False,
        },
    },
    "required": ["negativos", "harvest", "campanas", "synthesis"],
    "additionalProperties": False,
}


def _csv(records, prefix: str | None = None) -> str:
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    if prefix is not None and not df.empty:
        df = df.copy()
        df.insert(0, "row_id", make_ids(prefix, len(df)))
    # A fixed line ending keeps the stored fingerprint the same on Windows and Linux.
    return df.to_csv(index=False, lineterminator="\n")


def _missing_price_notes(d: StrData) -> str:
    # Empty when both prices are loaded, so a priced payload keeps its text and its digest.
    notes = ""
    if d.precio is None:
        notes += ("Precio del producto: NO cargado en Negatives — la regla R3 (gasto sin conversión) no se evaluó, "
                  "así que la lista de negativos no incluye los términos que gastaron sin convertir por esa regla.\n")
    if d.harvest_precio is None:
        notes += ("Precio del producto: NO cargado en Harvest — la columna Bid Sugerido llega vacía: no hay bids "
                  "calculados.\n")
    return notes


def build_context(d: StrData) -> tuple[str, list, dict]:
    marca = ", ".join(d.brand_terms) if d.brand_terms else "no declarada"
    params = (
        f"Cliente: {d.cliente}\n"
        f"Moneda de la cuenta: {d.currency_code or 'no informada'} (símbolo {currency_symbol(d.currency_code)})\n"
        f"Brand terms declarados por el AM: {marca}\n"
        f"CVR promedio del archivo: {d.cvr:.2f}%\n"
        f"Negatives — Target ACoS: {d.target_acos:.0f}% | Precio promedio: {money(d.precio, d.currency_code)} | "
        f"Umbral clicks sin orders: {d.umbral_clicks} | "
        f"Umbral spend sin orders: {money(d.umbral_spend, d.currency_code)}\n"
        f"Harvest — Target ACoS: {d.harvest_target_acos:.0f}% | "
        f"Precio promedio: {money(d.harvest_precio, d.currency_code)}\n"
        f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        + ("Calidad de datos: columna de costo NO detectada — Spend y ACoS llegan "
           "en 0 (inválidos) y la regla R3 quedó suprimida; la lista de negativos "
           "está incompleta por eso. Columnas válidas: Clicks, Orders, Sales, "
           "Impressions, CVR, CTR.\n" if not d.cost_detected else
           "Calidad de datos: columna de costo detectada; métricas de gasto válidas.\n")
        + _missing_price_notes(d)
        + "Listing context: NO disponible. Estos son los únicos valores operativos válidos."
    )
    kpis = "\n".join(f"{k}: {v}" for k, v in d.kpis.items())

    campanas = pd.DataFrame(d.campanas[:MAX_CAMPAIGNS])
    if not campanas.empty and {"Clicks", "Orders"} <= set(campanas.columns):
        # Bleeders must always get a diagnosis; clicks is the cost proxy.
        campanas["diagnostico_obligatorio"] = (
            (campanas["Clicks"] >= d.umbral_clicks) & (campanas["Orders"] == 0))

    negativos = pd.DataFrame(d.negativos)
    if not negativos.empty and {"Clicks", "Impressions"} <= set(negativos.columns):
        impressions = negativos["Impressions"].astype(float)
        negativos["CTR%"] = (negativos["Clicks"] / impressions.where(impressions > 0) * 100).round(2).fillna(0)

    docs = [
        {"title": "Parámetros", "content": params},
        {"title": "KPIs de la cuenta (calculados por la app — usar tal cual)",
         "content": kpis},
        {"title": f"Performance por campaña (top {len(campanas)} por "
                  f"{'spend' if d.cost_detected else 'clicks'})",
         "content": _csv(campanas)},
        {"title": f"Candidatos a negativizar ({len(d.negativos)} filas)",
         "content": _csv(negativos, NEG_PREFIX)},
        {"title": f"Candidatos a harvest ({len(d.harvest)} filas)",
         "content": _csv(d.harvest, HARV_PREFIX)},
    ]
    input_text = (
        "Analizá el Search Term Report según tu rol. Cubrí TODAS las filas de los "
        "documentos de candidatos (una opinión por row_id, ids exactos), diagnosticá "
        "las campañas que lo ameriten y cerrá con la síntesis ejecutiva."
    )
    return input_text, docs, OUTPUT_SCHEMA
