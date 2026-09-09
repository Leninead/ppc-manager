"""Ingest workflows for Mercado Libre.

This layer speaks Meli — items, visits, orders — and translates each domain
concept into a row inside our tables. It never touches OAuth: the caller
hands it a ready ``MeliClient`` (with a refresh callback wired) and a
``_Rest`` bound to the worker JWT.

Every stage records exactly one row in ``meli_ingestion_runs``: one clock,
one status, one row-count. Callers that want to observe the sync watch that
table, not stdout.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from core.meli_api.transport import (
    MeliClient,
    MeliClientError,
    NotFound,
)

log = logging.getLogger("meli_api.ingest")

# Table names — kept as constants so a rename lands in one place.
IDENTITIES_TABLE = "meli_auth_identities"
ITEM_SNAPSHOTS_TABLE = "meli_item_snapshots"
RENDIMIENTO_TABLE = "meli_rendimiento_diario"
ADS_DAILY_TABLE = "meli_ads_daily"
RUNS_TABLE = "meli_ingestion_runs"

# Window we sync on every run; the tables absorb overlap via their unique keys.
_VISITS_LAST_DAYS = 30
_ORDERS_SINCE_DAYS = 30
_ADS_LAST_DAYS = 90  # Product Ads reports typically cover 60-90d — a shorter
# window misses recent-past data that operators still want to see (holiday
# spikes, weekly cadence). The API bridge slices to 30d in the UI anyway.

# Product Ads endpoints demand these headers on top of the bearer token.
# The advertisers listing does not need Api-Version; the campaign/ad_group
# search endpoints do. X-Product-Id keeps us on the Product Ads surface even
# though the current documentation only requires it as a query param.
_ADS_ADVERTISERS_HEADERS = {"X-Product-Id": "PADS"}
_ADS_METRICS_HEADERS = {"Api-Version": "1", "X-Product-Id": "PADS"}

# Sentinel used as ad_group_id for the campaign-level rollup rows.
# meli_ads_daily.ad_group_id is NOT NULL, so a rollup needs a value that is
# distinct from any real ad_group id Meli will ever hand back.
_ADS_CAMPAIGN_ROLLUP_AGID = "ALL"

# Metrics we ask Meli for on every ads page. Kept close to the fields
# meli_ads_daily actually stores so the mapper stays a straight rename.
_ADS_METRIC_NAMES = (
    "clicks,cost,impressions,direct_units_quantity,"
    "direct_amount,total_amount,total_units_quantity"
)


# ---------------------------------------------------------------------------
# hydrate_identity
# ---------------------------------------------------------------------------
def hydrate_identity(rest, connection_row: dict) -> int:
    """Upsert a MELI identity row from an ``integration_connections`` row.

    The generic portal row and the Meli-specific identity row describe the
    same underlying seller account. We match by (integration_slug ==
    'mercado_libre', cuenta_externa_id ↔ user_id). Returns the identity id.

    Raises ``ValueError`` when the connection row is not a Mercado Libre
    account or is missing ``cuenta_externa_id``.
    """
    slug = str(connection_row.get("integration_slug") or "").strip()
    if slug and slug != "mercado_libre":
        raise ValueError(
            f"hydrate_identity called with slug={slug!r}; "
            "only mercado_libre connections are supported"
        )

    user_id = str(connection_row.get("cuenta_externa_id") or "").strip()
    if not user_id:
        raise ValueError("connection_row has no cuenta_externa_id")

    # The Meli OAuth worker stores the seller's real nickname in
    # `integration_connections.cliente` (from /users/me). `nombre_externo` is
    # reserved for a future free-form label the agency can set. Prefer nickname
    # first, fall back to the label, then to the numeric user_id.
    client = str(connection_row.get("cliente") or "").strip()
    external_name = str(connection_row.get("nombre_externo") or "").strip()
    payload: dict[str, Any] = {
        "user_id": user_id,
        "nickname": client or external_name or user_id,
        "cliente": client,
        "site_id": str(connection_row.get("marketplace") or "MLA"),
        "estado": "activo",
    }
    sealed = connection_row.get("refresh_token_sealed")
    if sealed:
        # The worker role can SELECT this column back; the app role cannot.
        payload["refresh_token_sealed"] = sealed
    if connection_row.get("scopes"):
        # PostgREST accepts a JSON list for text[] columns.
        payload["scopes"] = list(connection_row["scopes"])

    rest.upsert(IDENTITIES_TABLE, payload, on_conflict="user_id")

    rows = rest.select(
        IDENTITIES_TABLE,
        {"select": "id", "user_id": f"eq.{user_id}", "limit": "1"},
    )
    if not rows:
        raise RuntimeError(
            f"identity for user_id={user_id!r} not found after upsert"
        )
    return int(rows[0]["id"])


# ---------------------------------------------------------------------------
# sync_items
# ---------------------------------------------------------------------------
def sync_items(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
    user_id: str,
) -> tuple[int, int]:
    """Enumerate the seller's active items and snapshot each one for today.

    ``mla`` is the account-level site id (``MLA``/``MLM``/…) — kept in the
    signature for symmetry with the other stages and for future filtering;
    the enumeration itself is scoped by ``user_id``.

    Returns ``(items_seen, rows_written)``.
    """
    del mla  # unused: enumeration is scoped by user_id
    today = date.today().isoformat()
    items_seen = 0
    rows_written = 0

    for item_id in client.paginate(
        f"/users/{user_id}/items/search", params={"status": "active"}
    ):
        item_id_str = str(item_id)
        items_seen += 1
        try:
            detail = client.get(f"/items/{item_id_str}")
        except NotFound:
            # The listing vanished between search and detail: nothing to snapshot.
            continue

        row: dict[str, Any] = {
            "identity_id": identity_id,
            "mla": item_id_str,
            "captured_on": today,
            "payload": detail,
        }
        family_id = detail.get("family_id")
        if family_id:
            row["family_id"] = str(family_id)
        user_product_id = detail.get("user_product_id")
        if user_product_id:
            row["user_product_id"] = str(user_product_id)

        rest.upsert(
            ITEM_SNAPSHOTS_TABLE,
            row,
            on_conflict="identity_id,mla,captured_on",
        )
        rows_written += 1

    return items_seen, rows_written


# ---------------------------------------------------------------------------
# sync_visits
# ---------------------------------------------------------------------------
def sync_visits(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
    item_ids: Iterable[str],
) -> int:
    """For each item, pull the 30-day visits histogram, one row per day.

    Writes into ``meli_rendimiento_diario`` with ``origen='api'``. When
    ``sync_orders`` runs afterwards on the same (identity, mla, fecha) it
    only touches the sale columns — visits stay put because the update
    payload never contains ``visitas``.

    Returns the number of rows written.
    """
    del mla  # unused: item_ids are already the per-listing MLAs
    ids = [str(i) for i in item_ids]
    if not ids:
        return 0

    meta_by_mla = _latest_snapshot_meta(rest, identity_id, ids)
    rows_written = 0

    for item_id in ids:
        try:
            body = client.get(
                f"/items/{item_id}/visits/time_window",
                params={"last": _VISITS_LAST_DAYS, "unit": "day"},
            )
        except NotFound:
            continue

        meta = meta_by_mla.get(item_id, {})
        for entry in body.get("results") or []:
            day_iso = str(entry.get("date") or "")
            day = _iso_to_date(day_iso)
            if not day:
                continue
            visitas = int(entry.get("total") or 0)

            row: dict[str, Any] = {
                "identity_id": identity_id,
                "mla": item_id,
                "fecha": day,
                "visitas": visitas,
                "origen": "api",
            }
            if meta.get("titulo"):
                row["titulo"] = meta["titulo"]
            if meta.get("estado"):
                row["estado"] = meta["estado"]
            if meta.get("variantes"):
                row["variantes"] = int(meta["variantes"])

            rest.upsert(
                RENDIMIENTO_TABLE,
                row,
                on_conflict="identity_id,mla,fecha",
            )
            rows_written += 1

    return rows_written


# ---------------------------------------------------------------------------
# sync_orders
# ---------------------------------------------------------------------------
def sync_orders(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
    user_id: str,
    since_days: int = _ORDERS_SINCE_DAYS,
) -> int:
    """Aggregate paid orders per (item, day) and merge into rendimiento.

    Uses ``upsert`` with a payload that omits ``visitas`` so an existing row
    written by :func:`sync_visits` keeps its visit count. Returns the number
    of rows updated (or inserted, if visits never wrote them first).
    """
    del mla
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    since = since.replace(microsecond=0)
    since_iso = since.isoformat()

    # {(item_id, fecha): {ventas, unidades, facturacion}}
    agg: dict[tuple[str, str], dict[str, float]] = {}

    for order in client.paginate(
        "/orders/search",
        params={
            "seller": str(user_id),
            "order.date_created.from": since_iso,
            "order.status": "paid",
            "sort": "date_asc",
        },
    ):
        day = _order_date(order)
        if not day:
            continue
        for oi in order.get("order_items") or []:
            item = oi.get("item") or {}
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            qty = int(oi.get("quantity") or 0)
            unit_price = float(oi.get("unit_price") or 0)
            bucket = agg.setdefault(
                (item_id, day),
                {"ventas": 0, "unidades": 0, "facturacion": 0.0},
            )
            bucket["ventas"] += 1
            bucket["unidades"] += qty
            bucket["facturacion"] += qty * unit_price

    rows_updated = 0
    for (item_id, day), values in agg.items():
        row = {
            "identity_id": identity_id,
            "mla": item_id,
            "fecha": day,
            "ventas": int(values["ventas"]),
            "unidades": int(values["unidades"]),
            "facturacion": round(values["facturacion"], 2),
            "origen": "api",
        }
        rest.upsert(
            RENDIMIENTO_TABLE,
            row,
            on_conflict="identity_id,mla,fecha",
        )
        rows_updated += 1

    return rows_updated


# ---------------------------------------------------------------------------
# resolve_advertiser_id
# ---------------------------------------------------------------------------
def resolve_advertiser_id(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
) -> str | None:
    """Return the Product Ads advertiser_id for this identity, if any.

    Cache-first: if ``meli_auth_identities.advertiser_id`` is already set we
    trust it and skip the HTTP round-trip. When the identity has never been
    resolved we call ``/advertising/advertisers`` (with ``X-Product-Id: PADS``)
    and pick the row whose ``site_id`` matches ``mla``. On a hit we persist
    the advertiser_id onto the identity row so every later run stays cheap.

    Returns ``None`` when the account has no Product Ads advertiser
    provisioned. The caller uses that as a signal to skip the ads stage
    without recording an error.
    """
    identity_id_int = int(identity_id)
    site = str(mla or "").strip()

    try:
        cached_rows = rest.select(
            IDENTITIES_TABLE,
            {
                "select": "advertiser_id,user_id",
                "id": f"eq.{identity_id_int}",
                "limit": "1",
            },
        )
    except Exception as exc:
        log.warning(
            "meli_api: could not read cached advertiser_id for identity %s: %s",
            identity_id_int,
            exc,
        )
        cached_rows = []
    cached_user_id = ""
    if cached_rows:
        cached_row = cached_rows[0]
        cached_user_id = str(cached_row.get("user_id") or "").strip()
        cached_advertiser = str(cached_row.get("advertiser_id") or "").strip()
        if cached_advertiser:
            return cached_advertiser

    try:
        body = client.get(
            "/advertising/advertisers",
            extra_headers=_ADS_ADVERTISERS_HEADERS,
        )
    except NotFound:
        return None
    except MeliClientError as exc:
        # The account has no Product Ads access (403 or similar). Treat as
        # "no advertiser" so the caller records a clean skipped stage
        # instead of propagating an error.
        log.info(
            "meli_api: advertisers lookup rejected for identity %s: %s",
            identity_id_int,
            exc,
        )
        return None

    advertisers = body.get("advertisers") or body.get("results") or []
    if not isinstance(advertisers, list):
        return None

    picked: str | None = None
    for adv in advertisers:
        if not isinstance(adv, dict):
            continue
        adv_site = str(adv.get("site_id") or "").strip()
        adv_id = str(adv.get("advertiser_id") or "").strip()
        if not adv_id:
            continue
        if site and adv_site and adv_site != site:
            continue
        picked = adv_id
        break

    if not picked:
        return None

    # Persist the cache. The identities table's on_conflict target is
    # user_id (see 003_meli_api.sql), so we need it alongside the update.
    if not cached_user_id:
        try:
            cached_user_id = _identity_user_id(rest, identity_id_int)
        except Exception as exc:
            log.warning(
                "meli_api: could not read user_id for identity %s: %s",
                identity_id_int,
                exc,
            )
            cached_user_id = ""

    # The identity row already exists (hydrate_identity ran earlier in the
    # same sync). UPSERT would try to INSERT on a missing `user_id` match
    # and violate NOT NULL on `cliente`/`site_id`. UPDATE by id is safe and
    # narrower.
    try:
        rest.update(
            IDENTITIES_TABLE,
            {"id": f"eq.{identity_id_int}"},
            {"advertiser_id": picked},
        )
    except Exception as exc:
        log.warning(
            "meli_api: could not persist advertiser_id for identity %s: %s",
            identity_id_int,
            exc,
        )
    return picked


def _identity_user_id(rest, identity_id: int) -> str:
    """Read the identity's user_id so on_conflict upserts have both keys."""
    rows = rest.select(
        IDENTITIES_TABLE,
        {
            "select": "user_id",
            "id": f"eq.{int(identity_id)}",
            "limit": "1",
        },
    )
    if not rows:
        raise RuntimeError(
            f"identity id={identity_id!r} vanished before advertiser_id cache"
        )
    return str(rows[0]["user_id"])


# ---------------------------------------------------------------------------
# sync_ads
# ---------------------------------------------------------------------------
def sync_ads(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
    advertiser_id: str,
    since_days: int = _ADS_LAST_DAYS,
) -> tuple[int, int]:
    """Snapshot Product Ads metrics into ``meli_ads_daily``.

    Two levels are pulled:

    * campaign roll-up — one row per (identity, day, campaign, ``'ALL'``).
    * ad_group breakdown — one row per (identity, day, campaign, ad_group).

    ``on_conflict`` is the 4-column key ``identity_id,fecha,campaign_id,
    ad_group_id`` — see migration ``004_meli_ads_unique.sql`` for the
    matching unique index.

    Returns ``(requests_made, rows_written)``. ``requests_made`` counts the
    top-level Meli objects we paged through (each campaign + each ad_group),
    which is what the ``meli_ingestion_runs`` row records.
    """
    del mla  # unused: advertiser_id already scopes the account
    if not advertiser_id:
        return 0, 0

    today = date.today()
    date_from = (today - timedelta(days=int(since_days))).isoformat()
    date_to = today.isoformat()

    common_params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics_summary_type": "date_summary",
        "metrics": _ADS_METRIC_NAMES,
        "limit": 50,
    }

    requests_made = 0
    rows_written = 0
    campaigns: list[dict] = []

    for campaign in client.paginate(
        f"/advertising/advertisers/{advertiser_id}/product_ads/campaigns/search",
        params=dict(common_params),
        extra_headers=_ADS_METRICS_HEADERS,
    ):
        requests_made += 1
        if not isinstance(campaign, dict):
            continue
        campaigns.append(campaign)
        campaign_id = str(campaign.get("id") or "").strip()
        if not campaign_id:
            continue
        campaign_name = str(campaign.get("name") or "")
        for entry in _iter_metrics_summary(campaign):
            row = _ads_row(
                identity_id=identity_id,
                day=entry.get("date"),
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                ad_group_id=_ADS_CAMPAIGN_ROLLUP_AGID,
                ad_group_name="",
                mla="",
                metrics=entry,
            )
            if row is None:
                continue
            rest.upsert(
                ADS_DAILY_TABLE,
                row,
                on_conflict="identity_id,fecha,campaign_id,ad_group_id",
            )
            rows_written += 1

    for campaign in campaigns:
        campaign_id = str(campaign.get("id") or "").strip()
        if not campaign_id:
            continue
        campaign_name = str(campaign.get("name") or "")
        for group in client.paginate(
            f"/advertising/advertisers/{advertiser_id}/product_ads/ad_groups/search",
            params=dict(common_params, campaign_id=campaign_id),
            extra_headers=_ADS_METRICS_HEADERS,
        ):
            requests_made += 1
            if not isinstance(group, dict):
                continue
            # Meli's ad_groups endpoint sometimes returns `id` and sometimes
            # `ad_group_id` — tolerate both so a doc-version drift doesn't
            # silently drop every group.
            ad_group_id = str(group.get("id") or group.get("ad_group_id") or "").strip()
            if not ad_group_id or ad_group_id == _ADS_CAMPAIGN_ROLLUP_AGID:
                continue
            ad_group_name = str(group.get("name") or group.get("ad_group_name") or "")
            for entry in _iter_metrics_summary(group):
                row = _ads_row(
                    identity_id=identity_id,
                    day=entry.get("date"),
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    ad_group_id=ad_group_id,
                    ad_group_name=ad_group_name,
                    mla="",
                    metrics=entry,
                )
                if row is None:
                    continue
                rest.upsert(
                    ADS_DAILY_TABLE,
                    row,
                    on_conflict="identity_id,fecha,campaign_id,ad_group_id",
                )
                rows_written += 1

    return requests_made, rows_written


def _iter_metrics_summary(node: dict) -> Iterable[dict]:
    """Yield each per-day entry inside a campaign or ad_group payload."""
    summary = node.get("metrics_summary")
    if isinstance(summary, list):
        for entry in summary:
            if isinstance(entry, dict):
                yield entry


def _ads_row(
    *,
    identity_id: int,
    day: Any,
    campaign_id: str,
    campaign_name: str,
    ad_group_id: str,
    ad_group_name: str,
    mla: str,
    metrics: dict,
) -> dict | None:
    """Build one meli_ads_daily row from a metrics_summary entry."""
    day_iso = _iso_to_date(str(day or ""))
    if not day_iso:
        return None
    return {
        "identity_id": int(identity_id),
        "fecha": day_iso,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "ad_group_id": ad_group_id,
        "ad_group_name": ad_group_name,
        "mla": mla,
        "impresiones": int(metrics.get("impressions") or 0),
        "clics": int(metrics.get("clicks") or 0),
        "inversion": _to_money(metrics.get("cost")),
        "ingresos": _to_money(metrics.get("total_amount")),
        "ventas": int(metrics.get("total_units_quantity") or 0),
        "origen": "api",
    }


def _to_money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# sync_all — orchestration
# ---------------------------------------------------------------------------
def sync_all(
    client: MeliClient,
    rest,
    identity_id: int,
    mla: str,
    user_id: str,
) -> dict[str, dict]:
    """Run the four stages in order — items, visits, orders, ads —
    recording one ``meli_ingestion_runs`` row per stage. A failure inside a
    stage marks that stage's row as ``error`` and continues with the
    remaining stages — the operator can read the runs table to see what
    completed and what did not. The ads stage skips cleanly (status ``ok``,
    rows_written ``0``) when the account has no Product Ads advertiser.

    Returns a per-stage report dict, useful in tests.
    """
    report: dict[str, dict] = {}

    # STAGE items — the anchor. Without items we cannot fan out visits.
    items_ids: list[str] = []
    run_id = _start_run(rest, identity_id, "items")
    try:
        items_seen, rows_written = sync_items(
            client, rest, identity_id, mla, user_id
        )
        _finish_run(
            rest,
            run_id,
            status="ok",
            requests_made=items_seen + 1,
            rows_written=rows_written,
        )
        report["items"] = {"status": "ok", "rows": rows_written}
        # Load the MLAs we just snapshotted so the next stage can iterate
        # even if the caller cannot see the snapshots table.
        items_ids = _snapshotted_mlas(
            rest, identity_id, date.today().isoformat()
        )
    except Exception as exc:
        _finish_run(
            rest,
            run_id,
            status="error",
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        report["items"] = {"status": "error", "error": str(exc)}

    # STAGE visits — depends on items but we tolerate a soft-empty list.
    run_id = _start_run(rest, identity_id, "visits")
    try:
        rows_written = sync_visits(
            client, rest, identity_id, mla, items_ids
        )
        _finish_run(
            rest,
            run_id,
            status="ok",
            requests_made=len(items_ids),
            rows_written=rows_written,
        )
        report["visits"] = {"status": "ok", "rows": rows_written}
    except Exception as exc:
        _finish_run(
            rest,
            run_id,
            status="error",
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        report["visits"] = {"status": "error", "error": str(exc)}

    # STAGE orders — independent of the previous two.
    run_id = _start_run(rest, identity_id, "orders")
    try:
        rows_written = sync_orders(
            client, rest, identity_id, mla, user_id
        )
        _finish_run(
            rest,
            run_id,
            status="ok",
            rows_written=rows_written,
        )
        report["orders"] = {"status": "ok", "rows": rows_written}
    except Exception as exc:
        _finish_run(
            rest,
            run_id,
            status="error",
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        report["orders"] = {"status": "error", "error": str(exc)}

    # STAGE ads — optional; the account may not have a Product Ads advertiser
    # (never onboarded, or the token lacks the ads scope). Absence is not an
    # error: we still record a run with status "ok" and rows_written=0 so
    # the freshness watchdog sees the stage ran to completion.
    run_id = _start_run(rest, identity_id, "ads")
    try:
        advertiser_id = resolve_advertiser_id(client, rest, identity_id, mla)
        if not advertiser_id:
            _finish_run(
                rest,
                run_id,
                status="ok",
                requests_made=1,
                rows_written=0,
                error_message="no advertiser account",
            )
            report["ads"] = {
                "status": "ok",
                "rows": 0,
                "message": "no advertiser account",
            }
        else:
            requests_made, rows_written = sync_ads(
                client, rest, identity_id, mla, advertiser_id
            )
            _finish_run(
                rest,
                run_id,
                status="ok",
                requests_made=requests_made,
                rows_written=rows_written,
            )
            report["ads"] = {"status": "ok", "rows": rows_written}
    except Exception as exc:
        _finish_run(
            rest,
            run_id,
            status="error",
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        report["ads"] = {"status": "error", "error": str(exc)}

    return report


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _start_run(rest, identity_id: int, stage: str) -> int | None:
    """Open a run row and return its id (best-effort — None on read failure)."""
    started_at = _now_iso()
    payload = {
        "identity_id": identity_id,
        "stage": stage,
        "started_at": started_at,
        "status": "running",
    }
    try:
        rest.insert(RUNS_TABLE, payload)
    except Exception as exc:
        log.warning("meli_api: could not open run %s: %s", stage, exc)
        return None
    # PostgREST INSERT with `Prefer: return=minimal` gives no body — read
    # the id back matching on the timestamp we just wrote (client-generated,
    # unique per stage/identity per microsecond).
    try:
        rows = rest.select(
            RUNS_TABLE,
            {
                "select": "id",
                "identity_id": f"eq.{identity_id}",
                "stage": f"eq.{stage}",
                "started_at": f"eq.{started_at}",
                "limit": "1",
            },
        )
    except Exception as exc:
        log.warning("meli_api: could not re-read run %s: %s", stage, exc)
        return None
    return int(rows[0]["id"]) if rows else None


def _finish_run(
    rest,
    run_id: int | None,
    *,
    status: str,
    requests_made: int = 0,
    rows_written: int = 0,
    error_class: str | None = None,
    error_message: str | None = None,
) -> None:
    """Close a run row. Silent no-op when the run id is unknown."""
    if run_id is None:
        return
    changes: dict[str, Any] = {
        "status": status,
        "finished_at": _now_iso(),
        "requests_made": int(requests_made),
        "rows_written": int(rows_written),
    }
    if error_class is not None:
        changes["error_class"] = error_class
    if error_message is not None:
        changes["error_message"] = error_message
    try:
        # meli_ingestion_runs has no `updated_at` column; the stage's own
        # `finished_at` is the audit clock.
        rest.update(RUNS_TABLE, {"id": f"eq.{run_id}"}, changes, stamp=False)
    except Exception as exc:
        log.warning("meli_api: could not close run id=%s: %s", run_id, exc)


def _snapshotted_mlas(rest, identity_id: int, captured_on: str) -> list[str]:
    """Read the MLAs we snapshotted today, in a stable order."""
    try:
        rows = rest.select(
            ITEM_SNAPSHOTS_TABLE,
            {
                "select": "mla",
                "identity_id": f"eq.{identity_id}",
                "captured_on": f"eq.{captured_on}",
                "order": "mla.asc",
            },
        )
    except Exception as exc:
        log.warning("meli_api: could not enumerate snapshots: %s", exc)
        return []
    return [str(r["mla"]) for r in rows if r.get("mla")]


def _latest_snapshot_meta(
    rest, identity_id: int, mlas: list[str]
) -> dict[str, dict[str, Any]]:
    """Load ``titulo``/``estado`` for a batch of MLAs from the latest snapshot."""
    if not mlas:
        return {}
    # PostgREST accepts `in.(a,b,c)` for list filters. We stay defensive on
    # any read failure — falling back to empty means the rendimiento rows
    # carry NULL titulo/estado (nullable columns in the schema).
    filt = ",".join(mlas)
    try:
        rows = rest.select(
            ITEM_SNAPSHOTS_TABLE,
            {
                "select": "mla,payload,captured_on",
                "identity_id": f"eq.{identity_id}",
                "mla": f"in.({filt})",
                "order": "captured_on.desc",
            },
        )
    except Exception as exc:
        log.warning("meli_api: could not read item metadata: %s", exc)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mla = str(row.get("mla") or "")
        if not mla or mla in out:
            continue  # keep the freshest (order desc) — skip stale duplicates
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        meta: dict[str, Any] = {}
        if payload.get("title"):
            meta["titulo"] = str(payload["title"])
        if payload.get("status"):
            meta["estado"] = str(payload["status"])
        variations = payload.get("variations")
        if isinstance(variations, list) and variations:
            meta["variantes"] = len(variations)
        out[mla] = meta
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_date(value: str) -> str | None:
    """Return an ISO ``YYYY-MM-DD`` for a Meli-style timestamp, or None."""
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        # Meli returns timestamps like "2026-07-01T00:00:00.000Z"
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v).date().isoformat()
    except (ValueError, TypeError):
        # Some endpoints return date-only already.
        try:
            return date.fromisoformat(v[:10]).isoformat()
        except (ValueError, TypeError):
            return None


def _order_date(order: dict) -> str | None:
    """Pick the best date field on an order for daily bucketing."""
    for key in ("date_closed", "date_created", "last_updated"):
        day = _iso_to_date(str(order.get(key) or ""))
        if day:
            return day
    return None


__all__ = [
    "hydrate_identity",
    "sync_items",
    "sync_visits",
    "sync_orders",
    "resolve_advertiser_id",
    "sync_ads",
    "sync_all",
    "IDENTITIES_TABLE",
    "ITEM_SNAPSHOTS_TABLE",
    "RENDIMIENTO_TABLE",
    "ADS_DAILY_TABLE",
    "RUNS_TABLE",
    "MeliClientError",
]
