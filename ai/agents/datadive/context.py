"""What the DataDive agent receives and the shape it must answer in.

Serialization only: every number here was already computed by the module
(parse_mkl / keywords_to_mkl_df + the tab's filters). The AI judges, the
module keeps the math.
"""
from dataclasses import dataclass

import pandas as pd

KW_PREFIX = "K"
MAX_KEYWORDS = 120
_SV_SLOTS = 90     # core: the head of the niche, by volume
_TAIL_SLOTS = 30   # tail: the most relevant rows below the SV cut
# Canonical MKL columns, kept local on purpose: ai/ never imports from modules/
# (the agent must not depend on the parser layer).
_COL_SV = "SV"
_COL_RELEVANCE = "Relevance"


def select_keywords(df):
    """Rows that travel to the agent. Deterministic, and the module owns it.

    A top-N by SV describes only the head of the niche: the cheap, specific long
    tail — where conversion usually lives — fell out entirely, and with it the
    judgement skewed towards "expensive niche" because the sample was built from
    the most contested terms. A slice is reserved for the most relevant rows
    below the SV cut.
    """
    ordenado = df.sort_values(_COL_SV, ascending=False)
    nucleo = ordenado.head(_SV_SLOTS)
    cola = (ordenado.iloc[_SV_SLOTS:]
            .sort_values([_COL_RELEVANCE, _COL_SV], ascending=[False, False])
            .head(_TAIL_SLOTS))
    return pd.concat([nucleo, cola]).reset_index(drop=True)


@dataclass
class MklData:
    niche_label: str        # niche name (API) or uploaded file name
    fuente: str             # "API DataDive" | "Archivo"
    marketplace: str        # "" when unknown (file source)
    my_asin: str            # "" when the AM didn't set one
    min_sv: int             # tab filter
    min_rel: float          # tab filter (UI 0-10 scale)
    total_keywords: int     # filtered rows before the MAX_KEYWORDS cap
    competitor_asins: list
    keywords: list          # capped records: term, sv, relevance, sugg_bid,
                            # launch_score, mi_rank (int|None), comps_rankeando
    competitors: list | None = None  # optional records: asin, brand, price,
                                     # rating, reviews, sales_30d, revenue_30d,
                                     # kws_p1; last row = niche median
    idioma: str = "es"
    my_asin_en_niche: bool = True    # False = the declared ASIN has no rank
                                     # column in this dive, so an empty mi_rank
                                     # is missing data, not a missing ranking


def make_ids(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i + 1:02d}" for i in range(n)]


def _keywords_csv(records: list) -> str:
    df = pd.DataFrame(records)
    if not df.empty:
        df.insert(0, "row_id", make_ids(KW_PREFIX, len(df)))
    return df.to_csv(index=False)


# razon/racional come before the verdict fields on purpose: autoregressive
# generation conditions the judgement on the reasoning already written.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "maxItems": 8,
            "description": "ordenados por orden de ataque: clusters[0] es lo que "
                           "el AM trabaja primero. Cada row_id del documento "
                           "aparece en exactamente uno",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string",
                               "description": "nombre corto del cluster de intención"},
                    "racional": {"type": "string",
                                 "description": "una oración: qué agrupa y por qué "
                                                "le importa al AM"},
                    "row_ids": {"type": "array", "items": {"type": "string"},
                                "description": "row_ids exactos de las keywords "
                                               "del cluster"},
                    "match_type": {"enum": ["exact", "phrase", "broad",
                                            "product_targeting"],
                                   "description": "cómo entrar a este cluster; "
                                                  "product_targeting cuando son "
                                                  "ASINs o marcas ajenas"},
                    "prioridad": {"enum": ["alta", "media", "baja"],
                                  "description": "atacabilidad para este ASIN, "
                                                 "no tamaño del cluster"},
                },
                "required": ["nombre", "racional", "row_ids", "match_type",
                             "prioridad"],
                "additionalProperties": False,
            },
        },
        "gaps": {
            "type": "array",
            "maxItems": 10,
            "description": "el orden del array ES la prioridad: gaps[0] es el "
                           "primero a atacar. Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string",
                               "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: por qué este gap es "
                                             "atacable, citando la cifra que lo "
                                             "sostiene"},
                    "via": {"enum": ["PPC_AHORA", "LISTING_PRIMERO", "NO_ATACABLE"],
                            "description": "PPC_AHORA: se puede pujar hoy; "
                                           "LISTING_PRIMERO: sin relevancia en el "
                                           "listing la puja se quema; NO_ATACABLE: "
                                           "marca ajena, otra categoría o "
                                           "launch_score inviable"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón "
                                                 "como algo a verificar, nunca "
                                                 "como un hecho"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de "
                                                   "atacarlo, o null (el default)"},
                },
                "required": ["row_id", "razon", "via", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: qué es este niche y "
                                             "dónde está parado el ASIN propio, "
                                             "anclado en una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"},
                                 "maxItems": 3,
                                 "description": "acciones chicas de esta semana: "
                                                "verbo + row_ids + una cifra + qué "
                                                "se decide"},
                "mid_term": {"type": "array", "items": {"type": "string"},
                             "maxItems": 3,
                             "description": "oportunidades de 2 a 4 semanas"},
                "risks": {
                    "type": "array",
                    "maxItems": 4,
                    "description": "solo riesgos que se sostengan con una fila "
                                   "concreta del documento",
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
                                      "description": "2 oraciones copiables a "
                                                     "Slack: cifras primero, cero "
                                                     "adjetivos sin número"},
            },
            "required": ["situation", "week_actions", "mid_term", "risks",
                         "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["clusters", "gaps", "synthesis"],
    "additionalProperties": False,
}


def build_context(d: MklData) -> tuple[str, list, dict]:
    records = d.keywords[:MAX_KEYWORDS]
    params = (
        f"Niche: {d.niche_label}\n"
        f"Fuente de los datos: {d.fuente}\n"
        f"Marketplace: {d.marketplace or 'no informado'}\n"
        f"ASIN propio declarado por el AM: {d.my_asin or 'no declarado'}\n"
        + ("" if not d.my_asin else
           ("El ASIN propio figura entre los ASINs rastreados del niche.\n"
            if d.my_asin_en_niche else
            "CALIDAD DE DATOS: el ASIN propio NO figura entre los ASINs "
            "rastreados de este niche. mi_rank llega vacío en TODAS las filas "
            "por ausencia de dato, no porque el ASIN no rankee.\n"))
        + f"Filtros del tab: SV mínimo {d.min_sv} | Relevancia mínima {d.min_rel:.1f} "
        f"(escala 0-10)\n"
        f"Keywords tras el filtro: {d.total_keywords}; el documento trae "
        f"{len(records)}: las de mayor SV (bloque = nucleo) más las de mayor "
        f"relevancia por debajo de ese corte (bloque = cola).\n"
        + ("Sin truncamiento: viajaron todas las filas del filtro.\n"
           if d.total_keywords <= len(records) else
           f"Quedaron {d.total_keywords - len(records)} filas fuera del "
           "documento; no existen para vos.\n")
        + f"Competidores del niche: {len(d.competitor_asins)} ASINs\n"
        f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Keywords del niche ({len(records)} filas, top por SV)",
         "content": _keywords_csv(records)},
    ]
    if d.competitors:
        docs.append({
            "title": f"Competidores del niche ({len(d.competitors)} filas; "
                     "la última es la mediana del niche)",
            "content": pd.DataFrame(d.competitors).to_csv(index=False),
        })
    input_text = (
        "Analizá la Master Keyword List del niche según tu rol: agrupá las "
        "keywords en clusters de intención, priorizá los gaps atacables y cerrá "
        "con la síntesis ejecutiva. Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA
