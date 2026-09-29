"""A Campaign CSV uploaded by hand, read into the campaign totals the synced reads give: one row per campaign."""
import hashlib
import io
import math
import zipfile

import pandas as pd
import pytest

from core.amazon_ads.campaign_file import CAMPAIGN_COLUMNS, CampaignFileError, read_campaign_file
from core.amazon_ads.export_amounts import clean_money, known_money

HEADER_2026 = "Campaign name,Campaign ID,State,Type,Portfolio name,Impressions,Clicks,Total cost,Purchases,Sales"


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


def _xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def _row(campaigns: pd.DataFrame, name: str) -> dict:
    return campaigns[campaigns["campaign"] == name].iloc[0].to_dict()


def test_the_2026_export_becomes_one_row_per_campaign_in_the_columns_of_the_synced_totals():
    campaign_file = read_campaign_file(_csv(
        HEADER_2026,
        "Alpha,111,ENABLED,Sponsored Products,Kids,1000,50,$120.50,4,$480.00",
        "Beta,222,ENABLED,Sponsored Brands,,400,10,$30.00,1,$90.00",
        "Gamma,333,ENABLED,Sponsored Display,Kids,200,5,$10.00,0,$0.00",
    ), "campaigns.csv")

    campaigns = campaign_file.campaigns
    assert list(campaigns.columns) == CAMPAIGN_COLUMNS
    assert _row(campaigns, "Alpha") | {"ntb_orders": None, "ntb_sales": None} == {
        "product": "SP", "campaign_id": "111", "campaign": "Alpha", "portfolio": "Kids", "impressions": 1000,
        "clicks": 50, "spend": 120.5, "sales": 480.0, "orders": 4, "sales_clicks": 480.0, "orders_clicks": 4,
        "ntb_orders": None, "ntb_sales": None}
    assert _row(campaigns, "Beta")["portfolio"] == "" and _row(campaigns, "Beta")["product"] == "SB"
    assert campaign_file.products == ("SP", "SB", "SD")
    assert (campaign_file.ad_spend, campaign_file.ad_sales, campaign_file.campaign_count) == (160.5, 570.0, 3)
    assert campaign_file.has_portfolio and campaign_file.has_product and not campaign_file.has_new_to_brand
    assert campaign_file.missing_counts == ()


def test_a_legacy_export_is_read_by_its_own_names_and_what_it_lacks_stays_unknown():
    campaign_file = read_campaign_file(_csv(
        "Campaign Name,Status,Impressions,Clicks,Spend,Orders,Sales",
        "Alpha,enabled,1000,50,120.50,4,480",
    ), "legacy.csv")

    row = _row(campaign_file.campaigns, "Alpha")
    assert (row["spend"], row["orders"], row["sales"]) == (120.5, 4, 480.0)
    assert (row["product"], row["campaign_id"], row["portfolio"]) == ("", "", "")
    assert math.isnan(row["sales_clicks"]) and math.isnan(row["ntb_orders"])
    assert campaign_file.products == ()
    assert not (campaign_file.has_portfolio or campaign_file.has_product or campaign_file.has_new_to_brand)


def test_cost_and_portfolio_are_legacy_names_too():
    campaign_file = read_campaign_file(_csv("Campaign,Portfolio,Cost,Sales", "Alpha,Kids,12.00,40.00"), "old.csv")

    row = _row(campaign_file.campaigns, "Alpha")
    assert (row["spend"], row["portfolio"]) == (12.0, "Kids") and campaign_file.has_portfolio
    assert campaign_file.missing_counts == ("impressions", "clicks", "orders")
    assert (row["impressions"], row["clicks"], row["orders"]) == (0, 0, 0)


@pytest.mark.parametrize("prefix, currency", [("MX$", "MXN"), ("CA$", "CAD"), ("£", "GBP"), ("€", "EUR")])
def test_amounts_with_a_currency_symbol_are_read_and_the_one_symbol_they_share_names_the_currency(prefix, currency):
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Total cost,Sales",
        f'Alpha,"{prefix}5,796.55","{prefix}25,619.00"',
        f"Beta,{prefix}3.45,{prefix}0.00",
    ), "campaigns.csv")

    assert campaign_file.ad_spend == pytest.approx(5800.0)
    assert campaign_file.ad_sales == pytest.approx(25619.0)
    assert campaign_file.currency_code == currency


@pytest.mark.parametrize("spend, sales", [
    ("$10.00", "$40.00"),
    ("10.00", "40.00"),
    ("MX$10.00", "40.00"),
], ids=["bare-dollar", "no-symbol", "symbol-on-some-cells"])
def test_the_currency_stays_unknown_unless_every_amount_shares_one_unambiguous_symbol(spend, sales):
    campaign_file = read_campaign_file(_csv("Campaign name,Total cost,Sales", f"Alpha,{spend},{sales}"), "c.csv")

    assert campaign_file.currency_code == ""
    assert (campaign_file.ad_spend, campaign_file.ad_sales) == (10.0, 40.0)


def test_a_currency_column_names_the_currency_over_the_symbols():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Currency,Total cost,Sales",
        "Alpha,mxn,$10.00,$40.00",
        "Beta,MXN,$5.00,$0.00",
    ), "campaigns.csv")

    assert campaign_file.currency_code == "MXN"


@pytest.mark.parametrize("header, alpha, beta", [
    ("Campaign name,Budget currency,Total cost,Sales", "Alpha,MXN,10.00,40.00", "Beta,USD,5.00,0.00"),
    ("Campaign name,Total cost,Sales", "Alpha,MX$10.00,MX$40.00", "Beta,$5.00,$0.00"),
    ("Campaign name,Total cost,Sales", "Alpha,MX$10.00,MX$40.00", "Beta,€5.00,€0.00"),
], ids=["currency-column", "mx-and-bare-dollar", "mx-and-euro"])
def test_a_file_in_two_currencies_is_refused_instead_of_summed(header, alpha, beta):
    with pytest.raises(CampaignFileError, match="más de una moneda") as refused:
        read_campaign_file(_csv(header, alpha, beta), "campaigns.csv")

    assert "«campaigns.csv»" in str(refused.value) and "un solo marketplace" in str(refused.value)


def test_sales_are_never_taken_from_the_new_to_brand_or_click_only_columns():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Type,New-to-brand sales,Sales (clicks),NTB sales,Total cost,Sales",
        "Alpha,Sponsored Brands,70.00,60.00,70.00,10.00,100.00",
    ), "campaigns.csv")

    row = _row(campaign_file.campaigns, "Alpha")
    assert (row["sales"], row["sales_clicks"], row["ntb_sales"]) == (100.0, 60.0, 70.0)


def test_a_file_whose_only_sales_are_new_to_brand_or_click_only_is_missing_the_sales_column():
    with pytest.raises(CampaignFileError, match="Sales"):
        read_campaign_file(_csv("Campaign name,Total cost,New-to-brand sales,Sales (clicks)", "Alpha,10,5,6"),
                           "campaigns.csv")


@pytest.mark.parametrize("written, product", [
    ("Sponsored Products", "SP"), ("sponsored brands", "SB"), ("Sponsored Display", "SD"), ("SB", "SB"),
    ("Something else", ""), ("", ""),
])
def test_the_type_column_names_the_product(written, product):
    campaign_file = read_campaign_file(_csv("Campaign name,Type,Total cost,Sales", f"Alpha,{written},10,40"), "c.csv")

    assert _row(campaign_file.campaigns, "Alpha")["product"] == product


def test_new_to_brand_figures_land_only_on_brands_and_display_rows():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Type,Total cost,Purchases,Sales,New-to-brand purchases,New-to-brand sales",
        "Alpha,Sponsored Products,10,2,40,1,20",
        "Beta,Sponsored Brands,5,3,30,2,25",
        "Gamma,Sponsored Display,5,1,10,1,10",
    ), "campaigns.csv")

    campaigns = campaign_file.campaigns
    assert math.isnan(_row(campaigns, "Alpha")["ntb_orders"]) and math.isnan(_row(campaigns, "Alpha")["ntb_sales"])
    assert (_row(campaigns, "Beta")["ntb_orders"], _row(campaigns, "Beta")["ntb_sales"]) == (2, 25.0)
    assert (_row(campaigns, "Gamma")["ntb_orders"], _row(campaigns, "Gamma")["ntb_sales"]) == (1, 10.0)
    assert campaign_file.has_new_to_brand


@pytest.mark.parametrize("cell", ["-", ""], ids=["dash", "blank"])
def test_new_to_brand_and_click_only_cells_without_a_number_stay_unknown_instead_of_zero(cell):
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Type,Total cost,Purchases,Sales,Purchases (clicks),Sales (clicks),New-to-brand purchases,"
        "New-to-brand sales",
        f"Beta,Sponsored Brands,5,3,30,{cell},{cell},{cell},{cell}",
        "Gamma,Sponsored Display,5,1,10,0,$0.00,0,$0.00",
    ), "campaigns.csv")

    beta, gamma = _row(campaign_file.campaigns, "Beta"), _row(campaign_file.campaigns, "Gamma")
    assert all(math.isnan(beta[field]) for field in ("orders_clicks", "sales_clicks", "ntb_orders", "ntb_sales"))
    assert (gamma["orders_clicks"], gamma["sales_clicks"], gamma["ntb_orders"], gamma["ntb_sales"]) == (0, 0, 0, 0)


def test_new_to_brand_columns_without_the_type_cannot_be_placed_and_stay_unknown():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Total cost,Sales,NTB orders,NTB sales", "Beta,5,30,2,25"), "campaigns.csv")

    assert math.isnan(_row(campaign_file.campaigns, "Beta")["ntb_orders"])
    assert not campaign_file.has_new_to_brand


def test_a_campaign_on_several_rows_is_summed_into_one():
    campaign_file = read_campaign_file(_csv(
        "Date,Campaign name,Campaign ID,Type,Impressions,Clicks,Total cost,Purchases,Sales",
        "2026-08-03,Alpha,111,Sponsored Products,100,5,10.00,1,40.00",
        "2026-08-04,Alpha,111,Sponsored Products,200,7,12.50,2,55.00",
        "2026-08-03,Beta,222,Sponsored Brands,50,1,2.00,0,0.00",
    ), "daily.csv")

    assert campaign_file.campaign_count == 2
    row = _row(campaign_file.campaigns, "Alpha")
    assert (row["impressions"], row["clicks"], row["spend"], row["orders"], row["sales"]) == (300, 12, 22.5, 3, 95.0)


def test_ids_that_excel_rewrote_in_scientific_notation_do_not_merge_different_campaigns():
    campaign_file = read_campaign_file(_csv(
        HEADER_2026,
        "Brand Exact,1.23457E+14,ENABLED,Sponsored Products,,1000,50,$100.00,4,$400.00",
        "Brand Exact,1.23457E+14,ENABLED,Sponsored Products,,500,20,$50.00,2,$120.00",
        "Generic Broad,1.23457E+14,ENABLED,Sponsored Products,,2000,60,$300.00,2,$200.00",
        "Brand Video,1.23457E+14,ENABLED,Sponsored Brands,,400,10,$50.00,1,$150.00",
    ), "campaigns.csv")

    assert sorted(campaign_file.campaigns["campaign"]) == ["Brand Exact", "Brand Video", "Generic Broad"]
    assert campaign_file.products == ("SP", "SB")
    assert (_row(campaign_file.campaigns, "Brand Exact")["spend"], _row(campaign_file.campaigns, "Generic Broad")
            ["spend"]) == (150.0, 300.0)


def test_campaigns_that_share_a_name_across_products_stay_apart_without_ids():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Type,Total cost,Sales",
        "Brand,Sponsored Products,10,40",
        "Brand,Sponsored Brands,5,20",
    ), "campaigns.csv")

    assert sorted(campaign_file.campaigns["product"]) == ["SB", "SP"]


def test_a_campaign_that_served_nothing_is_left_out():
    campaign_file = read_campaign_file(_csv(
        HEADER_2026,
        "Alpha,111,ENABLED,Sponsored Products,,100,5,$10.00,1,$40.00",
        "Idle,222,ENABLED,Sponsored Products,,0,0,$0.00,0,$0.00",
    ), "campaigns.csv")

    assert list(campaign_file.campaigns["campaign"]) == ["Alpha"]


def test_paused_and_archived_campaigns_still_count_what_they_spent_in_the_range():
    campaign_file = read_campaign_file(_csv(
        HEADER_2026,
        "Alpha,111,ENABLED,Sponsored Products,,100,5,$10.00,1,$40.00",
        "Paused later,222,PAUSED,Sponsored Products,,100,5,$7.00,1,$20.00",
        "Archived,333,ARCHIVED,Sponsored Brands,,100,5,$3.00,0,$0.00",
    ), "campaigns.csv")

    assert (campaign_file.ad_spend, campaign_file.ad_sales, campaign_file.campaign_count) == (20.0, 60.0, 3)


def test_a_file_without_activity_reads_as_no_campaigns_not_as_an_error():
    campaign_file = read_campaign_file(_csv("Campaign name,Total cost,Sales", "Idle,$0.00,$0.00"), "campaigns.csv")

    assert list(campaign_file.campaigns.columns) == CAMPAIGN_COLUMNS and campaign_file.campaigns.empty
    assert (campaign_file.ad_spend, campaign_file.ad_sales, campaign_file.products) == (0.0, 0.0, ())


def test_a_row_without_a_campaign_name_or_id_is_not_a_campaign_and_is_not_summed():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Campaign ID,Total cost,Sales",
        "Alpha,111,10.00,40.00",
        ",222,5.00,20.00",
        ",,15.00,60.00",
    ), "campaigns.csv")

    assert sorted(campaign_file.campaigns["campaign"]) == ["Alpha", "Campaña 222"]
    assert campaign_file.ad_spend == 15.0


def test_counts_with_thousands_separators_are_read_whole():
    campaign_file = read_campaign_file(_csv(
        "Campaign name,Impressions,Clicks,Total cost,Sales", 'Alpha,"12,345","1,002",10.00,40.00'), "c.csv")

    row = _row(campaign_file.campaigns, "Alpha")
    assert (row["impressions"], row["clicks"]) == (12345, 1002)


def test_a_byte_order_mark_and_spaces_around_the_headers_do_not_hide_them():
    campaign_file = read_campaign_file(b"\xef\xbb\xbf Campaign name ,  Total cost , Sales \nAlpha,10.00,40.00\n",
                                       "campaigns.csv")

    assert (campaign_file.ad_spend, campaign_file.ad_sales) == (10.0, 40.0)


def test_the_campaign_export_as_xlsx_is_read_from_its_first_sheet():
    frame = pd.DataFrame({"Campaign name": ["Alpha"], "Campaign ID": ["111"], "Type": ["Sponsored Products"],
                          "Total cost": [10.0], "Sales": [40.0]})

    campaign_file = read_campaign_file(_xlsx({"Campaigns": frame}), "campaigns.xlsx")

    assert (campaign_file.ad_spend, campaign_file.ad_sales, campaign_file.products) == (10.0, 40.0, ("SP",))


def test_a_bulk_file_is_refused_because_its_rows_repeat_the_metrics_at_several_levels():
    sheet = pd.DataFrame({"Entity": ["Campaign", "Ad Group"], "Campaign Name": ["Alpha", "Alpha"],
                          "Spend": [10.0, 10.0], "Sales": [40.0, 40.0]})

    with pytest.raises(CampaignFileError, match="Bulk File") as refused:
        read_campaign_file(_xlsx({"Portfolios": pd.DataFrame(), "Sponsored Products Campaigns": sheet}), "bulk.xlsx")

    assert "Campaign CSV" in str(refused.value)


def _bulk_rows(product: str) -> pd.DataFrame:
    """A campaign with its ad group and target: each row repeats the campaign's spend and sales."""
    return pd.DataFrame({"Product": [product] * 3, "Entity": ["Campaign", "Ad Group", "Product Targeting"],
                         "Campaign ID": ["111"] * 3, "Campaign Name": ["Alpha", "", ""], "Spend": [50.0] * 3,
                         "Sales": [200.0] * 3, "Orders": [4] * 3, "Impressions": [900] * 3, "Clicks": [30] * 3})


@pytest.mark.parametrize("sheets", [
    {"Sponsored Brands Campaigns": _bulk_rows("Sponsored Brands")},
    {"Sponsored Display Campaigns": _bulk_rows("Sponsored Display")},
    {"SB Multi Ad Group Campaigns": _bulk_rows("Sponsored Brands")},
    {"Portfolios": pd.DataFrame({"Portfolio ID": ["9"], "Portfolio Name": ["Kids"]}),
     "Sponsored Brands Campaigns": _bulk_rows("Sponsored Brands")},
    {"Sheet1": _bulk_rows("Sponsored Products")},
], ids=["brands-only", "display-only", "brands-multi-ad-group", "portfolios-first", "entity-column"])
def test_a_bulk_file_without_sponsored_products_is_refused_too(sheets):
    with pytest.raises(CampaignFileError, match="Bulk File"):
        read_campaign_file(_xlsx(sheets), "bulk.xlsx")


def test_a_bulk_sheet_saved_as_csv_is_refused_by_its_entity_column():
    content = _bulk_rows("Sponsored Products").to_csv(index=False).encode("utf-8")

    with pytest.raises(CampaignFileError, match="Bulk File"):
        read_campaign_file(content, "Sponsored Products Campaigns.csv")


@pytest.mark.parametrize("header, missing", [
    ("State,Total cost,Sales", "nombre de la campaña"),
    ("Campaign name,Clicks,Sales", "Total cost"),
    ("Campaign name,Total cost,Purchases", "Sales"),
], ids=["no-campaign", "no-spend", "no-sales"])
def test_a_file_without_the_campaign_the_spend_or_the_sales_is_refused_and_says_which(header, missing):
    with pytest.raises(CampaignFileError, match=missing):
        read_campaign_file(_csv(header, "a,1,2"), "campaigns.csv")


def _zip_that_is_not_a_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


# An encrypted or password-protected .xlsx, or a renamed .xls, is an OLE2 compound file.
OLE2_BYTES = bytes.fromhex("D0CF11E0A1B11AE1") + bytes(504)


@pytest.mark.parametrize("content, name", [
    (b"not a workbook", "campaigns.xlsx"), (b"", "campaigns.csv"), (OLE2_BYTES, "campaigns.xlsx"),
    (_zip_that_is_not_a_workbook(), "campaigns.xlsx"),
], ids=["text-as-xlsx", "empty-csv", "ole2-as-xlsx", "docx-as-xlsx"])
def test_bytes_that_are_not_a_table_are_refused_with_a_message(content, name):
    with pytest.raises(CampaignFileError, match=name):
        read_campaign_file(content, name)


def test_the_file_keeps_its_name_and_a_digest_of_its_bytes():
    content = _csv("Campaign name,Total cost,Sales", "Alpha,10,40")

    campaign_file = read_campaign_file(content, "campaigns.csv")

    assert campaign_file.name == "campaigns.csv"
    assert campaign_file.digest == hashlib.sha256(content).hexdigest()[:16]


@pytest.mark.parametrize("written, amount", [("$1,234.50", 1234.5), ("MX$5,796.55", 5796.55), ("-€3.10", -3.1),
                                             ("", 0.0), ("—", 0.0), (12.5, 12.5)])
def test_the_money_cleaner_keeps_only_the_number(written, amount):
    assert clean_money(pd.Series([written])).iloc[0] == pytest.approx(amount)


@pytest.mark.parametrize("written", ["", "-", "—", "n/a"])
def test_a_cell_without_a_number_is_an_unknown_amount_not_a_zero(written):
    assert math.isnan(known_money(pd.Series([written])).iloc[0])


@pytest.mark.parametrize("written, amount", [("$0.00", 0.0), ("MX$5,796.55", 5796.55), ("-€3.10", -3.1)])
def test_a_cell_with_a_number_is_a_known_amount(written, amount):
    assert known_money(pd.Series([written])).iloc[0] == pytest.approx(amount)
