"""daily_metrics: the series the chat needs to draw how an account, a product or a campaign is doing."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone

import pytest

from services.mcp_server.tools import amazon_ads

PROFILE = {
    "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo LLC",
    "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "", "status": "active",
    "data_from": "2026-08-01", "data_through": "2026-09-16", "refreshed_on": "2026-09-17",
    "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": "",
}
# The campaign sync the window ends at: a nightly request of the last week, over the 65 days its history keeps.
CAMPAIGN_JOB = {"id": 441, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns", "trigger": "scheduled_daily",
                "external_account_id": "1111222233334444", "status": "completed", "window_start": "2026-09-10",
                "window_end": "2026-09-16", "local_day": "2026-09-17", "finished_at": "2026-09-17T11:05:00+00:00",
                "created_at": "2026-09-17T10:43:00+00:00"}
PRODUCT_HEADER = ["ad_product", "campaign_id", "name", "state", "start_date", "budget_amount", "budget_type",
                  "cost_type", "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy", "metrics_known",
                  "impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
                  "viewable_impressions", "currency_code"]


class _FakeRest:
    def __init__(self, days=None, profile=None, products=(), term_days=None, campaigns_synced=True):
        self._days = list(days or [])
        self._term_days = list(term_days or [])
        self._profile = profile or PROFILE
        self._products = list(products)
        self._campaigns_synced = campaigns_synced
        self.rpc_calls: list[dict] = []
        self.rpc_names: list[str] = []

    def select(self, table, params):
        if table == "integration_sync_jobs":
            synced = self._campaigns_synced and params.get("job_kind") == "eq.sp_campaigns"
            return [dict(CAMPAIGN_JOB)] if synced else []
        return [self._profile]

    def rpc(self, name, args, *, timeout_s=8):
        assert name in ("campaign_daily_totals", "ads_daily_totals")
        self.rpc_calls.append(args)
        self.rpc_names.append(name)
        return self._days if name == "campaign_daily_totals" else self._term_days

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "product_campaigns_between"
        if not self._products:
            return b""
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=PRODUCT_HEADER)
        writer.writeheader()
        writer.writerows(self._products)
        return buffer.getvalue().encode("utf-8")


def _day(day: str, ad_product: str = "SP", **overrides) -> dict:
    row = {"report_date": day, "ad_product": ad_product, "impressions": 1000, "clicks": 40, "cost": 30.0,
           "purchases_7d": 4, "sales_7d": 120.0, "purchases_14d": 6, "sales_14d": 200.0, "purchases": 0, "sales": 0,
           "purchases_clicks": 0, "sales_clicks": 0, "currency_code": "USD", "campaign_names": None}
    if ad_product != "SP":
        row.update({"purchases_7d": 0, "sales_7d": 0, "purchases_14d": 0, "sales_14d": 0, "purchases": 5,
                    "sales": 150.0, "purchases_clicks": 2, "sales_clicks": 60.0})
    row.update(overrides)
    return row


def _term_day(day: str, **overrides) -> dict:
    """A day of SP summed from the search terms: fewer impressions, the terms without clicks are not there."""
    row = {"report_date": day, "impressions": 400, "clicks": 40, "cost": 30.0, "purchases_7d": 4, "sales_7d": 120.0,
           "purchases_14d": 6, "sales_14d": 200.0, "currency_code": "USD", "campaign_names": None}
    row.update(overrides)
    return row


def test_each_day_carries_the_metrics_the_chat_can_draw():
    rest = _FakeRest([_day("2026-09-16")])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)

    assert payload["rows"] == [{"date": "2026-09-16", "spend": 30.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                "impressions": 1000, "acos": 25.0, "cvr": 10.0, "sales_clicks": 120.0,
                                "orders_clicks": 4}]
    assert payload["currency"] == "USD" and payload["attribution_days"] == 7
    assert payload["products"] == ["SP"]


def test_sb_and_sd_days_add_up_with_sp_in_campaign_managers_attribution():
    rest = _FakeRest([_day("2026-09-16"), _day("2026-09-16", "SB"), _day("2026-09-16", "SD", cost=10.0)])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)

    [row] = payload["rows"]
    assert (row["spend"], row["sales"], row["orders"]) == (70.0, 420.0, 14)
    # Click-only: SP's own, plus what SB and SD sold after a click.
    assert (row["sales_clicks"], row["orders_clicks"]) == (240.0, 8)
    assert payload["products"] == ["SP", "SB", "SD"]


def test_a_product_narrows_the_series_to_it():
    rest = _FakeRest([_day("2026-09-16"), _day("2026-09-16", "SB")])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, product="SB")

    assert (payload["rows"][0]["spend"], payload["rows"][0]["sales"]) == (30.0, 150.0)
    assert payload["products"] == ["SB"]


def test_an_unknown_product_is_refused():
    with pytest.raises(ValueError, match="product"):
        amazon_ads.daily_metrics(_FakeRest(), profile_id="1111222233334444", product="DSP")


def test_a_day_without_sales_has_no_acos_and_a_day_without_clicks_has_no_cvr():
    rest = _FakeRest([_day("2026-09-15", sales_7d=0, purchases_7d=0)])

    rows = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=2)["rows"]

    assert rows[0]["acos"] is None and rows[0]["cvr"] == 0.0
    assert rows[1] == {"date": "2026-09-16", "spend": 0.0, "sales": 0.0, "orders": 0, "clicks": 0,
                       "impressions": 0, "acos": None, "cvr": None, "sales_clicks": 0.0, "orders_clicks": 0}


def test_the_window_ends_on_the_last_synced_day_and_defaults_to_two_weeks():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444")

    assert rest.rpc_calls[0]["p_from"] == "2026-09-03" and rest.rpc_calls[0]["p_to"] == "2026-09-16"
    assert payload["window"] == {"from": "2026-09-03", "to": "2026-09-16", "days": 14}
    assert len(payload["rows"]) == 14


def test_the_campaign_window_is_capped_at_sixty_days_even_after_a_nightly_week():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=365)

    assert payload["window"]["days"] == 60
    assert "window_note" in payload


def test_the_search_term_window_is_clipped_to_what_the_account_has_synced():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=365, source="search_terms")

    assert payload["window"]["days"] == 47           # data_from 01/08 → 16/09, under the 60-day cap
    assert "window_note" in payload


def test_a_campaign_filter_names_the_campaigns_it_summed():
    rest = _FakeRest([_day("2026-09-16", campaign_names=["Demo - SP - KW - EXACT - cuchillo"])])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo")

    assert rest.rpc_calls[0]["p_campaign"] == "cuchillo"
    assert payload["campaigns"] == ["Demo - SP - KW - EXACT - cuchillo"]


def test_the_campaigns_it_summed_are_those_in_the_reports_not_every_one_with_that_name():
    """Counted as the account's campaigns, 41 with data would read as the account having 41, when it lists 121."""
    rest = _FakeRest([_day("2026-09-16", campaign_names=["Demo - SP - KW - EXACT - cuchillo"])])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo")

    assert payload["campaigns_note"] == (
        "Son las campañas con «cuchillo» en el nombre que figuran en los reportes de estos días, no todas las que la "
        "cuenta tiene con ese nombre: las que no tuvieron actividad pueden no figurar. Cuántas tiene la cuenta lo dice "
        "campaign_structure.")


def test_a_campaign_that_matches_nothing_returns_no_days_instead_of_a_series_of_zeros():
    """A row of zeros would read as a campaign that stopped spending, not as a name that matched nothing."""
    payload = amazon_ads.daily_metrics(_FakeRest([]), profile_id="1111222233334444", days=7, campaign="inexistente")

    assert payload["rows"] == [] and payload["campaigns"] == []
    assert "inexistente" in payload["note"] and "campaigns_note" not in payload


def test_a_short_fragment_that_matches_many_campaigns_lists_a_bounded_number_of_them():
    names = [f"Campaña {n:03d}" for n in range(amazon_ads.MAX_CAMPAIGNS_LISTED + 10)]
    rest = _FakeRest([_day("2026-09-16", campaign_names=names)])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="Campaña")

    assert len(payload["campaigns"]) == amazon_ads.MAX_CAMPAIGNS_LISTED
    assert payload["campaigns_total"] == len(names)


def test_the_series_says_which_products_it_covers_and_how_each_counts_a_sale():
    """The model must not compare an SB ACoS with an SP one as if both counted sales alike."""
    payload = amazon_ads.daily_metrics(_FakeRest(), profile_id="1111222233334444", days=1)

    assert "Sponsored Products, Brands y Display" in payload["source"]
    assert "después de un click o una vista" in payload["source"]


def test_old_format_sb_campaigns_without_metrics_are_named_as_missing_from_the_series():
    legacy = {field: "" for field in PRODUCT_HEADER} | {
        "ad_product": "SB", "campaign_id": "702", "name": "Brand Legacy", "state": "ENABLED",
        "is_multi_ad_groups": "f", "metrics_known": "f", "impressions": "0", "clicks": "0", "cost": "0",
        "purchases": "0", "sales": "0", "purchases_clicks": "0", "sales_clicks": "0", "viewable_impressions": "0"}

    payload = amazon_ads.daily_metrics(_FakeRest(products=[legacy]), profile_id="1111222233334444", days=1)

    assert payload["old_format_note"].startswith("1 campaña SB del formato anterior todavía no tiene métricas")


def test_a_vendor_account_reads_fourteen_day_attribution():
    rest = _FakeRest([_day("2026-09-16")], profile={**PROFILE, "account_type": "vendor"})

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)

    assert payload["rows"][0]["orders"] == 6 and payload["attribution_days"] == 14


def test_the_campaign_series_tells_how_to_ask_for_sp_summed_from_the_search_terms():
    """Both figures of SP are data the chat can offer: the campaign reports' never hides the search terms'."""
    payload = amazon_ads.daily_metrics(_FakeRest([_day("2026-09-16")]), profile_id="1111222233334444", days=1)

    assert payload["data_source"] == "campaigns"
    assert "source=search_terms" in payload["alternative"] and "menos impresiones" in payload["alternative"]


def test_sp_summed_from_the_search_terms_is_still_there_on_request():
    rest = _FakeRest([_day("2026-09-16")], term_days=[_term_day("2026-09-16")])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, source="search_terms")

    assert rest.rpc_names == ["ads_daily_totals"]
    assert payload["rows"] == [{"date": "2026-09-16", "spend": 30.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                "impressions": 400, "acos": 25.0, "cvr": 10.0}]
    assert payload["data_source"] == "search_terms" and payload["products"] == ["SP"]
    assert "search terms" in payload["source"] and "source=campaigns" in payload["alternative"]


def test_a_campaign_filter_also_works_on_the_search_terms():
    rest = _FakeRest(term_days=[_term_day("2026-09-16", campaign_names=["Demo - SP - KW - EXACT - cuchillo"])])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo",
                                       source="search_terms")

    assert rest.rpc_calls[0]["p_campaign"] == "cuchillo"
    assert payload["campaigns"] == ["Demo - SP - KW - EXACT - cuchillo"]


def test_each_source_ends_on_its_own_last_synced_day():
    """The search terms can be a day ahead of the campaign sync: each window is the one of its own data."""
    rest = _FakeRest(profile={**PROFILE, "data_through": "2026-09-17"})

    campaigns = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)
    terms = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, source="search_terms")

    assert campaigns["window"]["to"] == "2026-09-16" and terms["window"]["to"] == "2026-09-17"


def test_an_account_whose_campaigns_are_not_synced_yet_points_to_its_search_terms():
    rest = _FakeRest(term_days=[_term_day("2026-09-16")], campaigns_synced=False)

    with pytest.raises(ValueError, match="todavía no tiene campañas sincronizadas.*source=search_terms"):
        amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)
    assert amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1,
                                    source="search_terms")["rows"][0]["spend"] == 30.0


def test_an_sb_or_sd_series_offers_no_search_term_figures_because_there_are_none():
    payload = amazon_ads.daily_metrics(_FakeRest([_day("2026-09-16", "SB")]), profile_id="1111222233334444", days=1,
                                       product="SB")

    assert "alternative" not in payload


def test_the_search_terms_refuse_brands_and_display():
    with pytest.raises(ValueError, match="sólo son de Sponsored Products"):
        amazon_ads.daily_metrics(_FakeRest(), profile_id="1111222233334444", product="SB", source="search_terms")


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError, match="campaigns, search_terms"):
        amazon_ads.daily_metrics(_FakeRest(), profile_id="1111222233334444", source="business_report")


def test_the_window_helper_is_shared_with_top_search_terms():
    profile = amazon_ads.ReportProvider(_FakeRest()).profiles()[0]

    assert amazon_ads.window_for(profile, 7) == (date(2026, 9, 10), date(2026, 9, 16))
    assert amazon_ads.window_for(profile, 0) == (date(2026, 9, 16), date(2026, 9, 16))


@pytest.mark.parametrize("now, today, up_to_date", [
    # 02:00 UTC on the 18th is still the 17th in Los Angeles: data through the 16th is up to date.
    (datetime(2026, 9, 18, 2, 0, tzinfo=timezone.utc), "2026-09-17", True),
    (datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), "2026-09-18", False),
])
def test_each_account_says_its_own_today_and_whether_its_data_is_up_to_date(monkeypatch, now, today, up_to_date):
    monkeypatch.setattr(amazon_ads, "_now", lambda: now)

    (row,) = amazon_ads.list_accounts(_FakeRest())["rows"]

    assert (row["today"], row["up_to_date"]) == (today, up_to_date)


def test_a_calendar_month_returns_its_own_days_even_when_they_are_not_the_last_ones():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", date_from="2026-08-01",
                                       date_to="2026-08-31")

    assert (rest.rpc_calls[0]["p_from"], rest.rpc_calls[0]["p_to"]) == ("2026-08-01", "2026-08-31")
    assert payload["window"] == {"from": "2026-08-01", "to": "2026-08-31", "days": 31}
    assert len(payload["rows"]) == 31 and "window_note" not in payload


class _ManyAccounts(_FakeRest):
    """An agency with more accounts than one answer can carry."""

    def __init__(self, count: int):
        super().__init__([_day("2026-09-16")])
        self.profiles = [{**PROFILE, "profile_id": f"{5000 + n}", "cliente": f"Marca {n:03d}"} for n in range(count)]

    def select(self, table, params):
        return super().select(table, params) if table == "integration_sync_jobs" else self.profiles


def test_a_long_account_list_comes_in_pages_that_together_name_every_account():
    """The chat said «there are 52 and I could bring 45»: the rest has to be one call away."""
    rest = _ManyAccounts(120)

    first = amazon_ads.list_accounts(rest)
    assert first["total"] == 120 and first["showing"] < 120
    assert f"offset={first['showing']}" in first["note"]

    seen = [row["profile_id"] for row in first["rows"]]
    while len(seen) < first["total"]:
        seen += [row["profile_id"] for row in amazon_ads.list_accounts(rest, offset=len(seen))["rows"]]
    assert sorted(seen) == sorted(profile["profile_id"] for profile in rest.profiles)


def test_the_overview_of_many_accounts_comes_in_pages_and_says_how_to_ask_for_the_rest():
    """«Sólo pude ver 31 de las 52»: the currency warning used to overwrite the note that points to the next page."""
    rest = _ManyAccounts(120)

    first = amazon_ads.accounts_overview(rest, days=1)
    assert first["total"] == 120 and first["showing"] < 120
    assert f"offset={first['showing']}" in first["note"] and "moneda" in first["note"]

    second = amazon_ads.accounts_overview(rest, days=1, offset=first["showing"])
    assert second["offset"] == first["showing"]
    assert {row["profile_id"] for row in first["rows"]}.isdisjoint(row["profile_id"] for row in second["rows"])
