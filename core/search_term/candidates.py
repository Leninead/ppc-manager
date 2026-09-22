"""The Search Term Report's rules: its columns, the negative and harvest candidates and the AM's parameters.

M2, the analysis worker and the MCP server read them from here, so nothing here may import Streamlit or an agent.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.search_term.negatives import NegativeCandidate

# Rule 2 reference CVR when the data has no orders to measure one (INV-3 wants the product CVR; there is none).
REFERENCE_CVR_PERCENT = 10.0
DEFAULT_PRODUCT_PRICE = 30.0
DEFAULT_TARGET_ACOS = 30
DEFAULT_HARVEST_MIN_CLICKS = 15
ALREADY_EXACT_COLUMN = "Ya en Exact"
ALREADY_EXACT_VALUE = "Ya en Exact activo"

HARVEST_COLUMNS = ["Search Term", "Campaign", "Ad Group", "Clicks", "Orders", "ACoS", "CVR%", "Bid Sugerido",
                   "Regla", "Prioridad"]
_HARVEST_SORT = {"Alta": 0, "Media": 1}
_METRIC_COLUMNS = (("_spend", "spend"), ("_sales", "sales"), ("_orders", "orders"), ("_clicks", "clicks"),
                   ("_imps", "impressions"), ("_acos", "acos"), ("_ctr", "ctr"))


@dataclass(frozen=True)
class StrAnalysisParams:
    """The parameters an AM chooses for an account.

    Prices are None until someone types them; the analysis then runs without Rule 3 or suggested bids.
    """

    target_acos: int
    price: float | None
    harvest_target_acos: int
    harvest_price: float | None
    harvest_min_clicks: int
    brand_terms: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def defaults(cls, currency_code: str) -> StrAnalysisParams:
        # 30 means nothing in pesos or yen, so only dollar accounts start with a price.
        price = DEFAULT_PRODUCT_PRICE if uses_dollar_price(currency_code) else None
        return cls(DEFAULT_TARGET_ACOS, price, DEFAULT_TARGET_ACOS, price, DEFAULT_HARVEST_MIN_CLICKS, ())

    @classmethod
    def from_dict(cls, values: dict, currency_code: str) -> StrAnalysisParams:
        base = cls.defaults(currency_code)
        return cls(
            target_acos=int(values.get("target_acos", base.target_acos)),
            price=_optional_price(values.get("price", base.price)),
            harvest_target_acos=int(values.get("harvest_target_acos", base.harvest_target_acos)),
            harvest_price=_optional_price(values.get("harvest_price", base.harvest_price)),
            harvest_min_clicks=int(values.get("harvest_min_clicks", base.harvest_min_clicks)),
            brand_terms=normalized_brand_terms(values.get("brand_terms") or ()),
        )

    def as_dict(self) -> dict:
        return {"target_acos": self.target_acos, "price": self.price, "harvest_target_acos": self.harvest_target_acos,
                "harvest_price": self.harvest_price, "harvest_min_clicks": self.harvest_min_clicks,
                "brand_terms": list(self.brand_terms)}

    @property
    def digest(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def uses_dollar_price(currency_code: str) -> bool:
    return (currency_code or "").strip().upper() in ("", "USD")


def normalized_brand_terms(terms) -> tuple[str, ...]:
    """Lowercase, unique and sorted: the same brand terms typed in another order are the same parameters."""
    if isinstance(terms, str):
        terms = terms.split(",")
    return tuple(sorted({str(term).strip().lower() for term in terms if str(term).strip()}))


def detect_columns(frame: pd.DataFrame) -> dict:
    """Canonical key -> actual STR column name, matched by keywords in the header."""
    def find(keywords, exclude=None):
        for column in frame.columns:
            lowered = column.lower()
            if all(keyword in lowered for keyword in keywords):
                if exclude and any(word in lowered for word in exclude):
                    continue
                return column
        return None

    return {
        "search_term": find(["customer search term"]) or find(["search term"]) or find(["query"]),
        "spend":       find(["spend"]),
        "sales":       find(["sales"], exclude=["other", "advertised"]),
        "orders":      find(["order"], exclude=["other"]) or find(["purchases"]),
        "clicks":      find(["clicks"]) or find(["click"]),
        "impressions": find(["impressions"]) or find(["impression"]),
        "acos":        find(["acos"]),
        "ctr":         find(["ctr"]) or find(["click-through"]),
        "cvr":         find(["conversion"]) or find(["cvr"]),
        "campaign":    find(["campaign name"]) or find(["campaign"]),
        "ad_group":    find(["ad group"]),
        "match_type":  find(["match type"]) or find(["targeting type"]),
        "portfolio":   find(["portfolio name"]) or find(["portfolio"]),
    }


def numeric_column(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column and column in frame.columns:
        values = frame[column]
        if pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values):
            return values.fillna(0)
        cleaned = values.astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", "")
        return pd.to_numeric(cleaned, errors="coerce").fillna(0)
    return pd.Series(0, index=frame.index)


def add_metric_columns(frame: pd.DataFrame, cols: dict) -> None:
    """Adds the _spend/_sales/_orders/_clicks/_imps/_acos/_ctr numbers every M2 rule reads."""
    for hidden, key in _METRIC_COLUMNS:
        frame[hidden] = numeric_column(frame, cols[key])


def rule_two_cvr(total_clicks, total_orders) -> tuple[float, bool]:
    """(CVR % for the Rule 2 threshold, whether it is the reference value because nothing converted)."""
    if total_clicks > 0 and total_orders > 0:
        return total_orders / total_clicks * 100, False
    return REFERENCE_CVR_PERCENT, True


def measured_cvr(total_clicks, total_orders) -> float:
    return total_orders / total_clicks * 100 if total_clicks > 0 else 0.0


def clicks_threshold_for(total_clicks, total_orders) -> int:
    cvr, _ = rule_two_cvr(total_clicks, total_orders)
    return max(10, round((1 / (cvr / 100)) * 2))


def negative_candidate_rows(candidates: list[NegativeCandidate]) -> list[dict]:
    """Tab 2 table rows: display columns only, so the AI records never carry hidden ids."""
    return [{
        "Search Term": candidate.search_term,
        "Campaign": candidate.campaign,
        "Ad Group": candidate.ad_group,
        "Clicks": candidate.clicks,
        "Impressions": candidate.impressions,
        "Spend": candidate.spend,
        "Orders": candidate.orders,
        "ACoS": candidate.acos if candidate.acos is not None else 0,
        "Regla": candidate.rule,
        "Acción": candidate.action,
        "Match Type": candidate.match_type,
        "Prioridad": candidate.priority,
    } for candidate in candidates]


def harvest_candidate_rows(frame: pd.DataFrame, cols: dict, *, min_clicks, price, target_acos) -> pd.DataFrame:
    """Tab 3 rows in frame order: terms with clicks and orders that meet a harvest rule (SOP Capybaras 2026).

    Without a price there is no suggested bid; the column stays empty instead of pricing in the wrong currency.
    A price that is present gives the INV-1 bid (see suggested_bid).
    """
    converting = frame[(frame["_orders"] != 0) & (frame["_clicks"] != 0)]
    clicks, orders = converting["_clicks"], converting["_orders"]
    spend, sales = converting["_spend"], converting["_sales"]
    cvr = orders / clicks * 100
    acos = (spend / sales.where(sales > 0) * 100).fillna(999)
    main_rule = (orders >= 3) & (acos <= 25.0)
    high_cvr = (cvr >= 10.0) & (clicks >= min_clicks) & (orders >= 1)
    volume = orders >= 5
    matched = main_rule | high_cvr | volume
    if not matched.any():
        return pd.DataFrame(columns=HARVEST_COLUMNS)

    harvested = converting[matched]
    rules = [" + ".join(name for name, hit in (("Regla principal", main), ("CVR alto", cvr_hit), ("Volumen", vol)) if hit)
             for main, cvr_hit, vol in zip(main_rule[matched], high_cvr[matched], volume[matched])]
    harvested_cvr = cvr[matched].tolist()
    return pd.DataFrame({
        "Search Term": harvested[cols["search_term"]].astype(str).str.strip().tolist(),
        "Campaign": stripped_texts(harvested, cols["campaign"]),
        "Ad Group": stripped_texts(harvested, cols["ad_group"]),
        "Clicks": clicks[matched].astype(int).tolist(),
        "Orders": orders[matched].astype(int).tolist(),
        "ACoS": [round(value, 1) for value in acos[matched].tolist()],
        "CVR%": [round(value, 1) for value in harvested_cvr],
        "Bid Sugerido": [None if price is None else suggested_bid(value, price, target_acos) for value in harvested_cvr],
        "Regla": rules,
        "Prioridad": ["Alta" if main or cvr_hit else "Media"
                      for main, cvr_hit in zip(main_rule[matched], high_cvr[matched])],
    }, columns=HARVEST_COLUMNS)


def suggested_bid(cvr_percent: float, price: float, target_acos: float) -> float:
    """INV-1: the CVR counts up to 100%, the floor is Amazon's 0.10 and the bid never passes price × target ACoS.

    The ceiling wins over the floor: a product whose ceiling is under 0.10 cannot bid profitably at any price.
    """
    # Cents of the ceiling; the round() absorbs float error such as 16.4 * 30 = 491.99999999999994.
    ceiling = math.floor(round(price * target_acos, 6)) / 100
    bid = max(0.10, round(min(cvr_percent, 100.0) / 100 * price * (target_acos / 100), 2))
    return min(bid, ceiling)


def stripped_texts(frame: pd.DataFrame, column: str | None) -> list[str]:
    if not column or column not in frame.columns:
        return [""] * len(frame)
    return [str(value).strip() if pd.notna(value) else "" for value in frame[column]]


def campaign_states(frame: pd.DataFrame, columns: dict) -> dict:
    """(search term, campaign, ad group) -> the current state of its campaign, as the Amazon Ads report carries it."""
    keys = zip(stripped_texts(frame, columns["search_term"]), stripped_texts(frame, columns["campaign"]),
               stripped_texts(frame, columns["ad_group"]))
    return dict(zip(keys, stripped_texts(frame, "_campaign_status")))


def sorted_harvest(harvest: pd.DataFrame) -> pd.DataFrame:
    """Priority first, then orders; stable so equal rows keep the frame order."""
    if harvest.empty:
        return harvest
    order = harvest["Prioridad"].map(_HARVEST_SORT)
    return harvest.assign(_sort=order).sort_values(["_sort", "Orders"], ascending=[True, False],
                                                   kind="mergesort").drop(columns=["_sort"])


def mark_already_exact(harvest: pd.DataFrame, existing_exact_terms) -> pd.DataFrame:
    marked = harvest.copy()
    already = marked["Search Term"].str.lower().str.strip().isin(set(existing_exact_terms or ()))
    marked[ALREADY_EXACT_COLUMN] = np.where(already, ALREADY_EXACT_VALUE, "")
    return marked


def _optional_price(value) -> float | None:
    if value is None or value == "":
        return None
    price = float(value)
    return price if price > 0 else None
