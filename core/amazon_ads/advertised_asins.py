"""The advertised ASIN behind each Sponsored Products search term.

Amazon's search term report does not carry the advertised ASIN; the product ads listing says which
ASINs each ad group advertises. A term takes its ad group's ASIN when the group advertises only one.
Otherwise (several ASINs, or an ad group the listing never showed) it takes the ASIN its campaign
name carries, even if the group does not advertise it: accounts that name campaigns after a product
family put the family's ASIN in the name and advertise its children. Anything else stays without an
ASIN: metrics are never split between ASINs.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.ad_entities import PRODUCT_ADS_TABLE
from core.integrations.store import _Rest

ASIN_IN_CAMPAIGN_NAME = r"(B0[A-Z0-9]{8})"
# The canonical frame keeps Amazon's ad group id in this hidden column; a manual file has none.
AD_GROUP_ID_COLUMN = "_ad_group_id"

FROM_AD_GROUP = "ad_group"
FROM_CAMPAIGN_NAME = "campaign_name"
SEVERAL_ASINS = "several_asins"
WITHOUT_ASIN = "without_asin"


@dataclass(frozen=True)
class AsinAttribution:
    """Aligned with the frame it was computed from: each row's ASIN (NaN if none) and how it was resolved."""

    asins: pd.Series
    origins: pd.Series


def asins_from_campaigns(campaign_names: pd.Series) -> pd.Series:
    """ASIN embedded in each campaign name; NaN where the naming carries none."""
    return campaign_names.astype(str).str.extract(ASIN_IN_CAMPAIGN_NAME, expand=False)


def load_ad_group_asins(rest: _Rest, profile_id: str) -> dict[str, frozenset[str]]:
    """ad group id -> the ASINs its product ads advertise, from every listing the sync kept."""
    rows = rest.select(PRODUCT_ADS_TABLE, {"select": "ad_group_id,asin", "profile_id": f"eq.{profile_id}",
                                           "asin": "neq."})
    by_ad_group: dict[str, set[str]] = {}
    for row in rows:
        ad_group_id = str(row.get("ad_group_id") or "").strip()
        asin = str(row.get("asin") or "").strip().upper()
        if ad_group_id and asin:
            by_ad_group.setdefault(ad_group_id, set()).add(asin)
    return {ad_group_id: frozenset(asins) for ad_group_id, asins in by_ad_group.items()}


def attribute_asins(frame: pd.DataFrame, ad_group_asins: dict[str, frozenset[str]],
                    campaign_column: str | None) -> AsinAttribution:
    named = (asins_from_campaigns(frame[campaign_column]) if campaign_column in frame.columns
             else pd.Series(pd.NA, index=frame.index, dtype="object"))
    ad_groups = _ad_group_ids(frame)
    single = {group: next(iter(asins)) for group, asins in ad_group_asins.items() if len(asins) == 1}
    in_single = ad_groups.isin(single.keys())
    in_several = ad_groups.isin(_several_asin_groups(ad_group_asins))
    by_name = ~in_single & named.notna()

    asins = pd.Series(pd.NA, index=frame.index, dtype="object")
    origins = pd.Series(WITHOUT_ASIN, index=frame.index, dtype="object")
    asins[in_single] = ad_groups[in_single].map(single)
    origins[in_single] = FROM_AD_GROUP
    asins[by_name] = named[by_name]
    origins[by_name] = FROM_CAMPAIGN_NAME
    origins[in_several & named.isna()] = SEVERAL_ASINS
    return AsinAttribution(asins=asins, origins=origins)


def grouped_asin_counts(frame: pd.DataFrame, attribution: AsinAttribution,
                        ad_group_asins: dict[str, frozenset[str]]) -> dict[str, int]:
    """Attributed ASIN -> how many ASINs the several-ASIN ad groups whose spend it took by campaign name advertise."""
    ad_groups = _ad_group_ids(frame)
    by_name = (attribution.origins == FROM_CAMPAIGN_NAME) & ad_groups.isin(_several_asin_groups(ad_group_asins))
    pairs = pd.DataFrame({"asin": attribution.asins[by_name], "ad_group": ad_groups[by_name]}).drop_duplicates()
    grouped: dict[str, set[str]] = {}
    for asin, ad_group in zip(pairs["asin"], pairs["ad_group"]):
        grouped.setdefault(asin, set()).update(ad_group_asins[ad_group])
    return {asin: len(asins) for asin, asins in grouped.items()}


def _ad_group_ids(frame: pd.DataFrame) -> pd.Series:
    if AD_GROUP_ID_COLUMN not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[AD_GROUP_ID_COLUMN].fillna("").astype(str).str.strip()


def _several_asin_groups(ad_group_asins: dict[str, frozenset[str]]) -> set[str]:
    return {group for group, asins in ad_group_asins.items() if len(asins) > 1}
