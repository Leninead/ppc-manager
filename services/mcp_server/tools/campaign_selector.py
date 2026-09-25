"""Which campaigns a question names, resolved over one account's campaigns the same way in every tool.

A name is looked up exactly first: «Automática» names that campaign, not the six whose names contain it. Only when
no campaign has that exact name or id does it read as part of a name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

MAX_CAMPAIGNS_LISTED = 30
CAMPAIGN_STATES = ("ENABLED", "PAUSED", "ARCHIVED")
CampaignState = Literal["", "enabled", "paused", "archived"]
# The columns a catalog of campaigns carries (core/amazon_ads/campaign_catalog.py).
CATALOG_COLUMNS = ("product", "campaign_id", "campaign", "state", "portfolio", "daily_budget")
MATCHED_BY_ID = "id"
MATCHED_EXACTLY = "exacto"
MATCHED_BY_PART = "contiene"
MATCHED_BY_LIST = "lista"


@dataclass(frozen=True)
class CampaignRequest:
    """The campaigns a tool call names: one by name or id, several by exact name or id, a state, a portfolio."""

    campaign: str = ""
    campaigns: tuple[str, ...] = ()
    state: str = ""
    portfolio: str = ""

    @classmethod
    def of(cls, campaign: str = "", campaigns=None, state: str = "", portfolio: str = "") -> CampaignRequest:
        return cls(campaign.strip(), tuple(name.strip() for name in campaigns or () if name.strip()),
                   state.strip().upper(), portfolio.strip())

    def applied(self) -> bool:
        return bool(self.campaign or self.campaigns or self.state or self.portfolio)


@dataclass(frozen=True)
class CampaignSelection:
    """The campaigns a request resolved to, and how each name matched."""

    ids: frozenset[str]
    matched: tuple[dict, ...]
    matched_by: str
    not_found: tuple[str, ...] = ()

    def payload(self) -> dict:
        listed = [dict(row) for row in self.matched[:MAX_CAMPAIGNS_LISTED]]
        fields = {"matched_campaigns": listed}
        if self.matched_by:
            fields["campaign_match"] = self.matched_by
        if len(self.matched) > MAX_CAMPAIGNS_LISTED:
            fields["matched_campaigns_total"] = len(self.matched)
        if self.not_found:
            fields["campaigns_not_found"] = list(self.not_found)
        return fields


def no_match_note(request: CampaignRequest) -> str:
    """Why a tool answers no rows when no campaign answers to what it was asked."""
    hint = " Los nombres exactos salen de breakdown por campaña o de campaign_structure."
    if request.campaign and not (request.campaigns or request.portfolio or request.state):
        return f"Ninguna campaña de la cuenta tiene «{request.campaign}» en el nombre ni ese id.{hint}"
    return f"Ninguna campaña de la cuenta coincide con lo pedido (campaign, campaigns, state o portfolio).{hint}"


def select_campaigns(catalog: pd.DataFrame, request: CampaignRequest) -> CampaignSelection:
    """The catalog's campaigns the request names; an empty request names none of them."""
    if request.state and request.state not in CAMPAIGN_STATES:
        raise ValueError("state tiene que ser enabled, paused o archived.")
    chosen = catalog
    matched_by = ""
    not_found: list[str] = []
    if request.campaign or request.campaigns:
        by_name, matched_by, not_found = _named(catalog, request)
        chosen = catalog[by_name]
    if request.portfolio:
        chosen = chosen[_part_or_exact(chosen["portfolio"], request.portfolio)]
    if request.state:
        chosen = chosen[chosen["state"].eq(request.state)]
    matched = tuple({"campaign": row["campaign"], "campaign_id": row["campaign_id"], "product": row["product"],
                     "state": row["state"]} for row in chosen.sort_values(["campaign", "campaign_id"]).to_dict("records"))
    return CampaignSelection(frozenset(chosen["campaign_id"]), matched, matched_by, tuple(not_found))


def _named(catalog: pd.DataFrame, request: CampaignRequest):
    """(mask, how it matched, names not found) for the campaign and the list of campaigns asked for."""
    names = catalog["campaign"].str.casefold()
    mask = pd.Series(False, index=catalog.index)
    not_found = []
    for wanted in request.campaigns:
        found = catalog["campaign_id"].eq(wanted) | names.eq(wanted.casefold())
        if not found.any():
            not_found.append(wanted)
        mask |= found
    matched_by = MATCHED_BY_LIST if request.campaigns else ""
    if request.campaign:
        by_id = catalog["campaign_id"].eq(request.campaign)
        exact = names.eq(request.campaign.casefold())
        if by_id.any():
            mask |= by_id
            matched_by = matched_by or MATCHED_BY_ID
        elif exact.any():
            mask |= exact
            matched_by = matched_by or MATCHED_EXACTLY
        else:
            mask |= names.str.contains(request.campaign.casefold(), regex=False)
            matched_by = matched_by or MATCHED_BY_PART
    return mask, matched_by, not_found


def _part_or_exact(values: pd.Series, wanted: str) -> pd.Series:
    """The values that are exactly `wanted`, whatever the case, or, when none is, those that contain it."""
    folded = values.fillna("").astype(str).str.casefold()
    exact = folded.eq(wanted.casefold())
    return exact if exact.any() else folded.str.contains(wanted.casefold(), regex=False)


def merged_catalog(listed: pd.DataFrame | None, active: pd.DataFrame) -> pd.DataFrame:
    """The listed campaigns plus those with activity that the last listing no longer has, with an unknown state."""
    active = active.reindex(columns=list(CATALOG_COLUMNS))
    if listed is None or listed.empty:
        return active.assign(state=active["state"].fillna(""))
    missing = active[~active["campaign_id"].isin(listed["campaign_id"])].assign(state="", daily_budget=float("nan"))
    return pd.concat([listed.reindex(columns=list(CATALOG_COLUMNS)), missing], ignore_index=True)
