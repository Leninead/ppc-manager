"""PPC Insights por ASIN of Análisis Cruzado: PPC Insights' ASIN rule over the account's search terms. No network."""
import pandas as pd

from core.cross_analysis.asin_summary import (
    ACOS,
    AD_SPEND,
    ASIN,
    BR_SALES,
    BR_SESSIONS,
    CVR,
    GROUPED,
    PRODUCT,
    BusinessReportAsin,
    asin_summary,
    business_report_by_asin,
    top_terms,
)
from core.ppc_insights.asin_health import ATTRIBUTED, NO_ASINS, asin_coverage_caption, find_column
from core.search_term.frame import orders_column, sales_column
from tests.cross_analysis_data import search_terms, term_row

SALES, ORDERS = sales_column(7), orders_column(7)


def _summary(terms, ad_group_asins, business_report=None):
    return asin_summary(search_terms(*terms), ad_group_asins, business_report or {}, sales_column=SALES,
                        orders_column=ORDERS)


def test_an_ad_group_that_advertises_one_asin_gives_it_its_terms():
    summary = _summary([term_row("sleep sack", ad_group_id="4001", cost=10.0, sales=50.0, orders=2, clicks=20)],
                       {"4001": frozenset({"B0CYLMJJJC"})})

    row = summary.rows.iloc[0]
    assert (row[ASIN], row[AD_SPEND], row[ACOS], row[CVR], row[GROUPED]) == ("B0CYLMJJJC", 10.0, 20.0, 10.0, "")


def test_an_ad_group_of_several_asins_goes_whole_to_the_asin_its_campaign_name_carries():
    summary = _summary([term_row("sleep sack", ad_group_id="4002", campaign_name="Luna - B0FAMILY01 - SP - KW",
                                 cost=10.0)],
                       {"4002": frozenset({"B0CHILD0001", "B0CHILD0002"})})

    assert list(summary.rows[ASIN]) == ["B0FAMILY01"]
    assert summary.rows.iloc[0][GROUPED] == "2 ASINs"


def test_an_ad_group_of_several_asins_without_one_in_the_name_is_never_split():
    summary = _summary([term_row("sleep sack", ad_group_id="4002", cost=10.0),
                        term_row("luna pajamas", ad_group_id="4001", cost=30.0)],
                       {"4001": frozenset({"B0CYLMJJJC"}), "4002": frozenset({"B0CHILD0001", "B0CHILD0002"})})

    assert list(summary.rows[ASIN]) == ["B0CYLMJJJC"]
    assert summary.rows.iloc[0][AD_SPEND] == 30.0
    caption = asin_coverage_caption(summary.resolved.source, summary.resolved.spend_share)
    assert "producto anunciado del ad group 75.0%" in caption
    assert "El 25.0% sin ASIN no entra en las cards." in caption


def test_the_asin_comes_from_the_product_ads_since_the_terms_carry_no_asin_column():
    terms = search_terms(term_row("sleep sack", ad_group_id="4001"))

    assert find_column(terms, "ASIN") is None
    summary = asin_summary(terms, {"4001": frozenset({"B0CYLMJJJC"})}, {}, sales_column=SALES,
                           orders_column=ORDERS)
    assert summary.resolved.source == ATTRIBUTED


def test_without_any_asin_there_is_no_summary_row():
    summary = _summary([term_row("sleep sack")], {})

    assert summary.resolved.column is None
    assert summary.resolved.source == NO_ASINS
    assert summary.rows.empty


def test_the_asins_come_most_ad_spend_first():
    summary = _summary([term_row("small", ad_group_id="4001", cost=5.0),
                        term_row("big", ad_group_id="4002", cost=50.0)],
                       {"4001": frozenset({"B0AAAAAAAA"}), "4002": frozenset({"B0ZZZZZZZZ"})})

    assert list(summary.rows[ASIN]) == ["B0ZZZZZZZZ", "B0AAAAAAAA"]


def test_without_sales_or_clicks_acos_and_cvr_are_empty_never_zero():
    summary = _summary([term_row("sleep sack", ad_group_id="4001", cost=10.0, sales=0.0, orders=0, clicks=0)],
                       {"4001": frozenset({"B0CYLMJJJC"})})

    row = summary.rows.iloc[0]
    assert pd.isna(row[ACOS]) and pd.isna(row[CVR])


def test_the_business_report_figures_join_by_asin_and_stay_empty_when_missing():
    report = {"B0CYLMJJJC": BusinessReportAsin(title="Luna Sleep Sack", sessions=320.0, sales=1234.5, units=40.0)}
    summary = _summary([term_row("sleep sack", ad_group_id="4001"), term_row("other", ad_group_id="4002")],
                       {"4001": frozenset({"B0CYLMJJJC"}), "4002": frozenset({"B0OTHER001"})}, report)

    by_asin = summary.rows.set_index(ASIN)
    assert (by_asin.loc["B0CYLMJJJC", PRODUCT], by_asin.loc["B0CYLMJJJC", BR_SESSIONS],
            by_asin.loc["B0CYLMJJJC", BR_SALES]) == ("Luna Sleep Sack", 320.0, 1234.5)
    assert by_asin.loc["B0OTHER001", PRODUCT] == "B0OTHER001"
    assert pd.isna(by_asin.loc["B0OTHER001", BR_SESSIONS]) and pd.isna(by_asin.loc["B0OTHER001", BR_SALES])


def test_the_business_report_by_child_is_keyed_by_the_advertised_child_asin():
    report = pd.DataFrame({"(Parent) ASIN": ["B0PARENT01"], "(Child) ASIN": ["B0CHILD001"], "Title": ["Sleep sack"],
                           "Sessions - Total": ["1,200"], "Sessions - Total - B2B": ["5"],
                           "Ordered Product Sales": ["$2,345.67"], "Ordered Product Sales - B2B": ["$10.00"],
                           "Units Ordered": ["40"]})

    by_asin = business_report_by_asin(report)

    assert list(by_asin) == ["B0CHILD001"]
    assert by_asin["B0CHILD001"] == BusinessReportAsin(title="Sleep sack", sessions=1200.0, sales=2345.67,
                                                       units=40.0)


def test_a_business_report_with_a_single_asin_column_uses_it():
    by_asin = business_report_by_asin(pd.DataFrame({"ASIN": ["B0ONLY0001"], "Sessions - Total": [10]}))

    assert by_asin["B0ONLY0001"].sessions == 10.0
    assert by_asin["B0ONLY0001"].sales is None


def test_a_business_report_without_an_asin_column_gives_nothing():
    assert business_report_by_asin(pd.DataFrame({"Title": ["x"]})) == {}


def test_the_top_terms_sold_most_or_spent_most_when_none_sold():
    summary = _summary([term_row("sold", ad_group_id="4001", cost=1.0, sales=90.0, orders=3),
                        term_row("spent", ad_group_id="4001", cost=40.0),
                        term_row("idle", ad_group_id="4002", cost=5.0), term_row("idler", ad_group_id="4002", cost=9.0)],
                       {"4001": frozenset({"B0AAAAAAAA"}), "4002": frozenset({"B0ZZZZZZZZ"})})

    assert list(top_terms(summary, "B0AAAAAAAA", sales_column=SALES)["Customer Search Term"])[0] == "sold"
    assert list(top_terms(summary, "B0ZZZZZZZZ", sales_column=SALES)["Customer Search Term"]) == ["idler", "idle"]
