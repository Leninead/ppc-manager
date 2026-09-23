"""StructureProvider over a fake PostgREST: the SP structure as rows and under Bulk File headers. No network."""
from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime, timezone

import pandas as pd
import pytest
import requests

from core.amazon_ads.report_provider import READ_TIMEOUT_SECONDS, ProfileOption, ReportReadError
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    CAMPAIGN_NEGATIVE_KEYWORD,
    CAMPAIGN_NEGATIVE_PRODUCT_TARGETING,
    COUNT_COLUMNS,
    ENTITIES,
    KEYWORD,
    NEGATIVE_ENTITIES,
    NEGATIVE_KEYWORD,
    NEGATIVE_PRODUCT_TARGETING,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    ROW_COLUMNS,
    STRUCTURE_COLUMNS,
    STRUCTURE_COUNTS_RPC,
    STRUCTURE_RPC,
    StructureCounts,
    StructureProvider,
    bulk_frame,
)
from core.bulk.parser import get_exact_activas, get_portfolio_por_campaign

START, END = date(2026, 9, 10), date(2026, 9, 16)
WINDOW = {"p_profile_id": "p-1", "p_from": "2026-09-10", "p_to": "2026-09-16"}
LISTED = "2026-09-22 06:00:01.5+00"
SELLER = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Demo", "country_code": "US",
                                 "currency_code": "USD", "account_type": "seller"})
ID_COLUMNS = ("Ad ID", "Keyword ID", "Product Targeting ID")


class _FakeRest:
    def __init__(self, answer: bytes = b"", *, fail_with=None):
        self._answer = answer
        self._fail_with = fail_with
        self.calls = []

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.calls.append((name, args, timeout_s))
        if self._fail_with:
            raise self._fail_with
        return self._answer


def _csv(*rows, header=ROW_COLUMNS) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(header))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _row(family: str, /, **overrides) -> dict:
    row = {column: "" for column in ROW_COLUMNS}
    row.update({"entity": family, "campaign_id": "11", "campaign_name": "Demo SP - Exact", "state": "ENABLED",
                "metrics_known": "f", "listed_at": LISTED})
    row.update(overrides)
    return row


def _campaign(**overrides) -> dict:
    return _row(CAMPAIGN, **{"entity_id": "11", "portfolio_id": "501", "portfolio_name": "RANKING",
                             "targeting_type": "MANUAL", "budget_amount": "25", "budget_type": "DAILY",
                             "bidding_strategy": "LEGACY_FOR_SALES", "metrics_known": "t", "impressions": "900",
                             "clicks": "30", "cost": "21.5", "purchases_7d": "4", "sales_7d": "80.0",
                             "purchases_14d": "5", "sales_14d": "99.0", "currency_code": "USD", **overrides})


def _keyword(**overrides) -> dict:
    return _row(KEYWORD, **{"ad_group_id": "21", "entity_id": "9001", "ad_group_name": "AG - core",
                            "target_kind": "keyword", "target_text": "demo keyword", "match_type": "EXACT",
                            "default_bid": "0.75", "own_bid": "0.85", "bid": "0.85", "metrics_known": "t",
                            "impressions": "120", "clicks": "6", "cost": "4.5", "purchases_7d": "2",
                            "sales_7d": "40.0", "purchases_14d": "3", "sales_14d": "55.0", **overrides})


def _structure(*rows, option: ProfileOption = SELLER, **kwargs):
    rest = _FakeRest(_csv(*rows))
    return StructureProvider(rest).sp_structure(option, START, END, **kwargs), rest


def _only(result):
    assert len(result.frame) == 1
    return result.frame.iloc[0]


@pytest.mark.parametrize("entity, label, id_column", [
    (CAMPAIGN, "Campaign", None),
    (BIDDING_ADJUSTMENT, "Bidding Adjustment", None),
    (AD_GROUP, "Ad Group", None),
    (KEYWORD, "Keyword", "Keyword ID"),
    (PRODUCT_TARGETING, "Product Targeting", "Product Targeting ID"),
    (PRODUCT_AD, "Product Ad", "Ad ID"),
    (NEGATIVE_KEYWORD, "Negative Keyword", "Keyword ID"),
    (CAMPAIGN_NEGATIVE_KEYWORD, "Campaign Negative Keyword", "Keyword ID"),
    (NEGATIVE_PRODUCT_TARGETING, "Negative Product Targeting", "Product Targeting ID"),
    (CAMPAIGN_NEGATIVE_PRODUCT_TARGETING, "Campaign Negative Product Targeting", "Product Targeting ID"),
])
def test_each_family_is_its_bulk_entity_with_its_id_in_its_own_column(entity, label, id_column):
    result, _ = _structure(_row(entity, ad_group_id="21", entity_id="777"))

    row = _only(result)
    assert row["Entity"] == label
    assert (row["Campaign ID"], row["Ad Group ID"]) == ("11", "21")
    for column in ID_COLUMNS:
        assert row[column] == ("777" if column == id_column else "")


def test_the_families_and_the_negatives_are_named_once():
    assert len(ENTITIES) == len(set(ENTITIES)) == 10
    assert set(NEGATIVE_ENTITIES) < set(ENTITIES) and len(NEGATIVE_ENTITIES) == 4


@pytest.mark.parametrize("code, state", [("ENABLED", "enabled"), ("PAUSED", "paused"), ("ARCHIVED", "archived")])
def test_the_state_is_lower_case_as_a_bulk_file_writes_it(code, state):
    result, _ = _structure(_campaign(state=code))

    assert _only(result)["State"] == state


@pytest.mark.parametrize("code, label", [("AUTO", "Auto"), ("MANUAL", "Manual")])
def test_the_targeting_type_reads_as_a_bulk_file_writes_it(code, label):
    result, _ = _structure(_campaign(targeting_type=code))

    assert _only(result)["Targeting Type"] == label


@pytest.mark.parametrize("code, label", [
    ("MANUAL", "Fixed bid"),
    ("LEGACY_FOR_SALES", "Dynamic bids - down only"),
    ("AUTO_FOR_SALES", "Dynamic bids - up and down"),
    # A strategy with no bulk value shows as it came, never as empty.
    ("RULE_BASED", "RULE_BASED"),
])
def test_the_bid_strategy_is_the_value_a_bulk_upload_accepts(code, label):
    result, _ = _structure(_campaign(bidding_strategy=code))

    assert _only(result)["Bidding Strategy"] == label


@pytest.mark.parametrize("entity, code, label", [
    (KEYWORD, "EXACT", "Exact"),
    (KEYWORD, "PHRASE", "Phrase"),
    (KEYWORD, "BROAD", "Broad"),
    (NEGATIVE_KEYWORD, "NEGATIVE_EXACT", "Negative Exact"),
    (CAMPAIGN_NEGATIVE_KEYWORD, "NEGATIVE_PHRASE", "Negative Phrase"),
    (NEGATIVE_KEYWORD, "NEGATIVE_BROAD", "Negative Broad"),
    (PRODUCT_TARGETING, "", ""),
])
def test_the_match_type_reads_as_a_bulk_file_writes_it(entity, code, label):
    result, _ = _structure(_keyword(entity=entity, match_type=code))

    assert _only(result)["Match Type"] == label


@pytest.mark.parametrize("entity, keyword_text, expression", [
    (KEYWORD, "demo keyword", ""),
    (NEGATIVE_KEYWORD, "demo keyword", ""),
    (CAMPAIGN_NEGATIVE_KEYWORD, "demo keyword", ""),
    (PRODUCT_TARGETING, "", "demo keyword"),
    (NEGATIVE_PRODUCT_TARGETING, "", "demo keyword"),
    (CAMPAIGN_NEGATIVE_PRODUCT_TARGETING, "", "demo keyword"),
])
def test_the_target_text_goes_to_the_keyword_or_the_expression_column(entity, keyword_text, expression):
    result, _ = _structure(_keyword(entity=entity))

    row = _only(result)
    assert (row["Keyword Text"], row["Product Targeting Expression"]) == (keyword_text, expression)


def test_a_bidding_adjustment_carries_its_placement_percentage_and_strategy():
    result, _ = _structure(_row(BIDDING_ADJUSTMENT, placement="PLACEMENT_TOP", percentage="50",
                                bidding_strategy="AUTO_FOR_SALES"))

    row = _only(result)
    assert (row["Placement"], row["Percentage"]) == ("PLACEMENT_TOP", 50)
    assert row["Bidding Strategy"] == "Dynamic bids - up and down"


def test_the_portfolio_and_the_daily_budget_are_the_campaign_rows_own():
    result, _ = _structure(_campaign(), _keyword(portfolio_id="501", portfolio_name="RANKING"),
                           _campaign(campaign_id="12", entity_id="12", campaign_name="Demo SP - Lifetime",
                                     portfolio_id="502", portfolio_name="", budget_type="LIFETIME"))

    frame = result.frame.set_index(["Campaign ID", "Entity"])
    assert frame.loc[("11", "Campaign"), "Portfolio Name"] == "RANKING"
    assert frame.loc[("11", "Keyword"), "Portfolio Name"] == ""
    assert frame.loc[("12", "Campaign"), "Portfolio Name"] == "Portfolio 502"
    assert frame.loc[("11", "Campaign"), "Daily Budget"] == 25
    assert math.isnan(frame.loc[("12", "Campaign"), "Daily Budget"])


def test_the_bid_is_the_effective_one_and_the_own_and_default_go_apart():
    result, _ = _structure(_keyword(), _keyword(entity_id="9002", target_text="inherits", own_bid="", bid="0.75"))

    rows = result.rows.set_index("entity_id")
    assert tuple(rows.loc["9001", ["own_bid", "default_bid", "bid"]]) == (0.85, 0.75, 0.85)
    assert math.isnan(rows.loc["9002", "own_bid"]) and rows.loc["9002", "bid"] == 0.75
    frame = result.frame.set_index("Keyword ID")
    assert (frame.loc["9001", "Bid"], frame.loc["9001", "Ad Group Default Bid"]) == (0.85, 0.75)
    assert frame.loc["9002", "Bid"] == 0.75


def test_an_unknown_bid_stays_empty_never_zero():
    result, _ = _structure(_keyword(own_bid="", default_bid="", bid=""))

    assert math.isnan(result.rows.iloc[0]["bid"])
    assert math.isnan(_only(result)["Bid"]) and math.isnan(_only(result)["Ad Group Default Bid"])


@pytest.mark.parametrize("account_type, days, sales, orders", [("seller", 7, 40.0, 2), ("vendor", 14, 55.0, 3)])
def test_sales_and_orders_follow_the_accounts_attribution(account_type, days, sales, orders):
    option = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Demo", "account_type": account_type})
    result, _ = _structure(_keyword(), option=option)

    row = _only(result)
    assert result.attribution_days == days
    assert (row["Sales"], row["Orders"], row["Spend"], row["Impressions"]) == (sales, orders, 4.5, 120)


def test_rows_without_known_metrics_have_nan_metrics_not_zeros():
    result, _ = _structure(_keyword(metrics_known="f"), _row(AD_GROUP, ad_group_id="21", entity_id="21"))

    for field in ("impressions", "clicks", "cost", "purchases_7d", "sales_7d", "purchases_14d", "sales_14d"):
        assert result.rows[field].dtype == "float64"
        assert result.rows[field].isna().all()
    assert result.frame[["Impressions", "Clicks", "Spend", "Sales", "Orders"]].isna().all().all()
    assert result.rows["metrics_known"].tolist() == [False, False]


def test_a_known_row_without_activity_is_zero():
    result, _ = _structure(_keyword(impressions="0", clicks="", cost="0"))

    assert result.rows.iloc[0]["metrics_known"]
    assert (result.rows.iloc[0]["impressions"], result.rows.iloc[0]["clicks"]) == (0, 0)


def test_backslashes_postgrest_doubled_come_back_single():
    result, _ = _structure(_keyword(campaign_name="Demo \\\\ SP", target_text="size 5\\\\6"))

    assert result.rows.iloc[0]["campaign_name"] == "Demo \\ SP"
    assert _only(result)["Keyword Text"] == "size 5\\6"


def test_an_empty_answer_is_a_structure_with_every_column_and_no_rows():
    result = StructureProvider(_FakeRest(b"")).sp_structure(SELLER, START, END)

    assert list(result.rows.columns) == list(ROW_COLUMNS) and result.rows.empty
    assert list(result.frame.columns) == list(STRUCTURE_COLUMNS) and result.frame.empty
    assert result.listed_at == {}
    assert (result.currency_code, result.label) == ("USD", "Demo · US")


def test_without_the_accounts_currency_it_is_the_one_in_the_rows():
    option = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Demo"})
    result, _ = _structure(_campaign(currency_code="MXN"), _keyword(), option=option)

    assert result.currency_code == "MXN"


@pytest.mark.parametrize("answer", [
    _csv({column: "" for column in ROW_COLUMNS if column != "bid"},
         header=[column for column in ROW_COLUMNS if column != "bid"]),
    _csv(_keyword(bid="lots")),
    _csv(_keyword(impressions="many")),
    _csv(_keyword(metrics_known="true")),
    _csv(_keyword(entity="sb_keyword")),
])
def test_a_malformed_answer_is_a_read_error(answer):
    with pytest.raises(ReportReadError):
        StructureProvider(_FakeRest(answer)).sp_structure(SELLER, START, END)


def _http_error(status: int, body: bytes) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response._content = body
    return requests.HTTPError(response=response)


READS = ("sp_structure", "sp_structure_counts")


@pytest.mark.parametrize("read", READS)
def test_a_missing_function_means_migration_018_is_pending_not_an_error(read):
    failure = _http_error(404, b'{"code":"PGRST202","message":"Could not find the function"}')

    assert getattr(StructureProvider(_FakeRest(fail_with=failure)), read)(SELLER, START, END) is None


@pytest.mark.parametrize("read", READS)
@pytest.mark.parametrize("failure", [requests.ConnectionError("rest-gateway down"),
                                     _http_error(500, b'{"code":"57014","message":"statement timeout"}'),
                                     _http_error(404, b'{"code":"PGRST205","message":"Could not find the table"}')])
def test_any_other_failure_is_a_read_error(failure, read):
    with pytest.raises(ReportReadError):
        getattr(StructureProvider(_FakeRest(fail_with=failure)), read)(SELLER, START, END)


def test_an_inverted_range_or_an_unknown_family_fails_before_reading():
    rest = _FakeRest()

    with pytest.raises(ValueError):
        StructureProvider(rest).sp_structure(SELLER, END, START)
    with pytest.raises(ValueError):
        StructureProvider(rest).sp_structure(SELLER, START, END, entities=(KEYWORD, "keywords"))
    with pytest.raises(ValueError):
        StructureProvider(rest).sp_structure_counts(SELLER, END, START)
    assert rest.calls == []


def test_the_families_and_the_campaigns_are_asked_only_when_given():
    _, rest = _structure()
    _, narrowed = _structure(entities=(KEYWORD, PRODUCT_TARGETING), campaign_ids=("11", "12"))

    assert rest.calls == [(STRUCTURE_RPC, WINDOW, READ_TIMEOUT_SECONDS)]
    assert narrowed.calls == [(STRUCTURE_RPC, WINDOW | {"p_entities": ["keyword", "product_targeting"],
                                                        "p_campaign_ids": ["11", "12"]}, READ_TIMEOUT_SECONDS)]


def test_listed_at_is_each_familys_latest_listing():
    result, _ = _structure(_campaign(listed_at="2026-09-22 05:00:00+00"),
                           _keyword(listed_at="2026-09-21 06:00:00+00"),
                           _keyword(entity_id="9002", target_text="later", listed_at="2026-09-22 06:30:00.25+00"))

    assert result.listed_at == {
        CAMPAIGN: datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc),
        KEYWORD: datetime(2026, 9, 22, 6, 30, 0, 250000, tzinfo=timezone.utc),
    }
    assert isinstance(result.rows["listed_at"].dtype, pd.DatetimeTZDtype)


def test_rows_come_by_campaign_then_family_then_ad_group_and_text():
    beta = {"campaign_id": "12", "campaign_name": "Beta"}
    alpha = {"campaign_id": "11", "campaign_name": "Alpha"}
    result, _ = _structure(
        _row(NEGATIVE_KEYWORD, entity_id="n1", target_text="free", **alpha),
        _keyword(entity_id="k2", ad_group_name="AG - b", target_text="apple", **alpha),
        _campaign(entity_id="12", **beta),
        _row(PRODUCT_AD, entity_id="a1", **alpha),
        _keyword(entity_id="k1", ad_group_name="AG - a", target_text="zebra", **alpha),
        _row(BIDDING_ADJUSTMENT, placement="PLACEMENT_TOP", percentage="20", **alpha),
        _row(BIDDING_ADJUSTMENT, placement="PLACEMENT_PRODUCT_PAGE", percentage="0", **alpha),
        _row(AD_GROUP, entity_id="21", ad_group_name="AG - a", **alpha),
        _campaign(entity_id="11", **alpha),
    )

    order = list(zip(result.rows["entity"], result.rows["entity_id"], result.rows["placement"]))
    assert order == [
        (CAMPAIGN, "11", ""),
        (BIDDING_ADJUSTMENT, "", "PLACEMENT_PRODUCT_PAGE"),
        (BIDDING_ADJUSTMENT, "", "PLACEMENT_TOP"),
        (AD_GROUP, "21", ""),
        (KEYWORD, "k1", ""),
        (KEYWORD, "k2", ""),
        (PRODUCT_AD, "a1", ""),
        (NEGATIVE_KEYWORD, "n1", ""),
        (CAMPAIGN, "12", ""),
    ]
    assert list(result.frame["Entity"])[:2] == ["Campaign", "Bidding Adjustment"]


# The counts: how big each family is, without reading its rows.

def _count(entity: str, entity_rows: str, listed_at: str = LISTED) -> dict:
    return {"entity": entity, "entity_rows": entity_rows, "listed_at": listed_at}


def _counts(*rows, **kwargs):
    rest = _FakeRest(_csv(*rows, header=COUNT_COLUMNS))
    return StructureProvider(rest).sp_structure_counts(SELLER, START, END, **kwargs), rest


def test_the_counts_are_each_familys_rows_and_latest_listing_in_the_families_order():
    counts, _ = _counts(_count(NEGATIVE_KEYWORD, "310574", "2026-09-22 07:10:00+00"),
                        _count(CAMPAIGN, "42"),
                        _count(KEYWORD, "1800", "2026-09-22 06:30:00.25+00"))

    assert counts == StructureCounts(
        rows={CAMPAIGN: 42, KEYWORD: 1800, NEGATIVE_KEYWORD: 310574},
        listed_at={CAMPAIGN: datetime(2026, 9, 22, 6, 0, 1, 500000, tzinfo=timezone.utc),
                   KEYWORD: datetime(2026, 9, 22, 6, 30, 0, 250000, tzinfo=timezone.utc),
                   NEGATIVE_KEYWORD: datetime(2026, 9, 22, 7, 10, tzinfo=timezone.utc)},
    )
    assert list(counts.rows) == list(counts.listed_at) == [CAMPAIGN, KEYWORD, NEGATIVE_KEYWORD]
    assert all(type(rows) is int for rows in counts.rows.values())


def test_a_family_counted_at_zero_stays_listed():
    # sp_structure_counts answers the negative families at 0 once a complete run found none of them.
    counts, _ = _counts(_count(NEGATIVE_KEYWORD, "0", "2026-09-22 07:10:00+00"), _count(CAMPAIGN, "42"))

    assert counts.rows == {CAMPAIGN: 42, NEGATIVE_KEYWORD: 0}
    assert counts.listed_at[NEGATIVE_KEYWORD] == datetime(2026, 9, 22, 7, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("answer", [b"", _csv(header=COUNT_COLUMNS)])
def test_a_family_not_in_the_counts_is_not_synced_so_an_empty_answer_counts_nothing(answer):
    counts = StructureProvider(_FakeRest(answer)).sp_structure_counts(SELLER, START, END)

    assert counts == StructureCounts(rows={}, listed_at={})


def test_the_campaigns_are_counted_only_when_given():
    _, rest = _counts()
    _, narrowed = _counts(campaign_ids=("11", "12"))

    assert rest.calls == [(STRUCTURE_COUNTS_RPC, WINDOW, READ_TIMEOUT_SECONDS)]
    assert narrowed.calls == [(STRUCTURE_COUNTS_RPC, WINDOW | {"p_campaign_ids": ["11", "12"]}, READ_TIMEOUT_SECONDS)]


@pytest.mark.parametrize("answer", [
    _csv({"entity": CAMPAIGN, "entity_rows": "42"}, header=("entity", "entity_rows")),
    _csv(_count(CAMPAIGN, "many"), header=COUNT_COLUMNS),
    _csv(_count("sb_keyword", "42"), header=COUNT_COLUMNS),
    _csv(_count(CAMPAIGN, "42", "yesterday"), header=COUNT_COLUMNS),
])
def test_a_malformed_count_is_a_read_error(answer):
    with pytest.raises(ReportReadError):
        StructureProvider(_FakeRest(answer)).sp_structure_counts(SELLER, START, END)


# The Bulk readers of the modules, fed the frame as they are fed a downloaded Bulk File.

def _account():
    return _structure(
        _campaign(),
        _campaign(campaign_id="12", entity_id="12", campaign_name="Demo SP - Auto", portfolio_id="",
                  portfolio_name="", targeting_type="AUTO"),
        _row(AD_GROUP, ad_group_id="21", entity_id="21", ad_group_name="AG - core", default_bid="0.75"),
        _keyword(),
        _keyword(entity_id="9002", target_text="quiet keyword", own_bid="", bid="0.75", impressions="0",
                 clicks="0", cost="0", purchases_7d="0", sales_7d="0", purchases_14d="0", sales_14d="0"),
        _keyword(entity_id="9003", target_text="paused keyword", state="PAUSED"),
        _keyword(entity_id="9004", target_text="phrase keyword", match_type="PHRASE"),
        _row(NEGATIVE_KEYWORD, ad_group_id="21", entity_id="9100", target_text="negative exact",
             match_type="NEGATIVE_EXACT"),
        _row(PRODUCT_AD, ad_group_id="21", entity_id="8001", asin="B0TEST00001", sku="DEMO-001"),
    )[0].frame


def test_the_exact_guard_reads_the_enabled_exact_keywords():
    assert get_exact_activas(_account()) == {"demo keyword", "quiet keyword"}


def test_the_portfolio_guard_reads_the_campaigns_portfolio():
    assert get_portfolio_por_campaign(_account()) == {"11": "RANKING"}


def test_cross_analysis_reads_the_asin_of_each_ad_group():
    from modules.pages.analisis_cruzado import _asin_por_ad_group

    assert _asin_por_ad_group.__wrapped__(_account()) == {"21": "B0TEST00001"}


def test_target_graduation_returns_the_quiet_keyword_with_its_ad_group_and_bid():
    from modules.pages.ppc_audit import _analyze_target_graduation

    frame = _account()
    graduation = _analyze_target_graduation(frame[frame["Entity"] == "Keyword"], frame[frame["Entity"] == "Campaign"])

    assert list(graduation["Keyword ID"]) == ["9002"]
    row = graduation.iloc[0]
    assert (row["Ad Group Name"], row["Bid"], row["Campaign Impressions"]) == ("AG - core", 0.75, 360)


def test_bulk_frame_alone_keeps_the_rows_order_and_columns():
    result, _ = _structure(_campaign(), _keyword())

    frame = bulk_frame(result.rows, 14)
    assert list(frame.columns) == list(STRUCTURE_COLUMNS)
    assert list(frame["Entity"]) == ["Campaign", "Keyword"]
    assert list(frame["Sales"]) == [99.0, 55.0]
