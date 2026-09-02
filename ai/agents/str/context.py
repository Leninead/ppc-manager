"""What the STR agent receives and the shape it must answer in.

Serialization only: every number here was already computed by the module.
"""
from dataclasses import dataclass

import pandas as pd

NEG_PREFIX = "N"
HARV_PREFIX = "H"
MAX_CAMPAIGNS = 40


@dataclass
class StrData:
    cliente: str
    brand_terms: list
    target_acos: float          # Negatives tab slider
    precio: float               # Negatives tab price input
    cvr: float                  # account CVR computed from the file
    umbral_clicks: int          # Negatives rule 2 threshold
    umbral_spend: float         # Negatives rule 3 threshold
    harvest_target_acos: float  # Harvest tab slider
    harvest_precio: float       # Harvest tab price input
    kpis: dict                  # label -> formatted value (module's kpi_dict)
    campanas: list              # per-campaign aggregate records
    negativos: list             # df_neg records, module columns as-is
    harvest: list               # df_harv records, module columns as-is
    idioma: str = "es"          # output language: "es" | "en"
    cost_detected: bool = True  # False when the STR cost column was not found


def make_ids(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i + 1:02d}" for i in range(n)]


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
                              "description": "hasta 2 oraciones, salud contra el "
                                             "target ACoS anclada en cifras del "
                                             "documento KPIs"},
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
    return df.to_csv(index=False)


def build_context(d: StrData) -> tuple[str, list, dict]:
    marca = ", ".join(d.brand_terms) if d.brand_terms else "no declarada"
    params = (
        f"Cliente: {d.cliente}\n"
        f"Brand terms declarados por el AM: {marca}\n"
        f"CVR promedio del archivo: {d.cvr:.2f}%\n"
        f"Negatives — Target ACoS: {d.target_acos:.0f}% | Precio promedio: ${d.precio:.2f} | "
        f"Umbral clicks sin orders: {d.umbral_clicks} | Umbral spend sin orders: ${d.umbral_spend:.2f}\n"
        f"Harvest — Target ACoS: {d.harvest_target_acos:.0f}% | Precio promedio: ${d.harvest_precio:.2f}\n"
        f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        + ("Calidad de datos: columna de costo NO detectada — Spend y ACoS llegan "
           "en 0 (inválidos) y la regla R3 quedó suprimida; la lista de negativos "
           "está incompleta por eso. Columnas válidas: Clicks, Orders, Sales, "
           "Impressions, CVR, CTR.\n" if not d.cost_detected else
           "Calidad de datos: columna de costo detectada; métricas de gasto válidas.\n")
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
        negativos["CTR%"] = (negativos["Clicks"]
                             / negativos["Impressions"].replace(0, pd.NA)
                             * 100).astype(float).round(2).fillna(0)

    docs = [
        {"title": "Parámetros", "content": params},
        {"title": "KPIs de la cuenta (calculados por la app — usar tal cual)",
         "content": kpis},
        {"title": f"Performance por campaña (top {len(campanas)} por spend)",
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
