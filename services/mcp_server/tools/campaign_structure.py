"""campaign_structure: an account's campaigns as Amazon Ads last listed them, and the metrics of the window.

Sponsored Products carries its whole structure: campaigns with their placements, ad groups, keywords, product
targets, product ads and negatives. Sponsored Brands and Display carry their keywords and targets. `targets` asks
for a list of terms at once and answers one row per term, found or not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from core.amazon_ads.campaign_provider import BID_STRATEGY_LABELS
from core.amazon_ads.product_provider import TARGET_KIND_LABELS
from core.amazon_ads.report_provider import ProfileOption, _attribution_days, _portfolio_label
from core.amazon_ads.structure_provider import (
    _ATTRIBUTION_FIELDS,
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    CAMPAIGN_NEGATIVE_KEYWORD,
    CAMPAIGN_NEGATIVE_PRODUCT_TARGETING,
    KEYWORD,
    NEGATIVE_ENTITIES,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    StructureProvider,
)
from core.amazon_ads.sync_planner import CAMPAIGN_ENTITIES_KIND, SP_AD_GROUPS_KIND, SP_PRODUCT_ADS_KIND, SP_TARGETS_KIND
from core.integrations.sync_jobs import SyncJobStore
from services.mcp_server.limits import page
from services.mcp_server.tools.account_resolver import campaign_profile, choose_account
from services.mcp_server.tools.analyses import _account_time
from services.mcp_server.tools.campaign_selector import CampaignRequest, select_campaigns
from services.mcp_server.tools.figures import _metrics, _plain_number
from services.mcp_server.tools.metric_filters import (
    FILTER_METRICS,
    SORT_METRICS,
    FiltersParam,
    RowFilter,
    SortOrder,
    check_sort,
    sort_rows,
    with_sort_figure,
)
from services.mcp_server.tools.term_lookup import LOOKUP_NOTE, TargetMatch, lookup_terms
from services.mcp_server.tools.windows import DEFAULT_DAYS, requested_window, window_payload

DISTINCT_ADS_NOTE = ("Cada fila es un anuncio: un ASIN en varias campañas o ad groups son varios anuncios. distinct "
                     "cuenta los ASINs y SKUs distintos de todas las filas que cumplen el pedido, no sólo de esta página.")
# How Amazon Ads writes a product target that aims exactly at one ASIN; asin-expanded-from="…" is the expanded one.
ASIN_TARGET_PREFIX = 'asin="'
# What the chat asks for, and the families of the SP structure each one reads.
STRUCTURE_ENTITIES = {
    "campaigns": (CAMPAIGN,),
    "placements": (BIDDING_ADJUSTMENT,),
    "ad_groups": (AD_GROUP,),
    "keywords": (KEYWORD,),
    "product_targets": (PRODUCT_TARGETING,),
    "product_ads": (PRODUCT_AD,),
    "negatives": NEGATIVE_ENTITIES,
}
StructureEntity = Literal["campaigns", "placements", "ad_groups", "keywords", "product_targets", "product_ads",
                          "negatives"]
StructureProduct = Literal["", "SP", "SB", "SD"]
StructureMatchType = Literal["", "exact", "phrase", "broad", "asin", "category"]
StructureSortMetric = Literal["", "spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc",
                              "ctr", "aov", "bid_gap"]
# The rows that hang from a campaign carry its state: an enabled keyword of a paused campaign does not run.
_CAMPAIGN_CHILDREN = ("ad_groups", "keywords", "product_targets", "product_ads", "negatives")
# What `target` searches in each entity: a keyword, target or negative by its text, a product ad by its ASIN or SKU.
_TEXT_COLUMNS = {"keywords": ("target_text",), "product_targets": ("target_text",), "negatives": ("target_text",),
                 "product_ads": ("asin", "sku")}
# A campaign's row carries its placement adjustments, which the database keeps as rows of their own family, and the
# rows under a campaign read their campaigns for its state.
_STRUCTURE_READS = {**STRUCTURE_ENTITIES, "campaigns": (CAMPAIGN, BIDDING_ADJUSTMENT),
                    **{entity: (CAMPAIGN, *STRUCTURE_ENTITIES[entity]) for entity in _CAMPAIGN_CHILDREN}}
# Past this, negatives are read one campaign at a time: a big account's, read whole, are hundreds of MB for one page.
MAX_ACCOUNT_NEGATIVES = 5000
STRUCTURE_STATES = ("enabled", "paused", "archived")
StructureState = Literal["", "enabled", "paused", "archived"]
STRUCTURE_SOURCE = ("Sólo Sponsored Products. La estructura es la foto diaria de las listas de entidades de Amazon Ads "
                    "(campañas, ad groups, keywords, targets, anuncios y negativos): es la de la hora de listed_at, "
                    "no la de este momento. Las métricas de la ventana, sólo de campañas, keywords y product targets, "
                    "salen de los reportes. El bid de un keyword o target es el efectivo: el propio o, si no tiene, el "
                    "default de su ad group (bid_source dice cuál). Ad groups, keywords, targets, anuncios y negativos "
                    "traen el estado de su campaña (campaign_state): corren sólo si ellos y su campaña están "
                    "habilitados. Un ajuste por placement en 0 es sin ajuste; vacío es que no se sabe.")
SB_SD_SOURCE = ("Los keywords y targets de las campañas de {product}, de su última lista, con el bid efectivo: el propio "
                "o, si no tiene, el default de su ad group. cost_type es cómo paga su campaña: CPC por click, VCPM "
                "por mil impresiones visibles; sólo en CPC el bid es por click y hay bid_gap. Las métricas de la "
                "ventana salen de sus reportes de targeting, con las ventas y órdenes de Campaign Manager (después de un click o una vista, a 14 días); "
                "sales_clicks y orders_clicks son sólo las de después de un click. Traen el estado de su campaña "
                "(campaign_state): corren sólo si ellos y su campaña están habilitados.")
TARGET_FIGURES_NOTE = ("cpc es el costo por click de la ventana y bid_gap el bid menos el cpc, sólo con clicks y con un "
                       "bid por click: positivo es que el bid está por encima de lo que se pagó. El bid es el de la última lista y el cpc el de "
                       "la ventana: si el bid cambió en el medio, o la estrategia de puja lo sube, no son del mismo "
                       "momento. top_of_search_share es el top-of-search impression share de la ventana, ponderado "
                       "por impresiones; vacío es que Amazon no lo informó.")
_STRUCTURE_WHAT = {"campaigns": "campañas", "placements": "ajustes por placement", "ad_groups": "ad groups",
                   "keywords": "keywords", "product_targets": "product targets", "product_ads": "product ads",
                   "negatives": "negativos"}
_ENTITY_OF_FAMILY = {family: entity for entity, families in STRUCTURE_ENTITIES.items() for family in families}
# A listing whose job completed counts even with no rows; the negatives count by their snapshot, in the counts.
_LISTING_KINDS = {"campaigns": CAMPAIGN_ENTITIES_KIND, "ad_groups": SP_AD_GROUPS_KIND, "keywords": SP_TARGETS_KIND,
                  "product_targets": SP_TARGETS_KIND, "product_ads": SP_PRODUCT_ADS_KIND}
_CAMPAIGN_NEGATIVES = (CAMPAIGN_NEGATIVE_KEYWORD, CAMPAIGN_NEGATIVE_PRODUCT_TARGETING)
_MEASURED_ENTITIES = ("campaigns", "keywords", "product_targets")
_TARGET_ENTITIES = ("keywords", "product_targets")
# What the rows of each measured entity carry to filter by: only keywords and targets have a bid.
_CAMPAIGN_FILTER_METRICS = tuple(metric for metric in FILTER_METRICS if metric != "bid_gap")
_SB_SD_ENTITIES = {"keywords": "keyword", "product_targets": "product_targeting"}
# Campaign Manager's names for the placements, and the key each adjustment takes in a campaign's row.
_PLACEMENT_LABELS = {"PLACEMENT_TOP": "Top of search", "PLACEMENT_PRODUCT_PAGE": "Product pages",
                     "PLACEMENT_REST_OF_SEARCH": "Rest of search", "SITE_AMAZON_BUSINESS": "Amazon Business"}
_PLACEMENT_KEYS = {"PLACEMENT_TOP": "top_of_search_pct", "PLACEMENT_PRODUCT_PAGE": "product_pages_pct",
                   "PLACEMENT_REST_OF_SEARCH": "rest_of_search_pct", "SITE_AMAZON_BUSINESS": "amazon_business_pct"}
_EXPRESSION_KINDS = {"asin": "asin", "asin-expanded": "asin", "category": "category"}
# The only cost type whose bid is a price per click; a VCPM bid is per thousand viewable impressions.
CPC_COST_TYPE = "CPC"


def campaign_structure(rest, *, profile_id: str = "", account: str = "", entity: StructureEntity = "campaigns",
                       product: StructureProduct = "", campaign: str = "", campaigns: tuple[str, ...] = (),
                       portfolio: str = "", state: StructureState = "", target: str = "",
                       targets: tuple[str, ...] = (), match: TargetMatch = "exact",
                       match_type: StructureMatchType = "", days: int = DEFAULT_DAYS, date_from: str = "",
                       date_to: str = "", filters: FiltersParam = None, running_only: bool = False,
                       sort_by: StructureSortMetric = "", sort_order: SortOrder = "desc", offset: int = 0,
                       limit: int = 50) -> dict:
    """La estructura de las campañas de una cuenta, como Amazon Ads la listó por última vez: de Sponsored Products sus
    campañas con presupuesto, estrategia y ajustes por placement (`entity`=campaigns), o sus placements, ad_groups,
    keywords, product_targets, product_ads o negatives; de Sponsored Brands y Display (`product`), sus keywords y
    product_targets.

    `campaign`, `campaigns` y `portfolio` acotan a esas campañas; `state`, a las filas en ese estado; `target`, a los
    keywords, product targets o negativos que contienen ese texto. `targets` pregunta por una lista de términos y
    devuelve una fila por término. `filters`, `running_only`, `match_type` y `sort_by` eligen y ordenan campañas,
    keywords y product targets por sus métricas.
    """
    families = STRUCTURE_ENTITIES.get(entity)
    if families is None:
        raise ValueError(f"entity tiene que ser uno de: {', '.join(STRUCTURE_ENTITIES)}")
    if product not in ("", "SP", "SB", "SD"):
        raise ValueError("product tiene que ser SP, SB o SD.")
    if product in ("SB", "SD") and entity not in _TARGET_ENTITIES:
        raise ValueError(f"De {product} se leen sus keywords y product_targets: pedilo con uno de esos entity.")
    row_filter = RowFilter.from_request(filters, metrics=FILTER_METRICS if entity in _TARGET_ENTITIES
                                        else _CAMPAIGN_FILTER_METRICS)
    if sort_by:
        check_sort(sort_by, SORT_METRICS + (("bid_gap",) if entity in _TARGET_ENTITIES else ()))
    if (sort_by or row_filter.applied() or running_only) and entity not in _MEASURED_ENTITIES:
        raise ValueError(f"sort_by y los filtros por métricas (filters, running_only) son para "
                         f"{', '.join(_MEASURED_ENTITIES)}.")
    if match_type and entity not in _TARGET_ENTITIES:
        raise ValueError("match_type es para keywords y product_targets.")
    if state and state not in STRUCTURE_STATES:
        raise ValueError(f"state tiene que ser uno de: {', '.join(STRUCTURE_STATES)}, o vacío para todos")
    wanted_text = target.strip()
    if wanted_text and entity not in _TEXT_COLUMNS:
        raise ValueError(f"target busca en {', '.join(_TEXT_COLUMNS)}: pedilo con uno de esos entity")
    if targets:
        if entity not in _TARGET_ENTITIES:
            raise ValueError("targets busca keywords o product_targets: pedilo con uno de esos entity.")
        if wanted_text or sort_by or row_filter.applied():
            raise ValueError("targets ya devuelve una fila por término: pedilo sin target, sort_by ni filters.")
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    profile = campaign_profile(rest, choice.profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    request = CampaignRequest.of(campaign, campaigns, "", portfolio)
    listing = ListingRequest(entity=entity, state=state, target=wanted_text, targets=tuple(targets or ()),
                             match=match, match_type=match_type, row_filter=row_filter, running_only=running_only,
                             sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit)
    context = {"window": window_payload(start, end), "currency": profile.currency_code}
    if window_note:
        context["window_note"] = window_note
    if product in ("SB", "SD"):
        return _sb_sd_structure(rest, profile, start, end, product, request, listing, context)
    return _sp_structure(rest, profile, start, end, request, listing, context)


@dataclass(frozen=True)
class ListingRequest:
    """What a structure call asks for of the rows, once its account and window are known."""

    entity: str
    state: str
    target: str
    targets: tuple[str, ...]
    match: str
    match_type: str
    row_filter: RowFilter
    running_only: bool
    sort_by: str
    sort_order: str
    offset: int
    limit: int


def _sp_structure(rest, profile: ProfileOption, start: date, end: date, request: CampaignRequest,
                  listing: ListingRequest, context: dict) -> dict:
    entity, families = listing.entity, STRUCTURE_ENTITIES[listing.entity]
    context.update(attribution_days=_attribution_days(profile.account_type), source=STRUCTURE_SOURCE)
    provider = StructureProvider(rest)
    campaign_ids: tuple[str, ...] = ()
    if request.applied():
        campaigns = provider.sp_structure(profile, start, end, entities=(CAMPAIGN,))
        if campaigns is None:
            return _structure_not_synced(context)
        selection = select_campaigns(_campaign_catalog(campaigns.rows), request)
        context.update(selection.payload())
        if not selection.ids:
            if "campaigns" not in _listed_entities(rest, profile.profile_id, campaigns.listed_at):
                return _no_structure_rows(context, f"Todavía no se sincronizaron {_STRUCTURE_WHAT['campaigns']} "
                                                   "de esta cuenta.")
            # No counts: an empty one would read as nothing synced, and there are no campaigns to count in.
            return _no_structure_rows(
                {**context, "listed_at": _structure_listing_times(campaigns.listed_at, profile)},
                _no_campaign_note(request))
        campaign_ids = tuple(row["campaign_id"] for row in selection.matched)

    counted = provider.sp_structure_counts(profile, start, end, campaign_ids=campaign_ids)
    listed = _listed_entities(rest, profile.profile_id, counted.rows) if counted is not None else set()
    if not listed:
        return _structure_not_synced(context)
    if "campaigns" in listed and _placements_known(counted.rows):
        listed.add("placements")
    counts = {name: sum(counted.rows.get(family, 0) for family in STRUCTURE_ENTITIES[name])
              for name in STRUCTURE_ENTITIES if name in listed}
    context.update(counts=counts, listed_at=_structure_listing_times(counted.listed_at, profile))

    what = _STRUCTURE_WHAT[entity]
    asked = _campaigns_phrase(request)
    if entity not in listed:
        return _no_structure_rows(context, f"Todavía no se sincronizaron {what} "
                                           f"{f'de {asked}' if asked else 'de esta cuenta'}.")
    if not counts[entity]:
        none = (f"{asked[0].upper()}{asked[1:]} no tienen {what}" if asked
                else f"La cuenta no tiene {what} de Sponsored Products")
        return _no_structure_rows(context, f"{none} en el último listado.")
    if entity == "negatives" and counts[entity] > MAX_ACCOUNT_NEGATIVES and len(campaign_ids) != 1:
        return {"rows": [], **context, "note": _too_many_negatives(counts[entity], asked, len(campaign_ids))}

    structure = provider.sp_structure(profile, start, end, entities=_STRUCTURE_READS[entity],
                                      campaign_ids=campaign_ids)
    scope = structure.rows
    wanted = scope[scope["entity"].isin(families)]
    if listing.state:
        wanted = wanted[wanted["state"].str.upper() == listing.state.upper()]
    if listing.target:
        contains, exact = _text_matches(wanted, _TEXT_COLUMNS[entity], listing.target)
        # Exact rows first, so the first page answers "does the account have it".
        wanted = wanted.loc[(~exact[contains]).sort_values(kind="stable").index]
        if wanted.empty:
            return _no_structure_rows(context, f"Ninguno de los {what} {f'de {asked}' if asked else 'de la cuenta'} "
                                               f"contiene «{listing.target}» en el último listado.")
        context["exact_matches"] = int(exact.sum())
    placements = _campaign_placements(scope) if entity == "campaigns" else {}
    campaign_states = _campaign_states(scope) if entity in _CAMPAIGN_CHILDREN else {}
    shares = (provider.target_top_of_search(profile, start, end, "SP") or {}) if entity in _TARGET_ENTITIES else {}
    sales_field, orders_field = _ATTRIBUTION_FIELDS[structure.attribution_days]
    rows = []
    for record in wanted.to_dict("records"):
        row = _STRUCTURE_ROWS[entity](record)
        if entity == "campaigns":
            row.update(placements.get(record["campaign_id"], dict.fromkeys(_PLACEMENT_KEYS.values())))
        if entity in _CAMPAIGN_CHILDREN:
            row["campaign_state"] = campaign_states.get(record["campaign_id"], "")
        if record["metrics_known"]:
            row.update(_metrics(record["cost"], record[sales_field], record[orders_field], record["clicks"],
                                record["impressions"]))
        if entity in _TARGET_ENTITIES:
            _add_target_figures(row, shares.get(record["entity_id"]))
        rows.append(row)
    payload, kept = _listed_page(rows, listing, what, context)
    if entity == "product_ads":
        payload["distinct"] = {"asins": len({row["asin"] for row in kept if row["asin"]}),
                               "skus": len({row["sku"] for row in kept if row["sku"]})}
        payload["distinct_note"] = DISTINCT_ADS_NOTE
    if entity in _MEASURED_ENTITIES and not wanted["metrics_known"].all():
        payload["metrics_note"] = ("Todavía no hay reportes de esta ventana para estas filas: van sin métricas, que no "
                                   "se conocen (no son cero).")
    return payload


def _sb_sd_structure(rest, profile: ProfileOption, start: date, end: date, product: str, request: CampaignRequest,
                     listing: ListingRequest, context: dict) -> dict:
    """The keywords or product targets of the SB or SD campaigns, with their campaign's state and the window."""
    context.update(attribution_days=14, source=SB_SD_SOURCE.format(
        product="Sponsored Brands" if product == "SB" else "Sponsored Display"))
    targets = StructureProvider(rest).sb_sd_targets(profile, start, end, product)
    what = _STRUCTURE_WHAT[listing.entity]
    if targets is None:
        return _no_structure_rows(context, "La base todavía no tiene la lectura de keywords y targets de SB y SD "
                                           "(migración 019).")
    if targets.empty:
        return _no_structure_rows({**context, "counts": {}}, f"La cuenta no tiene keywords ni targets de {product} en "
                                                             "el último listado, o todavía no se sincronizaron.")
    if request.applied():
        catalog = pd.DataFrame({"product": product, "campaign_id": targets["campaign_id"],
                                "campaign": targets["campaign_name"], "state": targets["campaign_state"],
                                "portfolio": "", "daily_budget": float("nan")}).drop_duplicates("campaign_id")
        selection = select_campaigns(catalog, request)
        context.update(selection.payload())
        targets = targets[targets["campaign_id"].isin(selection.ids)]
    counts = {entity: int(targets["entity"].eq(family).sum()) for entity, family in _SB_SD_ENTITIES.items()}
    listed_at = _account_time(targets["listed_at"].max().to_pydatetime(), profile) if len(targets) else None
    context.update(counts=counts, listed_at=dict.fromkeys(_SB_SD_ENTITIES, listed_at) if listed_at else {})
    wanted = targets[targets["entity"].eq(_SB_SD_ENTITIES[listing.entity])]
    if listing.state:
        wanted = wanted[wanted["state"].str.upper() == listing.state.upper()]
    if listing.target:
        contains, exact = _text_matches(wanted, ("target_text",), listing.target)
        wanted = wanted.loc[(~exact[contains]).sort_values(kind="stable").index]
        context["exact_matches"] = int(exact.sum())
    if wanted.empty:
        return _no_structure_rows(context, f"No hay {what} de {product} que coincidan con lo pedido.")
    rows = []
    for record in wanted.to_dict("records"):
        row = {**_structure_target_row(record), "campaign_state": record["campaign_state"],
               "cost_type": record["cost_type"]}
        if record["metrics_known"]:
            row.update(_metrics(record["cost"], record["sales"], record["purchases"], record["clicks"],
                                record["impressions"]),
                       sales_clicks=_plain_number(record["sales_clicks"]),
                       orders_clicks=_plain_number(record["purchases_clicks"]))
        _add_target_figures(row, _plain_number(record["top_of_search_share"]),
                            bid_per_click=str(record["cost_type"]).upper() == CPC_COST_TYPE)
        rows.append(row)
    payload, _ = _listed_page(rows, listing, what, context)
    if not wanted["metrics_known"].all():
        payload["metrics_note"] = ("Todavía no hay reportes de targeting de esta ventana para estas filas: van sin "
                                   "métricas, que no se conocen (no son cero).")
    return payload


def _listed_page(rows: list[dict], listing: ListingRequest, what: str, context: dict) -> tuple[dict, list[dict]]:
    """(payload, the rows it kept): the rows looked up term by term, or filtered and ordered, and one page."""
    if listing.match_type:
        rows = [row for row in rows if _row_match_type(row) == listing.match_type]
    if listing.targets:
        looked_up = lookup_terms(rows, list(listing.targets), listing.match)
        payload = page(looked_up, offset=listing.offset, limit=listing.limit).as_payload(what="términos")
        payload.update(context, lookup_counts={"terms": len(looked_up),
                                               "found": sum(1 for row in looked_up if row["found"]),
                                               "running": sum(1 for row in looked_up if row.get("running"))},
                       lookup_note=LOOKUP_NOTE)
        return payload, rows
    if listing.running_only:
        rows = [row for row in rows if _runs(row)]
    rows = [row for row in rows if listing.row_filter.keeps(row)]
    if listing.sort_by:
        rows = sort_rows(with_sort_figure(rows, listing.sort_by), listing.sort_by, listing.sort_order)
    payload = page(rows, offset=listing.offset, limit=listing.limit).as_payload(what=what)
    payload.update(context, **listing.row_filter.described())
    if listing.running_only:
        payload["running_only"] = True
    if listing.entity in _TARGET_ENTITIES:
        payload["target_figures_note"] = TARGET_FIGURES_NOTE
    return payload, rows


def _add_target_figures(row: dict, top_of_search_share, *, bid_per_click: bool = True) -> None:
    """A keyword's or target's bid against what its clicks cost, and its top-of-search share; only a bid per click
    has a gap with a cost per click."""
    cpc = row.get("cpc")
    measurable = bid_per_click and cpc is not None and row.get("bid") is not None
    row["bid_gap"] = round(row["bid"] - cpc, 2) if measurable else None
    row["top_of_search_share"] = top_of_search_share


def _row_match_type(row: dict) -> str:
    """exact, phrase or broad for a keyword; asin or category for a product target, from its expression."""
    match_type = str(row.get("match_type") or "").lower()
    if match_type in ("exact", "phrase", "broad"):
        return match_type
    predicate = str(row.get("target") or "").split("=", 1)[0].strip().lower()
    return _EXPRESSION_KINDS.get(predicate, "")


def _runs(row: dict) -> bool:
    return str(row.get("state", "")).upper() == "ENABLED" and str(
        row.get("campaign_state", "ENABLED")).upper() == "ENABLED"


def _campaign_catalog(campaign_rows: pd.DataFrame) -> pd.DataFrame:
    """The listed SP campaigns in the columns the campaign selector reads."""
    return pd.DataFrame({
        "product": "SP", "campaign_id": campaign_rows["campaign_id"],
        "campaign": campaign_rows["campaign_name"].fillna("").astype(str).str.strip(),
        "state": campaign_rows["state"].fillna("").astype(str).str.upper(),
        "portfolio": [_portfolio_label(portfolio_id, name) for portfolio_id, name
                      in zip(campaign_rows["portfolio_id"], campaign_rows["portfolio_name"])],
        "daily_budget": campaign_rows["budget_amount"]})


def exact_keywords(rest, profile_id: str, start: date, end: date) -> dict[str, dict]:
    """Each term the account targets exactly, lowercased: a keyword in exact match, or an ASIN as an `asin="…"`
    product target. For each, the campaigns where it runs (it and its campaign enabled) and how many of its targets
    do not run. Empty when the structure was never listed."""
    entities = (CAMPAIGN, *STRUCTURE_ENTITIES["keywords"], *STRUCTURE_ENTITIES["product_targets"])
    structure = StructureProvider(rest).sp_structure(campaign_profile(rest, profile_id), start, end,
                                                     entities=entities)
    if structure is None:
        return {}
    scope = structure.rows
    campaign_states = _campaign_states(scope)
    targets = scope[scope["entity"].isin((*STRUCTURE_ENTITIES["keywords"], *STRUCTURE_ENTITIES["product_targets"]))]
    found: dict[str, dict] = {}
    for record in targets.to_dict("records"):
        term = _exact_term(record)
        if not term:
            continue
        entry = found.setdefault(term, {"running_in": [], "not_running": 0})
        runs = (str(record["state"]).upper() == "ENABLED"
                and str(campaign_states.get(record["campaign_id"], "")).upper() == "ENABLED")
        if runs:
            entry["running_in"].append(record["campaign_name"])
        else:
            entry["not_running"] += 1
    return found


def _exact_term(record: dict) -> str:
    """The lowercased term an exact keyword or an `asin="…"` product target aims at; empty for any other target."""
    text = str(record["target_text"]).strip()
    if record["entity"] in STRUCTURE_ENTITIES["product_targets"]:
        exact_asin = text.startswith(ASIN_TARGET_PREFIX) and text.endswith('"')
        return text[len(ASIN_TARGET_PREFIX):-1].casefold() if exact_asin else ""
    return text.casefold() if str(record["match_type"]).upper() == "EXACT" else ""


def _too_many_negatives(total: int, asked: str, campaigns: int) -> str:
    """Why negatives wider than one campaign come back only counted, and how to ask for fewer."""
    if not campaigns:
        return (f"La cuenta tiene {total} negativos: son demasiados para traerlos todos. Pedí los de una campaña con "
                "campaign (parte de su nombre o su id).")
    return (f"Las {campaigns} {asked.removeprefix('las ')} tienen {total} negativos: son demasiados para traerlos "
            "todos. Pedí los de una sola campaña con campaign (más de su nombre, o su id).")


def _campaigns_phrase(request: CampaignRequest) -> str:
    """How a note names the campaigns asked for: by the text asked, or as the ones asked for."""
    if not request.applied():
        return ""
    if request.campaign and not (request.campaigns or request.portfolio):
        return f"las campañas con «{request.campaign}»"
    return "las campañas pedidas"


def _no_campaign_note(request: CampaignRequest) -> str:
    if request.campaign and not (request.campaigns or request.portfolio):
        return (f"Ninguna campaña de Sponsored Products de la cuenta tiene «{request.campaign}» en el nombre ni ese "
                "id.")
    return ("Ninguna campaña de Sponsored Products de la cuenta coincide con lo pedido (campaign, campaigns o "
            "portfolio).")


def _structure_not_synced(context: dict) -> dict:
    return _no_structure_rows({**context, "counts": {}, "listed_at": {}},
                              "La estructura de las campañas de esta cuenta todavía no se sincronizó.")


def _no_structure_rows(context: dict, note: str) -> dict:
    return {"rows": [], "total": 0, "showing": 0, "offset": 0, **context, "note": note}


def _text_matches(rows, columns: tuple[str, ...], text: str):
    """(contains, exact): the rows with `text` in any of `columns`, whatever the case, and those that are exactly it."""
    needle = text.casefold()
    values = [rows[column].fillna("").astype(str).str.casefold() for column in columns]
    contains = values[0].str.contains(needle, regex=False)
    exact = values[0].eq(needle)
    for value in values[1:]:
        contains |= value.str.contains(needle, regex=False)
        exact |= value.eq(needle)
    return contains, exact


def _listed_entities(rest, profile_id: str, families) -> set[str]:
    """The entities Amazon Ads listed for the account: those whose families were counted, and those whose listing
    job completed empty."""
    listed = {_ENTITY_OF_FAMILY[family] for family in families} - {"placements"}
    store = SyncJobStore(rest)
    for kind in dict.fromkeys(kind for entity, kind in _LISTING_KINDS.items() if entity not in listed):
        job = store.latest_completed_for_profile(profile_id, kind)
        # A listing Amazon refused also completes, with no rows and the refusal as its warning.
        if job is not None and not job.warning:
            listed.update(entity for entity, listing in _LISTING_KINDS.items() if listing == kind)
    return listed


def _placements_known(families) -> bool:
    """Whether the campaigns in scope carry their placement adjustments: one listed without them has them unknown."""
    return BIDDING_ADJUSTMENT in families or CAMPAIGN not in families


def _structure_listing_times(listed_at: dict, profile: ProfileOption) -> dict:
    """When each entity the chat asks for was last listed, on the account's clock."""
    latest = {}
    for family, moment in listed_at.items():
        entity = _ENTITY_OF_FAMILY[family]
        latest[entity] = max(moment, latest.get(entity, moment))
    return {entity: _account_time(latest[entity], profile) for entity in STRUCTURE_ENTITIES if entity in latest}


def _campaign_states(scope) -> dict:
    """Campaign id -> the state its campaign was listed in."""
    campaigns = scope[scope["entity"].eq(CAMPAIGN)]
    return dict(zip(campaigns["campaign_id"], campaigns["state"]))


def _campaign_placements(scope) -> dict:
    """Campaign id -> its four placement percentages; a campaign without them has them unknown."""
    placements = {}
    for record in scope[scope["entity"].eq(BIDDING_ADJUSTMENT)].to_dict("records"):
        adjustments = placements.setdefault(record["campaign_id"], dict.fromkeys(_PLACEMENT_KEYS.values()))
        adjustments[_PLACEMENT_KEYS[record["placement"]]] = _plain_number(record["percentage"])
    return placements


def _structure_campaign_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "portfolio": _portfolio_label(record["portfolio_id"], record["portfolio_name"]),
            "state": record["state"], "targeting_type": record["targeting_type"],
            "budget": _plain_number(record["budget_amount"]), "budget_type": record["budget_type"],
            "bid_strategy": BID_STRATEGY_LABELS.get(record["bidding_strategy"], record["bidding_strategy"])}


def _structure_placement_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"], "state": record["state"],
            "bid_strategy": BID_STRATEGY_LABELS.get(record["bidding_strategy"], record["bidding_strategy"]),
            "placement": _PLACEMENT_LABELS.get(record["placement"], record["placement"]),
            "percentage": _plain_number(record["percentage"])}


def _structure_ad_group_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"], "state": record["state"],
            "default_bid": _plain_number(record["default_bid"])}


def _structure_target_row(record: dict) -> dict:
    own_bid, default_bid = _plain_number(record["own_bid"]), _plain_number(record["default_bid"])
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"],
            "target": record["target_text"], "target_id": record["entity_id"],
            "kind": TARGET_KIND_LABELS.get(record["target_kind"], record["target_kind"]),
            "match_type": record["match_type"], "state": record["state"], "bid": _plain_number(record["bid"]),
            "own_bid": own_bid, "default_bid": default_bid,
            "bid_source": "own" if own_bid is not None else "ad_group_default" if default_bid is not None else ""}


def _structure_product_ad_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"], "asin": record["asin"],
            "sku": record["sku"], "state": record["state"], "ad_id": record["entity_id"]}


def _structure_negative_row(record: dict) -> dict:
    return {"campaign": record["campaign_name"], "campaign_id": record["campaign_id"],
            "ad_group": record["ad_group_name"], "ad_group_id": record["ad_group_id"],
            "level": "campaign" if record["entity"] in _CAMPAIGN_NEGATIVES else "ad_group",
            "kind": TARGET_KIND_LABELS.get(record["target_kind"], record["target_kind"]),
            "negative": record["target_text"], "match_type": record["match_type"], "state": record["state"],
            "negative_id": record["entity_id"]}


_STRUCTURE_ROWS = {
    "campaigns": _structure_campaign_row,
    "placements": _structure_placement_row,
    "ad_groups": _structure_ad_group_row,
    "keywords": _structure_target_row,
    "product_targets": _structure_target_row,
    "product_ads": _structure_product_ad_row,
    "negatives": _structure_negative_row,
}
