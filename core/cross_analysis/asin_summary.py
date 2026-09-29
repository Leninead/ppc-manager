"""PPC Insights por ASIN of Análisis Cruzado: each advertised ASIN's search term totals and its top terms.

The ASIN behind each search term follows PPC Insights' rule (core/ppc_insights/asin_health.resolve_asins): the ad
group's own ASIN when it advertises only one, otherwise the ASIN its campaign name carries, and never a split of one ad
group's metrics between its ASINs.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.ppc_insights.asin_health import ResolvedAsins, resolve_asins
from core.ppc_metrics import calc_acos, calc_cvr
from core.search_term.frame import CLICKS, SPEND

ASIN = "ASIN"
PRODUCT = "Producto"
GROUPED = "Agrupa"
AD_SPEND = "Ad Spend"
AD_SALES = "Ad Sales"
ACOS = "ACoS %"
ORDERS = "Orders"
CVR = "CVR %"
BR_SESSIONS = "Sessions (BR)"
BR_SALES = "Total Sales (BR)"

TOP_TERMS_PER_ASIN = 5
ASINS_WITH_TOP_TERMS = 15
_TITLE_CHARACTERS = 50


@dataclass(frozen=True)
class BusinessReportAsin:
    title: str
    sessions: float | None
    sales: float | None
    units: float | None


@dataclass(frozen=True)
class AsinSummary:
    rows: pd.DataFrame  # one row per ASIN, most ad spend first
    terms: pd.DataFrame  # the search terms with their ASIN in `resolved.column`
    resolved: ResolvedAsins


def business_report_by_asin(report: pd.DataFrame) -> dict[str, BusinessReportAsin]:
    """The Business Report by ASIN, keyed by the child ASIN: the ASIN a product ad advertises."""
    columns = list(report.columns)
    asin_column = (_first_column(columns, "(child) asin") or _first_column(columns, "asin"))
    if asin_column is None:
        return {}
    title = _first_column(columns, "title")
    sessions = next((column for column in columns if "session" in column.lower() and "total" in column.lower()
                     and "b2b" not in column.lower()), None)
    sales = next((column for column in columns if "ordered product sales" in column.lower()
                  and "b2b" not in column.lower()), None)
    units = next((column for column in columns if "units ordered" in column.lower()
                  and "b2b" not in column.lower()), None)
    by_asin = {}
    for row in report.to_dict("records"):
        asin = str(row.get(asin_column) or "").strip()
        if not asin or asin.lower() == "nan":
            continue
        by_asin[asin] = BusinessReportAsin(
            title=str(row.get(title) or "")[:_TITLE_CHARACTERS] if title else "",
            sessions=_amount(row.get(sessions)) if sessions else None,
            sales=_amount(row.get(sales)) if sales else None,
            units=_amount(row.get(units)) if units else None,
        )
    return by_asin


def asin_summary(search_terms: pd.DataFrame, ad_group_asins: dict[str, frozenset[str]],
                 business_report: dict[str, BusinessReportAsin], *, sales_column: str,
                 orders_column: str) -> AsinSummary:
    """Each ASIN's spend, sales, orders, ACoS and CVR over its search terms, with the Business Report's figures."""
    resolved = resolve_asins(search_terms.copy(), ad_group_asins)
    terms = resolved.frame
    if resolved.column is None:
        return AsinSummary(pd.DataFrame(columns=_ROW_COLUMNS), terms, resolved)
    figures = [SPEND, sales_column, orders_column, CLICKS]
    for column in figures:
        terms[column] = pd.to_numeric(terms[column], errors="coerce").fillna(0)
    totals = terms.dropna(subset=[resolved.column]).groupby(resolved.column, as_index=False)[figures].sum()
    rows = []
    for record in totals.to_dict("records"):
        asin = str(record[resolved.column])
        report = business_report.get(asin)
        acos = calc_acos(record[SPEND], record[sales_column])
        cvr = calc_cvr(record[orders_column], record[CLICKS])
        grouped = resolved.grouped_asins.get(asin)
        rows.append({
            ASIN: asin,
            PRODUCT: report.title if report and report.title else asin,
            GROUPED: f"{grouped} ASINs" if grouped else "",
            AD_SPEND: round(float(record[SPEND]), 2),
            AD_SALES: round(float(record[sales_column]), 2),
            # INV-7: empty when the ASIN sold nothing (or got no click), never a 0 that reads as efficient.
            ACOS: round(acos, 1) if acos is not None else None,
            ORDERS: int(record[orders_column]),
            CVR: round(cvr, 1) if cvr is not None else None,
            BR_SESSIONS: report.sessions if report else None,
            BR_SALES: round(report.sales, 2) if report and report.sales is not None else None,
        })
    summary = pd.DataFrame(rows, columns=_ROW_COLUMNS).sort_values([AD_SPEND, ASIN], ascending=[False, True])
    return AsinSummary(summary.reset_index(drop=True), terms, resolved)


def top_terms(summary: AsinSummary, asin: str, *, sales_column: str) -> pd.DataFrame:
    """The ASIN's search terms that sold most, or spent most when none sold."""
    own = summary.terms[summary.terms[summary.resolved.column] == asin]
    ranking = sales_column if own[sales_column].sum() > 0 else SPEND
    return own.nlargest(TOP_TERMS_PER_ASIN, ranking)


_ROW_COLUMNS = [ASIN, PRODUCT, GROUPED, AD_SPEND, AD_SALES, ACOS, ORDERS, CVR, BR_SESSIONS, BR_SALES]


def _first_column(columns: list[str], fragment: str) -> str | None:
    return next((column for column in columns if fragment in column.lower()), None)


def _amount(value) -> float | None:
    """A Business Report figure as a number: its currency marks and thousands separators dropped; None if unreadable."""
    number = pd.to_numeric(str(value).replace("$", "").replace(",", "").replace("MX", "").strip(), errors="coerce")
    return None if pd.isna(number) else float(number)
