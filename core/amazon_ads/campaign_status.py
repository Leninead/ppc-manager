"""Campaign Manager's «Active status» filter: which campaigns each option keeps, by the state Amazon Ads lists.

The state is the campaign's switch (enabled, paused, archived) as of the last sync, not whether it is delivering.
"""
from __future__ import annotations

from enum import StrEnum

import pandas as pd

ENABLED = "ENABLED"
PAUSED = "PAUSED"
ARCHIVED = "ARCHIVED"


class StatusFilter(StrEnum):
    ALL = "all"
    ALL_BUT_ARCHIVED = "all_but_archived"
    ENABLED = "enabled"
    PAUSED = "paused"
    ARCHIVED = "archived"


_ONLY_STATE = {StatusFilter.ENABLED: ENABLED, StatusFilter.PAUSED: PAUSED, StatusFilter.ARCHIVED: ARCHIVED}


def status_mask(states: pd.Series, status_filter: StatusFilter) -> pd.Series:
    """True where `status_filter` keeps a campaign in that state, in any case; an unknown state is only in
    «All» and «All but archived», since nothing says it is archived."""
    normalized = states.fillna("").astype(str).str.strip().str.upper()
    if status_filter is StatusFilter.ALL:
        return pd.Series(True, index=states.index)
    if status_filter is StatusFilter.ALL_BUT_ARCHIVED:
        return normalized.ne(ARCHIVED)
    return normalized.eq(_ONLY_STATE[status_filter])


def filter_by_status(frame: pd.DataFrame, state_column: str, status_filter: StatusFilter) -> pd.DataFrame:
    """The rows of `frame` whose `state_column` `status_filter` keeps, in their order, as a new frame."""
    return frame[status_mask(frame[state_column], status_filter)].copy()
