"""The «Estado de campaña» rule (core/amazon_ads/campaign_status.py): which campaigns each option keeps."""
import warnings

import pandas as pd
import pytest

from core.amazon_ads.campaign_status import StatusFilter, filter_by_status, status_mask

# The listing writes states in capitals and a Campaign CSV in any case, sometimes with spaces around.
STATES = pd.Series(["ENABLED", "paused", " Archived ", "", None], index=[10, 11, 12, 13, 14])


@pytest.mark.parametrize(("status_filter", "kept"), [
    (StatusFilter.ALL, [10, 11, 12, 13, 14]),
    (StatusFilter.ALL_BUT_ARCHIVED, [10, 11, 13, 14]),
    (StatusFilter.ENABLED, [10]),
    (StatusFilter.PAUSED, [11]),
    (StatusFilter.ARCHIVED, [12]),
])
def test_each_option_keeps_the_campaigns_campaign_manager_keeps(status_filter, kept):
    assert list(STATES.index[status_mask(STATES, status_filter)]) == kept


def test_a_campaign_without_a_state_is_never_taken_for_an_active_or_an_archived_one():
    unknown = pd.Series(["", None])

    assert not status_mask(unknown, StatusFilter.ENABLED).any()
    assert not status_mask(unknown, StatusFilter.ARCHIVED).any()
    assert status_mask(unknown, StatusFilter.ALL_BUT_ARCHIVED).all()


def test_the_filter_keeps_the_rows_in_their_order():
    campaigns = pd.DataFrame({"Campaign name": ["Brand", "Old", "Generic"], "State": ["ENABLED", "PAUSED", "ENABLED"]})

    kept = filter_by_status(campaigns, "State", StatusFilter.ENABLED)

    assert list(kept["Campaign name"]) == ["Brand", "Generic"]


def test_a_page_can_add_columns_to_what_the_filter_returns_without_touching_its_input():
    campaigns = pd.DataFrame({"Campaign name": ["Brand", "Old"], "State": ["ENABLED", "PAUSED"]})

    kept = filter_by_status(campaigns, "State", StatusFilter.PAUSED)
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.SettingWithCopyWarning)
        kept["Term type"] = "Brand"

    assert "Term type" not in campaigns.columns
