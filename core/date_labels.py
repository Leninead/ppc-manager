"""Rótulos de fecha en español, compartidos por la app y los workers.

Viven fuera de `modules/pages/` porque el worker de análisis arma el mismo rótulo que la página
para el payload del agente: si difieren, difiere la huella y el análisis guardado no se encuentra.
"""
from __future__ import annotations

from datetime import date, timedelta

_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def short_date(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]}"


def date_range_label(start: date, end: date, *, with_year: bool = True) -> str:
    """Short Spanish range such as "15 ago – 13 sep 2026"; chunk labels leave the year out."""
    year = f" {end.year}" if with_year else ""
    if start == end:
        return f"{short_date(end)}{year}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day} – {short_date(end)}{year}"
    if start.year == end.year or not with_year:
        return f"{short_date(start)} – {short_date(end)}{year}"
    return f"{short_date(start)} {start.year} – {short_date(end)} {end.year}"


def day_phrase(day: date, today: date) -> str:
    if day == today:
        return "hoy"
    if day == today - timedelta(days=1):
        return "ayer"
    return f"el {short_date(day)}"


def data_of_day_phrase(day: date, today: date) -> str:
    phrase = day_phrase(day, today)
    return f"del {short_date(day)}" if phrase.startswith("el ") else f"de {phrase}"
