"""The documents a chat turn opens with: the analysis on screen and the earlier analyses of the same account.

A chat session reads them once; the provider keeps them in the session it resumes afterwards.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ai.agents import make_ids
from ai.agents.str.context import HARV_PREFIX, NEG_PREFIX
from core.ai_analysis.store import StoredAnalysis
from core.currency_format import money

DISPLAY_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
PREVIOUS_ANALYSES = 3


def analysis_chat_documents(current: StoredAnalysis | None, previous: list[StoredAnalysis], *,
                            currency_code: str) -> list[dict]:
    docs = []
    if current is not None and current.result:
        docs.append({"title": "Análisis IA vigente del reporte que el AM está viendo",
                     "content": _current_analysis_text(current, currency_code)})
    if previous:
        docs.append({"title": f"Análisis IA anteriores de esta cuenta ({len(previous)}, del más nuevo al más viejo)",
                     "content": "\n\n".join(_summary_text(analysis, currency_code) for analysis in previous)})
    return docs


def _current_analysis_text(analysis: StoredAnalysis, currency_code: str) -> str:
    result = analysis.result or {}
    lines = [_header(analysis, currency_code), "", _synthesis_text(result.get("synthesis") or {})]
    lines += _opinion_lines("Candidatos a negativizar", NEG_PREFIX, analysis.negative_records,
                            result.get("negativos") or [], currency_code)
    lines += _opinion_lines("Candidatos a harvest", HARV_PREFIX, analysis.harvest_records,
                            result.get("harvest") or [], currency_code)
    campaigns = result.get("campanas") or []
    if campaigns:
        lines += ["", "Diagnóstico por campaña:"]
        lines += [f"- {campaign.get('campaign', '')}: {campaign.get('diagnostico', '')}" for campaign in campaigns]
    return "\n".join(lines)


def _summary_text(analysis: StoredAnalysis, currency_code: str) -> str:
    return "\n".join([_header(analysis, currency_code), _synthesis_text((analysis.result or {}).get("synthesis") or {})])


def _header(analysis: StoredAnalysis, currency_code: str) -> str:
    params = analysis.params
    brand_terms = ", ".join(params.get("brand_terms") or []) or "no declarados"
    return (
        f"Período: {_day(analysis.window_start)} a {_day(analysis.window_end)} · "
        f"generado {_moment(analysis.finished_at)} · idioma {analysis.lang}\n"
        f"Parámetros: Target ACoS negativos {params.get('target_acos')}% · "
        f"precio {_price(params.get('price'), currency_code, 'sin cargar, sin regla R3')} · "
        f"Target ACoS harvest {params.get('harvest_target_acos')}% · "
        f"precio harvest {_price(params.get('harvest_price'), currency_code, 'sin cargar, sin bids sugeridos')} · "
        f"clicks mínimos harvest {params.get('harvest_min_clicks')} · brand terms: {brand_terms}"
    )


def _synthesis_text(synthesis: dict) -> str:
    lines = [f"Situación: {synthesis.get('situation', '')}"]
    if synthesis.get("week_actions"):
        lines.append("Acciones sugeridas para la semana:")
        lines += [f"{index}. {action}" for index, action in enumerate(synthesis["week_actions"], 1)]
    if synthesis.get("mid_term"):
        lines.append("Mediano plazo:")
        lines += [f"- {item}" for item in synthesis["mid_term"]]
    if synthesis.get("risks"):
        lines.append("Riesgos:")
        lines += [f"- {risk.get('type', '')} ({risk.get('urgency', '')}): {risk.get('detail', '')}"
                  for risk in synthesis["risks"]]
    return "\n".join(lines)


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


def _day(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "?"


def _moment(value: datetime | None) -> str:
    return value.astimezone(DISPLAY_TIMEZONE).strftime("%d/%m/%Y %H:%M") if value else "?"


def _price(value, currency_code: str, missing: str) -> str:
    return money(float(value), currency_code) if value is not None else missing
