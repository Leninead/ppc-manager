"""A ranked list of names with their share of a total: the whole name, the amount and a bar drawn to scale.

For names too long for a KPI card: campaign names run past 100 characters, and a card cuts them. The bar of a
row that holds 17% of the total fills 17% of its track, so the list also shows how concentrated the total is.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from core.ui import palette
from core.ui.kpi_grid import CARD_BACKGROUND, CARD_BORDER, PHONE_BREAKPOINT_PX

LIST_CLASS = "cap-ranking"


@dataclass(frozen=True)
class RankingRow:
    name: str
    amount: str
    share: float
    note: str = ""


def ranking_html(rows: list[RankingRow]) -> str:
    """The rows as an ordered list, first row first; the whole markup on one line, as `kpi_grid_html` does."""
    if not rows:
        return ""
    items = "".join(_row_html(position, row) for position, row in enumerate(rows, start=1))
    return (
        f"<style>.{LIST_CLASS}{{list-style:none;margin:0.4rem 0 1rem;padding:0;background:{palette.CARD};"
        f"border:1px solid {CARD_BORDER};border-radius:10px;}}"
        f".{LIST_CLASS} li{{display:grid;grid-template-columns:1.6rem minmax(0,1fr) 10rem;gap:0.75rem;"
        f"align-items:start;padding:0.65rem 0.9rem;border-top:1px solid {palette.LINE_SOFT};}}"
        f".{LIST_CLASS} li:first-child{{border-top:none;}}"
        f".{LIST_CLASS}-rank{{color:{palette.FG_SUBTLE};font-weight:600;font-variant-numeric:tabular-nums;}}"
        f".{LIST_CLASS}-name{{color:{palette.FG};line-height:1.35;overflow-wrap:anywhere;}}"
        f".{LIST_CLASS}-note{{display:block;color:{palette.FG_MUTED};font-size:0.8rem;margin-top:0.15rem;}}"
        f".{LIST_CLASS}-amount{{color:{palette.FG};font-weight:600;text-align:right;white-space:nowrap;"
        f"font-variant-numeric:tabular-nums;}}"
        f".{LIST_CLASS}-track{{display:block;height:6px;border-radius:3px;background:{CARD_BACKGROUND};"
        f"margin-top:0.35rem;}}"
        f".{LIST_CLASS}-track span{{display:block;height:6px;border-radius:3px;background:{palette.ACCENT};}}"
        f"@media(max-width:{PHONE_BREAKPOINT_PX}px){{.{LIST_CLASS} li{{grid-template-columns:1.6rem minmax(0,1fr);}}"
        f".{LIST_CLASS}-amount{{grid-column:2;text-align:left;}}}}"
        f"</style><ol class='{LIST_CLASS}' role='list'>{items}</ol>")


def render_ranking(rows: list[RankingRow]) -> None:
    import streamlit as st

    st.markdown(ranking_html(rows), unsafe_allow_html=True)


def _row_html(position: int, row: RankingRow) -> str:
    bar_width = min(max(row.share, 0.0), 100.0)
    note = f"<span class='{LIST_CLASS}-note'>{html.escape(row.note)}</span>" if row.note else ""
    return (
        f"<li><span class='{LIST_CLASS}-rank'>{position}</span>"
        f"<span class='{LIST_CLASS}-name'>{html.escape(row.name)}{note}</span>"
        f"<span class='{LIST_CLASS}-amount'>{html.escape(row.amount)} · {row.share:.1f}%"
        f"<span class='{LIST_CLASS}-track' aria-hidden='true'><span style='width:{bar_width:.1f}%'></span></span>"
        f"</span></li>")
