"""Amazon Ads in the moment, one account per call: what Amazon computes right now and the app does not keep.

Budget recommendations and usage, product stock and eligibility, the change history, suggested bids with each
keyword's impression share, the Sponsored Brands category benchmark, invoices and the brand store, read through
core/amazon_ads/live_reads.py. Each tool takes the account like the rest (profile_id, or part of its name), adds the
names the app already keeps and pages its rows. When Amazon fails the whole answer the tool raises a ValueError the
model reads; when only one part fails, `errors` says which, next to what did answer.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import partial
from typing import Literal

from core.amazon_ads import live_reads
from core.amazon_ads.campaign_catalog import campaign_catalog
from core.amazon_ads.campaign_totals import window_totals
from core.amazon_ads.live_reads import PRODUCTS, LiveAccount, LiveReadError
from core.amazon_ads.report_provider import PROFILE_SYNC_TABLE, ReportReadError
from services.mcp_server.limits import page, rows_within_chars
from services.mcp_server.tools.account_resolver import campaign_profile, choose_account
from services.mcp_server.tools.campaign_selector import CampaignRequest, no_match_note, select_campaigns
from services.mcp_server.tools.windows import DEFAULT_DAYS, window_for

LiveProduct = Literal["", "SP", "SB", "SD"]
HistoryEntity = Literal["", "campaign", "ad_group", "keyword", "product_target", "negative_keyword", "ad"]
HistoryChange = Literal["", "BID_AMOUNT", "BUDGET_AMOUNT", "STATUS", "IN_BUDGET", "PLACEMENT_GROUP",
                        "SMART_BIDDING_STRATEGY", "NAME", "START_DATE", "END_DATE"]
StoreMetric = Literal["VISITS", "VISITORS", "VIEWS", "SALES", "ORDERS", "UNITS", "NEW_TO_STORE", "BOUNCE_RATE",
                      "DWELL_TIME"]
StoreDimension = Literal["DATE", "PAGE", "SOURCE"]

SOURCE = "Amazon Ads, en vivo"
MAX_PRODUCTS = 600
MAX_BUDGET_CAMPAIGNS = 400
MAX_KEYWORD_IDEAS = 20
HISTORY_PAGE = 50
_PARALLEL = 6
_HISTORY_ENTITIES = {"campaign": "CAMPAIGN", "ad_group": "AD_GROUP", "keyword": "KEYWORD",
                     "product_target": "PRODUCT_TARGETING", "negative_keyword": "NEGATIVE_KEYWORD", "ad": "AD"}
BUDGET_NOTE = ("time_in_budget_pct es el % del tiempo de los últimos 7 días en que la campaña tuvo presupuesto (100 = "
               "nunca se quedó sin). missed_sales, missed_clicks y missed_impressions son lo que Amazon estima que se "
               "perdió por falta de presupuesto en esos 7 días, como rango [bajo, alto], en la moneda de la cuenta. "
               "usage_pct_now es cuánto del presupuesto de hoy lleva gastado en este momento: puede pasar de 100.")
BENCHMARK_NOTE = ("Cada fila es una marca de la cuenta en una categoría: brand es su cifra y median, top_25 y bottom_25 "
                  "los de las marcas de esa categoría en Sponsored Brands, como los da Amazon. acos y ctr en %, roas en "
                  "veces, impressions en cantidad.")


def available() -> bool:
    """Whether this server can open the accounts' Amazon Ads tokens; without them these tools are not offered."""
    return live_reads.configured()


def live_budget(rest, *, profile_id: str = "", account: str = "", product: LiveProduct = "", campaign: str = "",
                portfolio: str = "", only_limited: bool = False, offset: int = 0) -> dict:
    """Amazon's budget recommendation and today's budget usage of every enabled campaign of one account."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    catalog = _catalog(rest, live)
    enabled = catalog[catalog["state"].eq("ENABLED")]
    if product:
        enabled = enabled[enabled["product"].eq(product)]
    request = CampaignRequest.of(campaign=campaign, portfolio=portfolio)
    selection = select_campaigns(enabled, request) if request.applied() else None
    chosen = enabled[enabled["campaign_id"].isin(selection.ids)] if selection else enabled
    scope_note = ""
    if not selection:
        chosen, scope_note = _spending_campaigns(rest, live, chosen)
    if chosen.empty:
        note = no_match_note(request) if selection else (
            scope_note or "La cuenta no tiene campañas habilitadas de ese producto.")
        return {**_head(live), "rows": [], "total": 0, "showing": 0, "offset": 0, "note": note}

    api = live_reads.client_for(live)
    tasks: dict[str, Callable] = {}
    chunk_ids: dict[str, list[str]] = {}
    for code in PRODUCTS:
        ids = list(chosen.loc[chosen["product"].eq(code), "campaign_id"])
        # One task per batch of 100: a big account answers in the time of its slowest batch, not their sum.
        for number, chunk in enumerate(_chunks(ids, 100)):
            chunk_ids[f"recomendaciones {code} {number}"] = chunk
            tasks[f"recomendaciones {code} {number}"] = partial(live_reads.budget_recommendations, api, live, code,
                                                                chunk)
            tasks[f"uso {code} {number}"] = partial(live_reads.budget_usage, api, live, code, chunk)
        if ids:
            tasks[f"reglas {code}"] = partial(live_reads.budget_rules, api, live, code)
    portfolio_names = {} if selection else _portfolio_names(rest, live)
    if portfolio_names:
        tasks["uso portfolios"] = partial(live_reads.budget_usage, api, live, "PORTFOLIO", list(portfolio_names)[:100])
    results, errors = _run_all(tasks)
    unknown = {campaign_id for error in errors for campaign_id in chunk_ids.get(error["part"], [])}
    results = _merged_chunks(results)

    rows = [_budget_row(record, results, unknown) for record in chosen.to_dict("records")]
    limited = [row for row in rows if _is_limited(row)]
    shown = sorted(limited if only_limited else rows, key=_budget_order, reverse=True)
    payload = {**_head(live), **page(shown, offset=offset).as_payload(what="campañas")}
    rules = [rule for code in PRODUCTS for rule in results.get(f"reglas {code}") or []]
    payload["counts"] = {
        "campaigns": len(rows),
        "limited_last_7_days": sum(1 for row in rows if (row.get("time_in_budget_pct") or 100) < 100),
        "at_or_over_budget_now": sum(1 for row in rows if (row.get("usage_pct_now") or 0) >= 100),
        "without_recommendation": sum(1 for row in rows if row.get("recommendation") == "sin recomendación"),
        "budget_rules_active": sum(1 for rule in rules if rule.get("state") == "ACTIVE"),
    }
    payload["totals"] = {name: _summed_range(rows, name) for name in ("missed_sales", "missed_clicks",
                                                                      "missed_impressions")}
    if rules:
        payload["budget_rules"] = rules[:30]
    if "uso portfolios" in results:
        payload["portfolios"] = [{"portfolio": portfolio_names.get(portfolio_id) or portfolio_id,
                                  "portfolio_id": portfolio_id, **usage}
                                 for portfolio_id, usage in results["uso portfolios"].items()]
    if selection:
        payload.update(selection.payload())
    if scope_note:
        payload["scope"] = scope_note
    if errors:
        payload["errors"] = errors
    payload["notes"] = BUDGET_NOTE
    return payload


def live_products(rest, *, profile_id: str = "", account: str = "", asins: list[str] | None = None,
                  only_problems: bool = False, offset: int = 0) -> dict:
    """Stock, price, best seller rank and ad eligibility of an account's advertised ASINs, or of the ones asked."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    wanted = sorted({asin.strip().upper() for asin in asins or [] if asin and asin.strip()})
    if not wanted:
        wanted = _advertised_asins(rest, live)
    if not wanted:
        return {**_head(live), "rows": [], "total": 0, "showing": 0, "offset": 0,
                "note": "La cuenta no tiene anuncios de Sponsored Products habilitados en su último listado."}
    checked = wanted[:MAX_PRODUCTS]
    api = live_reads.client_for(live)
    results, errors = _run_all({f"productos {number}": partial(live_reads.product_metadata, api, live, chunk)
                                for number, chunk in enumerate(_chunks(checked, 300))})
    products = [product for part in results.values() for product in part]
    problems = [product for product in products if _has_problem(product)]
    shown = sorted(problems if only_problems else products,
                   key=lambda product: (not _has_problem(product), product.get("availability") or "", product["asin"]))
    payload = {**_head(live), **page(shown, offset=offset).as_payload(what="productos")}
    payload["counts"] = {
        "asins_checked": len(checked),
        "with_problems": len(problems),
        "by_availability": _counted(product.get("availability") for product in products),
        "by_eligibility": _counted(product.get("eligibility") for product in products),
        "not_found": len(set(checked) - {product["asin"] for product in products}),
    }
    if len(wanted) > MAX_PRODUCTS:
        payload["asins_not_checked"] = len(wanted) - MAX_PRODUCTS
    if payload["counts"]["not_found"] and not errors:
        payload["not_found_note"] = ("Amazon no devolvió datos de algunos ASINs: suelen ser productos que ya no están "
                                     "en el catálogo de la cuenta en ese país.")
    if errors:
        payload["errors"] = errors
    return payload


def _advertised_asins(rest, live: LiveAccount) -> list[str]:
    """The ASINs of enabled product ads in enabled Sponsored Products campaigns, as last listed."""
    catalog = campaign_catalog(rest, live.profile_id)
    enabled = set() if catalog is None else set(
        catalog.loc[catalog["state"].eq("ENABLED") & catalog["product"].eq("SP"), "campaign_id"])
    rows = rest.select("ads_product_ad", {"select": "asin,campaign_id", "profile_id": f"eq.{live.profile_id}",
                                          "state": "eq.ENABLED", "asin": "neq."})
    return sorted({str(row.get("asin") or "").strip().upper() for row in rows
                   if str(row.get("campaign_id") or "") in enabled} - {""})


def live_change_history(rest, *, profile_id: str = "", account: str = "", days: int = 7,
                        entity: HistoryEntity = "", change: HistoryChange = "", campaign: str = "",
                        offset: int = 0) -> dict:
    """What changed in an account's campaigns, ad groups, keywords, targets and ads, newest first."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    catalog = _catalog(rest, live)
    campaign_ids: tuple[str, ...] = ()
    selection = None
    if campaign:
        selection = select_campaigns(catalog, CampaignRequest.of(campaign=campaign))
        if not selection.ids:
            return {**_head(live), "rows": [], "total": 0, "showing": 0, "offset": 0,
                    "note": no_match_note(CampaignRequest.of(campaign=campaign))}
        campaign_ids = tuple(sorted(selection.ids))[:10]
    entities = (_HISTORY_ENTITIES[entity],) if entity else live_reads.HISTORY_ENTITIES
    result = live_reads.change_history(live_reads.client_for(live), live, days=days, entities=entities,
                                       change=change, campaign_ids=campaign_ids, offset=offset, count=HISTORY_PAGE)
    names = dict(zip(catalog["campaign_id"], catalog["campaign"]))
    events = [_named_event(event, names) for event in result["events"]]
    kept = rows_within_chars(events)
    total = result["total"] if result["total"] is not None else len(events)
    payload = {**_head(live), "days": min(max(int(days), 1), live_reads.MAX_HISTORY_DAYS), "rows": kept,
               "total": total, "showing": len(kept), "offset": offset}
    if offset + len(kept) < total:
        payload["note"] = (f"Hay {total} cambios y esta respuesta trae {len(kept)}, desde la posición {offset}. Pedí "
                           f"la página siguiente con offset={offset + len(kept)} o acotá con entity, change o campaign.")
    if selection and len(selection.ids) > 10:
        payload["campaigns_note"] = "Amazon filtra hasta 10 campañas por consulta: se tomaron las primeras 10."
    if selection:
        payload.update(selection.payload())
    payload["notes"] = ("Amazon no dice quién hizo cada cambio y no guarda historial de Sponsored Display. before y "
                        "after son el valor anterior y el nuevo; total llega como mucho a 10.000.")
    return payload


def live_keyword_bids(rest, *, profile_id: str = "", account: str = "", campaign: str, ad_group: str = "",
                      offset: int = 0) -> dict:
    """Amazon's suggested bid for each target of one ad group, with the account's impression share and rank on each
    keyword and, in Sponsored Products, Amazon's keyword ideas."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    catalog = _catalog(rest, live)
    request = CampaignRequest.of(campaign=campaign)
    selection = select_campaigns(catalog, request)
    if not selection.ids:
        raise ValueError(no_match_note(request))
    if len(selection.ids) > 1:
        names = ", ".join(f"«{row['campaign']}»" for row in selection.matched[:10])
        raise ValueError(f"«{campaign}» coincide con {len(selection.ids)} campañas ({names}): nombrá una por su id o "
                         "su nombre exacto.")
    campaign_id = next(iter(selection.ids))
    product = str(catalog.loc[catalog["campaign_id"].eq(campaign_id), "product"].iloc[0])
    targets = rest.select("ads_target", {"select": "ad_group_id,target_kind,target_text,match_type,state,bid",
                                         "profile_id": f"eq.{live.profile_id}", "campaign_id": f"eq.{campaign_id}",
                                         "state": "ilike.enabled"})
    groups: dict[str, list[dict]] = {}
    for target in targets:
        groups.setdefault(str(target.get("ad_group_id") or ""), []).append(target)
    if ad_group:
        if ad_group not in groups:
            raise ValueError(f"El ad group {ad_group} no tiene targets habilitados en esa campaña. Sus ad groups con "
                             f"targets: {', '.join(sorted(groups)) or 'ninguno'}.")
        ad_group_id = ad_group
    elif groups:
        ad_group_id = max(groups, key=lambda group_id: len(groups[group_id]))
    else:
        raise ValueError("La campaña no tiene keywords ni targets habilitados en su último listado.")
    chosen = groups[ad_group_id]
    api = live_reads.client_for(live)
    if product == "SP":
        result = _sp_bids(rest, api, live, campaign_id, ad_group_id, chosen)
    elif product == "SB":
        result = _sb_bids(api, live, campaign_id, chosen)
    else:
        result = _sd_bids(rest, api, live, campaign_id, chosen)
    payload = {**_head(live), "campaign": selection.matched[0]["campaign"], "campaign_id": campaign_id,
               "product": product, "ad_group_id": ad_group_id,
               **page(result.pop("rows"), offset=offset).as_payload(what="targets")}
    if len(groups) > 1 and not ad_group:
        payload["other_ad_groups"] = sorted(group_id for group_id in groups if group_id != ad_group_id)
    payload.update(result)
    return payload


def live_category_benchmark(rest, *, profile_id: str = "", account: str = "", days: int = 30,
                            offset: int = 0) -> dict:
    """How each brand of an account does in Sponsored Brands against its category: ACoS, ROAS, CTR, impressions."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    span = min(max(int(days), 1), 89)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=span - 1)
    found = live_reads.sb_category_benchmarks(live_reads.client_for(live), live, start, end)
    rows = found["rows"]
    payload = {**_head(live), "window": {"from": start.isoformat(), "to": end.isoformat()},
               **page(rows, offset=offset).as_payload(what="marcas y categorías")}
    if not rows:
        payload["note"] = "Amazon no tiene benchmark de Sponsored Brands para las marcas de esta cuenta en esas fechas."
    if found["more"]:
        payload["more_in_amazon"] = (f"Amazon tiene más de {len(rows)} combinaciones de marca y categoría; acá van las "
                                     "primeras.")
    payload["notes"] = BENCHMARK_NOTE
    return payload


def live_invoices(rest, *, profile_id: str = "", account: str = "", count: int = 12, invoice_id: str = "",
                  offset: int = 0) -> dict:
    """An account's latest Amazon Ads invoices, or what one invoice charged per campaign."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    api = live_reads.client_for(live)
    if invoice_id.strip():
        detail = live_reads.invoice_detail(api, live, invoice_id.strip())
        payload = {**_head(live), "invoice": detail["invoice"],
                   **page(detail["lines"], offset=offset).as_payload(what="líneas de la factura")}
        payload["cost_by_program"] = _cost_by_program(detail["lines"])
        return payload
    invoices = live_reads.invoices(api, live, count)
    payload = {**_head(live), **page(invoices, offset=offset).as_payload(what="facturas")}
    payload["notes"] = ("La factura del mes en curso (ACCUMULATING) no tiene invoice_id hasta que Amazon la emite. "
                        "Con invoice_id, esta herramienta trae lo que cobró esa factura por campaña.")
    return payload


def live_store(rest, *, profile_id: str = "", account: str = "", metric: StoreMetric = "VISITS",
               dimension: StoreDimension = "DATE", days: int = 30, store: str = "") -> dict:
    """One metric of an account's brand store by day, page or traffic source."""
    live, candidates = _live_account(rest, profile_id, account)
    if candidates:
        return candidates
    api = live_reads.client_for(live)
    stores = live_reads.stores(api, live)
    if not stores:
        return {**_head(live), "rows": [], "total": 0, "showing": 0, "offset": 0,
                "note": "La cuenta no tiene Stores en Amazon."}
    wanted = store.strip().casefold()
    picked = next((item for item in stores if wanted and wanted in str(item.get("name") or "").casefold()), stores[0])
    if not picked.get("brand_entity_id"):
        raise ValueError("Amazon no devolvió la marca de esa Store, así que no se pueden leer sus métricas.")
    span = min(max(int(days), 1), 100)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=span - 1)
    rows = live_reads.store_insights(api, live, picked["brand_entity_id"], metric, dimension, start, end)
    payload = {**_head(live), "store": picked.get("name"), "stores": [item.get("name") for item in stores],
               "metric": metric, "dimension": dimension, "window": {"from": start.isoformat(), "to": end.isoformat()},
               **page(rows).as_payload(what="filas")}
    if not rows:
        payload["note"] = "Amazon no tiene datos de esa métrica para la Store en esas fechas."
    return payload


def _live_account(rest, profile_id: str, account: str) -> tuple[LiveAccount | None, dict | None]:
    """The account to read live, or the candidates payload when its name matched several."""
    choice = choose_account(rest, profile_id, account, days=DEFAULT_DAYS)
    if choice.candidates:
        return None, choice.as_payload()
    rows = rest.select(PROFILE_SYNC_TABLE, {
        "select": "profile_id,connection_id,region,country_code,currency_code,cliente,account_name",
        "profile_id": f"eq.{choice.profile_id}", "limit": "1"})
    if not rows:
        raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {choice.profile_id}.")
    row = rows[0]
    if not row.get("connection_id"):
        raise ValueError("Esta cuenta no tiene una autorización de Amazon Ads conectada: hay que conectarla en "
                         "Integraciones.")
    country = str(row.get("country_code") or "")
    name = str(row.get("cliente") or row.get("account_name") or row["profile_id"])
    return LiveAccount(profile_id=str(row["profile_id"]), connection_id=int(row["connection_id"]),
                       region=str(row.get("region") or "NA").upper(), country=country,
                       currency=str(row.get("currency_code") or ""),
                       label=f"{name} · {country}" if country else name), None


def _head(live: LiveAccount) -> dict:
    return {"account": live.label, "profile_id": live.profile_id, "currency": live.currency, "source": SOURCE,
            "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _catalog(rest, live: LiveAccount):
    catalog = campaign_catalog(rest, live.profile_id)
    if catalog is None or catalog.empty:
        raise ValueError("La cuenta todavía no tiene campañas listadas en la app: aparecen después de su primera "
                         "sincronización.")
    return catalog


def _run_all(tasks: dict[str, Callable]) -> tuple[dict, list[dict]]:
    """Independent reads at once. A part that fails goes to errors with its sentence; if every part fails, the
    first sentence is the answer."""
    results: dict = {}
    errors: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(_PARALLEL, max(len(tasks), 1))) as pool:
        futures = {name: pool.submit(task) for name, task in tasks.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except LiveReadError as exc:
                errors.append({"part": name, "error": str(exc)})
    if tasks and not results:
        raise LiveReadError(errors[0]["error"])
    return results, errors


def _spending_campaigns(rest, live: LiveAccount, chosen):
    """The enabled campaigns that spent in the account's last 7 synced days, most spent first: a campaign without
    spend cannot have run out of budget. When that spend cannot be read, all of them."""
    try:
        view = campaign_profile(rest, live.profile_id)
        start, end = window_for(view, 7)
        spent = window_totals(rest, view, start, end).groupby("campaign_id")["spend"].sum()
    except (ValueError, ReportReadError):
        return chosen, ""
    spend = chosen["campaign_id"].map(spent).fillna(0)
    active = chosen[spend > 0].assign(_spend=spend[spend > 0]).sort_values("_spend", ascending=False)
    active = active.drop(columns="_spend")
    note = (f"Se miran las {len(active)} campañas habilitadas que gastaron del {start.isoformat()} al "
            f"{end.isoformat()}, de {len(chosen)} habilitadas: una campaña sin gasto no puede quedarse sin presupuesto.")
    if len(active) > MAX_BUDGET_CAMPAIGNS:
        note += f" Van las {MAX_BUDGET_CAMPAIGNS} de más gasto; campaign o portfolio acotan el resto."
        active = active.head(MAX_BUDGET_CAMPAIGNS)
    return active, note


def _merged_chunks(results: dict) -> dict:
    """The answers of a read split in batches ("uso SP 0", "uso SP 1"…) joined under one name ("uso SP")."""
    merged: dict = {}
    for name, value in results.items():
        base, _, number = name.rpartition(" ")
        if number.isdigit() and isinstance(value, dict):
            merged.setdefault(base, {}).update(value)
        else:
            merged[name] = value
    return merged


def _chunks(items: list, size: int) -> list[list]:
    return [items[start:start + size] for start in range(0, len(items), size)]


def _budget_row(record: dict, results: dict, unknown: set[str]) -> dict:
    code, campaign_id = record["product"], record["campaign_id"]
    usage = (results.get(f"uso {code}") or {}).get(campaign_id) or {}
    recommendations = results.get(f"recomendaciones {code}")
    row = {"campaign": record["campaign"], "campaign_id": campaign_id, "product": code,
           "portfolio": record.get("portfolio") or None,
           "daily_budget": usage.get("budget") if usage.get("budget") is not None else _float(record["daily_budget"]),
           "usage_pct_now": usage.get("usage_pct"), "usage_at": usage.get("updated_at")}
    if recommendations is None or campaign_id in unknown:
        return row
    recommendation = recommendations.get(campaign_id)
    if recommendation:
        row.update(recommendation)
    else:
        row["recommendation"] = "sin recomendación"
    return row


def _is_limited(row: dict) -> bool:
    return (row.get("time_in_budget_pct") is not None and row["time_in_budget_pct"] < 100) \
        or (row.get("usage_pct_now") or 0) >= 100


def _budget_order(row: dict) -> tuple:
    missed = row.get("missed_sales") or [None, None]
    return (missed[1] or 0, row.get("usage_pct_now") or 0)


def _summed_range(rows: list[dict], name: str) -> list | None:
    ranges = [row[name] for row in rows if row.get(name)]
    if not ranges:
        return None
    return [round(sum(low or 0 for low, _ in ranges), 2), round(sum(high or 0 for _, high in ranges), 2)]


def _portfolio_names(rest, live: LiveAccount) -> dict[str, str]:
    rows = rest.select("ads_portfolios", {"select": "portfolio_id,name,state", "profile_id": f"eq.{live.profile_id}"})
    return {str(row["portfolio_id"]): row.get("name") or "" for row in rows
            if str(row.get("state") or "").upper() == "ENABLED" and row.get("portfolio_id")}


def _has_problem(product: dict) -> bool:
    return product.get("availability") not in (None, "IN_STOCK") or product.get("eligibility") not in (None, "ELIGIBLE")


def _counted(values) -> dict:
    counts: dict = {}
    for value in values:
        key = value or "sin dato"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def _named_event(event: dict, names: dict) -> dict:
    campaign_id = str(event["detail"].get("campaignId") or (event["entity_id"] if event["entity"] == "CAMPAIGN" else ""))
    named = {**event}
    if campaign_id:
        named["campaign"] = names.get(campaign_id)
        named["campaign_id"] = campaign_id
    return named


def _sp_bids(rest, api, live: LiveAccount, campaign_id: str, ad_group_id: str, targets: list[dict]) -> dict:
    defaults = rest.select("ads_ad_group", {"select": "ad_group_id,default_bid", "profile_id": f"eq.{live.profile_id}",
                                            "ad_group_id": f"eq.{ad_group_id}", "limit": "1"})
    default_bid = _float((defaults or [{}])[0].get("default_bid"))
    keywords = [{"text": target["target_text"], "match": str(target.get("match_type") or "").upper(),
                 "bid": _float(target.get("bid")) or default_bid}
                for target in targets if target.get("target_kind") == "keyword"]
    others = [(target, live_reads.sp_target_expression(target.get("target_kind") or "", target.get("target_text") or ""))
              for target in targets if target.get("target_kind") != "keyword"]
    priced = [(target, expression) for target, expression in others if expression]
    tasks: dict[str, Callable] = {}
    if keywords:
        tasks["keywords"] = partial(live_reads.remembered, ("sp keywords", live.profile_id, ad_group_id),
                                    partial(live_reads.sp_keyword_recommendations, api, live, campaign_id, ad_group_id,
                                            keywords))
    if priced:
        tasks["targets"] = partial(live_reads.remembered, ("sp bids", live.profile_id, ad_group_id),
                                   partial(live_reads.sp_bid_recommendations, api, live, campaign_id, ad_group_id,
                                           [expression for _, expression in priced]))
    results, errors = _run_all(tasks)
    rows, fetched = [], []
    ideas = []
    if "keywords" in results:
        found, fetched_at = results["keywords"]
        fetched.append(fetched_at)
        by_keyword = {str(item["keyword"] or "").casefold(): item for item in found}
        for keyword in keywords:
            item = by_keyword.get(keyword["text"].casefold()) or {}
            rows.append({"target": keyword["text"], "kind": "keyword", "match": keyword["match"],
                         "bid": keyword["bid"], "suggested": (item.get("suggested_bids") or {}).get(keyword["match"]),
                         "impression_share_pct": item.get("impression_share_pct"),
                         "impression_rank": item.get("impression_rank")})
        ideas = sorted((item for item in found if not item["targeted"]),
                       key=lambda item: (item["impression_rank"] is None, item["impression_rank"] or 0))
    if "targets" in results:
        found, fetched_at = results["targets"]
        fetched.append(fetched_at)
        by_expression = {(item["type"], item.get("value")): item for item in found}
        for target, expression in priced:
            item = by_expression.get((expression["type"], expression.get("value"))) or {}
            rows.append({"target": target.get("target_text"), "kind": target.get("target_kind"),
                         "bid": _float(target.get("bid")) or default_bid,
                         "suggested": {key: item.get(key) for key in ("low", "suggested", "high")} if item else None})
    extra = {"keyword_ideas": ideas[:MAX_KEYWORD_IDEAS]} if ideas else {}
    skipped = [target.get("target_text") for target, expression in others if not expression]
    if skipped:
        extra["not_priced"] = {"count": len(skipped), "examples": skipped[:5],
                               "why": "Amazon no da bid sugerido para este tipo de target."}
    return {"rows": rows, **extra, **_freshness(fetched), **({"errors": errors} if errors else {}),
            "notes": ("impression_share_pct y impression_rank son de la cuenta en ese término, en los últimos 30 "
                      "días. suggested es el rango bajo, medio y alto que Amazon sugiere, en la moneda de la cuenta. "
                      "Amazon limita mucho estas consultas: lo pedido se reusa hasta 6 horas.")}


def _sb_bids(api, live: LiveAccount, campaign_id: str, targets: list[dict]) -> dict:
    keywords = [{"text": target["target_text"], "match": str(target.get("match_type") or "").upper(),
                 "bid": _float(target.get("bid"))} for target in targets if target.get("target_kind") == "keyword"]
    if not keywords:
        return {"rows": [], "note": "En Sponsored Brands Amazon sugiere bid y share sólo para keywords, y este ad "
                                    "group no tiene."}
    results, errors = _run_all({
        "share": partial(live_reads.sb_keyword_insights, api, live, keywords),
        "bids": partial(live_reads.sb_keyword_bids, api, live, campaign_id, keywords),
    })
    share = {(str(item["keyword"] or "").casefold(), str(item["match"] or "").upper()): item
             for item in results.get("share") or []}
    bids = {(str(item["keyword"] or "").casefold(), item["match"]): item for item in results.get("bids") or []}
    rows = []
    for keyword in keywords:
        key = (keyword["text"].casefold(), keyword["match"])
        found_share, found_bid = share.get(key) or {}, bids.get(key) or {}
        rows.append({"target": keyword["text"], "kind": "keyword", "match": keyword["match"], "bid": keyword["bid"],
                     "suggested": {name: found_bid.get(name) for name in ("low", "suggested", "high")}
                     if found_bid else None,
                     "impression_share_pct": found_share.get("impression_share_pct"),
                     "impression_rank": found_share.get("impression_rank"),
                     "alerts": found_share.get("alerts") or []})
    return {"rows": rows, **({"errors": errors} if errors else {}),
            "notes": ("impression_share_pct y impression_rank son de la cuenta en ese término, en los últimos 7 días, "
                      "y sólo existen para keywords que tuvieron impresiones.")}


def _sd_bids(rest, api, live: LiveAccount, campaign_id: str, targets: list[dict]) -> dict:
    campaign = rest.select("ads_sb_sd_campaign", {"select": "cost_type", "profile_id": f"eq.{live.profile_id}",
                                                  "campaign_id": f"eq.{campaign_id}", "limit": "1"})
    cost_type = str((campaign or [{}])[0].get("cost_type") or "CPC")
    paired = [(target, live_reads.sd_target_expression(target.get("target_text") or "")) for target in targets]
    priced = [(target, expression) for target, expression in paired if expression]
    found = live_reads.sd_target_bids(api, live, [expression for _, expression in priced], cost_type) if priced else []
    rows = []
    for (target, _), item in zip(priced, found):
        rows.append({"target": target.get("target_text"), "kind": target.get("target_kind"),
                     "bid": _float(target.get("bid")),
                     "suggested": {key: item.get(key) for key in ("low", "suggested", "high")},
                     **({"note": item["note"]} if item.get("note") else {})})
    skipped = [target.get("target_text") for target, expression in paired if not expression]
    extra = {"not_priced": {"count": len(skipped), "examples": skipped[:5],
                            "why": "Amazon sugiere bid de Display sólo para targets de producto y de categoría."}} \
        if skipped else {}
    return {"rows": rows, "cost_type": cost_type, **extra,
            "notes": ("suggested sale de las pujas ganadoras de los últimos 7 días; en campañas VCPM es por mil "
                      "impresiones visibles.")}


def _freshness(fetched: list[float]) -> dict:
    """When reused results were fetched, so a cached answer never passes as new."""
    oldest = min(fetched) if fetched else None
    if oldest is None or datetime.now(timezone.utc).timestamp() - oldest < 60:
        return {}
    return {"fetched_at": datetime.fromtimestamp(oldest, timezone.utc).isoformat(timespec="seconds"),
            "cached": True}


def _cost_by_program(lines: list[dict]) -> list[dict]:
    totals: dict[str, float] = {}
    currency = None
    for line in lines:
        cost = line.get("cost") or {}
        if cost.get("amount") is None:
            continue
        currency = currency or cost.get("currency")
        program = line.get("program") or "sin programa"
        totals[program] = totals.get(program, 0.0) + float(cost["amount"])
    return [{"program": program, "cost": round(amount, 2), "currency": currency}
            for program, amount in sorted(totals.items(), key=lambda item: -item[1])]


def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number
