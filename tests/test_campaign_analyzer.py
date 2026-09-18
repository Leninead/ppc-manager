"""The Campaign Analyzer's rules (core/amazon_ads/campaign_analyzer.py): M6's traffic light, moved out of the
page unchanged, and the additive signals next to it."""
from datetime import date

import pandas as pd
import pytest

from core.amazon_ads import campaign_analyzer as analyzer
from core.amazon_ads.campaign_analyzer import (
    BUDGET_LIMITED,
    GHOST,
    LOW_VISIBILITY,
    NEW_CAMPAIGN,
    OK,
    PAUSE,
    REVIEW,
    SCALE,
    CampaignAnalyzerParams,
)

PARAMS = CampaignAnalyzerParams(35.0, 20.0, 2)
WINDOW = (date(2026, 9, 10), date(2026, 9, 16))


def _campaign(campaign_id="1", name="Alpha", state="ENABLED", impressions=1000, clicks=20, cost=10.0, purchases=2,
              sales=100.0, acos=None):
    return {"Campaign name": name, "Campaign ID": campaign_id, "State": state, "Impressions": impressions,
            "Clicks": clicks, "Total cost": cost, "Purchases": purchases, "Sales": sales,
            "ACOS": (cost / sales) if acos is None and sales else acos}


def _diagnosed(rows, params=PARAMS):
    return analyzer.with_diagnosis(analyzer.analyzer_frame(pd.DataFrame(rows)), params)


def _signals(rows, inputs, params=PARAMS, window=WINDOW):
    campaigns = _diagnosed(rows, params)
    return analyzer.with_signals(campaigns, pd.DataFrame(inputs), params, window_start=window[0],
                                 window_end=window[1])


def _inputs(campaign_id="1", start=date(2026, 3, 1), budget_type="DAILY", capped=0, days=7, share=25.0):
    return {"Campaign ID": campaign_id, "start_date": start, "budget_type": budget_type,
            "budget_capped_days": capped, "days_with_impressions": days, "top_of_search_is": share}


class TestTrafficLight:
    def test_each_state_of_the_light_comes_out_as_m6_always_gave_it(self):
        campaigns = _diagnosed([
            _campaign("1", impressions=0, clicks=0, cost=0.0, purchases=0, sales=0.0),
            _campaign("2", cost=25.0, purchases=0, sales=0.0),
            _campaign("3", cost=90.0, purchases=1, sales=100.0),
            _campaign("4", cost=10.0, purchases=2, sales=100.0),
            _campaign("5", cost=30.0, purchases=1, sales=100.0),
        ])

        assert list(campaigns["Diagnóstico"]) == [GHOST, PAUSE, REVIEW, SCALE, OK]

    def test_spend_under_the_pause_threshold_without_orders_is_still_ok(self):
        assert list(_diagnosed([_campaign(cost=19.99, purchases=0, sales=0.0)])["Diagnóstico"]) == [OK]

    def test_only_enabled_campaigns_are_diagnosed(self):
        campaigns = _diagnosed([_campaign("1"), _campaign("2", state="PAUSED"), _campaign("3", state="enabled")])

        assert list(campaigns["Campaign ID"]) == ["1", "3"]

    def test_a_hand_uploaded_csv_with_dollar_signs_and_acos_as_a_fraction_reads_the_same(self):
        uploaded = [{"Campaign name": "Alpha", "State": "ENABLED", "Impressions": 1000, "Clicks": 20,
                     "Total cost": "$1,090.00", "Purchases": 1, "Sales": "$1,000.00", "ACOS": 1.09}]

        campaigns = _diagnosed(uploaded)

        assert campaigns.iloc[0]["_spend"] == pytest.approx(1090.0)
        assert campaigns.iloc[0]["_acos"] == pytest.approx(109.0)
        assert campaigns.iloc[0]["Diagnóstico"] == REVIEW

    @pytest.mark.parametrize("cost, sales", [("MX$5,796.55", "MX$25,619.00"), ("CA$5,796.55", "CA$25,619.00"),
                                             ("£5,796.55", "£25,619.00"), ("€5,796.55", "€25,619.00")])
    def test_a_hand_uploaded_csv_in_another_currency_keeps_its_spend_and_sales(self, cost, sales):
        """Love To Dream MX's Campaign CSV writes MX$: read as 0, no campaign could reach PAUSAR."""
        uploaded = [{"Campaign name": "Alpha", "State": "ENABLED", "Impressions": 1000, "Clicks": 20,
                     "Total cost": cost, "Purchases": 0, "Sales": sales, "ACOS": 0.2263}]

        campaigns = _diagnosed(uploaded)

        assert campaigns.iloc[0]["_spend"] == pytest.approx(5796.55)
        assert campaigns.iloc[0]["_sales"] == pytest.approx(25619.0)
        assert campaigns.iloc[0]["Diagnóstico"] == PAUSE

    def test_without_impressions_a_ghost_is_read_from_clicks(self):
        rows = [{"Campaign name": "Alpha", "State": "ENABLED", "Clicks": 0, "Total cost": 0, "Purchases": 0,
                 "Sales": 0}]

        frame = analyzer.analyzer_frame(pd.DataFrame(rows))

        assert not frame.has_impressions
        assert list(analyzer.with_diagnosis(frame, PARAMS)["Diagnóstico"]) == [GHOST]

    def test_without_acos_the_rate_comes_from_roas_and_then_from_spend_over_sales(self):
        from_roas = analyzer.analyzer_frame(pd.DataFrame([{"State": "ENABLED", "Total cost": 50, "Sales": 100,
                                                          "Purchases": 2, "ROAS": 2.0}]))
        derived = analyzer.analyzer_frame(pd.DataFrame([{"State": "ENABLED", "Total cost": 50, "Sales": 100,
                                                        "Purchases": 2}]))

        assert from_roas.campaigns.iloc[0]["_acos"] == pytest.approx(50.0)
        assert derived.campaigns.iloc[0]["_acos"] == pytest.approx(50.0)

    def test_the_account_thresholds_move_the_light(self):
        strict = CampaignAnalyzerParams(target_acos=20.0, spend_to_pause=5.0, min_orders_to_scale=1)

        campaigns = _diagnosed([_campaign("1", cost=6.0, purchases=0, sales=0.0),
                                _campaign("2", cost=45.0, purchases=1, sales=100.0)], strict)

        assert list(campaigns["Diagnóstico"]) == [PAUSE, REVIEW]


class TestSignals:
    def test_a_campaign_within_target_that_hit_its_budget_three_days_is_held_back_by_it(self):
        campaigns = _signals([_campaign(cost=10.0, purchases=2, sales=100.0)], [_inputs(capped=3)])

        assert campaigns.iloc[0]["Señales"] == BUDGET_LIMITED

    def test_hitting_the_budget_over_target_is_not_an_opportunity(self):
        campaigns = _signals([_campaign(cost=50.0, purchases=1, sales=100.0)], [_inputs(capped=5)])

        assert BUDGET_LIMITED not in campaigns.iloc[0]["Señales"]

    def test_two_capped_days_are_not_enough_in_a_week(self):
        campaigns = _signals([_campaign()], [_inputs(capped=2)])

        assert campaigns.iloc[0]["Señales"] == ""

    def test_in_a_window_of_two_days_both_days_capped_are_enough(self):
        campaigns = _signals([_campaign()], [_inputs(capped=2)], window=(date(2026, 9, 15), date(2026, 9, 16)))

        assert BUDGET_LIMITED in campaigns.iloc[0]["Señales"]

    def test_only_daily_budgets_can_be_capped_by_the_day(self):
        campaigns = _signals([_campaign()], [_inputs(capped=6, budget_type="")])

        assert BUDGET_LIMITED not in campaigns.iloc[0]["Señales"]

    def test_a_campaign_younger_than_two_weeks_is_new(self):
        new = _signals([_campaign()], [_inputs(start=date(2026, 9, 5))])
        settled = _signals([_campaign()], [_inputs(start=date(2026, 9, 2))])

        assert new.iloc[0]["Señales"] == NEW_CAMPAIGN and new.iloc[0]["_days_live"] == 12
        assert settled.iloc[0]["Señales"] == ""

    def test_low_top_of_search_share_is_flagged_only_where_the_light_is_red_or_yellow(self):
        campaigns = _signals([_campaign("1", cost=25.0, purchases=0, sales=0.0), _campaign("2")],
                             [_inputs("1", share=4.0), _inputs("2", share=4.0)])

        assert list(campaigns["Señales"]) == [LOW_VISIBILITY, ""]

    def test_a_share_amazon_did_not_report_flags_nothing(self):
        campaigns = _signals([_campaign(cost=25.0, purchases=0, sales=0.0)], [_inputs(share=float("nan"))])

        assert campaigns.iloc[0]["Señales"] == ""

    def test_signals_never_change_the_diagnosis(self):
        rows = [_campaign(cost=25.0, purchases=0, sales=0.0)]

        plain = _diagnosed(rows)
        signalled = _signals(rows, [_inputs(capped=7, start=date(2026, 9, 12), share=1.0)])

        assert list(signalled["Diagnóstico"]) == list(plain["Diagnóstico"]) == [PAUSE]
        assert signalled.iloc[0]["Señales"] == f"{NEW_CAMPAIGN} · {LOW_VISIBILITY}"

    def test_a_file_without_signal_inputs_has_no_signals(self):
        campaigns = analyzer.with_signals(_diagnosed([_campaign()]), None, PARAMS, window_start=None,
                                          window_end=None)

        assert list(campaigns["Señales"]) == [""]

    def test_the_rows_keep_their_order_and_index_after_the_signals(self):
        rows = [_campaign("2", name="Beta"), _campaign("1", name="Alpha")]

        campaigns = _signals(rows, [_inputs("1"), _inputs("2")])

        assert list(campaigns["Campaign ID"]) == ["2", "1"]
        assert list(campaigns.index) == list(_diagnosed(rows).index)


class TestProvisionalDays:
    def test_the_last_two_days_of_the_period_are_provisional(self):
        assert analyzer.provisional_days(*WINDOW) == [date(2026, 9, 15), date(2026, 9, 16)]

    def test_a_one_day_period_has_one_provisional_day(self):
        assert analyzer.provisional_days(date(2026, 9, 16), date(2026, 9, 16)) == [date(2026, 9, 16)]

    def test_no_period_no_provisional_days(self):
        assert analyzer.provisional_days(None, None) == []


class TestParams:
    @pytest.mark.parametrize("values, expected", [
        ({}, (35.0, 20.0, 2)),
        ({"target_acos": 40, "spend_to_pause": "15", "min_orders_to_scale": 3}, (40.0, 15.0, 3)),
        ({"target_acos": "no es un número"}, (35.0, 20.0, 2)),
    ])
    def test_saved_parameters_survive_broken_values(self, values, expected):
        params = CampaignAnalyzerParams.from_dict(values)

        assert (params.target_acos, params.spend_to_pause, params.min_orders_to_scale) == expected

    def test_an_int_and_a_float_of_the_same_value_share_a_digest(self):
        assert CampaignAnalyzerParams(35, 20, 2).digest == CampaignAnalyzerParams(35.0, 20.0, 2).digest
        assert CampaignAnalyzerParams(35.0, 20.0, 2).digest != CampaignAnalyzerParams(36.0, 20.0, 2).digest
