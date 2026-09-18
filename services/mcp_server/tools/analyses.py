"""El índice de análisis guardados y el contenido de uno.

Es la herramienta que resuelve el problema de contexto: en vez de pegar el análisis de cada cuenta
en el prompt, el modelo ve QUÉ hay y baja sólo el que necesita.
"""
from __future__ import annotations

from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads.report_provider import ReportProvider, account_labels
from services.mcp_server.limits import page

# Los módulos con análisis guardado. Espejo de ai_analysis_module_allowed (migración 011): si se
# suma uno a la base y no acá, el índice lo ignora en silencio.
MODULES = ("str", "bid_optimizer")
MODULE_LABELS = {"str": "Search Term Report", "bid_optimizer": "Bid Optimizer"}


def list_analyses(rest, *, profile_id: str = "", offset: int = 0, limit: int = 60) -> dict:
    """Qué análisis guardados existen, por cuenta y módulo, con su período y cuándo se generaron.

    Es un índice: dice qué hay, no qué dice. Para leer uno, `get_analysis`.
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
        "synthesis": (analysis.result or {}).get("synthesis") or {},
        "rows": _rows(analysis),
    }


def _rows(analysis) -> dict:
    """Las filas que el análisis citó, con el nombre que usa cada módulo y acotadas como todo lo demás.

    M2 guarda dos listas propias; los demás módulos usan la columna genérica `records`. Las listas ya
    nacen acotadas al generarse, pero el techo se aplica igual: el día que un módulo guarde de más,
    el corte tiene que verse acá y no en el contexto del cliente.
    """
    named = (("negativos", analysis.negative_records), ("harvest", analysis.harvest_records),
             ("filas", analysis.records))
    return {name: page(rows).as_payload(what=f"filas de {name}")
            for name, rows in named if rows}
