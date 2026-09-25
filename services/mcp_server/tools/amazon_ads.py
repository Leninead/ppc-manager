"""Las cuentas de Amazon Ads sincronizadas, sus search terms, su serie diaria, sus campañas, sus targets y la
estructura de sus campañas de Sponsored Products.

Se apoya en core/amazon_ads/ (report_provider, campaign_provider, product_provider, structure_provider,
campaign_totals y campaign_analyzer), que ya leen y clasifican sin Streamlit: acá no hay lógica de negocio nueva,
sólo la forma en que un modelo la consulta.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

import pandas as pd

from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads import campaign_totals
from core.amazon_ads.campaign_analyzer import (
    ANALYSIS_MODULE as CAMPAIGNS_MODULE,
    DIAGNOSIS_COLUMN,
    PAUSE,
    SIGNALS_COLUMN,
    CampaignAnalyzerParams,
    analyze,
    diagnosis_name,
    diagnosis_rules,
    provisional_days,
    signal_rules,
)
from core.amazon_ads.campaign_provider import (
    BID_STRATEGY,
    BUDGET_AMOUNT,
    CAMPAIGN_ID,
    CAMPAIGN_NAME,
    PORTFOLIO_NAME,
    TYPE,
    CampaignProvider,
    campaign_sync_view,
)
from core.amazon_ads.campaign_totals import NEW_TO_BRAND_PRODUCTS, sum_new_to_brand
from core.amazon_ads.product_provider import (
    PRODUCT_CODES,
    PRODUCT_TYPES,
    PURCHASES_CLICKS,
    SALES_CLICKS,
    TARGET_BID,
    TARGET_ID,
    TARGET_KIND,
    TARGET_MATCH,
    TARGET_PRODUCT,
    TARGET_TEXT,
    ProductProvider,
    campaigns_to_analyze,
)
from core.amazon_ads.report_provider import (
    ProfileOption,
    ReportProvider,
    _attribution_days,
    account_labels,
)
from core.amazon_ads.sync_planner import (
    CAMPAIGNS_KIND,
    profile_timezone,
)
from core.integrations.sync_jobs import SyncJobStore
from services.mcp_server.limits import page
from services.mcp_server.tools.account_resolver import campaign_profile as _campaign_profile
from services.mcp_server.tools.account_resolver import choose_account, matching_profiles, name_key
from services.mcp_server.tools.account_resolver import profile_by_id as _profile
from services.mcp_server.tools.campaign_selector import CampaignRequest, select_campaigns
from services.mcp_server.tools.figures import (
    ATTRIBUTION_NOTE,
    NEW_TO_BRAND_NOTE,
    SOURCE_CAMPAIGNS,
    SOURCE_SEARCH_TERMS,
    Product,
    Source,
    _add_old_format_note,
    _check_product,
    _check_source,
    _days_metrics,
    _metrics,
    _plain,
    _plain_number,
    _source_fields,
    _totals_metrics,
    attribution_days_by_product,
    new_to_brand_fields,
    whole_metrics,
)
from services.mcp_server.tools.metric_filters import (
    FiltersParam,
    RowFilter,
    SortMetric,
    SortOrder,
    check_sort,
    sort_rows,
    with_sort_figure,
)
from services.mcp_server.tools.period_comparison import (
    COMPARE_NOTE,
    Compare,
    activity_status,
    change_fields,
    change_leaders,
    comparison_window,
    status_counts,
)
from services.mcp_server.tools.windows import (
    DEFAULT_DAYS,
    clipped_window,
    days_note,
    outside_note,
    requested_dates,
    requested_window,
    window_for,
)
from services.mcp_server.tools.windows import window_payload as _window

MAX_CAMPAIGNS_LISTED = 30
RANKING_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr")
# What an enabled campaign's row carries to filter by.
CAMPAIGN_FILTER_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc")
RankingMetric = Literal["spend", "sales", "orders", "clicks", "impressions", "acos", "cvr"]
# "" = sin filtro: un parámetro opcional con None llegaría al modelo sin tipo.
Diagnosis = Literal["", "FANTASMA", "PAUSAR", "REVISAR", "ESCALAR", "OK"]
Signal = Literal["", "Limitada por presupuesto", "Nueva", "Baja visibilidad"]
CAMPAIGNS_SOURCE = ("Sponsored Products, Brands y Display, de la foto de campañas y sus reportes: trae también las "
                    "campañas habilitadas sin actividad. Las señales sólo existen para SP. " + ATTRIBUTION_NOTE)
TARGETS_SOURCE = ("Los targets habilitados de campañas habilitadas de SP, SB y SD, de las listas de keywords y targets, "
                  "con las impresiones de sus reportes de targeting. El bid es el efectivo: el propio del target o, si "
                  "no tiene, el default de su ad group. Los de ad groups de SP listados como pausados quedan afuera. No "
                  "incluye las campañas SB del formato anterior: sus targets no tienen reporte.")
# The report keeps the last name each campaign had in the period: its state says whether it runs, never its name.
CAMPAIGN_STATUS = "Campaign Status"


def list_accounts(rest, *, account: str = "", offset: int = 0) -> dict:
    """Las cuentas de Amazon Ads sincronizadas, con su país, moneda, hasta qué día tienen datos, qué día es hoy en
    cada una y si sus datos están al día. `account` deja las que tienen ese texto en el nombre, sin mirar mayúsculas,
    espacios ni guiones. Paginadas como toda respuesta larga: `offset` trae la página siguiente."""
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    now = _now()
    rows = [{
        "account": labels[profile.profile_id],
        "profile_id": profile.profile_id,
        "country": profile.country_code,
        "currency": profile.currency_code,
        "status": profile.status,
        "data_from": profile.data_from.isoformat() if profile.data_from else None,
        "data_through": profile.data_through.isoformat() if profile.data_through else None,
        **_freshness(profile, now),
    } for profile in profiles]
    wanted = name_key(account)
    if wanted:
        rows = [row for row in rows if wanted in name_key(row["account"])]
    rows.sort(key=lambda row: row["account"])
    payload = page(rows, offset=offset).as_payload(what="cuentas")
    if wanted and not rows:
        payload["note"] = f"Ninguna cuenta tiene «{account}» en el nombre; sin account vienen todas."
    return payload


def top_search_terms(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS, offset: int = 0,
                     limit: int = 50) -> dict:
    """Los search terms de mayor gasto de una cuenta en los últimos `days` días.

    El período se recorta a lo que la cuenta tiene sincronizado: pedir 60 días de una cuenta con 10
    devuelve esos 10 y lo dice, en vez de una ventana vacía.
    """
    choice = choose_account(rest, profile_id, account, days=days)
    if choice.candidates:
        return choice.as_payload()
    profile = _profile(rest, choice.profile_id)
    start, end = window_for(profile, days)
    source = ReportProvider(rest).search_terms(profile, start, end)

    frame = source.frame
    if frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0,
                "window": _window(start, end), "currency": source.currency_code,
                "note": "La cuenta no tuvo búsquedas con clicks en ese período."}

    spend = _column(frame, "spend")
    ordered = frame.sort_values(spend, ascending=False) if spend else frame
    rows = [{**{str(name): _plain(value) for name, value in row.items() if not str(name).startswith("_")},
             CAMPAIGN_STATUS: row.get("_campaign_status") or ""} for _, row in ordered.iterrows()]
    payload = page(rows, offset=offset, limit=limit).as_payload(what="search terms")
    payload["window"] = _window(start, end)
    payload["currency"] = source.currency_code
    _add_window_note(payload, int(days), start, end)
    return payload


def accounts_overview(rest, *, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                      account: str = "", product: Product = "", source: Source = "", compare: Compare = "",
                      compare_from: str = "", compare_to: str = "", offset: int = 0) -> dict:
    """Los totales de las campañas (SP, SB y SD, o sólo `product`) de cada cuenta sincronizada, o de las que llevan
    `account` en el nombre, en sus últimos `days` días o de `date_from` a `date_to`, todas en una llamada; con
    `source`=search_terms, los de SP sumados del reporte de search terms. `compare` pone cada cuenta al lado de su
    período anterior. Paginados como toda respuesta larga: `offset` trae la página siguiente.

    Una cuenta que no gastó vuelve en cero en vez de faltar: su ausencia se leería como que no
    existe. Una sin datos sincronizados en esas fechas vuelve sin cifras, con `window_note` diciendo qué días
    tiene. Cada una en su moneda, y la respuesta lo avisa: los montos no se suman entre monedas.
    """
    _check_source(source, product)
    _check_product(product)
    source = source or SOURCE_CAMPAIGNS
    period = requested_dates(date_from, date_to) if date_from or date_to else None
    jobs = SyncJobStore(rest)
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    if account.strip():
        profiles = matching_profiles(profiles, account)
        if not profiles:
            raise ValueError(f"Ninguna cuenta tiene «{account}» en el nombre; list_accounts da los nombres de todas.")
    rows, without_campaigns = [], []
    for profile in profiles:
        totals = _account_totals(rest, jobs, profile, days, source, period, product=product, compare=compare,
                                 compare_from=compare_from, compare_to=compare_to)
        if totals is not None:
            rows.append({"account": labels[profile.profile_id], "profile_id": profile.profile_id, **totals})
        elif profile.data_through is not None:
            without_campaigns.append(labels[profile.profile_id])
    rows.sort(key=lambda row: row["account"])
    payload = page(rows, offset=offset).as_payload(what="cuentas")
    payload.update(_source_fields(source, alternative=product in ("", "SP")),
                   counts={"accounts": len(rows),
                           "spend_exceeds_sales": sum(1 for row in rows if row.get("spend_exceeds_sales")),
                           "without_sales": sum(1 for row in rows if row.get("without_sales"))})
    currency_note = ("Cada cuenta está en su moneda: no sumes ni compares montos entre monedas distintas. "
                     "ACoS, CVR, órdenes y clicks sí se comparan entre cuentas. counts cuenta todas las cuentas de la "
                     "respuesta, no sólo esta página: spend_exceeds_sales son las que gastaron más de lo que vendieron y "
                     "without_sales las que gastaron sin vender nada.")
    # The page's own note says there are more accounts and how to ask for them: it must survive this one.
    payload["note"] = f"{payload['note']} {currency_note}" if "note" in payload else currency_note
    if compare or compare_from or compare_to:
        payload["compare_note"] = COMPARE_NOTE
    if product in NEW_TO_BRAND_PRODUCTS:
        payload["new_to_brand_note"] = NEW_TO_BRAND_NOTE
    # Missing from the rows they would read as accounts that do not exist: they are named, with where their SP is.
    if without_campaigns:
        payload["without_campaigns"] = sorted(without_campaigns)
        payload["without_campaigns_note"] = (
            "Estas cuentas todavía no tienen campañas sincronizadas, así que no están en estos totales. Sus cifras de "
            "Sponsored Products sumadas de los search terms están con source=search_terms.")
    return payload


def campaign_health(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS, date_from: str = "",
                    date_to: str = "", diagnosis: Diagnosis = "", signal: Signal = "", product: Product = "",
                    campaign: str = "", campaigns: tuple[str, ...] = (), portfolio: str = "",
                    target_acos: float = 0, spend_to_pause: float = 0, min_orders_to_scale: int = 0,
                    filters: FiltersParam = None, sort_by: SortMetric = "spend",
                    sort_order: SortOrder = "desc", compare: Compare = "", compare_from: str = "",
                    compare_to: str = "", order_by_change: bool = False, offset: int = 0, limit: int = 50,
                    min_budget_capped_days: int = 0) -> dict:
    """Las campañas habilitadas de una cuenta (SP, SB y SD) en sus últimos `days` días, o de `date_from` a `date_to`,
    con el diagnóstico de Bulk Campañas y sus señales. `min_budget_capped_days` deja las de SP que llegaron a su tope
    del día al menos esos días; `signal_counts` y `budget_capped` cruzan señales y topes con el diagnóstico.

    Parte de la foto de campañas, así que trae también las que no tuvieron actividad (las FANTASMA), que
    `breakdown` por campaña no ve. Clasifica con los parámetros guardados de la cuenta en Bulk Campañas, o
    con los de siempre, y dice cuáles usó; `target_acos`, `spend_to_pause` y `min_orders_to_scale` reemplazan
    los que se pasen (0 = no cambia). `product` acota todo a SP, SB o SD; `campaign`, `campaigns` y `portfolio`, a
    esas campañas; `diagnosis`, `signal` y `filters` sólo filtran filas: `counts` y `totals` cubren todas las
    habilitadas del alcance, no sólo la página. `compare` pone cada campaña al lado del período anterior.
    """
    check_sort(sort_by)
    _check_product(product)
    row_filter = RowFilter.from_request(filters, metrics=CAMPAIGN_FILTER_METRICS)
    if order_by_change and not (compare or compare_from or compare_to):
        raise ValueError("order_by_change ordena por el cambio contra otro período: pedilo con compare.")
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    profile_id = choice.profile_id
    profile = _campaign_profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    source = CampaignProvider(rest).campaigns(profile, start, end)
    products = ProductProvider(rest).campaigns(profile_id, start, end)
    frame = campaigns_to_analyze(source.frame, products)
    if product and TYPE in frame.columns:
        frame = frame[frame[TYPE] == PRODUCT_TYPES[product]]
    settings = AiAnalysisStore(rest).settings(CAMPAIGNS_MODULE, profile_id)
    saved = CampaignAnalyzerParams.from_dict(settings.params) if settings else CampaignAnalyzerParams.defaults()
    params = CampaignAnalyzerParams(target_acos or saved.target_acos, spend_to_pause or saved.spend_to_pause,
                                    min_orders_to_scale or saved.min_orders_to_scale)
    origin = ("guardados de la cuenta en Bulk Campañas" if settings
              else "valores por defecto de Bulk Campañas: la cuenta no guardó parámetros")
    if params != saved:
        origin = f"los pedidos en la llamada; los demás, {origin}"
    analyzer, campaigns_frame = analyze(frame, source.signal_inputs, params, window_start=start, window_end=end)
    context = {
        "window": _window(start, end), "currency": source.currency_code, "attribution_days": source.attribution_days,
        "source": CAMPAIGNS_SOURCE,
        "parameters": {**params.as_dict(), "origin": origin,
                       "rules": diagnosis_rules(params, has_impressions=analyzer.has_impressions),
                       "signal_rules": signal_rules(params, window_days=(end - start).days + 1)},
        # The last synced days are the provisional ones: a window ending earlier has none.
        "provisional_days": [day.isoformat() for day in provisional_days(None, profile.data_through)
                             if start <= day <= end],
    }
    if window_note:
        context["window_note"] = window_note
    _add_old_format_note(context, rest, profile_id, start, end, product, products=products)
    if campaigns_frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "counts": {}, "totals": None, **context,
                "note": "La cuenta no tiene campañas habilitadas en este período."}

    new_to_brand = products.new_to_brand if products is not None else {}
    rows = [_campaign_row(row, analyzer.has_impressions, new_to_brand) for _, row in campaigns_frame.iterrows()]
    request = CampaignRequest.of(campaign, campaigns, "", portfolio)
    if request.applied():
        catalog = pd.DataFrame(rows, columns=["product", "campaign_id", "campaign", "portfolio"]).assign(
            state="ENABLED", daily_budget=float("nan"))
        selection = select_campaigns(catalog, request)
        context.update(selection.payload())
        kept = [row for row in rows if row["campaign_id"] in selection.ids]
        campaigns_frame = campaigns_frame[campaigns_frame[CAMPAIGN_ID].astype(str).isin(selection.ids)]
        rows = kept
    if any(row["product"] in NEW_TO_BRAND_PRODUCTS for row in rows):
        context["new_to_brand_note"] = NEW_TO_BRAND_NOTE
    counts = campaigns_frame[DIAGNOSIS_COLUMN].map(diagnosis_name).value_counts()
    totals = whole_metrics(_metrics(campaigns_frame["_spend"].sum(), campaigns_frame["_sales"].sum(),
                                    campaigns_frame["_orders"].sum(), campaigns_frame["_clicks"].sum(),
                                    campaigns_frame["_impr"].sum() if analyzer.has_impressions else 0))
    crossed = {"signal_counts": _signal_counts(rows), "budget_capped": _budget_capped_counts(rows),
               "diagnosis_by_product": _diagnosis_by_product(rows)}
    leaders = {}
    rows = with_sort_figure(rows, sort_by)
    compared = comparison_window(profile, start, end, compare, compare_from, compare_to)
    if isinstance(compared, str):
        context["comparison_note"] = compared
    elif compared is not None:
        previous = _campaign_window_figures(rest, profile, compared.start, compared.end)
        rows = [{**row, **change_fields(row, previous.get(row["campaign_id"]), sort_by),
                 **activity_status(row, previous.get(row["campaign_id"]) or {})} for row in rows]
        leaders = change_leaders(rows, sort_by, name="campaign")
        context.update(compared.payload(), compare_counts=status_counts(rows))
    if diagnosis:
        rows = [row for row in rows if row["diagnosis"] == diagnosis]
    if signal:
        rows = [row for row in rows if signal in row["signals"]]
    if min_budget_capped_days:
        rows = [row for row in rows if (row.get("budget_capped_days") or 0) >= min_budget_capped_days]
    rows = [row for row in rows if row_filter.keeps(row)]
    rows = sort_rows(rows, f"delta_{sort_by}" if order_by_change else sort_by, sort_order)
    payload = page(rows, offset=offset, limit=limit).as_payload(what="campañas")
    payload.update(context, counts={str(name): int(count) for name, count in counts.items()}, totals=totals,
                   pause_spend=round(float(campaigns_frame.loc[campaigns_frame[DIAGNOSIS_COLUMN] == PAUSE,
                                                               "_spend"].sum()), 2),
                   **crossed, **row_filter.described())
    if leaders:
        payload["leaders"] = leaders
    return payload


def _campaign_window_figures(rest, profile: ProfileOption, start: date, end: date) -> dict[str, dict]:
    """Campaign id -> its metrics over [start, end], from the campaign reports of the three products."""
    frame = campaign_totals.window_totals(rest, profile, start, end)
    columns = list(campaign_totals.Totals.__dataclass_fields__)
    return {str(campaign_id): _totals_metrics(campaign_totals.Totals(**part[columns].sum().to_dict()))
            for campaign_id, part in frame.groupby("campaign_id")}


def _signal_counts(rows: list[dict]) -> dict:
    """Per signal, how many enabled campaigns carry it in each diagnosis."""
    found: dict[str, dict[str, int]] = {}
    for row in rows:
        for name in row["signals"]:
            per_diagnosis = found.setdefault(name, {})
            per_diagnosis[row["diagnosis"]] = per_diagnosis.get(row["diagnosis"], 0) + 1
    return found


def _budget_capped_counts(rows: list[dict]) -> dict:
    """How many SP campaigns reached their daily budget at least one day, in total and per diagnosis."""
    capped = sorted((row for row in rows if (row.get("budget_capped_days") or 0) >= 1),
                    key=lambda row: row["budget_capped_days"], reverse=True)
    per_diagnosis: dict[str, int] = {}
    for row in capped:
        per_diagnosis[row["diagnosis"]] = per_diagnosis.get(row["diagnosis"], 0) + 1
    listed = [{"campaign": row["campaign"], "diagnosis": row["diagnosis"], "days": row["budget_capped_days"],
               "acos": row.get("acos")} for row in capped[:MAX_CAMPAIGNS_LISTED]]
    return {"campaigns": len(capped), "by_diagnosis": per_diagnosis, "list": listed}


def _diagnosis_by_product(rows: list[dict]) -> dict:
    """Per product (SP, SB, SD), how many enabled campaigns fall in each diagnosis."""
    found: dict[str, dict[str, int]] = {}
    for row in rows:
        per_diagnosis = found.setdefault(str(row.get("product") or ""), {})
        per_diagnosis[row["diagnosis"]] = per_diagnosis.get(row["diagnosis"], 0) + 1
    return found


def idle_targets(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS, date_from: str = "",
                 date_to: str = "", product: Product = "", offset: int = 0, limit: int = 50) -> dict:
    """Target Graduation: los targets habilitados, de campañas habilitadas, sin una impresión en los últimos `days`
    días o de `date_from` a `date_to`, con su bid efectivo. Los de ad groups de SP listados como pausados no se miran.

    `counts` dice, por producto, cuántos se miraron y cuántos no tuvieron impresiones, también los que no
    entran en la página. `product` acota a SP, SB o SD.
    """
    _check_product(product)
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    profile_id = choice.profile_id
    profile = _campaign_profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    targets = ProductProvider(rest).idle_targets(profile_id, start, end)
    context = {"window": _window(start, end), "source": TARGETS_SOURCE}
    if window_note:
        context["window_note"] = window_note
    if targets is None or not targets.considered:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "counts": {}, **context,
                "note": "Los targets de esta cuenta todavía no se sincronizaron."}
    frame = targets.frame
    considered = targets.considered
    if product:
        frame = frame[frame[TARGET_PRODUCT] == product]
        considered = {product: considered.get(product, 0)}
    idle_by_product = frame[TARGET_PRODUCT].value_counts()
    counts = {code: {"considered": int(count), "idle": int(idle_by_product.get(code, 0))}
              for code, count in considered.items()}
    rows = [{"product": row[TARGET_PRODUCT], "campaign": str(row[CAMPAIGN_NAME] or "").strip(),
             "campaign_id": str(row[CAMPAIGN_ID]), "target": str(row[TARGET_TEXT] or "").strip(),
             "target_id": str(row[TARGET_ID]), "kind": row[TARGET_KIND], "match_type": row[TARGET_MATCH] or "",
             "bid": _plain_number(row[TARGET_BID])} for _, row in frame.iterrows()]
    payload = page(rows, offset=offset, limit=limit).as_payload(what="targets sin impresiones")
    payload.update(context, counts=counts)
    if product and not considered.get(product):
        payload["note"] = f"Todavía no hay targets de {PRODUCT_TYPES[product]} para evaluar en este período."
    return payload


def _campaign_row(row, has_impressions: bool, new_to_brand: dict | None = None) -> dict:
    record = {
        "campaign": str(row.get(CAMPAIGN_NAME) or "").strip(),
        "campaign_id": str(row.get(CAMPAIGN_ID) or ""),
        "product": PRODUCT_CODES.get(str(row.get(TYPE) or ""), "SP"),
        "portfolio": str(row.get(PORTFOLIO_NAME) or "").strip(),
        "bid_strategy": str(row.get(BID_STRATEGY) or "").strip(),
        "daily_budget": _plain_number(row.get(BUDGET_AMOUNT)),
        "diagnosis": diagnosis_name(row[DIAGNOSIS_COLUMN]),
        "signals": [signal for signal in str(row.get(SIGNALS_COLUMN) or "").split(" · ") if signal],
        **_metrics(row["_spend"], row["_sales"], row["_orders"], row["_clicks"],
                   row["_impr"] if has_impressions else 0),
    }
    # Only when the account has SB or SD: for SP they are its own sales and orders.
    if SALES_CLICKS in row.index:
        record["sales_clicks"] = _plain_number(row.get(SALES_CLICKS))
        record["orders_clicks"] = _plain_number(row.get(PURCHASES_CLICKS))
    for key, column in (("budget_capped_days", "_budget_capped_days"), ("days_with_impressions",
                                                                        "_days_with_impressions"),
                        ("top_of_search_share", "_top_of_search_is"), ("days_live", "_days_live")):
        if column in row.index:
            record[key] = _plain_number(row.get(column))
    if record["product"] in NEW_TO_BRAND_PRODUCTS and new_to_brand:
        record.update(new_to_brand_fields(new_to_brand.get(record["campaign_id"]), record["sales"]))
    return record


def _account_totals(rest, jobs: SyncJobStore, profile: ProfileOption, days: int, source: str,
                    period: tuple[date, date] | None, *, product: str = "", compare: str = "",
                    compare_from: str = "", compare_to: str = "") -> dict | None:
    """One account's row of accounts_overview, or None while it has no data from that source yet."""
    searched = source == SOURCE_SEARCH_TERMS
    synced = profile if searched else campaign_sync_view(
        profile, jobs.latest_completed_for_profile(profile.profile_id, CAMPAIGNS_KIND))
    if synced.data_through is None:
        return None
    if period is None:
        start, end, window_note = *window_for(synced, days), ""
    else:
        clipped = clipped_window(synced, *period)
        if clipped is None:
            return {"currency": profile.currency_code, "window": None, "window_note": outside_note(synced)}
        start, end, window_note = clipped
    figures, products = _account_figures(rest, profile, synced, start, end, searched, product)
    row = {"currency": profile.currency_code, "window": _window(start, end), **figures,
           "spend_exceeds_sales": figures["spend"] > figures["sales"],
           "without_sales": bool(figures["spend"]) and not figures["sales"],
           "attribution_days": attribution_days_by_product(products, _attribution_days(profile.account_type))}
    if window_note:
        row["window_note"] = window_note
    compared = comparison_window(synced, start, end, compare, compare_from, compare_to)
    if isinstance(compared, str):
        row["comparison_note"] = compared
    elif compared is not None:
        previous, _ = _account_figures(rest, profile, synced, compared.start, compared.end, searched, product)
        row.update(change_fields(figures, previous, "spend"), **activity_status(figures, previous),
                   comparison=_window(compared.start, compared.end))
    return row


def _account_figures(rest, profile: ProfileOption, synced: ProfileOption, start: date, end: date, searched: bool,
                     product: str) -> tuple[dict, list[str]]:
    """(metrics, products present) of one account over [start, end]; SB's or SD's new-to-brand when asked for one."""
    if searched:
        series = ReportProvider(rest).daily_totals(profile, start, end)
        return _days_metrics(series.days), ["SP"]
    series = campaign_totals.daily_totals(rest, synced, start, end, product=product)
    figures = _totals_metrics(campaign_totals.series_total(series))
    if product in NEW_TO_BRAND_PRODUCTS:
        figures.update(new_to_brand_fields(sum_new_to_brand(series.new_to_brand), figures["sales"]))
    return figures, list(series.products)


def _add_window_note(payload: dict, requested: int, start: date, end: date) -> None:
    note = days_note(requested, start, end)
    if note:
        payload["window_note"] = note


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _freshness(profile: ProfileOption, now: datetime) -> dict:
    """Today in the account's own zone, and whether its data reaches its yesterday, the last day a report can close."""
    today = now.astimezone(profile_timezone(profile.timezone, "")).date()
    return {"today": today.isoformat(),
            "up_to_date": profile.data_through is not None and profile.data_through >= today - timedelta(days=1)}


def _column(frame, keyword: str):
    return next((column for column in frame.columns if keyword in str(column).lower()), None)


