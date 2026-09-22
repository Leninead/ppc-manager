"""The Campaign Analyzer's rules (M6): the traffic light and the signals, without Streamlit.

The page, the analysis worker and the MCP server all classify campaigns through here, so the
screen, the stored analysis and the chat can never disagree about the same campaign. It lives in
core/amazon_ads/ because the MCP image copies this folder and not the rest of core/, and it imports
nothing from ai/ for the same reason.

The diagnosis is the one M6 always had, moved here unchanged. The signals are additive: they sit
next to the diagnosis and never change it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from core.amazon_ads.campaign_provider import (
    ACOS,
    CAMPAIGN_ID,
    CLICKS,
    IMPRESSIONS,
    PURCHASES,
    ROAS,
    SALES,
    SIGNAL_DAY_FIELDS,
    SIGNAL_SHARE_FIELD,
    STATE,
    TOTAL_COST,
)

ANALYSIS_MODULE = "bulk_campaigns"

GHOST = "👻 FANTASMA"
PAUSE = "🔴 PAUSAR"
REVIEW = "🟡 REVISAR"
SCALE = "✅ ESCALAR"
OK = "⚪ OK"
DIAGNOSES = (GHOST, PAUSE, REVIEW, SCALE, OK)
DIAGNOSIS_COLUMN = "Diagnóstico"
SIGNALS_COLUMN = "Señales"

# The defaults the M6 inputs always opened with.
DEFAULT_TARGET_ACOS = 35.0
DEFAULT_SPEND_TO_PAUSE = 20.0
DEFAULT_MIN_ORDERS_TO_SCALE = 2
REQUIRED_PERFORMANCE_COLUMNS = (STATE, TOTAL_COST, SALES, PURCHASES)

BUDGET_LIMITED = "Limitada por presupuesto"
NEW_CAMPAIGN = "Nueva"
LOW_VISIBILITY = "Baja visibilidad"
# Days of the period at or above 95% of that day's budget (the 95% lives in campaigns_between) for a
# campaign within target to count as held back by its budget.
BUDGET_CAPPED_MIN_DAYS = 3
# A campaign younger than this is still learning: its numbers are not yet its own.
NEW_CAMPAIGN_DAYS = 14
# Top-of-search impression share, in percent, under which a campaign that is not converting is also
# barely seen at the top. Initial threshold, to be validated against the accounts.
LOW_TOP_OF_SEARCH_SHARE = 10.0
# The last days of any period still gain attributed sales (7 days for sellers, 14 for vendors).
PROVISIONAL_DAYS = 2
_BUDGET_TYPE_DAILY = "DAILY"


@dataclass(frozen=True)
class CampaignAnalyzerParams:
    """What the AM sets on the screen and changes the classification."""

    target_acos: float
    spend_to_pause: float
    min_orders_to_scale: int

    @classmethod
    def defaults(cls) -> CampaignAnalyzerParams:
        return cls(DEFAULT_TARGET_ACOS, DEFAULT_SPEND_TO_PAUSE, DEFAULT_MIN_ORDERS_TO_SCALE)

    @classmethod
    def from_dict(cls, values: dict) -> CampaignAnalyzerParams:
        defaults = cls.defaults()
        return cls(
            target_acos=_number(values.get("target_acos"), float, defaults.target_acos),
            spend_to_pause=_number(values.get("spend_to_pause"), float, defaults.spend_to_pause),
            min_orders_to_scale=_number(values.get("min_orders_to_scale"), int, defaults.min_orders_to_scale),
        )

    def as_dict(self) -> dict:
        return {"target_acos": float(self.target_acos), "spend_to_pause": float(self.spend_to_pause),
                "min_orders_to_scale": int(self.min_orders_to_scale)}

    @property
    def review_acos_above(self) -> float:
        """A campaign with orders over this ACoS goes to REVISAR: twice the target."""
        return self.target_acos * 2

    @property
    def scale_acos_at_most(self) -> float:
        """A campaign with enough orders at or under this ACoS goes to ESCALAR: half the target."""
        return self.target_acos * 0.5

    @property
    def digest(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AnalyzerFrame:
    """The enabled campaigns with the numeric columns the diagnosis reads."""

    campaigns: pd.DataFrame
    has_impressions: bool
    has_acos: bool
    has_roas: bool


def missing_performance_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in REQUIRED_PERFORMANCE_COLUMNS if column not in frame.columns]


def analyzer_frame(frame: pd.DataFrame) -> AnalyzerFrame:
    """The enabled campaigns with _spend, _sales, _acos (percent), _orders, _impr and _clicks.

    Reads a Campaign CSV uploaded by hand as well as the API frame, so money may come as "$1,234.5"
    and ACOS as a fraction, as the export writes it.
    """
    has_impressions = IMPRESSIONS in frame.columns
    has_acos = ACOS in frame.columns
    has_roas = ROAS in frame.columns
    campaigns = frame.copy()
    campaigns["_spend"] = _clean_money(campaigns[TOTAL_COST])
    campaigns["_sales"] = _clean_money(campaigns[SALES])
    if has_acos:
        campaigns["_acos"] = pd.to_numeric(campaigns[ACOS], errors="coerce").fillna(0) * 100
    elif has_roas:
        roas = pd.to_numeric(campaigns[ROAS], errors="coerce").fillna(0)
        campaigns["_acos"] = (100 / roas.where(roas > 0)).fillna(0)
    else:
        campaigns["_acos"] = (campaigns["_spend"] / campaigns["_sales"].where(campaigns["_sales"] > 0)
                              * 100).fillna(0)
    campaigns["_orders"] = pd.to_numeric(campaigns[PURCHASES], errors="coerce").fillna(0)
    campaigns["_impr"] = (pd.to_numeric(campaigns[IMPRESSIONS], errors="coerce").fillna(0)
                          if has_impressions else None)
    campaigns["_clicks"] = (pd.to_numeric(campaigns[CLICKS], errors="coerce").fillna(0)
                            if CLICKS in campaigns.columns else 0)
    campaigns = campaigns[campaigns[STATE].str.upper() == "ENABLED"].copy()
    return AnalyzerFrame(campaigns, has_impressions, has_acos, has_roas)


def diagnose(row, params: CampaignAnalyzerParams, *, has_impressions: bool) -> str:
    """One enabled campaign's place in the traffic light: M6's rule, unchanged."""
    spend, acos, orders = row["_spend"], row["_acos"], row["_orders"]
    if spend == 0 and (row["_impr"] == 0 if has_impressions else row["_clicks"] == 0):
        return GHOST
    if orders == 0 and spend >= params.spend_to_pause:
        return PAUSE
    if orders > 0 and acos > params.review_acos_above:
        return REVIEW
    if orders >= params.min_orders_to_scale and acos <= params.scale_acos_at_most:
        return SCALE
    return OK


def diagnosis_rules(params: CampaignAnalyzerParams, *, has_impressions: bool) -> dict[str, str]:
    """Each diagnosis with the rule and the thresholds `diagnose` applies, in the order it checks them."""
    activity = "sin impresiones" if has_impressions else "sin clicks"
    return {
        diagnosis_name(GHOST): f"habilitada, sin gasto y {activity} en el período",
        diagnosis_name(PAUSE): f"sin órdenes y con un gasto de {params.spend_to_pause:g} o más",
        diagnosis_name(REVIEW): (f"con órdenes y un ACoS de más de {params.review_acos_above:g}% "
                                 "(el doble del target)"),
        diagnosis_name(SCALE): (f"con {params.min_orders_to_scale} órdenes o más y un ACoS de "
                                f"{params.scale_acos_at_most:g}% o menos (la mitad del target)"),
        diagnosis_name(OK): "las que no cumplen ninguna de las reglas anteriores",
    }


def with_diagnosis(analyzer: AnalyzerFrame, params: CampaignAnalyzerParams) -> pd.DataFrame:
    campaigns = analyzer.campaigns.copy()
    campaigns[DIAGNOSIS_COLUMN] = (
        campaigns.apply(diagnose, axis=1, params=params, has_impressions=analyzer.has_impressions)
        if not campaigns.empty else pd.Series(dtype=str))
    return campaigns


def analyze(frame: pd.DataFrame, signal_inputs: pd.DataFrame | None, params: CampaignAnalyzerParams, *,
            window_start: date | None, window_end: date | None) -> tuple[AnalyzerFrame, pd.DataFrame]:
    """The enabled campaigns with their diagnosis and signals: what the page, the agent and the chat read."""
    analyzer = analyzer_frame(frame)
    campaigns = with_signals(with_diagnosis(analyzer, params), signal_inputs, params,
                             window_start=window_start, window_end=window_end)
    return analyzer, campaigns


def diagnosis_name(diagnosis: str) -> str:
    """"🔴 PAUSAR" -> "PAUSAR": what an agent or a client outside the screen reads."""
    return str(diagnosis).split(" ", 1)[-1]


def with_signals(campaigns: pd.DataFrame, signal_inputs: pd.DataFrame | None, params: CampaignAnalyzerParams,
                 *, window_start: date | None, window_end: date | None) -> pd.DataFrame:
    """Adds the signal inputs and the Señales column; without inputs (a file) every campaign has none."""
    campaigns = campaigns.copy()
    if signal_inputs is None or CAMPAIGN_ID not in campaigns.columns or window_end is None:
        campaigns[SIGNALS_COLUMN] = ""
        return campaigns
    inputs = signal_inputs.rename(columns={
        "start_date": "_start_date", "budget_type": "_budget_type",
        SIGNAL_DAY_FIELDS[0]: "_budget_capped_days", SIGNAL_DAY_FIELDS[1]: "_days_with_impressions",
        SIGNAL_SHARE_FIELD: "_top_of_search_is"})
    index = campaigns.index
    campaigns = campaigns.merge(inputs, on=CAMPAIGN_ID, how="left")
    campaigns.index = index
    window_days = (window_end - window_start).days + 1 if window_start is not None else 1
    campaigns["_days_live"] = [_days_live(start, window_end) for start in campaigns["_start_date"]]
    campaigns[SIGNALS_COLUMN] = [
        " · ".join(_signals(row, params, window_days)) for _, row in campaigns.iterrows()]
    return campaigns


def provisional_days(window_start: date | None, window_end: date | None) -> list[date]:
    """The last days of the period, whose attributed sales can still grow."""
    if window_end is None:
        return []
    days = [window_end - timedelta(days=offset) for offset in range(PROVISIONAL_DAYS)]
    return sorted(day for day in days if window_start is None or day >= window_start)


def _signals(row, params: CampaignAnalyzerParams, window_days: int) -> list[str]:
    signals = []
    capped = row.get("_budget_capped_days")
    if (str(row.get("_budget_type") or "").upper() == _BUDGET_TYPE_DAILY and _known(capped)
            and capped >= min(BUDGET_CAPPED_MIN_DAYS, window_days)
            and row["_orders"] > 0 and row["_acos"] <= params.target_acos):
        signals.append(BUDGET_LIMITED)
    days_live = row.get("_days_live")
    if _known(days_live) and days_live < NEW_CAMPAIGN_DAYS:
        signals.append(NEW_CAMPAIGN)
    share = row.get("_top_of_search_is")
    if (_known(share) and share < LOW_TOP_OF_SEARCH_SHARE
            and row.get(DIAGNOSIS_COLUMN) in (PAUSE, REVIEW)):
        signals.append(LOW_VISIBILITY)
    return signals


def _days_live(start: date | None, window_end: date) -> int | None:
    if start is None or pd.isna(start):
        return None
    return (window_end - start).days + 1


def _known(value) -> bool:
    return value is not None and not pd.isna(value)


def _clean_money(series: pd.Series) -> pd.Series:
    # Anything but the number goes: a Campaign CSV writes "$1,234.50", but also "MX$", "CA$", "£" or "€".
    return pd.to_numeric(series.astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce").fillna(0)


def _number(value, kind, default):
    try:
        return kind(value) if value is not None else default
    except (TypeError, ValueError):
        return default
