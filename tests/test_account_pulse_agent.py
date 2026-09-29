"""The Account Pulse agent's contract: its documents, its answer's shape, its fingerprint and its text for the chat."""
from datetime import date, timedelta

import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.account_pulse.chat_document import reading_text
from ai.agents.account_pulse.context import MAX_CAMPAIGNS, OUTPUT_SCHEMA, TOPICS, VERDICTS, build_context
from core.account_pulse.ads_by_week import ads_by_week
from core.account_pulse.analysis import ANALYSIS_MODULE, FILE_ADS_ORIGIN, build_analysis_input
from core.account_pulse.campaigns import campaign_rows
from core.amazon_ads.campaign_file import read_campaign_file
from core.amazon_ads.campaign_totals import ProductDay, ProductSeries, Totals
from core.business_report.paid_split import file_split, paid_split

# Monday 3 to Sunday 16 August 2026; 16 September would be a holiday, 15 August is a Saturday.
FIRST, LAST = date(2026, 8, 3), date(2026, 8, 16)
THIS_WEEK_START = date(2026, 8, 10)
NO_ACCOUNT = "no se eligió la cuenta de Amazon Ads del BR"


def _daily_data() -> dict:
    days = [FIRST + timedelta(days=offset) for offset in range((LAST - FIRST).days + 1)]
    rows = [{"date": day, "sales": 150.0 if day >= THIS_WEEK_START else 100.0, "units": 10, "sessions": 200}
            for day in days]
    return {"daily": rows, "this_week_start": THIS_WEEK_START,
            "agg": {"Sales_TW": 1050.0, "Sales_PW": 700.0, "Units_TW": 70, "Units_PW": 70, "Sessions_TW": 1400,
                    "Sessions_PW": 1400, "CVR_TW": 5.0, "CVR_PW": 5.0, "BuyBox_TW": 96.5, "BuyBox_PW": 98.0}}


def _ads(first=FIRST, last=LAST, sales=60.0) -> ProductSeries:
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return ProductSeries(days=tuple(ProductDay(day, Totals(10.0, sales, 1, 5, 100, sales, 1)) for day in days),
                         campaigns=(), products=("SP", "SB"), currency_code="USD", attribution_days=7)


def _history(daily_data: dict) -> pd.DataFrame:
    return pd.DataFrame({"_date": pd.to_datetime([row["date"] for row in daily_data["daily"]]),
                         "_sales": [row["sales"] for row in daily_data["daily"]]})


CAMPAIGNS = [{"Campaign": "Luna - B0TEST0001 - SP - KW - EXACT - Brand", "Product": "SP", "Age": "NUEVA",
              "Impressions": 900, "Clicks": 40, "Spend": 90.0, "Sales": 300.0, "ACoS": 30.0, "Orders": 6},
             {"Campaign": "Old auto", "Product": "SP", "Age": "HEREDADA", "Impressions": 400, "Clicks": 12,
              "Spend": 25.0, "Sales": 0.0, "ACoS": None, "Orders": 0}]
BR_CHILD = {"B0BIG00001": {"Title": "Big", "Sales": 1000.0, "Sessions": 50, "BuyBox": 90.0}}


def _payload(*, ads=None, br_child=None, campaigns=CAMPAIGNS, target_acos=30):
    daily_data = _daily_data()
    history = _history(daily_data)
    weeks = ads_by_week(history, ads, THIS_WEEK_START) if ads is not None else None
    split = paid_split(history, ads) if ads is not None else None
    return build_analysis_input(daily_data, br_child, weeks=weeks, split=split, series=ads,
                                campaigns=campaigns if ads is not None else [],
                                account="Luna Kids · US" if ads is not None else "", ads_note=NO_ACCOUNT,
                                currency_code="USD" if ads is not None else "", target_acos=target_acos, lang="es")


def _documents(payload) -> dict:
    _, docs, _ = build_context(payload)
    return {doc["title"].split(" (")[0]: doc["content"] for doc in docs}


def test_without_an_account_the_parameters_say_why_and_nothing_about_ads_travels():
    documents = _documents(_payload())

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: ninguna" in params
    assert f"Datos de ads: ninguno: {NO_ACCOUNT}" in params
    assert "BR by Child: no se subió, así que no hay Buy Box por ASIN" in params
    assert "- Semana actual: del 2026-08-10 al 2026-08-16 (7 días)" in params
    assert "- Semana anterior: del 2026-08-03 al 2026-08-09 (7 días)" in params
    assert "- Ventas, semana actual: 1050" in params and "- Variación de ventas (%): 50" in params
    assert "- Variación del CVR (%): 0" in params
    assert "- Target ACoS (%): 30" in params
    assert "ACoS" not in params.replace("Target ACoS", "")
    assert set(documents) == {"Parámetros", "Días del Business Report"}
    days = documents["Días del Business Report"].splitlines()
    assert days[0] == "fecha,dia,tipo,ventas,unidades,sesiones"
    assert days[1] == "2026-08-03,lun,laboral,100.0,10,200"
    assert days[13] == "2026-08-15,sáb,fin de semana,150.0,10,200"


def test_with_an_account_each_week_carries_its_acos_and_tacos_over_its_own_days():
    documents = _documents(_payload(ads=_ads(last=date(2026, 8, 14))))

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: Luna Kids · US" in params
    assert "Datos de ads: los de la cuenta de arriba" in params
    assert "- Productos con actividad: SP, SB" in params
    assert "- Días con datos de ads, semana actual: 5 de 7" in params
    # 50 of spend over 300 of ad sales and the report's 750 of those five days.
    assert "- ACoS, semana actual (%): 16.7" in params and "- TACoS, semana actual (%): 6.7" in params
    assert "- ACoS, semana anterior (%): 16.7" in params and "- TACoS, semana anterior (%): 10" in params
    assert "- Variación del TACoS (%): -33.3" in params
    days = documents["Días del Business Report"].splitlines()
    assert days[0] == "fecha,dia,tipo,ventas,unidades,sesiones,spend_ads,ventas_ads"
    assert days[-1] == "2026-08-16,dom,fin de semana,150.0,10,200,,"
    campaigns = documents["Campañas con actividad"].splitlines()
    assert campaigns[0] == "campana,producto,tipo,impresiones,clicks,spend,ventas,acos,ordenes"
    assert campaigns[2] == "Old auto,SP,HEREDADA,400,12,25.0,0.0,,0"


def test_the_buybox_asins_travel_only_when_the_br_by_child_was_uploaded():
    documents = _documents(_payload(br_child=BR_CHILD))

    assert "BR by Child: subido" in documents["Parámetros"]
    assert documents["ASINs con BuyBox bajo 95%"].splitlines() == [
        "asin,titulo,ventas,sesiones,buybox,ventas_perdidas_est", "B0BIG00001,Big,1000.0,50,90.0,100.0"]


def test_ads_above_the_report_reach_the_agent_as_the_module_warning():
    params = _documents(_payload(ads=_ads(sales=500.0)))["Parámetros"]

    assert "- Aviso del módulo: las ventas de ads superan a las del Business Report en los mismos días" in params


def test_a_long_campaign_list_sends_the_most_spend_and_says_how_many_stayed_out():
    campaigns = [dict(CAMPAIGNS[0], Campaign=f"Campaign {index}") for index in range(MAX_CAMPAIGNS + 5)]

    params = _documents(_payload(ads=_ads(), campaigns=campaigns))["Parámetros"]

    assert (f"De {MAX_CAMPAIGNS + 5} campañas con actividad viajaron {MAX_CAMPAIGNS}, las de más spend; el resto (5) "
            "no existe para vos.") in params


def test_the_fingerprint_changes_with_what_the_agent_reads_and_only_with_that():
    same = build_agent_call(ANALYSIS_MODULE, _payload()).input_digest

    assert build_agent_call(ANALYSIS_MODULE, _payload()).input_digest == same
    assert build_agent_call(ANALYSIS_MODULE, _payload(target_acos=25)).input_digest != same
    assert build_agent_call(ANALYSIS_MODULE, _payload(ads=_ads())).input_digest != same


def _file_payload(sales="$1,280.00", content=None):
    daily_data = _daily_data()
    content = content or ("Campaign name,Type,Impressions,Clicks,Total cost,Purchases,Sales\n"
                          f'Alpha,Sponsored Products,900,40,$300.00,12,"{sales}"\n'
                          "Beta,Sponsored Brands,500,20,$20.00,0,$0.00\n")
    campaign_file = read_campaign_file(content.encode("utf-8"), "campaigns.csv")
    return build_analysis_input(daily_data, None, weeks=None, split=file_split(_history(daily_data), campaign_file),
                                series=None,
                                campaigns=campaign_rows(campaign_file.campaigns,
                                                        unknown_counts=campaign_file.missing_counts),
                                account="", ads_note="", currency_code="", target_acos=30, lang="es",
                                ads_file="campaigns.csv")


def test_with_a_campaign_csv_the_parameters_name_the_file_and_compare_no_weeks():
    documents = _documents(_file_payload())

    params = documents["Parámetros"]
    assert "Cuenta de Amazon Ads del Business Report: ninguna: el AM subió el Campaign CSV a mano" in params
    assert ("Datos de ads: los del Campaign CSV «campaigns.csv»: un total por campaña, sin detalle por día ni por "
            "semana") in params
    assert f"- Origen de los datos de ads: {FILE_ADS_ORIGIN}" in params
    assert "- Productos con actividad: SP, SB" in params
    # 320 of spend over 1,280 of ad sales and the report's 1,750 of all its days.
    assert "- Spend de ads: 320" in params and "- Ventas de ads: 1280" in params
    assert "- Ventas de todo el Business Report: 1750" in params
    assert "- ACoS (%): 25" in params and "- TACoS (%): 18.3" in params
    assert "semana actual (%): 25" not in params and "Variación del ACoS" not in params
    assert "Días con datos de ads" not in params and "Atribución" not in params
    assert "los de la cuenta de arriba" not in params
    assert documents["Días del Business Report"].splitlines()[0] == "fecha,dia,tipo,ventas,unidades,sesiones"
    campaigns = documents["Campañas con actividad"].splitlines()
    assert campaigns[1:] == ["Alpha,SP,HEREDADA,900,40,300.0,1280.0,23.4,12", "Beta,SB,HEREDADA,500,20,20.0,0.0,,0"]


def test_the_counts_a_campaign_csv_lacks_travel_empty_not_as_zero():
    content = "Campaign name,Total cost,Sales\nAlpha,$300.00,$1200.00\n"

    documents = _documents(_file_payload(content=content))

    assert "- Productos con actividad: sin dato" in documents["Parámetros"]
    assert documents["Campañas con actividad"].splitlines()[1] == "Alpha,,HEREDADA,,,300.0,1200.0,25.0,"


def test_a_campaign_csv_where_no_campaign_had_activity_tells_the_agent_no_product_had_any():
    content = ("Campaign name,Type,Total cost,Sales\nAlpha,Sponsored Products,$0.00,$0.00\n"
               "Beta,Sponsored Brands,$0.00,$0.00\n")

    documents = _documents(_file_payload(content=content))

    assert "- Productos con actividad: ninguno" in documents["Parámetros"]
    assert documents["Campañas con actividad"] == "ninguna campaña del Campaign CSV tuvo actividad"


def test_a_campaign_csv_whose_active_campaigns_are_no_sp_sb_or_sd_leaves_the_products_unknown():
    content = "Campaign name,Type,Total cost,Sales\nAlpha,Sponsored TV,$300.00,$1200.00\n"

    params = _documents(_file_payload(content=content))["Parámetros"]

    assert "- Productos con actividad: sin dato" in params


def test_a_campaign_csv_above_the_report_reaches_the_agent_as_the_file_warning():
    params = _documents(_file_payload(sales="$9,000.00"))["Parámetros"]

    assert "- Aviso del módulo: las ventas de ads del Campaign CSV superan a las de todo el Business Report" in params


def test_the_file_payload_is_its_own_data():
    assert build_agent_call(ANALYSIS_MODULE, _file_payload()).input_digest not in {
        build_agent_call(ANALYSIS_MODULE, _payload()).input_digest,
        build_agent_call(ANALYSIS_MODULE, _payload(ads=_ads())).input_digest}


def test_the_answer_reads_one_topic_per_row_before_the_synthesis():
    reading = OUTPUT_SCHEMA["properties"]["lecturas"]["items"]

    assert OUTPUT_SCHEMA["required"] == ["lecturas", "synthesis"]
    assert reading["properties"]["tema"]["enum"] == list(TOPICS)
    assert reading["properties"]["veredicto"]["enum"] == list(VERDICTS)
    assert list(reading["properties"]) == ["tema", "razon", "veredicto", "advertencia"]
    assert OUTPUT_SCHEMA["properties"]["synthesis"]["required"] == ["situation", "week_actions", "mid_term", "risks",
                                                                    "executive_summary"]


def test_the_chat_text_carries_the_synthesis_and_the_verdict_on_each_topic():
    answer = {"synthesis": {"situation": "Las ventas subieron 50%.", "week_actions": ["Subir el budget 10%"],
                            "mid_term": [], "risks": [], "executive_summary": "1.050 esta semana."},
              "lecturas": [{"tema": "VENTAS", "razon": "1.050 contra 700.", "veredicto": "OK", "advertencia": None},
                           {"tema": "PUBLICIDAD", "razon": "TACoS de 6,7%.", "veredicto": "VIGILAR",
                            "advertencia": "Faltan 2 días de ads."},
                           {"tema": "OTRA", "razon": "no existe", "veredicto": "OK", "advertencia": None}]}

    text = reading_text(answer)

    assert text.startswith("Situación: Las ventas subieron 50%.")
    assert "Ventas → OK: 1.050 contra 700." in text
    assert "Publicidad → VIGILAR: TACoS de 6,7%. · advertencia: Faltan 2 días de ads." in text
    assert "no existe" not in text
