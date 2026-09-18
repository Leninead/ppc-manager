"""El transporte HTTP: qué deja pasar, qué rechaza y qué herramientas publica."""
import asyncio
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from services.mcp_server.http_app import (
    DEFAULT_ALLOWED_HOSTS,
    HEALTH_PATH,
    MCP_PATH,
    allowed_hosts,
    build_app,
    build_server,
)
from services.mcp_server.server import build_tools

TOKEN = "un-token-de-servicio"


@pytest.fixture
def client():
    # testserver es el Host que pone TestClient: sin declararlo, la protección anti DNS-rebinding
    # del SDK contesta 421 antes de que el token llegue a decidir nada.
    app = build_app(build_tools(object()), TOKEN, hosts=["testserver"])
    with TestClient(app) as test_client:
        yield test_client


def test_health_answers_without_a_token_so_docker_can_check_the_process(client):
    response = client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["service"] == "ppc-manager"


def test_health_lists_the_tools_so_a_deploy_can_be_verified_from_outside(client):
    assert set(client.get(HEALTH_PATH).json()["tools"]) == {
        "list_accounts", "list_analyses", "get_analysis", "top_search_terms", "daily_metrics", "breakdown",
        "accounts_overview", "campaign_health", "idle_targets"}


def test_the_mcp_endpoint_without_a_token_is_rejected(client):
    assert client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401


@pytest.mark.parametrize("header", ["Bearer otro-token", "Basic " + TOKEN, TOKEN, ""])
def test_the_mcp_endpoint_with_a_wrong_token_is_rejected(client, header):
    response = client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={"Authorization": header})

    assert response.status_code == 401


def test_a_rejected_request_does_not_explain_what_was_missing(client):
    """A quien no tiene el token no se le cuenta cómo conseguirlo."""
    body = client.post(MCP_PATH, json={}, headers={"Authorization": "Bearer otro"}).json()

    assert body == {"error": "unauthorized"}


def test_the_right_token_reaches_the_protocol_instead_of_the_middleware(client):
    """Con el token correcto la respuesta ya no es 401: la da el protocolo MCP, no el guardia."""
    response = client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code != 401


def test_the_server_instructions_tell_the_model_not_to_trust_a_truncated_page():
    server = build_server(build_tools(object()))

    assert "Nunca" in server.instructions and "todos los datos" in server.instructions


def test_the_server_declares_itself_read_only_to_whoever_connects():
    assert "sólo lectura" in build_server(build_tools(object())).instructions


def test_every_published_tool_carries_a_typed_schema():
    server = build_server(build_tools(object()))

    for tool in asyncio.run(server.list_tools()):
        schema = tool.input_schema or {}
        for name, spec in schema.get("properties", {}).items():
            assert spec.get("type"), f"{tool.name}.{name} llegaría al modelo sin tipo"


def test_the_account_tools_require_the_profile_they_talk_about():
    server = build_server(build_tools(object()))
    required = {tool.name: (tool.input_schema or {}).get("required", [])
                for tool in asyncio.run(server.list_tools())}

    assert "profile_id" in required["get_analysis"]
    assert "profile_id" in required["top_search_terms"]
    assert required["daily_metrics"] == ["profile_id"]      # la ventana y la campaña son opcionales
    assert sorted(required["breakdown"]) == ["by", "profile_id"]
    assert required["list_accounts"] == []      # el punto de entrada no pide nada


def test_the_breakdown_offers_its_dimensions_and_metrics_as_closed_lists():
    """Un enum en el schema: el modelo elige entre lo que existe en vez de adivinar un nombre."""
    server = build_server(build_tools(object()))
    schema = next(tool.input_schema for tool in asyncio.run(server.list_tools()) if tool.name == "breakdown")

    assert schema["properties"]["by"]["enum"] == ["campaign", "portfolio", "product", "match_type", "search_term"]
    assert schema["properties"]["product"]["enum"] == ["", "SP", "SB", "SD"]
    assert "acos" in schema["properties"]["sort_by"]["enum"]


def test_the_figure_tools_offer_both_sources_of_sponsored_products_as_a_closed_list():
    """Campaign reports or search terms: the model picks one of the two, it never guesses a third."""
    server = build_server(build_tools(object()))
    schemas = {tool.name: tool.input_schema for tool in asyncio.run(server.list_tools())}

    for name in ("accounts_overview", "daily_metrics", "breakdown"):
        assert schemas[name]["properties"]["source"]["enum"] == ["", "campaigns", "search_terms"], name
        assert "source" not in schemas[name].get("required", []), name


def test_the_dns_rebinding_protection_stays_on_with_an_explicit_host_list(monkeypatch):
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)

    assert "localhost:8790" in allowed_hosts()


def test_the_allowed_hosts_can_be_declared_by_environment(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.capybaras.agency, otro:8790 ,")

    assert allowed_hosts() == ["mcp.capybaras.agency", "otro:8790"]


def test_a_host_outside_the_list_never_reaches_the_protocol():
    """El 421 del SDK llega antes que el token: un Host ajeno no puede ni intentar autenticarse."""
    app = build_app(build_tools(object()), TOKEN, hosts=["esperado"])

    with TestClient(app, base_url="http://intruso") as client:
        response = client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                               headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 421


def test_the_mcp_path_answers_without_a_redirect(client):
    """Un Mount dejaba /mcp redirigiendo a /mcp/ con 307, que algunos clientes no siguen en POST."""
    response = client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={"Authorization": f"Bearer {TOKEN}"}, follow_redirects=False)

    assert response.status_code != 307


def _compose_service(name: str) -> str:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.db.yml").read_text(encoding="utf-8")
    return compose.split(f"\n  {name}:\n", 1)[1].split("\n\n  ", 1)[0]


def test_the_vps_runs_the_mcp_server_on_the_private_network_only():
    """The provider reaches it as http://mcp-server:8790/mcp; nothing outside the host can."""
    service = _compose_service("mcp-server")

    assert '"services.mcp_server.server"' in service
    assert "image: ppc-manager-mcp:" in service      # its own image: the app's has no mcp package
    assert "ports:" not in service
    assert "networks: [web]" in service
    assert "mcp-server:8790" in DEFAULT_ALLOWED_HOSTS


def test_the_mcp_server_reads_with_the_apps_web_role_never_the_workers():
    service = _compose_service("mcp-server")

    assert "MCP_JWT: ${SUPABASE_KEY" in service
    assert "WORKER_JWT" not in service and "PGRST_JWT_SECRET" not in service
    assert "MCP_TOKEN: ${MCP_TOKEN" in service


def test_the_mcp_server_is_checked_on_its_own_port_not_on_streamlits():
    service = _compose_service("mcp-server")

    assert "8790/health" in service and "8501" not in service

