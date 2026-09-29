"""A Campaign CSV exported from Campaign Manager and uploaded by hand, read into the totals the synced reads give.

One row per campaign with activity, in the columns of `campaign_totals.window_totals`, whatever the campaign's state: a
campaign paused later still spent in the export's range. The file does not say which days it covers, whose account it
is or which attribution it used; it says its currency only through a currency column, or when every amount starts with
the same unambiguous symbol. A Bulk File, or a file in two currencies, is refused: its rows cannot be summed.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.campaign_totals import NEW_TO_BRAND_COLUMNS, NEW_TO_BRAND_PRODUCTS, PRODUCTS, Totals
from core.amazon_ads.export_amounts import clean_money, known_money
from core.amazon_ads.product_provider import PRODUCT_CODES
from core.bulk.parser import SHEET_CAMPAIGNS
from core.currency_format import CURRENCY_SYMBOLS
from core.search_term.frame import valid_currency_code

log = logging.getLogger(__name__)

CAMPAIGN_COLUMNS = ["product", "campaign_id", "campaign", "portfolio", *Totals.__dataclass_fields__,
                    *NEW_TO_BRAND_COLUMNS]
ACTIVITY_COLUMNS = ["impressions", "clicks", "spend", "sales", "orders"]
EXPORT_HINT = "Campaign Manager → Campaigns → Export, con el mismo rango de fechas"
UNREADABLE_MESSAGE = ("No se pudo leer «{name}». Subí el Campaign CSV (.csv o .xlsx) tal como lo exporta "
                      f"{EXPORT_HINT}.")
BULK_FILE_MESSAGE = ("«{name}» es un Bulk File: repite las métricas en cada nivel (campaña, grupo, keyword), así que "
                     f"sumarlo las contaría dos veces. Subí el Campaign CSV: {EXPORT_HINT}.")
MISSING_COLUMNS_MESSAGE = ("A «{name}» le falta {missing}. Subí el Campaign CSV tal como lo exporta "
                           f"{EXPORT_HINT}.")
MIXED_CURRENCIES_MESSAGE = ("«{name}» trae montos en más de una moneda, así que sumarlos no daría un total. Subí el "
                            f"Campaign CSV de un solo marketplace tal como lo exporta {EXPORT_HINT}.")

# Exact names, compared without case: the 2026 export first, then older ones. A substring would take "New-to-brand
# sales" or "Sales (clicks)" for the sales.
_HEADERS = {
    "campaign": ("campaign name", "campaign", "campaigns"),
    "campaign_id": ("campaign id",),
    "product": ("type", "campaign type"),
    "portfolio": ("portfolio name", "portfolio"),
    "impressions": ("impressions",),
    "clicks": ("clicks",),
    "spend": ("total cost", "spend", "cost"),
    "sales": ("sales", "total sales"),
    "orders": ("purchases", "orders"),
    "sales_clicks": ("sales (clicks)",),
    "orders_clicks": ("purchases (clicks)", "orders (clicks)"),
    "ntb_orders": ("new-to-brand purchases", "new-to-brand orders", "ntb purchases", "ntb orders"),
    "ntb_sales": ("new-to-brand sales", "ntb sales"),
    "currency": ("currency", "budget currency", "currency code"),
}
_REQUIRED = {"campaign": "el nombre de la campaña (Campaign name)", "spend": "el gasto (Total cost o Spend)",
             "sales": "las ventas (Sales)"}
_COUNTS = ("impressions", "clicks", "orders")
# An SB- or SD-only Bulk download has no Sponsored Products sheet; any campaigns sheet makes it a Bulk File.
_BULK_CAMPAIGN_SHEETS = {SHEET_CAMPAIGNS, "Sponsored Brands Campaigns", "Sponsored Display Campaigns",
                         "SB Multi Ad Group Campaigns"}
_PRODUCT_BY_TYPE = {**{name.casefold(): code for name, code in PRODUCT_CODES.items()},
                    **{code.casefold(): code for code in PRODUCTS}}
# A bare "$" is the dollar of several marketplaces: it names no currency.
_CURRENCY_BY_SYMBOL = {symbol: code for code, symbol in CURRENCY_SYMBOLS.items() if symbol != "$"}
_LEADING_SYMBOL = re.compile(r"\s*-?\s*([^\d.,\-\s]*)")


class CampaignFileError(ValueError):
    """The upload is not a Campaign CSV that can be summed; the message is shown to the user."""


@dataclass(frozen=True, eq=False)
class CampaignFile:
    """One Campaign CSV: its campaigns with activity, and what else the file says about them."""

    name: str
    digest: str               # the first 16 hex digits of the bytes' sha256: a new file is new data
    campaigns: pd.DataFrame   # CAMPAIGN_COLUMNS, one row per campaign with activity
    currency_code: str        # "" unless the file says it
    has_portfolio: bool
    has_product: bool         # the file carries the campaign type, so SP, SB and SD are told apart
    has_new_to_brand: bool    # and its new-to-brand columns, set on the SB and SD rows
    missing_counts: tuple[str, ...] = ()  # impressions, clicks or orders the file lacks: 0 in `campaigns`

    @property
    def ad_spend(self) -> float:
        return float(self.campaigns["spend"].sum())

    @property
    def ad_sales(self) -> float:
        return float(self.campaigns["sales"].sum())

    @property
    def products(self) -> tuple[str, ...]:
        return tuple(code for code in PRODUCTS if code in set(self.campaigns["product"]))

    @property
    def campaign_count(self) -> int:
        return len(self.campaigns)


def read_campaign_file(file_bytes: bytes, file_name: str) -> CampaignFile:
    """The .csv or the .xlsx (its first sheet) Campaign Manager exports; raises CampaignFileError when it is not one."""
    table = _read_table(file_bytes, file_name)
    sources = _header_sources(table.columns)
    missing = [label for field, label in _REQUIRED.items() if field not in sources]
    if missing:
        raise CampaignFileError(MISSING_COLUMNS_MESSAGE.format(name=file_name, missing=" ni ".join(missing)))
    cells = {field: table[source].fillna("").astype(str).str.strip() for field, source in sources.items()}
    has_product = "product" in cells
    has_new_to_brand = has_product and all(column in cells for column in NEW_TO_BRAND_COLUMNS)
    return CampaignFile(
        name=file_name,
        digest=hashlib.sha256(file_bytes).hexdigest()[:16],
        campaigns=_campaign_totals(cells, index=table.index),
        currency_code=_file_currency(cells, file_name),
        has_portfolio="portfolio" in cells,
        has_product=has_product,
        has_new_to_brand=has_new_to_brand,
        missing_counts=tuple(field for field in _COUNTS if field not in cells),
    )


def _read_table(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    buffer = io.BytesIO(file_bytes)
    try:
        if file_name.lower().endswith(".xlsx"):
            workbook = pd.ExcelFile(buffer)
            is_bulk = not _BULK_CAMPAIGN_SHEETS.isdisjoint(workbook.sheet_names)
            table = None if is_bulk else pd.read_excel(workbook, sheet_name=0, dtype=str)
        else:
            is_bulk = False
            table = pd.read_csv(buffer, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    # An encrypted .xlsx or a renamed .xls is an OLE2 file, which pandas hands to xlrd: not installed, ImportError.
    except (ValueError, zipfile.BadZipFile, OSError, KeyError, ImportError) as exc:
        log.warning("Campaign file %r could not be read: %s: %s", file_name, type(exc).__name__, exc)
        raise CampaignFileError(UNREADABLE_MESSAGE.format(name=file_name)) from exc
    # A Bulk sheet saved on its own keeps its Entity column, which the Campaign Manager export does not have.
    if is_bulk or "entity" in {_header_key(header) for header in table.columns}:
        raise CampaignFileError(BULK_FILE_MESSAGE.format(name=file_name))
    return table


def _header_key(header) -> str:
    return str(header).replace("\N{ZERO WIDTH NO-BREAK SPACE}", "").strip().casefold()


def _header_sources(headers) -> dict[str, object]:
    by_name: dict[str, object] = {}
    for header in headers:
        by_name.setdefault(_header_key(header), header)
    sources = {}
    for field, names in _HEADERS.items():
        source = next((by_name[name] for name in names if name in by_name), None)
        if source is not None:
            sources[field] = source
    return sources


def _campaign_totals(cells: dict[str, pd.Series], *, index: pd.Index) -> pd.DataFrame:
    blank = pd.Series("", index=index, dtype=object)
    product = cells["product"].str.casefold().map(_PRODUCT_BY_TYPE).fillna("") if "product" in cells else blank
    campaign_id = cells.get("campaign_id", blank)
    rows = pd.DataFrame({"product": product, "campaign_id": campaign_id, "campaign": cells["campaign"],
                         "portfolio": cells.get("portfolio", blank)})
    for field in ACTIVITY_COLUMNS:
        rows[field] = clean_money(cells[field]) if field in cells else 0.0
    sponsored_products = rows["product"].eq("SP")
    for field, total in (("sales_clicks", "sales"), ("orders_clicks", "orders")):
        # Sponsored Products counts a sale only after a click; the other products say it in their own column.
        known = known_money(cells[field]) if field in cells else float("nan")
        rows[field] = rows[total].where(sponsored_products, known)
    brand_rows = rows["product"].isin(NEW_TO_BRAND_PRODUCTS)
    for field in NEW_TO_BRAND_COLUMNS:
        rows[field] = known_money(cells[field]).where(brand_rows) if field in cells else float("nan")

    named, with_id = rows["campaign"].ne(""), rows["campaign_id"].ne("")
    # Without a name or an id a row is no campaign: a totals row would count everything twice.
    rows = rows[named | with_id].assign(campaign=rows["campaign"].where(named, "Campaña " + rows["campaign_id"]))
    # Excel re-saves a 15-digit id as "1.23457E+14", which several campaigns can share: only whole digits name one.
    whole_id = rows["campaign_id"].str.fullmatch(r"\d+")
    rows = rows.assign(_key=rows["campaign_id"].where(whole_id, rows["product"] + "\N{NULL}" + rows["campaign"]))
    grouped = rows.groupby("_key", sort=True)
    campaigns = grouped[["product", "campaign_id", "campaign", "portfolio"]].first()
    campaigns = campaigns.join(grouped[ACTIVITY_COLUMNS].sum())
    campaigns = campaigns.join(grouped[["sales_clicks", "orders_clicks", *NEW_TO_BRAND_COLUMNS]]
                               .agg(_sum_when_all_known))
    for field in _COUNTS:
        campaigns[field] = campaigns[field].round().astype(int)
    active = campaigns[campaigns[ACTIVITY_COLUMNS].ne(0).any(axis=1)]
    return active[CAMPAIGN_COLUMNS].reset_index(drop=True)


def _sum_when_all_known(values: pd.Series) -> float:
    return float(values.sum()) if values.notna().all() else float("nan")


def _file_currency(cells: dict[str, pd.Series], file_name: str) -> str:
    codes = set(cells["currency"].map(valid_currency_code)) - {""} if "currency" in cells else set()
    symbols = {_LEADING_SYMBOL.match(cell).group(1) for field in ("spend", "sales") for cell in cells[field]
               if any(character.isdigit() for character in cell)}
    # A bare number next to "$" names no second currency; "MX$" next to "$" does.
    if len(codes) > 1 or (not codes and len(symbols - {""}) > 1):
        raise CampaignFileError(MIXED_CURRENCIES_MESSAGE.format(name=file_name))
    if codes:
        return codes.pop()
    return _CURRENCY_BY_SYMBOL.get(symbols.pop(), "") if len(symbols) == 1 else ""
