"""daily_metrics: the series the chat needs to draw how an account, a product or a campaign is doing."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone

import pytest

from services.mcp_server.tools import amazon_ads, daily_series
from services.mcp_server.tools.campaign_selector import MAX_CAMPAIGNS_LISTED

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


CATALOG_HEADER = ["ad_product", "campaign_id", "name", "state", "portfolio_id", "portfolio_name", "budget_amount",
                  "budget_type"]
BY_CAMPAIGN_RPCS = ("campaign_daily_totals_by_campaign", "ads_daily_totals_by_campaign")


class _FakeRest:
    def __init__(self, days=None, profile=None, products=(), term_days=None, campaigns_synced=True, listed=(),
                 campaign_days=(), term_campaign_days=()):
        self._days = list(days or [])
        self._term_days = list(term_days or [])
        self._profile = profile or PROFILE
        self._products = list(products)
        self._campaigns_synced = campaigns_synced
        # The campaigns of the account's last listing, and each one's days in the campaign reports and search terms.
        self._listed = list(listed)
        self._campaign_days = list(campaign_days)
        self._term_campaign_days = list(term_campaign_days)
        self.rpc_calls: list[dict] = []
        self.rpc_names: list[str] = []

    def select(self, table, params):
        if table == "integration_sync_jobs":
            synced = self._campaigns_synced and params.get("job_kind") == "eq.sp_campaigns"
            return [dict(CAMPAIGN_JOB)] if synced else []
        return [self._profile]

    def rpc(self, name, args, *, timeout_s=8):
        assert name in ("campaign_daily_totals", "ads_daily_totals", *BY_CAMPAIGN_RPCS)
        self.rpc_calls.append(args)
        self.rpc_names.append(name)
        if name in BY_CAMPAIGN_RPCS:
            rows = self._campaign_days if name == BY_CAMPAIGN_RPCS[0] else self._term_campaign_days
            return [row for row in rows if row["campaign_id"] in args["p_campaign_ids"]]
        return self._days if name == "campaign_daily_totals" else self._term_days

    def rpc_csv(self, name, args, *, timeout_s=8):
        if name == "campaign_catalog":
            return _csv(CATALOG_HEADER, self._listed)
        if name == "campaign_window_totals":
            return b""
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


def _csv(header, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _listed(campaign_id: str, name: str, ad_product: str = "SP", state: str = "ENABLED") -> dict:
    return {"ad_product": ad_product, "campaign_id": campaign_id, "name": name, "state": state, "portfolio_id": "",
            "portfolio_name": "", "budget_amount": 20.0, "budget_type": "DAILY"}


def _campaign_day(day: str, campaign_id: str, ad_product: str = "SP", **overrides) -> dict:
    """One campaign's day, as the by-campaign read answers it."""
    row = {key: value for key, value in _day(day, ad_product, **overrides).items() if key != "campaign_names"}
    return {**row, "campaign_id": campaign_id, "new_to_brand_purchases": None, "new_to_brand_sales": None}


def _term_day(day: str, **overrides) -> dict:
    """A day of SP summed from the search terms: fewer impressions, the terms without clicks are not there."""
    row = {"report_date": day, "impressions": 400, "clicks": 40, "cost": 30.0, "purchases_7d": 4, "sales_7d": 120.0,
           "purchases_14d": 6, "sales_14d": 200.0, "currency_code": "USD", "campaign_names": None}
    row.update(overrides)
    return row


def test_each_day_carries_the_metrics_the_chat_can_draw():
    rest = _FakeRest([_day("2026-09-16")])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1)

    # 16/09/2026 is a Wednesday: the name comes with the date so the chat never works it out.
    assert payload["rows"] == [{"date": "2026-09-16", "weekday": "miércoles", "spend": 30.0, "sales": 120.0,
                                "orders": 4, "clicks": 40, "impressions": 1000, "acos": 25.0, "cvr": 10.0,
                                "roas": 4.0, "cpc": 0.75, "sales_clicks": 120.0, "orders_clicks": 4}]
    assert payload["currency"] == "USD" and payload["attribution_days"] == {"SP": 7}
    assert payload["products"] == ["SP"]


def test_sb_and_sd_days_add_up_with_sp_in_campaign_managers_attribution():
    rest = _FakeRest([_day("2026-09-16"), _day("2026-09-16", "SB"), _day("2026-09-16", "SD", cost=10.0)])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1)

    [row] = payload["rows"]
    assert (row["spend"], row["sales"], row["orders"]) == (70.0, 420.0, 14)
    # Click-only: SP's own, plus what SB and SD sold after a click.
    assert (row["sales_clicks"], row["orders_clicks"]) == (240.0, 8)
    assert payload["products"] == ["SP", "SB", "SD"]


def test_a_product_narrows_the_series_to_it():
    rest = _FakeRest([_day("2026-09-16"), _day("2026-09-16", "SB")])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, product="SB")

    assert (payload["rows"][0]["spend"], payload["rows"][0]["sales"]) == (30.0, 150.0)
    assert payload["products"] == ["SB"]


def test_an_unknown_product_is_refused():
    with pytest.raises(ValueError, match="product"):
        daily_series.daily_metrics(_FakeRest(), profile_id="1111222233334444", product="DSP")


def test_a_day_without_sales_has_no_acos_and_a_day_without_clicks_has_no_cvr():
    rest = _FakeRest([_day("2026-09-15", sales_7d=0, purchases_7d=0)])

    rows = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=2)["rows"]

    assert rows[0]["acos"] is None and rows[0]["cvr"] == 0.0
    assert rows[1] == {"date": "2026-09-16", "weekday": "miércoles", "spend": 0.0, "sales": 0.0, "orders": 0,
                       "clicks": 0, "impressions": 0, "acos": None, "cvr": None, "roas": None, "cpc": None,
                       "sales_clicks": 0.0, "orders_clicks": 0}


def test_the_window_ends_on_the_last_synced_day_and_defaults_to_two_weeks():
    rest = _FakeRest()

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444")

    # One read covers the window and the days before it that before_window and activity look at.
    assert rest.rpc_calls[0]["p_from"] <= "2026-09-03" and rest.rpc_calls[0]["p_to"] == "2026-09-16"
    assert payload["window"] == {"from": "2026-09-03", "to": "2026-09-16", "days": 14}
    assert len(payload["rows"]) == 14


def test_the_campaign_window_is_capped_at_sixty_days_even_after_a_nightly_week():
    rest = _FakeRest()

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=365)

    assert payload["window"]["days"] == 60
    assert "window_note" in payload


def test_the_search_term_window_is_clipped_to_what_the_account_has_synced():
    rest = _FakeRest()

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=365, source="search_terms")

    assert payload["window"]["days"] == 47           # data_from 01/08 → 16/09, under the 60-day cap
    assert "window_note" in payload


def test_a_campaign_filter_names_the_campaigns_it_summed_and_reads_them_by_id():
    rest = _FakeRest(listed=[_listed("301", "Demo - SP - KW - EXACT - cuchillo"), _listed("302", "Demo - SP - AUTO")],
                     campaign_days=[_campaign_day("2026-09-16", "301"), _campaign_day("2026-09-16", "302")])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo")

    by_campaign = [args for name, args in zip(rest.rpc_names, rest.rpc_calls) if name in BY_CAMPAIGN_RPCS]
    assert {tuple(args["p_campaign_ids"]) for args in by_campaign} == {("301",)}
    assert [campaign["campaign"] for campaign in payload["matched_campaigns"]] == [
        "Demo - SP - KW - EXACT - cuchillo"]
    assert payload["campaign_match"] == "contiene" and payload["rows"][0]["spend"] == 30.0


def test_a_listed_campaign_that_did_not_run_is_named_and_counted_apart():
    """Counted from the reports, 41 campaigns with data read as the account having 41, when it lists 121."""
    rest = _FakeRest(listed=[_listed("301", "cuchillo chef"), _listed("303", "cuchillo pan")],
                     campaign_days=[_campaign_day("2026-09-16", "301")])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo")

    assert len(payload["matched_campaigns"]) == 2
    assert [row["campaign_id"] for row in payload["by_campaign"]] == ["301"]
    assert payload["campaigns_note"].endswith("1 de ellas no tuvieron actividad en la ventana.")


def test_an_exact_campaign_name_reads_that_campaign_alone_and_a_part_of_a_name_sums_each_one_apart():
    """A campaign's name matched its 5 siblings too and the chat read the sum as that one campaign alone."""
    rest = _FakeRest(listed=[_listed("401", "Demo - SP - AUTO"), _listed("402", "Demo - SP - AUTO - BROAD")],
                     campaign_days=[_campaign_day("2026-09-16", "401"), _campaign_day("2026-09-16", "402", cost=10.0)])

    exact = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="Demo - SP - AUTO")
    several = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="Demo - SP")

    assert [campaign["campaign_id"] for campaign in exact["matched_campaigns"]] == ["401"]
    assert exact["campaign_match"] == "exacto" and exact["rows"][0]["spend"] == 30.0 and "by_campaign" not in exact
    assert several["campaign_match"] == "contiene" and several["rows"][0]["spend"] == 40.0
    assert [(row["campaign_id"], row["spend"]) for row in several["by_campaign"]] == [("401", 30.0), ("402", 10.0)]
    assert several["campaigns_note"].startswith("Cada fila suma las 2 campañas de matched_campaigns, no una sola")


def test_a_campaign_that_matches_nothing_returns_no_days_instead_of_a_series_of_zeros():
    """A row of zeros would read as a campaign that stopped spending, not as a name that matched nothing."""
    payload = daily_series.daily_metrics(_FakeRest(listed=[_listed("301", "Demo - SP - AUTO")]),
                                         profile_id="1111222233334444", days=7, campaign="inexistente")

    assert payload["rows"] == [] and payload["matched_campaigns"] == []
    assert "inexistente" in payload["note"] and "by_campaign" not in payload


def test_a_short_fragment_that_matches_many_campaigns_lists_a_bounded_number_of_them():
    listed = [_listed(str(500 + n), f"Campaña {n:03d}") for n in range(MAX_CAMPAIGNS_LISTED + 10)]
    rest = _FakeRest(listed=listed)

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="Campaña")

    assert len(payload["matched_campaigns"]) == MAX_CAMPAIGNS_LISTED
    assert payload["matched_campaigns_total"] == len(listed)


def test_the_series_says_which_products_it_covers_and_how_each_counts_a_sale():
    """The model must not compare an SB ACoS with an SP one as if both counted sales alike."""
    payload = daily_series.daily_metrics(_FakeRest(), profile_id="1111222233334444", days=1)

    assert "Sponsored Products, Brands y Display" in payload["source"]
    assert "después de un click o una vista" in payload["source"]


def test_old_format_sb_campaigns_without_metrics_are_named_as_missing_from_the_series():
    legacy = {field: "" for field in PRODUCT_HEADER} | {
        "ad_product": "SB", "campaign_id": "702", "name": "Brand Legacy", "state": "ENABLED",
        "is_multi_ad_groups": "f", "metrics_known": "f", "impressions": "0", "clicks": "0", "cost": "0",
        "purchases": "0", "sales": "0", "purchases_clicks": "0", "sales_clicks": "0", "viewable_impressions": "0"}

    payload = daily_series.daily_metrics(_FakeRest(products=[legacy]), profile_id="1111222233334444", days=1)

    assert payload["old_format_note"].startswith("1 campaña SB del formato anterior todavía no tiene métricas")


def test_a_vendor_account_reads_fourteen_day_attribution():
    rest = _FakeRest([_day("2026-09-16")], profile={**PROFILE, "account_type": "vendor"})

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1)

    assert payload["rows"][0]["orders"] == 6 and payload["attribution_days"] == {"SP": 14}


def test_the_campaign_series_tells_how_to_ask_for_sp_summed_from_the_search_terms():
    """Both figures of SP are data the chat can offer: the campaign reports' never hides the search terms'."""
    payload = daily_series.daily_metrics(_FakeRest([_day("2026-09-16")]), profile_id="1111222233334444", days=1)

    assert payload["data_source"] == "campaigns"
    assert "source=search_terms" in payload["alternative"] and "menos impresiones" in payload["alternative"]


def test_sp_summed_from_the_search_terms_is_still_there_on_request():
    rest = _FakeRest([_day("2026-09-16")], term_days=[_term_day("2026-09-16")])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, source="search_terms")

    assert rest.rpc_names == ["ads_daily_totals"]
    assert payload["rows"] == [{"date": "2026-09-16", "weekday": "miércoles", "spend": 30.0, "sales": 120.0,
                                "orders": 4, "clicks": 40, "impressions": 400, "acos": 25.0, "cvr": 10.0,
                                "roas": 4.0, "cpc": 0.75}]
    assert payload["data_source"] == "search_terms" and payload["products"] == ["SP"]
    assert "search terms" in payload["source"] and "source=campaigns" in payload["alternative"]


def test_a_campaign_filter_also_works_on_the_search_terms():
    term_day = {key: value for key, value in _term_day("2026-09-16").items() if key != "campaign_names"}
    rest = _FakeRest(listed=[_listed("301", "Demo - SP - KW - EXACT - cuchillo")],
                     term_campaign_days=[{**term_day, "campaign_id": "301"}])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo",
                                         source="search_terms")

    assert "ads_daily_totals_by_campaign" in rest.rpc_names
    assert [campaign["campaign"] for campaign in payload["matched_campaigns"]] == [
        "Demo - SP - KW - EXACT - cuchillo"]
    assert payload["rows"][0]["impressions"] == 400


def test_each_source_ends_on_its_own_last_synced_day():
    """The search terms can be a day ahead of the campaign sync: each window is the one of its own data."""
    rest = _FakeRest(profile={**PROFILE, "data_through": "2026-09-17"})

    campaigns = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1)
    terms = daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1, source="search_terms")

    assert campaigns["window"]["to"] == "2026-09-16" and terms["window"]["to"] == "2026-09-17"


def test_an_account_whose_campaigns_are_not_synced_yet_points_to_its_search_terms():
    rest = _FakeRest(term_days=[_term_day("2026-09-16")], campaigns_synced=False)

    with pytest.raises(ValueError, match="todavía no tiene campañas sincronizadas.*source=search_terms"):
        daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1)
    assert daily_series.daily_metrics(rest, profile_id="1111222233334444", days=1,
                                    source="search_terms")["rows"][0]["spend"] == 30.0


def test_an_sb_or_sd_series_offers_no_search_term_figures_because_there_are_none():
    payload = daily_series.daily_metrics(_FakeRest([_day("2026-09-16", "SB")]), profile_id="1111222233334444", days=1,
                                       product="SB")

    assert "alternative" not in payload


def test_the_search_terms_refuse_brands_and_display():
    with pytest.raises(ValueError, match="sólo son de Sponsored Products"):
        daily_series.daily_metrics(_FakeRest(), profile_id="1111222233334444", product="SB", source="search_terms")


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError, match="campaigns, search_terms"):
        daily_series.daily_metrics(_FakeRest(), profile_id="1111222233334444", source="business_report")


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

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", date_from="2026-08-01",
                                       date_to="2026-08-31")

    assert rest.rpc_calls[0]["p_from"] <= "2026-08-01" and rest.rpc_calls[0]["p_to"] == "2026-08-31"
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


def test_an_account_name_finds_its_accounts_in_one_call_whatever_its_spacing_and_case():
    """Every answer opened by paging the account list to find one client: a third of those calls were repeats."""
    rest = _ManyAccounts(120)

    found = amazon_ads.list_accounts(rest, account="marca 07")
    assert found["total"] == 10
    assert all(row["account"].startswith("Marca 07") for row in found["rows"])
    assert amazon_ads.list_accounts(rest, account="MARCA-071")["total"] == 1
    assert "Ninguna cuenta" in amazon_ads.list_accounts(rest, account="nadie")["note"]


def test_the_overview_of_many_accounts_comes_in_pages_and_says_how_to_ask_for_the_rest():
    """«Sólo pude ver 31 de las 52»: the currency warning used to overwrite the note that points to the next page."""
    rest = _ManyAccounts(120)

    first = amazon_ads.accounts_overview(rest, days=1)
    assert first["total"] == 120 and first["showing"] < 120
    assert f"offset={first['showing']}" in first["note"] and "moneda" in first["note"]

    second = amazon_ads.accounts_overview(rest, days=1, offset=first["showing"])
    assert second["offset"] == first["showing"]
    assert {row["profile_id"] for row in first["rows"]}.isdisjoint(row["profile_id"] for row in second["rows"])


def test_the_series_carries_the_highest_and_lowest_day_before_its_window():
    """The chat said spend «never went over $23.20 until the 2nd» looking only at its window: 15/08 had $35.30."""
    rest = _FakeRest([_day("2026-09-01", cost=35.3), _day("2026-09-05", cost=5.0), _day("2026-09-16", cost=30.0)])

    payload = daily_series.daily_metrics(rest, profile_id="1111222233334444", date_from="2026-09-10",
                                       date_to="2026-09-16")
    before = payload["before_window"]

    assert before["to"] == "2026-09-09"
    assert (before["extremes"]["spend"]["max"], before["extremes"]["spend"]["max_date"]) == (35.3, "2026-09-01")
    assert before["extremes"]["spend"]["min"] == 0
    assert payload["before_window_note"] == daily_series.BEFORE_WINDOW_NOTE
    assert payload["rows"][-1]["spend"] == 30.0


# ── by week or month, when activity started, new-to-brand ────────────────────────────────────────────────────────────

def test_a_series_by_week_sums_monday_to_sunday_and_marks_the_week_in_course_incomplete():
    """#12 asked for each week in its own call."""
    days = [_day("2026-09-07"), _day("2026-09-13"), _day("2026-09-15", cost=10.0)]

    payload = daily_series.daily_metrics(_FakeRest(days), profile_id="1111222233334444", granularity="week",
                                         periods=2)

    assert [(row["period_start"], row["period_end"], row["days_with_data"], row["complete"], row["spend"])
            for row in payload["rows"]] == [("2026-09-07", "2026-09-13", 7, True, 60.0),
                                             ("2026-09-14", "2026-09-20", 3, False, 10.0)]
    assert payload["window"] == {"from": "2026-09-07", "to": "2026-09-16", "days": 10}
    assert payload["granularity"] == "week" and "lunes a domingo" in payload["period_note"]


def test_a_series_by_month_says_which_months_the_history_cuts():
    payload = daily_series.daily_metrics(_FakeRest([_day("2026-08-20")]), profile_id="1111222233334444",
                                         granularity="month", periods=4)

    months = [(row["period_start"], row["complete"], row["spend"]) for row in payload["rows"]]
    assert months == [("2026-06-01", False, 0.0), ("2026-07-01", False, 0.0), ("2026-08-01", True, 30.0),
                      ("2026-09-01", False, 0.0)]
    # The campaign sync keeps 65 days: the first months are not there, and the answer says so.
    assert payload["data_since"] == "2026-07-14" and "datos desde el 2026-07-14" in payload["window_note"]


def test_more_periods_than_the_cap_are_cut_and_said():
    payload = daily_series.daily_metrics(_FakeRest(), profile_id="1111222233334444", granularity="week", periods=40)

    assert len(payload["rows"]) == 26 and "el máximo es 26" in payload["window_note"]


def test_the_series_says_when_clicks_and_spend_started_over_the_days_it_read():
    """«Por primera vez» was said about a campaign whose spend started before the days the chat looked at."""
    days = [_day("2026-09-10", clicks=0, cost=0.0), _day("2026-09-12"), _day("2026-09-15"), _day("2026-09-16")]

    payload = daily_series.daily_metrics(_FakeRest(days), profile_id="1111222233334444", days=3)

    # 60 days before the window: the campaign sync keeps more, but before_window reads that far.
    assert payload["activity"]["read_from"] == "2026-07-16"
    assert payload["activity"]["clicks"] == {"first_day": "2026-09-12", "streak_start": "2026-09-15",
                                             "reaches_read_start": False}
    assert "reaches_read_start" in payload["activity_note"]


def test_a_brands_or_display_series_carries_new_to_brand_and_says_when_a_day_never_measured_it():
    days = [_day("2026-09-15", "SB", new_to_brand_purchases=2, new_to_brand_sales=75.0),
            _day("2026-09-16", "SB", new_to_brand_purchases=None, new_to_brand_sales=None)]

    payload = daily_series.daily_metrics(_FakeRest(days), profile_id="1111222233334444", days=2, product="SB")

    assert [(row["ntb_orders"], row["ntb_sales"], row["ntb_sales_share"]) for row in payload["rows"]] == [
        (2, 75.0, 50.0), (None, None, None)]
    assert "no son cero" in payload["new_to_brand_note"]


def test_each_product_says_how_many_days_it_counts_a_sale():
    days = [_day("2026-09-16"), _day("2026-09-16", "SB"), _day("2026-09-16", "SD")]

    payload = daily_series.daily_metrics(_FakeRest(days), profile_id="1111222233334444", days=1)

    assert payload["attribution_days"] == {"SP": 7, "SB": 14, "SD": 14}


def test_the_account_can_be_named_instead_of_its_profile_id():
    payload = daily_series.daily_metrics(_FakeRest([_day("2026-09-16")]), account="marca demo", days=1)

    assert payload["rows"][0]["spend"] == 30.0
