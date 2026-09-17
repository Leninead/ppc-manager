"""Bid Optimizer over the canonical frame: column detection, ASIN origin and the bid math."""
import pandas as pd

from core.search_term_frame import console_columns
from modules.pages.bid_optimizer import (
    ASIN_FROM_CAMPAIGN,
    ASIN_FROM_FILE,
    asins_from_campaigns,
    bid_ai_records,
    bids_by_asin,
    budget_midpoint,
    campaign_placements,
    detect_columns,
    estado_por_cvr,
    resolve_asin_column,
)

ATTRIBUTION_DAYS = 7


def _canonical_frame(rows):
    """A frame shaped like what render_source_picker hands the module (no Advertised ASIN)."""
    frame = pd.DataFrame(rows)
    for column in console_columns(ATTRIBUTION_DAYS):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(ATTRIBUTION_DAYS)]


def _row(campaign="DG - B0CYLMJJJC - SP - KW - EXACT - Core", clicks=100, spend=50.0,
         sales=200.0, orders=10):
    return {"Customer Search Term": "vitamin a cream", "Campaign Name": campaign,
            "Clicks": clicks, "Spend": spend, "7 Day Total Sales": sales,
            "7 Day Total Orders (#)": orders, "Impressions": 1000}


def test_the_canonical_frame_has_no_advertised_asin_column():
    assert not any("advertised asin" in str(column).lower()
                   for column in console_columns(ATTRIBUTION_DAYS))


def test_detect_columns_maps_the_canonical_names():
    cols = detect_columns(_canonical_frame([_row()]))

    assert cols["clicks"] == "Clicks"
    assert cols["spend"] == "Spend"
    assert cols["orders"] == "7 Day Total Orders (#)"
    assert cols["campaign"] == "Campaign Name"
    assert cols["asin"] is None


def test_sales_wins_over_the_acos_column_whose_name_also_says_sales():
    cols = detect_columns(_canonical_frame([_row()]))

    assert cols["sales"] == "7 Day Total Sales"


def test_the_asin_comes_from_the_campaign_name_when_the_frame_has_none():
    frame = _canonical_frame([_row()])

    resolved, col_asin, origin = resolve_asin_column(frame, detect_columns(frame))

    assert col_asin == "_extracted_asin"
    assert origin == ASIN_FROM_CAMPAIGN
    assert list(resolved[col_asin]) == ["B0CYLMJJJC"]


def test_an_advertised_asin_column_wins_over_the_campaign_name():
    frame = _canonical_frame([_row()])
    frame["Advertised ASIN"] = "B0OTHER0001"

    resolved, col_asin, origin = resolve_asin_column(frame, detect_columns(frame))

    assert col_asin == "Advertised ASIN"
    assert origin == ASIN_FROM_FILE
    assert list(resolved[col_asin]) == ["B0OTHER0001"]


def test_a_naming_without_asin_resolves_to_no_column_instead_of_a_wrong_one():
    frame = _canonical_frame([_row(campaign="Campaña sin ASIN - Exact")])

    _, col_asin, origin = resolve_asin_column(frame, detect_columns(frame))

    assert col_asin is None
    assert origin == ""


def test_only_the_campaigns_that_carry_an_asin_yield_one():
    names = pd.Series(["DG - B0CYLMJJJC - SP", "Campaña sin ASIN", "X B0CYLM4L23 Y"])

    extracted = asins_from_campaigns(names)

    assert list(extracted.dropna()) == ["B0CYLMJJJC", "B0CYLM4L23"]
    assert pd.isna(extracted.iloc[1])


def test_the_bid_is_cvr_times_price_times_target_acos():
    frame = _canonical_frame([_row(clicks=100, orders=10, sales=200.0, spend=50.0)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)

    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25)

    row = bids.iloc[0]
    assert row["_cvr"] == 10.0            # 10 orders / 100 clicks
    assert row["_precio"] == 20.0         # 200 sales / 10 orders
    assert row["_bid_base"] == 0.5        # 0.10 * 20 * 0.25
    assert row["_acos"] == 25.0           # 50 spend / 200 sales


def test_the_inventory_price_replaces_the_average_selling_price():
    frame = _canonical_frame([_row(clicks=100, orders=10, sales=200.0)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)

    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25,
                        precio_map={"B0CYLMJJJC": 40.0})

    assert bids.iloc[0]["_precio"] == 40.0
    assert bids.iloc[0]["_bid_base"] == 1.0


def test_rows_of_the_same_asin_across_campaigns_are_summed_once():
    frame = _canonical_frame([
        _row(campaign="DG - B0CYLMJJJC - SP - EXACT", clicks=60, orders=6, sales=120.0, spend=30.0),
        _row(campaign="DG - B0CYLMJJJC - SP - BROAD", clicks=40, orders=4, sales=80.0, spend=20.0)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)

    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25)

    assert len(bids) == 1
    assert bids.iloc[0]["Clicks"] == 100
    assert bids.iloc[0]["_cvr"] == 10.0


def test_without_orders_there_is_no_measured_cvr_so_the_bid_stays_at_zero():
    frame = _canonical_frame([_row(clicks=50, orders=0, sales=0.0, spend=25.0)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)

    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25)

    assert bids.iloc[0]["_bid_base"] == 0.0
    assert bids.iloc[0]["_precio"] == 0.0


def test_the_traffic_light_reads_clicks_before_cvr():
    assert estado_por_cvr(cvr=0.0, clicks=0, orders=0) == "⚫ SIN DATA"
    assert estado_por_cvr(cvr=20.0, clicks=100, orders=6) == "🟢 ESCALAR"
    assert estado_por_cvr(cvr=10.0, clicks=100, orders=10) == "🟡 OK"
    assert estado_por_cvr(cvr=3.0, clicks=100, orders=3) == "🔴 REVISAR"


def test_a_high_cvr_without_enough_orders_is_not_promoted_to_escalar():
    assert estado_por_cvr(cvr=20.0, clicks=10, orders=2) == "🔴 REVISAR"


def test_campaign_placements_carry_the_sop_modifiers_for_the_detected_type():
    frame = _canonical_frame([_row(campaign="DG - B0CYLMJJJC - SP - PAT - Competitor")])
    cols = detect_columns(frame)

    rows = campaign_placements(frame, cols)

    assert rows[0]["Tipo Detectado"] == "PAT Competitor"
    assert (rows[0]["ToS %"], rows[0]["PDP %"]) == (0, 50)


def test_the_budget_midpoint_is_the_middle_of_the_sop_range():
    assert budget_midpoint("Exact Ranking") == 12.5
    assert budget_midpoint("PAT Competitor") == 6.5
    assert budget_midpoint("un tipo que no existe") == 10.0


def test_the_ai_records_are_native_types_ordered_by_spend():
    frame = _canonical_frame([
        _row(campaign="DG - B0CYLMJJJC - SP", spend=10.0),
        _row(campaign="DG - B0CYLM4L23 - SP", spend=90.0)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)
    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25)

    records = bid_ai_records(bids, cols, col_asin, keep=10)

    assert [record["asin"] for record in records] == ["B0CYLM4L23", "B0CYLMJJJC"]
    assert isinstance(records[0]["clicks"], int)
    assert isinstance(records[0]["bid_base"], float)


def test_the_ai_records_stop_at_the_cap():
    frame = _canonical_frame([_row(campaign=f"DG - B0CYLM{index:04d} - SP") for index in range(8)])
    cols = detect_columns(frame)
    resolved, col_asin, _ = resolve_asin_column(frame, cols)
    bids = bids_by_asin(resolved, cols, col_asin, target_acos=25)

    assert len(bid_ai_records(bids, cols, col_asin, keep=3)) == 3


def test_money_columns_read_the_same_whether_they_arrive_numeric_or_as_text():
    """El frame de la API llega numérico; el archivo a mano, con $ y comas."""
    from modules.pages.bid_optimizer import _numeric_column

    as_text = pd.Series(["$1,234.56", "78.90", "—"])
    as_numbers = pd.Series([1234.56, 78.90, 0.0])

    assert list(_numeric_column(as_text)) == [1234.56, 78.90, 0.0]
    assert list(_numeric_column(as_numbers)) == [1234.56, 78.90, 0.0]


def test_a_numeric_column_with_gaps_reads_them_as_zero_not_as_nan():
    from modules.pages.bid_optimizer import _numeric_column

    assert list(_numeric_column(pd.Series([5.0, None, 2.0]))) == [5.0, 0.0, 2.0]


def test_campaign_placements_aggregates_every_campaign_exactly_once():
    frame = _canonical_frame(
        [_row(campaign=f"DG - B0CYLM{index:04d} - SP - EXACT", spend=10.0, sales=40.0, orders=2)
         for index in range(50) for _ in range(3)])

    rows = campaign_placements(frame, detect_columns(frame))

    assert len(rows) == 50
    assert {row["Campaign"] for row in rows}.__len__() == 50
    assert rows[0]["Spend"] == 30.0    # las 3 filas de esa campaña, sumadas una sola vez
    assert rows[0]["Orders"] == 6
