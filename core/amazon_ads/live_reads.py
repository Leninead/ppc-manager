"""Amazon Ads reads answered in the moment, one account at a time, for the chat.

Only endpoints Amazon answers synchronously. Each function sends one documented request and keeps the fields a person
reads; a failure becomes one sentence for the account manager (`LiveReadError`, a ValueError, which the MCP server
shows to the model as it is). Nothing here writes to Amazon.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import quote, urlencode

import requests

from core.amazon_ads.api_client import AdsAccessDenied, AdsApiClient, AdsApiError, AdsThrottled
from core.amazon_ads.tokens import ConnectionUnavailable, TokenManager
from core.integrations import crypto, oauth
from core.integrations.store import _Rest

log = logging.getLogger(__name__)

TOKENS_JWT_ENV = "ADS_TOKENS_JWT"
# Someone is waiting on these calls: 5 s per attempt, 2 retries, never more than 2 s between attempts.
TIMEOUT_S = 5
RETRIES = 2
MAX_WAIT_S = 2.0
RECOMMENDATIONS_TTL_S = 6 * 3600
PRODUCTS = ("SP", "SB", "SD")
# Amazon's budget for a portfolio without a cap.
NO_CAP_BUDGET = 9_999_999_999
MAX_HISTORY_DAYS = 89
HISTORY_ENTITIES = ("CAMPAIGN", "AD_GROUP", "KEYWORD", "PRODUCT_TARGETING", "NEGATIVE_KEYWORD", "AD")
HISTORY_CHANGES = ("BID_AMOUNT", "BUDGET_AMOUNT", "STATUS", "IN_BUDGET", "PLACEMENT_GROUP", "SMART_BIDDING_STRATEGY",
                   "NAME", "START_DATE", "END_DATE")
STORE_METRICS = ("VISITS", "VISITORS", "VIEWS", "SALES", "ORDERS", "UNITS", "NEW_TO_STORE", "BOUNCE_RATE", "DWELL_TIME")
STORE_DIMENSIONS = ("DATE", "PAGE", "SOURCE")

_BUDGET_RECOMMENDATIONS = {
    "SP": ("/sp/campaigns/budgetRecommendations", "application/vnd.budgetrecommendation.v3+json"),
    "SB": ("/sb/campaigns/budgetRecommendations", "application/vnd.sbbudgetrecommendation.v4+json"),
    "SD": ("/sd/campaigns/budgetRecommendations", "application/vnd.sdbudgetrecommendations.v3+json"),
}
_BUDGET_USAGE = {
    "SP": ("/sp/campaigns/budget/usage", "application/vnd.spcampaignbudgetusage.v1+json", "campaignIds", "campaignId"),
    "SB": ("/sb/campaigns/budget/usage", "application/vnd.sbcampaignbudgetusage.v1+json", "campaignIds", "campaignId"),
    "SD": ("/sd/campaigns/budget/usage", "application/vnd.sdcampaignbudgetusage.v1+json", "campaignIds", "campaignId"),
    "PORTFOLIO": ("/portfolios/budget/usage", "application/vnd.portfoliobudgetusage.v1+json", "portfolioIds",
                  "portfolioId"),
}
_BUDGET_RULES = {"SP": "/sp/budgetRules", "SB": "/sb/budgetRules", "SD": "/sd/budgetRules"}
# MX and AU answer 422 to anything older than v5.
_SP_BIDS_MEDIA = "application/vnd.spthemebasedbidrecommendation.v5+json"
_SP_KEYWORDS_MEDIA = "application/vnd.spkeywordsrecommendation.v5+json"
_SD_BIDS_MEDIA = "application/vnd.sdtargetingrecommendations.v3.3+json"
_SP_AUTO_TARGETS = {"close-match": "CLOSE_MATCH", "loose-match": "LOOSE_MATCH", "substitutes": "SUBSTITUTES",
                    "complements": "COMPLEMENTS"}
_MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")
_QUOTED = re.compile(r'(asin|category)="([^"]+)"')


class LiveReadError(ValueError):
    """What went wrong, said for the account manager."""


@dataclass(frozen=True)
class LiveAccount:
    """The account a live read is for: whose token opens it and which regional host answers."""

    profile_id: str
    connection_id: int
    region: str
    country: str
    currency: str
    label: str


def configured() -> bool:
    """True when this process can open the accounts' tokens: the token role's JWT and the sealing key."""
    if not (os.environ.get("SUPABASE_URL", "").strip() and os.environ.get(TOKENS_JWT_ENV, "").strip()):
        return False
    return bool(os.environ.get(crypto.PRIVATE_KEY_ENV, "").strip()) or crypto.private_key_path().exists()


_tokens: TokenManager | None = None
_tokens_lock = threading.Lock()


def _token_manager() -> TokenManager:
    global _tokens
    with _tokens_lock:
        if _tokens is None:
            rest = _Rest(os.environ["SUPABASE_URL"].strip(), os.environ[TOKENS_JWT_ENV].strip())
            _tokens = TokenManager(rest, crypto.read_existing_private_key())
        return _tokens


def client_for(account: LiveAccount) -> AdsApiClient:
    try:
        tokens = _token_manager()
    except (crypto.SealError, KeyError) as exc:
        raise LiveReadError("Este servidor no puede abrir las autorizaciones de Amazon Ads: falta su configuración.") \
            from exc
    return AdsApiClient(region=account.region, client_id_source=tokens.client_id,
                        token_source=tokens.token_source(account.connection_id), max_retries=RETRIES,
                        timeout_s=TIMEOUT_S, max_retry_after_s=MAX_WAIT_S)


_remembered: dict[tuple, tuple[float, object]] = {}
_remembered_lock = threading.Lock()


def remembered(key: tuple, fetch: Callable[[], object], ttl_s: float = RECOMMENDATIONS_TTL_S) -> tuple[object, float]:
    """`fetch()` once per `ttl_s` for `key`, and when it was fetched (epoch seconds): for endpoints with a tight quota."""
    with _remembered_lock:
        hit = _remembered.get(key)
    if hit and time.time() - hit[0] < ttl_s:
        return hit[1], hit[0]
    value = fetch()
    fetched_at = time.time()
    with _remembered_lock:
        _remembered[key] = (fetched_at, value)
    return value, fetched_at


def explain(exc: Exception, account: LiveAccount, what: str) -> LiveReadError:
    if isinstance(exc, AdsThrottled):
        return LiveReadError(f"Amazon está limitando las consultas de {what} en esta cuenta: probá de nuevo en un minuto.")
    if isinstance(exc, (oauth.NeedsReauth, ConnectionUnavailable)):
        return LiveReadError(f"La autorización de Amazon Ads de {account.label} venció o está pausada: hay que "
                             "reconectarla en Integraciones.")
    if isinstance(exc, AdsAccessDenied):
        return LiveReadError(f"La autorización de Amazon Ads de {account.label} no tiene acceso a {what}.")
    if isinstance(exc, oauth.OAuthError):
        return LiveReadError("No se pudo renovar el acceso a Amazon Ads: probá de nuevo en un rato.")
    if isinstance(exc, AdsApiError):
        if exc.status is None:
            return LiveReadError(f"Amazon no respondió a tiempo al pedir {what}: probá de nuevo en un rato.")
        if exc.status >= 500:
            return LiveReadError(f"Amazon falló al responder {what} (HTTP {exc.status}): probá de nuevo en un rato.")
        detail = _amazon_message(exc.body)
        if "not supported" in detail.lower():
            return LiveReadError(f"Amazon no ofrece {what} en {account.country}.")
        return LiveReadError(f"Amazon rechazó el pedido de {what} (HTTP {exc.status}): {detail or 'sin detalle'}.")
    return LiveReadError(f"No se pudo hablar con Amazon al pedir {what}: probá de nuevo en un rato.")


def _amazon_message(body: str) -> str:
    """Amazon's own reason, short and without links."""
    text = (body or "").strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        text = str(parsed.get("message") or parsed.get("details") or parsed.get("description") or parsed.get("code")
                   or "")
    text = re.sub(r"https?://\S+", "", re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()[:200]


def _request(api: AdsApiClient, account: LiveAccount, what: str, method: str, path: str, *, body: dict | None = None,
             media: str | None = None, accept: str | None = None, query: dict | None = None,
             expected: tuple[int, ...] = (200, 207)) -> dict:
    if query:
        path = f"{path}?{urlencode(query)}"
    started = time.perf_counter()
    try:
        response = api.request(method, path, profile_id=account.profile_id, json_body=body,
                               content_type=media if body is not None else None, accept=accept or media,
                               expected=expected)
    except (AdsApiError, oauth.OAuthError, ConnectionUnavailable, crypto.SealError, requests.RequestException) as exc:
        log.info("ads live: %s for profile %s failed after %.0f ms (%s)", what, account.profile_id,
                 (time.perf_counter() - started) * 1000, type(exc).__name__)
        raise explain(exc, account, what) from exc
    log.info("ads live: %s for profile %s answered %s in %.0f ms", what, account.profile_id, response.status_code,
             (time.perf_counter() - started) * 1000)
    if response.status_code == 204:
        return {}
    try:
        parsed = response.json()
    except ValueError as exc:
        raise LiveReadError(f"Amazon devolvió algo que no se puede leer al pedir {what}.") from exc
    return parsed if isinstance(parsed, dict) else {"items": parsed}


def budget_recommendations(api, account: LiveAccount, product: str, campaign_ids: Sequence[str]) -> dict[str, dict | None]:
    """Per campaign id, Amazon's suggested budget and what its last 7 days lost for lack of budget; None when Amazon
    has no recommendation for it."""
    path, media = _BUDGET_RECOMMENDATIONS[product]
    found: dict[str, dict | None] = {}
    for chunk in _chunks(campaign_ids, 100):
        result = _request(api, account, "las recomendaciones de presupuesto", "POST", path,
                          body={"campaignIds": list(chunk)}, media=media)
        for item in _first_list(result, "budgetRecommendationsSuccessResults", "success"):
            campaign_id = _entity_id(item, chunk, "campaignId")
            if campaign_id:
                found[campaign_id] = _budget_recommendation(item, product)
        for item in _first_list(result, "budgetRecommendationsErrorResults", "error"):
            campaign_id = _entity_id(item, chunk, "campaignId")
            if campaign_id:
                found.setdefault(campaign_id, None)
    return found


def _budget_recommendation(item: dict, product: str) -> dict:
    missed = item.get("sevenDaysMissedOpportunities") or {}
    share = _number(missed.get("percentTimeInBudget"))
    if share is not None:
        # Sponsored Products answers a 0-1 fraction and −1 without data; Brands and Display answer 0-100.
        share = None if share < 0 else round(share * 100 if product == "SP" else share, 1)
    return {
        "suggested_budget": _number(item.get("suggestedBudget")),
        "time_in_budget_pct": share,
        "missed_sales": _range(missed, "estimatedMissedSales"),
        "missed_clicks": _range(missed, "estimatedMissedClicks"),
        "missed_impressions": _range(missed, "estimatedMissedImpressions"),
        "window": [missed.get("startDate"), missed.get("endDate")] if missed.get("startDate") else None,
        "rule_increase_pct": _number((item.get("budgetRuleRecommendation") or {}).get("suggestedBudgetIncreasePercent")),
    }


def budget_usage(api, account: LiveAccount, kind: str, ids: Sequence[str]) -> dict[str, dict]:
    """Per campaign (SP, SB, SD) or portfolio (PORTFOLIO) id: its budget and how much of it is spent right now."""
    path, media, body_key, id_key = _BUDGET_USAGE[kind]
    found: dict[str, dict] = {}
    for chunk in _chunks(ids, 100):
        result = _request(api, account, "el uso de presupuesto", "POST", path, body={body_key: list(chunk)},
                          media=media)
        for item in _first_list(result, "success"):
            entity_id = _entity_id(item, chunk, id_key)
            budget = _number(item.get("budget"))
            found[entity_id] = {
                "budget": None if budget is not None and budget >= NO_CAP_BUDGET else budget,
                "usage_pct": _number(item.get("budgetUsagePercent")),
                "updated_at": item.get("usageUpdatedTimestamp") or item.get("lastUpdatedDate"),
            }
    return found


def budget_rules(api, account: LiveAccount, product: str) -> list[dict]:
    rules: list[dict] = []
    token = ""
    for _ in range(5):
        query = {"pageSize": 30, **({"nextToken": token} if token else {})}
        result = _request(api, account, "las reglas de presupuesto", "GET", _BUDGET_RULES[product],
                          accept="application/json", query=query, expected=(200,))
        rules.extend(_budget_rule(rule, product) for rule in result.get("budgetRulesForAdvertiserResponse") or [])
        token = result.get("nextToken") or ""
        if not token:
            break
    return rules


def _budget_rule(rule: dict, product: str) -> dict:
    details = rule.get("ruleDetails") or {}
    increase = details.get("budgetIncreaseBy") or {}
    condition = details.get("performanceMeasureCondition") or {}
    duration = details.get("duration") or {}
    dates = duration.get("dateRangeTypeRuleDuration") or duration.get("eventTypeRuleDuration") or {}
    recurrence = details.get("recurrence") or {}
    return {
        "rule_id": rule.get("ruleId"),
        "name": details.get("name"),
        "product": product,
        "type": details.get("ruleType"),
        "state": rule.get("ruleState"),
        "status": rule.get("ruleStatus"),
        "increase_pct": _number(increase.get("value")) if increase.get("type") == "PERCENT" else None,
        "condition": (" ".join(str(part) for part in (condition.get("metricName"), condition.get("comparisonOperator"),
                                                      condition.get("threshold")) if part is not None) or None),
        "recurrence": recurrence.get("type"),
        "event": (duration.get("eventTypeRuleDuration") or {}).get("eventName"),
        "start": dates.get("startDate"),
        "end": dates.get("endDate"),
    }


def product_metadata(api, account: LiveAccount, asins: Sequence[str]) -> list[dict]:
    """Stock, price, best seller rank and whether each ASIN can be advertised."""
    rows: list[dict] = []
    for chunk in _chunks(asins, 300):
        result = _request(api, account, "los datos de los productos", "POST", "/product/metadata",
                          body={"asins": list(chunk), "pageIndex": 0, "pageSize": len(chunk), "checkItemDetails": True,
                                "checkEligibility": True, "adType": "SP"},
                          media="application/vnd.productmetadatarequest.v1+json",
                          accept="application/vnd.productmetadataresponse.v1+json", expected=(200,))
        rows.extend(_product(item) for item in result.get("ProductMetadataList") or [])
    return rows


def _product(item: dict) -> dict:
    price = item.get("priceToPay") or {}
    basis = item.get("basisPrice") or {}
    status = item.get("eligibilityStatus")
    return {
        "asin": item.get("asin"),
        "sku": item.get("sku"),
        "title": (item.get("title") or "")[:90] or None,
        "brand": item.get("brand"),
        "category": item.get("category"),
        "availability": item.get("availability"),
        "price": _number(price.get("amount")),
        "list_price": _number(basis.get("amount")),
        "currency": price.get("currency") or basis.get("currency"),
        "best_seller_rank": _number(item.get("bestSellerRank")),
        "eligibility": status,
        "ineligibility_codes": list(item.get("ineligibilityCodes") or []),
    }


def change_history(api, account: LiveAccount, *, days: int, entities: Sequence[str] = HISTORY_ENTITIES,
                   change: str = "", campaign_ids: Sequence[str] = (), offset: int = 0, count: int = 200) -> dict:
    """The newest changes of the last `days` days, with the value before and after. Amazon does not say who made
    them and keeps no Sponsored Display history."""
    now_ms = int(time.time() * 1000)
    span_days = min(max(int(days), 1), MAX_HISTORY_DAYS)
    event_types = {}
    for entity in entities:
        scope: dict = {}
        if campaign_ids and entity == "CAMPAIGN":
            scope["eventTypeIds"] = list(campaign_ids)[:10]
        elif campaign_ids:
            scope["parents"] = [{"campaignId": campaign_id} for campaign_id in list(campaign_ids)[:10]]
        else:
            scope["parents"] = [{"useProfileIdAdvertiser": True}]
        if change:
            scope["filters"] = [change]
        event_types[entity] = scope
    body = {"fromDate": now_ms - span_days * 86_400_000, "toDate": now_ms, "count": min(max(int(count), 50), 200),
            "pageOffset": max(int(offset), 0), "sort": {"key": "DATE", "direction": "DESC"},
            "eventTypes": event_types}
    result = _request(api, account, "el historial de cambios", "POST", "/history", body=body, media="application/json",
                      accept="application/json", expected=(200,))
    return {"events": [_event(event) for event in result.get("events") or []], "total": result.get("totalRecords")}


def _event(event: dict) -> dict:
    stamp = _number(event.get("timestamp"))
    detail = {key: value for key, value in (event.get("metadata") or {}).items() if value not in (None, "", [], {})}
    return {
        "at": datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat(timespec="minutes") if stamp else None,
        "entity": event.get("entityType"),
        "entity_id": str(event.get("entityId") or ""),
        "change": event.get("changeType"),
        "before": event.get("previousValue"),
        "after": event.get("newValue"),
        "detail": detail,
    }


def sp_target_expression(kind: str, text: str, match: str = "") -> dict | None:
    """The bid recommendation expression of a Sponsored Products target, or None for the kinds Amazon cannot price."""
    text = (text or "").strip()
    if kind == "keyword":
        return {"type": f"KEYWORD_{match}_MATCH", "value": text} if match in _MATCH_TYPES and text else None
    if kind == "auto":
        auto = _SP_AUTO_TARGETS.get(text.lower())
        return {"type": auto} if auto else None
    quoted = _QUOTED.fullmatch(text)
    if quoted:
        return {"type": "PAT_ASIN" if quoted.group(1) == "asin" else "PAT_CATEGORY", "value": quoted.group(2)}
    return None


def sd_target_expression(text: str) -> dict | None:
    """The Display bid recommendation expression of a product or category target; audiences have no simple one."""
    quoted = _QUOTED.fullmatch((text or "").strip())
    if not quoted:
        return None
    kind = "asinSameAs" if quoted.group(1) == "asin" else "asinCategorySameAs"
    return {"type": kind, "value": quoted.group(2)}


def sp_keyword_recommendations(api, account: LiveAccount, campaign_id: str, ad_group_id: str,
                               keywords: Sequence[dict]) -> list[dict]:
    """The ad group's keywords and Amazon's ideas, each with the account's 30-day impression share and rank and the
    suggested bid per match type."""
    targets = [{"keyword": keyword["text"], "matchType": keyword["match"], "userSelectedKeyword": True,
                **({"bid": float(keyword["bid"])} if keyword.get("bid") else {})}
               for keyword in keywords if keyword.get("match") in _MATCH_TYPES][:100]
    body = {"recommendationType": "KEYWORDS_FOR_ADGROUP", "campaignId": str(campaign_id), "adGroupId": str(ad_group_id),
            "maxRecommendations": 100, "sortDimension": "DEFAULT", "bidsEnabled": True,
            **({"targets": targets} if targets else {})}
    result = _request(api, account, "las keywords sugeridas", "POST", "/sp/targets/keywords/recommendations",
                      body=body, media=_SP_KEYWORDS_MEDIA, expected=(200,))
    return [_keyword_idea(item) for item in result.get("keywordTargetList") or []]


def _keyword_idea(item: dict) -> dict:
    bids = {}
    for info in item.get("bidInfo") or []:
        suggested = info.get("suggestedBid") or {}
        bids[info.get("matchType")] = {"low": _cents(suggested.get("rangeStart")),
                                       "suggested": _cents(suggested.get("rangeMedian")),
                                       "high": _cents(suggested.get("rangeEnd"))}
    return {
        "keyword": item.get("keyword"),
        "targeted": bool(item.get("userSelectedKeyword")),
        "impression_share_pct": _number(item.get("searchTermImpressionShare")),
        "impression_rank": _number(item.get("searchTermImpressionRank")),
        "suggested_bids": bids,
    }


def sp_bid_recommendations(api, account: LiveAccount, campaign_id: str, ad_group_id: str,
                           expressions: Sequence[dict]) -> list[dict]:
    body = {"recommendationType": "BIDS_FOR_EXISTING_AD_GROUP", "campaignId": str(campaign_id),
            "adGroupId": str(ad_group_id), "targetingExpressions": list(expressions)[:100]}
    result = _request(api, account, "los bids sugeridos", "POST", "/sp/targets/bid/recommendations", body=body,
                      media=_SP_BIDS_MEDIA, expected=(200,))
    rows = []
    for theme in result.get("bidRecommendations") or []:
        for item in theme.get("bidRecommendationsForTargetingExpressions") or []:
            values = sorted(value for value in (_number(bid.get("suggestedBid")) for bid in item.get("bidValues") or [])
                            if value is not None)
            expression = item.get("targetingExpression") or {}
            rows.append({"theme": theme.get("theme"), "type": expression.get("type"), "value": expression.get("value"),
                         "low": values[0] if values else None, "suggested": values[len(values) // 2] if values else None,
                         "high": values[-1] if values else None})
    return rows


def sb_keyword_insights(api, account: LiveAccount, keywords: Sequence[dict]) -> list[dict]:
    """The account's 7-day impression share and rank for each Sponsored Brands keyword, with Amazon's alerts."""
    sent = [{"keywordText": keyword["text"], "matchType": keyword["match"], "bid": float(keyword.get("bid") or 1.0)}
            for keyword in keywords if keyword.get("match") in _MATCH_TYPES][:100]
    if not sent:
        return []
    result = _request(api, account, "el share de impresiones de las keywords", "POST", "/sb/campaigns/insights",
                      body={"adGroups": [{"keywords": sent, "adFormat": "PRODUCT_COLLECTION"}]},
                      media="application/vnd.sbinsights.v4+json", expected=(200,))
    rows = []
    for insight in result.get("insights") or []:
        keyword = insight.get("keywordInsight") or {}
        rows.append({"keyword": keyword.get("keywordText"), "match": keyword.get("matchType"),
                     "impression_share_pct": _number(keyword.get("searchTermImpressionShare")),
                     "impression_rank": _number(keyword.get("searchTermImpressionRank")),
                     "alerts": list(keyword.get("alerts") or [])})
    return rows


def sb_keyword_bids(api, account: LiveAccount, campaign_id: str, keywords: Sequence[dict]) -> list[dict]:
    sent = [{"matchType": keyword["match"].lower(), "keywordText": keyword["text"]}
            for keyword in keywords if keyword.get("match") in _MATCH_TYPES][:100]
    if not sent:
        return []
    result = _request(api, account, "los bids sugeridos de Sponsored Brands", "POST", "/sb/recommendations/bids",
                      body={"campaignId": int(campaign_id), "keywords": sent, "adFormat": "productCollection"},
                      media="application/json", accept="application/vnd.sbbidsrecommendation.v3+json",
                      expected=(200,))
    rows = []
    for item in result.get("keywordsBidsRecommendationSuccessResults") or []:
        keyword = item.get("keyword") or {}
        bid = item.get("recommendedBid") or {}
        rows.append({"keyword": keyword.get("keywordText"), "match": str(keyword.get("matchType") or "").upper(),
                     "low": _number(bid.get("rangeStart")), "suggested": _number(bid.get("recommended")),
                     "high": _number(bid.get("rangeEnd"))})
    return rows


def sd_target_bids(api, account: LiveAccount, expressions: Sequence[dict], cost_type: str) -> list[dict]:
    vcpm = (cost_type or "").upper() == "VCPM"
    sent = list(expressions)[:100]
    body = {"bidOptimization": "reach" if vcpm else "clicks", "costType": "vcpm" if vcpm else "cpc",
            "targetingClauses": [{"targetingClause": {"expressionType": "manual", "expression": [expression]}}
                                 for expression in sent]}
    result = _request(api, account, "los bids sugeridos de Sponsored Display", "POST",
                      "/sd/targets/bid/recommendations", body=body, media=_SD_BIDS_MEDIA)
    rows = []
    for index, item in enumerate(result.get("bidRecommendations") or []):
        expression = sent[index] if index < len(sent) else {}
        known = str(item.get("code") or "200") == "200"
        rows.append({"type": expression.get("type"), "value": expression.get("value"),
                     "low": _number(item.get("rangeLower")) if known else None,
                     "suggested": _number(item.get("recommended")) if known else None,
                     "high": _number(item.get("rangeUpper")) if known else None,
                     **({} if known else {"note": "Amazon no tiene recomendación para este target"})})
    return rows


def sb_category_benchmarks(api, account: LiveAccount, start: date, end: date, pages: int = 3) -> dict:
    """Each brand of the account against its category in Sponsored Brands: the brand's figure, the median and the
    top and bottom quartiles. `more` says Amazon had pages left after `pages`."""
    rows: list[dict] = []
    token = ""
    for _ in range(pages):
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
                "metrics": ["ACOS", "CTR", "IMPRESSIONS", "ROAS"], "programType": "SB",
                **({"nextPageToken": token} if token else {})}
        result = _request(api, account, "el benchmark de categoría", "POST", "/benchmarks/brandsAndCategories",
                          body=body, media="application/vnd.reportdata.v1+json", expected=(200, 204))
        rows.extend(_benchmark(item) for item in result.get("brandsAndCategories") or [])
        token = result.get("nextPageToken") or ""
        if not token:
            break
    return {"rows": rows, "more": bool(token)}


def _benchmark(item: dict) -> dict:
    row = {"brand": item.get("brandName"), "category": item.get("categoryName") or item.get("category")}
    for metric, percent in (("acos", True), ("ctr", True), ("roas", False), ("impressions", False)):
        values = item.get(metric) or {}
        scale = 100 if percent else 1
        row[metric] = {name: _scaled(values.get(key), scale) for name, key in
                       (("brand", "value"), ("median", "median"), ("top_25", "top-25pct"),
                        ("bottom_25", "bottom-25pct"))}
    return row


def invoices(api, account: LiveAccount, count: int) -> list[dict]:
    # The versioned media type answers 406; plain JSON is what works, also for seller accounts.
    result = _request(api, account, "las facturas", "GET", "/invoices", accept="application/json",
                      query={"count": min(max(int(count), 1), 100)}, expected=(200,))
    payload = result.get("payload") or result
    return [_invoice(summary) for summary in payload.get("invoiceSummaries") or []]


def invoice_detail(api, account: LiveAccount, invoice_id: str) -> dict:
    result = _request(api, account, "la factura", "GET", f"/invoices/{quote(invoice_id, safe='')}",
                      accept="application/json", expected=(200,))
    payload = result.get("payload") or result
    lines = [{"campaign_id": str(line.get("campaignId") or ""), "campaign": line.get("campaignName") or line.get("name"),
              "program": line.get("programName"), "cost": _money(line.get("cost")),
              "events": line.get("costEventCount"), "event_type": line.get("costEventType"),
              "cost_per_unit": _number(line.get("costPerUnit"))}
             for line in payload.get("invoiceLines") or []]
    lines.sort(key=lambda line: line["cost"]["amount"] if line["cost"] and line["cost"]["amount"] else 0,
               reverse=True)
    return {"invoice": _invoice(payload.get("invoiceSummary") or {}), "lines": lines}


def _invoice(summary: dict) -> dict:
    # The month still open has no id until Amazon issues it.
    return {
        "invoice_id": summary.get("id"),
        "status": summary.get("status"),
        "period": [_iso_day(summary.get("fromDate")), _iso_day(summary.get("toDate"))],
        "invoice_date": _iso_day(summary.get("invoiceDate")),
        "due_date": _iso_day(summary.get("dueDate")),
        "amount": _money(summary.get("amountDue")),
        "tax": _money(summary.get("taxAmountDue")),
        "remaining": _money(summary.get("remainingAmountDue")),
    }


def stores(api, account: LiveAccount) -> list[dict]:
    # With an identifier Amazon rejects ASINs and other entities' ids: without one it lists the account's own stores.
    result = _request(api, account, "las Stores", "POST", "/brand/stores/v1/stores/list", body={"maxResults": 10},
                      media="application/vnd.bhstoreslist.v1+json", expected=(200,))
    return [{"store_id": store.get("storeId"), "name": store.get("storeName"),
             "brand_entity_id": store.get("brandEntityId")} for store in result.get("stores") or []]


def store_insights(api, account: LiveAccount, brand_entity_id: str, metric: str, dimension: str, start: date,
                   end: date) -> list[dict]:
    """One metric of a store by day, page or traffic source: Amazon answers one metric per request."""
    body = {"dimension": dimension, "metrics": [metric], "startDate": start.isoformat(), "endDate": end.isoformat()}
    result = _request(api, account, "las métricas de la Store", "POST",
                      f"/stores/{quote(brand_entity_id, safe='')}/insights", body=body,
                      media="application/vnd.GetInsightsForStoreRequest.v1+json",
                      accept="application/vnd.GetInsightsForStoreResponse.v1+json", expected=(200,))
    rows = []
    for item in result.get("metricsDetails") or []:
        row = {}
        for key, value in item.items():
            if key == "date":
                row[key] = _iso_day(value)
            else:
                number = _number(value)
                row[key] = number if number is not None else value
        rows.append(row)
    return rows


def _iso_day(value):
    """Amazon writes some days as YYYYMMDD: they leave here as YYYY-MM-DD."""
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _chunks(items: Sequence, size: int) -> list[list]:
    values = [str(item) for item in items]
    return [values[start:start + size] for start in range(0, len(values), size)]


def _first_list(result: dict, *keys: str) -> list[dict]:
    for key in keys:
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _entity_id(item: dict, chunk: Sequence[str], id_key: str) -> str:
    """The id an item of a batch answers for: its own when Amazon sends it, else the one at its index."""
    explicit = item.get(id_key)
    if explicit not in (None, ""):
        return str(explicit)
    index = item.get("index")
    return str(chunk[index]) if isinstance(index, int) and 0 <= index < len(chunk) else ""


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _scaled(value, scale: int):
    number = _number(value)
    return None if number is None else round(number * scale, 4)


def _cents(value):
    # The keyword recommendations price their bids in cents of the account's currency.
    number = _number(value)
    return None if number is None else round(number / 100, 2)


def _range(values: dict, prefix: str) -> list | None:
    low, high = _number(values.get(f"{prefix}Lower")), _number(values.get(f"{prefix}Upper"))
    return None if low is None and high is None else [low, high]


def _money(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {"amount": _number(value.get("amount")), "currency": value.get("currencyCode") or value.get("currency")}
