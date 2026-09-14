"""Date arithmetic for consents that die on a fixed calendar.

Login with Amazon refresh tokens issued from 2026-07-30 expire 365 days after
the advertiser consented, no matter how often they are refreshed. The date is
derived from `consent_date` plus the catalog's lifetime on every read — never
stored — so the warning can never drift from the fact it is computed from.

Shared by the worker (marks expired rows), the screen (paints the warning) and
the sidebar notice (counts what is about to expire).
"""
from __future__ import annotations

from datetime import date, timedelta

EXPIRY_WARNING_DAYS = 45


def expiry_date(consent_date: str, lifetime_days: int) -> date | None:
    """When the consent dies, or None for providers whose tokens do not expire."""
    if lifetime_days <= 0 or not consent_date:
        return None
    try:
        consented = date.fromisoformat(str(consent_date)[:10])
    except ValueError:
        return None
    return consented + timedelta(days=lifetime_days)


def days_left(consent_date: str, lifetime_days: int, today: date | None = None) -> int | None:
    expires = expiry_date(consent_date, lifetime_days)
    if expires is None:
        return None
    return (expires - (today or date.today())).days


def is_expiring_soon(consent_date: str, lifetime_days: int, today: date | None = None) -> bool:
    left = days_left(consent_date, lifetime_days, today)
    return left is not None and 0 <= left <= EXPIRY_WARNING_DAYS


def is_expired(consent_date: str, lifetime_days: int, today: date | None = None) -> bool:
    left = days_left(consent_date, lifetime_days, today)
    return left is not None and left < 0
