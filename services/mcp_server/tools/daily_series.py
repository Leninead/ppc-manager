"""daily_metrics: an account's series by day, week or month, of all its campaigns or of the ones a question names.

The figures come from the campaign reports of SP, SB and SD, or, with source=search_terms, from SP's search terms.
A campaign is named exactly first and read by its id, so five campaigns sharing a prefix never read as one.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from core.amazon_ads import campaign_totals
from core.amazon_ads.campaign_catalog import campaign_catalog
from core.amazon_ads.product_provider import NewToBrand
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError, _attribution_days
from services.mcp_server.tools.account_resolver import campaign_profile, choose_account, profile_by_id
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
    SOURCE_CAMPAIGNS,
    SOURCE_SEARCH_TERMS,
    Product,
    Source,
    _add_old_format_note,
    _check_product,
    _check_source,
    _metrics,
    _plain,
    _source_fields,
    attribution_days_by_product,
    new_to_brand_fields,
)
from services.mcp_server.tools.period_series import (
    ACTIVITY_NOTE,
    DEFAULT_PERIODS,
    MAX_PERIODS,
    MAX_WINDOW_DAYS,
    PERIOD_NOTE,
    Granularity,
    activity_payload,
    check_granularity,
    period_fields,
    periods_back,
    periods_within,
)
from services.mcp_server.tools.windows import clipped_window, earliest_day, requested_window, window_payload

# Two weeks: enough to see a shape, and the weekday pattern still reads.
DEFAULT_SERIES_DAYS = 14
# The day of the week comes with each date: a model working it out from the date got every name in a week wrong.
WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
BEFORE_WINDOW_MAX_DAYS = 60
BEFORE_WINDOW_METRICS = ("spend", "sales", "orders", "clicks", "impressions")
BEFORE_WINDOW_NOTE = ("before_window da, de los días sincronizados anteriores a la ventana (hasta 60), el día más alto y "
                      "el más bajo de cada métrica: un «nunca», un «desde el», un «por primera vez» o un «antes llegaba "
                      "como mucho a» se dicen contra esos días, no sólo contra los de rows.")
SUMMED_CAMPAIGNS_NOTE = ("Cada fila suma las {count} campañas de matched_campaigns, no una sola: lo de cada una está en "
                         "by_campaign.")
MISSING_MIGRATION = ("La base todavía no tiene la lectura por campaña (migración 019): la serie de una campaña no está "
                     "disponible hasta que se aplique.")
_METRIC_COLUMNS = ("spend", "sales", "orders", "clicks", "impressions", "sales_clicks", "orders_clicks")
_NEW_TO_BRAND_COLUMNS = ("ntb_orders", "ntb_sales")


def daily_metrics(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_SERIES_DAYS,
                  date_from: str = "", date_to: str = "", granularity: Granularity = "day", periods: int = 0,
                  campaign: str = "", campaigns: tuple[str, ...] = (), state: CampaignState = "",
                  portfolio: str = "", product: Product = "", source: Source = "") -> dict:
    """La serie de una cuenta por día, semana o mes, de todas sus campañas (SP, SB y SD, o sólo `product`) o de las
    que nombran `campaign`, `campaigns`, `state` y `portfolio`, en sus últimos `days` días, sus últimos `periods`
    semanas o meses, o de `date_from` a `date_to`.

    Salen de los reportes de campaña; con `source`=search_terms, sólo las de SP, sumadas del reporte de search
    terms. Una fila por cada día o período, también los que no gastaron: una serie con huecos se dibujaría como si
    esos días no existieran.
    """
    _check_product(product)
    _check_source(source, product)
    check_granularity(granularity)
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    request = CampaignRequest.of(campaign, campaigns, state, portfolio)
    searched = source == SOURCE_SEARCH_TERMS
    if searched:
        profile = profile_by_id(rest, choice.profile_id)
    else:
        profile = campaign_profile(rest, choice.profile_id, search_terms_hint=product in ("", "SP"))
    start, end, window_note, period_list = _window(profile, granularity, days, periods, date_from, date_to)
    before = _before_range(profile, start) if granularity == "day" else None
    read_from = before[0] if before else start
    reader = _DayReader(rest, profile, product, searched)
    context = {"window": window_payload(start, end), "currency": profile.currency_code,
               "data_since": earliest_day(profile).isoformat(), "granularity": granularity,
               **_source_fields(source or SOURCE_CAMPAIGNS, alternative=product in ("", "SP"))}
    if window_note:
        context["window_note"] = window_note
    if request.applied():
        selection = reader.select(request, read_from, end)
        context.update(selection.payload())
        if not selection.ids:
            return {"rows": [], **context, "note": no_match_note(request)}
    day_frame = reader.days(read_from, end)
    window_days = day_frame[day_frame["day"] >= start]
    ntb = product in campaign_totals.NEW_TO_BRAND_PRODUCTS
    if granularity == "day":
        rows = [{"date": row["day"].isoformat(), "weekday": WEEKDAYS[row["day"].weekday()],
                 **_row_figures(row_frame, searched, ntb)}
                for row, row_frame in ((row, window_days.loc[[index]]) for index, row in window_days.iterrows())]
    else:
        rows = [{**period_fields(period, start, end),
                 **_row_figures(window_days[(window_days["day"] >= period.start) & (window_days["day"] <= period.end)],
                                searched, ntb)} for period in period_list]
        context["period_note"] = PERIOD_NOTE
    products = ["SP"] if searched else reader.products
    context.update(attribution_days=attribution_days_by_product(products, _attribution_days(profile.account_type)),
                   products=products)
    if ntb:
        context["new_to_brand_note"] = NEW_TO_BRAND_NOTE
    if before:
        extremes = _extremes(day_frame[day_frame["day"] < start], before)
        if extremes:
            context.update(before_window=extremes, before_window_note=BEFORE_WINDOW_NOTE)
    context["activity"] = activity_payload(read_from, {
        "clicks": list(zip(day_frame["day"], day_frame["clicks"])),
        "spend": list(zip(day_frame["day"], day_frame["spend"]))})
    context["activity_note"] = ACTIVITY_NOTE
    if not searched:
        _add_old_format_note(context, rest, profile.profile_id, start, end, product)
    if request.applied():
        context.update(reader.by_campaign(start, end))
    return {"rows": rows, **context}


def _window(profile: ProfileOption, granularity: str, days: int, periods: int, date_from: str,
            date_to: str) -> tuple[date, date, str, list]:
    """(start, end, note, periods): the days to read and, by week or month, the calendar periods they fill."""
    if granularity == "day":
        start, end, note = requested_window(profile, days, date_from, date_to)
        return start, end, note, []
    if date_from or date_to:
        start, end, note = requested_window(profile, days, date_from, date_to, max_days=MAX_WINDOW_DAYS[granularity])
        return start, end, note, periods_within(start, end, granularity)
    asked = int(periods) or DEFAULT_PERIODS[granularity]
    count = max(1, min(asked, MAX_PERIODS[granularity]))
    period_list = periods_back(profile.data_through, granularity, count)
    clipped = clipped_window(profile, period_list[0].start, profile.data_through)
    start, end = clipped[0], clipped[1]
    notes = []
    if asked > MAX_PERIODS[granularity]:
        notes.append(f"Se pidieron {asked} períodos y el máximo es {MAX_PERIODS[granularity]}.")
    if start > period_list[0].start:
        notes.append(f"La cuenta tiene datos desde el {start.isoformat()}: los primeros períodos no están completos.")
    return start, end, " ".join(notes), period_list


def _before_range(profile: ProfileOption, start: date) -> tuple[date, date] | None:
    """The synced days before the window, up to BEFORE_WINDOW_MAX_DAYS."""
    if profile.data_from is None:
        return None
    first = max(profile.data_from, start - timedelta(days=BEFORE_WINDOW_MAX_DAYS))
    last = start - timedelta(days=1)
    return (first, last) if first <= last else None


def _extremes(before_days: pd.DataFrame, before: tuple[date, date]) -> dict | None:
    """Each metric's highest and lowest day before the window."""
    if before_days.empty:
        return None
    extremes = {}
    for metric in BEFORE_WINDOW_METRICS:
        high = before_days.loc[before_days[metric].idxmax()]
        low = before_days.loc[before_days[metric].idxmin()]
        extremes[metric] = {"max": _plain(round(high[metric], 2)), "max_date": high["day"].isoformat(),
                            "min": _plain(round(low[metric], 2)), "min_date": low["day"].isoformat()}
    return {"from": before[0].isoformat(), "to": before[1].isoformat(), "days": len(before_days),
            "extremes": extremes}


def _row_figures(days: pd.DataFrame, searched: bool, ntb: bool) -> dict:
    """The metrics of a day or a period; SP's click-only figures from the campaign reports, SB's or SD's
    new-to-brand when the series is one of them alone."""
    total = days[list(_METRIC_COLUMNS)].sum()
    figures = _metrics(total["spend"], total["sales"], total["orders"], total["clicks"], total["impressions"])
    if not searched:
        figures.update(sales_clicks=round(float(total["sales_clicks"]), 2), orders_clicks=int(total["orders_clicks"]))
    if ntb:
        known = days[list(_NEW_TO_BRAND_COLUMNS)].notna().all(axis=1).all()
        figures.update(new_to_brand_fields(
            NewToBrand(int(days["ntb_orders"].sum()), float(days["ntb_sales"].sum())) if known else None,
            figures["sales"]))
    return figures


class _DayReader:
    """The days of one account, of every campaign or of the selected ones, from one source."""

    def __init__(self, rest, profile: ProfileOption, product: str, searched: bool):
        self.rest, self.profile, self.product, self.searched = rest, profile, product, searched
        self.selection: CampaignSelection | None = None
        self.products: list[str] = []
        self._campaign_rows: pd.DataFrame | None = None

    def select(self, request: CampaignRequest, start: date, end: date) -> CampaignSelection:
        catalog = campaign_catalog(self.rest, self.profile.profile_id)
        try:
            active = campaign_totals.window_totals(self.rest, self.profile, start, end)
        except ReportReadError:
            active = pd.DataFrame(columns=["product", "campaign_id", "campaign", "portfolio"])
        if self.product:
            active = active[active["product"] == self.product]
            if catalog is not None:
                catalog = catalog[catalog["product"] == self.product]
        if self.searched:
            active = active[active["product"] == "SP"]
            if catalog is not None:
                catalog = catalog[catalog["product"] == "SP"]
        self.selection = select_campaigns(merged_catalog(catalog, active), request)
        return self.selection

    def days(self, start: date, end: date) -> pd.DataFrame:
        """One row per day of [start, end]: the metrics, and new-to-brand where the source has them."""
        calendar = pd.DataFrame({"day": [start + timedelta(days=offset) for offset in range((end - start).days + 1)]})
        if self.selection is not None:
            by_day = self._selected_days(start, end)
        elif self.searched:
            series = ReportProvider(self.rest).daily_totals(self.profile, start, end)
            by_day = pd.DataFrame([{"day": day.day, "spend": day.spend, "sales": day.sales, "orders": day.orders,
                                    "clicks": day.clicks, "impressions": day.impressions} for day in series.days])
        else:
            series = campaign_totals.daily_totals(self.rest, self.profile, start, end, product=self.product)
            self.products = list(series.products)
            ntb = series.new_to_brand or (None,) * len(series.days)
            by_day = pd.DataFrame([{"day": day.day, **vars(day.totals), **_new_to_brand_values(figures)}
                                   for day, figures in zip(series.days, ntb)])
        merged = calendar.merge(by_day, on="day", how="left") if not by_day.empty else calendar
        for column in _METRIC_COLUMNS:
            merged[column] = merged[column].fillna(0) if column in merged else 0
        for column in _NEW_TO_BRAND_COLUMNS:
            if column not in merged:
                merged[column] = float("nan")
        return merged

    def _selected_days(self, start: date, end: date) -> pd.DataFrame:
        ids = tuple(sorted(self.selection.ids))
        if self.searched:
            rows = ReportProvider(self.rest).daily_totals_by_campaign(self.profile, start, end, ids)
        else:
            rows = campaign_totals.daily_totals_by_campaign(self.rest, self.profile, start, end, ids)
        if rows is None:
            raise ValueError(MISSING_MIGRATION)
        if self.searched:
            rows = rows.assign(product="SP")
        self._campaign_rows = rows if self._campaign_rows is None else pd.concat([self._campaign_rows, rows])
        if not self.searched:
            self.products = [code for code in campaign_totals.PRODUCTS if code in set(rows["product"])]
        if rows.empty:
            return pd.DataFrame(columns=["day"])
        summed = rows.groupby("day")[[column for column in _METRIC_COLUMNS if column in rows]].sum()
        if not self.searched:
            known = rows.groupby("day")[list(_NEW_TO_BRAND_COLUMNS)].apply(lambda part: part.notna().all().all())
            ntb = rows.groupby("day")[list(_NEW_TO_BRAND_COLUMNS)].sum().where(known, float("nan"), axis=0)
            summed = summed.join(ntb)
        return summed.reset_index()

    def by_campaign(self, start: date, end: date) -> dict:
        """What each selected campaign added to the window, when the series sums more than one."""
        if self.selection is None or len(self.selection.ids) < 2 or self._campaign_rows is None:
            return {}
        window = self._campaign_rows[(self._campaign_rows["day"] >= start) & (self._campaign_rows["day"] <= end)]
        names = {row["campaign_id"]: row for row in self.selection.matched}
        contributions = []
        for campaign_id, part in window.groupby("campaign_id"):
            total = part[["spend", "sales", "orders", "clicks", "impressions"]].sum()
            listed = names.get(campaign_id, {})
            contributions.append({"campaign": listed.get("campaign", ""), "campaign_id": campaign_id,
                                  "product": listed.get("product", ""),
                                  **_metrics(total["spend"], total["sales"], total["orders"], total["clicks"],
                                             total["impressions"])})
        contributions.sort(key=lambda row: row["spend"], reverse=True)
        silent = len(self.selection.ids) - len(contributions)
        fields = {"by_campaign": contributions,
                  "campaigns_note": SUMMED_CAMPAIGNS_NOTE.format(count=len(self.selection.ids))}
        if silent:
            fields["campaigns_note"] += f" {silent} de ellas no tuvieron actividad en la ventana."
        return fields


def _new_to_brand_values(figures: NewToBrand | None) -> dict:
    if figures is None:
        return dict.fromkeys(_NEW_TO_BRAND_COLUMNS, float("nan"))
    return {"ntb_orders": figures.orders, "ntb_sales": figures.sales}
