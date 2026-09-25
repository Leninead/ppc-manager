"""breakdown: an account's totals over a window, split by campaign, portfolio, product, match type, search term or
ASIN and ranked, with each group compared against the period before or drawn week by week when asked.

Campaign, portfolio and product come from the campaign reports of SP, SB and SD; match type, search term and ASIN
from the search terms, which are only SP. One grouping serves the window, the period it is compared with and each
week or month of a series, so a group is the same group in all of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

import pandas as pd

from core.amazon_ads import campaign_totals
from core.amazon_ads.advertised_asins import SEVERAL_ASINS, WITHOUT_ASIN, attribute_asins
from core.amazon_ads.campaign_catalog import campaign_catalog
from core.amazon_ads.product_provider import PRODUCT_TYPES, NewToBrand
from core.amazon_ads.report_provider import ReportProvider, _attribution_days
from core.search_term import frame as canonical
from services.mcp_server.limits import page
from services.mcp_server.tools.account_resolver import campaign_profile, choose_account, profile_by_id
from services.mcp_server.tools.analyses import NO_PREVIOUS, trend_between
from services.mcp_server.tools.asin_attribution import ATTRIBUTION_NOTE, advertised_in, attribution_by_asin
from services.mcp_server.tools.campaign_selector import (
    CampaignRequest,
    CampaignSelection,
    CampaignState,
    merged_catalog,
    no_match_note,
    select_campaigns,
)
from services.mcp_server.tools.figures import (
    NEW_TO_BRAND_NOTE,
    SHARED_METRICS,
    SOURCE_CAMPAIGNS,
    SOURCE_SEARCH_TERMS,
    Product,
    Source,
    _add_old_format_note,
    _check_product,
    _check_source,
    _metrics,
    _source_fields,
    _totals_metrics,
    _with_shares,
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
    Compare,
    ComparisonWindow,
    change_leaders,
    compared_rows,
    compared_totals,
    comparison_window,
    status_counts,
)
from services.mcp_server.tools.period_series import Period, periods_within
from services.mcp_server.tools.windows import DEFAULT_DAYS, requested_window, window_payload

Dimension = Literal["campaign", "portfolio", "product", "match_type", "search_term", "campaign_search_term", "asin"]
DIMENSIONS = ("campaign", "portfolio", "product", "match_type", "search_term", "campaign_search_term", "asin")
CAMPAIGN_DIMENSIONS = ("campaign", "portfolio", "product")
# What the campaign reports and the search terms carry a row for, and so can filter by.
GROUP_FILTER_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc")
MatchTypeFilter = Literal["", "exact", "phrase", "broad", "auto", "asin", "category"]
# How a search term reached the ad: a keyword's match type, the automatic targeting, or a product target by ASIN
# or by category. The model copies what it gets, so the groups carry Campaign Manager's names.
MATCH_TYPE_LABELS = {"exact": "Exact", "phrase": "Phrase", "broad": "Broad", "auto": "Automática",
                     "asin": "Product targeting · ASIN", "category": "Product targeting · categoría",
                     "product_targeting": "Product targeting", "": "Sin tipo"}
_KEYWORD_ORIGINS = {"EXACT": "exact", "PHRASE": "phrase", "BROAD": "broad", "AUTO": "auto"}
_EXPRESSION_KINDS = {"asin": "asin", "asin-expanded": "asin", "category": "category"}
EMPTY_GROUPS = {"portfolio": "Sin portfolio"}
UNATTRIBUTED_GROUPS = {SEVERAL_ASINS: "Varios ASINs en el ad group", WITHOUT_ASIN: "Sin ASIN"}
MAX_SERIES_GROUPS = 20
UNSOLD_TERMS_NOTE = ("spend_without_sales es lo que gastaron, dentro de cada grupo, los search terms que no vendieron "
                     "nada en su campaña en el período: dice dónde está el gasto sin ventas sin sumar términos a mano.")
ASIN_NOTE = ("El ASIN de cada término sale del producto anunciado de su ad group cuando anuncia uno solo; si anuncia "
             "varios, o no está en el listado, del ASIN del nombre de la campaña aunque el ad group no lo anuncie. Ese "
             "ASIN puede agrupar a toda una familia de productos: hablá del grupo, no de un producto solo. Lo que no se "
             "pudo atribuir queda en «Varios ASINs en el ad group» o «Sin ASIN», sin repartir entre ASINs.")
CAMPAIGNS_COUNT_NOTE = ("campaigns es cuántas campañas suma cada grupo: la cifra de un grupo de varias no es la de una "
                        "campaña sola.")
OTHER_CAMPAIGNS_NOTE = ("other_campaigns dice en cuántas otras campañas corrió el mismo término y cuánto gastó en ellas: "
                        "la fila es la del término en esta campaña y este ad group, no su total.")
SERIES_NOTE = ("series trae, para los primeros grupos de la lista, su gasto y su ACoS en cada {period} de la ventana "
               "(la semana va de lunes a domingo); complete=false es un período que la ventana corta. trend compara "
               "los dos últimos períodos completos: subió, bajó o igual.")
_PERIOD_NAMES = {"week": "semana", "month": "mes"}
# The fields that name a group rather than measure it: a group that left keeps them, with zero figures.
_IDENTITY_FIELDS = ("group", "campaign_id", "product", "portfolio", "state", "daily_budget", "campaign", "ad_group")


@dataclass(frozen=True)
class Grouping:
    rows: list[dict]
    totals: dict
    extra_totals: dict


def breakdown(rest, *, by: Dimension, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS,
              date_from: str = "", date_to: str = "", product: Product = "", source: Source = "",
              sort_by: SortMetric = "spend", sort_order: SortOrder = "desc", filters: FiltersParam = None,
              campaign: str = "", campaigns: tuple[str, ...] = (), state: CampaignState = "",
              portfolio: str = "",
              asin: str = "", match_type: MatchTypeFilter = "", compare: Compare = "", compare_from: str = "",
              compare_to: str = "", order_by_change: bool = False, by_period: Period = "", series_groups: int = 10,
              offset: int = 0, limit: int = 50) -> dict:
    """Los totales de una cuenta en sus últimos `days` días o de `date_from` a `date_to`, agrupados por campaña,
    portfolio, producto, tipo de match, search term o ASIN, rankeados por `sort_by`.

    `filters` deja los grupos que cumplen sus cotas; `campaign`, `campaigns`, `state` y `portfolio` acotan las
    campañas que se suman, y `asin` y `match_type` los search terms. `compare` los pone al lado del período anterior y
    `by_period` dibuja la serie de los primeros `series_groups` grupos por semana o por mes.
    """
    if by not in DIMENSIONS:
        raise ValueError(f"by tiene que ser uno de: {', '.join(DIMENSIONS)}")
    check_sort(sort_by)
    _check_product(product)
    _check_source(source)
    if match_type not in MATCH_TYPE_LABELS or match_type == "product_targeting":
        raise ValueError("match_type tiene que ser exact, phrase, broad, auto, asin o category.")
    if by_period not in ("", "week", "month"):
        raise ValueError("by_period tiene que ser week o month.")
    if order_by_change and not (compare or compare_from or compare_to):
        raise ValueError("order_by_change ordena por el cambio contra otro período: pedilo con compare.")
    row_filter = RowFilter.from_request(filters, metrics=GROUP_FILTER_METRICS)
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    request = CampaignRequest.of(campaign, campaigns, state, portfolio)
    from_campaign_reports = source != SOURCE_SEARCH_TERMS and by in CAMPAIGN_DIMENSIONS
    if source == SOURCE_CAMPAIGNS and by not in CAMPAIGN_DIMENSIONS:
        raise ValueError(f"{by} sólo sale de los search terms: pedilo sin source o con source=search_terms.")
    wanted_asin = asin.strip().upper()
    if from_campaign_reports and (wanted_asin or match_type):
        raise ValueError("asin y match_type salen de los search terms: pedilo con source=search_terms, o agrupá por "
                         "search_term, match_type o asin.")
    if not from_campaign_reports and product not in ("", "SP"):
        raise ValueError(f"{by} sale de los search terms, que sólo son de Sponsored Products: pedilo sin product "
                         "o con product=SP.")

    if from_campaign_reports:
        reader = _CampaignReports(rest, choice.profile_id, by, product, request)
    else:
        reader = _SearchTerms(rest, choice.profile_id, by, request, wanted_asin, match_type)
    start, end, window_note = requested_window(reader.profile, days, date_from, date_to)
    grouping = reader.group(start, end)
    context = {"window": window_payload(start, end), "currency": reader.profile.currency_code or reader.currency,
               "attribution_days": _attribution_days(reader.profile.account_type), **reader.context(start, end)}
    if window_note:
        context["window_note"] = window_note
    if reader.selection is not None:
        context.update(reader.selection.payload())
    if grouping is None:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "totals": None, **context,
                "note": _empty_note(reader, request)}

    rows = with_sort_figure(grouping.rows, sort_by)
    totals = {**grouping.totals, **grouping.extra_totals}
    leaders = _leaders(rows)
    compared = comparison_window(reader.profile, start, end, compare, compare_from, compare_to)
    if isinstance(compared, str):
        context["comparison_note"] = compared
    elif isinstance(compared, ComparisonWindow):
        previous = reader.group(compared.start, compared.end)
        previous_rows = with_sort_figure(previous.rows, sort_by) if previous else []
        previous_totals = previous.totals if previous else _empty_totals()
        rows = compared_rows(rows, previous_rows, reader.key, sort_by, _gone_row)
        totals = {**compared_totals(grouping.totals, previous_totals), **grouping.extra_totals}
        leaders.update(change_leaders(rows, sort_by))
        context.update(compared.payload(), compare_counts=status_counts(rows))
    rows = [row for row in rows if row_filter.keeps(row)]
    rows = sort_rows(rows, f"delta_{sort_by}" if order_by_change else sort_by, sort_order)
    if by_period:
        _add_series(rows[offset:offset + max(1, min(int(series_groups), MAX_SERIES_GROUPS))], reader, by_period,
                    start, end)
        context["series_note"] = SERIES_NOTE.format(period=_PERIOD_NAMES[by_period])
    payload = page(rows, offset=offset, limit=limit).as_payload(what="grupos")
    payload.update(context, totals=totals, leaders=leaders, **row_filter.described())
    return payload


class _CampaignReports:
    """Groups of the campaign reports of SP, SB and SD: campaigns, portfolios or products."""

    empty_note = "Las campañas de la cuenta no tuvieron actividad en ese período."

    def __init__(self, rest, profile_id: str, by: str, product: str, request: CampaignRequest):
        self.rest, self.by, self.product, self.request = rest, by, product, request
        self.alternative = product in ("", "SP")
        self.profile = campaign_profile(rest, profile_id, search_terms_hint=self.alternative)
        self.currency = ""
        self.selection: CampaignSelection | None = None
        self._catalog = None
        self._listed_loaded = False

    def key(self, row: dict):
        return row["campaign_id"] if self.by == "campaign" else row["group"]

    def context(self, start: date, end: date) -> dict:
        fields = _source_fields(SOURCE_CAMPAIGNS, alternative=self.alternative)
        _add_old_format_note(fields, self.rest, self.profile.profile_id, start, end, self.product)
        if self.by in ("portfolio", "product"):
            fields["campaigns_note"] = CAMPAIGNS_COUNT_NOTE
        if self.by == "product" or (self.by == "campaign" and self.product in ("", "SB", "SD")):
            fields["new_to_brand_note"] = NEW_TO_BRAND_NOTE
        return fields

    def group(self, start: date, end: date) -> Grouping | None:
        frame = campaign_totals.window_totals(self.rest, self.profile, start, end)
        if self.product:
            frame = frame[frame["product"] == self.product]
        if self.request.applied():
            if self.selection is None:
                self.selection = select_campaigns(self._campaigns(frame), self.request)
            frame = frame[frame["campaign_id"].isin(self.selection.ids)]
        if frame.empty:
            return None
        catalog = self._campaigns(frame) if self.by == "campaign" else None
        columns = list(campaign_totals.Totals.__dataclass_fields__)
        keys = frame["campaign_id"] if self.by == "campaign" else self._labels(frame)
        rows = []
        for key, part in frame.groupby(keys, sort=False):
            figures = _totals_metrics(campaign_totals.Totals(**part[columns].sum().to_dict()))
            rows.append({**self._identity(key, part, catalog), **figures, **self._new_to_brand(part, figures)})
        whole = _totals_metrics(campaign_totals.Totals(**frame[columns].sum().to_dict()))
        return Grouping(_with_shares(rows, whole), whole_metrics(whole), {})

    def _labels(self, frame: pd.DataFrame) -> pd.Series:
        if self.by == "product":
            return frame["product"]
        return frame["portfolio"].replace("", EMPTY_GROUPS["portfolio"])

    def _identity(self, key, part: pd.DataFrame, catalog: pd.DataFrame | None) -> dict:
        if self.by != "campaign":
            label = PRODUCT_TYPES.get(key, key) if self.by == "product" else key
            return {"group": str(label), "campaigns": int(part["campaign_id"].nunique())}
        first = part.iloc[0]
        listed = catalog[catalog["campaign_id"] == key].iloc[0] if catalog is not None else None
        return {"group": str(first["campaign"]), "campaign_id": str(key), "product": first["product"],
                "portfolio": first["portfolio"], "state": listed["state"] if listed is not None else "",
                "daily_budget": _number(listed["daily_budget"]) if listed is not None else None}

    def _new_to_brand(self, part: pd.DataFrame, figures: dict) -> dict:
        """New-to-brand figures for a group of SB or SD campaigns alone; nothing for SP or a mix."""
        if self.by == "portfolio" or not part["product"].isin(campaign_totals.NEW_TO_BRAND_PRODUCTS).all():
            return {}
        known = part[["ntb_orders", "ntb_sales"]].notna().all(axis=1).all()
        total = NewToBrand(int(part["ntb_orders"].sum()), float(part["ntb_sales"].sum())) if known else None
        return new_to_brand_fields(total, figures["sales"])

    def _campaigns(self, frame: pd.DataFrame) -> pd.DataFrame:
        """The account's listed campaigns plus the ones with activity in the frame."""
        if not self._listed_loaded:
            self._catalog = campaign_catalog(self.rest, self.profile.profile_id)
            self._listed_loaded = True
        return merged_catalog(self._catalog, frame)


class _SearchTerms:
    """Groups of the Sponsored Products search terms: by campaign, portfolio, product, match type, term or ASIN."""

    def __init__(self, rest, profile_id: str, by: str, request: CampaignRequest, asin: str, match_type: str):
        self.rest, self.by, self.request, self.asin, self.match_type = rest, by, request, asin, match_type
        self.profile = profile_by_id(rest, profile_id)
        self.provider = ReportProvider(rest)
        self.currency = ""
        self.selection: CampaignSelection | None = None
        self.empty_note = (f"Ningún search term del período se atribuye al ASIN {asin}." if asin
                           else "La cuenta no tuvo búsquedas con clicks en ese período.")
        self._listed = None
        self._listed_loaded = False
        self._ad_group_asins = None
        self._advertised = None

    def key(self, row: dict):
        if self.by == "campaign":
            return row["campaign_id"]
        if self.by == "campaign_search_term":
            return row["group"], row["campaign_id"], row["ad_group"]
        return row["group"]

    def context(self, start: date, end: date) -> dict:
        fields = {**_source_fields(SOURCE_SEARCH_TERMS, alternative=self.by in CAMPAIGN_DIMENSIONS),
                  "spend_without_sales_note": UNSOLD_TERMS_NOTE}
        if self.by == "asin" or self.asin:
            fields["asin_note"] = ASIN_NOTE
        if self.by == "asin":
            fields["attribution_note"] = ATTRIBUTION_NOTE
        if self.by in ("portfolio", "product", "match_type", "search_term", "asin"):
            fields["campaigns_note"] = CAMPAIGNS_COUNT_NOTE
        if self.by == "campaign_search_term":
            fields["other_campaigns_note"] = OTHER_CAMPAIGNS_NOTE
        return fields

    def group(self, start: date, end: date) -> Grouping | None:
        terms = self.provider.search_terms(self.profile, start, end)
        self.currency = terms.currency_code
        frame = terms.frame
        if frame.empty:
            return None
        if self.request.applied():
            if self.selection is None:
                self.selection = select_campaigns(self._campaigns(frame), self.request)
            frame = frame[frame["_campaign_id"].isin(self.selection.ids)]
        attribution = None
        if self.by == "asin" or self.asin:
            attribution = attribute_asins(frame, self._asins_by_ad_group(), canonical.CAMPAIGN_NAME)
            asin_groups = attribution.asins.where(attribution.asins.notna(),
                                                  attribution.origins.map(UNATTRIBUTED_GROUPS))
            if self.asin:
                kept = asin_groups.eq(self.asin)
                frame, asin_groups = frame[kept], asin_groups[kept]
                attribution = type(attribution)(attribution.asins[kept], attribution.origins[kept])
        kinds = targeting_kinds(frame)
        if self.match_type:
            kept = kinds.eq(self.match_type)
            frame, kinds = frame[kept], kinds[kept]
            if attribution is not None:
                asin_groups = asin_groups[kept]
                attribution = type(attribution)(attribution.asins[kept], attribution.origins[kept])
        if frame.empty:
            return None
        spend_column = canonical.SPEND
        sales_column = canonical.sales_column(terms.attribution_days)
        orders_column = canonical.orders_column(terms.attribution_days)
        measured = frame.assign(
            _unsold=_spend_of_unsold_terms(frame, terms.attribution_days),
            _group=self._keys(frame, kinds, asin_groups if self.by == "asin" else None))
        sums = measured.groupby("_group", sort=False).agg(
            spend=(spend_column, "sum"), sales=(sales_column, "sum"), orders=(orders_column, "sum"),
            clicks=(canonical.CLICKS, "sum"), impressions=(canonical.IMPRESSIONS, "sum"),
            spend_without_sales=("_unsold", "sum"), campaigns=("_campaign_id", "nunique"))
        whole = sums.sum()
        totals = _metrics(whole.spend, whole.sales, whole.orders, whole.clicks, whole.impressions)
        extra_totals = {"spend_without_sales": round(float(whole.spend_without_sales), 2)}
        identities = self._identities(measured, start, end)
        rows = [{**identities(key), **_metrics(row.spend, row.sales, row.orders, row.clicks, row.impressions),
                 "spend_without_sales": round(float(row.spend_without_sales), 2),
                 **({"campaigns": int(row.campaigns)} if self.by not in ("campaign", "campaign_search_term") else {})}
                for key, row in sums.iterrows()]
        if self.by == "campaign_search_term":
            _add_other_campaigns(rows, measured, spend_column)
        if self.by == "asin":
            extra_totals.update(_unattributed(measured, attribution.origins, sales_column))
            self._add_asin_origins(rows, attribution, measured[spend_column], start, end)
        return Grouping(_with_shares(rows, totals), whole_metrics(totals), extra_totals)

    def _keys(self, frame: pd.DataFrame, kinds: pd.Series, asin_groups: pd.Series | None) -> pd.Series:
        if self.by == "asin":
            return asin_groups.loc[frame.index]
        if self.by == "campaign":
            return frame["_campaign_id"]
        if self.by == "campaign_search_term":
            return pd.Series(list(zip(frame[canonical.SEARCH_TERM].astype(str).str.strip(), frame["_campaign_id"],
                                      frame[canonical.AD_GROUP_NAME].fillna("").astype(str))), index=frame.index)
        if self.by == "product":
            return pd.Series(PRODUCT_TYPES["SP"], index=frame.index)
        if self.by == "match_type":
            return kinds.map(MATCH_TYPE_LABELS)
        if self.by == "portfolio":
            return frame[canonical.PORTFOLIO_NAME].fillna("").astype(str).str.strip().replace(
                "", EMPTY_GROUPS["portfolio"])
        return frame[canonical.SEARCH_TERM].fillna("").astype(str).str.strip().replace("", "Sin nombre")

    def _identities(self, measured: pd.DataFrame, start: date, end: date) -> Callable[[object], dict]:
        """How each group key names its row: a campaign by its id and name, a term within its campaign by all three."""
        names = measured.groupby("_campaign_id")[canonical.CAMPAIGN_NAME].first().to_dict()
        portfolios = measured.groupby("_campaign_id")[canonical.PORTFOLIO_NAME].first().to_dict()
        if self.by == "campaign":
            listed = self._campaigns(measured)
            states = dict(zip(listed["campaign_id"], listed["state"]))
            budgets = dict(zip(listed["campaign_id"], listed["daily_budget"]))
            return lambda key: {"group": str(names.get(key, "")).strip() or f"Campaña {key}", "campaign_id": str(key),
                                "product": "SP", "portfolio": str(portfolios.get(key) or ""),
                                "state": states.get(key, ""), "daily_budget": _number(budgets.get(key))}
        if self.by == "campaign_search_term":
            return lambda key: {"group": key[0], "campaign": str(names.get(key[1], "")).strip(),
                                "campaign_id": str(key[1]), "ad_group": key[2]}
        return lambda key: {"group": str(key)}

    def _add_asin_origins(self, rows: list[dict], attribution, spend: pd.Series, start: date, end: date) -> None:
        """Each ASIN's attributed_by and advertised_in; the groups of what no ASIN took carry neither."""
        origins = attribution_by_asin(attribution.asins, attribution.origins, spend)
        if self._advertised is None:
            self._advertised = advertised_in(self.rest, self.profile, start, end)
        for row in rows:
            if row["group"] in UNATTRIBUTED_GROUPS.values():
                continue
            row["attributed_by"] = origins.get(row["group"], "")
            if self._advertised is not None:
                row["advertised_in"] = self._advertised.get(row["group"], {"campaigns": 0, "running_campaigns": 0})

    def _asins_by_ad_group(self) -> dict:
        if self._ad_group_asins is None:
            self._ad_group_asins = self.provider.advertised_asins(self.profile.profile_id)
        return self._ad_group_asins

    def _campaigns(self, frame: pd.DataFrame) -> pd.DataFrame:
        """The account's listed campaigns plus the ones the search terms name."""
        if not self._listed_loaded:
            self._listed = campaign_catalog(self.rest, self.profile.profile_id)
            self._listed_loaded = True
        active = pd.DataFrame({
            "product": "SP", "campaign_id": frame["_campaign_id"],
            "campaign": frame[canonical.CAMPAIGN_NAME].fillna("").astype(str).str.strip(),
            "state": frame["_campaign_status"].fillna("").astype(str).str.upper(),
            "portfolio": frame[canonical.PORTFOLIO_NAME].fillna("").astype(str).str.strip(),
            "daily_budget": float("nan")}).drop_duplicates("campaign_id")
        return merged_catalog(self._listed, active)


def _empty_note(reader, request: CampaignRequest) -> str:
    """Why nothing came back: no campaign answers to what was asked, or those that do had no activity."""
    if reader.selection is not None and not reader.selection.ids:
        return no_match_note(request)
    if request.applied():
        return "Las campañas pedidas no tuvieron actividad en ese período."
    return reader.empty_note


def targeting_kinds(frame: pd.DataFrame) -> pd.Series:
    """Each search term row's targeting: exact, phrase, broad, auto, or a product target by asin or by category."""
    origins = frame["_origin_match_type"].fillna("").astype(str).str.upper()
    expressions = frame[canonical.TARGETING].fillna("").astype(str)
    kinds = origins.map(_KEYWORD_ORIGINS).fillna("")
    product_targets = origins.eq("PRODUCT_TARGETING")
    kinds[product_targets] = expressions[product_targets].map(_expression_kind)
    return kinds


def _expression_kind(expression: str) -> str:
    """asin or category, from the first predicate of Amazon's targeting expression (asin="…", category="…")."""
    predicate = expression.split("=", 1)[0].strip().lower()
    return _EXPRESSION_KINDS.get(predicate, "product_targeting")


def _spend_of_unsold_terms(frame, attribution_days: int):
    """Each row's spend when its search term sold nothing in that campaign over the window, else 0."""
    orders = frame.groupby([canonical.CAMPAIGN_NAME, canonical.SEARCH_TERM], dropna=False)[
        canonical.orders_column(attribution_days)].transform("sum")
    return frame[canonical.SPEND].where(orders.eq(0), 0.0)


def _add_other_campaigns(rows: list[dict], measured: pd.DataFrame, spend_column: str) -> None:
    """Each term-in-campaign row gets how many other campaigns ran the same term and what it spent in them."""
    terms = measured[canonical.SEARCH_TERM].astype(str).str.strip()
    per_campaign = measured.assign(_term=terms).groupby(["_term", "_campaign_id"])[spend_column].sum()
    for row in rows:
        spent = per_campaign.loc[row["group"]]
        others = spent.drop(labels=[row["campaign_id"]], errors="ignore")
        row["other_campaigns"] = {"count": int(len(others)), "spend": round(float(others.sum()), 2)}


def _unattributed(measured: pd.DataFrame, origins: pd.Series, sales_column: str) -> dict:
    """What no ASIN took: the spend and sales of the terms left in «Varios ASINs» or «Sin ASIN»."""
    left_out = origins.loc[measured.index].isin(tuple(UNATTRIBUTED_GROUPS))
    return {"unattributed_spend": round(float(measured.loc[left_out, canonical.SPEND].sum()), 2),
            "unattributed_sales": round(float(measured.loc[left_out, sales_column].sum()), 2)}


def _add_series(rows: list[dict], reader, by_period: str, start: date, end: date) -> None:
    """Each row's spend and ACoS in every week or month of the window, and whether they rose between the last two
    complete ones."""
    if not rows:
        return
    periods = periods_within(start, end, by_period)
    groupings = []
    for period in periods:
        first, last = max(period.start, start), min(period.end, end)
        grouping = reader.group(first, last)
        by_key = {reader.key(row): row for row in grouping.rows} if grouping else {}
        groupings.append((period, first <= period.start and period.end <= last, by_key))
    for row in rows:
        series = []
        for period, complete, by_key in groupings:
            found = by_key.get(reader.key(row))
            series.append({"period_start": period.start.isoformat(), "complete": complete,
                           "spend": found["spend"] if found else 0.0, "acos": found["acos"] if found else None})
        row["series"] = series
        row["trend"] = _series_trend(series)


def _series_trend(series: list[dict]) -> dict:
    """spend and acos between the last two complete periods, by the rule every *_vs_previo follows."""
    complete = [entry for entry in series if entry["complete"]]
    trend = {}
    for figure in ("spend", "acos"):
        if len(complete) < 2 or complete[-1][figure] is None or complete[-2][figure] is None:
            trend[figure] = NO_PREVIOUS
        else:
            trend[figure] = trend_between(complete[-1][figure], complete[-2][figure])
    return trend


def _gone_row(previous: dict) -> dict:
    """A group that had activity only in the period before: its names, and zero figures now."""
    row = {field: previous[field] for field in _IDENTITY_FIELDS if field in previous}
    row.update(_metrics(0, 0, 0, 0, 0))
    row.update({f"{metric}_share": None for metric in SHARED_METRICS})
    if "spend_without_sales" in previous:
        row["spend_without_sales"] = 0.0
    if "campaigns" in previous:
        row["campaigns"] = 0
    return row


def _empty_totals() -> dict:
    return whole_metrics(_metrics(0, 0, 0, 0, 0))


def _leaders(rows: list[dict]) -> dict:
    """Over every group, not only the page: which one leads each metric, and the ACoS ends among those that sold."""
    if not rows:
        return {}
    leaders = {f"most_{metric}": _leader(max(rows, key=lambda row: row[metric] or 0), metric)
               for metric in ("spend", "sales", "orders", "clicks")}
    sold = [row for row in rows if row.get("acos") is not None]
    if sold:
        leaders["lowest_acos"] = _leader(min(sold, key=lambda row: row["acos"]), "acos")
        leaders["highest_acos"] = _leader(max(sold, key=lambda row: row["acos"]), "acos")
    unsold = [row for row in rows if not row.get("sales") and row.get("spend")]
    leaders["groups_spending_without_sales"] = len(unsold)
    return leaders


def _leader(row: dict, metric: str) -> dict:
    return {"group": row["group"], metric: row[metric]}


def _number(value):
    if value is None or value != value:
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)
