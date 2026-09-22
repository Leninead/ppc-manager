"""What the app's modules compute for an account, read live with each module's own rules.

Every tool reads the synced data of one account and window and runs the functions its page runs (core/funnel,
core/search_term, core/bid_optimizer, core/ppc_insights), so the chat and the page never disagree. The window and
the values can be the ones the AM has on screen: the chat's turn note names them.
"""
from __future__ import annotations

import math
from typing import Literal

from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads.campaign_provider import (
    BUDGET_AMOUNT,
    CAMPAIGN_ID,
    CAMPAIGN_NAME,
    CLICKS,
    IMPRESSIONS,
    PORTFOLIO_NAME,
    TOTAL_COST,
    CampaignProvider,
)
from core.amazon_ads.report_provider import ReportProvider, ReportReadError
from core.bid_optimizer.bids import NO_ASIN_WARNING, BidAnalysisParams, bids_by_asin, resolve_asin_column
from core.bid_optimizer.bids import detect_columns as bid_columns
from core.funnel.coverage import (
    ACTIVE_CAMPAIGN_COLUMN,
    CAMPAIGN_STATE_COLUMN,
    CVR_COLUMN,
    DEFAULT_MATCH_TYPE,
    DEFAULT_MIN_ORDERS,
    MATCH_TYPES,
    SOURCE_CAMPAIGN_COLUMN,
    SUGGESTED_MATCH_COLUMN,
    FunnelInputError,
    acos_column,
    cover,
    harvest_candidates,
    orders_and_sales,
    suggested_campaigns,
)
from core.ppc_insights.asin_health import InsightsAnalysisParams, analyze_asins, resolve_asins
from core.search_term import frame as canonical
from core.search_term.candidates import (
    StrAnalysisParams,
    add_metric_columns,
    campaign_states,
    clicks_threshold_for,
    detect_columns,
    harvest_candidate_rows,
    negative_candidate_rows,
    sorted_harvest,
)
from core.search_term.negatives import (
    ACTION_NEGATIVE,
    AD_GROUP_STATE_UNVERIFIED_NOTE,
    EXACT_GUARD_PARTIAL_NOTE,
    NegativeCandidate,
    evaluate_candidates,
    select_for_bulk,
)
from services.mcp_server.limits import page
from services.mcp_server.tools.amazon_ads import DEFAULT_DAYS, _campaign_profile, _profile, _window, requested_window

FunnelSection = Literal["idle_campaigns", "gap_terms", "harvest"]
CandidateSection = Literal["negatives", "harvest"]
MatchType = Literal["Phrase", "Exact", "Broad"]

# The modules whose saved account parameters the tools start from, as the analyses store names them.
SEARCH_TERM_SETTINGS = "str"
BID_OPTIMIZER_SETTINGS = "bid_optimizer"
PPC_INSIGHTS_SETTINGS = "ppc_insights"

FUNNEL_SOURCE = ("Sólo Sponsored Products: los search terms de la cuenta (el reporte sólo trae los que tuvieron "
                 "clicks) cruzados por Campaign ID con la foto de campañas, que también trae las habilitadas sin "
                 "actividad. Las mismas reglas que Análisis de Funnel.")
CANDIDATES_SOURCE = ("Sólo Sponsored Products, del reporte de search terms. Las mismas reglas que las pestañas "
                     "Negatives Mining y Harvest del Search Term Report.")
BIDS_SOURCE = ("Del reporte de search terms: el ASIN sale del nombre de la campaña y el precio es el ticket promedio "
               "del período. El Inventory Report, con el precio de lista, se sube a mano en el Bid Optimizer y acá "
               "no está.")
ASIN_HEALTH_SOURCE = ("Del reporte de search terms, con el ASIN de cada término como en PPC Insights. El SQP, el "
                      "Business Report y el Campaign CSV se suben a mano en el módulo y acá no están: Buy Box, "
                      "estructura de campañas y visibilidad valen su punto neutro.")

_FUNNEL_WHAT = {"idle_campaigns": "campañas activas sin search terms",
                "gap_terms": "search terms de campañas pausadas o inexistentes", "harvest": "candidatos a harvest"}
_PRIORITY_ORDER = {"Alta": 0, "Media": 1, "Revisar": 2}
NEGATIVE_TOTALS = ("spend", "clicks", "impressions")


def funnel_coverage(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                    section: FunnelSection = "idle_campaigns", min_orders: int = DEFAULT_MIN_ORDERS,
                    match_type: MatchType = DEFAULT_MATCH_TYPE, offset: int = 0, limit: int = 50) -> dict:
    """Análisis de Funnel of an account: its active campaigns without a single search term, the search terms of
    paused or missing campaigns with the campaign to create for each, and the terms to harvest.

    `section` picks the list; `counts` covers the three over the whole window.
    """
    if section not in _FUNNEL_WHAT:
        raise ValueError(f"section tiene que ser uno de: {', '.join(_FUNNEL_WHAT)}")
    if match_type not in MATCH_TYPES:
        raise ValueError(f"match_type tiene que ser uno de: {', '.join(MATCH_TYPES)}")
    if min_orders < 1:
        raise ValueError("min_orders tiene que ser 1 o más.")
    profile = _profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    search_terms = ReportProvider(rest).search_terms(profile, start, end)
    campaign_view = _campaign_profile(rest, profile_id)
    campaigns = CampaignProvider(rest).campaigns(campaign_view, start, end)
    try:
        coverage = cover(search_terms.frame, campaigns.frame, match_by_id=True)
        harvest = harvest_candidates(search_terms.frame, coverage, min_orders)
    except FunnelInputError as exc:
        raise ValueError(str(exc)) from exc
    suggested = suggested_campaigns(coverage.gap_terms, coverage.columns, match_type)

    if section == "idle_campaigns":
        rows = _idle_campaign_rows(coverage.idle_campaigns)
    elif section == "gap_terms":
        rows = [_gap_term_row(row) for _, row in suggested.iterrows()]
    else:
        rows = [_harvest_row(row, coverage.columns) for _, row in harvest.iterrows()]
    exact = int((harvest[SUGGESTED_MATCH_COLUMN] == "Exact").sum())
    sold_active = orders_and_sales(coverage.active_terms, coverage.columns)
    sold_elsewhere = orders_and_sales(coverage.gap_terms, coverage.columns)
    sold = orders_and_sales(search_terms.frame, coverage.columns)
    payload = page(rows, offset=offset, limit=limit).as_payload(what=_FUNNEL_WHAT[section])
    payload.update(
        window=_window(start, end), currency=search_terms.currency_code,
        attribution_days=search_terms.attribution_days, source=FUNNEL_SOURCE, matched_by=coverage.matched_by,
        parameters={"min_orders": min_orders, "match_type": match_type},
        counts={"sponsored_products_campaigns": len(coverage.campaigns),
                "active_campaigns": len(coverage.active_campaigns), "paused_campaigns": coverage.paused_campaigns,
                "active_campaigns_without_search_terms": len(coverage.idle_campaigns),
                "search_term_rows_from_active_campaigns": len(coverage.active_terms),
                "search_term_rows_from_paused_or_missing_campaigns": len(coverage.gap_terms),
                "orders_from_active_campaigns": sold_active.orders,
                "sales_from_active_campaigns": sold_active.sales,
                "orders_from_paused_or_missing_campaigns": sold_elsewhere.orders,
                "sales_from_paused_or_missing_campaigns": sold_elsewhere.sales,
                "orders_from_search_terms": sold.orders, "sales_from_search_terms": sold.sales,
                "search_terms_without_an_active_campaign": len(suggested),
                "harvest": len(harvest), "harvest_exact": exact, "harvest_phrase": len(harvest) - exact})
    if window_note:
        payload["window_note"] = window_note
    if campaign_view.data_through < end:
        payload["campaigns_note"] = (f"Las métricas de las campañas llegan hasta el "
                                     f"{campaign_view.data_through.isoformat()}: los días siguientes de la ventana "
                                     "no están en sus cifras.")
    return payload


def search_term_candidates(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "",
                           date_to: str = "", section: CandidateSection = "negatives",
                           portfolios: tuple[str, ...] = (), price: float = 0, harvest_price: float = 0,
                           harvest_target_acos: int = 0, harvest_min_clicks: int = 0, offset: int = 0,
                           limit: int = 50) -> dict:
    """The Search Term Report's candidates of an account: to negate (with their rule and action) or to harvest (with
    their rule and suggested bid).

    Starts from the parameters saved for the account in the Search Term Report, or the defaults of its currency;
    `price`, `harvest_price`, `harvest_target_acos` and `harvest_min_clicks` replace the ones given (0 = unchanged).
    `portfolios` keeps only those portfolios, as the page's filter does.
    """
    if section not in ("negatives", "harvest"):
        raise ValueError("section tiene que ser negatives o harvest.")
    profile = _profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    source = ReportProvider(rest).search_terms(profile, start, end)
    frame = source.frame
    if portfolios:
        frame = frame[frame[canonical.PORTFOLIO_NAME].isin(portfolios)]
    frame = frame.copy()
    columns = detect_columns(frame)
    add_metric_columns(frame, columns)
    settings = AiAnalysisStore(rest).settings(SEARCH_TERM_SETTINGS, profile_id)
    saved = (StrAnalysisParams.from_dict(settings.params, source.currency_code) if settings
             else StrAnalysisParams.defaults(source.currency_code))
    product_price = price or saved.price
    bid_price = harvest_price or saved.harvest_price
    bid_target = harvest_target_acos or saved.harvest_target_acos
    min_clicks = harvest_min_clicks or saved.harvest_min_clicks
    clicks_threshold = clicks_threshold_for(frame["_clicks"].sum(), frame["_orders"].sum())
    spend_threshold = math.inf if product_price is None else product_price * 0.50
    context = {"window": _window(start, end), "currency": source.currency_code,
               "attribution_days": source.attribution_days, "source": CANDIDATES_SOURCE,
               "parameters": {"price": product_price, "harvest_price": bid_price, "harvest_target_acos": bid_target,
                              "harvest_min_clicks": min_clicks, "clicks_threshold": clicks_threshold,
                              "spend_threshold": None if product_price is None else round(spend_threshold, 2),
                              "portfolios": list(portfolios or []),
                              "origin": ("guardados de la cuenta en el Search Term Report" if settings
                                         else "valores por defecto del Search Term Report: la cuenta no guardó "
                                              "parámetros")}}
    if window_note:
        context["window_note"] = window_note

    if section == "negatives":
        candidates = evaluate_candidates(frame, columns, clicks_threshold=clicks_threshold,
                                         spend_threshold=spend_threshold) if columns["search_term"] else []
        # The bulk guards read every ad group, so they get the frame before the portfolio filter, as on the page.
        verdicts = _bulk_verdicts(candidates, source.frame)
        rows = sorted((_negative_row(row, candidate.campaign_status, verdict)
                       for candidate, row, verdict in zip(candidates, negative_candidate_rows(candidates), verdicts)),
                      key=lambda row: (_PRIORITY_ORDER.get(row["priority"], 3), -row["spend"]))
        what = "candidatos a negativo"
        counts = _counts(rows, "priority") | {f"action_{key}": value for key, value in _counts(rows, "action").items()}
        missing = ("Sin precio del producto no corre la Regla 3 (gasto sin conversión)." if product_price is None
                   else "")
        totals = _totals(rows, NEGATIVE_TOTALS)
        bulk = {"totals_in_bulk": _totals([row for row in rows if row["in_bulk"]], NEGATIVE_TOTALS),
                "bulk_notes": [EXACT_GUARD_PARTIAL_NOTE, AD_GROUP_STATE_UNVERIFIED_NOTE]}
    else:
        harvest = (sorted_harvest(harvest_candidate_rows(frame, columns, min_clicks=min_clicks, price=bid_price,
                                                         target_acos=bid_target)) if columns["search_term"] else None)
        states = campaign_states(frame, columns)
        rows = [] if harvest is None else [_str_harvest_row(row, states) for row in harvest.to_dict("records")]
        what = "candidatos a harvest"
        counts = _counts(rows, "priority")
        missing = "Sin precio de harvest no hay bid sugerido." if bid_price is None else ""
        totals = _totals(rows, ("clicks", "orders"))
        bulk = {}
    payload = page(rows, offset=offset, limit=limit).as_payload(what=what)
    payload.update(context, counts=counts, totals=totals, **bulk)
    if missing:
        payload["parameters_note"] = missing
    return payload


def bid_suggestions(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                    target_acos: int = 0, offset: int = 0, limit: int = 50) -> dict:
    """The Bid Optimizer of an account: the suggested bid per ASIN (CVR × price × target ACoS) and its traffic light
    by CVR, the highest spend first.

    Starts from the target ACoS saved for the account in the Bid Optimizer, or its default; `target_acos` replaces it.
    """
    profile = _profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    source = ReportProvider(rest).search_terms(profile, start, end)
    settings = AiAnalysisStore(rest).settings(BID_OPTIMIZER_SETTINGS, profile_id)
    saved = BidAnalysisParams.from_dict(settings.params) if settings else BidAnalysisParams.defaults()
    target = target_acos or saved.target_acos
    context = {"window": _window(start, end), "currency": source.currency_code, "source": BIDS_SOURCE,
               "parameters": {"target_acos": target,
                              "origin": ("guardado de la cuenta en el Bid Optimizer" if settings and not target_acos
                                         else "pedido en la llamada" if target_acos
                                         else "valor por defecto del Bid Optimizer: la cuenta no guardó "
                                              "parámetros")}}
    if window_note:
        context["window_note"] = window_note
    columns = bid_columns(source.frame)
    missing = [key for key in ("clicks", "orders", "sales", "spend") if columns[key] is None]
    if missing or source.frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, **context,
                "note": "La cuenta no tuvo búsquedas con clicks en ese período."}
    frame, asin_column, asin_source = resolve_asin_column(source.frame, columns)
    if asin_column is None:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, **context, "note": NO_ASIN_WARNING}
    by_asin = bids_by_asin(frame, columns, asin_column, target, {})
    rows = sorted((_bid_row(row, columns, asin_column) for _, row in by_asin.iterrows()),
                  key=lambda row: -row["spend"])
    payload = page(rows, offset=offset, limit=limit).as_payload(what="ASINs")
    payload.update(context, asin_source=asin_source)
    return payload


def asin_health(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                target_acos: int = 0, offset: int = 0, limit: int = 50) -> dict:
    """PPC Insights of an account: the health score (0-100) of each ASIN with its parts, spend, ACoS, CVR and the
    spend of its terms that did not sell, the highest spend first.

    Starts from the target ACoS saved for the account in PPC Insights, or its default; `target_acos` replaces it.
    """
    profile = _profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    provider = ReportProvider(rest)
    source = provider.search_terms(profile, start, end)
    notes = []
    try:
        ad_group_asins = provider.advertised_asins(profile_id)
    except ReportReadError:
        ad_group_asins = {}
        notes.append("No se pudieron leer los productos anunciados: el ASIN de cada término sale del nombre de la "
                     "campaña.")
    settings = AiAnalysisStore(rest).settings(PPC_INSIGHTS_SETTINGS, profile_id)
    saved = (InsightsAnalysisParams.from_dict(settings.params, source.currency_code) if settings
             else InsightsAnalysisParams.defaults(source.currency_code))
    target = target_acos or saved.target_acos
    resolved = resolve_asins(source.frame.copy(), ad_group_asins)
    asin_data = analyze_asins(resolved.frame.copy(), None, None, None, target, resolved.column)
    rows = sorted((_asin_row(asin, metrics, resolved.grouped_asins.get(asin)) for asin, metrics in asin_data.items()),
                  key=lambda row: (-row["spend"], row["asin"]))
    payload = page(rows, offset=offset, limit=limit).as_payload(what="ASINs")
    payload.update(window=_window(start, end), currency=source.currency_code, source=ASIN_HEALTH_SOURCE,
                   asin_source=resolved.source, asin_spend_share=resolved.spend_share,
                   parameters={"target_acos": target,
                               "origin": ("pedido en la llamada" if target_acos
                                          else "guardado de la cuenta en PPC Insights" if settings
                                          else "valor por defecto de PPC Insights: la cuenta no guardó "
                                               "parámetros")})
    if window_note:
        payload["window_note"] = window_note
    if notes:
        payload["asin_note"] = " ".join(notes)
    return payload


def _idle_campaign_rows(idle) -> list[dict]:
    rows = [{"campaign": str(row[CAMPAIGN_NAME]).strip(), "campaign_id": str(row[CAMPAIGN_ID]),
             "portfolio": str(row.get(PORTFOLIO_NAME) or "").strip(), "daily_budget": _number(row.get(BUDGET_AMOUNT)),
             "impressions": _number(row.get(IMPRESSIONS)), "clicks": _number(row.get(CLICKS)),
             "spend": _number(row.get(TOTAL_COST))} for _, row in idle.iterrows()]
    return sorted(rows, key=lambda row: -(row["daily_budget"] or 0))


def _gap_term_row(row) -> dict:
    return {"search_term": row["Customer Search Term"],
            "source_campaign": str(row["Campaña origen (inactiva)"]).strip(),
            "campaign_state": row[CAMPAIGN_STATE_COLUMN], "clicks": _number(row["Clicks"]),
            "spend": _number(row["Spend"]), "orders": _number(row["Orders"]), "sales": _number(row["Sales"]),
            "suggested_campaign": row["Nombre sugerido"], "product": row["Producto inferido"],
            "asin": row["ASIN inferido"]}


def _harvest_row(row, columns: dict) -> dict:
    return {"search_term": str(row[columns["search_term"]]).strip(), "campaigns": row[SOURCE_CAMPAIGN_COLUMN],
            "in_active_campaign": bool(row[ACTIVE_CAMPAIGN_COLUMN]),
            "impressions": _number(row.get(columns["impressions"])), "clicks": _number(row.get(columns["clicks"])),
            "orders": _number(row.get(columns["orders"])), "sales": _number(row.get(columns["sales"])),
            "spend": _number(row.get(columns["spend"])), "acos": _number(row.get(acos_column(columns))),
            "cvr": _number(row.get(CVR_COLUMN)), "match_type": row[SUGGESTED_MATCH_COLUMN]}


def _negative_row(row: dict, campaign_state: str, verdict: dict) -> dict:
    return {"search_term": row["Search Term"], "campaign": row["Campaign"], "campaign_state": campaign_state,
            **verdict, "ad_group": row["Ad Group"],
            "clicks": _number(row["Clicks"]), "impressions": _number(row["Impressions"]),
            "spend": _number(row["Spend"]) or 0, "orders": _number(row["Orders"]), "acos": _number(row["ACoS"]),
            "rule": row["Regla"], "action": row["Acción"], "match_type": row["Match Type"],
            "priority": row["Prioridad"]}


def _str_harvest_row(row: dict, states: dict) -> dict:
    return {"search_term": row["Search Term"], "campaign": row["Campaign"],
            "campaign_state": states.get((row["Search Term"], row["Campaign"], row["Ad Group"]), ""),
            "ad_group": row["Ad Group"],
            "clicks": _number(row["Clicks"]), "orders": _number(row["Orders"]), "acos": _number(row["ACoS"]),
            "cvr": _number(row["CVR%"]), "suggested_bid": _number(row["Bid Sugerido"]), "rule": row["Regla"],
            "priority": row["Prioridad"]}


def _bid_row(row, columns: dict, asin_column: str) -> dict:
    return {"asin": str(row[asin_column]).strip(), "clicks": _number(row[columns["clicks"]]),
            "orders": _number(row[columns["orders"]]), "cvr": _number(row["_cvr"]), "price": _number(row["_precio"]),
            "spend": _number(row[columns["spend"]]) or 0, "sales": _number(row[columns["sales"]]),
            "acos": _number(row["_acos"]), "suggested_bid": _number(row["_bid_base"]),
            "status": str(row["Estado"]).split(" ", 1)[-1]}


def _asin_row(asin, metrics: dict, grouped_asins: int | None) -> dict:
    top_terms = metrics["top_kws"]
    row = {"asin": str(asin), "health_score": metrics["health_score"],
           "health_parts": {part: _number(points) for part, points in metrics["health_parts"].items()},
           "spend": _number(metrics["spend"]) or 0, "sales": _number(metrics["sales"]),
           "orders": _number(metrics["orders"]), "clicks": _number(metrics["clicks"]),
           "acos": _number(metrics["acos"]), "cvr": _number(metrics["cvr"]),
           "spend_without_sales": _number(metrics["wasted_spend"]),
           "top_search_terms": [] if top_terms.empty else top_terms["Search Term"].astype(str).tolist()}
    if grouped_asins:
        row["grouped_asins"] = grouped_asins
    return row


def _bulk_verdicts(candidates: list[NegativeCandidate], frame) -> list[dict]:
    """Whether each candidate goes into the Search Term Report's negatives bulk and, if it stays out, the module's
    reason; a candidate whose action is not Negativo is never in the bulk and has no reason."""
    if not candidates:
        return []
    _, exclusions = select_for_bulk(candidates, frame)
    reasons = {id(exclusion.candidate): exclusion.reason for exclusion in exclusions}
    return [{"in_bulk": candidate.action == ACTION_NEGATIVE and id(candidate) not in reasons,
             "bulk_exclusion": reasons.get(id(candidate), "")} for candidate in candidates]


def _totals(rows: list[dict], keys: tuple[str, ...]) -> dict:
    """Every row of the section summed, so the answer quotes a total instead of adding rows up."""
    return {key: _number(sum(row[key] or 0 for row in rows)) for key in keys}


def _counts(rows: list[dict], key: str) -> dict:
    counts: dict = {}
    for row in rows:
        counts[str(row[key])] = counts.get(str(row[key]), 0) + 1
    return counts


def _number(value):
    """JSON-safe: a missing value or NaN is None, an integral number an int, anything else rounded to 2."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return int(number) if number.is_integer() else round(number, 2)
