"""Which Sponsored Products keywords run, read from the SP structure listing and not from the reports.

A report only carries the keywords that got clicks in its window; the listing carries every keyword with its state.
"""
from __future__ import annotations

import pandas as pd

from core.amazon_ads.structure_provider import AD_GROUP, CAMPAIGN, KEYWORD

_ENABLED = "ENABLED"
_EXACT = "EXACT"


def normalized_keyword(text: object) -> str:
    """The form a keyword and a search term are compared in: case folded, with single spaces."""
    return " ".join(str(text).split()).casefold()


def active_keyword_texts(structure_rows: pd.DataFrame) -> frozenset[str]:
    """The normalized text of every SP keyword that runs, whatever its match type.

    `structure_rows` are `SpStructure.rows` with the campaign, ad_group and keyword families. A keyword runs when it
    and its campaign are enabled and its ad group is not listed as paused; an ad group the listing never saw counts
    as enabled, as in Target Graduation.
    """
    entity = structure_rows["entity"]
    enabled = structure_rows["state"].fillna("").astype(str).str.upper().eq(_ENABLED)
    running_campaigns = set(structure_rows.loc[entity.eq(CAMPAIGN) & enabled, "campaign_id"])
    stopped_ad_groups = set(structure_rows.loc[entity.eq(AD_GROUP) & ~enabled, "ad_group_id"])
    keywords = structure_rows[entity.eq(KEYWORD) & enabled]
    running = keywords[keywords["campaign_id"].isin(running_campaigns)
                       & ~keywords["ad_group_id"].isin(stopped_ad_groups)]
    texts = (normalized_keyword(text) for text in running["target_text"])
    return frozenset(text for text in texts if text)


def enabled_exact_keyword_texts(structure_rows: pd.DataFrame) -> frozenset[str]:
    """The normalized text of every enabled SP keyword in exact match, in any campaign of the account.

    INV-11.2's universe: the keyword's own state, as the Bulk File's keyword rows carry it, and not only the keywords
    that got clicks in a report's window.
    """
    keywords = structure_rows[structure_rows["entity"].eq(KEYWORD)]
    enabled_exact = keywords[keywords["state"].fillna("").astype(str).str.upper().eq(_ENABLED)
                             & keywords["match_type"].fillna("").astype(str).str.upper().eq(_EXACT)]
    texts = (normalized_keyword(text) for text in enabled_exact["target_text"])
    return frozenset(text for text in texts if text)
