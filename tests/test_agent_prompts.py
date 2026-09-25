"""Contract of the shared reading rules across the AI agents' prompts.

The <lectura> block (how a synthesis must read for a junior AM) is copied
verbatim into every agent prompt because the runtime only appends
_shared/chat.md. This test keeps the three copies identical so the rule
cannot drift silently in one agent, and pins the SQP situation spec that
used to force seven rollup figures into three sentences.
"""
import re
from pathlib import Path

import pytest

_AGENTS = Path("ai/agents")
_SLUGS = ["str", "sqp", "datadive", "bulk_campaigns", "ppc_insights", "funnel", "sbh", "ppc_forecast"]


def _block(slug: str) -> str:
    text = (_AGENTS / slug / "prompt.md").read_text(encoding="utf-8")
    found = re.findall(r"<lectura>\n(.*?)\n</lectura>", text, flags=re.S)
    assert len(found) == 1, f"{slug}: expected exactly one <lectura> block"
    return found[0]


def test_reading_rules_identical_across_agents():
    blocks = {slug: _block(slug) for slug in _SLUGS}
    assert len(set(blocks.values())) == 1


@pytest.mark.parametrize("slug", _SLUGS)
def test_reading_rules_cover_the_known_jargon(slug):
    block = _block(slug)
    for term in ("shares ponderados", "etapa dominante de fuga", "cobertura",
                 "materialidad", "rollup"):
        assert term in block
    assert "sin cifras" in block and "Slack" in block


def test_every_agent_chat_narrows_an_answer_that_came_only_counted_instead_of_asking_the_am():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "**Si una herramienta te devuelve sólo cuántos son, el recorte lo elegís vos.**" in rules
    assert "siempre dentro de la cuenta y el período que ya están en juego" in rules


def test_a_paged_answer_is_still_listed_not_narrowed():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "Si la respuesta trajo filas, aunque avise que hay más, esta regla no aplica" in rules


def test_the_chat_quantifies_only_what_it_read_whole():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "vale únicamente sobre filas que trajiste enteras con ese mismo filtro" in rules
    assert "De las filas que una página no trajo sabés cuántas son, no cómo son." in rules
    assert "Una lista se nombra por el filtro que la armó" in rules
    assert "Esa conclusión vale sobre todos los niches de la organización" in rules
    assert "en qué niches está un cliente se sabe sólo de los niches que abriste" in rules
    assert "Dice cuántos, no cuáles" in rules
    assert "SB y SD no lo traen: de ellas no se sabe si tocaron su presupuesto." in rules


def test_the_chat_gives_each_count_its_denominator_and_counts_rows_not_a_synthesis():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "Y va con su denominador y su filtro, para que se pueda comprobar" in rules
    assert "Un «sólo» o un «el único» sin el total del que sale no se escribe." in rules
    assert "Vale también para el número de una pregunta o un ofrecimiento del cierre" in rules
    assert "va con esas filas nombradas al lado cuando son pocas, y se cuenta sobre esa lista" in rules
    assert "nunca de contarlas a ojo" in rules
    assert "nunca en el texto de una síntesis ni en la situación que trae `list_analyses`" in rules
    assert "traé sus filas y contalas: vale el número de las filas" in rules
    assert "la tabla trae esa cifra en cada fila" in rules
    assert "Una fila que cumple el criterio y dejás afuera por otra razón se nombra igual" in rules
    assert "«El resto», «los demás» o «fuera de X» es el total menos esa parte" in rules


def test_the_chat_writes_its_headline_from_the_rows_it_shows():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "se escriben con la lista o la tabla ya armada, y dicen sólo lo que cumplen todas sus filas" in rules
    assert "cambia el titular, no la fila" in rules


def test_the_chat_dates_the_start_of_a_series_only_with_the_days_before_it():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "sobre una serie necesita los días de antes, o los de después" in rules
    assert "decí «en los días que miré» y no afirmes cuándo empezó" in rules


def test_the_chat_names_the_attribution_window_of_each_ad_product():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "La atribución no es una sola" in rules
    assert "`attribution_days` de cada respuesta (7 días en una cuenta de seller)" in rules
    assert "las de Brands y Display, de 14 días, también después de una vista" in rules


def test_the_chat_reads_the_top_of_search_share_as_impressions_not_sales():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "Dice dónde se mostró, no dónde vende" in rules


def test_the_chat_answers_every_part_of_a_question():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "cada una lleva su respuesta en el mismo mensaje" in rules
    assert "una respuesta que cubre sólo la parte que tenés a mano deja la otra sin contestar" in rules


def test_the_chat_crosses_asins_and_the_account_products_before_naming_them():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "Un término que es un ASIN se pauta como product target" in rules
    assert "`asin=\"…\"` es el target exact y `asin-expanded-from=\"…\"` el expandido" in rules
    assert "Los productos de una cuenta" in rules and "salen de sus product ads" in rules
    assert "se pregunta de a uno, con `entity`=product_ads y `target`=el ASIN" in rules
    assert "no sólo los que venden en ads" in rules
    assert "de cada ASIN de la lista decí en qué niche lo encontraste" in rules


def test_the_chat_looks_for_a_whole_client_in_every_niche_its_searches_bring():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "buscá por cada tipo de producto que anuncia y también por las palabras de sus campañas" in rules
    assert "Abrí todos los niches que devuelva cada búsqueda" in rules
    assert "va dentro de la primera oración, la que contesta, y en esa misma frase dice sobre qué niches vale" in rules
    assert "Nunca va primero la conclusión y su alcance en otra oración." in rules
    assert "aunque hayas abierto todos los niches que trajeron tus búsquedas" in rules


def test_a_general_question_is_answered_over_every_account_and_a_particular_one_over_its_account():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "cada pregunta es general o particular" in rules
    assert "Se contesta sobre todas sus cuentas, sin preguntar cuál" in rules
    assert "Cerrá ofreciendo abrir en detalle la cuenta que más pesa, con su razón" in rules
    assert "las que más pesan, hasta cinco: la lista entera es para cuando el AM abre esa cuenta" in rules
    assert "nunca por el nombre de una herramienta" in rules
    assert "Si la pantalla o la conversación la traen" in rules and "sin preguntar" in rules
    assert "Nunca nombres cuentas sin decir por qué esas" in rules


def test_the_chat_answers_for_each_campaign_a_name_matches():
    """#23 named two «PHRASE - Vitamin A Discovery» campaigns and the answer took one without naming the other."""
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "nombralas y contestá por cada una: `by_campaign` en `daily_metrics`" in rules
    assert "Nunca elijas en silencio una de las campañas que coinciden." in rules


def test_every_agent_chat_proposes_an_account_with_its_reason():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "**Una cuenta propuesta va con su razón.**" in rules
    assert "nunca una lista de cuentas sin criterio" in rules
    assert "dos o tres de las que viste" not in rules


def test_the_chat_does_not_date_a_change_from_the_structure_listing():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "Tampoco dice desde cuándo" in rules
    assert "Sin eso, decí que no se sabe desde cuándo." in rules


def test_the_chat_drafts_a_reply_even_when_it_cannot_see_what_the_reply_is_about():
    rules = (_AGENTS / "orchestrator" / "prompt.md").read_text(encoding="utf-8")

    assert "Un pedido de redactar" in rules
    assert "el borrador va igual, con lo que falta entre corchetes" in rules
    assert "Los corchetes van sólo dentro de un borrador" in rules


def test_every_agent_chat_checks_its_answer_against_the_tools_before_writing_it():
    rules = (_AGENTS / "_shared" / "chat.md").read_text(encoding="utf-8")

    assert "repasala contra lo que devolvieron las herramientas" in rules
    assert "copiados de su fila y su columna, no de memoria" in rules
    assert "comprobados contra las filas que los sostienen" in rules
    assert "una sola que la contradiga la vuelve falsa" in rules
    assert "recorriendo una por una todas las filas candidatas" in rules
    assert "Lo que no pase el repaso se saca o se dice con su alcance." in rules


def test_sqp_situation_spec_no_longer_enumerates_the_rollup():
    text = (_AGENTS / "sqp" / "prompt.md").read_text(encoding="utf-8")
    spec = next(line for line in text.splitlines()
                if line.startswith("- situation:"))
    assert "ancladas en los shares ponderados" not in spec
    assert "sin cifras" in spec and "exposición" in spec
    exec_spec = next(line for line in text.splitlines()
                     if line.startswith("- executive_summary:"))
    assert "no aplica a la situación" in exec_spec
