"""Amounts as the Amazon Ads console exports write them: "$1,234.50", but also "MX$", "CA$", "£" or "€"."""
from __future__ import annotations

import pandas as pd


def clean_money(values: pd.Series) -> pd.Series:
    """The amounts as numbers, 0 where a cell holds none: anything but the number goes."""
    return known_money(values).fillna(0)


def known_money(values: pd.Series) -> pd.Series:
    """The amounts as numbers, NaN where a cell holds none: a "-" or a blank is not a measured zero."""
    return pd.to_numeric(values.astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
