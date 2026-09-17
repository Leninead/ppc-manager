"""Las cuentas de Amazon Ads sincronizadas y sus search terms.

Se apoya en core/amazon_ads/report_provider.py, que ya lee sin Streamlit: acá no hay lógica de
negocio nueva, sólo la forma en que un modelo la consulta.
"""
from __future__ import annotations

from datetime import date, timedelta

from core.ai_analysis.account_summaries import account_labels
from core.amazon_ads.report_provider import ProfileOption, ReportProvider
from services.mcp_server.limits import page

# Un modelo que pide "los search terms de la cuenta" no quiere 177.000 filas: quiere los que mueven
# la aguja. El orden por gasto convierte una consulta vaga en una respuesta útil.
DEFAULT_DAYS = 7
MAX_DAYS = 60


def list_accounts(rest) -> dict:
    """Las cuentas de Amazon Ads sincronizadas, con su país, moneda y hasta qué día tienen datos."""
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    rows = [{
        "account": labels[profile.profile_id],
        "profile_id": profile.profile_id,
        "country": profile.country_code,
        "currency": profile.currency_code,
        "status": profile.status,
        "data_from": profile.data_from.isoformat() if profile.data_from else None,
        "data_through": profile.data_through.isoformat() if profile.data_through else None,
    } for profile in profiles]
    rows.sort(key=lambda row: row["account"])
    return page(rows, limit=len(rows) or 1).as_payload(what="cuentas")


def top_search_terms(rest, *, profile_id: str, days: int = DEFAULT_DAYS, offset: int = 0,
                     limit: int = 50) -> dict:
    """Los search terms de mayor gasto de una cuenta en los últimos `days` días.

    El período se recorta a lo que la cuenta tiene sincronizado: pedir 60 días de una cuenta con 10
    devuelve esos 10 y lo dice, en vez de una ventana vacía.
    """
    profile = _profile(rest, profile_id)
    window_days = max(1, min(int(days), MAX_DAYS))
    end = profile.data_through
    start = max(profile.data_from or end, end - timedelta(days=window_days - 1))
    source = ReportProvider(rest).search_terms(profile, start, end)

    frame = source.frame
    if frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0,
                "window": _window(start, end), "currency": source.currency_code,
                "note": "La cuenta no tuvo búsquedas con clicks en ese período."}

    spend = _column(frame, "spend")
    ordered = frame.sort_values(spend, ascending=False) if spend else frame
    rows = [{str(name): _plain(value) for name, value in row.items() if not str(name).startswith("_")}
            for _, row in ordered.iterrows()]
    payload = page(rows, offset=offset, limit=limit).as_payload(what="search terms")
    payload["window"] = _window(start, end)
    payload["currency"] = source.currency_code
    if start != (profile.data_from or start) and window_days > (end - start).days + 1:
        payload["window_note"] = "El período se recortó a los días que la cuenta tiene sincronizados."
    return payload


def _profile(rest, profile_id: str) -> ProfileOption:
    for profile in ReportProvider(rest).profiles():
        if profile.profile_id == profile_id:
            if profile.data_through is None:
                raise ValueError(f"La cuenta {profile_id} todavía no tiene datos sincronizados.")
            return profile
    raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")


def _window(start: date, end: date) -> dict:
    return {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days + 1}


def _column(frame, keyword: str):
    return next((column for column in frame.columns if keyword in str(column).lower()), None)


def _plain(value):
    """JSON no sabe de numpy ni de Timestamp; el cliente MCP tampoco."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
