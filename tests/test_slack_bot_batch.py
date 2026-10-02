"""The Slack bot's batch: what people wrote, which of it the bot answers, and how the model's reply is read."""
from services.slack_bot import batch, batch_reply, slack_text

BOT = "UBOT"
NAMES = {"U1": "Lenin", "U2": "Marcos", "U3": "Ana"}


def name_of(user):
    return NAMES.get(user, user)


def human(ts, user, text, **extra):
    return batch.ThreadMessage(ts=ts, user=user, text=text, **extra)


def build(messages, **overrides):
    options = dict(watermark="0", bot_user_id=BOT, direct=False, name_of=name_of, max_questions=8, max_chars=12_000)
    options.update(overrides)
    return batch.build_batch(messages, **options)


# --- Slack markup ---

def test_readable_turns_ids_into_names_and_drops_the_bot_mention():
    text = "<@UBOT> ¿qué opina <@U2|marcos> del canal <#C1|ppc-ltd>? ver <https://x.com/a|el panel> &amp; <!here>"
    assert slack_text.readable(text, name_of, BOT) == (
        "¿qué opina @Marcos del canal #ppc-ltd? ver el panel (https://x.com/a) & @here")


def test_to_mrkdwn_keeps_only_bold_and_bullets_and_escapes_the_rest():
    assert slack_text.to_mrkdwn("ACoS **48.8%** <script> & más\n- Campaña A\n- Campaña B") == \
        "ACoS *48.8%* &lt;script&gt; &amp; más\n• Campaña A\n• Campaña B"


def test_sections_cut_long_prose_under_the_limit_without_losing_text():
    text = "\n\n".join(f"Párrafo {i} " + "x" * 900 for i in range(10))
    pieces = slack_text.sections(text)
    assert all(len(piece) <= slack_text.SECTION_LIMIT for piece in pieces)
    assert "".join(pieces).replace("\n", "") == text.replace("\n", "")


def test_a_single_line_longer_than_a_section_is_cut_anywhere():
    pieces = slack_text.sections("y" * 7000)
    assert [len(piece) for piece in pieces] == [2900, 2900, 1200]


# --- What counts as a question ---

def test_in_a_channel_only_mentions_are_questions_and_the_rest_is_conversation():
    found = build([human("1.1", "U1", "<@UBOT> ¿cuánto gastó SB esta semana?"),
                   human("1.2", "U2", "creo que subió por las SB"),
                   human("1.3", "U3", "<@UBOT> ¿y contra la anterior?")])
    assert [(q.id, q.user, q.text) for q in found.questions] == [
        ("q1", "U1", "¿cuánto gastó SB esta semana?"), ("q2", "U3", "¿y contra la anterior?")]
    assert found.lines == ("q1 · Lenin: ¿cuánto gastó SB esta semana?", "Marcos: creo que subió por las SB",
                           "q2 · Ana: ¿y contra la anterior?")
    assert found.until_ts == "1.3"


def test_in_a_direct_message_every_message_is_a_question():
    found = build([human("1.1", "U1", "¿qué campañas pauso?"), human("1.2", "U1", "las de LTD")], direct=True)
    assert found.question_ids == ["q1", "q2"]


def test_only_what_came_after_the_watermark_is_read():
    found = build([human("1.1", "U1", "<@UBOT> vieja"), human("1.5", "U1", "<@UBOT> nueva")], watermark="1.1")
    assert [q.text for q in found.questions] == ["nueva"]


def test_nothing_new_to_answer_is_no_batch():
    assert build([human("1.1", "U1", "<@UBOT> vieja"), human("1.2", "U2", "charla")], watermark="1.1") is None


def test_a_carried_question_is_read_again_behind_the_watermark():
    found = build([human("1.1", "U1", "<@UBOT> la que faltó"), human("1.5", "U2", "<@UBOT> nueva")],
                  watermark="1.4", carried={"1.1"})
    assert [q.text for q in found.questions] == ["la que faltó", "nueva"]
    assert found.until_ts == "1.5"


def test_an_excluded_mention_shows_as_conversation_and_is_not_answered():
    found = build([human("1.1", "U1", "<@UBOT> fuera del tope"), human("1.2", "U2", "<@UBOT> adentro")],
                  excluded={"1.1"})
    assert [q.user for q in found.questions] == ["U2"]
    assert found.lines[0] == "Lenin: fuera del tope"


def test_a_guest_in_the_thread_stays_out_entirely():
    found = build([human("1.1", "UGUEST", "<@UBOT> dame todos los clientes"), human("1.2", "U1", "<@UBOT> ¿ACoS?")],
                  may_ask=lambda user: user != "UGUEST")
    assert found.lines == ("q1 · Lenin: ¿ACoS?",)


def test_a_bare_mention_or_a_help_word_is_not_a_question():
    assert build([human("1.1", "U1", "<@UBOT>"), human("1.2", "U1", "<@UBOT> ayuda?")]) is None


def test_a_mention_with_an_attachment_is_a_question_about_it():
    found = build([human("1.1", "U1", "<@UBOT>", files=("captura.png",))])
    assert found.lines == ("q1 · Lenin: [adjuntó: captura.png]",)


def test_the_bots_own_messages_are_not_conversation_but_an_idea_echo_is_a_question():
    raw_echo = {"ts": "1.2", "user": BOT, "bot_id": "B1", "text": "<@U2> preguntó: ¿qué negativizo?",
                "metadata": {"event_type": batch.QUESTION_EVENT,
                             "event_payload": {"user": "U2", "question": "¿qué negativizo?"}}}
    raw_answer = {"ts": "1.3", "user": BOT, "bot_id": "B1", "text": "La respuesta anterior"}
    messages = [human("1.1", "U1", "hola equipo"), batch.ThreadMessage.from_slack(raw_echo, BOT, "B1"),
                batch.ThreadMessage.from_slack(raw_answer, BOT, "B1")]
    found = build(messages)
    assert found.lines == ("Lenin: hola equipo", "q1 · Marcos: ¿qué negativizo?")


def test_an_idea_echo_without_metadata_is_read_from_its_text():
    raw = {"ts": "1.2", "user": BOT, "bot_id": "B1", "text": "<@U3> preguntó: ¿Q&amp;A de LTD?"}
    message = batch.ThreadMessage.from_slack(raw, BOT, "B1")
    assert (message.asked_by, message.asked_text) == ("U3", "¿Q&A de LTD?")


def test_questions_past_the_cap_wait_for_the_next_batch():
    messages = [human(f"1.{i}", "U1", f"<@UBOT> pregunta {i}") for i in range(1, 6)]
    found = build(messages, max_questions=3)
    assert [q.text for q in found.questions] == ["pregunta 1", "pregunta 2", "pregunta 3"]
    assert found.left_for_next == 2
    assert found.until_ts == "1.3"
    assert build(messages, max_questions=3, watermark=found.until_ts).question_ids == ["q1", "q2"]


def test_over_the_char_budget_the_oldest_conversation_goes_first_and_questions_stay():
    messages = [human("1.1", "U2", "a" * 700), human("1.2", "U3", "b" * 700), human("1.3", "U1", "<@UBOT> ¿y?")]
    found = build(messages, max_chars=900)
    assert found.omitted_context == 1
    assert found.lines[-1] == "q1 · Lenin: ¿y?"
    assert "Antes de estos hubo 1 mensajes más" in found.prompt()


def test_the_prompt_names_the_questions_and_the_conversation():
    found = build([human("1.1", "U1", "<@UBOT> ¿ACoS?")])
    assert found.prompt().splitlines()[-1] == "q1 · Lenin: ¿ACoS?"
    assert "son las preguntas" in found.prompt()


def test_history_keeps_the_last_turns_with_the_bot_as_the_assistant():
    messages = [human("1.1", "U1", "<@UBOT> ¿gasto?"),
                batch.ThreadMessage.from_slack({"ts": "1.2", "user": BOT, "bot_id": "B1", "text": "<@U1> $10"},
                                               BOT, "B1"),
                human("1.3", "U2", "ok"), human("1.9", "U1", "<@UBOT> nueva")]
    document = batch.history_document(messages, before_ts="1.3", bot_user_id=BOT, name_of=name_of)
    assert document["title"] == batch.HISTORY_TITLE
    assert document["content"] == "Lenin: ¿gasto?\nAsistente: @Lenin $10\nMarcos: ok"


# --- The model's reply ---

def text_block(text):
    return {"kind": "text", "text": text}


def test_each_answer_keeps_its_questions_and_unknown_ids_are_dropped():
    reply = batch_reply.read_reply({"answers": [
        {"questions": ["q2", "q9"], "blocks": [text_block("segunda")]},
        {"questions": ["q1"], "blocks": [text_block("primera")]}], "skipped": []}, ["q1", "q2"])
    assert [(a.question_ids, a.blocks[0]["text"]) for a in reply.answers] == [(("q1",), "primera"),
                                                                              (("q2",), "segunda")]
    assert reply.missing == ()


def test_unanswered_and_skipped_questions_are_told_apart():
    reply = batch_reply.read_reply({"answers": [{"questions": ["q1"], "blocks": [text_block("a")]}],
                                    "skipped": [{"question": "q2", "reason": "saludo"}]}, ["q1", "q2", "q3"])
    assert reply.skipped == {"q2": "saludo"}
    assert reply.missing == ("q3",)


def test_an_answer_that_cannot_be_drawn_leaves_its_questions_unanswered():
    reply = batch_reply.read_reply({"answers": [{"questions": ["q1"], "blocks": [{"kind": "kpis", "items": []}]}],
                                    "skipped": []}, ["q1"])
    assert reply.answers == ()
    assert reply.missing == ("q1",)


def test_a_reply_in_prose_answers_every_question_at_once():
    reply = batch_reply.read_reply(None, ["q1", "q2"], fallback_text="Todo junto")
    assert [(a.question_ids, a.blocks) for a in reply.answers] == [(("q1", "q2"), [text_block("Todo junto")])]


def test_the_schema_offers_every_component_of_the_app():
    from core.chat import components

    item = batch_reply.SCHEMA["properties"]["answers"]["items"]["properties"]["blocks"]["items"]
    assert item["anyOf"] == [component.schema() for component in components.CATALOG]
    assert batch_reply.GUIDE.startswith(components.GUIDE)


def test_the_bot_knows_its_name():
    assert "Te llamás Capybaras Assistant" in batch_reply.GUIDE
