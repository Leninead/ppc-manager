"""The window of days a tool reads: the account's last days, or the exact dates asked for, clipped to what it synced."""
from __future__ import annotations

from datetime import date, timedelta

from core.amazon_ads.report_provider import ProfileOption

DEFAULT_DAYS = 7
MAX_DAYS = 60


def window_for(profile: ProfileOption, days: int, *, max_days: int = MAX_DAYS) -> tuple[date, date]:
    """The account's last `days` synced days, capped at `max_days` and clipped to what it has."""
    window_days = max(1, min(int(days), max_days))
    end = profile.data_through
    return max(profile.data_from or end, end - timedelta(days=window_days - 1)), end


def requested_window(profile: ProfileOption, days: int, date_from: str = "", date_to: str = "", *,
                     max_days: int = MAX_DAYS) -> tuple[date, date, str]:
    """(start, end, note): the exact dates asked for, clipped to what the account has synced, or its last `days`.

    The dates are the ones the AM has on screen, so the chat can read what the page shows and not only the last days.
    """
    if not (date_from or date_to):
        start, end = window_for(profile, days, max_days=max_days)
        return start, end, days_note(int(days), start, end, max_days=max_days)
    start, end = requested_dates(date_from, date_to, max_days=max_days)
    clipped = clipped_window(profile, start, end)
    if clipped is None:
        raise ValueError(outside_note(profile))
    return clipped


def requested_dates(date_from: str, date_to: str, *, max_days: int = MAX_DAYS) -> tuple[date, date]:
    """The period asked for, checked before any account is read: well formed, in order and not too long."""
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except ValueError as exc:
        raise ValueError("date_from y date_to van juntos y en formato AAAA-MM-DD.") from exc
    if end < start:
        raise ValueError(f"date_to ({end.isoformat()}) es anterior a date_from ({start.isoformat()}).")
    if (end - start).days + 1 > max_days:
        raise ValueError(f"El período puede tener hasta {max_days} días; del {start.isoformat()} al "
                         f"{end.isoformat()} hay {(end - start).days + 1}.")
    return start, end


def clipped_window(profile: ProfileOption, start: date, end: date) -> tuple[date, date, str] | None:
    """(start, end, note) of the period cut to the days the account has synced, or None when it has none of them."""
    earliest = earliest_day(profile)
    clipped_start, clipped_end = max(start, earliest), min(end, profile.data_through)
    if clipped_start > clipped_end:
        return None
    if (clipped_start, clipped_end) == (start, end):
        return start, end, ""
    return clipped_start, clipped_end, (
        f"Se pidió del {start.isoformat()} al {end.isoformat()} y la cuenta tiene datos sincronizados del "
        f"{earliest.isoformat()} al {profile.data_through.isoformat()}: la ventana se recortó a esos días.")


def earliest_day(profile: ProfileOption) -> date:
    return profile.data_from or profile.data_through - timedelta(days=MAX_DAYS - 1)


def outside_note(profile: ProfileOption) -> str:
    return (f"La cuenta tiene datos sincronizados del {earliest_day(profile).isoformat()} al "
            f"{profile.data_through.isoformat()}: el período pedido queda afuera.")


def days_note(requested: int, start: date, end: date, *, max_days: int = MAX_DAYS) -> str:
    returned = (end - start).days + 1
    if returned >= requested:
        return ""
    if requested > max_days and returned == max_days:
        return f"Se pidieron {requested} días y el máximo es {max_days}: la ventana trae esos."
    return f"Se pidieron {requested} días y la cuenta tiene {returned} sincronizados: la ventana se recortó a esos."


def window_payload(start: date, end: date) -> dict:
    return {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days + 1}
