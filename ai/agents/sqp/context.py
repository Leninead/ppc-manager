"""What the SQP agent receives and the shape it must answer in.

Serialization only: every number here was already computed by the module
(_compute_funnel_signals / _compute_account_rollup in search_query_performance).
"""
from dataclasses import dataclass, field

import pandas as pd

QUERY_PREFIX = "Q"
MAX_ROWS = 40

WARNING_TYPES = [
    "DEFENSA_MARCA_ROTA", "GEMAS_OCULTAS", "FUGA_CHECKOUT_HEAD_TERM",
    "CLUSTER_PREMIUM_RIESGO", "VOLUMEN_SIN_VISIBILIDAD", "COBERTURA_BAJA",
    "SIN_DATO_PRECIO_MASIVO", "INTEGRIDAD_EXPORT",
    "CAVEAT_ATRIBUCION_24H", "FOTO_SEMANAL_SIN_TENDENCIA",
]


@dataclass
class SqpData:
    brand: str                  # brand detected in the file (or "no detectada")
    brand_terms: list           # brand terms declared by the AM
    week: str                   # report range exactly as the file states it
    rollup: dict                # _compute_account_rollup output, as-is
    signal_rows: list           # top-40 rows of the signals frame, module columns as-is
    language: str = "es"        # output language: "es" | "en"
    defense_floor: float = 80.0
    extra: dict = field(default_factory=dict)


def make_ids(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i + 1:02d}" for i in range(n)]


# reasoning comes before every verdict on purpose: autoregressive generation
# conditions the labels on the reasoning already written.
_QUERY_OPINION = {
    "type": "object",
    "properties": {
        "row_id": {"type": "string",
                   "description": "id exacto de la fila, tal como figura en el documento"},
        "reasoning": {"type": "string",
                      "description": "una o dos oraciones con el juicio, citando >=2 "
                                     "cifras de su fila nombradas con el glosario, nunca por columna"},
        "query_type": {"enum": ["BRANDED", "COMPETIDOR", "COMPARATIVA", "GENERICA"],
                       "description": "is_own_brand=true fuerza BRANDED; el resto "
                                      "es juicio semántico sobre el texto de la query"},
        "funnel_diagnosis": {"enum": ["SIN_VISIBILIDAD", "FUGA_CTR", "FUGA_PDP",
                                      "FUGA_CHECKOUT", "MERCADO_DEBIL",
                                      "FUNNEL_SANO", "DOMINANTE",
                                      "DATOS_INSUFICIENTES"],
                             "description": "anclado en leak_stage y leak_is_own "
                                            "precomputados; SIN_VISIBILIDAD si "
                                            "is_invisible=true; DATOS_INSUFICIENTES "
                                            "forzoso con marca presente y "
                                            "sufficient_data=false"},
        "price_causality": {"enum": ["PRECIO_CAUSA_PROBABLE", "SHOCK_PRECIO_TARDIO",
                                     "PRECIO_DESCARTADO", "INDETERMINADO"],
                            "description": "solo evaluable en FUGA_PDP (usa gap_cart) "
                                           "y FUGA_CHECKOUT (usa gap_purchase); en "
                                           "cualquier otro diagnóstico: INDETERMINADO"},
        "action": {"enum": ["ESCALAR_BID", "AGREGAR_EXACT", "DEFENDER_MARCA",
                            "ARREGLAR_CREATIVO_SERP", "ARREGLAR_PDP",
                            "REVISAR_PRECIO_OFERTA", "REVISAR_LOGISTICA_BUYBOX",
                            "MONITOREAR", "IGNORAR"],
                   "description": "una sola, según la precedencia del prompt; "
                                  "DATOS_INSUFICIENTES fuerza MONITOREAR"},
        "confidence": {"enum": ["ALTA", "MEDIA", "BAJA"],
                       "description": "BAJA obliga a formular la acción como "
                                      "'verificar', nunca como 'ejecutar'"},
        "warning": {"type": ["string", "null"],
                    "description": "riesgo concreto que el AM debe mirar antes de "
                                   "ejecutar, o null (el default)"},
    },
    "required": ["row_id", "reasoning", "query_type", "funnel_diagnosis",
                 "price_causality", "action", "confidence", "warning"],
    "additionalProperties": False,
}

_RISK = {
    "type": "object",
    "properties": {
        "type": {"enum": WARNING_TYPES,
                 "description": "solo tipos cuyo pre-flag del rollup dio true, "
                                "más los dos standing (CAVEAT/FOTO)"},
        "detail": {"type": "string",
                   "description": "una o dos oraciones citando las cifras del rollup "
                                  "o de las filas que lo disparan"},
        "urgency": {"enum": ["ALTA", "MEDIA"]},
    },
    "required": ["type", "detail", "urgency"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {"type": "array", "items": _QUERY_OPINION},
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: salud de la semana anclada "
                                             "en los shares ponderados y la etapa "
                                             "dominante de fuga del rollup"},
                "week_actions": {"type": "array", "items": {"type": "string"},
                                 "description": "3 a 7 bullets ordenados por opp_usd: "
                                                "verbo + row_ids + cifra + qué se decide"},
                "mid_term": {"type": "array", "items": {"type": "string"},
                             "description": "0 a 3 bullets, oportunidades 2-4 semanas"},
                "risks": {"type": "array", "items": _RISK},
                "executive_summary": {"type": "string",
                                      "description": "4-6 líneas listas para Slack, tono "
                                                     "Capybaras: cifras primero, cero "
                                                     "adjetivos sin número, cierra con "
                                                     "las 3 próximas acciones"},
            },
            "required": ["situation", "week_actions", "mid_term",
                         "risks", "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["queries", "synthesis"],
    "additionalProperties": False,
}

_ROW_COLS = [
    "query", "volume", "volume_tier",
    "imp_b", "imp_t", "clk_b", "clk_t", "cart_b", "cart_t", "pur_b", "pur_t",
    "imp_share", "click_share", "cart_share", "purchase_share",
    "d1", "d2", "d3", "leak_stage", "leak_is_own",
    "ctr_index", "cart_index", "purchase_index",
    "gap_click", "gap_cart", "gap_purchase", "price_trend", "price_band",
    "price_self_diluted", "is_own_brand",
    "defense_breach_stage", "defense_breach_share",
    "sufficient_data", "hidden_gem", "is_invisible", "market_buys", "share_state",
    "speed_premium", "opp_usd",
]


def _csv(records, prefix: str | None = None) -> str:
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    if not df.empty:
        df = df[[c for c in _ROW_COLS if c in df.columns]].copy()
        if prefix is not None:
            df.insert(0, "row_id", make_ids(prefix, len(df)))
    return df.to_csv(index=False)


def _fmt_rollup(r: dict) -> str:
    shares, deltas = r.get("weighted_shares", {}), r.get("weighted_deltas", {})
    thresholds = r.get("thresholds", {})
    flags = r.get("pre_flags", {})
    lines = [
        f"Queries en el archivo: {r.get('n_queries')}",
        "Shares de cuenta ponderados por volumen (%): "
        + " | ".join(f"{k}: {v}" for k, v in shares.items()),
        "Deltas agregados de cascada (puntos): "
        + " | ".join(f"{k}: {v}" for k, v in deltas.items()),
        f"Etapa dominante de fuga (filas con datos): {r.get('dominant_leak_stage') or 'ninguna'}",
        f"Cobertura: {r.get('pct_rows_with_data')}% de las filas CON marca presente "
        f"tienen datos suficientes | {r.get('pct_invisible')}% del archivo sin "
        f"visibilidad (marca ausente) | {r.get('pct_no_price_data')}% sin dato de "
        f"precio | integridad shares vs export: {r.get('pct_integrity_ok')}% OK",
        f"Oportunidad total: ${r.get('total_opp_usd')} | "
        f"sin visibilidad: {r['invisible']['rows']} filas por ${r['invisible']['opp_usd']}",
        f"Gemas ocultas: {r['gems']['rows']} (top: {', '.join(r['gems']['top_queries']) or '—'})",
        f"Defensa de marca rota: {r['defense_broken']['rows']} filas "
        f"({', '.join(r['defense_broken']['queries']) or '—'})",
        f"Premium riesgo con fuga de conversión: {r.get('premium_risk_leaking')} filas",
        f"Cola fuera del top {MAX_ROWS}: {r['tail']['rows']} filas | "
        f"${r['tail']['opp_usd']} de oportunidad | {r['tail']['gems']} gemas | "
        f"{r['tail']['invisible']} sin visibilidad",
        "Umbrales adaptativos de este archivo: "
        + " | ".join(f"{k}: {v}" for k, v in thresholds.items()),
        "Pre-flags de riesgos (solo los true se redactan): "
        + " | ".join(f"{k}: {'true' if v else 'false'}" for k, v in flags.items()),
    ]
    return "\n".join(lines)


def build_context(d: SqpData) -> tuple[str, list, dict]:
    declared_terms = ", ".join(d.brand_terms) if d.brand_terms else "no declarados"
    params = (
        f"Marca detectada en el archivo: {d.brand}\n"
        f"Brand terms declarados por el AM: {declared_terms}\n"
        f"Semana del reporte: {d.week}\n"
        f"Piso de defensa BRANDED: {d.defense_floor:.0f}% de share por etapa\n"
        f"Idioma de salida: {'en (English)' if d.language == 'en' else 'es (español)'}\n"
        "Materialidad de deltas: relativa a este archivo (peor cuartil), no absoluta.\n"
        "CVR en este dominio: purchases/impressions del SQP — no comparable con el CVR "
        "por clicks de un Search Term Report.\n"
        "Atribución: purchases del SQP usan ventana de 24h — direccionales, jamás "
        "conciliables contra Business Report.\n"
        "Un solo archivo semanal: es una foto, no una tendencia."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": "Rollup de cuenta (calculado por la app — usar tal cual)",
         "content": _fmt_rollup(d.rollup)},
        {"title": f"Señales por query (top {len(d.signal_rows)} por prioridad)",
         "content": _csv(d.signal_rows, QUERY_PREFIX)},
    ]
    input_text = (
        "Analizá el Search Query Performance según tu rol. Emití una opinión por "
        "cada row_id del documento de señales (todas, ids exactos), y cerrá con la "
        "síntesis ejecutiva redactando solo los riesgos cuyo pre-flag dio true más "
        "los dos standing."
    )
    return input_text, docs, OUTPUT_SCHEMA
