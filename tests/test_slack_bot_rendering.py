"""The Slack bot's rendering: every chat component as Block Kit or PNG, in the order the model wrote them."""
import io

import pytest
from PIL import Image

from core.chat import components
from services.slack_bot import charts, to_slack

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def parts_of(*blocks, **options):
    return to_slack.answer_parts(components.normalize({"blocks": list(blocks)}), **options)


def message_blocks(parts):
    return [part.blocks for part in parts if isinstance(part, to_slack.MessagePart)]


@pytest.mark.parametrize("component", components.CATALOG, ids=lambda component: component.kind)
def test_every_component_example_renders_within_slacks_limits(component):
    parts = parts_of(component.example)
    assert parts
    for part in parts:
        if isinstance(part, to_slack.ChartPart):
            assert part.png.startswith(PNG_SIGNATURE)
            assert part.alt
            continue
        assert 0 < len(part.blocks) <= 50
        assert part.text
        for block in part.blocks:
            if block["type"] == "section" and "text" in block:
                assert len(block["text"]["text"]) <= 3000


def test_text_converts_the_chat_prose_rules():
    [part] = parts_of({"kind": "text", "text": "La cuenta corre a **ACoS 48.8%**.\n- Campaña A"})
    assert part.blocks == [to_slack.section("La cuenta corre a *ACoS 48.8%*.\n• Campaña A")]


def test_kpis_become_fields_with_their_tone_and_detail():
    [part] = parts_of({"kind": "kpis", "items": [
        {"label": "ACoS", "value": "48.8%", "detail": "target 30%", "tone": "bad"},
        {"label": "Órdenes", "value": "198", "detail": "", "tone": "neutral"}]})
    assert part.blocks == [{"type": "section", "fields": [
        {"type": "mrkdwn", "text": "*ACoS*\n48.8% 🔴\n_target 30%_"},
        {"type": "mrkdwn", "text": "*Órdenes*\n198"}]}]


def test_a_table_is_slacks_table_block_with_a_bold_header_and_figures_right_aligned():
    [part] = parts_of({"kind": "table", "columns": ["Cuenta", "ACoS"], "rows": [
        [{"value": "Cuenta A", "tone": "neutral"}, {"value": "98.8%", "tone": "bad"}]]})
    [table] = part.blocks
    assert table["type"] == "table"
    assert table["column_settings"] == [{"is_wrapped": True}, {"align": "right"}]
    header, row = table["rows"]
    assert header[0]["elements"][0]["elements"][0] == {"type": "text", "text": "Cuenta", "style": {"bold": True}}
    assert row == [{"type": "raw_text", "text": "Cuenta A"}, {"type": "raw_text", "text": "98.8% 🔴"}]


def test_a_table_ends_its_message_so_what_follows_stays_below_it():
    parts = parts_of({"kind": "text", "text": "Arriba"},
                     {"kind": "table", "columns": ["A", "B"], "rows": [[{"value": "x", "tone": "neutral"},
                                                                        {"value": "1", "tone": "neutral"}]]},
                     {"kind": "action", "text": "Abajo"})
    first, second = message_blocks(parts)
    assert [block["type"] for block in first] == ["section", "table"]
    assert second == [to_slack.section(">➡️ Abajo")]


def test_two_tables_go_in_two_messages():
    table = {"kind": "table", "columns": ["A"], "rows": [[{"value": "x", "tone": "neutral"}]]}
    assert [[b["type"] for b in blocks] for blocks in message_blocks(parts_of(table, table))] == [["table"], ["table"]]


def test_a_table_too_big_for_slack_is_sent_aligned_in_a_code_block():
    rows = [[{"value": f"Campaña {i}", "tone": "neutral"}, {"value": f"{i}.0%", "tone": "neutral"}]
            for i in range(150)]
    blocks = [block for part in message_blocks(parts_of({"kind": "table", "columns": ["Campaña", "ACoS"],
                                                         "rows": rows})) for block in part]
    assert all(block["type"] == "section" and block["text"]["text"].startswith("```") for block in blocks)
    assert "Campaña 149" in blocks[-1]["text"]["text"]


def test_charts_are_images_between_the_messages_around_them():
    parts = parts_of({"kind": "text", "text": "Antes"},
                     {"kind": "bars", "metric": "Gasto", "items": [{"label": "A", "value": 2, "display": "$2",
                                                                    "tone": "neutral"}]},
                     {"kind": "text", "text": "Después"})
    assert [type(part).__name__ for part in parts] == ["MessagePart", "ChartPart", "MessagePart"]
    assert parts[1].title == "Gasto"
    assert parts[1].alt == "Gasto\nA: $2"


def test_alert_and_action_are_quoted_with_their_mark():
    [part] = parts_of({"kind": "alert", "level": "warning", "text": "Datos de **ayer**"},
                      {"kind": "action", "text": "Pausar A"})
    assert part.blocks == [to_slack.section(">⚠️ Datos de *ayer*"), to_slack.section(">➡️ Pausar A")]


def test_the_header_sources_and_mention_go_first():
    [part] = parts_of({"kind": "text", "text": "Hola"}, header="Para <@U1>", sources="Leyó: Campañas",
                      mention="<@U1>")
    assert part.blocks[:2] == [to_slack.context("Para <@U1>"), to_slack.context("Leyó: Campañas")]
    assert part.text == "<@U1> Hola"


def test_a_long_answer_is_split_under_slacks_block_limit():
    text = "\n\n".join("p" * 2800 for _ in range(60))
    parts = parts_of({"kind": "text", "text": text})
    assert len(parts) == 2
    assert all(len(part.blocks) <= 45 for part in parts)


def test_ideas_are_buttons_that_carry_the_whole_question():
    question = "¿Qué search terms venden y todavía no tengo en exact en ninguna de las campañas activas de la cuenta?"
    blocks = to_slack.ideas_blocks("Ideas:", [question])
    button = blocks[1]["elements"][0]
    assert button["action_id"] == "idea_0"
    assert button["value"] == question
    assert len(button["text"]["text"]) <= 75


@pytest.mark.parametrize("block", [
    {"kind": "bars", "metric": "Gasto sin ventas", "items": [
        {"label": "Campaña con un nombre larguísimo que no entra en el ancho", "value": 203.8, "display": "$203.80",
         "tone": "bad"}, {"label": "Marca", "value": 0, "display": "$0.00", "tone": "neutral"}]},
    {"kind": "pie", "metric": "Gasto por tipo de match", "items": [
        {"label": "Exact", "value": 420, "display": "$420"}, {"label": "Phrase", "value": 160, "display": "$160"}]},
    {"kind": "trend", "label": "Órdenes diarias", "display": "25 el domingo", "points": [3, 3, 3],
     "start": "lun", "end": "dom", "tone": "neutral"},
], ids=lambda block: block["kind"])
def test_charts_draw_a_png_at_twice_the_panel_width(block):
    image = Image.open(io.BytesIO(charts.draw(components.normalize({"blocks": [block]})[0])))
    assert image.format == "PNG"
    assert image.width == 840


def test_the_chart_font_has_accents():
    assert charts.font_path() is not None, "reportlab's Vera.ttf is missing: Pillow's own font has no ñ or tildes"
