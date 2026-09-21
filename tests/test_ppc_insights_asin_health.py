"""PPC Insights rules: the ASIN behind each search term, the metrics per ASIN and the health score."""
import pandas as pd
import pytest

from core.amazon_ads.advertised_asins import (
    FROM_AD_GROUP,
    FROM_CAMPAIGN_NAME,
    SEVERAL_ASINS,
    WITHOUT_ASIN,
    attribute_asins,
)
from core.ppc_insights.asin_health import (
    ATTRIBUTED,
    FROM_FILE,
    MAX_POINTS,
    NEUTRAL_POINTS,
    NO_ASINS,
    RESOLVED_ASIN_COLUMN,
    WHOLE_ACCOUNT,
    analyze_asins,
    health_score,
    health_score_parts,
    resolve_asins,
)
from core.search_term.frame import console_columns

ATTRIBUTION_DAYS = 7
HERO, VARIANT, OTHER, COMPETITOR, FAMILY = "B0CYLMJJJC", "B0CYLM4L23", "B0F4KXZVNM", "B0COMPET01", "B0FAMILY01"


def _frame(rows):
    """Shaped like the picker's API frame: console columns plus the hidden ad group id, no Advertised ASIN."""
    frame = pd.DataFrame(rows)
    for column in console_columns(ATTRIBUTION_DAYS):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(ATTRIBUTION_DAYS) + ["_ad_group_id"]]


def _row(ad_group, campaign="DG - SP - KW - EXACT", term="vitamin a cream", spend=10.0, sales=40.0, orders=2,
         clicks=20):
    return {"Customer Search Term": term, "Campaign Name": campaign, "_ad_group_id": ad_group, "Spend": spend,
            "7 Day Total Sales": sales, "7 Day Total Orders (#)": orders, "Clicks": clicks, "Impressions": 500}


MAPPING = {"AG1": frozenset({HERO}), "AG2": frozenset({VARIANT, OTHER})}


def test_an_ad_group_that_advertises_one_asin_gives_it_to_every_term():
    attribution = attribute_asins(_frame([_row("AG1"), _row("AG1", term="night cream")]), MAPPING, "Campaign Name")

    assert list(attribution.asins) == [HERO, HERO]
    assert set(attribution.origins) == {FROM_AD_GROUP}


def test_with_several_asins_the_campaign_name_decides_even_if_the_ad_group_does_not_advertise_it():
    frame = _frame([_row("AG2", campaign=f"DG - {OTHER} - SP - KW"),
                    _row("AG2", campaign=f"DG - {FAMILY} - SP - KW"),
                    _row("AG2", campaign="DG - SP - AUTO")])

    attribution = attribute_asins(frame, MAPPING, "Campaign Name")

    assert attribution.asins.iloc[0] == OTHER and attribution.origins.iloc[0] == FROM_CAMPAIGN_NAME
    # Accounts named by family put the family's ASIN in the name and advertise its children.
    assert attribution.asins.iloc[1] == FAMILY and attribution.origins.iloc[1] == FROM_CAMPAIGN_NAME
    assert pd.isna(attribution.asins.iloc[2]) and attribution.origins.iloc[2] == SEVERAL_ASINS


def test_an_ad_group_with_one_asin_wins_over_the_asin_in_the_campaign_name():
    attribution = attribute_asins(_frame([_row("AG1", campaign=f"DG - {COMPETITOR} - SP - PAT")]), MAPPING,
                                  "Campaign Name")

    assert attribution.asins.iloc[0] == HERO and attribution.origins.iloc[0] == FROM_AD_GROUP


def test_an_ad_group_the_listing_never_showed_falls_back_to_the_campaign_name():
    frame = _frame([_row("AG9", campaign=f"DG - {OTHER} - SP"), _row("AG9", campaign="DG - SP - BROAD")])

    attribution = attribute_asins(frame, MAPPING, "Campaign Name")

    assert attribution.asins.iloc[0] == OTHER and attribution.origins.iloc[0] == FROM_CAMPAIGN_NAME
    assert pd.isna(attribution.asins.iloc[1]) and attribution.origins.iloc[1] == WITHOUT_ASIN


def test_a_manual_file_without_ad_groups_uses_only_the_campaign_name():
    frame = pd.DataFrame([{"Campaign Name": f"DG - {HERO} - SP", "Spend": 5.0}, {"Campaign Name": "DG", "Spend": 5.0}])

    attribution = attribute_asins(frame, {}, "Campaign Name")

    assert attribution.asins.iloc[0] == HERO and pd.isna(attribution.asins.iloc[1])


def test_resolved_asins_report_the_share_of_spend_by_origin():
    frame = _frame([_row("AG1", spend=60.0), _row("AG2", spend=30.0), _row("AG9", spend=10.0)])

    resolved = resolve_asins(frame, MAPPING)

    assert resolved.source == ATTRIBUTED and resolved.column == RESOLVED_ASIN_COLUMN
    assert resolved.spend_share == {FROM_AD_GROUP: 60.0, SEVERAL_ASINS: 30.0, WITHOUT_ASIN: 10.0}
    assert list(resolved.frame[RESOLVED_ASIN_COLUMN].dropna()) == [HERO]
    assert resolved.report_spend == 100.0


def test_the_origins_cover_all_the_spend_of_the_report():
    frame = _frame([_row("AG1", spend=40.0), _row("AG2", campaign=f"DG - {FAMILY} - SP", spend=35.0),
                    _row("AG2", spend=15.0), _row("AG9", spend=10.0)])

    resolved = resolve_asins(frame, MAPPING)

    assert resolved.spend_share == {FROM_AD_GROUP: 40.0, FROM_CAMPAIGN_NAME: 35.0, SEVERAL_ASINS: 15.0,
                                    WITHOUT_ASIN: 10.0}
    assert sum(resolved.spend_share.values()) == 100.0


def test_a_card_taken_from_the_campaign_name_says_how_many_asins_its_ad_groups_advertise():
    mapping = {**MAPPING, "AG3": frozenset({VARIANT, "B0CHILD0003"})}
    frame = _frame([_row("AG2", campaign=f"DG - {FAMILY} - SP"), _row("AG3", campaign=f"DG - {FAMILY} - SP"),
                    _row("AG1", campaign=f"DG - {FAMILY} - SP"), _row("AG9", campaign=f"DG - {OTHER} - SP")])

    resolved = resolve_asins(frame, mapping)

    # AG2 and AG3 advertise VARIANT, OTHER and B0CHILD0003; AG1 has one ASIN and AG9 no listing, so neither counts.
    assert resolved.grouped_asins == {FAMILY: 3}


def test_a_file_with_its_own_asin_column_keeps_it_over_any_attribution():
    frame = _frame([_row("AG2"), _row("AG2")])
    frame["Advertised ASIN"] = [OTHER, ""]

    resolved = resolve_asins(frame, MAPPING)

    assert resolved.source == FROM_FILE and resolved.column == "Advertised ASIN"
    assert resolved.spend_share == {FROM_FILE: 50.0, WITHOUT_ASIN: 50.0}


def test_without_any_asin_the_frame_stays_whole_and_the_analysis_reads_the_account():
    frame = _frame([_row("AG9"), _row("AG9", term="night cream")])

    resolved = resolve_asins(frame, {})
    asin_data = analyze_asins(resolved.frame, None, None, None, 25, resolved.column)

    assert resolved.source == NO_ASINS and RESOLVED_ASIN_COLUMN not in resolved.frame.columns
    assert list(asin_data) == [WHOLE_ACCOUNT] and asin_data[WHOLE_ACCOUNT]["spend"] == 20.0


def test_the_metrics_per_asin_add_up_only_the_terms_attributed_to_it():
    frame = _frame([_row("AG1", spend=30.0, sales=90.0, orders=3, clicks=30),
                    _row("AG1", term="bleeding term", spend=12.0, sales=0.0, orders=0, clicks=15),
                    _row("AG2", spend=99.0)])
    resolved = resolve_asins(frame, MAPPING)

    asin_data = analyze_asins(resolved.frame, None, None, None, 25, resolved.column)

    assert list(asin_data) == [HERO]
    hero = asin_data[HERO]
    assert (hero["spend"], hero["sales"], hero["orders"], hero["clicks"]) == (42.0, 90.0, 3.0, 45.0)
    assert hero["wasted_spend"] == 12.0 and list(hero["bleeders"]["Search Term"]) == ["bleeding term"]
    assert hero["health_score"] == round(sum(hero["health_parts"].values()))


def test_a_term_below_the_bleeder_spend_is_not_wasted_spend():
    frame = _frame([_row("AG1", term="cheap miss", spend=5.0, sales=0.0, orders=0),
                    _row("AG1", spend=20.0, sales=80.0, orders=2)])
    resolved = resolve_asins(frame, MAPPING)

    hero = analyze_asins(resolved.frame, None, None, None, 25, resolved.column)[HERO]

    assert hero["wasted_spend"] == 0.0 and hero["bleeders"].empty


@pytest.mark.parametrize("inputs, expected", [
    ({"acos": None, "cvr": None, "buybox": None, "funnel_complete": None, "imp_share": None}, 48),
    ({"acos": 20.0, "cvr": 15.0, "buybox": 95.0, "funnel_complete": True, "imp_share": 30.0}, 100),
    ({"acos": 30.0, "cvr": 7.5, "buybox": 0.0, "funnel_complete": False, "imp_share": 0.0}, 46),
    ({"acos": 100.0, "cvr": 0.0, "buybox": 47.5, "funnel_complete": None, "imp_share": 12.0}, 39),
])
def test_the_health_score_keeps_the_points_the_module_always_gave(inputs, expected):
    assert health_score(target_acos=25, **inputs) == expected


def test_a_part_without_its_source_gives_its_neutral_points():
    parts = health_score_parts(acos=None, target_acos=25, cvr=None, buybox=None, funnel_complete=None, imp_share=None)

    assert parts == NEUTRAL_POINTS
    assert set(parts) == set(MAX_POINTS)
