"""El techo de las respuestas del MCP: cortar siempre, y decir siempre que se cortó."""
import json

from services.mcp_server.limits import MAX_ROWS, MAX_ROWS_CHARS, MAX_TEXT_CHARS, clip_text, page

# A real campaign_structure negative: 50 of these overflow the provider's 20000 characters.
_NEGATIVE = {"campaign": "ShaperShorts - B09467RFYY | SP - KW | Branded KWs 1 TOS +100", "campaign_id": "26578476765418",
             "ad_group": "Body Shaper Shorts", "ad_group_id": "131949007616102", "level": "ad_group",
             "kind": "Keyword", "negative": "44d bras wide shapermint", "match_type": "NEGATIVE_EXACT",
             "state": "ENABLED", "negative_id": "79308573823496"}


def _negatives(count: int) -> list[dict]:
    return [dict(_NEGATIVE, negative_id=str(79308573823496 + index)) for index in range(count)]


def test_a_short_result_travels_whole_and_says_nothing_about_truncation():
    result = page([1, 2, 3]).as_payload(what="cuentas")

    assert result["rows"] == [1, 2, 3]
    assert (result["total"], result["showing"]) == (3, 3)
    assert "note" not in result


def test_a_long_result_is_cut_and_the_note_says_how_many_there_were():
    result = page(list(range(1000))).as_payload(what="términos")

    assert len(result["rows"]) == MAX_ROWS
    assert result["total"] == 1000
    assert "1000 términos" in result["note"]
    assert f"offset={MAX_ROWS}" in result["note"]


def test_the_note_tells_the_model_not_to_answer_as_if_it_had_everything():
    note = page(list(range(1000))).as_payload(what="filas")["note"]

    assert "No respondas como si estas fueran todas." in note


def test_a_caller_asking_for_more_than_the_ceiling_still_gets_the_ceiling():
    assert len(page(list(range(1000)), limit=10_000).rows) == MAX_ROWS


def test_a_caller_asking_for_less_gets_less():
    assert len(page(list(range(1000)), limit=5).rows) == 5


def test_a_zero_or_negative_limit_never_yields_an_empty_page():
    assert len(page(list(range(10)), limit=0).rows) == 1
    assert len(page(list(range(10)), limit=-5).rows) == 1


def test_paging_walks_the_whole_set_without_gaps_or_repeats():
    rows = list(range(450))
    seen = []
    offset = 0
    while True:
        current = page(rows, offset=offset)
        seen += current.rows
        if not current.truncated:
            break
        offset += len(current.rows)

    assert seen == rows


def test_a_page_of_wide_rows_stops_before_the_provider_cuts_it():
    result = page(_negatives(572), limit=50).as_payload(what="negativos")

    assert 0 < result["showing"] < 50
    assert len(json.dumps(result, ensure_ascii=False, indent=2)) <= MAX_TEXT_CHARS
    assert f"trae {result['showing']}, desde la posición 0" in result["note"]
    assert f"offset={result['showing']}" in result["note"]


def test_a_row_past_the_budget_on_its_own_still_travels_alone():
    rows = [{"text": "x" * (MAX_ROWS_CHARS * 2)}, {"text": "y"}]

    assert page(rows).rows == rows[:1]


def test_paging_wide_rows_walks_the_whole_set_without_gaps_or_repeats():
    rows = _negatives(300)
    seen = []
    offset = 0
    while True:
        current = page(rows, offset=offset)
        seen += current.rows
        if not current.truncated:
            break
        offset += len(current.rows)

    assert seen == rows


def test_the_page_says_how_many_there_are_before_its_rows():
    keys = list(page(list(range(1000))).as_payload(what="filas"))

    assert keys == ["total", "showing", "offset", "note", "rows"]


def test_the_last_page_is_not_flagged_as_truncated():
    assert page(list(range(250)), offset=200).truncated is False


def test_an_offset_past_the_end_gives_nothing_and_does_not_crash():
    result = page(list(range(10)), offset=999).as_payload(what="filas")

    assert result["rows"] == []
    assert result["total"] == 10


def test_a_short_text_is_left_alone():
    assert clip_text("corto") == "corto"


def test_a_long_text_is_cut_at_a_visible_edge_that_states_the_real_size():
    clipped = clip_text("x" * 50_000, what="análisis")

    assert clipped.startswith("x" * MAX_TEXT_CHARS)
    assert "50000 caracteres" in clipped
    assert "análisis" in clipped
