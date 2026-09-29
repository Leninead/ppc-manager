"""The Account Pulse agent's payload, built from what the page computed, so the page and the tests build the same one."""
from __future__ import annotations

import math
from datetime import date, timedelta

from ai.agents.account_pulse.context import PulseData
from core.account_pulse.ads_by_week import AdWeeks
from core.account_pulse.buybox import buybox_alerts
from core.account_pulse.day_types import day_type
from core.amazon_ads.campaign_totals import ProductSeries
from core.business_report.paid_split import PaidSplit

ANALYSIS_MODULE = "account_pulse"
UNKNOWN = "sin dato"
FILE_ADS_ORIGIN = ("un Campaign CSV subido a mano: un total por campaña, sin detalle por día, así que no hay ACoS ni "
                   "TACoS de cada semana; no dice qué días cubre, así que se compara con todos los días del Business "
                   "Report")
_WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
# (figure, its change's label, the parser's key, decimals, unit)
_COMPARED = (("Ventas", "Variación de ventas (%)", "Sales", 2, ""),
             ("Unidades", "Variación de unidades (%)", "Units", 0, ""),
             ("Sesiones", "Variación de sesiones (%)", "Sessions", 0, ""),
             ("CVR", "Variación del CVR (%)", "CVR", 2, " (%)"))


def build_analysis_input(daily_data: dict, br_child: dict | None, *, weeks: AdWeeks | None, split: PaidSplit | None,
                         series: ProductSeries | None, campaigns: list[dict], account: str, ads_note: str,
                         currency_code: str, target_acos: float, lang: str, ads_file: str = "") -> PulseData:
    """`daily_data` is the page's parsed daily Business Report; `br_child` is None when no BR by Child was uploaded.
    With a Campaign CSV (`ads_file`) the split is the file's, against every day of the report, with no weeks nor
    `series`. `ads_note` says why there are no ads figures, and is ignored when there are."""
    from_file = split is not None and split.from_file
    with_account_ads = weeks is not None and series is not None
    with_ads = with_account_ads or from_file
    return PulseData(
        account=account, ads_note="" if with_ads else ads_note, currency_code=currency_code,
        figures=pulse_figures(daily_data, weeks if with_account_ads else None, split if with_ads else None,
                              target_acos, has_active_campaigns=bool(campaigns)),
        days=_day_records(daily_data["daily"], series if with_account_ads else None),
        buybox=[_buybox_record(alert) for alert in buybox_alerts(br_child)] if br_child is not None else None,
        campaigns=[_campaign_record(row) for row in campaigns] if with_ads else [],
        idioma=lang,
        ads_file=ads_file if from_file else "",
    )


def pulse_figures(daily_data: dict, weeks: AdWeeks | None, split: PaidSplit | None, target_acos: float, *,
                  has_active_campaigns: bool = True) -> dict:
    """The module's figures by name, as the page shows them and the agent reads them. A Campaign CSV's `split` comes
    with no `weeks`: one set of ads figures for the file's whole period, where `has_active_campaigns` tells a file
    whose campaigns all stood still from one that does not say SP, SB or SD."""
    agg, days = daily_data["agg"], [row["date"] for row in daily_data["daily"]]
    this_week_start = daily_data["this_week_start"]
    figures = {
        "Días del Business Report": len(set(days)),
        "Semana actual": _week_label([day for day in days if day >= this_week_start]),
        "Semana anterior": _week_label([day for day in days if day < this_week_start]),
    }
    for name, change_label, key, decimals, unit in _COMPARED:
        this_week, prior_week = agg[f"{key}_TW"], agg[f"{key}_PW"]
        figures[f"{name}, semana actual{unit}"] = round(float(this_week), decimals)
        figures[f"{name}, semana anterior{unit}"] = round(float(prior_week), decimals)
        figures[change_label] = _percent(_change(this_week, prior_week))
    if _known(agg.get("BuyBox_TW")):
        figures["Buy Box promedio, semana actual (%)"] = agg["BuyBox_TW"]
        prior_buybox = agg.get("BuyBox_PW")
        figures["Buy Box promedio, semana anterior (%)"] = prior_buybox if _known(prior_buybox) else UNKNOWN
    figures["Target ACoS (%)"] = target_acos
    if split is not None and split.from_file:
        figures.update(_file_ads_figures(split, has_active_campaigns=has_active_campaigns))
        return figures
    if weeks is None or split is None:
        return figures
    figures["Productos con actividad"] = ", ".join(split.products) or "ninguno"
    figures["Atribución de Sponsored Products (días)"] = split.attribution_days
    for name, week in (("semana actual", weeks.this_week), ("semana anterior", weeks.prior_week)):
        figures.update(_week_ads(name, week))
    for label, measure in (("ACoS", "acos"), ("TACoS", "tacos")):
        this_week, prior_week = (getattr(week, measure) if week is not None else None
                                 for week in (weeks.this_week, weeks.prior_week))
        figures[f"Variación del {label} (%)"] = _percent(_change(this_week, prior_week))
    if split.ads_exceed_br:
        figures["Aviso del módulo"] = "las ventas de ads superan a las del Business Report en los mismos días"
    return figures


def _file_ads_figures(split: PaidSplit, *, has_active_campaigns: bool) -> dict:
    figures = {
        "Origen de los datos de ads": FILE_ADS_ORIGIN,
        "Productos con actividad": ", ".join(split.products) or (UNKNOWN if has_active_campaigns else "ninguno"),
        "Spend de ads": _amount(split.ad_spend),
        "Ventas de ads": _amount(split.ad_sales),
        "Ventas de todo el Business Report": _amount(split.br_sales),
        "ACoS (%)": _percent(split.acos),
        "TACoS (%)": _percent(split.tacos),
    }
    if split.ads_exceed_br:
        figures["Aviso del módulo"] = "las ventas de ads del Campaign CSV superan a las de todo el Business Report"
    return figures


def _week_ads(name: str, week: PaidSplit | None) -> dict:
    if week is None:
        return {f"Días con datos de ads, {name}": "0: la sincronización de campañas no cubre esos días"}
    return {
        f"Días con datos de ads, {name}": f"{week.covered_days} de {week.history_days}",
        f"Spend de ads, {name}": _amount(week.ad_spend),
        f"Ventas de ads, {name}": _amount(week.ad_sales),
        f"ACoS, {name} (%)": _percent(week.acos),
        f"TACoS, {name} (%)": _percent(week.tacos),
    }


def _week_label(days: list[date]) -> str:
    if not days:
        return "sin días"
    first, last = min(days), max(days)
    count = len(set(days))
    calendar_days = (last - first + timedelta(days=1)).days
    gaps = f", faltan {calendar_days - count} días del rango" if calendar_days > count else ""
    return f"del {first.isoformat()} al {last.isoformat()} ({count} días{gaps})"


def _day_records(daily: list[dict], series: ProductSeries | None) -> list[dict]:
    ad_days = {day.day: day.totals for day in series.days} if series is not None else {}
    records = []
    for row in daily:
        kind, holiday = day_type(row["date"])
        record = {"fecha": row["date"].isoformat(), "dia": _WEEKDAYS[row["date"].weekday()],
                  "tipo": f"festivo ({holiday})" if holiday else "fin de semana" if kind == "Finde" else "laboral",
                  "ventas": _amount(row["sales"]), "unidades": int(row["units"]), "sesiones": int(row["sessions"])}
        if series is not None:
            totals = ad_days.get(row["date"])
            record["spend_ads"] = _amount(totals.spend) if totals is not None else None
            record["ventas_ads"] = _amount(totals.sales) if totals is not None else None
        records.append(record)
    return records


def _buybox_record(alert: dict) -> dict:
    return {"asin": alert["asin"], "titulo": alert["title"], "ventas": _amount(alert["sales"]),
            "sesiones": int(alert["sessions"]), "buybox": round(float(alert["buybox"]), 1),
            "ventas_perdidas_est": _amount(alert["lost_sales"])}


def _campaign_record(row: dict) -> dict:
    return {"campana": row["Campaign"], "producto": row["Product"], "tipo": row["Age"],
            "impresiones": row["Impressions"], "clicks": row["Clicks"], "spend": row["Spend"], "ventas": row["Sales"],
            "acos": row["ACoS"], "ordenes": row["Orders"]}


def _known(value) -> bool:
    return value is not None and not math.isnan(float(value))


def _change(this_week, prior_week) -> float | None:
    if not _known(this_week) or not _known(prior_week) or not prior_week:
        return None
    return (float(this_week) - float(prior_week)) / float(prior_week) * 100


def _amount(value: float) -> float:
    return round(float(value), 2)


def _percent(value: float | None):
    return round(value, 1) if value is not None else UNKNOWN
