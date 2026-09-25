"""The PPC Forecast agent's payload, built from what the page computed, so the page and the tests build the same one."""
from __future__ import annotations

import pandas as pd

from ai.agents.ppc_forecast.context import ForecastData
from core.amazon_ads.campaign_totals import ProductSeries
from core.ppc_forecast.paid_split import PaidSplit, spend_for_target
from core.ppc_forecast.projection import DATE, PROJECTED_SALES, SalesForecast

ANALYSIS_MODULE = "ppc_forecast"
UNKNOWN = "sin dato"
_WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def build_analysis_input(history: pd.DataFrame, forecast: SalesForecast, *, split: PaidSplit | None,
                         ads: ProductSeries | None, account: str, ads_note: str, currency_code: str,
                         lang: str) -> ForecastData:
    """`history` is the Business Report per day (`_date`, `_sales`, `_units`, `_sess`); `ads` the series behind
    `split`. `ads_note` says why there is no split, and is ignored when there is one."""
    ads = ads if split is not None else None
    return ForecastData(account=account, ads_note="" if split is not None else ads_note,
                        currency_code=currency_code, figures=forecast_figures(history, forecast, split),
                        history=_history_records(history, ads), projection=_projection_records(forecast.projection),
                        idioma=lang)


def forecast_figures(history: pd.DataFrame, forecast: SalesForecast, split: PaidSplit | None) -> dict:
    """The module's figures by name, as the page shows them and the agent reads them."""
    ratio = forecast.trend.weekend_ratio
    figures = {
        "Días del Business Report": int(history["_date"].dt.date.nunique()),
        "Primer día": history["_date"].min().date().isoformat(),
        "Último día": history["_date"].max().date().isoformat(),
        "Ventas promedio por día": _amount(forecast.average_daily_sales),
        "Tendencia por día": _amount(forecast.trend.slope),
        "Ventas de un sábado o domingo sobre las de un día hábil": round(ratio, 2) if ratio is not None else UNKNOWN,
        "Horizonte en días": forecast.horizon,
        "Ventas proyectadas en el horizonte": _amount(forecast.projected_sales),
        "Crecimiento objetivo (%)": forecast.target_growth,
        "Ventas con el crecimiento objetivo": _amount(forecast.sales_with_growth),
    }
    if split is None:
        return figures
    needed = spend_for_target(split, forecast.sales_with_growth)
    figures.update({
        "Días con datos de ads": (f"{split.covered_days} de {split.history_days}, del {split.start.isoformat()} al "
                                  f"{split.end.isoformat()}"),
        "Productos con actividad": ", ".join(split.products) or "ninguno",
        "Atribución de Sponsored Products (días)": split.attribution_days,
        "Spend de ads": _amount(split.ad_spend),
        "Ventas de ads": _amount(split.ad_sales),
        "Ventas del Business Report en esos días": _amount(split.br_sales),
        "ACoS (%)": _percent(split.acos),
        "TACoS (%)": _percent(split.tacos),
        "Ventas orgánicas estimadas": _amount(split.organic_sales),
        "Parte de las ventas que vino de ads (%)": _percent(split.paid_share),
        "Spend estimado para el objetivo": _amount(needed) if needed is not None else UNKNOWN,
    })
    if split.ads_exceed_br:
        figures["Aviso del módulo"] = "las ventas de ads superan a las del Business Report en los mismos días"
    return figures


def _history_records(history: pd.DataFrame, ads: ProductSeries | None) -> list[dict]:
    ad_days = {day.day: day.totals for day in ads.days} if ads is not None else {}
    with_units, with_sessions = history["_units"].notna().any(), history["_sess"].notna().any()
    records = []
    for when, sales, units, sessions in zip(history["_date"], history["_sales"], history["_units"], history["_sess"]):
        record = {"fecha": when.date().isoformat(), "dia": _WEEKDAYS[when.dayofweek], "ventas": _amount(sales)}
        if with_units:
            record["unidades"] = int(units)
        if with_sessions:
            record["sesiones"] = int(sessions)
        if ads is not None:
            totals = ad_days.get(when.date())
            record["spend_ads"] = _amount(totals.spend) if totals is not None else None
            record["ventas_ads"] = _amount(totals.sales) if totals is not None else None
        records.append(record)
    return records


def _projection_records(projection: pd.DataFrame) -> list[dict]:
    return [{"fecha": day, "dia": _WEEKDAYS[pd.Timestamp(day).dayofweek], "ventas_proyectadas": sales}
            for day, sales in zip(projection[DATE], projection[PROJECTED_SALES])]


def _amount(value: float) -> float:
    return round(float(value), 2)


def _percent(value: float | None):
    return round(value, 1) if value is not None else UNKNOWN
