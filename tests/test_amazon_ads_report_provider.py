"""ReportProvider over a fake PostgREST, with M2's real `_detect_cols` as the column oracle. No network."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone

import pandas as pd
import pytest
import requests

from core import search_term_frame as canonical
from core.amazon_ads.report_provider import (
    PROFILE_SYNC_TABLE,
    READ_TIMEOUT_SECONDS,
    SEARCH_TERMS_RPC,
    ProfileOption,
    ReportProvider,
    ReportReadError,
)
from core.search_term_frame import HIDDEN_ID_COLUMNS, SOURCE_API, console_columns
from modules.pages.search_term_report import _detect_cols

RPC_HEADER = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting", "search_term",
              "campaign_name", "campaign_status", "ad_group_name", "keyword_text", "ad_keyword_status",
              "portfolio_id", "portfolio_name", "impressions", "clicks", "cost", "purchases_7d", "sales_7d",
              "units_7d", "purchases_14d", "sales_14d", "units_14d", "currency_code"]
LAST_SUCCESS = datetime(2026, 9, 14, 11, 5, tzinfo=timezone.utc)
START, END = date(2026, 8, 31), date(2026, 9, 13)


class _FakeRest:
    def __init__(self, *, profile_rows=None, csv_bytes=b"", fail_with=None):
        self._profile_rows = list(profile_rows or [])
        self._csv_bytes = csv_bytes
        self._fail_with = fail_with
        self.selects: list[tuple[str, dict]] = []
        self.rpc_calls: list[tuple[str, dict, int]] = []

    def select(self, table, params):
        self.selects.append((table, params))
        if self._fail_with:
            raise self._fail_with
        return self._profile_rows

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.rpc_calls.append((name, args, timeout_s))
        if self._fail_with:
            raise self._fail_with
        return self._csv_bytes


def _profile_row(**overrides) -> dict:
    row = {
        "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo Seller LLC",
        "country_code": "MX", "currency_code": "MXN", "account_type": "seller", "timezone": "America/Los_Angeles",
        "status": "active", "data_from": "2026-07-11", "data_through": "2026-09-13", "refreshed_on": "2026-09-14",
        "last_success_at": "2026-09-14T11:05:00+00:00", "last_error": "",
    }
    row.update(overrides)
    return row


def _option(**overrides) -> ProfileOption:
    return ProfileOption.from_row(_profile_row(**overrides))


def _api_row(**overrides) -> dict:
    row = {
        "campaign_id": "300000000000001", "ad_group_id": "400000000000001", "keyword_type": "BROAD",
        "keyword_id": "500000000000001", "match_type": "BROAD", "targeting": "jabon neutro",
        "search_term": "jabon neutro bebe", "campaign_name": "Demo - SP - KW - BROAD", "campaign_status": "ENABLED",
        "ad_group_name": "Grupo Demo", "keyword_text": "jabon neutro", "ad_keyword_status": "ENABLED",
        "portfolio_id": "600000000000001", "portfolio_name": "DISCOVERY", "impressions": "1600", "clicks": "40",
        "cost": "30.0000", "purchases_7d": "3", "sales_7d": "120.0000", "units_7d": "4", "purchases_14d": "5",
        "sales_14d": "200.0000", "units_14d": "6", "currency_code": "MXN",
    }
    row.update(overrides)
    return row


def _csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RPC_HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _read(rows: list[dict], **option_overrides):
    rest = _FakeRest(csv_bytes=_csv(rows))
    source = ReportProvider(rest).search_terms(_option(**option_overrides), START, END)
    return source, rest


def _expected_detection(days: int) -> dict[str, str]:
    return {
        "search_term": "Customer Search Term", "spend": "Spend", "sales": f"{days} Day Total Sales",
        "orders": f"{days} Day Total Orders (#)", "clicks": "Clicks", "impressions": "Impressions",
        "acos": "Total Advertising Cost of Sales (ACoS)", "ctr": "Click-Thru Rate (CTR)",
        "cvr": f"{days} Day Conversion Rate", "campaign": "Campaign Name", "ad_group": "Ad Group Name",
        "match_type": "Match Type", "portfolio": "Portfolio name",
    }


def test_profiles_query_excludes_inactive_and_sorts_by_label_then_country():
    rest = _FakeRest(profile_rows=[
        _profile_row(profile_id="3", cliente="zeta cosmetics", country_code="US"),
        _profile_row(profile_id="2", cliente="Alfa Kids", country_code="US"),
        _profile_row(profile_id="1", cliente="alfa kids", country_code="CA"),
    ])

    options = ReportProvider(rest).profiles()

    assert [option.profile_id for option in options] == ["1", "2", "3"]
    table, params = rest.selects[0]
    assert table == PROFILE_SYNC_TABLE
    assert params["status"] == "neq.inactive"


def test_profile_label_falls_back_to_account_name():
    assert _option(cliente="").label == "Demo Seller LLC"
    assert _option().label == "Marca Demo"


def test_profile_option_parses_dates_timestamps_and_account_id():
    option = _option(account_id=None, data_from=None)

    assert option.account_id is None
    assert option.data_from is None
    assert option.data_through == date(2026, 9, 13)
    assert option.refreshed_on == date(2026, 9, 14)
    assert option.last_success_at == LAST_SUCCESS


def test_profiles_read_failure_raises_report_read_error_with_spanish_message():
    rest = _FakeRest(fail_with=requests.ConnectionError("gateway down"))

    with pytest.raises(ReportReadError, match="No se pudo leer las cuentas de Amazon Ads"):
        ReportProvider(rest).profiles()


def test_search_terms_calls_rpc_with_iso_dates_and_long_timeout():
    _, rest = _read([_api_row()])

    assert rest.rpc_calls == [(SEARCH_TERMS_RPC,
                               {"p_profile_id": "1111222233334444", "p_from": "2026-08-31", "p_to": "2026-09-13"},
                               READ_TIMEOUT_SECONDS)]


def test_seller_frame_uses_the_seven_day_triple():
    source, _ = _read([_api_row()], account_type="seller")
    first = source.frame.iloc[0]

    assert source.attribution_days == 7
    assert (first["7 Day Total Sales"], first["7 Day Total Orders (#)"], first["7 Day Total Units (#)"]) == (120.0, 3, 4)
    assert not any(column.startswith("14 Day") for column in source.frame.columns)
    assert first["Total Advertising Cost of Sales (ACoS)"] == 25.0
    assert first["7 Day Conversion Rate"] == 7.5


def test_vendor_frame_uses_the_fourteen_day_triple():
    source, _ = _read([_api_row()], account_type="Vendor")
    first = source.frame.iloc[0]

    assert source.attribution_days == 14
    assert (first["14 Day Total Sales"], first["14 Day Total Orders (#)"], first["14 Day Total Units (#)"]) == (200.0, 5, 6)
    assert not any(column.startswith("7 Day") for column in source.frame.columns)
    assert first["Total Advertising Cost of Sales (ACoS)"] == 15.0


@pytest.mark.parametrize("account_type, days", [("seller", 7), ("vendor", 14)])
def test_m2_detect_cols_maps_every_canonical_key_and_never_a_hidden_column(account_type, days):
    source, _ = _read([_api_row(), _api_row(search_term="otro termino")], account_type=account_type)

    detected = _detect_cols(source.frame)

    assert detected == _expected_detection(days)
    assert not any(str(column).startswith("_") for column in detected.values())


def test_hidden_columns_come_last_in_contract_order():
    source, _ = _read([_api_row()])

    columns = list(source.frame.columns)
    assert columns == console_columns(7) + list(HIDDEN_ID_COLUMNS)


def test_keyword_rows_keep_their_match_type_and_origin():
    source, _ = _read([_api_row(match_type="exact", keyword_type="EXACT")])
    first = source.frame.iloc[0]

    assert first["Match Type"] == "EXACT"
    assert first["_origin_match_type"] == "EXACT"
    assert first["_keyword_type"] == "EXACT"


@pytest.mark.parametrize("target_type, origin", [
    ("TARGETING_EXPRESSION_PREDEFINED", "AUTO"),
    ("TARGETING_EXPRESSION", "PRODUCT_TARGETING"),
])
def test_targets_show_a_dash_match_type_and_their_origin(target_type, origin):
    source, _ = _read([_api_row(match_type=target_type, keyword_type=target_type, targeting="close-match",
                                keyword_id="700000000000001", keyword_text="")])
    first = source.frame.iloc[0]

    assert first["Match Type"] == "-"
    assert first["Targeting"] == "close-match"
    assert first["_origin_match_type"] == origin


def test_unknown_targeting_type_has_dash_and_empty_origin():
    source, _ = _read([_api_row(match_type="", keyword_type="THEME")])

    assert source.frame.iloc[0]["Match Type"] == "-"
    assert source.frame.iloc[0]["_origin_match_type"] == ""


def test_portfolio_label_uses_name_then_id_then_empty():
    source, _ = _read([
        _api_row(search_term="con nombre", portfolio_name="RANKING Core", cost="3"),
        _api_row(search_term="sin nombre", portfolio_id="600000000000009", portfolio_name="", cost="2"),
        _api_row(search_term="sin portfolio", portfolio_id="", portfolio_name="", cost="1"),
    ])
    labels = dict(zip(source.frame["Customer Search Term"], source.frame["Portfolio name"]))

    assert labels == {"con nombre": "RANKING Core", "sin nombre": "Portfolio 600000000000009",
                      "sin portfolio": ""}


def test_ids_stay_exact_strings():
    long_id = "123456789012345678"
    source, _ = _read([_api_row(campaign_id=long_id, ad_group_id="400000000000001", keyword_id="")])
    first = source.frame.iloc[0]

    assert first["_campaign_id"] == long_id
    assert first["_ad_group_id"] == "400000000000001"
    assert first["_keyword_id"] == ""
    assert source.frame["_campaign_id"].map(type).eq(str).all()


def test_search_terms_that_look_like_missing_values_stay_text():
    source, _ = _read([_api_row(search_term="NA"), _api_row(search_term="null", cost="1")])

    assert set(source.frame["Customer Search Term"]) == {"NA", "null"}


def test_rows_are_sorted_by_spend_then_clicks_then_term():
    source, _ = _read([
        _api_row(search_term="b", cost="5", clicks="2"),
        _api_row(search_term="a", cost="5", clicks="2"),
        _api_row(search_term="c", cost="9", clicks="1"),
        _api_row(search_term="d", cost="5", clicks="8"),
    ])

    assert list(source.frame["Customer Search Term"]) == ["c", "d", "a", "b"]


def test_ties_come_out_in_one_order_whatever_order_the_rpc_answers_in():
    rows = [
        _api_row(ad_group_id="400000000000002", keyword_id="500000000000009"),
        _api_row(ad_group_id="400000000000001", keyword_id="500000000000003"),
        _api_row(ad_group_id="400000000000001", keyword_id="500000000000002", targeting="otro"),
        _api_row(ad_group_id="400000000000001", keyword_id="500000000000002"),
    ]

    orders = {tuple(zip(source.frame["_ad_group_id"], source.frame["_keyword_id"], source.frame["Targeting"]))
              for source in (_read(permutation)[0] for permutation in (rows, rows[::-1], rows[1:] + rows[:1]))}

    assert orders == {(("400000000000001", "500000000000002", "jabon neutro"),
                       ("400000000000001", "500000000000002", "otro"),
                       ("400000000000001", "500000000000003", "jabon neutro"),
                       ("400000000000002", "500000000000009", "jabon neutro"))}


def test_source_metadata_label_currency_bulk_ready_profile():
    source, _ = _read([_api_row()])

    assert source.source == SOURCE_API
    assert source.label == "Marca Demo · MX"
    assert source.currency_code == "MXN"
    assert source.bulk_ready is True
    assert source.profile_id == "1111222233334444"


def test_currency_falls_back_to_the_data_when_the_profile_has_none():
    source, _ = _read([_api_row(currency_code="usd")], currency_code="", country_code="US")

    assert source.currency_code == "USD"
    assert source.label == "Marca Demo · US"


def test_signature_is_stable_and_changes_with_range_or_new_ingest():
    rest = _FakeRest(csv_bytes=_csv([_api_row()]))
    provider = ReportProvider(rest)
    option = _option()

    first = provider.search_terms(option, START, END).signature
    again = provider.search_terms(_option(), START, END).signature
    other_range = provider.search_terms(option, date(2026, 9, 1), END).signature
    newer_ingest = provider.search_terms(_option(last_success_at="2026-09-15T11:05:00+00:00"), START, END).signature

    assert first == again
    assert len(first) == 16
    assert len({first, other_range, newer_ingest}) == 3


def test_empty_answer_gives_an_empty_frame_m2_still_detects():
    for csv_bytes in (b"", _csv([])):
        source = ReportProvider(_FakeRest(csv_bytes=csv_bytes)).search_terms(_option(), START, END)

        assert source.frame.empty
        assert list(source.frame.columns) == console_columns(7) + list(HIDDEN_ID_COLUMNS)
        assert _detect_cols(source.frame) == _expected_detection(7)


def test_inverted_range_is_rejected_before_reading():
    rest = _FakeRest(csv_bytes=_csv([_api_row()]))

    with pytest.raises(ValueError, match="ends before it starts"):
        ReportProvider(rest).search_terms(_option(), END, START)
    assert rest.rpc_calls == []


def test_rpc_failure_raises_report_read_error():
    rest = _FakeRest(fail_with=requests.HTTPError("503 Server Error"))

    with pytest.raises(ReportReadError):
        ReportProvider(rest).search_terms(_option(), START, END)


def test_answer_without_expected_columns_raises_report_read_error():
    broken = pd.DataFrame([_api_row()]).drop(columns=["sales_14d"]).to_csv(index=False).encode("utf-8")

    with pytest.raises(ReportReadError):
        ReportProvider(_FakeRest(csv_bytes=broken)).search_terms(_option(), START, END)


def test_non_numeric_metric_raises_report_read_error():
    with pytest.raises(ReportReadError):
        _read([_api_row(clicks="muchos")])


def _record_out_csv(rows: list[dict]) -> bytes:
    """CSV the way PostgREST's text/csv writes it: fields quoted and '"' and backslash doubled, like record_out."""
    def field(value: str) -> str:
        needs_quotes = value == "" or any(character in '"\\(),' or character.isspace() for character in value)
        escaped = "".join(character * 2 if character in ('"', "\\") else character for character in value)
        return f'"{escaped}"' if needs_quotes else escaped

    lines = [",".join(RPC_HEADER)] + [",".join(field(str(row[column])) for column in RPC_HEADER) for row in rows]
    return "\n".join(lines).encode("utf-8")


def test_backslashes_doubled_by_the_csv_answer_are_restored_in_every_text_column():
    backslash = "\\"
    term = f"shoe{backslash}size"
    campaign = f'Demo {backslash}{backslash} "SP"'
    rest = _FakeRest(csv_bytes=_record_out_csv([_api_row(search_term=term, campaign_name=campaign,
                                                         keyword_text=f"kw{backslash}")]))

    first = ReportProvider(rest).search_terms(_option(), START, END).frame.iloc[0]

    assert first["Customer Search Term"] == term
    assert first["Campaign Name"] == campaign
    assert first["_keyword_text"] == f"kw{backslash}"


def test_portfolio_name_missing_flags_only_a_portfolio_id_without_name():
    source, _ = _read([
        _api_row(search_term="con nombre", portfolio_name="RANKING Core", cost="3"),
        _api_row(search_term="sin nombre", portfolio_id="987", portfolio_name=" ", cost="2"),
        _api_row(search_term="sin portfolio", portfolio_id="", portfolio_name="", cost="1"),
    ])
    flags = dict(zip(source.frame["Customer Search Term"], source.frame[canonical.PORTFOLIO_NAME_MISSING]))

    assert flags == {"con nombre": False, "sin nombre": True, "sin portfolio": False}


@pytest.mark.parametrize("purchases_7d, purchases_14d, expected", [("0", "3", 3), ("2", "5", 5), ("4", "1", 4)])
def test_any_window_purchases_is_the_larger_of_both_windows(purchases_7d, purchases_14d, expected):
    source, _ = _read([_api_row(purchases_7d=purchases_7d, purchases_14d=purchases_14d)], account_type="seller")

    assert source.frame.iloc[0][canonical.ANY_WINDOW_PURCHASES] == expected
    assert source.frame.iloc[0]["7 Day Total Orders (#)"] == int(purchases_7d)


@pytest.mark.parametrize("profile_currency, data_currency, expected", [
    ("<b>MXN</b>", "", ""),
    ("", "US$", ""),
    ("", "eur", "EUR"),
    ("MXN'", "MXN", "MXN"),
])
def test_currency_codes_that_are_not_three_letters_become_empty(profile_currency, data_currency, expected):
    source, _ = _read([_api_row(currency_code=data_currency)], currency_code=profile_currency)

    assert source.currency_code == expected


def test_ratios_are_zero_without_traffic_or_sales():
    source, _ = _read([_api_row(impressions="0", clicks="0", cost="0", sales_7d="0", purchases_7d="0")])
    first = source.frame.iloc[0]

    assert (first[canonical.CTR], first[canonical.CPC], first["7 Day Conversion Rate"], first[canonical.ACOS]) == (
        0.0, 0.0, 0.0, 0.0)
