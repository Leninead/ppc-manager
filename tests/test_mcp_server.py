"""El servidor MCP: qué expone, qué exige y qué nunca devuelve."""
import pytest

from services.mcp_server import server
from services.mcp_server.tools import analyses, windows


class _FakeRest:
    """No se toca en estos tests: las herramientas se registran sin consultar nada."""


def _tools():
    return {tool["name"]: tool for tool in server.build_tools(_FakeRest())}


def test_the_server_exposes_the_read_tools_and_nothing_that_writes():
    names = set(_tools())

    assert names == {"list_accounts", "list_analyses", "get_analysis", "top_search_terms", "daily_metrics",
                     "breakdown", "accounts_overview", "campaign_health", "idle_targets", "campaign_structure",
                     "funnel_coverage", "search_term_candidates", "bid_suggestions", "asin_health"}
    assert not any(word in name for name in names
                   for word in ("create", "update", "delete", "request", "save", "write"))


def test_every_tool_says_what_it_does_so_the_model_can_choose():
    for name, tool in _tools().items():
        assert len(tool["description"]) > 40, f"{name} no explica qué hace"


def test_the_figure_tools_say_sponsored_products_also_comes_summed_from_the_search_terms():
    """Without it the model would only know one of the two SP figures, and read the other as an error."""
    for name in ("accounts_overview", "daily_metrics", "breakdown"):
        assert "source=search_terms" in _tools()[name]["description"], name


def test_the_index_tool_names_the_modules_it_can_serve():
    assert all(module in _tools()["get_analysis"]["description"] for module in analyses.MODULES)


def test_a_domain_tool_never_mentions_another_domain():
    """Preguntar por Amazon no puede arrastrar Mercado Libre: cada herramienta vive en su dominio."""
    ads = _tools()["top_search_terms"]["description"].lower()

    assert "amazon" in ads
    assert "mercado libre" not in ads and "meli" not in ads


def test_without_a_token_the_server_refuses_to_start(monkeypatch):
    monkeypatch.delenv(server.TOKEN_ENV, raising=False)

    with pytest.raises(server.ConfigurationError, match="no arranca sin autenticación"):
        server.required_token()


def test_an_empty_token_counts_as_no_token(monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, "   ")

    with pytest.raises(server.ConfigurationError):
        server.required_token()


def test_without_a_database_the_server_refuses_to_start(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://db")
    monkeypatch.delenv(server.JWT_ENV, raising=False)

    with pytest.raises(server.ConfigurationError, match="SUPABASE_URL o MCP_JWT"):
        server.rest_from_env()


@pytest.mark.parametrize("header", [
    None, "", "secreto", "Basic secreto", "Bearer", "Bearer otro", "bearer ",
])
def test_anything_that_is_not_the_exact_bearer_is_rejected(header):
    assert server.authorize(header, "secreto") is False


@pytest.mark.parametrize("header", [
    "Bearer secreto", "bearer secreto", "BEARER secreto",
    # Espacio de más: lo toleran casi todos los stacks HTTP y el token igual tiene que coincidir
    # exacto, así que rechazarlo sólo produciría un 401 incomprensible.
    "Bearer  secreto",
])
def test_the_right_bearer_is_accepted_whatever_the_case_of_the_scheme(header):
    assert server.authorize(header, "secreto") is True


def test_an_empty_expected_token_never_authorizes_anyone():
    assert server.authorize("Bearer ", "") is False
    assert server.authorize("Bearer algo", "") is False


def test_the_search_term_window_is_capped_so_nobody_asks_for_a_year():
    assert windows.MAX_DAYS <= 60          # la retención real de spSearchTerm en Amazon
    assert windows.DEFAULT_DAYS <= windows.MAX_DAYS


def test_the_module_list_mirrors_the_one_the_database_allows():
    """Si alguien suma un módulo en la migración y no acá, el índice lo ignora en silencio."""
    import re
    from pathlib import Path

    # La lista vigente es la de la última migración que redefine la función.
    defining = sorted(path for path in Path("deploy/db/migrations").glob("*.sql")
                      if "function ai_analysis_module_allowed" in path.read_text(encoding="utf-8"))
    latest = defining[-1].read_text(encoding="utf-8")
    allowed = re.search(r"select p_module in \(([^)]*)\)", latest).group(1)

    assert {name.strip().strip("'") for name in allowed.split(",")} == set(analyses.MODULES)


def test_without_its_secrets_the_server_idles_instead_of_exiting_into_a_restart_loop(monkeypatch, caplog):
    """Serving nothing is the safe state; exiting would crash-loop under `restart: unless-stopped`."""
    monkeypatch.delenv(server.TOKEN_ENV, raising=False)
    idled = []

    with caplog.at_level("ERROR"):
        assert server.run(idle=lambda: idled.append(True)) == 2

    assert idled == [True]
    assert "no arranca sin autenticación" in caplog.text



def test_every_new_field_and_filter_is_described_where_the_model_picks_its_calls():
    """The model chooses its calls from these descriptions: a field it is not told about is a field it never asks."""
    described = {tool["name"]: tool["description"] for tool in server.build_tools(object())}

    for name in ("get_analysis", "top_search_terms", "daily_metrics", "breakdown", "campaign_health", "idle_targets",
                 "campaign_structure", "funnel_coverage", "search_term_candidates", "bid_suggestions", "asin_health"):
        assert "account, en lugar de profile_id" in described[name], name
    for name in ("breakdown", "campaign_health", "campaign_structure"):
        assert "filters recibe cotas por métrica" in described[name] and "sort_order=asc" in described[name], name
    for name in ("breakdown", "campaign_health", "accounts_overview"):
        assert "compare=previous" in described[name] and "order_by_change" in described[name], name
    assert "granularity=week o month" in described["daily_metrics"] and "activity" in described["daily_metrics"]
    assert "by_period=week o month" in described["breakdown"] and "other_campaigns" in described["breakdown"]
    assert "attributed_by" in described["breakdown"] and "attributed_by" in described["asin_health"]
    assert "targets pregunta por una lista" in described["campaign_structure"]
    assert "bid_gap" in described["campaign_structure"] and "product=SB o SD" in described["campaign_structure"]
    assert "cost_type" in described["campaign_structure"]
    assert "where deja sólo las filas" in described["get_analysis"]
    assert "compare_previous" in described["bid_suggestions"]
    assert "spend_exceeds_sales" in described["accounts_overview"] and "ntb_orders" in described["accounts_overview"]
