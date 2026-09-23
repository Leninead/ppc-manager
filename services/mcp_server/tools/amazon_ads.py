"""Las cuentas de Amazon Ads sincronizadas, sus search terms, su serie diaria, sus campañas, sus targets y la
estructura de sus campañas de Sponsored Products.

Se apoya en core/amazon_ads/ (report_provider, campaign_provider, product_provider, structure_provider,
campaign_totals y campaign_analyzer), que ya leen y clasifican sin Streamlit: acá no hay lógica de negocio nueva,
sólo la forma en que un modelo la consulta.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from core.search_term import frame as canonical
from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads import campaign_totals
from core.amazon_ads.advertised_asins import SEVERAL_ASINS, WITHOUT_ASIN, attribute_asins
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
)
from core.amazon_ads.campaign_provider import (
    BID_STRATEGY,
    BID_STRATEGY_LABELS,
    BUDGET_AMOUNT,
    CAMPAIGN_ID,
    CAMPAIGN_NAME,
    PORTFOLIO_NAME,
    TYPE,
    CampaignProvider,
    campaign_sync_view,
)
from core.amazon_ads.product_provider import (
    PRODUCT_CODES,
    PRODUCT_TYPES,
    PURCHASES_CLICKS,
    SALES_CLICKS,
    TARGET_BID,
    TARGET_ID,
    TARGET_KIND,
    TARGET_KIND_LABELS,
    TARGET_MATCH,
    TARGET_PRODUCT,
    TARGET_TEXT,
    ProductCampaigns,
    ProductProvider,
    campaigns_to_analyze,
)
from core.amazon_ads.report_provider import (
    DayTotals,
    ProfileOption,
    ReportProvider,
    _attribution_days,
    _portfolio_label,
    account_labels,
)
from core.amazon_ads.structure_provider import (
    _ATTRIBUTION_FIELDS,
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    CAMPAIGN_NEGATIVE_KEYWORD,
    CAMPAIGN_NEGATIVE_PRODUCT_TARGETING,
    KEYWORD,
    NEGATIVE_ENTITIES,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    StructureProvider,
)
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    CAMPAIGNS_KIND,
    SP_AD_GROUPS_KIND,
    SP_PRODUCT_ADS_KIND,
    SP_TARGETS_KIND,
    profile_timezone,
)
from core.integrations.sync_jobs import SyncJobStore
from services.mcp_server.limits import page
from services.mcp_server.tools.analyses import _account_time

# Un modelo que pide "los search terms de la cuenta" no quiere 177.000 filas: quiere los que mueven
# la aguja. El orden por gasto convierte una consulta vaga en una respuesta útil.
DEFAULT_DAYS = 7
MAX_DAYS = 60
# Dos semanas: alcanzan para ver una forma, y el patrón de los días de semana todavía se lee.
DEFAULT_SERIES_DAYS = 14
MAX_CAMPAIGNS_LISTED = 30
# Cómo cuenta cada producto sus ventas: sin esto, el modelo compara ACoS de SB con los de SP como si fueran iguales.
ATTRIBUTION_NOTE = ("Las ventas y órdenes de cada producto son las de Campaign Manager: SP después de un click; SB y SD "
                    "después de un click o una vista, a 14 días. sales_clicks y orders_clicks son sólo las de "
                    "después de un click: lo comparable entre productos.")
SERIES_SOURCE = "Sponsored Products, Brands y Display, de los reportes de campaña. " + ATTRIBUTION_NOTE
SEARCH_TERMS_SOURCE = ("Sólo Sponsored Products, sumado del reporte de search terms: sólo trae términos con clicks, así "
                       "que tiene muchas menos impresiones que los reportes de campaña; gasto, clicks, ventas y órdenes "
                       "quedan casi iguales.")
# Las cifras de SP salen de dos fuentes que no coinciden en impresiones: cada respuesta dice cómo pedir la otra,
# para que el chat las ofrezca como dos datos y no presente una en lugar de la otra.
SOURCE_CAMPAIGNS = "campaigns"
SOURCE_SEARCH_TERMS = "search_terms"
SOURCES = (SOURCE_CAMPAIGNS, SOURCE_SEARCH_TERMS)
SEARCH_TERMS_ALTERNATIVE = ("Las cifras de Sponsored Products también salen sumadas del reporte de search terms, con "
                            "source=search_terms: sólo traen términos con clicks, así que tienen muchas menos impresiones. "
                            "Son las que coinciden con el Search Term Report.")
CAMPAIGNS_ALTERNATIVE = ("Con source=campaigns salen de los reportes de campaña: suman Sponsored Brands y Display, y en "
                         "Sponsored Products traen todas las impresiones, también las de términos sin clicks.")
# Lo que el STR ya sabe agrupar: con esto una torta o un ranking sale de una llamada, no de sumar páginas. Por
# producto es un solo grupo, SP: el modelo lo pide así para comparar SP entre las dos fuentes.
_SEARCH_TERM_GROUPS = {"campaign": canonical.CAMPAIGN_NAME, "portfolio": canonical.PORTFOLIO_NAME, "product": None,
                       "match_type": "_origin_match_type", "search_term": canonical.SEARCH_TERM}
# Lo que agrupan los reportes de campaña de los tres productos: la fuente de siempre de campaña y portfolio.
_CAMPAIGN_GROUPS = ("campaign", "portfolio", "product")
_DIMENSIONS = ("campaign", "portfolio", "product", "match_type", "search_term", "asin")
_EMPTY_GROUP = {"portfolio": "Sin portfolio", "match_type": "Sin tipo"}
# Lo que no se atribuye a un ASIN queda en su grupo, sin repartir: los grupos siguen sumando el total.
_UNATTRIBUTED_GROUPS = {SEVERAL_ASINS: "Varios ASINs en el ad group", WITHOUT_ASIN: "Sin ASIN"}
ASIN_NOTE = ("El ASIN de cada término sale del producto anunciado de su ad group cuando anuncia uno solo; si anuncia "
             "varios, o no está en el listado, del ASIN del nombre de la campaña aunque el ad group no lo anuncie. Ese "
             "ASIN puede agrupar a toda una familia de productos: hablá del grupo, no de un producto solo. Lo que no se "
             "pudo atribuir queda en «Varios ASINs en el ad group» o «Sin ASIN», sin repartir entre ASINs.")
# El modelo copia lo que recibe: si le llega PRODUCT_TARGETING, el AM lee PRODUCT_TARGETING.
_MATCH_TYPE_LABELS = {"AUTO": "Automática", "PRODUCT_TARGETING": "Product targeting", "BROAD": "Broad",
                      "PHRASE": "Phrase", "EXACT": "Exact"}
RANKING_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr")
Dimension = Literal["campaign", "portfolio", "product", "match_type", "search_term", "asin"]
RankingMetric = Literal["spend", "sales", "orders", "clicks", "impressions", "acos", "cvr"]
# "" = sin filtro: un parámetro opcional con None llegaría al modelo sin tipo.
Diagnosis = Literal["", "FANTASMA", "PAUSAR", "REVISAR", "ESCALAR", "OK"]
Signal = Literal["", "Limitada por presupuesto", "Nueva", "Baja visibilidad"]
Product = Literal["", "SP", "SB", "SD"]
# "" = la fuente de siempre de cada herramienta: los reportes de campaña, salvo tipo de match y search term.
Source = Literal["", "campaigns", "search_terms"]
CAMPAIGNS_SOURCE = ("Sponsored Products, Brands y Display, de la foto de campañas y sus reportes: trae también las "
                    "campañas habilitadas sin actividad. Las señales sólo existen para SP. " + ATTRIBUTION_NOTE)
TARGETS_SOURCE = ("Los targets habilitados de campañas habilitadas de SP, SB y SD, de las listas de keywords y targets, "
                  "con las impresiones de sus reportes de targeting. El bid es el efectivo: el propio del target o, si "
                  "no tiene, el default de su ad group. Los de ad groups de SP listados como pausados quedan afuera. No "
                  "incluye las campañas SB del formato anterior: sus targets no tienen reporte.")
# What the chat asks for, and the families of the SP structure each one reads.
STRUCTURE_ENTITIES = {
    "campaigns": (CAMPAIGN,),
    "placements": (BIDDING_ADJUSTMENT,),
    "ad_groups": (AD_GROUP,),
    "keywords": (KEYWORD,),
    "product_targets": (PRODUCT_TARGETING,),
    "product_ads": (PRODUCT_AD,),
    "negatives": NEGATIVE_ENTITIES,
}
StructureEntity = Literal["campaigns", "placements", "ad_groups", "keywords", "product_targets", "product_ads",
                          "negatives"]
# A campaign's row carries its placement adjustments, which the database keeps as rows of their own family.
_STRUCTURE_READS = {**STRUCTURE_ENTITIES, "campaigns": (CAMPAIGN, BIDDING_ADJUSTMENT)}
# Past this, negatives are read one campaign at a time: a big account's, read whole, are hundreds of MB for one page.
MAX_ACCOUNT_NEGATIVES = 5000
STRUCTURE_STATES = ("enabled", "paused", "archived")
StructureState = Literal["", "enabled", "paused", "archived"]
STRUCTURE_SOURCE = ("Sólo Sponsored Products. La estructura es la foto diaria de las listas de entidades de Amazon Ads "
                    "(campañas, ad groups, keywords, targets, anuncios y negativos): es la de la hora de listed_at, "
                    "no la de este momento. Las métricas de la ventana, sólo de campañas, keywords y product targets, "
                    "salen de los reportes. El bid de un keyword o target es el efectivo: el propio o, si no tiene, el "
                    "default de su ad group (bid_source dice cuál). Un ajuste por placement en 0 es sin ajuste; vacío "
                    "es que no se sabe.")
_STRUCTURE_WHAT = {"campaigns": "campañas", "placements": "ajustes por placement", "ad_groups": "ad groups",
                   "keywords": "keywords", "product_targets": "product targets", "product_ads": "product ads",
                   "negatives": "negativos"}
_ENTITY_OF_FAMILY = {family: entity for entity, families in STRUCTURE_ENTITIES.items() for family in families}
# A listing whose job completed counts even with no rows; the negatives count by their snapshot, in the counts.
_LISTING_KINDS = {"campaigns": CAMPAIGN_ENTITIES_KIND, "ad_groups": SP_AD_GROUPS_KIND, "keywords": SP_TARGETS_KIND,
                  "product_targets": SP_TARGETS_KIND, "product_ads": SP_PRODUCT_ADS_KIND}
_CAMPAIGN_NEGATIVES = (CAMPAIGN_NEGATIVE_KEYWORD, CAMPAIGN_NEGATIVE_PRODUCT_TARGETING)
_MEASURED_ENTITIES = ("campaigns", "keywords", "product_targets")
# Campaign Manager's names for the placements, and the key each adjustment takes in a campaign's row.
_PLACEMENT_LABELS = {"PLACEMENT_TOP": "Top of search", "PLACEMENT_PRODUCT_PAGE": "Product pages",
                     "PLACEMENT_REST_OF_SEARCH": "Rest of search", "SITE_AMAZON_BUSINESS": "Amazon Business"}
_PLACEMENT_KEYS = {"PLACEMENT_TOP": "top_of_search_pct", "PLACEMENT_PRODUCT_PAGE": "product_pages_pct",
                   "PLACEMENT_REST_OF_SEARCH": "rest_of_search_pct", "SITE_AMAZON_BUSINESS": "amazon_business_pct"}
# The report keeps the last name each campaign had in the period: its state says whether it runs, never its name.
CAMPAIGN_STATUS = "Campaign Status"


def list_accounts(rest) -> dict:
    """Las cuentas de Amazon Ads sincronizadas, con su país, moneda, hasta qué día tienen datos, qué día es hoy en
    cada una y si sus datos están al día."""
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
    rows = [{**{str(name): _plain(value) for name, value in row.items() if not str(name).startswith("_")},
             CAMPAIGN_STATUS: row.get("_campaign_status") or ""} for _, row in ordered.iterrows()]
    payload = page(rows, offset=offset, limit=limit).as_payload(what="search terms")
    payload["window"] = _window(start, end)
    payload["currency"] = source.currency_code
    _add_window_note(payload, int(days), start, end)
    return payload


def daily_metrics(rest, *, profile_id: str, days: int = DEFAULT_SERIES_DAYS, campaign: str = "",
                  product: Product = "", source: Source = "") -> dict:
    """Las métricas por día de las campañas de una cuenta (SP, SB y SD, o sólo `product`), o de las campañas
    cuyo nombre contiene `campaign`.

    Salen de los reportes de campaña; con `source`=search_terms, sólo las de SP, sumadas del reporte de search
    terms. Una fila por cada día de la ventana, también los que no gastaron: una serie con huecos se
    dibujaría como si esos días no existieran.
    """
    _check_product(product)
    _check_source(source, product)
    if source == SOURCE_SEARCH_TERMS:
        profile = _profile(rest, profile_id)
        start, end = window_for(profile, days)
        series = ReportProvider(rest).daily_totals(profile, start, end, campaign=campaign)
        rows, products = [_day_row(day) for day in series.days], ["SP"]
    else:
        profile = _campaign_profile(rest, profile_id, search_terms_hint=product in ("", "SP"))
        start, end = window_for(profile, days)
        series = campaign_totals.daily_totals(rest, profile, start, end, campaign=campaign, product=product)
        rows = [{"date": day.day.isoformat(), **_totals_metrics(day.totals)} for day in series.days]
        products = list(series.products)
    payload = {"rows": rows, "window": _window(start, end), "currency": series.currency_code,
               "attribution_days": series.attribution_days, "products": products,
               **_source_fields(source or SOURCE_CAMPAIGNS, alternative=product in ("", "SP"))}
    _add_window_note(payload, int(days), start, end)
    if source != SOURCE_SEARCH_TERMS:
        _add_old_format_note(payload, rest, profile_id, start, end, product)
    fragment = campaign.strip()
    if fragment:
        payload["campaigns"] = list(series.campaigns[:MAX_CAMPAIGNS_LISTED])
        if len(series.campaigns) > MAX_CAMPAIGNS_LISTED:
            payload["campaigns_total"] = len(series.campaigns)
        if not series.campaigns:
            payload["rows"] = []
            payload["note"] = (f"Ninguna campaña de la cuenta tiene «{fragment}» en el nombre en este período. "
                               "Buscá el nombre exacto con campaign_health o breakdown por campaña.")
    return payload


def accounts_overview(rest, *, days: int = DEFAULT_DAYS, source: Source = "") -> dict:
    """Los totales de las campañas (SP, SB y SD) de cada cuenta sincronizada en sus últimos `days` días, todas
    en una llamada; con `source`=search_terms, los de SP sumados del reporte de search terms.

    Una cuenta que no gastó vuelve en cero en vez de faltar: su ausencia se leería como que no
    existe. Cada una en su moneda, y la respuesta lo avisa: los montos no se suman entre monedas.
    """
    _check_source(source)
    source = source or SOURCE_CAMPAIGNS
    jobs = SyncJobStore(rest)
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    rows, without_campaigns = [], []
    for profile in profiles:
        totals = _account_totals(rest, jobs, profile, days, source)
        if totals is not None:
            rows.append({"account": labels[profile.profile_id], "profile_id": profile.profile_id, **totals})
        elif profile.data_through is not None:
            without_campaigns.append(labels[profile.profile_id])
    rows.sort(key=lambda row: row["account"])
    payload = page(rows, limit=len(rows) or 1).as_payload(what="cuentas")
    payload.update(_source_fields(source, alternative=True))
    payload["note"] = ("Cada cuenta está en su moneda: no sumes ni compares montos entre monedas distintas. "
                       "ACoS, CVR, órdenes y clicks sí se comparan entre cuentas.")
    # Missing from the rows they would read as accounts that do not exist: they are named, with where their SP is.
    if without_campaigns:
        payload["without_campaigns"] = sorted(without_campaigns)
        payload["without_campaigns_note"] = (
            "Estas cuentas todavía no tienen campañas sincronizadas, así que no están en estos totales. Sus cifras de "
            "Sponsored Products sumadas de los search terms están con source=search_terms.")
    return payload


def breakdown(rest, *, profile_id: str, by: Dimension, days: int = DEFAULT_DAYS, product: Product = "",
              source: Source = "", sort_by: RankingMetric = "spend", asin: str = "", offset: int = 0,
              limit: int = 50) -> dict:
    """Los totales de una cuenta en la ventana, agrupados por campaña, portfolio, producto, tipo de match, search term
    o ASIN.

    Campaña, portfolio y producto salen de los reportes de campaña de SP, SB y SD (`product` los acota a uno);
    tipo de match, search term y ASIN, de los search terms, que sólo son de SP. Campaña, portfolio y producto también
    salen de los search terms con `source`=search_terms (por producto, un solo grupo: SP). `asin` deja sólo los
    search terms de ese ASIN. Ordenados de mayor a menor por `sort_by`; los grupos sin ventas no tienen ACoS y quedan
    al final de ese orden. `totals` suma todos los grupos, también los que no entran en la página.
    """
    if by not in _DIMENSIONS:
        raise ValueError(f"by tiene que ser uno de: {', '.join(_DIMENSIONS)}")
    if sort_by not in RANKING_METRICS:
        raise ValueError(f"sort_by tiene que ser uno de: {', '.join(RANKING_METRICS)}")
    _check_product(product)
    _check_source(source)
    wanted_asin = asin.strip().upper()
    if source == SOURCE_CAMPAIGNS and by not in _CAMPAIGN_GROUPS:
        raise ValueError(f"{by} sólo sale de los search terms: pedilo sin source o con source=search_terms.")
    if wanted_asin and source != SOURCE_SEARCH_TERMS and by in _CAMPAIGN_GROUPS:
        raise ValueError("El filtro asin sale de los search terms: pedilo con source=search_terms, o agrupá por "
                         "search_term o match_type.")
    if source != SOURCE_SEARCH_TERMS and by in _CAMPAIGN_GROUPS:
        return _campaign_breakdown(rest, profile_id, by, days, product, sort_by, offset, limit)
    if product not in ("", "SP"):
        raise ValueError(f"{by} sale de los search terms, que sólo son de Sponsored Products: pedilo sin product "
                         "o con product=SP.")
    profile = _profile(rest, profile_id)
    start, end = window_for(profile, days)
    terms = ReportProvider(rest).search_terms(profile, start, end)
    context = {"window": _window(start, end), "currency": terms.currency_code,
               "attribution_days": terms.attribution_days,
               **_source_fields(SOURCE_SEARCH_TERMS, alternative=by in _CAMPAIGN_GROUPS)}
    frame = terms.frame
    if frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "totals": None, **context,
                "note": "La cuenta no tuvo búsquedas con clicks en ese período."}

    asin_groups = None
    if by == "asin" or wanted_asin:
        attribution = attribute_asins(frame, ReportProvider(rest).advertised_asins(profile.profile_id),
                                      canonical.CAMPAIGN_NAME)
        asin_groups = attribution.asins.where(attribution.asins.notna(), attribution.origins.map(_UNATTRIBUTED_GROUPS))
        context["asin_note"] = ASIN_NOTE
    if wanted_asin:
        frame = frame[asin_groups.eq(wanted_asin)]
        if frame.empty:
            return {"rows": [], "total": 0, "showing": 0, "offset": 0, "totals": None, **context,
                    "note": f"Ningún search term del período se atribuye al ASIN {wanted_asin}."}

    column = _SEARCH_TERM_GROUPS.get(by)
    if by == "asin":
        groups = asin_groups.loc[frame.index]
    elif column is None:  # by product: every search term is Sponsored Products
        groups = PRODUCT_TYPES["SP"]
    else:
        groups = (frame[column].fillna("").astype(str).str.strip()
                  .replace(_MATCH_TYPE_LABELS if by == "match_type" else {})
                  .replace("", _EMPTY_GROUP.get(by, "Sin nombre")))
    sums = frame.assign(_group=groups).groupby("_group", sort=False).agg(
        spend=(canonical.SPEND, "sum"), sales=(canonical.sales_column(terms.attribution_days), "sum"),
        orders=(canonical.orders_column(terms.attribution_days), "sum"), clicks=(canonical.CLICKS, "sum"),
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


def campaign_health(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                    diagnosis: Diagnosis = "", signal: Signal = "", product: Product = "",
                    target_acos: float = 0, spend_to_pause: float = 0, min_orders_to_scale: int = 0,
                    sort_by: RankingMetric = "spend", offset: int = 0, limit: int = 50) -> dict:
    """Las campañas habilitadas de una cuenta (SP, SB y SD) en sus últimos `days` días, o de `date_from` a `date_to`,
    con el diagnóstico de Bulk Campañas y sus señales.

    Parte de la foto de campañas, así que trae también las que no tuvieron actividad (las FANTASMA), que
    `breakdown` por campaña no ve. Clasifica con los parámetros guardados de la cuenta en Bulk Campañas, o
    con los de siempre, y dice cuáles usó; `target_acos`, `spend_to_pause` y `min_orders_to_scale` reemplazan
    los que se pasen (0 = no cambia). `product` acota todo a SP, SB o SD; `diagnosis` y `signal` sólo
    filtran filas: `counts` y `totals` cubren todas las habilitadas del alcance, no sólo la página.
    """
    if sort_by not in RANKING_METRICS:
        raise ValueError(f"sort_by tiene que ser uno de: {', '.join(RANKING_METRICS)}")
    _check_product(product)
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
    analyzer, campaigns = analyze(frame, source.signal_inputs, params, window_start=start, window_end=end)
    context = {
        "window": _window(start, end), "currency": source.currency_code, "attribution_days": source.attribution_days,
        "source": CAMPAIGNS_SOURCE,
        "parameters": {**params.as_dict(), "origin": origin,
                       "rules": diagnosis_rules(params, has_impressions=analyzer.has_impressions)},
        # The last synced days are the provisional ones: a window ending earlier has none.
        "provisional_days": [day.isoformat() for day in provisional_days(None, profile.data_through)
                             if start <= day <= end],
    }
    if window_note:
        context["window_note"] = window_note
    _add_old_format_note(context, rest, profile_id, start, end, product, products=products)
    if campaigns.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "counts": {}, "totals": None, **context,
                "note": "La cuenta no tiene campañas habilitadas en este período."}

    rows = [_campaign_row(row, analyzer.has_impressions) for _, row in campaigns.iterrows()]
    counts = campaigns[DIAGNOSIS_COLUMN].map(diagnosis_name).value_counts()
    totals = _metrics(campaigns["_spend"].sum(), campaigns["_sales"].sum(), campaigns["_orders"].sum(),
                      campaigns["_clicks"].sum(), campaigns["_impr"].sum() if analyzer.has_impressions else 0)
    if diagnosis:
        rows = [row for row in rows if row["diagnosis"] == diagnosis]
    if signal:
        rows = [row for row in rows if signal in row["signals"]]
    rows.sort(key=lambda row: (row[sort_by] is not None, row[sort_by] or 0), reverse=True)
    payload = page(rows, offset=offset, limit=limit).as_payload(what="campañas")
    payload.update(context, counts={str(name): int(count) for name, count in counts.items()}, totals=totals,
                   pause_spend=round(float(campaigns.loc[campaigns[DIAGNOSIS_COLUMN] == PAUSE, "_spend"].sum()), 2))
    return payload


def idle_targets(rest, *, profile_id: str, days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                 product: Product = "", offset: int = 0, limit: int = 50) -> dict:
    """Target Graduation: los targets habilitados, de campañas habilitadas, sin una impresión en los últimos `days`
    días o de `date_from` a `date_to`, con su bid efectivo. Los de ad groups de SP listados como pausados no se miran.

    `counts` dice, por producto, cuántos se miraron y cuántos no tuvieron impresiones, también los que no
    entran en la página. `product` acota a SP, SB o SD.
    """
    _check_product(product)
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


def campaign_structure(rest, *, profile_id: str, entity: StructureEntity = "campaigns", campaign: str = "",
                       state: StructureState = "", days: int = DEFAULT_DAYS, date_from: str = "", date_to: str = "",
                       offset: int = 0, limit: int = 50) -> dict:
    """La estructura de Sponsored Products de una cuenta, como Amazon Ads la listó por última vez: sus campañas con
    presupuesto, estrategia y ajustes por placement (`entity`=campaigns), o sus placements, ad_groups, keywords,
    product_targets, product_ads o negatives.

    `campaign` deja la estructura de las campañas con eso en el nombre, o de la campaña con ese id; `state`, las filas
    en ese estado. `counts` dice cuántas hay de cada tipo en la cuenta o en esas campañas, en cualquier estado, y
    `listed_at` cuándo se listó cada tipo. Campañas, keywords y product targets traen sus métricas de los últimos
    `days` días, o de `date_from` a `date_to`, cuando hay reportes de esa ventana. Más de `MAX_ACCOUNT_NEGATIVES`
    negativos se leen de a una campaña: sin `campaign`, o con uno que abarca varias campañas, vuelven sólo contados.
    """
    families = STRUCTURE_ENTITIES.get(entity)
    if families is None:
        raise ValueError(f"entity tiene que ser uno de: {', '.join(STRUCTURE_ENTITIES)}")
    if state and state not in STRUCTURE_STATES:
        raise ValueError(f"state tiene que ser uno de: {', '.join(STRUCTURE_STATES)}, o vacío para todos")
    profile = _campaign_profile(rest, profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    context = {"window": _window(start, end), "currency": profile.currency_code,
               "attribution_days": _attribution_days(profile.account_type), "source": STRUCTURE_SOURCE}
    if window_note:
        context["window_note"] = window_note
    provider = StructureProvider(rest)
    fragment = campaign.strip()
    named = None
    if fragment:
        campaigns = provider.sp_structure(profile, start, end, entities=(CAMPAIGN,))
        if campaigns is None:
            return _structure_not_synced(context)
        named = _named_campaigns(campaigns.rows, fragment)
        if named.empty:
            if "campaigns" not in _listed_entities(rest, profile_id, campaigns.listed_at):
                return _no_structure_rows(context, f"Todavía no se sincronizaron {_STRUCTURE_WHAT['campaigns']} "
                                                   "de esta cuenta.")
            # No counts: an empty one would read as nothing synced, and there are no campaigns to count in.
            return _no_structure_rows(
                {**context, "listed_at": _structure_listing_times(campaigns.listed_at, profile)},
                f"Ninguna campaña de Sponsored Products de la cuenta tiene «{fragment}» en el nombre ni ese id.")
    campaign_ids = tuple(named["campaign_id"]) if named is not None else ()

    counted = provider.sp_structure_counts(profile, start, end, campaign_ids=campaign_ids)
    listed = _listed_entities(rest, profile_id, counted.rows) if counted is not None else set()
    if not listed:
        return _structure_not_synced(context)
    if "campaigns" in listed and _placements_known(counted.rows):
        listed.add("placements")
    counts = {name: sum(counted.rows.get(family, 0) for family in STRUCTURE_ENTITIES[name])
              for name in STRUCTURE_ENTITIES if name in listed}
    context.update(counts=counts, listed_at=_structure_listing_times(counted.listed_at, profile))
    if named is not None:
        names = list(dict.fromkeys(named["campaign_name"]))
        context["campaigns"] = names[:MAX_CAMPAIGNS_LISTED]
        if len(names) > MAX_CAMPAIGNS_LISTED:
            context["campaigns_total"] = len(names)

    what = _STRUCTURE_WHAT[entity]
    if entity not in listed:
        where = f"de las campañas con «{fragment}»" if fragment else "de esta cuenta"
        return _no_structure_rows(context, f"Todavía no se sincronizaron {what} {where}.")
    if not counts[entity]:
        none = (f"Las campañas con «{fragment}» no tienen {what}" if fragment
                else f"La cuenta no tiene {what} de Sponsored Products")
        return _no_structure_rows(context, f"{none} en el último listado.")
    if entity == "negatives" and counts[entity] > MAX_ACCOUNT_NEGATIVES and len(campaign_ids) != 1:
        return {"rows": [], **context, "note": _too_many_negatives(counts[entity], fragment, len(campaign_ids))}

    structure = provider.sp_structure(profile, start, end, entities=_STRUCTURE_READS[entity],
                                      campaign_ids=campaign_ids)
    scope = structure.rows
    wanted = scope[scope["entity"].isin(families)]
    if state:
        wanted = wanted[wanted["state"].str.upper() == state.upper()]
    placements = _campaign_placements(scope) if entity == "campaigns" else {}
    sales_field, orders_field = _ATTRIBUTION_FIELDS[structure.attribution_days]
    rows = []
    for record in wanted.to_dict("records"):
        row = _STRUCTURE_ROWS[entity](record)
        if entity == "campaigns":
            row.update(placements.get(record["campaign_id"], dict.fromkeys(_PLACEMENT_KEYS.values())))
        if record["metrics_known"]:
            row.update(_metrics(record["cost"], record[sales_field], record[orders_field], record["clicks"],
                                record["impressions"]))
        rows.append(row)
    payload = page(rows, offset=offset, limit=limit).as_payload(what=what)
    payload.update(context)
    if entity in _MEASURED_ENTITIES and not wanted["metrics_known"].all():
        payload["metrics_note"] = ("Todavía no hay reportes de esta ventana para estas filas: van sin métricas, que no "
                                   "se conocen (no son cero).")
    return payload


def _too_many_negatives(total: int, fragment: str, campaigns: int) -> str:
    """Why negatives wider than one campaign come back only counted, and how to ask for fewer."""
    if not fragment:
        return (f"La cuenta tiene {total} negativos: son demasiados para traerlos todos. Pedí los de una campaña con "
                "campaign (parte de su nombre o su id).")
    return (f"Las {campaigns} campañas con «{fragment}» tienen {total} negativos: son demasiados para traerlos todos. "
            "Pedí los de una sola campaña con campaign (más de su nombre, o su id).")


def _structure_not_synced(context: dict) -> dict:
    return _no_structure_rows({**context, "counts": {}, "listed_at": {}},
                              "La estructura de las campañas de esta cuenta todavía no se sincronizó.")


def _no_structure_rows(context: dict, note: str) -> dict:
    return {"rows": [], "total": 0, "showing": 0, "offset": 0, **context, "note": note}


def _named_campaigns(campaigns, fragment: str):
    """The campaign rows `fragment` names: by part of their name, whatever the case, or by their id."""
    named = campaigns["campaign_id"].eq(fragment) | campaigns["campaign_name"].str.casefold().str.contains(
        fragment.casefold(), regex=False)
    return campaigns[named]


def _listed_entities(rest, profile_id: str, families) -> set[str]:
    """The entities Amazon Ads listed for the account: those whose families were counted, and those whose listing
    job completed empty."""
    listed = {_ENTITY_OF_FAMILY[family] for family in families} - {"placements"}
    store = SyncJobStore(rest)
    for kind in dict.fromkeys(kind for entity, kind in _LISTING_KINDS.items() if entity not in listed):
        job = store.latest_completed_for_profile(profile_id, kind)
        # A listing Amazon refused also completes, with no rows and the refusal as its warning.
        if job is not None and not job.warning:
            listed.update(entity for entity, listing in _LISTING_KINDS.items() if listing == kind)
    return listed


def _placements_known(families) -> bool:
    """Whether the campaigns in scope carry their placement adjustments: one listed without them has them unknown."""
    return BIDDING_ADJUSTMENT in families or CAMPAIGN not in families


def _structure_listing_times(listed_at: dict, profile: ProfileOption) -> dict:
    """When each entity the chat asks for was last listed, on the account's clock."""
    latest = {}
    for family, moment in listed_at.items():
        entity = _ENTITY_OF_FAMILY[family]
        latest[entity] = max(moment, latest.get(entity, moment))
    return {entity: _account_time(latest[entity], profile) for entity in STRUCTURE_ENTITIES if entity in latest}


def _campaign_placements(scope) -> dict:
    """Campaign id -> its four placement percentages; a campaign without them has them unknown."""
    placements = {}
    for record in scope[scope["entity"].eq(BIDDING_ADJUSTMENT)].to_dict("records"):
        adjustments = placements.setdefault(record["campaign_id"], dict.fromkeys(_PLACEMENT_KEYS.values()))
        adjustments[_PLACEMENT_KEYS[record["placement"]]] = _plain_number(record["percentage"])
    return placements


def _structure_campaign_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "portfolio": _portfolio_label(record["portfolio_id"], record["portfolio_name"]),
            "state": record["state"], "targeting_type": record["targeting_type"],
            "budget": _plain_number(record["budget_amount"]), "budget_type": record["budget_type"],
            "bid_strategy": BID_STRATEGY_LABELS.get(record["bidding_strategy"], record["bidding_strategy"])}


def _structure_placement_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"], "state": record["state"],
            "bid_strategy": BID_STRATEGY_LABELS.get(record["bidding_strategy"], record["bidding_strategy"]),
            "placement": _PLACEMENT_LABELS.get(record["placement"], record["placement"]),
            "percentage": _plain_number(record["percentage"])}


def _structure_ad_group_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"], "state": record["state"],
            "default_bid": _plain_number(record["default_bid"])}


def _structure_target_row(record: dict) -> dict:
    own_bid, default_bid = _plain_number(record["own_bid"]), _plain_number(record["default_bid"])
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"],
            "target": record["target_text"], "target_id": record["entity_id"],
            "kind": TARGET_KIND_LABELS.get(record["target_kind"], record["target_kind"]),
            "match_type": record["match_type"], "state": record["state"], "bid": _plain_number(record["bid"]),
            "own_bid": own_bid, "default_bid": default_bid,
            "bid_source": "own" if own_bid is not None else "ad_group_default" if default_bid is not None else ""}


def _structure_product_ad_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"], "asin": record["asin"],
            "sku": record["sku"], "state": record["state"], "ad_id": record["entity_id"]}


def _structure_negative_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"],
            "level": "campaign" if record["entity"] in _CAMPAIGN_NEGATIVES else "ad_group",
            "kind": TARGET_KIND_LABELS.get(record["target_kind"], record["target_kind"]),
            "negative": record["target_text"], "match_type": record["match_type"], "state": record["state"],
            "negative_id": record["entity_id"]}


_STRUCTURE_ROWS = {
    "campaigns": _structure_campaign_row,
    "placements": _structure_placement_row,
    "ad_groups": _structure_ad_group_row,
    "keywords": _structure_target_row,
    "product_targets": _structure_target_row,
    "product_ads": _structure_product_ad_row,
    "negatives": _structure_negative_row,
}


def _campaign_profile(rest, profile_id: str, *, search_terms_hint: bool = False) -> ProfileOption:
    """La cuenta como la ve la sincronización de campañas: los días que guarda, hasta su última corrida completa."""
    for profile in ReportProvider(rest).profiles():
        if profile.profile_id == profile_id:
            view = campaign_sync_view(
                profile, SyncJobStore(rest).latest_completed_for_profile(profile_id, CAMPAIGNS_KIND))
            if view.data_through is None:
                hint = (" Sus cifras de Sponsored Products sumadas de los search terms están con source=search_terms."
                        if search_terms_hint and profile.data_through is not None else "")
                raise ValueError(f"La cuenta {profile_id} todavía no tiene campañas sincronizadas.{hint}")
            return view
    raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")


def _campaign_row(row, has_impressions: bool) -> dict:
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
    return record


def _campaign_breakdown(rest, profile_id: str, by: str, days: int, product: str, sort_by: str, offset: int,
                        limit: int) -> dict:
    # SB and SD have nothing in the search terms: only a split that holds SP can be asked from there.
    alternative = product in ("", "SP")
    profile = _campaign_profile(rest, profile_id, search_terms_hint=alternative)
    start, end = window_for(profile, days)
    frame = campaign_totals.window_totals(rest, profile, start, end)
    if product:
        frame = frame[frame["product"] == product]
    context = {"window": _window(start, end), "currency": profile.currency_code,
               "attribution_days": _attribution_days(profile.account_type),
               **_source_fields(SOURCE_CAMPAIGNS, alternative=alternative)}
    _add_old_format_note(context, rest, profile_id, start, end, product)
    if frame.empty:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "totals": None, **context,
                "note": "Las campañas de la cuenta no tuvieron actividad en ese período."}
    groups = frame[by].replace(PRODUCT_TYPES) if by == "product" else frame[by]
    groups = groups.replace("", _EMPTY_GROUP.get(by, "Sin nombre"))
    metric_columns = list(campaign_totals.Totals.__dataclass_fields__)
    sums = frame.assign(_group=groups).groupby("_group", sort=False)[metric_columns].sum()
    rows = [{"group": str(group), **_totals_metrics(campaign_totals.Totals(**row))}
            for group, row in sums.to_dict("index").items()]
    rows.sort(key=lambda row: (row[sort_by] is not None, row[sort_by] or 0), reverse=True)
    payload = page(rows, offset=offset, limit=limit).as_payload(what="grupos")
    payload.update(context, totals=_totals_metrics(campaign_totals.Totals(**sums.sum().to_dict())))
    _add_window_note(payload, int(days), start, end)
    return payload


def _check_product(product: str) -> None:
    if product and product not in PRODUCT_TYPES:
        raise ValueError(f"product tiene que ser uno de: {', '.join(PRODUCT_TYPES)}, o vacío para los tres")


def _check_source(source: str, product: str = "") -> None:
    if source and source not in SOURCES:
        raise ValueError(f"source tiene que ser uno de: {', '.join(SOURCES)}, o vacío para la fuente de siempre")
    if source == SOURCE_SEARCH_TERMS and product not in ("", "SP"):
        raise ValueError("Los search terms sólo son de Sponsored Products: pedilo sin product o con product=SP.")


def _source_fields(source: str, *, alternative: bool) -> dict:
    """Where the figures come from and, when SP's also exist in the other source, how to ask for those."""
    fields = {"data_source": source,
              "source": SERIES_SOURCE if source == SOURCE_CAMPAIGNS else SEARCH_TERMS_SOURCE}
    if alternative:
        fields["alternative"] = SEARCH_TERMS_ALTERNATIVE if source == SOURCE_CAMPAIGNS else CAMPAIGNS_ALTERNATIVE
    return fields


def _account_totals(rest, jobs: SyncJobStore, profile: ProfileOption, days: int, source: str) -> dict | None:
    """One account's row of accounts_overview, or None while it has no data from that source yet."""
    if source == SOURCE_SEARCH_TERMS:
        if profile.data_through is None:
            return None
        start, end = window_for(profile, days)
        series = ReportProvider(rest).daily_totals(profile, start, end)
        return {"currency": series.currency_code, "window": _window(start, end), **_days_metrics(series.days)}
    view = campaign_sync_view(profile, jobs.latest_completed_for_profile(profile.profile_id, CAMPAIGNS_KIND))
    if view.data_through is None:
        return None
    start, end = window_for(view, days)
    series = campaign_totals.daily_totals(rest, view, start, end)
    return {"currency": series.currency_code, "window": _window(start, end),
            **_totals_metrics(campaign_totals.series_total(series))}


def _day_row(day: DayTotals) -> dict:
    return {"date": day.day.isoformat(), **_days_metrics((day,))}


def _days_metrics(days) -> dict:
    return _metrics(sum(day.spend for day in days), sum(day.sales for day in days), sum(day.orders for day in days),
                    sum(day.clicks for day in days), sum(day.impressions for day in days))


def _totals_metrics(totals: campaign_totals.Totals) -> dict:
    return {**_metrics(totals.spend, totals.sales, totals.orders, totals.clicks, totals.impressions),
            "sales_clicks": round(float(totals.sales_clicks), 2), "orders_clicks": int(totals.orders_clicks)}


def _add_old_format_note(payload: dict, rest, profile_id: str, start: date, end: date, product: str, *,
                         products: ProductCampaigns | None = None) -> None:
    """Says so when SB campaigns of the old format have unknown metrics: their spend is in no total."""
    if product not in ("", "SB"):
        return
    products = products if products is not None else ProductProvider(rest).campaigns(profile_id, start, end)
    if products is None or not products.without_metrics:
        return
    count = len(products.without_metrics)
    payload["old_format_note"] = (
        ("1 campaña SB del formato anterior todavía no tiene métricas: su gasto y sus ventas no están"
         if count == 1 else
         f"{count} campañas SB del formato anterior todavía no tienen métricas: su gasto y sus ventas no están")
        + " en estos números. Aparecen cuando termina de cargarse su historia.")


def _plain_number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN: unknown, not zero
        return None
    return int(number) if number.is_integer() else round(number, 2)


def window_for(profile: ProfileOption, days: int) -> tuple[date, date]:
    """Los últimos `days` días sincronizados de una cuenta, con tope en MAX_DAYS y recortados a lo que tiene."""
    window_days = max(1, min(int(days), MAX_DAYS))
    end = profile.data_through
    return max(profile.data_from or end, end - timedelta(days=window_days - 1)), end


def requested_window(profile: ProfileOption, days: int, date_from: str = "",
                     date_to: str = "") -> tuple[date, date, str]:
    """(start, end, note): the exact dates asked for, clipped to what the account has synced, or its last `days`.

    The dates are the ones the AM has on screen, so the chat can read what the page shows and not only the last days.
    """
    if not (date_from or date_to):
        start, end = window_for(profile, days)
        return start, end, _days_note(int(days), start, end)
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except ValueError as exc:
        raise ValueError("date_from y date_to van juntos y en formato AAAA-MM-DD.") from exc
    if end < start:
        raise ValueError(f"date_to ({end.isoformat()}) es anterior a date_from ({start.isoformat()}).")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"El período puede tener hasta {MAX_DAYS} días; del {start.isoformat()} al "
                         f"{end.isoformat()} hay {(end - start).days + 1}.")
    earliest = profile.data_from or profile.data_through - timedelta(days=MAX_DAYS - 1)
    clipped_start, clipped_end = max(start, earliest), min(end, profile.data_through)
    if clipped_start > clipped_end:
        raise ValueError(f"La cuenta tiene datos sincronizados del {earliest.isoformat()} al "
                         f"{profile.data_through.isoformat()}: el período pedido queda afuera.")
    if (clipped_start, clipped_end) == (start, end):
        return start, end, ""
    return clipped_start, clipped_end, (
        f"Se pidió del {start.isoformat()} al {end.isoformat()} y la cuenta tiene datos sincronizados del "
        f"{earliest.isoformat()} al {profile.data_through.isoformat()}: la ventana se recortó a esos días.")


def _add_window_note(payload: dict, requested: int, start: date, end: date) -> None:
    note = _days_note(requested, start, end)
    if note:
        payload["window_note"] = note


def _days_note(requested: int, start: date, end: date) -> str:
    returned = (end - start).days + 1
    if returned >= requested:
        return ""
    if requested > MAX_DAYS and returned == MAX_DAYS:
        return f"Se pidieron {requested} días y el máximo es {MAX_DAYS}: la ventana trae esos."
    return f"Se pidieron {requested} días y la cuenta tiene {returned} sincronizados: la ventana se recortó a esos."


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _freshness(profile: ProfileOption, now: datetime) -> dict:
    """Today in the account's own zone, and whether its data reaches its yesterday, the last day a report can close."""
    today = now.astimezone(profile_timezone(profile.timezone, "")).date()
    return {"today": today.isoformat(),
            "up_to_date": profile.data_through is not None and profile.data_through >= today - timedelta(days=1)}


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
