"""Account Pulse's campaigns over the Business Report's days: most spend first, each with its product and its age."""
from __future__ import annotations

import re

import pandas as pd

# The names Capybaras gives the campaigns it launches ("[Producto] - [ASIN] - SP - KW - …"); the rest were inherited.
_NEW_CAMPAIGN_PATTERNS = (r"\bSP\b.*\bKW\b", r"\bSP\b.*\bPAT\b", r"\bSD\b.*\bRET\b", r"202[5-9]")


def campaign_age(name: str) -> str:
    """NUEVA when the name follows the Capybaras naming convention, HEREDADA otherwise."""
    if any(re.search(pattern, name, re.IGNORECASE) for pattern in _NEW_CAMPAIGN_PATTERNS):
        return "NUEVA"
    return "HEREDADA"


def campaign_rows(totals: pd.DataFrame, *, unknown_counts: tuple[str, ...] = ()) -> list[dict]:
    """One row per campaign of `totals` (the account's campaign totals over a window, or a Campaign CSV's), most spend
    first. `unknown_counts` names the counts (impressions, clicks, orders) a Campaign CSV lacks: None in every row.

    ACoS is None for a campaign that sold nothing: a 0% would read as the account's best campaign."""
    # The read comes in no set order: ties are broken by product and id so the same data lists the same way.
    ordered = totals.sort_values(["spend", "product", "campaign_id"], ascending=[False, True, True], kind="stable")

    def count(row, field: str) -> int | None:
        return None if field in unknown_counts else int(getattr(row, field))

    return [{
        "Campaign": row.campaign,
        "Product": row.product,
        "Age": campaign_age(row.campaign),
        "Impressions": count(row, "impressions"),
        "Clicks": count(row, "clicks"),
        "Spend": round(float(row.spend), 2),
        "Sales": round(float(row.sales), 2),
        "ACoS": round(row.spend / row.sales * 100, 1) if row.sales > 0 else None,
        "Orders": count(row, "orders"),
    } for row in ordered.itertuples(index=False)]
