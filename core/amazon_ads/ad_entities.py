"""Targets and SB/SD campaigns per profile, mapped to `ads_target` and `ads_sb_sd_campaign`.

The entity universe `campaign_entities` keeps for SP campaigns, extended to SP keywords and
targeting clauses, SB campaigns, keywords, product targets and themes, and SD campaigns and
targets. The reports only return what had activity in the range asked for; these listings return
every enabled or paused entity, with the state and bid it has now.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import date, datetime

from core.amazon_ads.api_client import AdsApiClient, AdsApiError
from core.integrations.store import _Rest

log = logging.getLogger(__name__)

TARGETS_TABLE = "ads_target"
PRODUCT_CAMPAIGNS_TABLE = "ads_sb_sd_campaign"

SP_KEYWORDS_PATH = "/sp/keywords/list"
SP_KEYWORD_MEDIA_TYPE = "application/vnd.spKeyword.v3+json"
SP_TARGETS_PATH = "/sp/targets/list"
SP_TARGET_MEDIA_TYPE = "application/vnd.spTargetingClause.v3+json"
SB_CAMPAIGNS_PATH = "/sb/v4/campaigns/list"
SB_CAMPAIGN_MEDIA_TYPE = "application/vnd.sbcampaignresource.v4+json"
SB_KEYWORDS_PATH = "/sb/keywords"
SB_TARGETS_PATH = "/sb/targets/list"
SB_THEMES_PATH = "/sb/themes/list"
SD_CAMPAIGNS_PATH = "/sd/campaigns"
SD_AD_GROUPS_PATH = "/sd/adGroups"
SD_TARGETS_PATH = "/sd/targets"
# SB's bid strategy when automated bidding is off; with it on, the strategy Amazon names.
SB_MANUAL_BIDDING = "MANUAL"

# Page sizes as verified against the live API: SP returns 1000 even when asked for more, SB campaigns
# answer 400 above 100.
SP_PAGE_SIZE = 1000
SB_CAMPAIGNS_PAGE_SIZE = 100
SB_TARGETS_PAGE_SIZE = 1000
SB_THEMES_PAGE_SIZE = 100
# The older SB keyword and SD listings page by offset instead of by token.
OFFSET_PAGE_SIZE = 5000
# A profile with more pages than this means the paging is looping, not real entities.
MAX_PAGES = 200
# An account can hold ~45k SP targets; one upsert per thousand keeps each request and statement small.
SAVE_BATCH_ROWS = 1000

_LISTED_STATES = ("ENABLED", "PAUSED")
_OFFSET_STATE_FILTER = ",".join(state.lower() for state in _LISTED_STATES)
# How Amazon refuses an SB feature the marketplace does not offer: Shapermint AU got 400 "Marketplace
# A39IBJ37TRP1C6 do not have access to Sponsored Brands product targeting functionality" from /sb/targets/list.
_NO_MARKETPLACE_ACCESS = "do not have access"

# Report-style text per predicate type, keyed without case or underscores so SP's ASIN_SAME_AS and
# SB/SD's asinSameAs share an entry. Any other type keeps its own name, kebab-cased.
_PREDICATE_TEXT = {
    "asinsameas": 'asin="{}"',
    "asincategorysameas": 'category="{}"',
    "asinbrandsameas": 'brand="{}"',
    "asinpricelessthan": "price<{}",
    "asinpricegreaterthan": "price>{}",
    "asinpricebetween": "price={}",
    "asinreviewratinglessthan": "rating<{}",
    "asinreviewratinggreaterthan": "rating>{}",
    "asinreviewratingbetween": "rating={}",
    "lookback": "lookback={}",
    "audiencesameas": 'audience="{}"',
}
# SP auto-targeting groups, named as the spTargeting report's `targeting` column names them.
_AUTO_GROUP_TEXT = {
    "queryhighrelmatches": "close-match",
    "querybroadrelmatches": "loose-match",
    "asinsubstituterelated": "substitutes",
    "asinaccessoryrelated": "complements",
}
_AUDIENCE_TYPES = {"views", "purchases", "audience"}
_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def fetch_sp_targets(api: AdsApiClient, profile_id: str) -> list[dict]:
    """Keywords and targeting clauses together: the two kinds of SP target."""
    keywords = _list_by_token(api, profile_id, SP_KEYWORDS_PATH, "keywords",
                              _state_filtered(SP_PAGE_SIZE), SP_KEYWORD_MEDIA_TYPE)
    clauses = _list_by_token(api, profile_id, SP_TARGETS_PATH, "targetingClauses",
                             _state_filtered(SP_PAGE_SIZE), SP_TARGET_MEDIA_TYPE)
    return ([_keyword_row("SP", raw) for raw in keywords if _has(raw, "keywordId")]
            + [_sp_clause_row(raw) for raw in clauses if _has(raw, "targetId")])


def fetch_sb_campaigns(api: AdsApiClient, profile_id: str) -> list[dict]:
    campaigns = _list_by_token(api, profile_id, SB_CAMPAIGNS_PATH, "campaigns",
                               _state_filtered(SB_CAMPAIGNS_PAGE_SIZE), SB_CAMPAIGN_MEDIA_TYPE)
    return [_sb_campaign_row(raw) for raw in campaigns if _has(raw, "campaignId")]


def fetch_sb_targets(api: AdsApiClient, profile_id: str) -> list[dict]:
    """Keywords, product targets and themes together: the three kinds of SB target."""
    keywords = _list_by_offset(api, profile_id, SB_KEYWORDS_PATH)
    # Neither body carries a state filter (/sb/targets/list answers 422 to one), so it is applied below.
    targets = _unless_not_offered(
        lambda: _list_by_token(api, profile_id, SB_TARGETS_PATH, "targets", {"maxResults": SB_TARGETS_PAGE_SIZE}),
        profile_id, SB_TARGETS_PATH)
    themes = _unless_not_offered(
        lambda: _list_by_token(api, profile_id, SB_THEMES_PATH, "themes", {"maxResults": SB_THEMES_PAGE_SIZE}),
        profile_id, SB_THEMES_PATH)
    return ([_keyword_row("SB", raw) for raw in keywords if _has(raw, "keywordId")]
            + [_sb_target_row(raw) for raw in targets if _has(raw, "targetId") and _is_listed(raw)]
            + [_theme_row(raw) for raw in themes if _has(raw, "themeId") and _is_listed(raw)])


def fetch_sd_campaigns(api: AdsApiClient, profile_id: str) -> list[dict]:
    """SD campaigns with the bid optimization of their ad groups, where SD keeps its bid strategy."""
    campaigns = [raw for raw in _list_by_offset(api, profile_id, SD_CAMPAIGNS_PATH) if _has(raw, "campaignId")]
    if not campaigns:
        return []
    strategies = _sd_bid_strategies(_list_by_offset(api, profile_id, SD_AD_GROUPS_PATH))
    return [_sd_campaign_row(raw, strategies.get(_id_text(raw["campaignId"]), "")) for raw in campaigns]


def fetch_sd_targets(api: AdsApiClient, profile_id: str) -> list[dict]:
    targets = _list_by_offset(api, profile_id, SD_TARGETS_PATH)
    return [_sd_target_row(raw) for raw in targets if _has(raw, "targetId")]


def save_targets(rest: _Rest, profile_id: str, ad_product: str, targets: list[dict], seen_at: datetime) -> int:
    """Upsert only: an archived target drops out of the listing, and its report rows still need its text."""
    rows_by_id = {
        target["target_id"]: {**target, "ad_product": ad_product, "profile_id": profile_id,
                              "seen_at": seen_at.isoformat()}
        for target in targets
        if target.get("target_id")
    }
    return _upsert_in_batches(rest, TARGETS_TABLE, list(rows_by_id.values()),
                              on_conflict="profile_id,ad_product,target_id")


def save_product_campaigns(rest: _Rest, profile_id: str, campaigns: list[dict], seen_at: datetime) -> int:
    """Upsert only, like targets. SB and SD rows may share a call, so the product is part of the key."""
    rows_by_key = {
        (campaign.get("ad_product"), campaign["campaign_id"]): {
            **campaign, "profile_id": profile_id, "seen_at": seen_at.isoformat(),
        }
        for campaign in campaigns
        if campaign.get("campaign_id")
    }
    return _upsert_in_batches(rest, PRODUCT_CAMPAIGNS_TABLE, list(rows_by_key.values()),
                              on_conflict="profile_id,ad_product,campaign_id")


def _upsert_in_batches(rest: _Rest, table: str, rows: list[dict], on_conflict: str) -> int:
    # Each batch is one bulk upsert, which PostgREST fails if it repeats a key: hence the callers' dicts.
    for start in range(0, len(rows), SAVE_BATCH_ROWS):
        rest.upsert(table, rows[start:start + SAVE_BATCH_ROWS], on_conflict=on_conflict)
    return len(rows)


def _state_filtered(page_size: int) -> dict:
    return {"stateFilter": {"include": list(_LISTED_STATES)}, "maxResults": page_size}


def _list_by_token(api: AdsApiClient, profile_id: str, path: str, items_key: str, body: dict,
                   media_type: str | None = None) -> list[dict]:
    items: list[dict] = []
    seen_tokens: set[str] = set()
    request_body = body
    for _ in range(MAX_PAGES):
        response = api.request(
            "POST",
            path,
            profile_id=profile_id,
            json_body=request_body,
            content_type=media_type,
            # A typed listing gets its type as Accept too: SP v3 answers 415 to the session's default `*/*`.
            accept=media_type,
        )
        page = _read_page(response, path, profile_id)
        if not isinstance(page, dict):
            raise AdsApiError(f"unexpected {path} page for profile {profile_id}", status=response.status_code)
        items.extend(raw for raw in page.get(items_key) or [] if isinstance(raw, dict))

        next_token = str(page.get("nextToken") or "")
        if not next_token:
            return items
        if next_token in seen_tokens:
            log.warning("amazon_ads: profile %s repeated a %s page token, stopping", profile_id, path)
            return items
        seen_tokens.add(next_token)
        # Every page repeats the filters and page size; only the token changes.
        request_body = {**body, "nextToken": next_token}
    raise AdsApiError(f"{path} for profile {profile_id} exceeded {MAX_PAGES} pages")


def _list_by_offset(api: AdsApiClient, profile_id: str, path: str) -> list[dict]:
    items: list[dict] = []
    for page_number in range(MAX_PAGES):
        start_index = page_number * OFFSET_PAGE_SIZE
        response = api.request(
            "GET",
            f"{path}?startIndex={start_index}&count={OFFSET_PAGE_SIZE}&stateFilter={_OFFSET_STATE_FILTER}",
            profile_id=profile_id,
        )
        page = _read_page(response, path, profile_id)
        if not isinstance(page, list):
            raise AdsApiError(f"unexpected {path} page for profile {profile_id}", status=response.status_code)
        items.extend(raw for raw in page if isinstance(raw, dict))
        # Only a short page is known to be the last; after a full one the next may still come back empty.
        if len(page) < OFFSET_PAGE_SIZE:
            return items
    raise AdsApiError(f"{path} for profile {profile_id} exceeded {MAX_PAGES} pages")


def _unless_not_offered(fetch: Callable[[], list[dict]], profile_id: str, path: str) -> list[dict]:
    """The listing, or none when the marketplace does not offer that SB feature: the account has no such
    targets, and failing would leave it without its SB campaigns too."""
    try:
        return fetch()
    except AdsApiError as exc:
        if exc.status != 400 or _NO_MARKETPLACE_ACCESS not in exc.body.lower():
            raise
        log.info("amazon_ads: profile %s: %s is not offered in its marketplace, listed as empty", profile_id, path)
        return []


def _read_page(response, path: str, profile_id: str):
    try:
        return response.json()
    except ValueError:
        raise AdsApiError(f"unreadable {path} page for profile {profile_id}",
                          status=response.status_code) from None


def _has(raw, id_key: str) -> bool:
    return isinstance(raw, dict) and raw.get(id_key) not in (None, "")


def _is_listed(raw: dict) -> bool:
    return _upper(raw.get("state")) in _LISTED_STATES


def _target_row(ad_product: str, raw: dict, id_key: str, kind: str, text: str, match_type: str = "") -> dict:
    return {
        "ad_product": ad_product,
        "target_id": _id_text(raw[id_key]),
        "campaign_id": _id_text(raw.get("campaignId")),
        "ad_group_id": _id_text(raw.get("adGroupId")),
        "target_kind": kind,
        "target_text": text,
        "match_type": match_type,
        "state": _upper(raw.get("state")),
        "bid": _amount(raw.get("bid")),
    }


def _keyword_row(ad_product: str, raw: dict) -> dict:
    return _target_row(ad_product, raw, "keywordId", "keyword", str(raw.get("keywordText") or ""),
                       match_type=_upper(raw.get("matchType")))


def _sp_clause_row(raw: dict) -> dict:
    predicates = _predicates(raw.get("resolvedExpression"), raw.get("expression"))
    kind = "auto" if _upper(raw.get("expressionType")) == "AUTO" else "product"
    return _target_row("SP", raw, "targetId", kind, _expression_text(predicates))


def _sb_target_row(raw: dict) -> dict:
    predicates = _predicates(raw.get("resolvedExpressions"), raw.get("expressions"))
    return _target_row("SB", raw, "targetId", "product", _expression_text(predicates))


def _theme_row(raw: dict) -> dict:
    # KEYWORDS_RELATED_TO_YOUR_BRAND reads keywords-related-to-your-brand in the sbTargeting report.
    return _target_row("SB", raw, "themeId", "theme", _kebab(str(raw.get("themeType") or "")))


def _sd_target_row(raw: dict) -> dict:
    predicates = _predicates(raw.get("resolvedExpression"), raw.get("expression"))
    if _upper(raw.get("expressionType")) == "AUTO":
        kind = "auto"
    elif any(_is_audience(predicate) for predicate in predicates):
        kind = "audience"
    else:
        kind = "product"
    return _target_row("SD", raw, "targetId", kind, _expression_text(predicates))


def _is_audience(predicate: dict) -> bool:
    # Remarketing (views, purchases) and audiences wrap a nested list of their own predicates.
    return (str(predicate.get("type") or "").lower() in _AUDIENCE_TYPES
            or isinstance(predicate.get("value"), list))


def _product_campaign_row(ad_product: str, raw: dict, *, is_multi_ad_groups: bool | None = None,
                          goal: str = "", tactic: str = "", bid_strategy: str = "") -> dict:
    return {
        "ad_product": ad_product,
        "campaign_id": _id_text(raw["campaignId"]),
        "name": str(raw.get("name") or ""),
        "state": _upper(raw.get("state")),
        "budget_amount": _amount(raw.get("budget")),
        "budget_type": _upper(raw.get("budgetType")),
        "cost_type": _upper(raw.get("costType")),
        # Amazon omits portfolioId entirely when the campaign is in no portfolio.
        "portfolio_id": _id_text(raw.get("portfolioId")),
        "start_date": _day(raw.get("startDate")),
        "is_multi_ad_groups": is_multi_ad_groups,
        "goal": goal,
        "tactic": tactic,
        "bid_strategy": bid_strategy,
    }


def _sb_campaign_row(raw: dict) -> dict:
    multi_ad_groups = raw.get("isMultiAdGroupsEnabled")
    return _product_campaign_row(
        "SB", raw,
        is_multi_ad_groups=multi_ad_groups if isinstance(multi_ad_groups, bool) else None,
        goal=str(raw.get("goal") or ""),
        bid_strategy=_sb_bid_strategy(raw.get("bidding")),
    )


def _sd_campaign_row(raw: dict, bid_strategy: str = "") -> dict:
    return _product_campaign_row("SD", raw, tactic=str(raw.get("tactic") or ""), bid_strategy=bid_strategy)


def _sb_bid_strategy(bidding) -> str:
    """MANUAL without automated bidding; with it, the strategy it optimizes for, e.g. MAXIMIZE_IMMEDIATE_SALES."""
    if not isinstance(bidding, dict):
        return ""
    automated = bidding.get("bidOptimization")
    if isinstance(automated, str):
        automated = {"true": True, "false": False}.get(automated.strip().lower())
    if automated is None:
        return ""
    if not automated:
        return SB_MANUAL_BIDDING
    return _upper(bidding.get("bidOptimizationStrategy")) or "AUTOMATED"


def _sd_bid_strategies(ad_groups: list) -> dict[str, str]:
    """campaign id -> its ad groups' bid optimizations (clicks, conversions, reach), comma-joined if they differ."""
    by_campaign: dict[str, set[str]] = {}
    for raw in ad_groups:
        if not isinstance(raw, dict) or not _has(raw, "campaignId"):
            continue
        optimization = str(raw.get("bidOptimization") or "").strip().lower()
        if optimization:
            by_campaign.setdefault(_id_text(raw["campaignId"]), set()).add(optimization)
    return {campaign_id: ",".join(sorted(values)) for campaign_id, values in by_campaign.items()}


def _predicates(*candidates) -> list[dict]:
    """The first non-empty predicate list: the resolved one names categories where the raw one has node ids."""
    for candidate in candidates:
        predicates = [item for item in candidate if isinstance(item, dict)] if isinstance(candidate, list) else []
        if predicates:
            return predicates
    return []


def _expression_text(predicates: list[dict]) -> str:
    return " ".join(text for text in map(_predicate_text, predicates) if text)


def _predicate_text(predicate: dict) -> str:
    type_name = str(predicate.get("type") or "").strip()
    if not type_name:
        return ""
    key = type_name.replace("_", "").lower()
    value = predicate.get("value")
    if isinstance(value, list):
        return f"{_kebab(type_name)}=({_expression_text(_predicates(value))})"
    if key in _AUTO_GROUP_TEXT:
        return _AUTO_GROUP_TEXT[key]
    if value is None or str(value).strip() == "":
        # A predicate without a value is a named group: similarProduct, exactProduct.
        return _kebab(type_name)
    template = _PREDICATE_TEXT.get(key)
    if template is None:
        return f'{_kebab(type_name)}="{value}"'
    return template.format(value)


def _kebab(name: str) -> str:
    """asinSameAs and ASIN_SAME_AS both become asin-same-as."""
    return _WORD_BOUNDARY.sub("-", name.strip()).replace("_", "-").lower()


def _upper(value) -> str:
    return str(value or "").strip().upper()


def _id_text(value) -> str:
    # Amazon sends ids as JSON numbers, some 18 digits long; a float rendering would break every join.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _day(value) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        # The SD listing sends YYYYMMDD; the SB listing sends ISO dates.
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        log.warning("amazon_ads: campaign date %r is not a date, stored empty", raw)
        return None


def _amount(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        log.warning("amazon_ads: amount %r is not a number, stored empty", value)
        return None
