"""What the PPC Insights agent receives and the shape it must answer in.

Serialization only: the health score, its five parts and every metric were already computed by the
module. The AI decides which ASINs to act on first and what weighs most on each one; it never
recomputes a figure.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ASIN_PREFIX = "P"
MAX_ASINS = 40
FOCUS_VALUES = ("DESPERDICIO", "ACOS", "CONVERSION", "BUYBOX", "FUNNEL", "ESCALAR", "MONITOREAR")

_PART_NAMES = {"cvr": "CVR", "buybox": "BuyBox", "acos": "ACoS", "funnel": "Funnel", "imp_share": "Impression Share"}
_SOURCE_OF_PART = {"buybox": "br", "funnel": "campaigns", "imp_share": "sqp"}
_SOURCE_NAMES = {"sqp": "SQP", "br": "Business Report", "campaigns": "Campaign CSV"}
_ORIGIN_NAMES = {"file": "columna de ASIN del archivo", "ad_group": "producto anunciado del ad group",
                 "campaign_name": "nombre de la campaña",
                 "several_asins": "ad group con varios ASINs y sin ASIN en el nombre", "without_asin": "sin ASIN"}


@dataclass
class InsightsData:
    account_label: str      # profile or uploaded file the report came from
    period_label: str       # date range on screen, or "" for a manual file
    currency_code: str      # "" when the source did not declare one
    target_acos: int        # the page's slider
    price: float | None     # average product price the AM typed; None when not declared
    asin_source: str        # file | attributed | none
    asin_spend_share: dict  # row origin -> % of the report's spend
    sources: dict           # {"sqp": bool, "br": bool, "campaigns": bool}
    brand_sqp: dict | None  # imp_share, purchase_share and sqp_gaps of the brand, when an SQP was loaded
    score_scale: dict       # health score part -> (points it can give, points without its source)
    wasted_spend_rule: tuple  # (minimum spend of a term, how many terms) behind gasto_sin_venta
    total_asins: int        # rows before the MAX_ASINS cap
    asins: list             # capped records, in row_id order
    idioma: str = "es"


# razon before foco on purpose: autoregressive generation conditions the focus on the reasoning written.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "asins": {
            "type": "array",
            "maxItems": 12,
            "description": "el orden del array ES la prioridad: asins[0] es lo que el AM mira primero. "
                           "Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string",
                               "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: qué pesa más en la salud de este ASIN, citando la "
                                             "cifra del documento que lo sostiene"},
                    "foco": {"enum": list(FOCUS_VALUES),
                             "description": "lo primero que el AM tiene que atender en este ASIN"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón como algo a verificar, nunca "
                                                 "como un hecho"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de actuar, o null"},
                },
                "required": ["row_id", "razon", "foco", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: cómo está la salud de los productos de la cuenta, "
                                             "anclada en una cifra del documento"},
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
                                      "description": "2 oraciones copiables a Slack: cifras primero, cero "
                                                     "adjetivos sin número"},
            },
            "required": ["situation", "week_actions", "mid_term", "risks", "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["asins", "synthesis"],
    "additionalProperties": False,
}


def build_context(d: InsightsData) -> tuple[str, list, dict]:
    records = d.asins[:MAX_ASINS]
    params = (
        f"Cuenta: {d.account_label}\n"
        f"Período: {d.period_label or 'no informado'}\n"
        f"Moneda: {d.currency_code or 'no declarada'}\n"
        f"Target ACoS: {d.target_acos}%\n"
        f"Precio promedio del producto: {_price_line(d.price)}\n"
        f"Origen del ASIN: {_asin_source_line(d)}\n"
        f"Fuentes cargadas además del Search Term Report: {_sources_line(d.sources)}\n"
        f"Partes del health score (máximo · valor sin dato): "
        + ", ".join(f"{_PART_NAMES[part]} {top:g} · {neutral:g}" for part, (top, neutral) in d.score_scale.items())
        + "\n"
        + _missing_parts_line(d)
        + _module_rules_line(d)
        + _brand_sqp_line(d.brand_sqp)
        + f"ASINs tras agrupar: {d.total_asins}; el documento trae {len(records)}, los de mayor gasto.\n"
        + f"Mediana de clicks entre las filas del documento: {_clicks_median(records)}\n"
        + ("Sin truncamiento: viajaron todas las filas.\n" if d.total_asins <= len(records) else
           f"Quedaron {d.total_asins - len(records)} filas fuera del documento; no existen para vos.\n")
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Salud por ASIN ({len(records)} filas, top por gasto)", "content": _asins_csv(records)},
    ]
    input_text = (
        "Analizá la salud de los ASINs según tu rol: priorizá en cuáles actuar, decí qué pesa más en cada uno "
        "y cerrá con la síntesis ejecutiva. Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _clicks_median(records: list) -> int:
    clicks = sorted(int(record.get("clicks") or 0) for record in records)
    if not clicks:
        return 0
    middle = len(clicks) // 2
    return clicks[middle] if len(clicks) % 2 else (clicks[middle - 1] + clicks[middle]) // 2


def _price_line(price) -> str:
    if price is None:
        return "no declarado"
    return f"{float(price):.2f} (lo escribió el AM, no sale de los reportes)"


def _asin_source_line(d: InsightsData) -> str:
    if d.asin_source == "file":
        base = "la columna de ASIN del archivo"
    elif d.asin_source == "attributed":
        base = ("el producto anunciado del ad group de cada término cuando anuncia uno solo; si anuncia varios, o "
                "el listado no vio el ad group, el ASIN del nombre de la campaña, aunque ese ad group no lo anuncie")
    else:
        base = "ninguno: ningún término tiene ASIN, y la única fila (ALL) es la cuenta entera"
    shares = " · ".join(f"{_ORIGIN_NAMES.get(origin, origin)} {share}%"
                        for origin, share in sorted(d.asin_spend_share.items(), key=lambda item: -item[1]))
    return f"{base}. Reparto del gasto: {shares}" if shares else base


def _sources_line(sources: dict) -> str:
    return "; ".join(f"{name} {'sí' if sources.get(key) else 'no'}" for key, name in _SOURCE_NAMES.items())


def _missing_parts_line(d: InsightsData) -> str:
    missing = [_PART_NAMES[part] for part in d.score_scale
               if part in _SOURCE_OF_PART and not d.sources.get(_SOURCE_OF_PART[part])]
    if not missing:
        return ""
    return (f"SIN DATO: {', '.join(missing)} valen el neutro en todas las filas porque no se cargó su fuente. "
            "Esos puntos no dicen nada del ASIN: no los leas como salud buena ni mala.\n")


def _module_rules_line(d: InsightsData) -> str:
    acos_neutral = d.score_scale["acos"][1]
    cvr_neutral = d.score_scale["cvr"][1]
    min_spend, terms = d.wasted_spend_rule
    return (f"Reglas del módulo: acos vacío = el ASIN gastó y no vendió en el período, y su parte de ACoS vale el "
            f"neutro ({acos_neutral:g}); un cvr de 0% también vale el neutro ({cvr_neutral:g}). gasto_sin_venta suma "
            f"sólo los hasta {terms} términos de mayor gasto con más de {min_spend:g} de gasto y 0 órdenes: no es "
            "todo el gasto sin venta del ASIN.\n")


def _brand_sqp_line(brand_sqp: dict | None) -> str:
    if not brand_sqp:
        return ""
    return (f"SQP de la marca (no de cada ASIN, así que pts_imp_share es igual en todas las filas): impression "
            f"share {brand_sqp.get('imp_share')}%, purchase share {brand_sqp.get('purchase_share')}%, "
            f"{brand_sqp.get('sqp_gaps')} queries con más de 500 impresiones donde la marca no aparece.\n")


def _asins_csv(records: list) -> str:
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame.insert(0, "row_id", make_ids(ASIN_PREFIX, len(frame)))
    # A fixed line ending keeps the digest the same on Windows and Linux.
    return frame.to_csv(index=False, lineterminator="\n")
