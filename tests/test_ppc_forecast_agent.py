"""The PPC Forecast agent's contract: its documents, its answer's shape, its fingerprint and its text for the chat."""
from datetime import date, timedelta

import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.ppc_forecast.chat_document import reading_text
from ai.agents.ppc_forecast.context import MAX_HISTORY_DAYS, OUTPUT_SCHEMA, TOPICS, build_context
from core.amazon_ads.campaign_totals import ProductDay, ProductSeries, Totals
from core.ppc_forecast.analysis import ANALYSIS_MODULE, build_analysis_input
from core.ppc_forecast.paid_split import paid_split
from core.ppc_forecast.projection import forecast_sales

FIRST, LAST = date(2026, 8, 3), date(2026, 8, 30)


def _history(first=FIRST, last=LAST, *, units=True, sessions=True) -> pd.DataFrame:
    days = pd.date_range(first, last, freq="D")
    sales = [60.0 if day.dayofweek >= 5 else 100.0 for day in days]
    return pd.DataFrame({"_date": days, "_sales": sales,
                         "_units": [s // 10 for s in sales] if units else float("nan"),
                         "_sess": [s * 2 for s in sales] if sessions else float("nan")})


def _ads(first=FIRST, last=LAST, spend=10.0, sales=40.0) -> ProductSeries:
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return ProductSeries(days=tuple(ProductDay(day, Totals(spend, sales, 1, 5, 100, sales, 1)) for day in days),
                         campaigns=(), products=("SP", "SB"), currency_code="USD", attribution_days=7)


def _payload(history=None, *, ads=None, growth=10, horizon=14, note="no se eligió la cuenta de Amazon Ads del BR"):
    history = _history() if history is None else history
    split = paid_split(history, ads) if ads is not None else None
    return build_analysis_input(history, forecast_sales(history, horizon, growth), split=split, ads=ads,
                                account="Luna Kids · US" if ads is not None else "", ads_note=note,
                                currency_code="USD" if ads is not None else "", lang="es")


def _documents(payload) -> dict:
    _, docs, _ = build_context(payload)
    return {doc["title"].split(" (")[0]: doc["content"] for doc in docs}


def test_without_an_account_the_parameters_say_why_and_the_history_has_no_ads_columns():
    documents = _documents(_payload())

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: ninguna" in params
    assert "Datos de ads: ninguno: no se eligió la cuenta de Amazon Ads del BR" in params
    assert "Moneda: la del Business Report, que el módulo no conoce" in params
    assert "- Ventas proyectadas en el horizonte: 1240" in params
    assert "- Ventas con el crecimiento objetivo: 1364" in params
    assert "- Ventas de un sábado o domingo sobre las de un día hábil: 0.6" in params
    assert "Spend de ads" not in params and "Spend estimado" not in params
    assert documents["Historia diaria"].splitlines()[0] == "fecha,dia,ventas,unidades,sesiones"
    assert documents["Historia diaria"].splitlines()[1] == "2026-08-03,lun,100.0,10,200"
    assert documents["Proyección diaria"].splitlines()[:2] == ["fecha,dia,ventas_proyectadas", "2026-08-31,lun,100.0"]


def test_with_an_account_the_parameters_carry_the_split_and_the_spend_estimate():
    documents = _documents(_payload(ads=_ads(last=date(2026, 8, 20))))

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: Luna Kids · US" in params
    assert "Datos de ads: los de la cuenta de arriba" in params
    assert "Moneda: USD" in params
    assert "- Días con datos de ads: 18 de 28, del 2026-08-03 al 2026-08-20" in params
    assert "- Productos con actividad: SP, SB" in params
    assert "- Spend de ads: 180" in params and "- Ventas de ads: 720" in params
    # 14 weekdays at 100 and 4 weekend days at 60 fall inside the covered days.
    assert "- Ventas del Business Report en esos días: 1640" in params
    assert "- ACoS (%): 25" in params
    assert "- TACoS (%): 11" in params
    assert "- Ventas orgánicas estimadas: 920" in params
    assert "- Spend estimado para el objetivo: 149.71" in params
    history = documents["Historia diaria"].splitlines()
    assert history[0] == "fecha,dia,ventas,unidades,sesiones,spend_ads,ventas_ads"
    assert history[1] == "2026-08-03,lun,100.0,10,200,10.0,40.0"
    assert history[-1] == "2026-08-30,dom,60.0,6,120,,"


def test_ads_above_the_report_reach_the_agent_as_the_module_warning():
    params = _documents(_payload(ads=_ads(sales=500.0)))["Parámetros"]

    assert "- Aviso del módulo: las ventas de ads superan a las del Business Report en los mismos días" in params


def test_columns_the_report_does_not_carry_are_left_out_instead_of_sent_as_zero():
    history = _history(units=False, sessions=False)

    documents = _documents(_payload(history))

    assert documents["Historia diaria"].splitlines()[0] == "fecha,dia,ventas"


def test_a_long_history_sends_its_most_recent_days_and_says_how_many_stayed_out():
    history = _history(FIRST - timedelta(days=200), LAST)

    _, docs, _ = build_context(_payload(history))

    assert docs[1]["title"] == f"Historia diaria ({MAX_HISTORY_DAYS} filas)"
    assert docs[1]["content"].splitlines()[-1].startswith("2026-08-30")
    assert "De 228 días del Business Report viajaron los 180 más recientes; los 48 anteriores no existen para vos." \
        in docs[0]["content"]


def test_the_fingerprint_changes_with_what_the_agent_reads_and_only_with_that():
    same = build_agent_call(ANALYSIS_MODULE, _payload()).input_digest

    assert build_agent_call(ANALYSIS_MODULE, _payload()).input_digest == same
    assert build_agent_call(ANALYSIS_MODULE, _payload(growth=20)).input_digest != same
    assert build_agent_call(ANALYSIS_MODULE, _payload(ads=_ads())).input_digest != same


def test_the_answer_reads_one_figure_per_topic_before_the_synthesis():
    reading = OUTPUT_SCHEMA["properties"]["lecturas"]["items"]

    assert OUTPUT_SCHEMA["required"] == ["lecturas", "synthesis"]
    assert reading["properties"]["tema"]["enum"] == list(TOPICS)
    assert list(reading["properties"]) == ["tema", "razon", "confianza", "advertencia"]
    assert OUTPUT_SCHEMA["properties"]["synthesis"]["required"] == ["situation", "week_actions", "mid_term", "risks",
                                                                    "executive_summary"]


def test_the_chat_text_carries_the_synthesis_and_the_confidence_in_each_figure():
    answer = {"synthesis": {"situation": "Las ventas suben 2 por día.", "week_actions": ["Subir el budget 10%"],
                            "mid_term": [], "risks": [], "executive_summary": "1.240 en 14 días."},
              "lecturas": [{"tema": "PROYECCION", "razon": "28 días parejos.", "confianza": "alta",
                            "advertencia": None},
                           {"tema": "PRESUPUESTO", "razon": "TACoS de 11%.", "confianza": "media",
                            "advertencia": "El TACoS puede subir."},
                           {"tema": "OTRA", "razon": "no existe", "confianza": "baja", "advertencia": None}]}

    text = reading_text(answer)

    assert text.startswith("Situación: Las ventas suben 2 por día.")
    assert "Proyección de ventas → alta: 28 días parejos." in text
    assert "Spend estimado para el objetivo → media: TACoS de 11%. · advertencia: El TACoS puede subir." in text
    assert "no existe" not in text
