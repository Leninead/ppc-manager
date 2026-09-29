"""What the PPC Audit Pro agent receives and the shape it must answer in.

Serialization only: the KPIs, the structure checks, the segments and Target Graduation were already computed by the
module (core/ppc_audit/checks.py). The AI judges which findings to act on first.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ROW_PREFIX = "U"
MAX_MIXED = 20
MAX_CAMPAIGNS = 10
MAX_DUPLICATES = 20
MAX_GRADUATION = 40
MAX_WASTED_TERMS = 20
VERDICTS = ("ACTUAR", "ESPERAR", "INVESTIGAR")


@dataclass
class AuditData:
    account_label: str      # "cuenta · país" or the uploaded file
    period_label: str       # date range on screen, or "" for a Bulk File
    currency_code: str      # "" when the source did not declare one
    attribution_days: int | None  # 7 for sellers, 14 for vendors; None for a Bulk File
    source: str             # "Amazon Ads" or "Bulk File subido a mano"
    brand_terms: list       # what the AM typed, normalized
    counts: dict            # the module's figures over the whole account, not only the rows below
    missing: list           # what the source lacks, each with its reason
    segments: list          # SP / SB / SD performance by segment, without row_id
    mixed: list             # campaigns whose running keywords mix match types
    campaigns: list         # SP campaigns that spent the most
    duplicates: list        # the same keyword and match type running in two or more campaigns
    graduation: list        # keywords without impressions in campaigns with traffic, the actionable ones first
    wasted_terms: list      # SP search terms that spent the most without selling
    idioma: str = "es"


# razon before veredicto on purpose: autoregressive generation conditions the verdict on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "hallazgos": {
            "type": "array",
            "maxItems": 12,
            "description": "el orden del array ES la prioridad: hallazgos[0] es lo que el AM mira primero. "
                           "Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string", "description": "id exacto de la fila del documento"},
                    "razon": {"type": "string",
                              "description": "una oración: qué pasa con esta fila y por qué importa, citando la "
                                             "cifra del documento que lo sostiene"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "qué hacer con lo que ya encontró el módulo: actuar ahora, esperar "
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
                              "description": "2-3 oraciones: cómo está la cuenta según la auditoría, anclado en "
                                             "una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                 "description": "acciones de esta semana: verbo + row_ids + una cifra + qué se "
                                                "decide"},
                "mid_term": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                             "description": "oportunidades de 2 a 4 semanas"},
                "risks": {
                    "type": "array",
                    "maxItems": 4,
                    "description": "solo riesgos que se sostengan con una cifra o una fila concreta del documento",
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
    "required": ["hallazgos", "synthesis"],
    "additionalProperties": False,
}

_GROUPS = (
    ("mixed", MAX_MIXED, "Campañas con match types mixtos"),
    ("campaigns", MAX_CAMPAIGNS, "Campañas de Sponsored Products con más gasto"),
    ("duplicates", MAX_DUPLICATES, "Keywords duplicadas entre campañas"),
    ("graduation", MAX_GRADUATION, "Target Graduation: keywords sin impresiones en campañas con tráfico"),
    ("wasted_terms", MAX_WASTED_TERMS, "Search terms de Sponsored Products sin ventas"),
)


def records_of(d: AuditData) -> list:
    """Every row the documents carry, in row_id order: the groups one after the other."""
    return [record for group, cap, _ in _GROUPS for record in getattr(d, group)[:cap]]


def build_context(d: AuditData) -> tuple[str, list, dict]:
    ids = iter(make_ids(ROW_PREFIX, len(records_of(d))))
    counts = "\n".join(f"- {label}: {_value(value)}" for label, value in d.counts.items())
    missing = "\n".join(f"- {reason}" for reason in d.missing) or "- nada"
    params = (
        f"Cuenta: {d.account_label}\n"
        f"Fuente: {d.source}\n"
        f"Período: {d.period_label or 'no informado'}\n"
        f"Moneda: {d.currency_code or 'no declarada'}\n"
        f"Atribución de ventas y órdenes de Sponsored Products: "
        f"{f'{d.attribution_days} días' if d.attribution_days else 'la del archivo'}\n"
        f"Brand terms: {', '.join(d.brand_terms) or 'ninguno'}\n"
        f"Cifras del módulo sobre toda la cuenta:\n{counts}\n"
        f"Lo que la fuente no tiene:\n{missing}\n"
        + "".join(_cap_line(title, len(getattr(d, group)), min(cap, len(getattr(d, group))))
                  for group, cap, title in _GROUPS)
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [{"title": "Parámetros", "content": params}]
    if d.segments:
        docs.append({"title": f"Performance por segmento ({len(d.segments)} filas, sin row_id)",
                     "content": _csv(d.segments)})
    for group, cap, title in _GROUPS:
        rows = getattr(d, group)[:cap]
        if rows:
            docs.append({"title": f"{title} ({len(rows)} filas)",
                         "content": _csv(rows, [next(ids) for _ in rows])})
    input_text = (
        "Analizá la auditoría según tu rol: priorizá qué hallazgos atender, dictá el veredicto sobre lo que ya "
        "encontró el módulo y cerrá con la síntesis ejecutiva. Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _cap_line(title: str, total: int, sent: int) -> str:
    if total <= sent:
        return f"{title}: viajaron todas, {total}.\n"
    return f"{title}: de {total} viajaron {sent}; las {total - sent} restantes no existen para vos.\n"


def _csv(rows: list, row_ids: list | None = None) -> str:
    # Each document is one group already: the column would repeat its title on every row.
    frame = pd.DataFrame(rows).drop(columns=["grupo"], errors="ignore")
    if row_ids is not None:
        frame.insert(0, "row_id", row_ids)
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return frame.to_csv(index=False, lineterminator="\n")


def _value(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
