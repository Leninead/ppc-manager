"""campaign_structure: the SP structure of an account as Amazon Ads last listed it, for the chat.

Each entity answers with the fields that matter for it, a keyword says whether its bid is its own or its ad
group's default, and the answer says when each family was listed and when a family was never synced. The counts
come from the database; only the family asked for is read, and a big account's negatives only per campaign.
"""
import csv
import io
import json
from pathlib import Path

import pytest
import requests

from core.amazon_ads.structure_provider import (
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    CAMPAIGN_NEGATIVE_KEYWORD,
    CAMPAIGN_NEGATIVE_PRODUCT_TARGETING,
    COUNT_COLUMNS,
    KEYWORD,
    NEGATIVE_ENTITIES,
    NEGATIVE_KEYWORD,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    ROW_COLUMNS,
    STRUCTURE_COUNTS_RPC,
    STRUCTURE_RPC,
)
from services.mcp_server import server
from services.mcp_server.limits import MAX_TEXT_CHARS
from services.mcp_server.tools import amazon_ads

CAMPAIGNS_LISTED = "2026-09-22 06:00:01+00"
TARGETS_LISTED = "2026-09-22 06:05:00+00"
NEGATIVES_LISTED = "2026-09-22 06:07:30+00"


def _row(family, campaign_id, campaign_name, listed_at, **fields):
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update(entity=family, campaign_id=campaign_id, campaign_name=campaign_name, state="ENABLED",
               metrics_known="f", currency_code="USD", listed_at=listed_at)
    row.update(fields)
    return row


def _campaign(campaign_id, name, **fields):
    return _row(CAMPAIGN, campaign_id, name, CAMPAIGNS_LISTED, entity_id=campaign_id, **{
        "targeting_type": "MANUAL", "budget_amount": "25", "budget_type": "DAILY", "bidding_strategy": "MANUAL",
        "metrics_known": "t", "impressions": "0", "clicks": "0", "cost": "0", "purchases_7d": "0", "sales_7d": "0",
        "purchases_14d": "0", "sales_14d": "0", **fields})


def _placement(campaign_id, name, placement, percentage):
    return _row(BIDDING_ADJUSTMENT, campaign_id, name, CAMPAIGNS_LISTED, bidding_strategy="LEGACY_FOR_SALES",
                placement=placement, percentage=percentage)


def _target(family, campaign_id, name, ad_group_id, ad_group_name, target_id, text, **fields):
    return _row(family, campaign_id, name, TARGETS_LISTED, ad_group_id=ad_group_id, ad_group_name=ad_group_name,
                entity_id=target_id, target_text=text, **{
                    "target_kind": "keyword", "metrics_known": "t", "impressions": "0", "clicks": "0", "cost": "0",
                    "purchases_7d": "0", "sales_7d": "0", "purchases_14d": "0", "sales_14d": "0", **fields})


def _negative(family, campaign_id, name, negative_id, text, *, ad_group_id="", ad_group_name="", kind="keyword",
              match_type=""):
    return _row(family, campaign_id, name, NEGATIVES_LISTED, ad_group_id=ad_group_id, ad_group_name=ad_group_name,
                entity_id=negative_id, target_text=text, target_kind=kind, match_type=match_type)


EXACT, AUTO, OLD = "Demo SP - Exact", "Demo SP - Auto", "Old launch"
STRUCTURE = [
    _campaign("11", EXACT, portfolio_id="501", portfolio_name="RANKING", bidding_strategy="LEGACY_FOR_SALES",
              impressions="900", clicks="30", cost="21.5", purchases_7d="4", sales_7d="80.0", purchases_14d="5",
              sales_14d="99.0"),
    _placement("11", EXACT, "PLACEMENT_TOP", "50"),
    _placement("11", EXACT, "PLACEMENT_PRODUCT_PAGE", "0"),
    _placement("11", EXACT, "PLACEMENT_REST_OF_SEARCH", "0"),
    _placement("11", EXACT, "SITE_AMAZON_BUSINESS", "0"),
    _campaign("12", AUTO, state="PAUSED", targeting_type="AUTO", budget_amount="10",
              bidding_strategy="AUTO_FOR_SALES"),
    _campaign("13", OLD, state="ARCHIVED", budget_amount="5"),
    _row(AD_GROUP, "11", EXACT, CAMPAIGNS_LISTED, ad_group_id="21", entity_id="21", ad_group_name="AG - core",
         default_bid="0.8"),
    _row(AD_GROUP, "12", AUTO, CAMPAIGNS_LISTED, ad_group_id="22", entity_id="22", ad_group_name="AG - auto",
         state="PAUSED", default_bid="0.5"),
    _target(KEYWORD, "11", EXACT, "21", "AG - core", "9001", "demo cream", match_type="EXACT", own_bid="1.25",
            default_bid="0.8", bid="1.25", impressions="500", clicks="10", cost="12.5", purchases_7d="2",
            sales_7d="40.0"),
    _target(KEYWORD, "11", EXACT, "21", "AG - core", "9002", "demo lotion", match_type="PHRASE", default_bid="0.8",
            bid="0.8"),
    _target(PRODUCT_TARGETING, "12", AUTO, "22", "AG - auto", "9101", "close-match", target_kind="auto",
            state="PAUSED", default_bid="0.5", bid="0.5"),
    _row(PRODUCT_AD, "11", EXACT, CAMPAIGNS_LISTED, ad_group_id="21", ad_group_name="AG - core", entity_id="7001",
         asin="B0CYLMJJJC", sku="DG-CREAM-01"),
    _negative(NEGATIVE_KEYWORD, "11", EXACT, "8001", "free", ad_group_id="21", ad_group_name="AG - core",
              match_type="NEGATIVE_EXACT"),
    _negative(CAMPAIGN_NEGATIVE_KEYWORD, "11", EXACT, "8002", "cheap", match_type="NEGATIVE_PHRASE"),
    _negative(CAMPAIGN_NEGATIVE_PRODUCT_TARGETING, "12", AUTO, "8003", 'asin="B0COMPETE1"', kind="product"),
]


def _csv(rows, columns=ROW_COLUMNS) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _counted(rows, *, negatives_snapshot: bool = True) -> list[dict]:
    """What sp_structure_counts answers for these rows: one row per family present, and each negative family at 0
    when a complete negatives run exists."""
    families = {}
    for row in rows:
        family = families.setdefault(row["entity"], {"entity": row["entity"], "entity_rows": 0, "listed_at": ""})
        family["entity_rows"] += 1
        family["listed_at"] = max(family["listed_at"], row["listed_at"])
    if negatives_snapshot:
        for entity in NEGATIVE_ENTITIES:
            families.setdefault(entity, {"entity": entity, "entity_rows": 0, "listed_at": NEGATIVES_LISTED})
    return list(families.values())


def _missing_function() -> requests.HTTPError:
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"code":"PGRST202","message":"Could not find the function"}'
    return requests.HTTPError(response=response)


# The listings a synced account has completed, each one also when it stored no rows.
LISTINGS = ("campaign_entities", "sp_ad_groups", "sp_targets", "sp_product_ads", "sp_negatives")
_JOB_FILTERS = ("job_kind", "status", "external_account_id")


class FakeRest:
    def __init__(self, structure=STRUCTURE, *, fail_with=None, listings=LISTINGS, counted=None,
                 negatives_snapshot=True):
        self.structure = list(structure)
        self.fail_with = fail_with
        # What the counts RPC answers when it is not the count of `structure`.
        self.counted = counted
        # Whether ads_listing_snapshot holds a complete negatives run of the account.
        self.negatives_snapshot = negatives_snapshot
        self.reads = []
        self.profiles = [{"profile_id": "111", "account_id": 1, "cliente": "dermaglos", "account_name": "Dermaglos",
                          "country_code": "US", "currency_code": "USD", "account_type": "seller",
                          "timezone": "America/Los_Angeles", "status": "active", "data_from": "2026-07-11",
                          "data_through": "2026-09-14", "refreshed_on": "2026-09-15",
                          "last_success_at": "2026-09-15T10:00:00+00:00", "last_error": ""}]
        self.jobs = [{"id": 441, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns",
                      "trigger": "scheduled_daily", "external_account_id": "111", "status": "completed",
                      "window_start": "2026-07-14", "window_end": "2026-09-16", "local_day": "2026-09-17",
                      "finished_at": "2026-09-18T00:51:00+00:00", "created_at": "2026-09-18T00:43:00+00:00"}]
        self.jobs += [{**self.jobs[0], "id": 500 + index, "job_kind": kind, "window_start": None, "window_end": None}
                      for index, kind in enumerate(listings)]

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [dict(row) for row in self.profiles]
        if table == "integration_sync_jobs":
            assert params["order"] == "finished_at.desc,id.desc"
            matching = [dict(job) for job in self.jobs
                        if all(params[column] == f"eq.{job[column]}" for column in _JOB_FILTERS if column in params)]
            return sorted(matching, key=lambda job: (job["finished_at"] or "", job["id"]), reverse=True)[:1]
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, **_):
        assert name in (STRUCTURE_RPC, STRUCTURE_COUNTS_RPC)
        self.reads.append((name, args))
        if self.fail_with:
            raise self.fail_with
        rows = [row for row in self.structure
                if row["entity"] in args.get("p_entities", [row["entity"]])
                and row["campaign_id"] in args.get("p_campaign_ids", [row["campaign_id"]])]
        if name == STRUCTURE_COUNTS_RPC:
            assert "p_entities" not in args
            counted = self.counted if self.counted is not None else _counted(
                rows, negatives_snapshot=self.negatives_snapshot)
            return _csv(counted, COUNT_COLUMNS)
        return _csv(rows)

    def row_reads(self) -> list[tuple]:
        """The families and campaigns each read of rows asked for."""
        return [(args.get("p_entities"), args.get("p_campaign_ids")) for name, args in self.reads
                if name == STRUCTURE_RPC]


def _structure(rest=None, **options):
    return amazon_ads.campaign_structure(rest or FakeRest(), profile_id="111", **options)


def _by(rows, key):
    return {row[key]: row for row in rows}


def test_campaigns_carry_their_budget_strategy_portfolio_and_placement_adjustments():
    rows = _by(_structure()["rows"], "campaign_id")

    exact = rows["11"]
    assert (exact["campaign"], exact["state"], exact["targeting_type"], exact["portfolio"]) == (
        EXACT, "ENABLED", "MANUAL", "RANKING")
    assert (exact["budget"], exact["budget_type"], exact["bid_strategy"]) == (
        25, "DAILY", "Dynamic bidding (down only)")
    assert (exact["top_of_search_pct"], exact["product_pages_pct"], exact["rest_of_search_pct"],
            exact["amazon_business_pct"]) == (50, 0, 0, 0)
    # Never listed with its adjustments: unknown, not zero.
    assert (rows["12"]["top_of_search_pct"], rows["12"]["amazon_business_pct"]) == (None, None)
    assert rows["12"]["bid_strategy"] == "Dynamic bidding (up and down)"


def test_campaigns_come_in_every_state_with_their_window_metrics_as_a_seller_counts_them():
    rows = _by(_structure()["rows"], "campaign_id")

    assert {campaign_id: row["state"] for campaign_id, row in rows.items()} == {
        "11": "ENABLED", "12": "PAUSED", "13": "ARCHIVED"}
    exact = rows["11"]
    assert (exact["spend"], exact["sales"], exact["orders"], exact["clicks"], exact["impressions"]) == (
        21.5, 80.0, 4, 30, 900)
    assert (exact["acos"], exact["cvr"]) == (26.9, 13.33)


def test_placements_are_one_row_per_placement_under_campaign_manager_names():
    rows = _structure(entity="placements")["rows"]

    assert [(row["campaign"], row["placement"], row["percentage"]) for row in rows] == [
        (EXACT, "Product pages", 0), (EXACT, "Rest of search", 0), (EXACT, "Top of search", 50),
        (EXACT, "Amazon Business", 0)]
    assert rows[0]["bid_strategy"] == "Dynamic bidding (down only)"


def test_ad_groups_carry_their_default_bid():
    rows = _structure(entity="ad_groups")["rows"]

    assert [(row["campaign"], row["ad_group"], row["ad_group_id"], row["state"], row["default_bid"])
            for row in rows] == [(AUTO, "AG - auto", "22", "PAUSED", 0.5), (EXACT, "AG - core", "21", "ENABLED", 0.8)]
    assert "spend" not in rows[0]


def test_a_keyword_says_whether_its_bid_is_its_own_or_its_ad_group_default():
    rows = _by(_structure(entity="keywords")["rows"], "target")

    own = rows["demo cream"]
    assert (own["bid"], own["own_bid"], own["default_bid"], own["bid_source"]) == (1.25, 1.25, 0.8, "own")
    assert (own["match_type"], own["ad_group"], own["target_id"], own["kind"]) == (
        "EXACT", "AG - core", "9001", "Keyword")
    inherited = rows["demo lotion"]
    assert (inherited["bid"], inherited["own_bid"], inherited["default_bid"], inherited["bid_source"]) == (
        0.8, None, 0.8, "ad_group_default")


def test_a_list_by_a_criterion_comes_sorted_filtered_and_counted_in_one_call():
    """Asked for the 10 worst keywords, the chat read 342 in 21 calls and described a cut its rows did not follow."""
    sold = _structure(entity="keywords", min_spend=1, sort_by="spend")
    assert [row["target"] for row in sold["rows"]] == ["demo cream"]
    assert sold["total"] == 1 and sold["filters"] == {"min_spend": 1}

    running = _structure(running_only=True)
    assert [row["campaign_id"] for row in running["rows"]] == ["11"]

    with pytest.raises(ValueError, match="sort_by y los filtros"):
        _structure(entity="negatives", sort_by="spend")


def test_keywords_without_traffic_are_there_with_their_zeros():
    rows = _by(_structure(entity="keywords")["rows"], "target")

    assert (rows["demo cream"]["spend"], rows["demo cream"]["orders"]) == (12.5, 2)
    assert (rows["demo lotion"]["impressions"], rows["demo lotion"]["spend"]) == (0, 0.0)


def test_product_targets_carry_their_kind_and_no_match_type():
    [row] = _structure(entity="product_targets")["rows"]

    assert (row["target"], row["kind"], row["match_type"], row["state"], row["bid_source"]) == (
        "close-match", "Automático", "", "PAUSED", "ad_group_default")


def test_product_ads_count_their_distinct_asins_apart_from_the_ads():
    """Asked how many products 5 campaigns advertise, the chat said 167: those were ads, 61 distinct ASINs."""
    payload = _structure(entity="product_ads")

    assert payload["distinct"] == {"asins": 1, "skus": 1}
    assert "un ASIN en varias campañas" in payload["distinct_note"]


def test_product_ads_carry_their_asin_and_sku():
    [row] = _structure(entity="product_ads")["rows"]

    assert (row["campaign"], row["ad_group"], row["asin"], row["sku"], row["ad_id"], row["state"]) == (
        EXACT, "AG - core", "B0CYLMJJJC", "DG-CREAM-01", "7001", "ENABLED")


def test_negatives_carry_their_level_kind_and_match_type():
    rows = _by(_structure(entity="negatives")["rows"], "negative_id")

    assert (rows["8001"]["level"], rows["8001"]["ad_group"], rows["8001"]["negative"], rows["8001"]["match_type"],
            rows["8001"]["kind"]) == ("ad_group", "AG - core", "free", "NEGATIVE_EXACT", "Keyword")
    assert (rows["8002"]["level"], rows["8002"]["ad_group"], rows["8002"]["match_type"]) == (
        "campaign", "", "NEGATIVE_PHRASE")
    assert (rows["8003"]["level"], rows["8003"]["kind"], rows["8003"]["negative"], rows["8003"]["match_type"]) == (
        "campaign", "Producto", 'asin="B0COMPETE1"', "")


def test_counts_cover_every_family_of_the_account_whatever_the_state_filter():
    payload = _structure(state="paused")

    assert payload["counts"] == {"campaigns": 3, "placements": 4, "ad_groups": 2, "keywords": 2,
                                 "product_targets": 1, "product_ads": 1, "negatives": 3}
    assert [row["campaign_id"] for row in payload["rows"]] == ["12"]


def test_a_state_filter_leaves_the_rows_in_that_state():
    assert [row["target"] for row in _structure(entity="keywords", state="enabled")["rows"]] == [
        "demo cream", "demo lotion"]
    assert _structure(entity="keywords", state="paused")["rows"] == []


def test_rows_under_a_campaign_carry_its_state_since_an_enabled_keyword_of_a_paused_one_does_not_run():
    serum = _target(KEYWORD, "12", AUTO, "22", "AG - auto", "9003", "demo serum", match_type="EXACT",
                    default_bid="0.5", bid="0.5")
    rest = FakeRest(STRUCTURE + [serum])

    keywords = _by(_structure(rest, entity="keywords")["rows"], "target")
    negatives = _by(_structure(rest, entity="negatives")["rows"], "negative_id")

    assert (keywords["demo cream"]["state"], keywords["demo cream"]["campaign_state"]) == ("ENABLED", "ENABLED")
    assert (keywords["demo serum"]["state"], keywords["demo serum"]["campaign_state"]) == ("ENABLED", "PAUSED")
    assert (negatives["8001"]["campaign_state"], negatives["8003"]["campaign_state"]) == ("ENABLED", "PAUSED")
    assert "campaign_state" not in _structure(rest)["rows"][0]


def test_a_keyword_is_found_by_part_of_its_text_in_any_campaign_whatever_the_case():
    serum = _target(KEYWORD, "12", AUTO, "22", "AG - auto", "9003", "Demo Cream Serum", match_type="PHRASE",
                    default_bid="0.5", bid="0.5")
    rest = FakeRest(STRUCTURE + [serum])

    payload = _structure(rest, entity="keywords", target="demo CREAM")

    assert [(row["target"], row["campaign"], row["campaign_state"]) for row in payload["rows"]] == [
        ("demo cream", EXACT, "ENABLED"), ("Demo Cream Serum", AUTO, "PAUSED")]
    # The text only narrows the rows: the counts stay those of the account.
    assert payload["counts"]["keywords"] == 3


def test_the_rows_that_are_exactly_the_target_come_before_those_that_only_contain_it():
    longer = _target(KEYWORD, "11", EXACT, "21", "AG - core", "9004", "a demo cream pack", match_type="PHRASE",
                     default_bid="0.8", bid="0.8")
    rest = FakeRest(STRUCTURE + [longer])

    payload = _structure(rest, entity="keywords", target="Demo Cream", limit=1)

    assert [row["target"] for row in payload["rows"]] == ["demo cream"]
    assert payload["total"] == 2
    # Where a keyword is counts only its exact rows, not the longer ones that contain it.
    assert payload["exact_matches"] == 1


def test_a_target_no_row_contains_says_so_and_is_read_as_plain_text():
    payload = _structure(entity="keywords", target="cream (xl")

    assert payload["rows"] == []
    assert payload["note"] == "Ninguno de los keywords de la cuenta contiene «cream (xl» en el último listado."
    assert _structure(entity="negatives", campaign="exact", target="pink")["note"] == (
        "Ninguno de los negativos de las campañas con «exact» contiene «pink» en el último listado.")


def test_a_target_on_an_entity_without_text_is_refused():
    with pytest.raises(ValueError, match="target busca en keywords, product_targets, negatives, product_ads"):
        _structure(entity="ad_groups", target="cream")


def test_a_product_ad_is_found_by_its_asin_or_sku_in_any_state_the_exact_asin_first():
    paused = _row(PRODUCT_AD, "12", AUTO, CAMPAIGNS_LISTED, ad_group_id="22", ad_group_name="AG - auto",
                  entity_id="7002", asin="B0CYLMJJJC", sku="DG-CREAM-02", state="PAUSED")
    bundle = _row(PRODUCT_AD, "11", EXACT, CAMPAIGNS_LISTED, ad_group_id="21", ad_group_name="AG - core",
                  entity_id="7003", asin="B0F548KTXD", sku="PACK-B0CYLMJJJC")
    rest = FakeRest(STRUCTURE + [bundle, paused])

    by_asin = _structure(rest, entity="product_ads", target="b0cylmjjjc")
    by_sku = _structure(rest, entity="product_ads", target="dg-cream")

    found = [(row["ad_id"], row["state"]) for row in by_asin["rows"]]
    assert sorted(found[:2]) == [("7001", "ENABLED"), ("7002", "PAUSED")] and found[2] == ("7003", "ENABLED")
    assert sorted(row["ad_id"] for row in by_sku["rows"]) == ["7001", "7002"]
    assert _structure(rest, entity="product_ads", target="B0NOTOURS1")["note"] == (
        "Ninguno de los product ads de la cuenta contiene «B0NOTOURS1» en el último listado.")


def test_a_campaign_is_found_by_part_of_its_name_whatever_the_case():
    payload = _structure(entity="keywords", campaign="sp - EXACT")

    assert [row["target"] for row in payload["rows"]] == ["demo cream", "demo lotion"]
    assert payload["counts"] == {"campaigns": 1, "placements": 4, "ad_groups": 1, "keywords": 2,
                                 "product_targets": 0, "product_ads": 1, "negatives": 2}
    assert payload["campaigns"] == [EXACT]


def test_a_campaign_is_found_by_its_id():
    payload = _structure(entity="negatives", campaign="12")

    assert [row["negative_id"] for row in payload["rows"]] == ["8003"]
    assert payload["campaigns"] == [AUTO]


def test_a_campaign_filter_that_finds_nothing_says_so():
    payload = _structure(campaign="brand defense")

    assert payload["rows"] == []
    assert payload["note"] == ("Ninguna campaña de Sponsored Products de la cuenta tiene «brand defense» en el nombre "
                               "ni ese id.")
    # An empty counts would tell the chat that nothing is synced, when there is just nothing to count.
    assert "counts" not in payload and payload["listed_at"] == {"campaigns": "2026-09-21T23:00:01-07:00"}


def test_a_campaign_filter_on_an_account_whose_campaigns_were_never_listed_says_they_are_not_synced():
    without_campaigns = [row for row in STRUCTURE if row["entity"] not in ("campaign", "bidding_adjustment")]
    rest = FakeRest(without_campaigns, listings=tuple(kind for kind in LISTINGS if kind != "campaign_entities"))

    filtered, unfiltered = _structure(rest, campaign="brand defense"), _structure(rest)

    assert filtered["note"] == unfiltered["note"] == "Todavía no se sincronizaron campañas de esta cuenta."


def test_a_campaign_without_that_family_says_it_has_none_in_the_last_listing():
    payload = _structure(entity="keywords", campaign="auto")

    assert payload["rows"] == [] and payload["counts"]["keywords"] == 0
    assert payload["note"] == "Las campañas con «auto» no tienen keywords en el último listado."


def test_listed_at_says_when_each_family_was_listed_on_the_account_clock():
    listed_at = _structure()["listed_at"]

    assert listed_at == {"campaigns": "2026-09-21T23:00:01-07:00", "placements": "2026-09-21T23:00:01-07:00",
                         "ad_groups": "2026-09-21T23:00:01-07:00", "keywords": "2026-09-21T23:05:00-07:00",
                         "product_targets": "2026-09-21T23:05:00-07:00", "product_ads": "2026-09-21T23:00:01-07:00",
                         "negatives": "2026-09-21T23:07:30-07:00"}


def test_a_family_never_listed_says_it_is_not_synced_yet_and_has_no_count():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES],
                    listings=tuple(kind for kind in LISTINGS if kind != "sp_negatives"), negatives_snapshot=False)

    payload = _structure(rest, entity="negatives")

    assert payload["rows"] == []
    assert payload["note"] == "Todavía no se sincronizaron negativos de esta cuenta."
    assert "negatives" not in payload["counts"] and "negatives" not in payload["listed_at"]


def test_negatives_are_synced_by_a_complete_run_not_by_a_job_that_closed_or_one_under_way():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES], negatives_snapshot=False)
    # A job of an earlier build completed without leaving a run, and today's is paused partway.
    rest.jobs.append({**rest.jobs[0], "id": 700, "job_kind": "sp_negatives", "status": "pending",
                      "finished_at": None, "rows_written": 40000,
                      "progress": {"listing": 0, "next_token": "page-41", "seen_at": NEGATIVES_LISTED,
                                   "rows": 40000}})

    payload = _structure(rest, entity="negatives")

    assert payload["note"] == "Todavía no se sincronizaron negativos de esta cuenta."
    assert "negatives" not in payload["counts"] and rest.row_reads() == []


def test_a_complete_run_that_found_no_negatives_says_so_though_a_later_job_was_refused():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES],
                    listings=tuple(kind for kind in LISTINGS if kind != "sp_negatives"))
    rest.jobs.append({**rest.jobs[0], "id": 700, "job_kind": "sp_negatives", "rows_written": 0,
                      "warning": "sin permiso para leer los negativos", "finished_at": "2026-09-22T10:00:00+00:00"})

    payload = _structure(rest, entity="negatives")

    assert payload["counts"]["negatives"] == 0
    assert payload["listed_at"]["negatives"] == "2026-09-21T23:07:30-07:00"
    assert payload["note"] == "La cuenta no tiene negativos de Sponsored Products en el último listado."


def test_without_migration_018_the_structure_is_not_synced_yet():
    payload = _structure(FakeRest(fail_with=_missing_function()))

    assert payload["rows"] == [] and payload["counts"] == {}
    assert payload["note"] == "La estructura de las campañas de esta cuenta todavía no se sincronizó."


def test_nothing_listed_at_all_is_not_synced_yet_either():
    assert _structure(FakeRest([], listings=(), negatives_snapshot=False))["note"] == (
        "La estructura de las campañas de esta cuenta todavía no se sincronizó.")


def test_a_family_listed_empty_counts_zero_instead_of_reading_as_never_synced():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] != PRODUCT_TARGETING])

    payload = _structure(rest, entity="product_targets")

    assert payload["rows"] == [] and payload["counts"]["product_targets"] == 0
    assert payload["note"] == "La cuenta no tiene product targets de Sponsored Products en el último listado."


def test_a_listing_amazon_refused_is_not_read_as_an_empty_one():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] != PRODUCT_TARGETING],
                    listings=tuple(kind for kind in LISTINGS if kind != "sp_targets"))
    rest.jobs.append({**rest.jobs[0], "id": 600, "job_kind": "sp_targets", "rows_written": 0,
                      "warning": "sin permiso para leer keywords y targets"})

    payload = _structure(rest, entity="product_targets")

    assert "product_targets" not in payload["counts"]
    assert payload["note"] == "Todavía no se sincronizaron product targets de esta cuenta."


def test_an_account_whose_listings_found_no_sp_campaign_says_so():
    payload = _structure(FakeRest([]))

    assert payload["rows"] == []
    assert payload["counts"] == dict.fromkeys(amazon_ads.STRUCTURE_ENTITIES, 0)
    assert payload["note"] == "La cuenta no tiene campañas de Sponsored Products en el último listado."


def test_campaigns_listed_without_their_adjustments_have_placements_unknown_not_zero():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] != BIDDING_ADJUSTMENT])

    payload = _structure(rest, entity="placements")

    assert payload["rows"] == [] and "placements" not in payload["counts"]
    assert payload["note"] == "Todavía no se sincronizaron ajustes por placement de esta cuenta."
    assert _structure(rest, entity="placements", campaign="exact")["note"] == (
        "Todavía no se sincronizaron ajustes por placement de las campañas con «exact».")


def test_rows_without_reports_in_the_window_go_without_metrics_and_the_answer_says_so():
    rest = FakeRest([_campaign("11", EXACT, metrics_known="f")])

    payload = _structure(rest)

    assert "spend" not in payload["rows"][0] and "impressions" not in payload["rows"][0]
    assert payload["metrics_note"].startswith("Todavía no hay reportes de esta ventana")
    assert "metrics_note" not in _structure()


def test_one_campaign_is_counted_and_read_on_its_own_instead_of_the_whole_account():
    rest = FakeRest()

    payload = _structure(rest, entity="keywords", campaign="exact")

    assert [row["target"] for row in payload["rows"]] == ["demo cream", "demo lotion"]
    assert [(name, args.get("p_entities"), args.get("p_campaign_ids")) for name, args in rest.reads] == [
        (STRUCTURE_RPC, ["campaign"], None), (STRUCTURE_COUNTS_RPC, None, ["11"]),
        (STRUCTURE_RPC, ["campaign", "keyword"], ["11"])]


def test_several_campaigns_are_read_by_their_ids_and_no_match_reads_only_the_campaigns():
    rest = FakeRest()

    payload = _structure(rest, entity="ad_groups", campaign="demo sp")
    _structure(rest, campaign="brand defense")

    assert [row["ad_group"] for row in payload["rows"]] == ["AG - auto", "AG - core"]
    assert payload["campaigns"] == [AUTO, EXACT]
    assert [(name, args.get("p_entities"), args.get("p_campaign_ids")) for name, args in rest.reads] == [
        (STRUCTURE_RPC, ["campaign"], None), (STRUCTURE_COUNTS_RPC, None, ["12", "11"]),
        (STRUCTURE_RPC, ["campaign", "ad_group"], ["12", "11"]), (STRUCTURE_RPC, ["campaign"], None)]


def test_the_counts_come_from_the_database_and_only_the_family_asked_for_and_its_campaigns_are_read():
    # The ad group negatives the database counts, far more than the rows this fake would read.
    rest = FakeRest(counted=[{**family, "entity_rows": 4200, "listed_at": "2026-09-22 06:09:00+00"}
                             if family["entity"] == NEGATIVE_KEYWORD else family for family in _counted(STRUCTURE)])

    payload = _structure(rest, entity="ad_groups")

    assert payload["counts"]["negatives"] == 4202
    assert payload["listed_at"]["negatives"] == "2026-09-21T23:09:00-07:00"
    assert rest.row_reads() == [(["campaign", "ad_group"], None)]


def test_campaigns_read_their_placement_adjustments_and_negatives_their_four_families_and_campaigns():
    rest = FakeRest()

    _structure(rest)
    _structure(rest, entity="negatives")

    assert rest.row_reads() == [(["campaign", "bidding_adjustment"], None), (["campaign", *NEGATIVE_ENTITIES], None)]


def test_a_family_with_nothing_in_the_last_listing_is_not_read():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] != PRODUCT_TARGETING])

    _structure(rest, entity="product_targets")
    _structure(rest, entity="keywords", campaign="auto")

    assert rest.row_reads() == [(["campaign"], None)]


def _many_negatives(count: int) -> list[dict]:
    """A big account's negatives: all at the ad group level of the auto campaign, but one in the exact one."""
    return [_negative(CAMPAIGN_NEGATIVE_KEYWORD, "11", EXACT, "8900", "cheap", match_type="NEGATIVE_PHRASE"),
            *(_negative(NEGATIVE_KEYWORD, "12", AUTO, str(90000 + index), f"term {index}", ad_group_id="22",
                        ad_group_name="AG - auto", match_type="NEGATIVE_EXACT") for index in range(count - 1))]


def test_a_big_accounts_negatives_are_not_read_without_a_campaign_and_the_answer_says_how_many_there_are():
    negatives = amazon_ads.MAX_ACCOUNT_NEGATIVES + 1
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES] + _many_negatives(negatives))

    payload = _structure(rest, entity="negatives")

    assert payload["rows"] == [] and rest.row_reads() == []
    assert payload["counts"]["negatives"] == negatives
    assert payload["listed_at"]["negatives"] == "2026-09-21T23:07:30-07:00"
    assert payload["note"] == (f"La cuenta tiene {negatives} negativos: son demasiados para traerlos todos. Pedí los "
                               "de una campaña con campaign (parte de su nombre o su id).")
    json.dumps(payload)


def test_a_big_accounts_negatives_are_read_per_campaign():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES]
                    + _many_negatives(amazon_ads.MAX_ACCOUNT_NEGATIVES + 1))

    exact = _structure(rest, entity="negatives", campaign="exact")
    auto = _structure(rest, entity="negatives", campaign="auto", limit=2)

    assert [row["negative_id"] for row in exact["rows"]] == ["8900"] and exact["counts"]["negatives"] == 1
    assert (auto["total"], auto["showing"]) == (amazon_ads.MAX_ACCOUNT_NEGATIVES, 2)
    assert rest.row_reads()[-1] == (["campaign", *NEGATIVE_ENTITIES], ["12"])


def test_a_filter_that_takes_in_several_campaigns_of_a_big_account_does_not_read_their_negatives():
    negatives = amazon_ads.MAX_ACCOUNT_NEGATIVES * 3
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES] + _many_negatives(negatives))

    # Every campaign name carries "SP" in the agency's naming, so this one takes in the whole account.
    payload = _structure(rest, entity="negatives", campaign="demo sp")

    assert payload["rows"] == [] and rest.row_reads() == [(["campaign"], None)]
    assert payload["counts"]["negatives"] == negatives
    assert payload["note"] == (f"Las 2 campañas con «demo sp» tienen {negatives} negativos: son demasiados para "
                               "traerlos todos. Pedí los de una sola campaña con campaign (más de su nombre, o su id).")


def test_one_campaign_is_read_whole_even_past_the_negatives_limit():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES]
                    + _many_negatives(amazon_ads.MAX_ACCOUNT_NEGATIVES + 2))

    payload = _structure(rest, entity="negatives", campaign="auto", limit=1)

    assert (payload["total"], payload["showing"]) == (amazon_ads.MAX_ACCOUNT_NEGATIVES + 1, 1)
    assert rest.row_reads()[-1] == (["campaign", *NEGATIVE_ENTITIES], ["12"])


def test_an_account_at_the_negatives_limit_reads_them_without_a_campaign():
    rest = FakeRest([row for row in STRUCTURE if row["entity"] not in NEGATIVE_ENTITIES]
                    + _many_negatives(amazon_ads.MAX_ACCOUNT_NEGATIVES))

    payload = _structure(rest, entity="negatives", limit=1)

    assert (payload["total"], payload["showing"]) == (amazon_ads.MAX_ACCOUNT_NEGATIVES, 1)
    assert rest.row_reads() == [(["campaign", *NEGATIVE_ENTITIES], None)]


def test_a_page_says_there_are_more_rows_and_where_the_next_one_starts():
    payload = _structure(entity="keywords", limit=1)

    assert (payload["total"], payload["showing"]) == (2, 1)
    assert "offset=1" in payload["note"]
    assert [row["target"] for row in _structure(entity="keywords", offset=1, limit=1)["rows"]] == ["demo lotion"]


def test_a_page_of_keywords_fits_with_its_context_under_the_provider_cut():
    keywords = [_target(KEYWORD, "11", EXACT, "21", "AG - core", str(9500 + index), f"demo cream term {index}",
                        match_type="EXACT", default_bid="0.8", bid="0.8") for index in range(120)]
    rest = FakeRest([row for row in STRUCTURE if row["entity"] != KEYWORD] + keywords)

    payload = _structure(rest, entity="keywords")

    assert len(json.dumps(payload, ensure_ascii=False, indent=2)) <= MAX_TEXT_CHARS
    assert payload["total"] == 120 and 0 < payload["showing"] < 50
    assert f"offset={payload['showing']}" in payload["note"]


def test_the_window_comes_from_the_campaign_sync_and_the_days_on_screen_are_read_exactly():
    rest = FakeRest()

    assert _structure(rest)["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}
    _structure(rest, date_from="2026-09-12", date_to="2026-09-16")

    assert [(name, args["p_from"], args["p_to"]) for name, args in rest.reads] == [
        (STRUCTURE_COUNTS_RPC, "2026-09-10", "2026-09-16"), (STRUCTURE_RPC, "2026-09-10", "2026-09-16"),
        (STRUCTURE_COUNTS_RPC, "2026-09-12", "2026-09-16"), (STRUCTURE_RPC, "2026-09-12", "2026-09-16")]
    # Without a campaign filter the whole account is counted and read.
    assert all(set(args) <= {"p_profile_id", "p_from", "p_to", "p_entities"} for _, args in rest.reads)


def test_the_whole_payload_is_plain_json_with_its_source_and_currency():
    for entity in amazon_ads.STRUCTURE_ENTITIES:
        payload = _structure(entity=entity)
        json.dumps(payload)
        assert payload["source"] == amazon_ads.STRUCTURE_SOURCE
        assert (payload["currency"], payload["attribution_days"]) == ("USD", 7)


def test_an_unknown_entity_or_state_is_refused():
    with pytest.raises(ValueError, match="entity"):
        _structure(entity="bids")
    with pytest.raises(ValueError, match="state"):
        _structure(state="deleted")


def test_the_chat_is_told_the_graduation_bid_is_the_effective_one_and_paused_ad_groups_are_left_out():
    idle = {tool["name"]: tool for tool in server.build_tools(object())}["idle_targets"]["description"]
    prompt = (Path(__file__).resolve().parents[1] / "ai/agents/orchestrator/prompt.md").read_text(encoding="utf-8")

    for text in (amazon_ads.TARGETS_SOURCE, idle, amazon_ads.idle_targets.__doc__):
        assert "efectivo" in text and "listados como pausados" in text
    # The ad group listing asks only for enabled and paused ones: an archived ad group is never known as such.
    for text in (amazon_ads.TARGETS_SOURCE, idle, amazon_ads.idle_targets.__doc__, prompt):
        assert "archivados no se miran" not in text and "archivados quedan afuera" not in text
    assert "ad groups de Sponsored Products listados como pausados no se miran" in prompt


def test_the_chat_is_told_how_to_find_a_keyword_and_that_it_runs_only_with_its_campaign():
    description = {tool["name"]: tool for tool in server.build_tools(object())}["campaign_structure"]["description"]
    prompt = (Path(__file__).resolve().parents[1] / "ai/agents/orchestrator/prompt.md").read_text(encoding="utf-8")

    assert "target deja los keywords, product targets o negativos que contienen ese texto" in description
    assert "o los product ads con ese ASIN o SKU" in description and "si un ASIN es suyo" in description
    assert "exact_matches dice cuántos son" in description
    assert "en cuántos lugares está ese keyword lo dice `exact_matches`, no el total de filas" in prompt
    for text in (description, amazon_ads.STRUCTURE_SOURCE):
        assert "campaign_state" in text and "corren sólo si ellos y su campaña están habilitados" in text
    assert "`campaign_structure` con `entity`=keywords y `target` dice si la cuenta tiene una keyword" in prompt
    assert "una keyword habilitada de una campaña pausada no corre" in prompt


def test_the_chat_is_told_a_big_accounts_negatives_come_per_campaign():
    description = {tool["name"]: tool for tool in server.build_tools(object())}["campaign_structure"]["description"]
    prompt = (Path(__file__).resolve().parents[1] / "ai/agents/orchestrator/prompt.md").read_text(encoding="utf-8")

    assert (f"Más de {amazon_ads.MAX_ACCOUNT_NEGATIVES} negativos los da sólo de a una campaña: sin campaign, o con "
            "uno que abarca varias campañas, negatives vuelve con counts y sin filas.") in description
    assert "Los negativos de una cuenta grande se piden de a una campaña" in prompt
    assert "Si ninguna campaña coincide con `campaign`, la respuesta no trae `counts`" in prompt
