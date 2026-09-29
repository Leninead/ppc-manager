"""The Weekly Client Report agent's contract: its documents, its answer's shape, its fingerprint and its texts."""
from datetime import date, timedelta

import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.weekly_report.chat_document import client_message, reading_text
from ai.agents.weekly_report.context import MAX_PRODUCTS, OUTPUT_SCHEMA, TOPICS, VERDICTS, build_context
from core.amazon_ads.campaign_totals import ProductDay, ProductSeries, Totals
from core.business_report.paid_split import paid_split
from core.weekly_report.advertising import advertising_summary
from core.weekly_report.analysis import ANALYSIS_MODULE, build_analysis_input

# Monday 3 to Sunday 16 August 2026: the prior week sells 400 a day and this one 500.
FIRST, LAST = date(2026, 8, 3), date(2026, 8, 16)
DAYS = [FIRST + timedelta(days=offset) for offset in range(14)]
BR_DAILY = {"Sales_TW": 3500.0, "Sales_PW": 2800.0, "Units_TW": 35, "Units_PW": 30, "Sessions_TW": 175,
            "Sessions_PW": 150, "CVR_TW": 20.0, "CVR_PW": 20.0, "BuyBox_TW": 97.5, "BuyBox_PW": 98.0,
            "period_tw": {"start": "2026-08-10", "end": "2026-08-16", "days": 7},
            "period_pw": {"start": "2026-08-03", "end": "2026-08-09", "days": 7},
            "daily_sales": {day.isoformat(): 500.0 if day >= date(2026, 8, 10) else 400.0 for day in DAYS}}
BR_CHILD = {"B0TEST0001": {"Title": "Producto Uno", "Sales": 1500.0, "Units": 15.0, "Sessions": 75.0, "CVR": 20.0,
                           "BuyBox": 96.67},
            "B0TEST0002": {"Title": "Producto Dos", "Sales": 2000.0, "Units": 20.0, "Sessions": 100.0, "CVR": 20.0,
                           "BuyBox": 100.0}}
BR_CHILD_PW = {"B0TEST0001": {"Title": "Producto Uno", "Sales": 750.0, "Units": 8.0, "Sessions": 40.0, "CVR": 20.0,
                              "BuyBox": 100.0}}
ATOM = {"B0TEST0002": {"Spend_TW": 100.0, "Spend_PW": 80.0, "Sales_TW": 400.0, "Sales_PW": 300.0}}
NAN = float("nan")
CAMPAIGNS = pd.DataFrame(
    [("SP", "1", "Brand exact", "Brand", 120.0, 600.0, 12, 40, 900, 600.0, 12, NAN, NAN),
     ("SD", "4", "Retargeting", "", 40.0, 50.0, 4, 10, 2000, 25.0, 2, 2, 30.0)],
    columns=["product", "campaign_id", "campaign", "portfolio", "spend", "sales", "orders", "clicks", "impressions",
             "sales_clicks", "orders_clicks", "ntb_orders", "ntb_sales"])
NO_ACCOUNT = "no se eligió la cuenta de Amazon Ads del BR"


def _history() -> pd.DataFrame:
    daily = BR_DAILY["daily_sales"]
    return pd.DataFrame({"_date": pd.to_datetime(list(daily)), "_sales": list(daily.values())})


def _series(sales: float = 40.0) -> ProductSeries:
    return ProductSeries(days=tuple(ProductDay(day, Totals(10.0, sales, 1, 5, 100, sales, 1)) for day in DAYS),
                         campaigns=(), products=("SP", "SD"), currency_code="USD", attribution_days=7)


def _payload(*, ads=False, weekly=False, atom=None, client="Luna Kids MX", changelog="", ad_sales=40.0,
             products=BR_CHILD):
    series = _series(ad_sales) if ads else None
    return build_analysis_input(
        BR_DAILY, products, BR_CHILD_PW, atom or {}, weekly_products=weekly, product_days=7 if weekly else 14,
        advertising=advertising_summary(CAMPAIGNS) if ads else None,
        split=paid_split(_history(), series) if ads else None, account="Luna Kids · US" if ads else "",
        ads_note=NO_ACCOUNT, currency_code="USD" if ads else "", client=client, changelog=changelog, lang="es")


def _documents(payload) -> dict:
    _, docs, _ = build_context(payload)
    return {doc["title"].split(" (")[0]: doc["content"] for doc in docs}


def test_without_the_account_the_parameters_say_why_and_only_the_products_travel():
    documents = _documents(_payload())

    params = documents["Parámetros"]
    assert "Cliente: Luna Kids MX" in params
    assert f"Publicidad de la cuenta: ninguna: {NO_ACCOUNT}" in params
    assert "- Semana actual: del 2026-08-10 al 2026-08-16 (7 días)" in params
    assert "- Comparación semanal por producto: no: las cifras por producto cubren el período completo (14 días)" in params
    assert "- Ventas, semana actual: 3500" in params and "- Variación de ventas (%): 25" in params
    assert "- Buy Box promedio, semana anterior (%): 98" in params
    assert "- Ads por ASIN (Atom 11): no se subió el Atom 11" in params
    assert set(documents) == {"Parámetros", "Productos"}
    products = documents["Productos"].splitlines()
    assert products[0] == "asin,producto,ventas,unidades,sesiones,cvr,buybox"
    assert products[1] == "B0TEST0002,Producto Dos,2000.0,20,100,20.0,100.0"


def test_the_weekly_product_mode_and_atom_11_add_their_columns_and_figures():
    documents = _documents(_payload(weekly=True, atom=ATOM))

    params = documents["Parámetros"]
    assert "- Comparación semanal por producto: sí: un BR by Child de 7 días por semana" in params
    assert "- Spend de ads por ASIN (Atom 11), semana actual: 100" in params
    assert "- ACoS de Atom 11, semana actual (%): 25" in params
    # 100 of Atom 11 spend over the 3,500 the account sold this week.
    assert "- TACoS de Atom 11, semana actual (%): 2.9" in params
    products = documents["Productos"].splitlines()
    assert products[0] == ("asin,producto,ventas,unidades,sesiones,cvr,buybox,ventas_anterior,unidades_anterior,"
                           "sesiones_anterior,spend_ads,ventas_ads")
    assert products[1] == "B0TEST0002,Producto Dos,2000.0,20,100,20.0,100.0,,,,100.0,400.0"
    assert products[2] == "B0TEST0001,Producto Uno,1500.0,15,75,20.0,96.7,750.0,8.0,40.0,,"


def test_with_the_account_the_advertising_travels_with_its_source_days_and_new_to_brand():
    documents = _documents(_payload(ads=True))

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: Luna Kids · US" in params
    assert "Publicidad de la cuenta: la de la cuenta de arriba" in params
    assert "- Publicidad de la cuenta, días: del 2026-08-03 al 2026-08-16: 14 de 14 días del BR" in params
    assert "- Productos con actividad: SP, SD" in params
    # 160 of spend over 650 of ad sales across both campaigns.
    assert "- ACoS de la cuenta (%): 24.6" in params
    # 140 of spend over the 6,300 the report sold those days.
    assert "- TACoS de la cuenta (%): 2.2" in params
    assert "- Órdenes new-to-brand (SB y SD): 2" in params
    assert "- Parte new-to-brand de las órdenes de SB y SD (%): 50" in params
    assert "- Vistas de la página de detalle: sin dato: no se sincronizan" in params
    assert documents["Campañas de más spend"].splitlines()[:2] == [
        "campana,producto,impresiones,clicks,ctr,spend,ventas,acos,ordenes",
        "Brand exact,SP,900,40,4.44,120.0,600.0,20.0,12"]
    assert documents["Portfolios"].splitlines()[1:] == ["Brand,120.0,600.0,20.0", "(Sin Portfolio),40.0,50.0,80.0"]


def test_ads_above_the_report_reach_the_agent_as_the_module_warning():
    params = _documents(_payload(ads=True, ad_sales=1000.0))["Parámetros"]

    assert "- Aviso del módulo: las ventas de ads superan a las del Business Report en los mismos días" in params


def test_the_changelog_travels_only_when_the_am_wrote_it():
    documents = _documents(_payload(changelog="- Pausamos 3 campañas con ACoS sobre 100%"))

    assert documents["Cambios de la semana, escritos por el AM"] == "- Pausamos 3 campañas con ACoS sobre 100%"
    assert "Cambios de la semana, escritos por el AM" not in _documents(_payload())


def test_a_long_product_list_sends_the_best_sellers_and_says_how_many_stayed_out():
    products = {f"B0TEST{index:04d}": dict(BR_CHILD["B0TEST0001"], Sales=float(index))
                for index in range(MAX_PRODUCTS + 3)}

    params = _documents(_payload(products=products))["Parámetros"]

    assert (f"De {MAX_PRODUCTS + 3} productos del BR by Child viajaron {MAX_PRODUCTS}, los de más ventas; el resto (3) "
            "no existe para vos.") in params


def test_the_fingerprint_changes_with_what_the_agent_reads_and_only_with_that():
    same = build_agent_call(ANALYSIS_MODULE, _payload()).input_digest

    assert build_agent_call(ANALYSIS_MODULE, _payload()).input_digest == same
    assert build_agent_call(ANALYSIS_MODULE, _payload(client="Otro")).input_digest != same
    assert build_agent_call(ANALYSIS_MODULE, _payload(changelog="- Nuevas rules")).input_digest != same
    assert build_agent_call(ANALYSIS_MODULE, _payload(ads=True)).input_digest != same


def test_the_answer_reads_each_topic_then_the_synthesis_then_the_client_summary():
    reading = OUTPUT_SCHEMA["properties"]["lecturas"]["items"]
    summary = OUTPUT_SCHEMA["properties"]["resumen_cliente"]

    assert OUTPUT_SCHEMA["required"] == ["lecturas", "synthesis", "resumen_cliente"]
    assert reading["properties"]["tema"]["enum"] == list(TOPICS)
    assert reading["properties"]["veredicto"]["enum"] == list(VERDICTS)
    assert summary["required"] == ["situacion", "highlights", "atencion", "proximos_pasos"]


ANSWER = {"synthesis": {"situation": "Las ventas subieron 25%.", "week_actions": ["Subir el budget de Brand exact"],
                        "mid_term": [], "risks": [], "executive_summary": "3.500 esta semana."},
          "lecturas": [{"tema": "VENTAS", "razon": "3.500 contra 2.800.", "veredicto": "OK", "advertencia": None}],
          "resumen_cliente": {"situacion": "Fue una buena semana: vendimos 3.500, un 25% más.",
                              "highlights": ["Las ventas subieron 25%"], "atencion": [],
                              "proximos_pasos": ["Vamos a escalar la campaña de marca"]}}


def test_the_client_message_keeps_the_sections_it_has_in_the_reports_language():
    assert client_message(ANSWER, "Luna Kids MX", "es") == (
        "📊 RESUMEN SEMANAL — Luna Kids MX\n\n"
        "📍 SITUACIÓN GENERAL\nFue una buena semana: vendimos 3.500, un 25% más.\n\n"
        "📈 HIGHLIGHTS\n• Las ventas subieron 25%\n\n"
        "🎯 PRÓXIMOS PASOS\n• Vamos a escalar la campaña de marca")
    assert client_message(ANSWER, "", "en").startswith("📊 WEEKLY SUMMARY\n\n📍 OVERVIEW\n")


def test_the_chat_text_carries_the_synthesis_the_verdicts_and_the_client_message():
    text = reading_text(ANSWER, client="Luna Kids MX", lang="es")

    assert text.startswith("Situación: Las ventas subieron 25%.")
    assert "Ventas → OK: 3.500 contra 2.800." in text
    assert "📊 RESUMEN SEMANAL — Luna Kids MX" in text
