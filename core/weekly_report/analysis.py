"""The Weekly Client Report agent's payload, built from what the page parsed and computed, so the page and the tests
build the same one."""
from __future__ import annotations

import math

from ai.agents.weekly_report.context import WeeklyData
from core.business_report.paid_split import PaidSplit
from core.weekly_report.advertising import Advertising

ANALYSIS_MODULE = "weekly_report"
UNKNOWN = "sin dato"
FILE_ADS_ORIGIN = "un Campaign CSV subido a mano: no dice qué días cubre ni con qué atribución se exportó"
FILE_COUNT_UNKNOWN = f"{UNKNOWN}: el Campaign CSV no trae la columna"
# (figure, its change's label, the daily report's key, decimals, unit)
_COMPARED = (("Ventas", "Variación de ventas (%)", "Sales", 2, ""),
             ("Unidades", "Variación de unidades (%)", "Units", 0, ""),
             ("Sesiones", "Variación de sesiones (%)", "Sessions", 0, ""),
             ("CVR", "Variación del CVR (%)", "CVR", 2, " (%)"))


def build_analysis_input(br_daily: dict, br_child: dict, br_child_pw: dict, atom: dict, *, weekly_products: bool,
                         product_days: int | None, advertising: Advertising | None, split: PaidSplit | None,
                         account: str, ads_note: str, currency_code: str, client: str, changelog: str,
                         lang: str, ads_file: str = "") -> WeeklyData:
    """`br_daily` is the page's parsed daily Business Report, `br_child_pw` counts only with `weekly_products`, and
    `ads_note` says why there is no account advertising: it is ignored when there is. With the Campaign CSV named
    `ads_file` the advertising needs no split, which then only adds the TACoS."""
    with_ads = advertising is not None and (split is not None or bool(ads_file))
    advertising_file = ads_file if with_ads else ""
    return WeeklyData(
        client=client.strip(), account=account, ads_note="" if with_ads else ads_note, currency_code=currency_code,
        figures=weekly_figures(br_daily, atom, weekly_products=weekly_products, product_days=product_days,
                               has_products=bool(br_child), advertising=advertising if with_ads else None,
                               split=split if with_ads else None, ads_file=advertising_file),
        products=_product_records(br_child, br_child_pw if weekly_products else {}, atom, weekly_products),
        campaigns=[_campaign_record(campaign) for campaign in advertising.campaigns] if with_ads else [],
        portfolios=_portfolio_records(advertising.portfolios) if with_ads else [],
        changelog=changelog.strip(), idioma=lang, ads_file=advertising_file,
    )


def weekly_figures(br_daily: dict, atom: dict, *, weekly_products: bool, product_days: int | None,
                   has_products: bool, advertising: Advertising | None, split: PaidSplit | None,
                   ads_file: str = "") -> dict:
    """The module's figures by name, as the report shows them and the agent reads them."""
    figures = {"Semana actual": _period_label(br_daily.get("period_tw")),
               "Semana anterior": _period_label(br_daily.get("period_pw")),
               "Comparación semanal por producto": _products_mode(weekly_products, product_days, has_products)}
    for name, change_label, key, decimals, unit in _COMPARED:
        this_week, prior_week = br_daily[f"{key}_TW"], br_daily[f"{key}_PW"]
        figures[f"{name}, semana actual{unit}"] = round(float(this_week), decimals)
        figures[f"{name}, semana anterior{unit}"] = round(float(prior_week), decimals)
        figures[change_label] = _percent(_change(this_week, prior_week))
    for name, key in (("semana actual", "BuyBox_TW"), ("semana anterior", "BuyBox_PW")):
        if _known(br_daily.get(key)):
            figures[f"Buy Box promedio, {name} (%)"] = round(float(br_daily[key]), 1)
    figures.update(_atom_figures(atom, br_daily["Sales_TW"]))
    if advertising is not None and (split is not None or ads_file):
        figures.update(_account_ads_figures(advertising, split, from_file=bool(ads_file)))
    return figures


def _products_mode(weekly_products: bool, product_days: int | None, has_products: bool) -> str:
    if not has_products:
        return "no: no se subió el BR by Child"
    if weekly_products:
        return "sí: un BR by Child de 7 días por semana"
    days = f" ({product_days} días)" if product_days else ""
    return f"no: las cifras por producto cubren el período completo{days}"


def _atom_figures(atom: dict, sales_this_week: float) -> dict:
    if not atom:
        return {"Ads por ASIN (Atom 11)": "no se subió el Atom 11"}
    spend_tw, spend_pw = (sum(row.get(f"Spend_{week}", 0) for row in atom.values()) for week in ("TW", "PW"))
    sales_tw, sales_pw = (sum(row.get(f"Sales_{week}", 0) for row in atom.values()) for week in ("TW", "PW"))
    return {
        "Spend de ads por ASIN (Atom 11), semana actual": _amount(spend_tw),
        "Spend de ads por ASIN (Atom 11), semana anterior": _amount(spend_pw),
        "Ventas de ads por ASIN (Atom 11), semana actual": _amount(sales_tw),
        "Ventas de ads por ASIN (Atom 11), semana anterior": _amount(sales_pw),
        "ACoS de Atom 11, semana actual (%)": _percent(spend_tw / sales_tw * 100 if sales_tw > 0 else None),
        "TACoS de Atom 11, semana actual (%)": _percent(
            spend_tw / sales_this_week * 100 if sales_this_week > 0 and spend_tw > 0 else None),
    }


def _account_ads_figures(advertising: Advertising, split: PaidSplit | None, *, from_file: bool) -> dict:
    """`split` is None only for a Campaign CSV uploaded without the daily report."""
    totals = advertising.totals
    figures = _file_source_figures(advertising, split) if from_file else _synced_source_figures(split)
    figures.update({
        "Campañas con actividad": advertising.campaign_count,
        "Impresiones": _count(totals["Impressions"]),
        "Clicks": _count(totals["Clicks"]),
        "CTR (%)": _percent(totals["CTR"]),
        "CPC": _amount(totals["CPC"]) if totals["CPC"] is not None else UNKNOWN,
        "Spend de ads de la cuenta": _amount(totals["Spend"]),
        "Ventas de ads de la cuenta": _amount(totals["Sales"]),
        "Órdenes de ads de la cuenta": _count(totals["Orders"]),
        "ACoS de la cuenta (%)": _percent(totals["ACoS"]),
        "TACoS de la cuenta (%)": _percent(split.tacos if split is not None else None),
    })
    new_to_brand = advertising.new_to_brand
    if new_to_brand is None:
        figures["New-to-brand de Sponsored Brands y Display"] = UNKNOWN
    else:
        figures.update({"Órdenes new-to-brand (SB y SD)": new_to_brand.orders,
                        "Ventas new-to-brand (SB y SD)": _amount(new_to_brand.sales),
                        "Parte new-to-brand de las órdenes de SB y SD (%)": _percent(advertising.new_to_brand_share)})
    figures["Vistas de la página de detalle"] = (f"{UNKNOWN}: no se leen del Campaign CSV" if from_file
                                                 else f"{UNKNOWN}: no se sincronizan")
    if split is not None and split.ads_exceed_br:
        figures["Aviso del módulo"] = ("las ventas de ads del Campaign CSV superan a las de todo el BR diario"
                                       if from_file else
                                       "las ventas de ads superan a las del Business Report en los mismos días")
    return figures


def _synced_source_figures(split: PaidSplit) -> dict:
    return {
        "Publicidad de la cuenta, días": (f"del {split.start.isoformat()} al {split.end.isoformat()}: "
                                          f"{split.covered_days} de {split.history_days} días del BR"),
        "Productos con actividad": ", ".join(split.products) or "ninguno",
        "Atribución de Sponsored Products (días)": split.attribution_days,
    }


def _file_source_figures(advertising: Advertising, split: PaidSplit | None) -> dict:
    compared = (f", así que se compara con los {split.history_days} días del BR diario, del "
                f"{split.start.isoformat()} al {split.end.isoformat()}" if split is not None else "")
    # Without campaigns with activity no product had any, whether or not the file names the types.
    products = ", ".join(advertising.products) or ("ninguno" if not advertising.campaign_count else UNKNOWN)
    return {"Publicidad de la cuenta, origen": FILE_ADS_ORIGIN + compared, "Productos con actividad": products}


def _product_records(br_child: dict, br_child_pw: dict, atom: dict, weekly_products: bool) -> list[dict]:
    records = []
    for asin, row in sorted(br_child.items(), key=lambda item: (-item[1]["Sales"], item[0])):
        record = {"asin": asin, "producto": row.get("Title", ""), "ventas": _amount(row["Sales"]),
                  "unidades": int(row["Units"]), "sesiones": int(row["Sessions"]),
                  "cvr": round(row["CVR"], 2) if _known(row.get("CVR")) else None,
                  "buybox": round(row["BuyBox"], 1) if _known(row.get("BuyBox")) else None}
        if weekly_products:
            prior = br_child_pw.get(asin)
            record.update(ventas_anterior=_amount(prior["Sales"]) if prior else None,
                          unidades_anterior=int(prior["Units"]) if prior else None,
                          sesiones_anterior=int(prior["Sessions"]) if prior else None)
        if atom:
            ads = atom.get(asin)
            record.update(spend_ads=_amount(ads["Spend_TW"]) if ads else None,
                          ventas_ads=_amount(ads["Sales_TW"]) if ads else None)
        records.append(record)
    return records


def _campaign_record(campaign: dict) -> dict:
    return {"campana": campaign["Campaign"], "producto": campaign["Product"], "impresiones": campaign["Impressions"],
            "clicks": campaign["Clicks"], "ctr": campaign["CTR"], "spend": campaign["Spend"],
            "ventas": campaign["Sales"], "acos": campaign["ACoS"], "ordenes": campaign["Orders"]}


def _portfolio_records(portfolios: list[dict] | None) -> list[dict] | None:
    if portfolios is None:
        return None
    return [{"portfolio": portfolio["Portfolio"], "spend": portfolio["Spend"], "ventas": portfolio["Sales"],
             "acos": portfolio["ACoS"]} for portfolio in portfolios]


def _period_label(period: dict | None) -> str:
    if not period:
        return "sin días"
    return f"del {period['start']} al {period['end']} ({period['days']} días)"


def _known(value) -> bool:
    return value is not None and not math.isnan(float(value))


def _change(this_week, prior_week) -> float | None:
    if not _known(this_week) or not _known(prior_week) or not prior_week:
        return None
    return (float(this_week) - float(prior_week)) / float(prior_week) * 100


def _count(value: float | None) -> int | str:
    """None only for a count the Campaign CSV lacks."""
    return FILE_COUNT_UNKNOWN if value is None else int(value)


def _amount(value: float) -> float:
    return round(float(value), 2)


def _percent(value: float | None):
    return round(value, 1) if value is not None else UNKNOWN
