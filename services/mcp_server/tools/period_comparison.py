"""A list's rows next to the same rows in the period before: how much each moved, and which appeared or left.

Each row takes seven fields and no more, so a compared page still holds most of its rows: the percent change of
spend, sales and orders, the ACoS change in points, the previous spend and sales, and the change of the figure the
list is ordered by, in its own units. A row that appeared says status=new; one that left comes back with zero
figures and status=gone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Literal

from core.amazon_ads.report_provider import ProfileOption
from services.mcp_server.tools.windows import clipped_window, requested_dates, window_payload

Compare = Literal["", "previous"]
STATUS_NEW = "new"
STATUS_GONE = "gone"
PERCENT_CHANGES = ("spend", "sales", "orders")
COMPARE_NOTE = ("Cada fila trae su cambio contra el período de comparison: delta_spend_pct, delta_sales_pct y "
                "delta_orders_pct en %, delta_acos_pp en puntos de ACoS, previous_spend y previous_sales, y "
                "delta_<métrica> en unidades de la métrica por la que se ordenó. status=new es un grupo que no tuvo "
                "actividad en el período anterior (sus % no existen: no se divide por cero); status=gone, uno que "
                "tuvo y ya no, con sus cifras de ahora en cero: total también las cuenta, y compare_counts dice "
                "cuántas son new y cuántas gone. totals.previous es el total del período anterior. Citá estos campos: "
                "no calcules diferencias ni porcentajes a mano.")


@dataclass(frozen=True)
class ComparisonWindow:
    start: date
    end: date
    note: str = ""

    def payload(self) -> dict:
        fields = {"comparison": window_payload(self.start, self.end), "compare_note": COMPARE_NOTE}
        if self.note:
            fields["comparison_note"] = self.note
        return fields


def comparison_window(profile: ProfileOption, start: date, end: date, compare: str, compare_from: str = "",
                      compare_to: str = "") -> ComparisonWindow | str | None:
    """The period the window is compared against, clipped to what the account synced; None when nothing was asked,
    and the reason as text when the account has no day of it."""
    if compare_from or compare_to:
        wanted = requested_dates(compare_from, compare_to)
    elif compare == "previous":
        length = (end - start).days + 1
        wanted = (start - timedelta(days=length), start - timedelta(days=1))
    elif compare:
        raise ValueError("compare tiene que ser previous, o vacío para no comparar.")
    else:
        return None
    clipped = clipped_window(profile, *wanted)
    if clipped is None:
        return (f"No hay con qué comparar: la cuenta no tiene datos sincronizados del {wanted[0].isoformat()} al "
                f"{wanted[1].isoformat()}.")
    return ComparisonWindow(*clipped)


def change_fields(current: dict, previous: dict | None, metric: str) -> dict:
    """The seven fields a compared row takes; `previous` is None when the row had no activity then."""
    before = previous or {}
    fields = {f"delta_{name}_pct": percent_change(current.get(name), before.get(name) if previous else 0)
              for name in PERCENT_CHANGES}
    fields["delta_acos_pp"] = (round(current["acos"] - before["acos"], 1)
                               if current.get("acos") is not None and before.get("acos") is not None else None)
    fields["previous_spend"] = round(float(before.get("spend") or 0), 2)
    fields["previous_sales"] = round(float(before.get("sales") or 0), 2)
    fields[f"delta_{metric}"] = absolute_change(current.get(metric), before.get(metric) if previous else 0)
    return fields


def percent_change(current, previous) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 1)


def absolute_change(current, previous) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def compared_rows(rows: list[dict], previous_rows: list[dict], key: Callable[[dict], object], metric: str,
                  gone_row: Callable[[dict], dict]) -> list[dict]:
    """The rows with their change fields, plus a zeroed row for each one that only had activity before."""
    before = {key(row): row for row in previous_rows}
    now = {key(row) for row in rows}
    compared = []
    for row in rows:
        previous = before.get(key(row))
        fields = change_fields(row, previous, metric)
        if previous is None:
            fields["status"] = STATUS_NEW
        compared.append({**row, **fields})
    for identity, previous in before.items():
        if identity in now:
            continue
        gone = gone_row(previous)
        compared.append({**gone, **change_fields(gone, previous, metric), "status": STATUS_GONE})
    return compared


def status_counts(rows: list[dict]) -> dict:
    """How many compared rows appeared and how many left, over every row, not only the page."""
    return {status: sum(1 for row in rows if row.get("status") == status) for status in (STATUS_NEW, STATUS_GONE)}


def change_leaders(rows: list[dict], metric: str, *, name: str = "group") -> dict:
    """The row whose `metric` rose the most and the one whose fell the most, over every compared row."""
    field = f"delta_{metric}"
    moved = [row for row in rows if row.get(field) is not None]
    leaders = {}
    rose = [row for row in moved if row[field] > 0]
    fell = [row for row in moved if row[field] < 0]
    if rose:
        top = max(rose, key=lambda row: row[field])
        leaders["biggest_rise"] = {name: top[name], field: top[field]}
    if fell:
        bottom = min(fell, key=lambda row: row[field])
        leaders["biggest_fall"] = {name: bottom[name], field: bottom[field]}
    return leaders


def activity_status(current: dict, previous: dict) -> dict:
    """status=new or gone for a row that is always listed, by whether it spent in each period."""
    if previous.get("spend") and not current.get("spend"):
        return {"status": STATUS_GONE}
    if current.get("spend") and not previous.get("spend"):
        return {"status": STATUS_NEW}
    return {}


def compared_totals(totals: dict, previous_totals: dict) -> dict:
    """The whole's own change, and the previous period's whole under `previous`."""
    return {**totals, **{f"delta_{name}_pct": percent_change(totals.get(name), previous_totals.get(name))
                         for name in PERCENT_CHANGES},
            "delta_acos_pp": (round(totals["acos"] - previous_totals["acos"], 1)
                              if totals.get("acos") is not None and previous_totals.get("acos") is not None
                              else None),
            "previous": previous_totals}
