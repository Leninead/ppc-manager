"""El índice de análisis guardados y el contenido de uno.

Es la herramienta que resuelve el problema de contexto: en vez de pegar el análisis de cada cuenta
en el prompt, el modelo ve QUÉ hay y baja sólo el que necesita.
"""
from __future__ import annotations

from ai.agents import make_ids
from ai.agents.row_annotation import annotate_row_ids, replace_row_ids, row_labels
from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads.report_provider import ReportProvider, account_labels
from services.mcp_server.limits import page

# Los módulos con análisis guardado. Espejo de ai_analysis_module_allowed (migraciones 011 y 014): si
# se suma uno a la base y no acá, el índice lo ignora en silencio.
MODULES = ("str", "bid_optimizer", "bulk_campaigns")
MODULE_LABELS = {"str": "Search Term Report", "bid_optimizer": "Bid Optimizer", "bulk_campaigns": "Bulk Campañas"}
# Cómo nombró el agente las filas de cada módulo: (grupo, prefijo del row_id, campo con el término).
# Copia de ai/agents/*/context.py, que esta imagen no trae; un test las mantiene iguales.
ROW_IDS = {
    "str": (("negativos", "N", "Search Term"), ("harvest", "H", "Search Term")),
    "bid_optimizer": (("filas", "A", "asin"),),
    "bulk_campaigns": (("filas", "C", "campaign"),),
}
_RECORDS = {"negativos": "negative_records", "harvest": "harvest_records", "filas": "records"}
# La situación de cada análisis viaja en el índice para comparar cuentas en una llamada; el resto
# de la síntesis, con get_analysis.
HEADLINE_MAX_CHARS = 600


def list_analyses(rest, *, profile_id: str = "", offset: int = 0, limit: int = 60) -> dict:
    """Qué análisis guardados existen, por cuenta y módulo, con su período, su target, su situación y sus riesgos.

    Alcanza para comparar cuentas en una llamada. Para las filas y el resto de la síntesis, `get_analysis`.
    """
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    wanted = [p for p in profiles if p.data_through is not None
              and (not profile_id or p.profile_id == profile_id)]
    if profile_id and not wanted:
        raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")

    store = AiAnalysisStore(rest)
    rows = []
    for module in MODULES:
        newest = store.latest_by_subject(module, [p.profile_id for p in wanted])
        by_subject = {analysis.subject_id: analysis for analysis in newest}
        for profile in wanted:
            analysis = by_subject.get(profile.profile_id)
            if analysis is None:
                continue
            rows.append({
                "account": labels[profile.profile_id],
                "profile_id": profile.profile_id,
                "module": module,
                "module_label": MODULE_LABELS.get(module, module),
                "window": {"from": analysis.window_start.isoformat() if analysis.window_start else None,
                           "to": analysis.window_end.isoformat() if analysis.window_end else None},
                "finished_at": analysis.finished_at.isoformat() if analysis.finished_at else None,
                "lang": analysis.lang,
                "target_acos": (analysis.params or {}).get("target_acos"),
                "situation": _headline(analysis),
                "risks": _risk_levels(analysis),
            })
    rows.sort(key=lambda row: (row["finished_at"] or "", row["account"]), reverse=True)
    payload = page(rows, offset=offset, limit=limit).as_payload(what="análisis guardados")
    payload["modules"] = list(MODULES)
    if not rows:
        payload["note"] = ("Ninguna cuenta tiene análisis guardado todavía. No es que no haya datos: "
                           "es que nadie generó un análisis.")
    return payload


def get_analysis(rest, *, profile_id: str, module: str) -> dict:
    """El último análisis guardado de una cuenta y un módulo: su síntesis y sus filas."""
    if module not in MODULES:
        raise ValueError(f"Módulo desconocido: {module!r}. Los que hay: {', '.join(MODULES)}.")
    profiles = ReportProvider(rest).profiles()
    profile = next((p for p in profiles if p.profile_id == profile_id), None)
    if profile is None:
        raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")

    found = AiAnalysisStore(rest).latest_by_subject(module, [profile_id])
    if not found:
        return {"account": account_labels(profiles)[profile_id], "module": module, "analysis": None,
                "note": (f"{MODULE_LABELS.get(module, module)} no tiene análisis guardado para esta "
                         "cuenta. Se genera solo cuando llegan datos nuevos, o a pedido desde la app.")}
    analysis = found[0]
    return {
        "account": account_labels(profiles)[profile_id],
        "profile_id": profile_id,
        "module": module,
        "module_label": MODULE_LABELS.get(module, module),
        "window": {"from": analysis.window_start.isoformat() if analysis.window_start else None,
                   "to": analysis.window_end.isoformat() if analysis.window_end else None},
        "finished_at": analysis.finished_at.isoformat() if analysis.finished_at else None,
        "currency": profile.currency_code,
        "synthesis": _annotated((analysis.result or {}).get("synthesis") or {}, _labels(analysis)),
        "rows": _rows(analysis),
    }


def _groups(analysis):
    """(grupo, prefijo, campo del término, filas) de cada lista que el análisis guardó."""
    for name, prefix, item_field in ROW_IDS.get(analysis.module, ()):
        records = getattr(analysis, _RECORDS[name]) or []
        if records:
            yield name, prefix, item_field, records


def _labels(analysis) -> dict:
    return {row_id: term for _, prefix, item_field, records in _groups(analysis)
            for row_id, term in row_labels(prefix, records, item_field).items()}


def _headline(analysis) -> str:
    """La situación, con cada fila nombrada por su término: en el índice no viajan las filas."""
    synthesis = (analysis.result or {}).get("synthesis") or {}
    text = replace_row_ids(str(synthesis.get("situation") or synthesis.get("executive_summary") or "").strip(),
                           _labels(analysis))
    if len(text) <= HEADLINE_MAX_CHARS:
        return text
    return text[:HEADLINE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _risk_levels(analysis) -> list[dict]:
    """Tipo y urgencia de cada riesgo, sin el detalle: alcanza para cruzar cuentas y el detalle está en get_analysis."""
    risks = ((analysis.result or {}).get("synthesis") or {}).get("risks") or []
    return [{"type": str(risk.get("type") or "").strip(), "urgency": str(risk.get("urgency") or "").strip().lower()}
            for risk in risks if isinstance(risk, dict)]


def _annotated(value, labels: dict):
    """Cada row_id que cita la síntesis, seguido de su término: sin eso, "N03" no dice nada fuera de la app."""
    if isinstance(value, str):
        return annotate_row_ids(value, labels)
    if isinstance(value, list):
        return [_annotated(item, labels) for item in value]
    if isinstance(value, dict):
        return {key: _annotated(item, labels) for key, item in value.items()}
    return value


def _rows(analysis) -> dict:
    """Las filas que el análisis citó, cada una con su row_id, acotadas como todo lo demás.

    Las listas ya nacen acotadas al generarse, pero el techo se aplica igual: el día que un módulo
    guarde de más, el corte tiene que verse acá y no en el contexto del cliente.
    """
    return {name: page([{"row_id": row_id, **row} for row_id, row in zip(make_ids(prefix, len(records)), records)])
            .as_payload(what=f"filas de {name}")
            for name, prefix, _, records in _groups(analysis)}
