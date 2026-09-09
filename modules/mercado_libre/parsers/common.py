"""Utilities shared by the Mercado Libre parsers.

The core problem this module solves: MELI exports come in Spanish number
format (dot = thousands separator, comma = decimal). Pandas reads them the
other way around, so a listing with 1.564 visits is read as 1,564 visits.
Without this normalization, every conversion, sales-velocity and alert
calculation is off by a factor of 1000.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalize_text(value) -> str:
    """Lowercase, no accents, no duplicate whitespace."""
    if pd.isna(value):
        return ""
    txt = unicodedata.normalize("NFKD", str(value))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def to_int(value) -> int | None:
    """Convert a MELI value to int respecting Spanish number format.

    Accepts what already comes numeric and what comes as text with
    separators. Returns None for empty or uninterpretable input so 'no data'
    and 'zero' stay distinct downstream.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return int(value)

    if isinstance(value, float):
        # Pandas already broke the number: 1.564 was really 1564.
        # A float with a decimal part in a count column is always a
        # mis-parsed thousands separator.
        if value.is_integer():
            return int(value)
        text = f"{value!r}"
    else:
        text = str(value)

    text = text.strip()
    if text in ("", "-", "—", "N/A", "n/a"):
        return None

    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    # Spanish format: dot separates thousands, comma separates decimals.
    text = text.replace(".", "").replace(",", ".")
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def to_decimal(value) -> float | None:
    """Convert amounts and percentages ('$ 221.658', '3,8%') to float."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    text = str(value).strip()
    if text in ("", "-", "—", "N/A", "n/a"):
        return None

    is_percent = "%" in text
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number / 100 if is_percent else number


def normalize_mla(value) -> str | None:
    """Unify the listing id to MLA1234567890.

    The rendimiento report exports the id without a prefix (869673559) while
    Publicaciones and Ads carry the full one (MLA869673559). Without this
    normalization the cross-join between reports finds no matches.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper().replace(" ", "")
    if not text or text in ("-", "—"):
        return None
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    return f"MLA{digits}"


def extract_period(text) -> tuple[date, date] | None:
    """Read the date range from the rendimiento report header.

    MELI writes the period in prose: "...desde el 2 de julio de 2026 hasta
    el 17 de julio de 2026." Extracting it avoids asking the user for the
    dates and stores each upload with its real window.
    """
    cleaned = normalize_text(text)
    pattern = r"(\d{1,2}) de ([a-z]+) de (\d{4})"
    matches = re.findall(pattern, cleaned)
    if len(matches) < 2:
        return None

    dates = []
    for day, month, year in matches[:2]:
        month_num = _MONTHS.get(month)
        if month_num is None:
            return None
        dates.append(date(int(year), month_num, int(day)))

    from_date, to_date = sorted(dates)
    return from_date, to_date
