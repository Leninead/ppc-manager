"""Targeting reports of Sponsored Products, Brands and Display, and the Brands and Display campaign reports,
mapped to `ads_target_daily` and `ads_sb_sd_campaign_daily`, grouped by report day.

Six reports feed two tables and differ only in which report field holds which column, so one parser reads them
all and each report is a field mapping: five of Reporting v3, and SB's v2 campaign report for the campaigns v3
leaves out. A row carries every column of its table, also one its report lacks (0 for
a metric, None for a fact): the day is written with jsonb_populate_recordset, where a missing key lands as NULL.

SP campaigns stay in `campaign_rows`: they have their own table, with 7 and 14 day attribution.
"""
from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from core.amazon_ads.report_fetcher import ReportSpec
from core.amazon_ads.search_term_rows import ReportRowsError, iter_report

log = logging.getLogger(__name__)

MONEY_DECIMALS = 4


@dataclass(frozen=True)
class _Table:
    entity: str                 # what a row is about, as messages name it
    key: str                    # the column a day's repeated rows are merged on
    metrics: tuple[str, ...]    # summed and never below zero; 0 where a report does not carry one
    optionals: tuple[str, ...]  # facts where unknown is not zero; None where a report does not carry one


_TARGET_TABLE = _Table(
    entity="target",
    key="target_id",
    # SP attributes sales over 7 and 14 days; SB and SD report all sales and the click-attributed ones.
    metrics=("impressions", "clicks", "cost", "purchases_7d", "sales_7d", "purchases_14d", "sales_14d",
             "purchases", "sales", "purchases_clicks", "sales_clicks"),
    optionals=("top_of_search_is",),
)
_CAMPAIGN_TABLE = _Table(
    entity="campaign",
    key="campaign_id",
    metrics=("impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
             "new_to_brand_purchases", "new_to_brand_sales", "viewable_impressions"),
    optionals=("budget_amount", "top_of_search_is"),
)
_MONEY_COLUMNS = frozenset({"cost", "sales_7d", "sales_14d", "sales", "sales_clicks", "new_to_brand_sales"})
_OPTIONAL_NAMES = {"budget_amount": "budget", "top_of_search_is": "share"}

_KEYWORD_MATCH_TYPES = frozenset({"BROAD", "PHRASE", "EXACT"})
# keywordType means the same in the SP and SB reports, and keywordId is the id of every kind: keywords, product
# targets, auto targets and SB themes alike.
_KIND_BY_KEYWORD_TYPE = {
    "TARGETING_EXPRESSION": "product",
    "TARGETING_EXPRESSION_PREDEFINED": "auto",
    "THEME": "theme",
}
_AUDIENCE_PREDICATES = ("views", "purchases", "audience")
_LEADING_PREDICATE = re.compile(r"[\s(\[\"']*([A-Za-z][\w-]*)")


def _target_by_keyword_type(texts: Mapping[str, str]) -> dict:
    keyword_type = texts["kind"].upper()
    if keyword_type in _KEYWORD_MATCH_TYPES:
        kind, match_type = "keyword", keyword_type
    else:
        # A type Amazon adds later is still a target with spend: it is kept as a product target, not refused.
        kind, match_type = _KIND_BY_KEYWORD_TYPE.get(keyword_type, "product"), ""
    return {"target_kind": kind, "target_text": texts["text"], "match_type": match_type}


def _target_by_expression(texts: Mapping[str, str]) -> dict:
    # SD has no keyword type, so the expression's leading predicate tells: views=(...), purchases=(...) and
    # audience=... reach people; similarProduct is Amazon's pick; asin=, category=, brand=, price... name products.
    leading = _LEADING_PREDICATE.match(texts["kind"])
    predicate = re.sub(r"[-_]", "", leading.group(1)).lower() if leading else ""
    if predicate.startswith(_AUDIENCE_PREDICATES):
        kind = "audience"
    elif predicate == "similarproduct":
        kind = "auto"
    else:
        kind = "product"
    return {"target_kind": kind, "target_text": texts["text"], "match_type": ""}


def _campaign_cost_type(texts: Mapping[str, str]) -> dict:
    return {"cost_type": texts["cost_type"].upper()}


def _unknown_cost_type(texts: Mapping[str, str]) -> dict:
    return {"cost_type": ""}


# Compared by identity: there is one parser per report, and its mappings are dicts.
@dataclass(frozen=True, eq=False)
class _Parser:
    """One report read into one table; the worker calls `load_compact_report`, `day_row_positions` and
    `day_rows`, as it does with `campaign_rows`."""

    spec: ReportSpec
    ad_product: str                        # the tables' short form of the spec's ad product: SP, SB or SD
    table: _Table
    ids: Mapping[str, str]                 # id column -> report field, the table's key among them
    texts: Mapping[str, tuple[str, ...]]   # what `describe` reads -> report fields; the first non-empty one wins
    describe: Callable[[Mapping[str, str]], dict]
    metrics: Mapping[str, str]             # the table's metrics this report carries -> report field
    optionals: Mapping[str, str] = field(default_factory=dict)
    currency_field: str | None = None      # None: the report carries no currency, so the profile's is used
    # False for a report of one day with no date field (SB's v2 report): its rows are its window's only day.
    dated: bool = True
    _index: Mapping[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", {name: index for index, name in enumerate(self.spec.columns)})
        # Asking for exactly the fields this parser reads is what keeps request and mapping from drifting.
        read = {*(("date",) if self.dated else ()), *self.ids.values(),
                *(name for names in self.texts.values() for name in names),
                *self.metrics.values(), *self.optionals.values(), *filter(None, (self.currency_field,))}
        drift = read.symmetric_difference(self.spec.columns)
        if drift:
            raise ValueError(f"{self.spec.report_type_id} asks for fields it does not read, or reads fields it does"
                             f" not ask for: {sorted(drift)}")

    def load_compact_report(self, gzip_path) -> list[tuple]:
        """The report's rows as compact rows, which take far less memory than its parsed JSON objects."""
        return self.compact_rows(iter_report(gzip_path))

    def compact_rows(self, api_rows: Iterable) -> list[tuple]:
        compacted = []
        for position, api_row in enumerate(api_rows):
            if not isinstance(api_row, dict):
                raise ReportRowsError(f"{self._label} row {position} is not an object")
            compacted.append(tuple(api_row.get(name) for name in self.spec.columns))
        return compacted

    def rows_by_day(self, api_rows: Iterable[dict], *, profile_id: str, currency_code: str, window_start: date,
                    window_end: date) -> dict[date, list[dict]]:
        """Every day of the window as a key (empty list when the report had nothing that day);
        rows sharing the table's key are merged by summing their metrics."""
        report_rows = self.compact_rows(api_rows)
        positions_by_day = self.day_row_positions(report_rows, window_start=window_start, window_end=window_end)
        return {
            day: self.day_rows(report_rows, positions, profile_id=profile_id, currency_code=currency_code, day=day)
            for day, positions in positions_by_day.items()
        }

    def day_row_positions(self, report_rows: Sequence[tuple], *, window_start: date,
                          window_end: date) -> dict[date, list[int]]:
        """Every day of the window as a key, with the positions of that day's rows.

        Checks every row, so a report with one unusable row is refused before any day is written.
        """
        if window_end < window_start:
            raise ReportRowsError(f"window ends before it starts: {window_start}..{window_end}")
        if not self.dated and window_end != window_start:
            raise ReportRowsError(f"{self._label} covers one day, not {window_start}..{window_end}")
        positions_by_day: dict[date, list[int]] = {
            window_start + timedelta(days=offset): []
            for offset in range((window_end - window_start).days + 1)
        }
        key_index = self._index[self.ids[self.table.key]]
        checked = (*self.metrics.values(), *self.optionals.values())
        negatives: list[tuple] = []
        for position, report_row in enumerate(report_rows):
            report_day = self._report_day(report_row, position) if self.dated else window_start
            if report_day not in positions_by_day:
                raise ReportRowsError(
                    f"{self._label} row {position} is dated {report_day}, outside {window_start}..{window_end}"
                )
            key = _id_text(report_row[key_index])
            if not key:
                raise ReportRowsError(f"{self._label} row {position} has no {self.table.entity} id")
            for name in checked:
                number = self._number(report_row, name, position)
                if number < 0:
                    negatives.append((report_day, key, name, number))
            positions_by_day[report_day].append(position)
        if negatives:
            day, key, name, number = negatives[0]
            unknown = " and ".join(_OPTIONAL_NAMES[column] for column in self.optionals)
            log.warning("amazon_ads: %s %s..%s has %d values below zero (Amazon adjustments), stored as 0%s;"
                        " first: %s %s on %s %s=%s", self._label, window_start, window_end, len(negatives),
                        f" ({unknown} as unknown)" if unknown else "", self.table.entity, key, day, name, number)
        return positions_by_day

    def day_rows(self, report_rows: Sequence[tuple], positions: Iterable[int], *, profile_id: str,
                 currency_code: str, day: date) -> list[dict]:
        """One day's table rows from rows checked by `day_row_positions`; rows repeating a key are summed."""
        merged: dict[str, dict] = {}
        for position in positions:
            row = self._table_row(report_rows[position], position, profile_id, currency_code, day)
            existing = merged.get(row[self.table.key])
            if existing is None:
                merged[row[self.table.key]] = row
            else:
                self._add_metrics(existing, row)
        return list(merged.values())

    @property
    def _label(self) -> str:
        return f"{self.spec.report_type_id} report"

    def _table_row(self, report_row: tuple, position: int, profile_id: str, currency_code: str,
                   report_day: date) -> dict:
        row: dict = {"profile_id": profile_id, "report_date": report_day.isoformat(), "ad_product": self.ad_product}
        for column, name in self.ids.items():
            row[column] = _id_text(report_row[self._index[name]])
        row.update(self.describe({purpose: self._text(report_row, names) for purpose, names in self.texts.items()}))
        for column in self.table.metrics:
            name = self.metrics.get(column)
            number = self._metric(report_row, name, position) if name else 0.0
            row[column] = round(number, MONEY_DECIMALS) if column in _MONEY_COLUMNS else int(round(number))
        for column in self.table.optionals:
            name = self.optionals.get(column)
            value = self._optional_metric(report_row, name, position) if name else None
            row[column] = None if value is None else round(value, MONEY_DECIMALS)
        reported_currency = report_row[self._index[self.currency_field]] if self.currency_field else None
        row["currency_code"] = str(reported_currency or currency_code or "").strip().upper()
        return row

    def _add_metrics(self, existing: dict, duplicate: dict) -> None:
        # The share is weighted by each row's own impressions, so it is merged before they are summed.
        existing["top_of_search_is"] = _merged_share(existing, duplicate)
        if "budget_amount" in existing:
            existing["budget_amount"] = max((value for value in (existing["budget_amount"], duplicate["budget_amount"])
                                             if value is not None), default=None)
        if "cost_type" in existing and not existing["cost_type"]:
            existing["cost_type"] = duplicate["cost_type"]
        for column in self.table.metrics:
            if column in _MONEY_COLUMNS:
                existing[column] = round(existing[column] + duplicate[column], MONEY_DECIMALS)
            else:
                existing[column] += duplicate[column]

    def _report_day(self, report_row: tuple, position: int) -> date:
        raw_date = str(report_row[self._index["date"]] or "").strip()
        try:
            return date.fromisoformat(raw_date[:10])
        except ValueError:
            raise ReportRowsError(f"{self._label} row {position} has no valid date") from None

    def _text(self, report_row: tuple, names: tuple[str, ...]) -> str:
        for name in names:
            value = report_row[self._index[name]]
            text = "" if value is None else str(value).strip()
            if text:
                return text
        return ""

    def _number(self, report_row: tuple, name: str, position: int) -> float:
        """The field as a finite number, sign kept; a report with one that is not a number cannot be trusted."""
        value = report_row[self._index[name]]
        if value is None or value == "":
            return 0.0
        if isinstance(value, bool):
            raise ReportRowsError(f"{self._label} row {position} has a non-numeric {name}")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ReportRowsError(f"{self._label} row {position} has a non-numeric {name}") from None
        if not math.isfinite(number):
            raise ReportRowsError(f"{self._label} row {position} has an impossible {name}: {number}")
        return number

    def _metric(self, report_row: tuple, name: str, position: int) -> float:
        # Amazon removes invalid traffic from days it already reported, and on a day with nothing else the net can
        # fall below zero (seen: impressions -2 on a day with no activity). Every reader sums these as counts that
        # are never negative, so the day keeps none; `day_row_positions` logs what was adjusted.
        return max(self._number(report_row, name, position), 0.0)

    def _optional_metric(self, report_row: tuple, name: str, position: int) -> float | None:
        """None when Amazon left the field out or sent one below zero: unknown, never a made-up 0."""
        value = report_row[self._index[name]]
        if value is None or value == "":
            return None
        number = self._number(report_row, name, position)
        return number if number >= 0 else None


def _merged_share(existing: dict, duplicate: dict) -> float | None:
    known = [row for row in (existing, duplicate) if row["top_of_search_is"] is not None]
    if not known:
        return None
    weight = sum(row["impressions"] for row in known)
    if weight == 0:
        return round(sum(row["top_of_search_is"] for row in known) / len(known), MONEY_DECIMALS)
    return round(sum(row["top_of_search_is"] * row["impressions"] for row in known) / weight, MONEY_DECIMALS)


def _id_text(value) -> str:
    # Amazon sends ids as JSON numbers; a float rendering ("1.5e+14") would break every join.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# The five reports, each asking for the columns the live API accepted for it (checked 2026-09-18), in that order.
# Amazon keeps SP targeting data for 95 days, SB for 60 and SD for 65.

SP_TARGETING_SPEC = ReportSpec(
    report_type_id="spTargeting",
    group_by=("targeting",),
    columns=("date", "campaignId", "adGroupId", "keywordId", "keyword", "keywordType", "matchType", "targeting",
             "impressions", "clicks", "cost", "purchases7d", "sales7d", "purchases14d", "sales14d",
             "topOfSearchImpressionShare"),
    ad_product="SPONSORED_PRODUCTS",
    retention_days=95,
)
SB_CAMPAIGN_SPEC = ReportSpec(
    report_type_id="sbCampaigns",
    group_by=("campaign",),
    columns=("date", "campaignId", "impressions", "clicks", "cost", "purchases", "sales", "purchasesClicks",
             "salesClicks", "costType", "viewableImpressions", "campaignBudgetAmount", "campaignBudgetCurrencyCode",
             "topOfSearchImpressionShare", "newToBrandPurchases", "newToBrandSales"),
    ad_product="SPONSORED_BRANDS",
    retention_days=60,
)
SB_TARGETING_SPEC = ReportSpec(
    report_type_id="sbTargeting",
    group_by=("targeting",),
    columns=("date", "campaignId", "adGroupId", "keywordId", "keywordText", "keywordType", "matchType",
             "targetingExpression", "targetingText", "impressions", "clicks", "cost", "purchases", "sales",
             "purchasesClicks", "salesClicks"),
    ad_product="SPONSORED_BRANDS",
    retention_days=60,
)
# The two newToBrand columns are Amazon's documented sdCampaigns metrics, not yet checked against the live API.
SD_CAMPAIGN_SPEC = ReportSpec(
    report_type_id="sdCampaigns",
    group_by=("campaign",),
    columns=("date", "campaignId", "impressions", "impressionsViews", "clicks", "cost", "purchases", "sales",
             "purchasesClicks", "salesClicks", "costType", "campaignBudgetAmount", "campaignBudgetCurrencyCode",
             "newToBrandPurchases", "newToBrandSales"),
    ad_product="SPONSORED_DISPLAY",
    retention_days=65,
)
SD_TARGETING_SPEC = ReportSpec(
    report_type_id="sdTargeting",
    group_by=("targeting",),
    columns=("date", "campaignId", "adGroupId", "targetingId", "targetingExpression", "targetingText",
             "impressions", "clicks", "cost", "purchases", "sales", "purchasesClicks", "salesClicks"),
    ad_product="SPONSORED_DISPLAY",
    retention_days=65,
)
# SB's v2 campaign report, for the campaigns v3 leaves out while in preview (isMultiAdGroupsEnabled = false).
# Measured on 2026-09-16: for the 587 campaigns both reports have, v2's figures are v3's. It is one day per
# report, with no date field; its sales are 14-day and click-only (it refuses view-attributed metrics). The
# metrics are ids and numbers only: asking for a name or a state makes v2 answer every campaign ever made.
SB_LEGACY_CAMPAIGN_SPEC = ReportSpec(
    report_type_id="hsaCampaigns",
    group_by=(),
    columns=("campaignId", "impressions", "clicks", "cost", "attributedConversions14d", "attributedSales14d",
             "attributedOrdersNewToBrand14d", "attributedSalesNewToBrand14d"),
    ad_product="SPONSORED_BRANDS",
    retention_days=60,
)

# Brands and Display name their metrics alike.
_BRANDS_DISPLAY_METRICS = {
    "impressions": "impressions",
    "clicks": "clicks",
    "cost": "cost",
    "purchases": "purchases",
    "sales": "sales",
    "purchases_clicks": "purchasesClicks",
    "sales_clicks": "salesClicks",
}

SP_TARGETING_ROWS = _Parser(
    spec=SP_TARGETING_SPEC,
    ad_product="SP",
    table=_TARGET_TABLE,
    ids={"target_id": "keywordId", "campaign_id": "campaignId", "ad_group_id": "adGroupId"},
    # matchType repeats keywordType in this report; it only speaks when keywordType is missing.
    texts={"kind": ("keywordType", "matchType"), "text": ("targeting", "keyword")},
    describe=_target_by_keyword_type,
    metrics={"impressions": "impressions", "clicks": "clicks", "cost": "cost", "purchases_7d": "purchases7d",
             "sales_7d": "sales7d", "purchases_14d": "purchases14d", "sales_14d": "sales14d"},
    optionals={"top_of_search_is": "topOfSearchImpressionShare"},
)
SB_CAMPAIGN_ROWS = _Parser(
    spec=SB_CAMPAIGN_SPEC,
    ad_product="SB",
    table=_CAMPAIGN_TABLE,
    ids={"campaign_id": "campaignId"},
    texts={"cost_type": ("costType",)},
    describe=_campaign_cost_type,
    metrics={**_BRANDS_DISPLAY_METRICS, "new_to_brand_purchases": "newToBrandPurchases",
             "new_to_brand_sales": "newToBrandSales", "viewable_impressions": "viewableImpressions"},
    optionals={"budget_amount": "campaignBudgetAmount", "top_of_search_is": "topOfSearchImpressionShare"},
    currency_field="campaignBudgetCurrencyCode",
)
SB_TARGETING_ROWS = _Parser(
    spec=SB_TARGETING_SPEC,
    ad_product="SB",
    table=_TARGET_TABLE,
    ids={"target_id": "keywordId", "campaign_id": "campaignId", "ad_group_id": "adGroupId"},
    # targetingText is the readable form (category="Everyday Bras" where keywordText has the category id).
    texts={"kind": ("keywordType", "matchType"), "text": ("targetingText", "keywordText", "targetingExpression")},
    describe=_target_by_keyword_type,
    metrics=_BRANDS_DISPLAY_METRICS,
)
SD_CAMPAIGN_ROWS = _Parser(
    spec=SD_CAMPAIGN_SPEC,
    ad_product="SD",
    table=_CAMPAIGN_TABLE,
    ids={"campaign_id": "campaignId"},
    texts={"cost_type": ("costType",)},
    describe=_campaign_cost_type,
    # SD's name for what SB calls viewableImpressions.
    metrics={**_BRANDS_DISPLAY_METRICS, "new_to_brand_purchases": "newToBrandPurchases",
             "new_to_brand_sales": "newToBrandSales", "viewable_impressions": "impressionsViews"},
    optionals={"budget_amount": "campaignBudgetAmount"},
    currency_field="campaignBudgetCurrencyCode",
)
SD_TARGETING_ROWS = _Parser(
    spec=SD_TARGETING_SPEC,
    ad_product="SD",
    table=_TARGET_TABLE,
    ids={"target_id": "targetingId", "campaign_id": "campaignId", "ad_group_id": "adGroupId"},
    texts={"kind": ("targetingExpression",), "text": ("targetingText", "targetingExpression")},
    describe=_target_by_expression,
    metrics=_BRANDS_DISPLAY_METRICS,
)
SB_LEGACY_CAMPAIGN_ROWS = _Parser(
    spec=SB_LEGACY_CAMPAIGN_SPEC,
    ad_product="SB",
    table=_CAMPAIGN_TABLE,
    ids={"campaign_id": "campaignId"},
    texts={},
    describe=_unknown_cost_type,
    # Click-only sales are all the sales it has, so they fill both pairs, as SB's own reports do when no view
    # attributes one.
    metrics={"impressions": "impressions", "clicks": "clicks", "cost": "cost",
             "purchases": "attributedConversions14d", "sales": "attributedSales14d",
             "purchases_clicks": "attributedConversions14d", "sales_clicks": "attributedSales14d",
             "new_to_brand_purchases": "attributedOrdersNewToBrand14d",
             "new_to_brand_sales": "attributedSalesNewToBrand14d"},
    dated=False,
)
