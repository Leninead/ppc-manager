"""Every account of the overview counted and ranked, so a question about all of them needs no paging.

Asked how the ads of all the accounts were doing, the chat paged the 52 accounts four times and then spent two and a
half minutes counting, in its reasoning, how many rose and which moved most. Those counts are arithmetic: they are
done here, over every account and not only a page. Percentages and counts compare across currencies; amounts are
added up only within one.
"""
from __future__ import annotations

MOVERS = 3
SUMMARY_NOTE = ("summary cuenta y ordena todas las cuentas de la respuesta, no sólo esta página: con él contestás cómo "
                "vienen, cuántas subieron o bajaron y cuáles se movieron más, sin pedir las otras páginas. by_currency "
                "suma los montos dentro de cada moneda. Las filas son el detalle de cada cuenta.")


def overview_summary(rows: list[dict], *, compared: bool) -> dict:
    measured = [row for row in rows if row.get("spend") is not None]
    spending = [row for row in measured if row["spend"] > 0]
    summary = {
        "accounts": len(rows),
        "with_spend": len(spending),
        "without_spend": sorted(row["account"] for row in measured if not row["spend"]),
        "without_figures": sorted(row["account"] for row in rows if row.get("spend") is None),
        "spend_exceeds_sales": sum(1 for row in spending if row.get("spend_exceeds_sales")),
        "without_sales": sum(1 for row in spending if row.get("without_sales")),
        "by_currency": _currency_totals(spending, compared),
    }
    if compared:
        summary["changes"] = {"spend": _directions(spending, "delta_spend_pct"),
                              "sales": _directions(spending, "delta_sales_pct"),
                              "orders": _directions(spending, "delta_orders_pct"),
                              "acos_points": _directions(spending, "delta_acos_pp")}
        summary["movers"] = {"sales_rise": _movers(rows, "delta_sales_pct", "sales", highest=True),
                             "sales_drop": _movers(rows, "delta_sales_pct", "sales", highest=False),
                             "spend_rise": _movers(rows, "delta_spend_pct", "spend", highest=True),
                             "spend_drop": _movers(rows, "delta_spend_pct", "spend", highest=False),
                             "acos_rise": _movers(rows, "delta_acos_pp", "acos", highest=True),
                             "acos_drop": _movers(rows, "delta_acos_pp", "acos", highest=False)}
    return summary


def _directions(rows: list[dict], key: str) -> dict:
    values = [row.get(key) for row in rows]
    return {"up": sum(1 for value in values if value is not None and value > 0),
            "down": sum(1 for value in values if value is not None and value < 0),
            "flat": sum(1 for value in values if value == 0),
            "without_previous": sum(1 for value in values if value is None)}


def _movers(rows: list[dict], key: str, metric: str, *, highest: bool) -> list[dict]:
    """The accounts that moved most by `key`, each with the metric now and before: enough to name the change."""
    moved = [row for row in rows if row.get(key) is not None and (row[key] > 0 if highest else row[key] < 0)]
    moved.sort(key=lambda row: row[key], reverse=highest)
    return [{"account": row["account"], "profile_id": row["profile_id"], "currency": row.get("currency"),
             key: row[key], metric: row.get(metric),
             **({f"previous_{metric}": row[f"previous_{metric}"]} if f"previous_{metric}" in row else {})}
            for row in moved[:MOVERS]]


def _currency_totals(rows: list[dict], compared: bool) -> list[dict]:
    currencies: dict[str, list[dict]] = {}
    for row in rows:
        currencies.setdefault(str(row.get("currency") or ""), []).append(row)
    totals = []
    for currency, accounts in sorted(currencies.items(), key=lambda item: -len(item[1])):
        spend, sales = _sum(accounts, "spend"), _sum(accounts, "sales")
        line = {"currency": currency, "accounts": len(accounts), "spend": spend, "sales": sales,
                "orders": _sum(accounts, "orders"), "clicks": _sum(accounts, "clicks"),
                "acos": round(spend / sales * 100, 2) if sales else None}
        if compared:
            previous_spend, previous_sales = _sum(accounts, "previous_spend"), _sum(accounts, "previous_sales")
            line.update(previous_spend=previous_spend, previous_sales=previous_sales,
                        delta_spend_pct=_change(spend, previous_spend), delta_sales_pct=_change(sales, previous_sales))
        totals.append(line)
    return totals


def _sum(rows: list[dict], key: str) -> float:
    return round(sum(row.get(key) or 0 for row in rows), 2)


def _change(now: float, before: float) -> float | None:
    return round((now - before) / before * 100, 1) if before else None
