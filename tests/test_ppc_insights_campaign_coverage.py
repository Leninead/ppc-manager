"""Which SP campaigns run for each ASIN and of which kinds: from the account's listing, or from a Campaign CSV."""
import pandas as pd
import pytest

from core.amazon_ads.report_provider import ReportReadError
from core.amazon_ads.sync_planner import SP_PRODUCT_ADS_KIND, SP_TARGETS_KIND
from core.ppc_insights.asin_health import NEUTRAL_POINTS, WHOLE_ACCOUNT, analyze_asins
from core.ppc_insights.campaign_coverage import (
    LISTING_ENTITIES,
    STRUCTURE_PENDING_REASON,
    AsinCampaigns,
    FileCampaigns,
    read_campaign_listing,
)
from core.search_term.frame import console_columns
from tests.ppc_insights_campaigns_data import (
    DAY,
    LISTED_AT,
    PROFILE,
    ListingRest,
    ad_group,
    campaign,
    completed_job,
    keyword,
    listed_campaigns,
    product_ad,
    product_target,
)

HERO = "B0CYLMJJJC"
LOTION = "B0CYLM4L23"
FAMILY = "B0FAMILY01"


# ── the listing ──────────────────────────────────────────────────────────────

def test_an_ad_group_covers_the_asin_it_advertises_with_the_kinds_it_runs():
    campaigns = listed_campaigns(
        campaign("1", "Luna - SP - KW - Exact"), product_ad("1", "10", HERO),
        keyword("1", "10", "vitamin a cream", "EXACT"), keyword("1", "10", "night cream", "PHRASE"),
        campaign("2", "Luna - SP - Auto"), product_ad("2", "20", LOTION))

    assert campaigns.for_asin(HERO) == AsinCampaigns(1, frozenset({"Exact", "Phrase"}))
    assert campaigns.for_asin(LOTION) == AsinCampaigns(1, frozenset())


def test_an_auto_campaign_is_auto_and_auto_with_exact_completes_the_funnel():
    campaigns = listed_campaigns(
        campaign("1", "Luna - SP - Auto", targeting="AUTO"), product_ad("1", "10", HERO),
        product_target("1", "10", "close-match"),
        campaign("2", "Luna - SP - KW - Exact"), product_ad("2", "20", HERO),
        keyword("2", "20", "vitamin a cream", "EXACT"))

    coverage = campaigns.for_asin(HERO)

    assert coverage == AsinCampaigns(2, frozenset({"Auto", "Exact"}))
    assert coverage.funnel_complete and coverage.kinds_label == "Auto, Exact"


def test_the_campaign_name_covers_the_family_asin_its_ad_groups_do_not_advertise():
    campaigns = listed_campaigns(
        campaign("1", f"Luna - {FAMILY} - SP - KW - Broad"),
        product_ad("1", "10", "B0CHILD0001"), product_ad("1", "10", "B0CHILD0002"),
        keyword("1", "10", "sleep sack", "BROAD"))

    assert campaigns.for_asin(FAMILY) == AsinCampaigns(1, frozenset({"Broad"}))
    assert campaigns.for_asin("B0CHILD0002") == AsinCampaigns(1, frozenset({"Broad"}))


def test_what_does_not_run_does_not_cover():
    campaigns = listed_campaigns(
        campaign("1", "Luna - SP - paused campaign", state="PAUSED"), product_ad("1", "10", HERO),
        keyword("1", "10", "a", "EXACT"),
        campaign("2", "Luna - SP - paused ad group"), ad_group("2", "20", state="PAUSED"),
        product_ad("2", "20", HERO), keyword("2", "20", "b", "EXACT"),
        campaign("3", "Luna - SP - paused ad"), product_ad("3", "30", HERO, state="PAUSED"),
        keyword("3", "30", "c", "EXACT"),
        campaign("4", "Luna - SP - archived", state="ARCHIVED"), product_ad("4", "40", HERO),
        campaign("5", "Luna - SP - paused keyword"), product_ad("5", "50", HERO),
        keyword("5", "50", "d", "EXACT", state="PAUSED"), keyword("5", "50", "e", "BROAD"))

    assert campaigns.for_asin(HERO) == AsinCampaigns(1, frozenset({"Broad"}))
    assert campaigns.campaign_count == 1


def test_an_ad_group_the_listing_never_showed_counts_as_enabled():
    campaigns = listed_campaigns(campaign("1", "Luna - SP - KW"), product_ad("1", "10", HERO),
                                 keyword("1", "10", "vitamin a cream", "EXACT"))

    assert campaigns.for_asin(HERO).campaigns == 1


def test_product_targets_are_pat_only_in_manual_campaigns():
    campaigns = listed_campaigns(
        campaign("1", "Luna - SP - PAT"), product_ad("1", "10", HERO),
        product_target("1", "10", 'asin="B0RIVAL001"'),
        campaign("2", "Luna - SP - Auto", targeting="AUTO"), product_ad("2", "20", LOTION),
        product_target("2", "20", "loose-match"))

    assert campaigns.for_asin(HERO).kinds == frozenset({"PAT"})
    assert campaigns.for_asin(LOTION).kinds == frozenset({"Auto"})


def test_several_ad_groups_of_one_campaign_count_it_once_and_the_account_row_counts_every_campaign():
    campaigns = listed_campaigns(
        campaign("1", "Luna - SP - KW"), product_ad("1", "10", HERO), keyword("1", "10", "a", "EXACT"),
        product_ad("1", "11", HERO), keyword("1", "11", "b", "BROAD"),
        campaign("2", "Luna - SP - Auto", targeting="AUTO"), product_ad("2", "20", LOTION))

    assert campaigns.for_asin(HERO) == AsinCampaigns(1, frozenset({"Exact", "Broad"}))
    assert campaigns.for_asin(WHOLE_ACCOUNT) == AsinCampaigns(2, frozenset({"Exact", "Broad", "Auto"}))


def test_an_asin_no_campaign_runs_for_has_none_and_an_incomplete_funnel():
    coverage = listed_campaigns(campaign("1", "Luna - SP - KW"), product_ad("1", "10", HERO),
                                keyword("1", "10", "a", "EXACT")).for_asin(LOTION)

    assert coverage == AsinCampaigns(0, frozenset())
    assert coverage.kinds_label == "—" and not coverage.funnel_complete


# ── reading it ───────────────────────────────────────────────────────────────

def test_the_read_asks_for_the_five_families_over_one_day():
    rest = ListingRest([campaign("1", "Luna"), product_ad("1", "10", HERO), keyword("1", "10", "a", "EXACT")])

    listing = read_campaign_listing(rest, PROFILE, DAY)

    [args] = rest.reads
    assert tuple(args["p_entities"]) == LISTING_ENTITIES
    assert (args["p_from"], args["p_to"]) == (DAY.isoformat(), DAY.isoformat())
    assert listing.campaigns is not None and listing.campaigns.listed_at == LISTED_AT


@pytest.mark.parametrize("rows, missing", [
    ([], "Todavía no se listaron las campañas"),
    ([campaign("1", "Luna"), keyword("1", "10", "a", "EXACT")], "Todavía no se listaron los anuncios"),
    ([campaign("1", "Luna"), product_ad("1", "10", HERO)], "Todavía no se listaron los keywords y product targets"),
])
def test_the_coverage_is_unknown_until_campaigns_ads_and_targets_were_listed(rows, missing):
    listing = read_campaign_listing(ListingRest(rows), PROFILE, DAY)

    assert listing.campaigns is None and listing.missing_reason.startswith(missing)
    assert not listing.refused


def test_a_family_listed_without_rows_counts_as_listed():
    rest = ListingRest([campaign("1", "Luna"), product_ad("1", "10", HERO)], jobs=[completed_job(SP_TARGETS_KIND)])

    listing = read_campaign_listing(rest, PROFILE, DAY)

    assert listing.campaigns is not None and listing.campaigns.for_asin(HERO) == AsinCampaigns(1, frozenset())


def test_a_listing_amazon_refused_says_so():
    rest = ListingRest([campaign("1", "Luna"), keyword("1", "10", "a", "EXACT")],
                       jobs=[completed_job(SP_PRODUCT_ADS_KIND, warning="sin permiso para leer los anuncios")])

    listing = read_campaign_listing(rest, PROFILE, DAY)

    assert listing.campaigns is None and listing.refused
    assert "rechazó el listado de los anuncios" in listing.missing_reason
    assert "sin permiso para leer los anuncios" in listing.missing_reason


def test_a_base_without_the_structure_says_a_migration_is_missing():
    listing = read_campaign_listing(ListingRest(missing=True), PROFILE, DAY)

    assert listing.campaigns is None and listing.missing_reason == STRUCTURE_PENDING_REASON


def test_a_base_that_cannot_be_read_raises():
    with pytest.raises(ReportReadError):
        read_campaign_listing(ListingRest(fail=True), PROFILE, DAY)


# ── a Campaign CSV uploaded by hand: the rule the module always had ──────────

def test_a_campaign_csv_covers_by_name_and_reads_the_kinds_from_words_of_the_name():
    frame = pd.DataFrame({"Campaign Name": [f"DG - {HERO} - SP - AUTO", f"DG - {HERO} - SP - KW - EXACT",
                                            f"DG - {HERO} - SP - KW - BROAD - paused", "DG - SP - PHRASE"],
                          "State": ["enabled", "enabled", "paused", "enabled"],
                          "Targeting Type": ["Auto", "Manual", "Manual", "Manual"]})

    coverage = FileCampaigns(frame).for_asin(HERO)

    assert coverage == AsinCampaigns(2, frozenset({"Auto", "Exact", "Manual"}))
    assert coverage.funnel_complete


def test_a_campaign_csv_without_a_name_column_says_nothing_of_any_asin():
    assert FileCampaigns(pd.DataFrame({"Spend": [1.0]})).for_asin(HERO) is None


# ── the funnel part of the health score ──────────────────────────────────────

def _report(ad_group_id):
    frame = pd.DataFrame([{"Customer Search Term": "vitamin a cream", "Campaign Name": "Luna - SP",
                           "Spend": 20.0, "7 Day Total Sales": 80.0, "7 Day Total Orders (#)": 4, "Clicks": 30,
                           "Impressions": 900, "_asin": HERO, "_ad_group_id": ad_group_id}])
    for column in console_columns(7):
        if column not in frame.columns:
            frame[column] = 0
    return frame


@pytest.mark.parametrize("campaigns, points, types", [
    (None, NEUTRAL_POINTS["funnel"], None),
    ("auto+exact", 15, "Auto, Exact"),
    ("exact", 8, "Exact"),
])
def test_the_listing_gives_the_funnel_part_its_points(campaigns, points, types):
    rows = {"auto+exact": [campaign("1", "Luna - Auto", targeting="AUTO"), product_ad("1", "10", HERO),
                           campaign("2", "Luna - KW"), product_ad("2", "20", HERO),
                           keyword("2", "20", "a", "EXACT")],
            "exact": [campaign("2", "Luna - KW"), product_ad("2", "20", HERO), keyword("2", "20", "a", "EXACT")]}
    coverage = listed_campaigns(*rows[campaigns]) if campaigns else None

    metrics = analyze_asins(_report("10"), None, None, coverage, 25, "_asin")[HERO]

    assert metrics["health_parts"]["funnel"] == points
    assert metrics["campaign_types"] == types
