"""The component catalog: what the model may send, what it reads, what the panel draws and what text reads."""
import jsonschema
import pytest

from core import chat_components
from core.chat_components import CATALOG, bars, pie, trend
from core.chat_components.base import TONE_COLOR

KINDS = [component.kind for component in CATALOG]


def _answer(*blocks):
    return {"blocks": list(blocks)}


def _fill_strings(value, filler):
    """The example with every string the AM reads replaced; kind, tone and level keep their meaning."""
    if isinstance(value, dict):
        return {k: v if k in ("kind", "tone", "level") else _fill_strings(v, filler) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_strings(v, filler) for v in value]
    return filler if isinstance(value, str) else value


@pytest.mark.parametrize("component", CATALOG, ids=KINDS)
def test_a_component_the_model_can_choose_is_drawable_and_readable(component):
    jsonschema.validate(_answer(component.example), chat_components.SCHEMA)
    cleaned = component.clean(component.example)
    assert cleaned is not None and cleaned["kind"] == component.kind
    assert component.render(cleaned) and component.plain(cleaned).strip()


@pytest.mark.parametrize("component", CATALOG, ids=KINDS)
def test_the_model_reads_what_each_component_is_for_and_how_it_is_drawn(component):
    assert f"**{component.kind}**" in chat_components.GUIDE
    assert component.purpose in chat_components.GUIDE and component.looks in chat_components.GUIDE


def test_the_catalog_has_no_duplicate_kinds_and_says_where_bold_applies():
    assert len(set(KINDS)) == len(KINDS)
    prose = [c.kind for c in CATALOG if c.prose]
    assert f"En {', '.join(prose)} rige la negrita" in chat_components.GUIDE


@pytest.mark.parametrize("component", CATALOG, ids=KINDS)
def test_a_component_never_leaks_markup_a_newline_or_latex_into_the_thread(component):
    html = component.render(component.clean(_fill_strings(component.example, "<script>x</script> $5\notra")))
    assert "<script>" not in html and "\n" not in html and "$" not in html


@pytest.mark.parametrize("component", CATALOG, ids=KINDS)
def test_a_carriage_return_never_reaches_the_thread_either(component):
    for breaks in ("a\r\rb", "a\r\n\r\nb", "a\r\r\nb"):
        html = component.render(component.clean(_fill_strings(component.example, breaks)))
        assert "\r" not in html and "\n" not in html


@pytest.mark.parametrize("component", CATALOG, ids=KINDS)
def test_map_strings_reaches_every_string_the_am_reads(component):
    block = component.clean(_fill_strings(component.example, "N01"))
    mapped = chat_components.map_strings([block], lambda s: s.replace("N01", "N01 (toy box)"))
    before = chat_components.render([block]).count("N01")
    assert before > 0
    assert chat_components.render(mapped).count("N01 (toy box)") == before
    assert "N01 (toy box)" in chat_components.plain_text(mapped)


@pytest.mark.parametrize("block", [
    {"kind": "chart", "text": "x"},
    {"kind": "text"},
    {"kind": "table", "columns": ["A"]},
    {"kind": "table", "columns": ["A"], "rows": [[{"value": "1", "tone": "red"}]]},
    {"kind": "kpis", "items": []},
    {"kind": "bars", "metric": "", "items": [{"label": "A", "value": "12", "display": "12", "tone": "neutral"}]},
    {"kind": "trend", "label": "", "display": "", "points": [1], "start": "", "end": "", "tone": "neutral"},
    {"kind": "pie", "metric": "", "items": [{"label": "A", "value": 1, "display": "1"}]},
    {"kind": "pie", "metric": "", "items": [{"label": str(n), "value": 1, "display": "1"} for n in range(7)]},
    {"kind": "alert", "level": "urgent", "text": "x"},
    {"kind": "action", "text": "x", "extra": "y"},
])
def test_the_schema_refuses_what_the_panel_cannot_draw(block):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_answer(block), chat_components.SCHEMA)


def test_the_schema_refuses_an_answer_without_components():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"blocks": []}, chat_components.SCHEMA)


@pytest.mark.parametrize("structured", [None, "text", [], {}, {"blocks": []},
                                        {"blocks": [{"kind": "text", "text": "  "}]}])
def test_nothing_drawable_is_none(structured):
    assert chat_components.normalize(structured) is None


@pytest.mark.parametrize("structured", [
    {"blocks": 5},
    {"blocks": [{"kind": ["table"], "rows": 5}]},
    {"blocks": [{"kind": "table", "columns": 5, "rows": 5}]},
    {"blocks": [{"kind": "bars", "metric": "m", "items": 5}]},
    {"blocks": [{"kind": "trend", "label": "", "display": "", "points": 5, "start": "", "end": "", "tone": "bad"}]},
    {"blocks": [{"kind": "bars", "metric": "m", "items": [
        {"label": "a", "value": 10 ** 400, "display": "x", "tone": "bad"}]}]},
])
def test_an_answer_of_the_wrong_shape_is_dropped_instead_of_failing_the_turn(structured):
    assert chat_components.normalize(structured) is None


def test_components_keep_their_order_and_an_unknown_kind_with_text_is_read_as_text():
    blocks = chat_components.normalize(_answer(
        {"kind": "text", "text": " Conclusión "},
        {"kind": "table", "columns": ["A"], "rows": []},
        "not a block",
        {"kind": "kpis", "items": [{"label": "ACoS", "value": "48.8%", "detail": "", "tone": "bad"}]},
        {"kind": "chart", "text": "un tipo que no existe"},
        {"kind": "action", "text": "Bajar el bid"},
    ))
    assert [b["kind"] for b in blocks] == ["text", "kpis", "text", "action"]
    assert blocks[0]["text"] == "Conclusión" and blocks[2]["text"] == "un tipo que no existe"


def test_a_wider_table_is_never_cut_and_a_short_row_is_padded():
    table = chat_components.normalize(_answer({"kind": "table", "columns": ["A", "B"], "rows": [
        [{"value": "x", "tone": "good"}, {"value": "1", "tone": "neutral"}, {"value": "extra", "tone": "bad"}],
        [{"value": "y", "tone": "red"}, "  42 "],
        [{"value": "z", "tone": "neutral"}],
    ]}))[0]
    assert table["columns"] == ["A", "B", ""]
    assert table["rows"][1][:2] == [{"value": "y", "tone": "neutral"}, {"value": "42", "tone": "neutral"}]
    assert len(table["rows"][2]) == 3


def test_a_table_puts_names_left_figures_right_and_color_only_on_a_judgment():
    table = chat_components.normalize(_answer({"kind": "table", "columns": ["Término", "Gasto"], "rows": [
        [{"value": "brita", "tone": "neutral"}, {"value": "$32.24", "tone": "bad"}],
        [{"value": "knife", "tone": "neutral"}, {"value": "$4.10", "tone": "good"}],
        [{"value": "scissor", "tone": "neutral"}, {"value": "$1.00", "tone": "neutral"}]]}))
    html = chat_components.render(table)
    assert html.count(TONE_COLOR["bad"]) == 1 and html.count(TONE_COLOR["good"]) == 1
    assert "text-align:left" in html and "text-align:right" in html and "&#36;32.24" in html


def test_kpis_keep_only_cards_with_a_figure_and_color_the_figure():
    block = chat_components.normalize(_answer({"kind": "kpis", "items": [
        {"label": "ACoS", "value": "48.8%", "detail": "target 30%", "tone": "bad"},
        {"label": "Vacía", "value": " ", "detail": "", "tone": "good"}]}))[0]
    assert [item["label"] for item in block["items"]] == ["ACoS"]
    html = chat_components.render([block])
    assert "repeat(1," in html and TONE_COLOR["bad"] in html and "target 30%" in html
    assert chat_components.plain_text([block]) == "ACoS: 48.8% (target 30%)"


def test_bars_are_proportional_to_the_highest_value_and_keep_a_small_value_visible():
    block = chat_components.normalize(_answer({"kind": "bars", "metric": "Gasto", "items": [
        {"label": "A", "value": 200, "display": "$200", "tone": "bad"},
        {"label": "B", "value": 1, "display": "$1", "tone": "neutral"},
        {"label": "C", "value": -5, "display": "-$5", "tone": "neutral"},
        {"label": "D", "value": 0, "display": "", "tone": "neutral"}]}))[0]
    assert [bars._width(item["value"], 200) for item in block["items"]] == [100.0, 1.5, 0, 0]
    assert block["items"][3]["display"] == "0"
    html = chat_components.render([block])
    assert "width:100.0%" in html and TONE_COLOR["bad"] in html


@pytest.mark.parametrize("value", ["12", True, float("nan"), None])
def test_a_bar_without_a_real_number_is_dropped(value):
    block = chat_components.normalize(_answer({"kind": "bars", "metric": "", "items": [
        {"label": "A", "value": value, "display": "x", "tone": "neutral"},
        {"label": "B", "value": 3, "display": "3", "tone": "neutral"}]}))[0]
    assert [item["label"] for item in block["items"]] == ["B"]


def test_a_trend_draws_its_series_and_marks_the_last_point():
    block = chat_components.normalize(_answer(trend.COMPONENT.example))[0]
    html = chat_components.render([block])
    x, y = trend._coordinates(block["points"])[-1]
    assert "<polyline" in html and f'cx="{x}" cy="{y}"' in html
    assert TONE_COLOR["bad"] in html and ">lun<" in html and ">dom<" in html
    assert chat_components.plain_text([block]).endswith("42 → 45 → 39 → 51 → 30 → 28 → 25 (lun a dom)")


def test_a_flat_trend_sits_in_the_middle_and_a_single_point_is_read_as_text():
    assert {y for _, y in trend._coordinates([5, 5, 5])} == {28.0}
    block = chat_components.normalize(_answer({"kind": "trend", "label": "Órdenes", "display": "25",
                                               "points": [25], "start": "", "end": "", "tone": "neutral"}))[0]
    assert block == {"kind": "text", "text": "Órdenes: 25"}


def test_a_trend_too_wide_to_scale_draws_flat_and_one_end_is_kept_in_its_text():
    assert {y for _, y in trend._coordinates([1e308, -1e308, 0])} == {28.0}
    block = chat_components.normalize(_answer({"kind": "trend", "label": "Órdenes", "display": "25",
                                               "points": [1, 2, 3], "start": "", "end": "dom", "tone": "neutral"}))[0]
    assert chat_components.plain_text([block]).endswith("1 → 2 → 3 (dom)")


def test_an_alert_with_an_unknown_level_is_info_and_each_level_looks_different():
    block = chat_components.normalize(_answer({"kind": "alert", "level": "urgent", "text": "Ojo"}))[0]
    assert block["level"] == "info"
    looks = {chat_components.render([{**block, "level": level}]) for level in ("info", "warning", "critical")}
    assert len(looks) == 3


def test_plain_text_is_one_paragraph_per_component():
    blocks = chat_components.normalize(_answer(
        {"kind": "text", "text": "Dos términos:"},
        {"kind": "table", "columns": ["Término", "Gasto"], "rows": [[{"value": "brita", "tone": "neutral"},
                                                                     {"value": "$32.24", "tone": "bad"}]]},
        {"kind": "action", "text": "Pausar brita"}))
    assert chat_components.plain_text(blocks) == "Dos términos:\n\nTérmino | Gasto\nbrita | $32.24\n\nPausar brita"


def _pie(*slices):
    return {"kind": "pie", "metric": "Gasto por ASIN",
            "items": [{"label": label, "value": value, "display": f"${value}"} for label, value in slices]}


def test_a_pie_splits_its_ring_in_proportion_and_the_panel_computes_each_share():
    block = chat_components.normalize(_answer(_pie(("A", 120), ("B", 60), ("C", 20))))[0]
    html = chat_components.render([block])
    assert [pie._shares(block["items"])] == [[60.0, 30.0, 10.0]]
    assert html.count("<circle") == 3 and "60.0%" in html and "10.0%" in html
    assert chat_components.plain_text([block]) == "Gasto por ASIN\nA: $120 (60.0%)\nB: $60 (30.0%)\nC: $20 (10.0%)"


def test_each_slice_starts_where_the_previous_one_ends_from_twelve_o_clock():
    block = chat_components.normalize(_answer(_pie(("A", 3), ("B", 1))))[0]
    assert [offset for offset, _ in pie._arcs(block["items"])] == [25.0, 50.0]


def test_a_pie_left_with_one_slice_is_read_as_text():
    block = chat_components.normalize(_answer(_pie(("A", 10), ("B", 0), ("C", -4))))[0]
    assert block == {"kind": "text", "text": "Gasto por ASIN: A $10"}


@pytest.mark.parametrize("value", ["12", True, float("nan"), None, -3, 0])
def test_a_slice_without_a_positive_number_is_dropped(value):
    block = chat_components.normalize(_answer(
        {"kind": "pie", "metric": "", "items": [{"label": "A", "value": value, "display": "x"},
                                                 {"label": "B", "value": 3, "display": "3"},
                                                 {"label": "C", "value": 1, "display": "1"}]}))[0]
    assert [item["label"] for item in block["items"]] == ["B", "C"]


def test_a_pie_with_more_slices_than_it_can_tell_apart_is_drawn_as_bars():
    block = chat_components.normalize(_answer(_pie(*[(f"S{n}", 10 - n) for n in range(8)])))[0]
    assert block["kind"] == "bars" and [item["label"] for item in block["items"]] == [f"S{n}" for n in range(8)]
    assert block["metric"] == "Gasto por ASIN"


def test_every_slice_of_a_full_pie_has_its_own_color():
    block = chat_components.normalize(_answer(_pie(*[(f"S{n}", 10 - n) for n in range(6)])))[0]
    html = chat_components.render([block])
    assert all(color in html for color in pie.SLICE_COLORS)
