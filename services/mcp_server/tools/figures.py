"""The figures every Amazon Ads tool hands the chat: a row's metrics, a whole's, each part's share of it, and where
they come from."""
from __future__ import annotations

from datetime import date
from typing import Literal

from core.amazon_ads import campaign_totals
from core.amazon_ads.product_provider import PRODUCT_TYPES, NewToBrand, ProductCampaigns, ProductProvider
from services.mcp_server.tools.metric_filters import aov, ctr

SHARED_METRICS = ("spend", "sales", "orders", "clicks")
# Cómo cuenta cada producto sus ventas: sin esto, el modelo compara ACoS de SB con los de SP como si fueran iguales.
ATTRIBUTION_NOTE = ("Las ventas y órdenes de cada producto son las de Campaign Manager: SP después de un click; SB y SD "
                    "después de un click o una vista, a 14 días. sales_clicks y orders_clicks son sólo las de "
                    "después de un click: lo comparable entre productos.")
SERIES_SOURCE = "Sponsored Products, Brands y Display, de los reportes de campaña. " + ATTRIBUTION_NOTE
SEARCH_TERMS_SOURCE = ("Sólo Sponsored Products, sumado del reporte de search terms: sólo trae términos con clicks, así "
                       "que tiene muchas menos impresiones que los reportes de campaña; gasto, clicks, ventas y órdenes "
                       "quedan casi iguales.")
# Las cifras de SP salen de dos fuentes que no coinciden en impresiones: cada respuesta dice cómo pedir la otra,
# para que el chat las ofrezca como dos datos y no presente una en lugar de la otra.
SOURCE_CAMPAIGNS = "campaigns"
SOURCE_SEARCH_TERMS = "search_terms"
SOURCES = (SOURCE_CAMPAIGNS, SOURCE_SEARCH_TERMS)
SEARCH_TERMS_ALTERNATIVE = ("Las cifras de Sponsored Products también salen sumadas del reporte de search terms, con "
                            "source=search_terms: sólo traen términos con clicks, así que tienen muchas menos impresiones. "
                            "Son las que coinciden con el Search Term Report.")
CAMPAIGNS_ALTERNATIVE = ("Con source=campaigns salen de los reportes de campaña: suman Sponsored Brands y Display, y en "
                         "Sponsored Products traen todas las impresiones, también las de términos sin clicks.")
NEW_TO_BRAND_NOTE = ("ntb_orders y ntb_sales son las órdenes y ventas de clientes nuevos para la marca, como las cuentan "
                     "Sponsored Brands y Display, y ntb_sales_share su parte de las ventas (%). Vacías no son cero: "
                     "algún día del período no las midió.")
Product = Literal["", "SP", "SB", "SD"]
# "" = la fuente de siempre de cada herramienta: los reportes de campaña, salvo tipo de match y search term.
Source = Literal["", "campaigns", "search_terms"]
# How many days each product counts a sale after its ad; SP's depend on the account type.
SPONSORED_BRANDS_DISPLAY_ATTRIBUTION_DAYS = 14


def _with_shares(rows: list[dict], totals: dict) -> list[dict]:
    """Each group's percent of the whole's spend, sales, orders and clicks: «most of» reads off a number."""
    for row in rows:
        for metric in SHARED_METRICS:
            whole = totals.get(metric) or 0
            row[f"{metric}_share"] = round(row[metric] / whole * 100, 1) if whole else None
    return rows


def _check_product(product: str) -> None:
    if product and product not in PRODUCT_TYPES:
        raise ValueError(f"product tiene que ser uno de: {', '.join(PRODUCT_TYPES)}, o vacío para los tres")


def _check_source(source: str, product: str = "") -> None:
    if source and source not in SOURCES:
        raise ValueError(f"source tiene que ser uno de: {', '.join(SOURCES)}, o vacío para la fuente de siempre")
    if source == SOURCE_SEARCH_TERMS and product not in ("", "SP"):
        raise ValueError("Los search terms sólo son de Sponsored Products: pedilo sin product o con product=SP.")


def _source_fields(source: str, *, alternative: bool) -> dict:
    """Where the figures come from and, when SP's also exist in the other source, how to ask for those."""
    fields = {"data_source": source,
              "source": SERIES_SOURCE if source == SOURCE_CAMPAIGNS else SEARCH_TERMS_SOURCE}
    if alternative:
        fields["alternative"] = SEARCH_TERMS_ALTERNATIVE if source == SOURCE_CAMPAIGNS else CAMPAIGNS_ALTERNATIVE
    return fields


def _days_metrics(days) -> dict:
    return _metrics(sum(day.spend for day in days), sum(day.sales for day in days), sum(day.orders for day in days),
                    sum(day.clicks for day in days), sum(day.impressions for day in days))


def _totals_metrics(totals: campaign_totals.Totals) -> dict:
    return {**_metrics(totals.spend, totals.sales, totals.orders, totals.clicks, totals.impressions),
            "sales_clicks": round(float(totals.sales_clicks), 2), "orders_clicks": int(totals.orders_clicks)}


def whole_metrics(metrics: dict) -> dict:
    """A whole's metrics plus its CTR and average order value, which the rows leave out to stay short."""
    return {**metrics, "ctr": ctr(metrics.get("clicks"), metrics.get("impressions")),
            "aov": aov(metrics.get("sales"), metrics.get("orders"))}


def attribution_days_by_product(products, sponsored_products_days: int) -> dict[str, int]:
    """How many days after its ad each product present counts a sale: SP by the account type, SB and SD 14."""
    return {product: sponsored_products_days if product == "SP" else SPONSORED_BRANDS_DISPLAY_ATTRIBUTION_DAYS
            for product in products}


def new_to_brand_fields(figures: NewToBrand | None, sales) -> dict:
    """An SB or SD row's new-to-brand orders, sales and share of its sales; empty values when unmeasured."""
    if figures is None:
        return {"ntb_orders": None, "ntb_sales": None, "ntb_sales_share": None}
    return {"ntb_orders": figures.orders, "ntb_sales": round(figures.sales, 2),
            "ntb_sales_share": round(figures.sales / sales * 100, 1) if sales else None}


def _add_old_format_note(payload: dict, rest, profile_id: str, start: date, end: date, product: str, *,
                         products: ProductCampaigns | None = None) -> None:
    """Says so when SB campaigns of the old format have unknown metrics: their spend is in no total."""
    if product not in ("", "SB"):
        return
    products = products if products is not None else ProductProvider(rest).campaigns(profile_id, start, end)
    if products is None or not products.without_metrics:
        return
    count = len(products.without_metrics)
    payload["old_format_note"] = (
        ("1 campaña SB del formato anterior todavía no tiene métricas: su gasto y sus ventas no están"
         if count == 1 else
         f"{count} campañas SB del formato anterior todavía no tienen métricas: su gasto y sus ventas no están")
        + " en estos números. Aparecen cuando termina de cargarse su historia.")


def _plain_number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN: unknown, not zero
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _metrics(spend, sales, orders, clicks, impressions) -> dict:
    spend, sales, orders, clicks = float(spend), float(sales), int(orders), int(clicks)
    return {"spend": round(spend, 2), "sales": round(sales, 2), "orders": orders, "clicks": clicks,
            "impressions": int(impressions),
            "acos": round(spend / sales * 100, 1) if sales else None,
            "cvr": round(orders / clicks * 100, 2) if clicks else None,
            # Spend without a sale returns nothing: its ROAS is 0, not unknown.
            "roas": round(sales / spend, 2) if spend else None,
            "cpc": round(spend / clicks, 2) if clicks else None}


def _plain(value):
    """JSON no sabe de numpy ni de Timestamp; el cliente MCP tampoco."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
