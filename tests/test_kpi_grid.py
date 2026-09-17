"""La grilla de KPIs: se acomoda a la cantidad de tarjetas y no rompe el alto de una fila."""
import re

from core.ui.kpi_grid import Kpi, balanced_columns, kpi_card_html, kpi_grid_html


def test_an_empty_list_draws_nothing():
    assert kpi_grid_html([]) == ""


def test_the_grid_lays_three_kpis_in_one_row_and_twelve_in_three_full_rows():
    three = kpi_grid_html([Kpi(f"kpi {i}", str(i)) for i in range(3)])
    twelve = kpi_grid_html([Kpi(f"kpi {i}", str(i)) for i in range(12)])

    assert "repeat(3,minmax(0,1fr))" in three
    assert "repeat(4,minmax(0,1fr))" in twelve
    assert twelve.count("border-radius:10px") == 12


def test_the_column_count_avoids_a_ragged_last_row():
    assert [balanced_columns(n) for n in (1, 3, 4, 5)] == [1, 3, 4, 5]
    assert balanced_columns(12) == 4      # 4 + 4 + 4, no 5 + 5 + 2
    assert balanced_columns(6) == 3
    assert balanced_columns(10) == 5
    assert balanced_columns(7) == 4       # ninguno divide justo


def test_two_grids_of_different_size_do_not_fight_over_the_same_class():
    five = kpi_grid_html([Kpi(f"k{i}", str(i)) for i in range(5)])
    three = kpi_grid_html([Kpi(f"k{i}", str(i)) for i in range(3)])

    assert "cap-kpi-grid-5" in five and "cap-kpi-grid-3" not in five
    assert "cap-kpi-grid-3" in three and "cap-kpi-grid-5" not in three


def test_the_grid_collapses_to_one_column_on_a_phone():
    grid = kpi_grid_html([Kpi(f"k{i}", str(i)) for i in range(12)])

    assert "@media(max-width:520px)" in grid and "grid-template-columns:1fr" in grid


def test_a_card_without_a_delta_draws_no_empty_slot_so_its_content_stays_centred():
    grid = kpi_grid_html([Kpi("ACoS", "142.8%", delta=112.8, delta_good=False), Kpi("ROAS", "0.70x")])

    assert "min-height" not in grid
    assert grid.count("↑") == 1


def test_the_row_keeps_one_height_through_the_grid_and_not_through_padding():
    grid = kpi_grid_html([Kpi("ACoS", "142.8%", delta=112.8), Kpi("ROAS", "0.70x")])

    assert "align-items:stretch" in grid


def test_a_rise_is_green_when_rising_is_good_and_red_when_it_is_not():
    good = kpi_card_html(Kpi("Sales", "$100", delta=12.0, delta_good=True))
    bad = kpi_card_html(Kpi("ACoS", "80%", delta=12.0, delta_good=False))

    assert "#1B6B2F" in good and "↑" in good
    assert "#B71C1C" in bad and "↑" in bad


def test_a_drop_flips_the_colour_the_same_way():
    good = kpi_card_html(Kpi("ACoS", "20%", delta=-12.0, delta_good=False))
    bad = kpi_card_html(Kpi("Sales", "$80", delta=-12.0, delta_good=True))

    assert "#1B6B2F" in good and "↓" in good
    assert "#B71C1C" in bad and "↓" in bad


def test_no_change_reads_flat_and_grey():
    flat = kpi_card_html(Kpi("Clicks", "100", delta=0.0))

    assert "→" in flat and "#888" in flat


def test_the_label_and_the_value_are_escaped_before_reaching_the_page():
    card = kpi_card_html(Kpi("<script>alert(1)</script>", "<b>99</b>"))

    assert "<script>" not in card
    assert "&lt;script&gt;" in card and "&lt;b&gt;99&lt;/b&gt;" in card


def test_the_cards_are_centred_and_stretched_to_the_row():
    card = kpi_card_html(Kpi("Spend", "$1.00"))
    grid = kpi_grid_html([Kpi("Spend", "$1.00")])

    assert "text-align:center" in card and "justify-content:center" in card
    assert "align-items:stretch" in grid


def test_the_caller_can_force_a_column_count():
    grid = kpi_grid_html([Kpi(f"k{i}", str(i)) for i in range(6)], columns=2)

    assert "repeat(2,minmax(0,1fr))" in grid


def test_values_that_are_not_strings_still_render():
    card = kpi_card_html(Kpi("ASINs", 27))

    assert re.search(r">27<", card)
