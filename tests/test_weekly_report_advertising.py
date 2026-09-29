"""The Weekly Client Report's Advertising sheet from the account's campaign totals over the report's days, or from a
Campaign CSV uploaded by hand."""
from datetime import date, timedelta

import pandas as pd
from openpyxl import load_workbook

from core.amazon_ads.campaign_file import read_campaign_file
from core.amazon_ads.product_provider import NewToBrand
from core.business_report.paid_split import file_split
from core.weekly_report.advertising import TOP_CAMPAIGNS, advertising_summary
from modules.pages import weekly_client_report as wcr
from modules.pages.ad_account_block import AccountAds

COLUMNS = ["product", "campaign_id", "campaign", "portfolio", "spend", "sales", "orders", "clicks", "impressions",
           "sales_clicks", "orders_clicks", "ntb_orders", "ntb_sales"]
NAN = float("nan")
ROWS = [
    ("SP", "1", "Brand exact", "Brand", 120.0, 600.0, 12, 40, 900, 600.0, 12, NAN, NAN),
    ("SP", "2", "Old auto", "", 30.0, 0.0, 0, 12, 400, 0.0, 0, NAN, NAN),
    ("SB", "3", "Video", "Brand", 10.0, 40.0, 2, 8, 1400, 20.0, 1, 1, 20.0),
    ("SD", "4", "Retargeting", "Generic", 40.0, 50.0, 4, 10, 2000, 25.0, 2, 2, 30.0),
]
SOURCE = "Fuente: Luna Kids · US · 03–16 ago 2026 · 14 de 14 días del BR con datos de ads · SP · SB · SD."
# Campaign Manager's export without portfolio or new-to-brand columns: 150 spent and 600 sold.
CAMPAIGN_CSV = ("Campaign name,Type,Impressions,Clicks,Total cost,Purchases,Sales\n"
                "Brand exact,Sponsored Products,900,40,$120.00,12,$600.00\n"
                "Video,Sponsored Brands,1400,8,$30.00,0,$0.00\n").encode("utf-8")
UNTYPED_CSV = ("Campaign Name,Portfolio,Spend,Orders,Sales\n"
               "Brand exact,Brand,MX$120.00,12,MX$600.00\n").encode("utf-8")
# Campaign Manager lets the AM leave columns out: without the counts, 250 spent and 1,250 sold.
WITHOUT_COUNTS_CSV = ("Campaign name,Type,Total cost,Sales\n"
                      "Kids SP,Sponsored Products,$200.00,$1000.00\n"
                      "Kids SB,Sponsored Brands,$50.00,$250.00\n").encode("utf-8")
WITHOUT_CLICKS_CSV = "Campaign name,Impressions,Total cost,Sales\nKids SP,5000,$200.00,$1000.00\n".encode("utf-8")
# The file names each campaign's type, but none of them ran in the export's range.
IDLE_CSV = ("Campaign name,Type,Impressions,Clicks,Total cost,Purchases,Sales\n"
            "Kids SP,Sponsored Products,0,0,$0.00,0,$0.00\n").encode("utf-8")
# Monday 3 to Sunday 16 August 2026.
REPORT_DAYS = [date(2026, 8, 3) + timedelta(days=offset) for offset in range(14)]


def _frame(rows=ROWS) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def test_the_totals_add_every_product_and_leave_acos_unknown_without_sales():
    summary = advertising_summary(_frame())

    assert summary.totals == {"Impressions": 4700.0, "Clicks": 70.0, "Spend": 200.0, "Sales": 690.0, "Orders": 18.0,
                              "CTR": 1.49, "CPC": 2.86, "ACoS": 28.99}
    assert summary.campaign_count == 4
    assert advertising_summary(_frame([ROWS[1]])).totals["ACoS"] is None


def test_the_top_campaigns_come_most_spend_first_and_a_campaign_without_sales_has_no_acos():
    summary = advertising_summary(_frame())

    assert [(campaign["Campaign"], campaign["ACoS"]) for campaign in summary.campaigns] == [
        ("Brand exact", 20.0), ("Retargeting", 80.0), ("Old auto", None), ("Video", 25.0)]
    assert summary.campaigns[0] == {"Campaign": "Brand exact", "Product": "SP", "Impressions": 900, "Clicks": 40,
                                    "CTR": 4.44, "Spend": 120.0, "Sales": 600.0, "ACoS": 20.0, "Orders": 12}


def test_the_alarms_are_the_campaigns_over_60_and_the_ones_that_spent_without_selling():
    summary = advertising_summary(_frame())

    assert [campaign["Campaign"] for campaign in summary.alarms] == ["Retargeting", "Old auto"]


def test_only_the_top_campaigns_are_listed_but_every_campaign_counts():
    rows = [("SP", str(index), f"Campaign {index}", "", float(index), 10.0, 1, 1, 10, 10.0, 1, NAN, NAN)
            for index in range(1, TOP_CAMPAIGNS + 6)]

    summary = advertising_summary(_frame(rows))

    assert len(summary.campaigns) == TOP_CAMPAIGNS and summary.campaign_count == TOP_CAMPAIGNS + 5
    assert summary.campaigns[0]["Campaign"] == f"Campaign {TOP_CAMPAIGNS + 5}"


def test_the_portfolios_add_their_campaigns_and_name_the_ones_without_a_portfolio():
    summary = advertising_summary(_frame())

    assert summary.portfolios == [{"Portfolio": "Brand", "Spend": 130.0, "Sales": 640.0, "ACoS": 20.3},
                                  {"Portfolio": "Generic", "Spend": 40.0, "Sales": 50.0, "ACoS": 80.0},
                                  {"Portfolio": "(Sin Portfolio)", "Spend": 30.0, "Sales": 0.0, "ACoS": None}]


def test_the_products_with_activity_come_in_their_usual_order_and_stay_unnamed_when_the_source_does_not_say_them():
    assert advertising_summary(_frame()).products == ("SP", "SB", "SD")
    assert advertising_summary(_frame([("",) + row[1:] for row in ROWS])).products == ()


def test_a_source_without_portfolios_leaves_them_unknown_instead_of_one_without_portfolio():
    assert advertising_summary(_frame(), with_portfolios=False).portfolios is None


def test_new_to_brand_adds_brands_and_display_over_their_own_orders():
    summary = advertising_summary(_frame())

    assert summary.new_to_brand == NewToBrand(3, 50.0)
    assert summary.new_to_brand_share == 50.0


def test_new_to_brand_is_unknown_when_a_display_day_was_never_measured_or_nothing_credits_it():
    unmeasured = [row if row[0] != "SD" else row[:11] + (NAN, NAN) for row in ROWS]

    assert advertising_summary(_frame(unmeasured)).new_to_brand is None
    assert advertising_summary(_frame(ROWS[:2])).new_to_brand is None


def _file_ads(content: bytes = CAMPAIGN_CSV, *, with_daily_report: bool = True):
    campaign_file = read_campaign_file(content, "campaigns.csv")
    history = pd.DataFrame({"_date": pd.to_datetime(REPORT_DAYS), "_sales": [450.0] * len(REPORT_DAYS)})
    ads = AccountAds(currency_code=campaign_file.currency_code, campaigns=campaign_file.campaigns,
                     split=file_split(history, campaign_file) if with_daily_report else None,
                     source_file=campaign_file.name, file_digest=campaign_file.digest)
    return ads, advertising_summary(campaign_file.campaigns, with_portfolios=campaign_file.has_portfolio,
                                    unknown_counts=campaign_file.missing_counts)


def _advertising_sheet(**kwargs):
    buf = wcr._build_weekly_excel({}, {}, {}, {}, "Luna", kwargs.pop("lang", "es"), None, **kwargs)
    return load_workbook(buf)["\U0001f4e3 Advertising"]


def test_the_sheet_shows_the_account_figures_in_its_currency_with_their_source():
    sheet = _advertising_sheet(advertising=advertising_summary(_frame()), ads_currency="USD", ads_source=SOURCE)

    assert sheet["A1"].value == "Luna — Advertising Overview"
    assert sheet["A2"].value == SOURCE
    assert [cell.value for cell in sheet[4]][:8] == ["4,700", "70", "1.49%", "$2.86", "$200.00", "$690.00", "29.0%",
                                                     "18"]
    assert sheet["A5"].value == ("New-to-brand (SB y SD): 3 órdenes (50.0%) · ventas $50.00  |  Vistas de la página "
                                 "de detalle: — (no se sincronizan)")
    rows = {row[0].value: [cell.value for cell in row] for row in sheet.iter_rows(min_row=7) if row[0].value}
    assert rows["Brand exact"] == ["Brand exact", "SP", 900, 40, 4.44, 120.0, 600.0, 20.0, 12]
    assert rows["Old auto"][7] == "—"
    assert rows["  Old auto — sin ventas | Spend $30.00 | Sales $0.00"][0] is not None
    assert rows["(Sin Portfolio)"][:4] == ["(Sin Portfolio)", 30.0, 0.0, "—"]
    brand_row = next(row for row in sheet.iter_rows(min_row=7) if row[0].value == "Brand exact")
    assert brand_row[5].number_format == '"$"#,##0.00'


def test_new_to_brand_that_is_not_known_reads_as_a_dash():
    sheet = _advertising_sheet(advertising=advertising_summary(_frame(ROWS[:2])), ads_currency="MXN",
                               ads_source=SOURCE, lang="en")

    assert sheet["A5"].value == "New-to-brand (SB and SD): —  |  Detail page views: — (not synced)"
    assert sheet["E4"].value == "MX$150.00"


def test_without_the_account_the_sheet_says_why():
    sheet = _advertising_sheet(ads_note="no se eligió la cuenta de Amazon Ads del BR")

    assert sheet["A1"].value == "⚠️ Sin datos de Amazon Ads: no se eligió la cuenta de Amazon Ads del BR."


def test_the_source_line_of_a_campaign_csv_names_the_file_and_what_it_does_not_say():
    ads, advertising = _file_ads()

    assert wcr._ads_source(ads, advertising, "es") == (
        "Fuente: Campaign CSV subido a mano (campaigns.csv) · SP · SB. El archivo no dice qué días cubre ni con qué "
        "atribución se exportó: tiene que estar exportado con los días del BR diario (03–16 ago 2026). Tampoco dice "
        "la moneda.")
    assert wcr._ads_source(ads, advertising, "en") == (
        "Source: Campaign CSV uploaded by hand (campaigns.csv) · SP · SB. The file does not say which days it covers "
        "or which attribution it was exported with: it has to be exported over the daily BR's days (Aug 03–16 2026). "
        "Nor does it say the currency.")


def test_the_source_line_of_a_campaign_csv_without_the_daily_report_or_campaign_types_claims_no_days():
    ads, advertising = _file_ads(UNTYPED_CSV, with_daily_report=False)

    assert wcr._ads_source(ads, advertising, "es") == (
        "Fuente: Campaign CSV subido a mano (campaigns.csv) · sin decir si son SP, SB o SD. El archivo no dice qué "
        "días cubre ni con qué atribución se exportó: sus cifras son las del rango con que se exportó.")


def test_a_campaign_csv_sheet_leaves_new_to_brand_views_and_portfolios_out_when_the_file_lacks_them():
    ads, advertising = _file_ads()

    sheet = _advertising_sheet(advertising=advertising, ads_currency=ads.currency_code, ads_source="Fuente",
                               ads_from_file=True)

    assert sheet["A5"].value == ("New-to-brand (SB y SD): —  |  Vistas de la página de detalle: — (no se leen del "
                                 "Campaign CSV)")
    assert [cell.value for cell in sheet[4]][:8] == ["2,300", "48", "2.09%", "$3.12", "$150.00", "$600.00", "25.0%",
                                                     "12"]
    rows = {row[0].value: [cell.value for cell in row] for row in sheet.iter_rows(min_row=7) if row[0].value}
    assert rows["Brand exact"] == ["Brand exact", "SP", 900, 40, 4.44, 120.0, 600.0, 20.0, 12]
    assert "PORTFOLIOS" not in rows


def test_a_campaign_csv_with_portfolios_lists_them_in_its_currency():
    ads, advertising = _file_ads(UNTYPED_CSV)

    sheet = _advertising_sheet(advertising=advertising, ads_currency=ads.currency_code, ads_source="Source",
                               ads_from_file=True, lang="en")

    assert sheet["A5"].value == "New-to-brand (SB and SD): —  |  Detail page views: — (not read from the Campaign CSV)"
    assert sheet["E4"].value == "MX$120.00"
    rows = {row[0].value: [cell.value for cell in row] for row in sheet.iter_rows(min_row=7) if row[0].value}
    assert rows["Brand"][:4] == ["Brand", 120.0, 600.0, 20.0]


def test_the_counts_a_campaign_csv_lacks_are_unknown_not_zero():
    _, advertising = _file_ads(WITHOUT_COUNTS_CSV)

    assert advertising.totals == {"Impressions": None, "Clicks": None, "Spend": 250.0, "Sales": 1250.0,
                                  "Orders": None, "CTR": None, "CPC": None, "ACoS": 20.0}
    assert advertising.campaigns[0] == {"Campaign": "Kids SP", "Product": "SP", "Impressions": None, "Clicks": None,
                                        "CTR": None, "Spend": 200.0, "Sales": 1000.0, "ACoS": 20.0, "Orders": None}
    assert advertising.new_to_brand_share is None


def test_impressions_without_clicks_leave_the_click_figures_unknown():
    _, advertising = _file_ads(WITHOUT_CLICKS_CSV)

    totals = advertising.totals
    assert (totals["Impressions"], totals["Clicks"], totals["CTR"], totals["CPC"]) == (5000.0, None, None, None)
    assert (advertising.campaigns[0]["Impressions"], advertising.campaigns[0]["CTR"]) == (5000, None)


def test_the_sheet_shows_the_counts_a_campaign_csv_lacks_as_dashes():
    ads, advertising = _file_ads(WITHOUT_COUNTS_CSV)

    sheet = _advertising_sheet(advertising=advertising, ads_currency=ads.currency_code, ads_source="Fuente",
                               ads_from_file=True)

    assert [cell.value for cell in sheet[4]][:8] == ["—", "—", "—", "—", "$250.00", "$1,250.00", "20.0%", "—"]
    rows = {row[0].value: [cell.value for cell in row] for row in sheet.iter_rows(min_row=7) if row[0].value}
    assert rows["Kids SP"] == ["Kids SP", "SP", "—", "—", "—", 200.0, 1000.0, 20.0, "—"]


def test_the_source_line_of_a_typed_campaign_csv_without_activity_says_none_ran_not_that_it_lacks_the_types():
    ads, advertising = _file_ads(IDLE_CSV)

    assert wcr._ads_source(ads, advertising, "es") == (
        "Fuente: Campaign CSV subido a mano (campaigns.csv) · sin campañas con actividad. El archivo no dice qué días "
        "cubre ni con qué atribución se exportó: tiene que estar exportado con los días del BR diario (03–16 ago 2026). "
        "Tampoco dice la moneda.")
    assert wcr._ads_source(ads, advertising, "en").startswith(
        "Source: Campaign CSV uploaded by hand (campaigns.csv) · no campaigns with activity. ")
