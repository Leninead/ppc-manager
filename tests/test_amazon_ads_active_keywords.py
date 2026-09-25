"""Which SP keywords run, from the structure listing with their campaign and ad group states. No network."""
import csv
import io
from datetime import date

from core.amazon_ads.active_keywords import active_keyword_texts, normalized_keyword
from core.amazon_ads.report_provider import ProfileOption
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    CAMPAIGN,
    KEYWORD,
    PRODUCT_TARGETING,
    ROW_COLUMNS,
    StructureProvider,
)

DAY = date(2026, 9, 24)
LISTED = "2026-09-24 06:00:01+00"
PROFILE = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Luna", "country_code": "US",
                                  "currency_code": "USD", "account_type": "seller"})


class _FakeRest:
    def __init__(self, rows):
        self._rows = rows

    def rpc_csv(self, name, args, *, timeout_s=8):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(ROW_COLUMNS))
        writer.writeheader()
        writer.writerows(self._rows)
        return buffer.getvalue().encode("utf-8")


def _row(entity, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "state": "ENABLED", "metrics_known": "f", "listed_at": LISTED})
    row.update(values)
    return row


def _campaign(campaign_id, state="ENABLED") -> dict:
    return _row(CAMPAIGN, campaign_id=campaign_id, entity_id=campaign_id, state=state)


def _ad_group(ad_group_id, campaign_id="1", state="ENABLED") -> dict:
    return _row(AD_GROUP, campaign_id=campaign_id, ad_group_id=ad_group_id, entity_id=ad_group_id, state=state)


def _keyword(text, *, campaign_id="1", ad_group_id="10", state="ENABLED", match_type="EXACT") -> dict:
    return _row(KEYWORD, campaign_id=campaign_id, ad_group_id=ad_group_id, entity_id=f"{text}-{match_type}",
                target_kind="keyword", target_text=text, match_type=match_type, state=state)


def _active(*rows) -> frozenset[str]:
    structure = StructureProvider(_FakeRest(list(rows))).sp_structure(PROFILE, DAY, DAY)
    return active_keyword_texts(structure.rows)


def test_a_keyword_runs_when_it_its_campaign_and_its_ad_group_are_enabled():
    assert _active(_campaign("1"), _ad_group("10"), _keyword("vitamin a cream")) == {"vitamin a cream"}


def test_a_paused_or_archived_keyword_does_not_run():
    active = _active(_campaign("1"), _ad_group("10"), _keyword("paused one", state="PAUSED"),
                     _keyword("archived one", state="ARCHIVED"), _keyword("live one"))

    assert active == {"live one"}


def test_a_keyword_of_a_paused_archived_or_unlisted_campaign_does_not_run():
    active = _active(_campaign("1", state="PAUSED"), _campaign("2", state="ARCHIVED"),
                     _keyword("in paused", campaign_id="1"), _keyword("in archived", campaign_id="2"),
                     _keyword("in unlisted", campaign_id="3"))

    assert active == frozenset()


def test_a_paused_ad_group_stops_its_keywords_and_an_unlisted_one_counts_as_enabled():
    active = _active(_campaign("1"), _ad_group("10", state="PAUSED"),
                     _keyword("in paused ad group", ad_group_id="10"), _keyword("in unlisted ad group", ad_group_id="11"))

    assert active == {"in unlisted ad group"}


def test_the_text_is_case_folded_with_single_spaces_whatever_the_match_type():
    active = _active(_campaign("1"), _ad_group("10"), _keyword("Vitamin A  Cream", match_type="BROAD"),
                     _keyword("vitamin a cream", match_type="PHRASE"), _keyword("  ", match_type="EXACT"))

    assert active == {"vitamin a cream"}


def test_product_targets_are_not_keywords():
    target = _row(PRODUCT_TARGETING, campaign_id="1", ad_group_id="10", entity_id="t-1", target_kind="product",
                  target_text='asin="B0CYLMJJJC"')

    assert _active(_campaign("1"), _ad_group("10"), target) == frozenset()


def test_normalized_keyword_is_the_form_both_sides_are_compared_in():
    assert normalized_keyword("  Crema  Vitamina A ") == "crema vitamina a"
    assert normalized_keyword("STRASSE") == normalized_keyword("straße")
