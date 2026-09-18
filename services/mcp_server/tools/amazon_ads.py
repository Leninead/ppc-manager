"""Las cuentas de Amazon Ads sincronizadas, sus search terms y su serie diaria.

Se apoya en core/amazon_ads/report_provider.py, que ya lee sin Streamlit: acá no hay lógica de
negocio nueva, sólo la forma en que un modelo la consulta.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from core import search_term_frame as canonical
from core.amazon_ads.report_provider import DayTotals, ProfileOption, ReportProvider, account_labels
from services.mcp_server.limits import page

# Un modelo que pide "los search terms de la cuenta" no quiere 177.000 filas: quiere los que mueven
# la aguja. El orden por gasto convierte una consulta vaga en una respuesta útil.
DEFAULT_DAYS = 7
MAX_DAYS = 60
# Dos semanas: alcanzan para ver una forma, y el patrón de los días de semana todavía se lee.
DEFAULT_SERIES_DAYS = 14
MAX_CAMPAIGNS_LISTED = 30
SERIES_SOURCE = "Sponsored Products, sumado del reporte de search terms: no incluye Sponsored Brands ni Display."
# Lo que el STR ya sabe agrupar: con esto una torta o un ranking sale de una llamada, no de sumar páginas.
_GROUP_COLUMNS = {"campaign": canonical.CAMPAIGN_NAME, "portfolio": canonical.PORTFOLIO_NAME,
                  "match_type": "_origin_match_type", "search_term": canonical.SEARCH_TERM}
_EMPTY_GROUP = {"portfolio": "Sin portfolio", "match_type": "Sin tipo"}
# El modelo copia lo que recibe: si le llega PRODUCT_TARGETING, el AM lee PRODUCT_TARGETING.
_MATCH_TYPE_LABELS = {"AUTO": "Automática", "PRODUCT_TARGETING": "Product targeting", "BROAD": "Broad",
                      "PHRASE": "Phrase", "EXACT": "Exact"}
RANKING_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr")
Dimension = Literal["campaign", "portfolio", "match_type", "search_term"]
RankingMetric = Literal["spend", "sales", "orders", "clicks", "impressions", "acos", "cvr"]


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
    start, end = window_for(profile, days)
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
    _add_window_note(payload, int(days), start, end)
    return payload


def daily_metrics(rest, *, profile_id: str, days: int = DEFAULT_SERIES_DAYS, campaign: str = "") -> dict:
    """Las métricas por día de una cuenta, o de las campañas cuyo nombre contiene `campaign`.

    Una fila por cada día de la ventana, también los que no gastaron: una serie con huecos se
    dibujaría como si esos días no existieran.
    """
    profile = _profile(rest, profile_id)
    start, end = window_for(profile, days)
    series = ReportProvider(rest).daily_totals(profile, start, end, campaign=campaign)
    payload = {"rows": [_day_row(day) for day in series.days], "window": _window(start, end),
               "currency": series.currency_code, "attribution_days": series.attribution_days,
               "source": SERIES_SOURCE}
    _add_window_note(payload, int(days), start, end)
    fragment = campaign.strip()
    if fragment:
        payload["campaigns"] = list(series.campaigns[:MAX_CAMPAIGNS_LISTED])
        if len(series.campaigns) > MAX_CAMPAIGNS_LISTED:
            payload["campaigns_total"] = len(series.campaigns)
        if not series.campaigns:
            payload["rows"] = []
            payload["note"] = (f"Ninguna campaña de la cuenta tiene «{fragment}» en el nombre en este período. "
                               "Buscá el nombre exacto con top_search_terms o get_analysis.")
    return payload


def breakdown(rest, *, profile_id: str, by: Dimension, days: int = DEFAULT_DAYS, sort_by: RankingMetric = "spend",
              offset: int = 0, limit: int = 50) -> dict:
    """Los totales de una cuenta en la ventana, agrupados por campaña, portfolio, tipo de match o search term.

    Ordenados de mayor a menor por `sort_by`; los grupos sin ventas no tienen ACoS y quedan al final
    de ese orden. `totals` suma todos los grupos, también los que no entran en la página.
    """
    if by not in _GROUP_COLUMNS:
        raise ValueError(f"by tiene que ser uno de: {', '.join(_GROUP_COLUMNS)}")
    if sort_by not in RANKING_METRICS:
        raise ValueError(f"sort_by tiene que ser uno de: {', '.join(RANKING_METRICS)}")
    profile = _profile(rest, profile_id)
    start, end = window_for(profile, days)
    source = ReportProvider(rest).search_terms(profile, start, end)
    context = {"window": _window(start, end), "currency": source.currency_code,
               "attribution_days": source.attribution_days, "source": SERIES_SOURCE}
    frame = source.frame
    if frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "totals": None, **context,
                "note": "La cuenta no tuvo búsquedas con clicks en ese período."}

    groups = (frame[_GROUP_COLUMNS[by]].fillna("").astype(str).str.strip()
              .replace(_MATCH_TYPE_LABELS if by == "match_type" else {})
              .replace("", _EMPTY_GROUP.get(by, "Sin nombre")))
    sums = frame.assign(_group=groups).groupby("_group", sort=False).agg(
        spend=(canonical.SPEND, "sum"), sales=(canonical.sales_column(source.attribution_days), "sum"),
        orders=(canonical.orders_column(source.attribution_days), "sum"), clicks=(canonical.CLICKS, "sum"),
        impressions=(canonical.IMPRESSIONS, "sum"))
    rows = [{"group": str(group), **_metrics(row.spend, row.sales, row.orders, row.clicks, row.impressions)}
            for group, row in sums.iterrows()]
    rows.sort(key=lambda row: (row[sort_by] is not None, row[sort_by] or 0), reverse=True)
    payload = page(rows, offset=offset, limit=limit).as_payload(what="grupos")
    totals = sums.sum()
    payload.update(context, totals=_metrics(totals.spend, totals.sales, totals.orders, totals.clicks,
                                            totals.impressions))
    _add_window_note(payload, int(days), start, end)
    return payload


def window_for(profile: ProfileOption, days: int) -> tuple[date, date]:
    """Los últimos `days` días sincronizados de una cuenta, con tope en MAX_DAYS y recortados a lo que tiene."""
    window_days = max(1, min(int(days), MAX_DAYS))
    end = profile.data_through
    return max(profile.data_from or end, end - timedelta(days=window_days - 1)), end


def _add_window_note(payload: dict, requested: int, start: date, end: date) -> None:
    returned = (end - start).days + 1
    if returned >= requested:
        return
    if requested > MAX_DAYS and returned == MAX_DAYS:
        payload["window_note"] = f"Se pidieron {requested} días y el máximo es {MAX_DAYS}: la ventana trae esos."
    else:
        payload["window_note"] = (f"Se pidieron {requested} días y la cuenta tiene {returned} sincronizados: "
                                  "la ventana se recortó a esos.")


def _day_row(day: DayTotals) -> dict:
    return {"date": day.day.isoformat(), **_metrics(day.spend, day.sales, day.orders, day.clicks, day.impressions)}


def _metrics(spend, sales, orders, clicks, impressions) -> dict:
    spend, sales, orders, clicks = float(spend), float(sales), int(orders), int(clicks)
    return {"spend": round(spend, 2), "sales": round(sales, 2), "orders": orders, "clicks": clicks,
            "impressions": int(impressions),
            "acos": round(spend / sales * 100, 1) if sales else None,
            "cvr": round(orders / clicks * 100, 2) if clicks else None}


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
