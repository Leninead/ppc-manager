"""Whether an account already targets a search term exactly, for every tool whose rows are search terms."""
from __future__ import annotations

import logging
from datetime import date

from core.amazon_ads.report_provider import ReportReadError
from services.mcp_server.tools.campaign_structure import exact_keywords

log = logging.getLogger(__name__)

RUNNING = "corre"
NOT_RUNNING = "no corre"
MISSING = "no está"
COVERAGE_STATES = (RUNNING, NOT_RUNNING, MISSING)
MAX_RUNNING_CAMPAIGNS = 3


def mark_exact_coverage(rows: list[dict], rest, profile_id: str, start: date, end: date, *,
                        term_field: str = "search_term") -> bool:
    """Each row gets `exact_in_account`, and `exact_running_in` when its exact runs.

    An exact is a keyword in exact match or, for an ASIN term, an `asin="…"` product target; it runs when it and its
    campaign are enabled, and it does not when either is paused. False, with the rows untouched, when the account's
    structure was never listed or could not be read: then nobody can say which terms are covered.
    """
    if not rows:
        return False
    try:
        exact = exact_keywords(rest, profile_id, start, end)
    except (ReportReadError, ValueError) as exc:
        log.warning("exact keywords of profile %s could not be read: %s", profile_id, exc)
        return False
    if not exact:
        return False
    for row in rows:
        entry = exact.get(str(row[term_field]).strip().casefold())
        row["exact_in_account"] = RUNNING if entry and entry["running_in"] else NOT_RUNNING if entry else MISSING
        if entry and entry["running_in"]:
            row["exact_running_in"] = entry["running_in"][:MAX_RUNNING_CAMPAIGNS]
    return True


def coverage_counts(rows: list[dict]) -> dict[str, int]:
    """How many rows run in exact, have an exact that does not run, or have none."""
    return {state: sum(1 for row in rows if row.get("exact_in_account") == state) for state in COVERAGE_STATES}


def rows_without_running_exact(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("exact_in_account") != RUNNING]
