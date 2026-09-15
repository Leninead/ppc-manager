"""Tests for core/search_term_file.py with synthetic files that copy the real console header layouts."""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
from datetime import datetime

import pandas as pd
import pytest

from core.search_term_file import (
    ALL_ACCOUNTS_KEY,
    CONSOLE_2026_ATTRIBUTION_DAYS,
    FORMAT_CONSOLE_2026,
    FORMAT_CONSOLE_LEGACY,
    FORMAT_UNKNOWN,
    FileAccount,
    SearchTermFileError,
    read_search_term_file,
)
from core.search_term_frame import SOURCE_FILE, console_columns
from modules.pages.search_term_report import _detect_cols

LEGACY_HEADERS = [
    "Start Date", "End Date", "Portfolio name", "Currency", "Campaign Name", "Ad Group Name", "Retailer", "Country",
    "Targeting", "Match Type", "Customer Search Term", "Impressions", "Clicks", "Click-Thru Rate (CTR)",
    "Cost Per Click (CPC)", "Spend", "7 Day Total Sales ", "Total Advertising Cost of Sales (ACOS) ",
    "Total Return on Advertising Spend (ROAS)", "7 Day Total Orders (#)", "7 Day Total Units (#)",
    "7 Day Conversion Rate", "7 Day Advertised SKU Units (#)", "7 Day Other SKU Units (#)",
    "7 Day Advertised SKU Sales ", "7 Day Other SKU Sales ",
]

CONSOLE_2026_HEADERS = [
    "Budget currency", "Date range", "Advertiser account ID", "Advertiser account name", "Portfolio ID",
    "Portfolio name", "Campaign ID", "Campaign name", "Ad group ID", "Ad group name", "Search term", "Impressions",
    "Clicks", "CTR", "Total cost", "Purchases", "Sales", "Units sold", "Cost per purchase", "Purchase rate", "ROAS",
    "Purchases (promoted)", "Sales (promoted)", "Units sold (promoted)", "Cost per purchase (promoted)",
    "Purchase rate (promoted)", "ROAS (promoted)", "Purchases (halo)", "Sales (halo)", "Units sold (halo)",
    "Purchases (new to brand)", "Sales (new to brand)", "Units sold (new to brand)",
    "Cost per purchase (new to brand)", "Purchase rate (new to brand)", "ROAS (new to brand)", "Detail page views",
    "Cost per detail page view", "Detail page view rate",
]

NORTH_ACCOUNT_ID = "4471029384756102"
SOUTH_ACCOUNT_ID = "5582130495867213"
SOUTH_CAMPAIGN_ID = "281234567890123456"

EXPECTED_2026_DETECTION = {
    "search_term": "Customer Search Term",
    "spend": "Spend",
    "sales": "7 Day Total Sales",
    "orders": "7 Day Total Orders (#)",
    "clicks": "Clicks",
    "impressions": "Impressions",
    "acos": "Total Advertising Cost of Sales (ACoS)",
    "ctr": "Click-Thru Rate (CTR)",
    "cvr": "7 Day Conversion Rate",
    "campaign": "Campaign Name",
    "ad_group": "Ad Group Name",
    "match_type": "Match Type",
    "portfolio": "Portfolio name",
}


def _legacy_row(term: str, currency: str, country: str, *, impressions: int, clicks: int, spend: float,
                sales: float, orders: int) -> dict:
    return {
        "Start Date": datetime(2026, 8, 18), "End Date": datetime(2026, 8, 24), "Portfolio name": "Portfolio Alfa",
        "Currency": currency, "Campaign Name": "Campaña Demo - KW - Exact", "Ad Group Name": "Grupo Demo",
        "Retailer": "Amazon", "Country": country, "Targeting": "botella termica", "Match Type": "EXACT",
        "Customer Search Term": term, "Impressions": impressions, "Clicks": clicks,
        "Click-Thru Rate (CTR)": clicks / impressions, "Cost Per Click (CPC)": spend / clicks, "Spend": spend,
        "7 Day Total Sales ": sales, "Total Advertising Cost of Sales (ACOS) ": spend / sales if sales else None,
        "Total Return on Advertising Spend (ROAS)": sales / spend, "7 Day Total Orders (#)": orders,
        "7 Day Total Units (#)": orders, "7 Day Conversion Rate": orders / clicks,
        "7 Day Advertised SKU Units (#)": orders, "7 Day Other SKU Units (#)": 0,
        "7 Day Advertised SKU Sales ": sales, "7 Day Other SKU Sales ": 0.0,
    }


def _xlsx_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    return buffer.getvalue()


def _legacy_xlsx(rows: list[dict], headers: list[str] = LEGACY_HEADERS) -> bytes:
    return _xlsx_bytes(pd.DataFrame(rows).reindex(columns=headers))


def _mexico_legacy_rows() -> list[dict]:
    return [
        _legacy_row("botella termica", "MXN", "MX", impressions=900, clicks=12, spend=48.5, sales=310.0, orders=2),
        _legacy_row("termo acero 1l", "MXN", "MX", impressions=450, clicks=6, spend=21.0, sales=0.0, orders=0),
        _legacy_row("vaso termico", "MXN", "MX", impressions=1200, clicks=20, spend=66.0, sales=455.5, orders=3),
    ]


def _console_2026_row(account_id: str, account_name: str, currency: str, term: str, **metrics: str) -> dict:
    row = dict.fromkeys(CONSOLE_2026_HEADERS, "")
    row.update({
        "Budget currency": currency, "Date range": "Aug 18, 2026 - Aug 24, 2026",
        "Advertiser account ID": account_id, "Advertiser account name": account_name,
        "Portfolio ID": "", "Portfolio name": f"Portfolio {account_name}",
        "Campaign ID": "181234567890123456", "Campaign name": f"Campaña {account_name}",
        "Ad group ID": "191234567890123456", "Ad group name": f"Grupo {account_name}", "Search term": term,
    })
    row.update(metrics)
    return row


def _two_account_rows() -> list[dict]:
    north, south = ("Tienda Ejemplo Norte", "USD"), ("Marca Demo Sur", "MXN")
    return [
        _console_2026_row(NORTH_ACCOUNT_ID, *north, "vaso infantil", **{
            "Impressions": "400", "Clicks": "10", "Total cost": "5.50", "Purchases": "1", "Sales": "18.99",
            "Units sold": "1"}),
        _console_2026_row(SOUTH_ACCOUNT_ID, *south, "botella termica 1l", **{
            "Campaign ID": SOUTH_CAMPAIGN_ID, "Ad group ID": "391234567890123457", "Impressions": "1600",
            "Clicks": "40", "CTR": "0.025", "Total cost": "30.00", "Purchases": "3", "Sales": "120.00",
            "Units sold": "4"}),
        _console_2026_row(NORTH_ACCOUNT_ID, *north, "plato bambu", **{
            "Impressions": "250", "Clicks": "4", "Total cost": "2.20", "Purchases": "0", "Sales": "0",
            "Units sold": "0"}),
        _console_2026_row(SOUTH_ACCOUNT_ID, *south, "termo sin trafico", **{
            "Campaign ID": "", "Impressions": "0", "Clicks": "0", "Total cost": "0", "Purchases": "0", "Sales": "0",
            "Units sold": ""}),
        _console_2026_row(SOUTH_ACCOUNT_ID, *south, "tapa de repuesto", **{
            "Impressions": "300", "Clicks": "5", "Total cost": "2.35", "Purchases": "0", "Sales": "0",
            "Units sold": "0"}),
    ]


def _csv_bytes(rows: list[dict], headers: list[str] = CONSOLE_2026_HEADERS) -> bytes:
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode("utf-8-sig")


def _digest(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


# Legacy console export

def test_legacy_fixture_keeps_the_real_header_layout_with_trailing_spaces():
    headers = list(pd.read_excel(io.BytesIO(_legacy_xlsx(_mexico_legacy_rows()))).columns)
    assert headers == LEGACY_HEADERS
    assert "7 Day Total Sales " in headers


def test_legacy_frame_passes_through_unchanged():
    file_bytes = _legacy_xlsx(_mexico_legacy_rows())
    todays_frame = pd.read_excel(io.BytesIO(file_bytes))

    search_term_file = read_search_term_file(file_bytes, "str_semana.xlsx")
    source = search_term_file.source_for(ALL_ACCOUNTS_KEY, file_name="str_semana.xlsx",
                                         file_bytes_digest=_digest(file_bytes))

    assert search_term_file.format == FORMAT_CONSOLE_LEGACY
    pd.testing.assert_frame_equal(source.frame, todays_frame)
    assert _detect_cols(source.frame) == _detect_cols(todays_frame)
    assert _detect_cols(source.frame)["sales"] == "7 Day Total Sales "


def test_legacy_single_currency_is_one_account_with_that_currency():
    file_bytes = _legacy_xlsx(_mexico_legacy_rows())
    search_term_file = read_search_term_file(file_bytes, "str_semana.xlsx")
    source = search_term_file.source_for(ALL_ACCOUNTS_KEY, file_name="str_semana.xlsx",
                                         file_bytes_digest=_digest(file_bytes))

    assert search_term_file.accounts == (FileAccount(ALL_ACCOUNTS_KEY, "str_semana.xlsx", "MXN", 3),)
    assert (source.currency_code, source.source, source.bulk_ready) == ("MXN", SOURCE_FILE, False)
    assert (source.label, source.attribution_days, source.profile_id) == ("str_semana.xlsx", 7, "")
    assert source.signature == f"{_digest(file_bytes)[:16]}:{ALL_ACCOUNTS_KEY}"


def test_legacy_file_with_several_currencies_splits_by_currency_and_country():
    rows = [
        _legacy_row("water bottle", "USD", "US", impressions=800, clicks=10, spend=12.0, sales=60.0, orders=2),
        _legacy_row("gourde isotherme", "CAD", "CA", impressions=300, clicks=5, spend=6.5, sales=0.0, orders=0),
        _legacy_row("steel tumbler", "USD", "US", impressions=500, clicks=8, spend=9.0, sales=35.0, orders=1),
    ]
    file_bytes = _legacy_xlsx(rows)
    todays_frame = pd.read_excel(io.BytesIO(file_bytes))

    search_term_file = read_search_term_file(file_bytes, "str_norteamerica.xlsx")

    assert search_term_file.accounts == (
        FileAccount("CAD:CA", "CA · CAD", "CAD", 1),
        FileAccount("USD:US", "US · USD", "USD", 2),
    )
    us_source = search_term_file.source_for("USD:US", file_name="str_norteamerica.xlsx",
                                            file_bytes_digest=_digest(file_bytes))
    expected_us_rows = todays_frame[todays_frame["Currency"] == "USD"].reset_index(drop=True)
    pd.testing.assert_frame_equal(us_source.frame, expected_us_rows)
    assert us_source.currency_code == "USD"
    assert us_source.label == "US · USD · str_norteamerica.xlsx"


def test_legacy_file_without_currency_column_has_unknown_currency():
    headers = [header for header in LEGACY_HEADERS if header != "Currency"]
    search_term_file = read_search_term_file(_legacy_xlsx(_mexico_legacy_rows(), headers), "sin_moneda.xlsx")
    assert search_term_file.format == FORMAT_CONSOLE_LEGACY
    assert search_term_file.accounts[0].currency_code == ""


def test_legacy_fourteen_day_export_reports_fourteen_day_attribution():
    renamed = {header: header.replace("7 Day", "14 Day") for header in LEGACY_HEADERS}
    rows = [{renamed[key]: value for key, value in row.items()} for row in _mexico_legacy_rows()]
    search_term_file = read_search_term_file(_legacy_xlsx(rows, list(renamed.values())), "vendor.xlsx")
    assert search_term_file.attribution_days == 14


def test_legacy_csv_with_byte_order_mark_is_detected():
    frame = pd.DataFrame(_mexico_legacy_rows()).reindex(columns=LEGACY_HEADERS)
    file_bytes = frame.to_csv(index=False).encode("utf-8-sig")
    assert file_bytes.startswith(codecs.BOM_UTF8)

    search_term_file = read_search_term_file(file_bytes, "str_semana.csv")
    source = search_term_file.source_for(ALL_ACCOUNTS_KEY, file_name="str_semana.csv",
                                         file_bytes_digest=_digest(file_bytes))

    assert search_term_file.format == FORMAT_CONSOLE_LEGACY
    assert list(source.frame.columns) == LEGACY_HEADERS
    assert source.currency_code == "MXN"


# 2026 console export

def test_console_2026_fixture_has_byte_order_mark_and_real_headers():
    file_bytes = _csv_bytes(_two_account_rows())
    assert file_bytes.startswith(codecs.BOM_UTF8)
    assert list(pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig").columns) == CONSOLE_2026_HEADERS


def test_console_2026_splits_accounts_by_advertiser_account_with_their_currency():
    search_term_file = read_search_term_file(_csv_bytes(_two_account_rows()), "search_term.csv")
    assert search_term_file.format == FORMAT_CONSOLE_2026
    assert search_term_file.attribution_days == CONSOLE_2026_ATTRIBUTION_DAYS == 7
    assert search_term_file.accounts == (
        FileAccount(NORTH_ACCOUNT_ID, "Tienda Ejemplo Norte", "USD", 2),
        FileAccount(SOUTH_ACCOUNT_ID, "Marca Demo Sur", "MXN", 3),
    )


def _global_account_rows() -> list[dict]:
    # As the console exports it: ids wrapped in ="…" and one advertiser account spanning two marketplaces.
    wrapped_account_id = '="amzn1.ads-account.g.demo0global0account"'
    return [
        _console_2026_row(wrapped_account_id, "Cuenta Global Demo", "USD", "knife sharpener", **{
            "Campaign ID": '="171234567890123"', "Ad group ID": '="87966052056847"', "Impressions": "900",
            "Clicks": "20", "Total cost": "12.50", "Purchases": "2", "Sales": "59.98", "Units sold": "2"}),
        _console_2026_row(wrapped_account_id, "Cuenta Global Demo", "MXN", "afilador de cuchillos", **{
            "Campaign ID": '="171234567890999"', "Ad group ID": '="87966052050000"', "Impressions": "300",
            "Clicks": "6", "Total cost": "9.67", "Purchases": "1", "Sales": "380.99", "Units sold": "1"}),
        _console_2026_row(wrapped_account_id, "Cuenta Global Demo", "USD", "sharpener stone", **{
            "Impressions": "100", "Clicks": "2", "Total cost": "1.10", "Purchases": "0", "Sales": "0",
            "Units sold": "0"}),
    ]


def test_console_2026_account_with_two_currencies_splits_by_currency():
    file_bytes = _csv_bytes(_global_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")

    account_id = "amzn1.ads-account.g.demo0global0account"
    assert search_term_file.accounts == (
        FileAccount(f"{account_id}:USD", "Cuenta Global Demo · USD", "USD", 2),
        FileAccount(f"{account_id}:MXN", "Cuenta Global Demo · MXN", "MXN", 1),
    )
    usd, mxn = (search_term_file.source_for(account.key, file_name="search_term.csv",
                                            file_bytes_digest=_digest(file_bytes))
                for account in search_term_file.accounts)
    assert (usd.currency_code, usd.frame["Spend"].sum()) == ("USD", pytest.approx(13.60))
    assert (mxn.currency_code, list(mxn.frame["Customer Search Term"])) == ("MXN", ["afilador de cuchillos"])


def test_console_2026_unwraps_excel_text_ids():
    file_bytes = _csv_bytes(_global_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")
    mxn_key = search_term_file.accounts[1].key
    first = search_term_file.source_for(mxn_key, file_name="search_term.csv",
                                        file_bytes_digest=_digest(file_bytes)).frame.iloc[0]
    assert mxn_key.startswith("amzn1.ads-account.")
    assert (first["_campaign_id"], first["_ad_group_id"]) == ("171234567890999", "87966052050000")


def _south_source(file_bytes: bytes | None = None):
    file_bytes = file_bytes or _csv_bytes(_two_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")
    return search_term_file.source_for(SOUTH_ACCOUNT_ID, file_name="search_term.csv",
                                       file_bytes_digest=_digest(file_bytes))


def test_console_2026_maps_to_canonical_columns_with_hidden_ids_last():
    assert list(_south_source().frame.columns) == console_columns(7) + ["_campaign_id", "_ad_group_id"]


def test_console_2026_canonical_frame_is_detected_by_m2():
    detected = _detect_cols(_south_source().frame)
    assert detected == EXPECTED_2026_DETECTION
    assert detected["spend"] == "Spend"
    assert detected["ad_group"] == "Ad Group Name"


def test_console_2026_raw_file_would_break_m2_detection():
    raw = pd.read_csv(io.BytesIO(_csv_bytes(_two_account_rows())), encoding="utf-8-sig")
    detected = _detect_cols(raw)
    assert detected["spend"] is None
    assert detected["ad_group"] == "Ad group ID"


def test_console_2026_row_values_and_computed_ratios():
    first = _south_source().frame.iloc[0]
    assert first["Customer Search Term"] == "botella termica 1l"
    assert first["Campaign Name"] == "Campaña Marca Demo Sur"
    assert first["Ad Group Name"] == "Grupo Marca Demo Sur"
    assert first["Portfolio name"] == "Portfolio Marca Demo Sur"
    assert (first["Match Type"], first["Targeting"]) == ("", "")
    assert (first["Impressions"], first["Clicks"], first["Spend"]) == (1600, 40, 30.0)
    assert (first["7 Day Total Sales"], first["7 Day Total Orders (#)"], first["7 Day Total Units (#)"]) == (120.0, 3, 4)
    assert first["Click-Thru Rate (CTR)"] == 2.5
    assert first["Cost Per Click (CPC)"] == 0.75
    assert first["7 Day Conversion Rate"] == 7.5
    assert first["Total Advertising Cost of Sales (ACoS)"] == 25.0


def test_console_2026_zero_denominators_and_blank_cells_become_zero():
    frame = _south_source().frame
    no_traffic, no_sales = frame.iloc[1], frame.iloc[2]
    assert no_traffic["7 Day Total Units (#)"] == 0
    assert (no_traffic["Click-Thru Rate (CTR)"], no_traffic["Cost Per Click (CPC)"],
            no_traffic["7 Day Conversion Rate"], no_traffic["Total Advertising Cost of Sales (ACoS)"]) == (0, 0, 0, 0)
    assert no_sales["Total Advertising Cost of Sales (ACoS)"] == 0
    assert no_sales["Cost Per Click (CPC)"] == 0.47


def test_console_2026_keeps_long_ids_as_exact_text():
    first = _south_source().frame.iloc[0]
    assert first["_campaign_id"] == SOUTH_CAMPAIGN_ID
    assert first["_ad_group_id"] == "391234567890123457"


def test_console_2026_source_metadata():
    file_bytes = _csv_bytes(_two_account_rows())
    source = _south_source(file_bytes)
    assert (source.source, source.currency_code, source.bulk_ready) == (SOURCE_FILE, "MXN", False)
    assert (source.attribution_days, source.profile_id) == (7, "")
    assert source.label == "Marca Demo Sur · search_term.csv"
    assert source.signature == f"{_digest(file_bytes)[:16]}:{SOUTH_ACCOUNT_ID}"


def test_console_2026_account_frames_hold_only_their_rows():
    file_bytes = _csv_bytes(_two_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")
    north = search_term_file.source_for(NORTH_ACCOUNT_ID, file_name="search_term.csv",
                                        file_bytes_digest=_digest(file_bytes))
    assert list(north.frame["Customer Search Term"]) == ["vaso infantil", "plato bambu"]
    assert list(north.frame.index) == [0, 1]
    assert north.currency_code == "USD"


def test_source_for_unknown_account_raises_key_error():
    file_bytes = _csv_bytes(_two_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")
    with pytest.raises(KeyError, match="no-existe"):
        search_term_file.source_for("no-existe", file_name="search_term.csv", file_bytes_digest=_digest(file_bytes))


def test_source_for_returns_an_independent_frame_each_time():
    file_bytes = _csv_bytes(_two_account_rows())
    search_term_file = read_search_term_file(file_bytes, "search_term.csv")
    first = search_term_file.source_for(SOUTH_ACCOUNT_ID, file_name="search_term.csv",
                                        file_bytes_digest=_digest(file_bytes))
    first.frame["_spend"] = 0
    second = search_term_file.source_for(SOUTH_ACCOUNT_ID, file_name="search_term.csv",
                                         file_bytes_digest=_digest(file_bytes))
    assert "_spend" not in second.frame.columns


def test_console_2026_without_account_id_column_is_one_account():
    headers = [header for header in CONSOLE_2026_HEADERS
               if header not in ("Advertiser account ID", "Advertiser account name")]
    rows = [row for row in _two_account_rows() if row["Budget currency"] == "MXN"]
    search_term_file = read_search_term_file(_csv_bytes(rows, headers), "una_cuenta.csv")
    assert search_term_file.format == FORMAT_CONSOLE_2026
    assert search_term_file.accounts == (FileAccount(ALL_ACCOUNTS_KEY, "una_cuenta.csv", "MXN", 3),)


def test_legacy_currency_cell_with_markup_becomes_unknown_currency():
    rows = [_legacy_row("botella termica", "<img src=x onerror=alert(1)>", "MX", impressions=900, clicks=12,
                        spend=48.5, sales=310.0, orders=2)]
    search_term_file = read_search_term_file(_legacy_xlsx(rows), "str_tercero.xlsx")

    assert [account.currency_code for account in search_term_file.accounts] == [""]


def test_legacy_file_splits_only_by_valid_currency_codes():
    rows = [
        _legacy_row("water bottle", "usd", "US", impressions=800, clicks=10, spend=12.0, sales=60.0, orders=2),
        _legacy_row("gourde isotherme", "CA$", "CA", impressions=300, clicks=5, spend=6.5, sales=0.0, orders=0),
    ]
    search_term_file = read_search_term_file(_legacy_xlsx(rows), "str_mixto.xlsx")

    assert search_term_file.accounts == (FileAccount(ALL_ACCOUNTS_KEY, "str_mixto.xlsx", "USD", 2),)


@pytest.mark.parametrize("budget_currency, expected", [("MX$", ""), ("<b>USD", ""), ("mxn", "MXN")])
def test_console_2026_budget_currency_must_be_three_letters(budget_currency, expected):
    rows = [{**row, "Budget currency": budget_currency} for row in _two_account_rows()]
    search_term_file = read_search_term_file(_csv_bytes(rows), "search_term.csv")

    assert {account.currency_code for account in search_term_file.accounts} == {expected}


def test_console_2026_layout_in_xlsx_is_also_mapped():
    file_bytes = _xlsx_bytes(pd.DataFrame(_two_account_rows()).reindex(columns=CONSOLE_2026_HEADERS))
    search_term_file = read_search_term_file(file_bytes, "search_term.xlsx")
    source = search_term_file.source_for(SOUTH_ACCOUNT_ID, file_name="search_term.xlsx",
                                         file_bytes_digest=_digest(file_bytes))
    assert search_term_file.format == FORMAT_CONSOLE_2026
    assert [account.currency_code for account in search_term_file.accounts] == ["USD", "MXN"]
    assert source.frame.iloc[0]["Total Advertising Cost of Sales (ACoS)"] == 25.0


# Unknown and unreadable files

def test_unknown_format_returns_frame_as_is_without_currency():
    file_bytes = "Fecha,Producto,Monto\n2026-08-18,Termo,12.5\n2026-08-19,Vaso,7\n".encode("utf-8")
    search_term_file = read_search_term_file(file_bytes, "otro_reporte.csv")
    source = search_term_file.source_for(ALL_ACCOUNTS_KEY, file_name="otro_reporte.csv",
                                         file_bytes_digest=_digest(file_bytes))

    assert search_term_file.format == FORMAT_UNKNOWN
    assert search_term_file.accounts == (FileAccount(ALL_ACCOUNTS_KEY, "otro_reporte.csv", "", 2),)
    pd.testing.assert_frame_equal(source.frame, pd.read_csv(io.BytesIO(file_bytes)))
    assert source.currency_code == ""


@pytest.mark.parametrize("file_bytes, file_name", [
    (b"esto no es un excel", "roto.xlsx"),
    (b"PK\x03\x04basura", "roto.xlsx"),
    (b"", "vacio.csv"),
])
def test_unreadable_file_raises_search_term_file_error(file_bytes, file_name):
    with pytest.raises(SearchTermFileError, match=file_name) as raised:
        read_search_term_file(file_bytes, file_name)
    assert isinstance(raised.value, ValueError)
