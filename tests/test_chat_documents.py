"""The text the app chat reads about each module's AI answer.

Expected strings are written by hand from the agents' output contracts, never copied from the code under test.
"""
from ai.agents.datadive.chat_document import reading_text as datadive_reading
from ai.agents.sqp.chat_document import reading_text as sqp_reading
from ai.agents.synthesis_text import synthesis_text

_SYNTHESIS = {"situation": "La marca no aparece en la cabeza del niche.", "week_actions": ["Pujar K01"],
              "mid_term": [], "risks": [{"type": "COBERTURA", "detail": "cubre 40 de 393", "urgency": "MEDIA"}],
              "executive_summary": "40 queries, 3 acciones."}


def test_the_synthesis_carries_the_executive_summary_only_when_the_agent_wrote_one():
    text = synthesis_text(_SYNTHESIS)

    assert text.splitlines() == [
        "Situación: La marca no aparece en la cabeza del niche.",
        "Acciones sugeridas para la semana:", "1. Pujar K01",
        "Riesgos:", "- COBERTURA (MEDIA): cubre 40 de 393",
        "Resumen ejecutivo: 40 queries, 3 acciones."]
    assert "Resumen ejecutivo" not in synthesis_text({"situation": "s"})


def test_every_sqp_opinion_sits_next_to_the_query_of_its_row():
    records = [{"query": "luna pajamas "}, {"query": "kids pajamas"}]
    result = {"synthesis": {"situation": "s"}, "queries": [
        {"row_id": "Q02", "query_type": "GENERICA", "funnel_diagnosis": "FUGA_CTR",
         "price_causality": "INDETERMINADO", "action": "ARREGLAR_CREATIVO_SERP", "confidence": "MEDIA",
         "reasoning": "4.1% de share de clics", "warning": "muestra fina"},
        {"row_id": "Q09", "query_type": "BRANDED", "funnel_diagnosis": "DOMINANTE",
         "price_causality": "INDETERMINADO", "action": "MONITOREAR", "confidence": "ALTA",
         "reasoning": "fila que no viajó", "warning": None},
    ]}

    lines = sqp_reading(result, records).splitlines()

    assert ("Q02 · kids pajamas → GENERICA · FUGA_CTR · INDETERMINADO · ARREGLAR_CREATIVO_SERP · MEDIA: "
            "4.1% de share de clics · advertencia: muestra fina") in lines
    assert not any(line.startswith("Q09") or line.startswith("Q01") for line in lines)


def test_datadive_clusters_keep_their_attack_order_and_only_the_keywords_on_screen():
    records = [{"term": "collagen powder", "sv": 120000}, {"term": "collagen peptides", "sv": 45000},
               {"term": "marca ajena", "sv": 9000}]
    result = {"synthesis": {"situation": "s"},
              "clusters": [{"nombre": "Núcleo", "prioridad": "alta", "match_type": "exact",
                            "racional": "Cabeza del niche.", "row_ids": ["K01", "K02", "K77"]},
                           {"nombre": "Ruido", "prioridad": "baja", "match_type": "broad",
                            "racional": "Otra marca.", "row_ids": ["K03"]}],
              "gaps": [{"row_id": "K02", "via": "PPC_AHORA", "confianza": "alta", "razon": "rank 34",
                        "advertencia": None},
                       {"row_id": "K88", "via": "NO_ATACABLE", "confianza": "baja", "razon": "x",
                        "advertencia": None}]}

    lines = datadive_reading(result, records).splitlines()

    assert ("1. Núcleo · prioridad alta · exact · 2 keywords, SV 165,000: Cabeza del niche. "
            "Keywords: K01 (collagen powder), K02 (collagen peptides)") in lines
    assert lines.index("2. Ruido · prioridad baja · broad · 1 keywords, SV 9,000: Otra marca. "
                       "Keywords: K03 (marca ajena)") > lines.index(
        "1. Núcleo · prioridad alta · exact · 2 keywords, SV 165,000: Cabeza del niche. "
        "Keywords: K01 (collagen powder), K02 (collagen peptides)")
    assert "K02 · collagen peptides → PPC_AHORA · alta: rank 34" in lines
    assert not any(line.startswith("K88") for line in lines)


def test_a_datadive_answer_without_gaps_has_no_gap_section():
    text = datadive_reading({"synthesis": {"situation": "s"}, "clusters": [], "gaps": []}, [])

    assert text == "Situación: s"
