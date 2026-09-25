"""Which campaigns a question names: by id, by exact name, or by part of the name, the same in every tool."""
from __future__ import annotations

import pandas as pd
import pytest

from services.mcp_server.tools.campaign_selector import (
    MAX_CAMPAIGNS_LISTED,
    CampaignRequest,
    merged_catalog,
    no_match_note,
    select_campaigns,
)

CATALOG = pd.DataFrame([
    {"product": "SP", "campaign_id": "1", "campaign": "Automática", "state": "ENABLED", "portfolio": "Hero",
     "daily_budget": 20.0},
    {"product": "SP", "campaign_id": "2", "campaign": "Automática - Cremas", "state": "ENABLED", "portfolio": "Hero",
     "daily_budget": 10.0},
    {"product": "SP", "campaign_id": "3", "campaign": "Automática - Lociones", "state": "PAUSED",
     "portfolio": "Hero 2", "daily_budget": 10.0},
    {"product": "SB", "campaign_id": "4", "campaign": "Brand Video", "state": "ENABLED", "portfolio": "",
     "daily_budget": 30.0},
])


def _ids(**asked) -> list[str]:
    return sorted(select_campaigns(CATALOG, CampaignRequest.of(**asked)).ids)


def test_an_exact_name_names_that_campaign_and_not_the_ones_that_contain_it():
    """The total of «Automática» summed 6 autos and was read as the one campaign of that name."""
    selection = select_campaigns(CATALOG, CampaignRequest.of("automática"))

    assert sorted(selection.ids) == ["1"] and selection.matched_by == "exacto"


def test_part_of_a_name_names_every_campaign_that_holds_it_when_none_is_called_so():
    selection = select_campaigns(CATALOG, CampaignRequest.of("cremas"))

    assert sorted(selection.ids) == ["2"] and selection.matched_by == "contiene"
    assert _ids(campaign="Automática -") == ["2", "3"]


def test_an_id_names_its_campaign():
    selection = select_campaigns(CATALOG, CampaignRequest.of("4"))

    assert sorted(selection.ids) == ["4"] and selection.matched_by == "id"


def test_a_list_names_each_campaign_by_exact_name_or_id_and_says_which_it_did_not_find():
    selection = select_campaigns(CATALOG, CampaignRequest.of(campaigns=["Brand Video", "2", "No existe"]))

    assert sorted(selection.ids) == ["2", "4"] and selection.matched_by == "lista"
    assert selection.payload()["campaigns_not_found"] == ["No existe"]


def test_a_state_and_a_portfolio_narrow_the_campaigns():
    assert _ids(state="paused") == ["3"]
    assert _ids(portfolio="hero") == ["1", "2"]
    assert _ids(portfolio="hero 2") == ["3"]
    with pytest.raises(ValueError, match="state"):
        _ids(state="running")


def test_the_payload_names_a_bounded_number_of_campaigns_and_how_they_matched():
    catalog = pd.DataFrame([{"product": "SP", "campaign_id": str(n), "campaign": f"Camp {n:03d}", "state": "ENABLED",
                             "portfolio": "", "daily_budget": 1.0} for n in range(MAX_CAMPAIGNS_LISTED + 5)])

    payload = select_campaigns(catalog, CampaignRequest.of("camp")).payload()

    assert len(payload["matched_campaigns"]) == MAX_CAMPAIGNS_LISTED
    assert payload["matched_campaigns_total"] == MAX_CAMPAIGNS_LISTED + 5
    assert payload["campaign_match"] == "contiene"
    assert payload["matched_campaigns"][0] == {"campaign": "Camp 000", "campaign_id": "0", "product": "SP",
                                               "state": "ENABLED"}


def test_a_campaign_with_activity_the_listing_no_longer_has_keeps_an_unknown_state():
    active = pd.DataFrame([{"product": "SP", "campaign_id": "9", "campaign": "Old", "portfolio": ""}])

    merged = merged_catalog(CATALOG, active)

    assert merged.set_index("campaign_id").loc["9", "state"] == ""
    assert len(merged_catalog(None, active)) == 1


def test_the_note_of_a_name_that_matched_nothing_repeats_the_name():
    assert "«inexistente»" in no_match_note(CampaignRequest.of("inexistente"))
    assert "campaign, campaigns, state o portfolio" in no_match_note(CampaignRequest.of("x", portfolio="y"))
