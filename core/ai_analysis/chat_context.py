"""What the chat reads about a Search Term analysis: the one on screen and the earlier ones of the same account.

A chat session reads them once; the provider keeps them in the session it resumes afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ai.agents import make_ids
from ai.agents.row_annotation import annotate_row_ids, replace_row_ids, row_labels
from ai.agents.str.context import HARV_PREFIX, NEG_PREFIX
from ai.agents.synthesis_text import synthesis_text
from core.ai_analysis.store import StoredAnalysis
from core.currency_format import money

DISPLAY_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
PREVIOUS_ANALYSES = 3


@dataclass(frozen=True)
class InMemoryAnalysis:
    """An analysis of an uploaded file: never stored, read with the same text as a stored one."""

    result: dict | None
    params: dict
    lang: str
    finished_at: datetime | None
    negative_records: list = field(default_factory=list)
    harvest_records: list = field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None


def in_memory_analysis(result: dict | None, *, params: dict, lang: str, finished_at: float | None,
                       negative_records: list, harvest_records: list) -> InMemoryAnalysis:
    """finished_at is the runtime's epoch seconds."""
    moment = datetime.fromtimestamp(finished_at, tz=timezone.utc) if finished_at else None
    return InMemoryAnalysis(result=result, params=params, lang=lang, finished_at=moment,
                            negative_records=list(negative_records), harvest_records=list(harvest_records))


def analysis_chat_documents(current: StoredAnalysis | None, previous: list[StoredAnalysis], *,
                            currency_code: str) -> list[dict]:
    docs = []
    if current is not None and current.result:
        docs.append({"title": "Análisis IA vigente del reporte que el AM está viendo",
                     "content": current_analysis_text(current, currency_code)})
    if previous:
        docs.append({"title": f"Análisis IA anteriores de esta cuenta ({len(previous)}, del más nuevo al más viejo)",
                     "content": "\n\n".join(analysis_summary_text(analysis, currency_code) for analysis in previous)})
    return docs


def current_analysis_text(analysis: StoredAnalysis | InMemoryAnalysis, currency_code: str) -> str:
    result = analysis.result or {}
    lines = [_header(analysis, currency_code), "", annotate_row_ids(_synthesis(analysis), _terms_by_row_id(analysis))]
    lines += _opinion_lines("Candidatos a negativizar", NEG_PREFIX, analysis.negative_records,
                            result.get("negativos") or [], currency_code)
    lines += _opinion_lines("Candidatos a harvest", HARV_PREFIX, analysis.harvest_records,
                            result.get("harvest") or [], currency_code)
    campaigns = result.get("campanas") or []
    if campaigns:
        lines += ["", "Diagnóstico por campaña:"]
        lines += [f"- {campaign.get('campaign', '')}: {campaign.get('diagnostico', '')}" for campaign in campaigns]
    return "\n".join(lines)


def analysis_summary_text(analysis: StoredAnalysis, currency_code: str) -> str:
    """Header and synthesis only, with each row id replaced by its term: no table travels with it, and
    the same ids name other terms in the analysis on screen."""
    return "\n".join([_header(analysis, currency_code), replace_row_ids(_synthesis(analysis), _terms_by_row_id(analysis))])


def _synthesis(analysis: StoredAnalysis | InMemoryAnalysis) -> str:
    return synthesis_text((analysis.result or {}).get("synthesis") or {})


def _terms_by_row_id(analysis: StoredAnalysis | InMemoryAnalysis) -> dict:
    return {**row_labels(NEG_PREFIX, analysis.negative_records, "Search Term"),
            **row_labels(HARV_PREFIX, analysis.harvest_records, "Search Term")}


def _header(analysis: StoredAnalysis | InMemoryAnalysis, currency_code: str) -> str:
    params = analysis.params
    brand_terms = ", ".join(params.get("brand_terms") or []) or "no declarados"
    return (
        f"Período: {_period(analysis)} · "
        f"generado {_moment(analysis.finished_at)} · idioma {analysis.lang}\n"
        f"Parámetros: Target ACoS negativos {params.get('target_acos')}% · "
        f"precio {_price(params.get('price'), currency_code, 'sin cargar, sin regla R3')} · "
        f"Target ACoS harvest {params.get('harvest_target_acos')}% · "
        f"precio harvest {_price(params.get('harvest_price'), currency_code, 'sin cargar, sin bids sugeridos')} · "
        f"clicks mínimos harvest {params.get('harvest_min_clicks')} · brand terms: {brand_terms}"
    )


def _opinion_lines(title: str, prefix: str, records: list, opinions: list, currency_code: str) -> list[str]:
    if not records:
        return []
    by_id = {opinion.get("row_id"): opinion for opinion in opinions}
    lines = ["", f"{title} ({len(records)}):"]
    for row_id, record in zip(make_ids(prefix, len(records)), records):
        opinion = by_id.get(row_id, {})
        figures = (f"{record.get('Clicks', 0)} clicks · {record.get('Orders', 0)} órdenes · "
                   f"gasto {money(float(record.get('Spend') or 0), currency_code)}" if "Spend" in record
                   else f"{record.get('Clicks', 0)} clicks · {record.get('Orders', 0)} órdenes · "
                        f"ACoS {record.get('ACoS', 0)}%")
        warning = f" · advertencia: {opinion['advertencia']}" if opinion.get("advertencia") else ""
        lines.append(f"{row_id} · {record.get('Search Term', '')} · {record.get('Campaign', '')} · "
                     f"{record.get('Regla', '')} · {figures} → {opinion.get('categoria', 'sin opinión')}: "
                     f"{opinion.get('razon', '')}{warning}")
    return lines


def _period(analysis: StoredAnalysis | InMemoryAnalysis) -> str:
    if analysis.window_start is None and analysis.window_end is None:
        return "el del archivo subido"
    return f"{_day(analysis.window_start)} a {_day(analysis.window_end)}"


def _day(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "?"


def _moment(value: datetime | None) -> str:
    return value.astimezone(DISPLAY_TIMEZONE).strftime("%d/%m/%Y %H:%M") if value else "?"


def _price(value, currency_code: str, missing: str) -> str:
    return money(float(value), currency_code) if value is not None else missing
