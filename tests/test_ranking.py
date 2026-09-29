"""The ranked list of core/ui/ranking.py: whole names, amounts, shares and a bar drawn to scale."""
import re

from core.ui.kpi_grid import PHONE_BREAKPOINT_PX
from core.ui.ranking import RankingRow, ranking_html

ROWS = [
    RankingRow("BEST SELLER | B0CYLM4L23 - B0CYLMJJJC | SP | KW | EXACT | RANK |ASIN l COMPETIDORES", "$93.71", 17.1,
               "ACoS 260.6%"),
    RankingRow("DG | DISCOVERY | SP | AUTO | B0F4KXZVNM", "$66.86", 12.2, "Sin ventas"),
]


def _items(markup: str) -> list[str]:
    return re.findall(r"<li>(.*?)</li>", markup)


def test_every_row_keeps_its_whole_name_its_position_amount_share_and_note():
    first, second = _items(ranking_html(ROWS))

    assert "<span class='cap-ranking-rank'>1</span>" in first
    assert "BEST SELLER | B0CYLM4L23 - B0CYLMJJJC | SP | KW | EXACT | RANK |ASIN l COMPETIDORES" in first
    assert "$93.71 · 17.1%" in first and "ACoS 260.6%" in first
    assert "<span class='cap-ranking-rank'>2</span>" in second and "Sin ventas" in second


def test_the_bar_is_drawn_to_scale_and_never_past_its_track():
    markup = ranking_html([RankingRow("Half", "$1", 50.0), RankingRow("Rounding", "$1", 100.4),
                           RankingRow("Refund", "$1", -2.0)])

    assert re.findall(r"style='width:([\d.]+)%'", markup) == ["50.0", "100.0", "0.0"]


def test_names_and_notes_typed_by_people_are_escaped():
    markup = ranking_html([RankingRow("<script>alert(1)</script> & co", "$1", 10.0, "<b>note</b>")])

    assert "<script>alert" not in markup
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in markup
    assert "&lt;b&gt;note&lt;/b&gt;" in markup


def test_a_row_without_a_note_draws_no_empty_line():
    assert "cap-ranking-note" not in _items(ranking_html([RankingRow("Plain", "$5", 5.0)]))[0]


def test_on_a_phone_the_amount_moves_under_the_name():
    markup = ranking_html(ROWS)

    assert f"@media(max-width:{PHONE_BREAKPOINT_PX}px)" in markup
    assert ".cap-ranking-amount{grid-column:2;text-align:left;}" in markup


def test_no_rows_draw_nothing():
    assert ranking_html([]) == ""
