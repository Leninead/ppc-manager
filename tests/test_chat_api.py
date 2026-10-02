"""PPC Manager's chat API for the Slack bot: the request it accepts, the turn it runs, and the door it runs behind."""
import functools
import http.client
import inspect
import json
import threading
import uuid

import pytest
import requests

from ai import client as ai_client
from ai import runtime
from core.chat import ads_scope, components, panel
from core.chat.ads_scope import AccountVehicle
from services.chat_api import account_scope, batch_reply
from services.chat_api.account_scope import AccountScopes, TurnScope
from services.chat_api.server import HEALTH_PATH, MAX_BODY_BYTES, TURN_PATH, ChatApiServer
from services.chat_api.turns import Place, TurnRequest, answer_turn, turn_note
from services.slack_bot import chat_client

TOKEN = "secreto"
TOOL = "mcp__ppc_manager__daily_metrics"
LABEL = "Serie diaria · Agency OS"
RESULT = {"type": "result", "session_id": "S9", "tool_calls": [TOOL], "failed_tools": [], "total_cost_usd": 0.42,
          "structured_output": {"answers": [{"questions": ["q1"],
                                             "blocks": [{"kind": "text", "text": "SB gastó $120."}]}],
                                "skipped": [{"question": "q2", "reason": "saludo"}]}}
HISTORY = {"title": "Conversación previa de este hilo de Slack", "content": "Lenin: primera"}


def body(**overrides):
    payload = {"conversation": "slack:CPPC:1000.000", "prompt": "q1 · Lenin: ¿cuánto gastó SB?\nq2 · Ana: hola",
               "question_ids": ["q1", "q2"],
               "questions": [{"asker": "Lenin", "text": "¿cuánto gastó SB?"}, {"asker": "Ana", "text": "hola"}],
               "place": {"direct": False, "channel_name": "ppc-ltd", "client": "Love To Dream", "country": "mx"},
               "requested_by": "slack:Lenin, Ana"}
    payload.update(overrides)
    return payload


class Scopes:
    def __init__(self, region="NA"):
        self.region = region

    def for_country(self, country, requested_by):
        if not self.region:
            return TurnScope(None, None)
        return TurnScope({"account_id": 1, "profile_id": "9", "requested_by": requested_by, "dynamic": True},
                         self.region)


class Provider:
    """Plays the AI provider's stream: the events of one turn, then the error it raises, if any."""

    def __init__(self, events, error):
        self.events = events
        self.error = error
        self.calls = []

    def __call__(self, **call):
        self.calls.append(call)
        yield from self.events
        if self.error:
            raise self.error


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(ai_client, "available_tools", lambda: frozenset({"ppc_manager", "amazon_ads", "datadive"}))
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])

    def install(*events, error=None):
        fake = Provider(events, error)
        monkeypatch.setattr(ai_client, "ask_stream", fake)
        return fake

    return install


def run(request, scopes=None):
    events, rows = [], []
    answer_turn(request, events.append, scopes=scopes or Scopes(),
                directory=lambda: {"title": "Directorio", "content": "cuentas"}, record=rows.append)
    return events, rows


# --- The request ---

def test_a_request_is_read_with_its_place_and_questions():
    request = TurnRequest.from_json(body(session_id="S1", session_region="NA", effort="medium", history=HISTORY))
    assert request.place == Place(direct=False, channel_name="ppc-ltd", client="Love To Dream", country="MX")
    assert request.questions == [("Lenin", "¿cuánto gastó SB?"), ("Ana", "hola")]
    assert (request.session_id, request.session_region, request.effort) == ("S1", "NA", "medium")
    assert request.history == HISTORY


@pytest.mark.parametrize("broken", [
    [], "texto", body(prompt=""), body(conversation=None), body(question_ids=[]), body(question_ids=["q1", 2]),
    body(question_ids=[f"q{i}" for i in range(51)]), body(questions="x"), body(questions=["x"]), body(place=None),
    body(history={"title": "sin contenido"}), body(prompt="x" * 200_001), body(requested_by=["Lenin"]),
])
def test_a_malformed_request_is_refused_before_the_provider(broken):
    with pytest.raises(ValueError):
        TurnRequest.from_json(broken)


# --- The turn ---

def test_a_batch_is_the_app_chats_turn_with_the_batch_schema(provider):
    fake = provider({"type": "tool", "name": TOOL}, {"type": "tool_result", "name": TOOL, "ok": True}, RESULT)
    events, rows = run(TurnRequest.from_json(body()))

    [call] = fake.calls
    assert call["output_schema"] == batch_reply.SCHEMA
    assert call["system"].endswith(batch_reply.GUIDE)
    assert call["input_text"].endswith("\n\nq1 · Lenin: ¿cuánto gastó SB?\nq2 · Ana: hola")
    assert "#ppc-ltd" in call["input_text"] and "Love To Dream (MX)" in call["input_text"]
    assert call["context"] == [{"title": "Directorio", "content": "cuentas"}]
    assert call["session_id"] is None
    assert call["ads_scope"]["requested_by"] == "slack:Lenin, Ana"

    assert events[:2] == [{"type": "tool", "name": TOOL, "label": LABEL},
                          {"type": "tool_result", "name": TOOL, "ok": True}]
    result = events[-1]
    assert result["type"] == "result"
    assert [(a["question_ids"], a["blocks"][0]["text"]) for a in result["answers"]] == [(["q1"], "SB gastó $120.")]
    assert (result["skipped"], result["missing"]) == ({"q2": "saludo"}, [])
    assert (result["session_id"], result["region"], result["new_session"]) == ("S9", "NA", True)
    assert (result["sources"], result["failed_sources"], result["tool_count"]) == ([LABEL], [], 1)
    assert result["cost_usd"] == 0.42

    [row] = rows
    assert (row.page, row.username, row.ads_account, row.cost_usd) == ("slack", "slack:Lenin, Ana", "Love To Dream",
                                                                       0.42)
    assert row.conversation_id == str(uuid.uuid5(uuid.NAMESPACE_URL, "slack:CPPC:1000.000"))
    assert row.question == "Lenin: ¿cuánto gastó SB?\nAna: hola"
    assert (row.answer, row.error, row.tools) == ("SB gastó $120.", None, (TOOL,))


def test_a_resumed_session_reads_no_opening_documents(provider):
    fake = provider(RESULT)
    events, _ = run(TurnRequest.from_json(body(session_id="S1", session_region="NA")))
    [call] = fake.calls
    assert (call["session_id"], call["context"]) == ("S1", [])
    assert events[-1]["new_session"] is False


def test_a_new_session_opens_with_the_directory_and_the_threads_history(provider):
    fake = provider(RESULT)
    events, _ = run(TurnRequest.from_json(body(history=HISTORY)))
    [call] = fake.calls
    assert [document["title"] for document in call["context"]] == ["Directorio", HISTORY["title"]]
    assert events[-1]["new_session"] is True


@pytest.mark.parametrize("session_region", ["EU", None])
def test_a_session_from_another_region_is_handed_back_without_asking_the_provider(provider, session_region):
    fake = provider(RESULT)
    events, rows = run(TurnRequest.from_json(body(session_id="S1", session_region=session_region)))
    assert (events[-1]["type"], events[-1]["kind"]) == ("error", "session_lost")
    assert fake.calls == [] and rows == []


def test_without_live_amazon_ads_the_turn_goes_with_ppc_managers_tools(provider):
    fake = provider(RESULT)
    events, _ = run(TurnRequest.from_json(body()), scopes=Scopes(region=None))
    [call] = fake.calls
    assert call["ads_scope"] is None and "amazon_ads" not in call["tools"]
    assert events[-1]["region"] is None


def test_the_note_tells_the_model_where_it_answers():
    channel = turn_note(Place(direct=False, channel_name="ppc-ltd", client="Love To Dream", country="MX"),
                        TurnScope({}, "NA"))
    assert "#ppc-ltd" in channel and "Love To Dream (MX)" in channel and "región NA" in channel
    direct = turn_note(Place(direct=True), TurnScope(None, None))
    assert "mensaje directo" in direct and "no está disponible" in direct


@pytest.mark.parametrize("error, kind", [
    (ai_client.QuotaExceeded("cuota", 300), "quota"),
    (ai_client.UpstreamError("se cortó"), "failed"),
    (ai_client.ProviderDown("caído"), "unavailable"),
])
def test_a_provider_error_reaches_the_bot_as_an_event_and_is_recorded(provider, error, kind):
    provider(error=error)
    events, rows = run(TurnRequest.from_json(body()))
    assert (events[-1]["type"], events[-1]["kind"], events[-1]["message"]) == ("error", kind, str(error))
    assert events[-1].get("retry_after") == (300 if kind == "quota" else None)
    [row] = rows
    assert (row.answer, row.error) == (None, str(error))


def test_a_stream_without_a_result_is_a_failed_turn(provider):
    provider({"type": "tool", "name": TOOL})
    events, _ = run(TurnRequest.from_json(body()))
    assert (events[-1]["type"], events[-1]["kind"]) == ("error", "failed")


def test_a_session_the_provider_lost_asks_the_bot_for_the_thread_instead_of_failing(provider):
    provider(error=ai_client.UpstreamError("session not found"))
    events, rows = run(TurnRequest.from_json(body(session_id="S1", session_region="NA")))
    assert events[-1] == {"type": "error", "kind": "session_lost", "message": "session not found"}
    assert rows == []


def test_a_turn_record_that_fails_never_costs_the_answer(provider):
    provider(RESULT)
    events = []

    def broken(row):
        raise RuntimeError("base caída")

    answer_turn(TurnRequest.from_json(body()), events.append, scopes=Scopes(), directory=lambda: None, record=broken)
    assert events[-1]["type"] == "result"


# --- Which account opens live Amazon Ads ---

def vehicle(region, country):
    return AccountVehicle(account_id=1 if region == "NA" else 2, profile_id="9", region=region, country_code=country,
                          client="X")


@pytest.fixture
def ai_enabled(monkeypatch):
    monkeypatch.setattr(account_scope.ai_config, "AI_ENABLED", True)


def test_a_channels_country_picks_the_live_amazon_ads_region(ai_enabled):
    scopes = AccountScopes(load_vehicles=lambda: [vehicle("NA", "US"), vehicle("NA", "MX"), vehicle("EU", "DE")])
    eu = scopes.for_country("DE", "slack:Lenin")
    assert (eu.region, eu.ads_scope["account_id"], eu.ads_scope["requested_by"]) == ("EU", 2, "slack:Lenin")
    assert scopes.for_country("", "slack:Lenin").region == "NA"


def test_without_connected_accounts_the_turn_goes_without_live_amazon_ads(ai_enabled):
    scope = AccountScopes(load_vehicles=lambda: []).for_country("MX", "slack:Lenin")
    assert (scope.ads_scope, scope.region) == (None, None)


def test_the_accounts_are_read_again_only_after_two_minutes(ai_enabled):
    reads, now = [], [0.0]

    def load():
        reads.append(now[0])
        return [vehicle("NA", "US")]

    scopes = AccountScopes(load_vehicles=load, clock=lambda: now[0])
    scopes.for_country("US", "x")
    scopes.for_country("US", "x")
    now[0] = 121.0
    scopes.for_country("US", "x")
    assert reads == [0.0, 121.0]


# --- The door ---

@pytest.fixture
def chat_api():
    servers = []

    def start(answer, token=TOKEN):
        server = ChatApiServer(("127.0.0.1", 0), token, scopes=Scopes(), answer=answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def never_called(request, emit, *, scopes):
    raise AssertionError("the turn ran behind a closed door")


def post(url, payload, token=TOKEN):
    return requests.post(url + TURN_PATH, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=10)


def test_the_health_check_answers_without_a_token(chat_api):
    url = chat_api(never_called)
    assert requests.get(url + HEALTH_PATH, timeout=10).json() == {"ok": True}
    assert requests.get(url + "/otra", timeout=10).status_code == 404


@pytest.mark.parametrize("token", ["", "otro", TOKEN + "x"])
def test_a_wrong_token_is_refused_before_the_turn(chat_api, token):
    assert post(chat_api(never_called), body(), token=token).status_code == 401


def test_a_server_without_a_token_refuses_everyone(chat_api):
    assert post(chat_api(never_called, token=""), body(), token="").status_code == 401


def test_a_malformed_or_oversized_body_is_refused_before_the_turn(chat_api):
    url = chat_api(never_called)
    assert post(url, body(question_ids=[])).status_code == 400
    assert requests.post(url + TURN_PATH, data=b"{no es json", timeout=10,
                         headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 400
    for length, status in ((str(MAX_BODY_BYTES + 1), 413), ("muchos", 400)):
        connection = http.client.HTTPConnection("127.0.0.1", int(url.rsplit(":", 1)[1]), timeout=10)
        connection.putrequest("POST", TURN_PATH)
        connection.putheader("Authorization", f"Bearer {TOKEN}")
        connection.putheader("Content-Length", length)
        connection.endheaders()
        assert connection.getresponse().status == status
        connection.close()


def test_a_turn_that_breaks_still_ends_the_stream_with_an_error(chat_api):
    def broken(request, emit, *, scopes):
        emit({"type": "tool", "name": TOOL, "label": LABEL})
        raise KeyError("model")

    response = post(chat_api(broken), body())
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["Content-Type"] == "application/x-ndjson"
    assert lines == [{"type": "tool", "name": TOOL, "label": LABEL},
                     {"type": "error", "kind": "failed", "message": "KeyError"}]


# --- The bot's client against the real door ---

def test_the_bots_client_reads_the_chats_turn_through_the_door(chat_api, provider):
    provider({"type": "tool", "name": TOOL}, {"type": "tool_result", "name": TOOL, "ok": True}, RESULT)
    rows = []
    url = chat_api(functools.partial(answer_turn, directory=lambda: None, record=rows.append))
    heard = []
    outcome = chat_client.ChatClient(url, TOKEN).turn(body(), heard.append)
    assert heard == [LABEL]
    assert [(a.question_ids, a.blocks[0]["text"]) for a in outcome.reply.answers] == [(("q1",), "SB gastó $120.")]
    assert (outcome.reply.skipped, outcome.reply.missing) == ({"q2": "saludo"}, ())
    assert (outcome.session_id, outcome.region, outcome.new_session) == ("S9", "NA", True)
    assert (outcome.sources, outcome.tool_count, outcome.cost_usd) == ((LABEL,), 1, 0.42)
    assert len(rows) == 1


@pytest.mark.parametrize("error, raised", [
    (ai_client.QuotaExceeded("cuota", 300), chat_client.ChatQuota),
    (ai_client.ProviderDown("caído"), chat_client.ChatError),
])
def test_the_bots_client_hears_the_chats_errors(chat_api, provider, error, raised):
    provider(error=error)
    url = chat_api(functools.partial(answer_turn, directory=lambda: None, record=lambda row: None))
    with pytest.raises(raised) as caught:
        chat_client.ChatClient(url, TOKEN).turn(body(), lambda label: None)
    assert str(caught.value) == str(error)
    if raised is chat_client.ChatQuota:
        assert caught.value.retry_after == 300


@pytest.mark.parametrize("session_region, stream, error", [
    ("NA", (), ai_client.UpstreamError("session not found")),
    ("EU", (RESULT,), None),
])
def test_the_bots_client_hears_a_session_that_cannot_be_resumed(chat_api, provider, session_region, stream, error):
    provider(*stream, error=error)
    url = chat_api(functools.partial(answer_turn, directory=lambda: None, record=lambda row: None))
    with pytest.raises(chat_client.SessionLost):
        chat_client.ChatClient(url, TOKEN).turn(body(session_id="S1", session_region=session_region),
                                                lambda label: None)


def test_the_bots_client_names_a_wrong_token_and_an_unreachable_chat(chat_api):
    url = chat_api(never_called)
    with pytest.raises(chat_client.ChatError, match="CHAT_API_TOKEN"):
        chat_client.ChatClient(url, "otro").turn(body(), lambda label: None)
    with pytest.raises(chat_client.ChatError, match="no pude llegar"):
        chat_client.ChatClient("http://127.0.0.1:9", TOKEN).turn(body(), lambda label: None)


# --- What the turn takes from ppc-manager without changing it: these fail the day the app moves under it ---

def test_the_private_call_builder_still_takes_a_guide_and_a_schema():
    parameters = inspect.signature(runtime._followup_call).parameters
    assert list(parameters)[:7] == ["slug", "session_id", "question", "ads_scope", "context_docs", "note", "thread"]
    assert {"guide", "output_schema", "effort"} <= set(parameters)
    assert list(inspect.signature(runtime._remember_session).parameters) == ["call", "resp"]


def test_the_panels_tool_labels_are_still_there():
    labels = panel._L["es"]
    assert panel._tool_labels([TOOL], labels) == [LABEL]
    assert panel._failed_labels([TOOL], [TOOL], labels) == [LABEL]


def test_the_ads_scope_helpers_stay_pure():
    assert {"build_vehicles", "pick_vehicle", "SLUG", "AccountVehicle"} <= set(dir(ads_scope))


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
    item = batch_reply.SCHEMA["properties"]["answers"]["items"]["properties"]["blocks"]["items"]
    assert item["anyOf"] == [component.schema() for component in components.CATALOG]
    assert batch_reply.GUIDE.startswith(components.GUIDE)


def test_the_assistant_knows_its_name():
    assert "Te llamás Capybaras Assistant" in batch_reply.GUIDE
