"""API bridge: reshape Meli API tables into the shapes the M36 UI expects.

The M36 module was born from Excel exports and its downstream views
(``tracker``, ``stock``, ``alertas``) read a DataFrame that matches the
``meli-{rendimiento,publicaciones,ads}-v{1,2}`` schemas. When the API ingest
started landing rows into ``meli_rendimiento_diario``,
``meli_item_snapshots`` and ``meli_ads_daily``, we didn't want to rewrite
the views — so the bridge reshapes those relational rows into snapshot
DataFrames that look identical to what the Excel parsers produce.

The bridge is READ-ONLY. Writes into the API tables belong to
``core.meli_api.ingest``; this module just projects them.

Sourcing hierarchy inside ``_latest_snapshot``:
  1. If an active ``meli_auth_identity`` exists for the given ``cliente`` and
     the bridge returns a non-None DataFrame, use it (``origen='api'``).
  2. Otherwise fall back to the last local Parquet snapshot on disk
     (``origen='excel'``).

Rows carry ``origen`` so the UI can show the source and downstream logic can
filter by it without having to load two frames.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import pandas as pd

log = logging.getLogger("mercado_libre.api_bridge")

# Table names — the same constants the ingest layer writes to.
IDENTITIES_TABLE = "meli_auth_identities"
RENDIMIENTO_TABLE = "meli_rendimiento_diario"
ITEM_SNAPSHOTS_TABLE = "meli_item_snapshots"
ADS_DAILY_TABLE = "meli_ads_daily"

# Window we present to the UI. Matches the ingest side (``_VISITS_LAST_DAYS``
# and ``_ADS_LAST_DAYS`` in ``core.meli_api.ingest``) so the "snapshot" the AM
# sees actually consolidates every row the worker has written for that
# identity.
_LOOKBACK_DAYS = int(os.environ.get("MELI_BRIDGE_LOOKBACK_DAYS", "30"))
# ^ Configurable so dev environments with historical Excel (e.g. the local
# simulator serving July data in September) can bump the window and still
# see rows in the UI. Production defaults to 30 days — matches the operator's
# mental model and the schema's `evolution_notes.window_days`.

# Sentinel the ingest writes into ``ad_group_id`` for the campaign-level
# roll-up row. Duplicated here (not imported) to keep the bridge decoupled
# from the ingest module; the ingest owns the constant. If the two ever
# drift, the tests in ``test_meli_api_bridge`` catch it — the bridge would
# start double-counting the per-ad_group rows.
_ADS_CAMPAIGN_ROLLUP_AGID = "ALL"


# ---------------------------------------------------------------------------
# Identity lookup — shared by every builder.
# ---------------------------------------------------------------------------
def _resolve_identity_id(rest, client: str, mla: str) -> int | None:
    """Return the ``meli_auth_identities.id`` for (cliente, site_id), or None.

    ``mla`` here is the account-level site id (``MLA``/``MLM``/``MLB``/...),
    following the naming convention used across ``core.meli_api``. We match
    ``estado='activo'`` so revoked or paused identities never poison the UI.
    """
    if not client:
        return None
    params = {
        "select": "id",
        "cliente": f"eq.{client}",
        "estado": "eq.activo",
        "limit": "1",
    }
    if mla:
        params["site_id"] = f"eq.{mla}"
    try:
        rows = rest.select(IDENTITIES_TABLE, params)
    except Exception as exc:  # noqa: BLE001 — bridge must not take the UI down
        log.warning("meli_api bridge: identity lookup failed: %s", exc)
        return None
    if not rows:
        return None
    return int(rows[0]["id"])


# ---------------------------------------------------------------------------
# build_rendimiento_snapshot
# ---------------------------------------------------------------------------
def build_rendimiento_snapshot(
    rest, client: str, mla: str
) -> pd.DataFrame | None:
    """Consolidate the last 30 daily rows of ``meli_rendimiento_diario`` into a
    single per-MLA snapshot matching ``meli-rendimiento-v2``.

    ``mla`` is the account-level site id (used to disambiguate multi-site
    identities). Returns ``None`` when no identity resolves or the table is
    empty for that identity — callers fall back to the local Parquet.
    """
    identity_id = _resolve_identity_id(rest, client, mla)
    if identity_id is None:
        return None

    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    try:
        rows = rest.select(
            RENDIMIENTO_TABLE,
            {
                "select": (
                    "mla,fecha,visitas,ventas,unidades,facturacion,"
                    "estado,titulo,variantes"
                ),
                "identity_id": f"eq.{identity_id}",
                "fecha": f"gte.{since}",
                "order": "fecha.asc",
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("meli_api bridge: rendimiento select failed: %s", exc)
        return None
    if not rows:
        return None

    raw = pd.DataFrame(rows)
    raw["fecha"] = pd.to_datetime(raw["fecha"]).dt.date
    for col in ("visitas", "ventas", "unidades"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0).astype("int64")
    raw["facturacion"] = pd.to_numeric(raw["facturacion"], errors="coerce").fillna(0.0)
    raw["variantes"] = pd.to_numeric(raw["variantes"], errors="coerce").fillna(1).astype("int64")

    # Consolidate daily rows into one row per MLA — same shape ``parse``
    # returns for the Excel path. ``titulo``/``estado`` take the freshest
    # non-null value (rows come in ascending order, so ``last`` wins).
    def _last_non_null(series: pd.Series) -> Any:
        cleaned = series.dropna()
        return cleaned.iloc[-1] if len(cleaned) else None

    aggregate = raw.groupby("mla", as_index=False).agg(
        title=("titulo", _last_non_null),
        status=("estado", _last_non_null),
        visitas=("visitas", "sum"),
        ventas=("ventas", "sum"),
        unidades=("unidades", "sum"),
        facturacion=("facturacion", "sum"),
        variantes=("variantes", "max"),
    )
    aggregate["titulo"] = aggregate["titulo"].fillna("").astype(str)
    aggregate["estado"] = aggregate["estado"].fillna("").astype(str)

    # Conversion recomputed post-aggregation. Averaging the daily rates would
    # weight small-traffic days the same as big ones and misrepresent the
    # publication.
    visitas_validas = aggregate["visitas"].where(aggregate["visitas"] > 0)
    aggregate["conversion"] = aggregate["ventas"] / visitas_validas

    # The window bounds come from the data actually present — not from
    # ``today - 30`` — so a fresh identity with only a week of history shows
    # the true 7-day span.
    start = raw["fecha"].min()
    end = raw["fecha"].max()
    days = (end - start).days + 1
    aggregate["desde"] = start.isoformat()
    aggregate["hasta"] = end.isoformat()
    aggregate["dias"] = int(days)
    aggregate["origen"] = "api"
    return aggregate


# ---------------------------------------------------------------------------
# build_publicaciones_snapshot
# ---------------------------------------------------------------------------
def build_publicaciones_snapshot(
    rest, client: str, mla: str
) -> pd.DataFrame | None:
    """Flatten the latest ``meli_item_snapshots.payload`` per MLA into a
    DataFrame matching ``meli-publicaciones-v2``.

    Only the freshest ``captured_on`` per MLA is kept — the same shape a
    single Excel export produces. Returns ``None`` when no identity resolves
    or no snapshots exist for that identity.
    """
    identity_id = _resolve_identity_id(rest, client, mla)
    if identity_id is None:
        return None

    try:
        rows = rest.select(
            ITEM_SNAPSHOTS_TABLE,
            {
                "select": "mla,payload,captured_on",
                "identity_id": f"eq.{identity_id}",
                "order": "captured_on.desc",
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("meli_api bridge: item snapshots select failed: %s", exc)
        return None
    if not rows:
        return None

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for row in rows:
        mla_id = str(row.get("mla") or "").strip()
        if not mla_id or mla_id in seen:
            continue  # freshest wins — rows come ordered desc by captured_on
        seen.add(mla_id)
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        # Prefer the id inside the payload only as a last-resort fallback:
        # the table column is what the ingest wrote and what our schema keys
        # everything on.
        item_id = mla_id or str(payload.get("id") or "").strip()
        title = str(payload.get("title") or "").strip()
        status = str(payload.get("status") or "").strip()
        stock_val = payload.get("available_quantity")
        try:
            stock = float(stock_val) if stock_val is not None else 0.0
        except (TypeError, ValueError):
            stock = 0.0
        precio_val = payload.get("price")
        try:
            precio = float(precio_val) if precio_val is not None else None
        except (TypeError, ValueError):
            precio = None
        variations = payload.get("variations")
        variantes = len(variations) if isinstance(variations, list) and variations else 1
        records.append({
            "mla": item_id,
            "titulo": title,
            "estado": status,
            "stock": stock,
            "precio": precio,
            "variantes": int(variantes),
            "origen": "api",
        })

    if not records:
        return None

    df = pd.DataFrame(records)
    df["stock"] = df["stock"].astype("float64")
    df["variantes"] = df["variantes"].astype("int64")
    # Keep column order predictable for downstream views that reach for cols
    # by position in the tail of the frame (there are a few).
    return df[["mla", "titulo", "estado", "stock", "precio", "variantes", "origen"]]


# ---------------------------------------------------------------------------
# build_ads_snapshot
# ---------------------------------------------------------------------------
def build_ads_snapshot(rest, client: str, mla: str) -> pd.DataFrame | None:
    """Consolidate the last 30 days of ``meli_ads_daily`` into a per-(campaña,
    publicación) snapshot matching ``meli-ads-v2``.

    ``mla`` is the account-level site id (used to disambiguate multi-site
    identities); the per-item ``mla`` used as PK of the snapshot lives on
    every row of ``meli_ads_daily``. Rows tagged with the campaign-rollup
    sentinel (``ad_group_id='ALL'``) are excluded so we do not double-count
    metrics that are already summed inside the per-ad_group breakdown.

    Returns ``None`` when no identity resolves or no ad rows exist in the
    window — callers fall back to the local Parquet (``origen='excel'``).
    """
    identity_id = _resolve_identity_id(rest, client, mla)
    if identity_id is None:
        return None

    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    try:
        rows = rest.select(
            ADS_DAILY_TABLE,
            {
                "select": (
                    "fecha,campaign_id,campaign_name,ad_group_id,"
                    "ad_group_name,mla,impresiones,clics,inversion,ingresos"
                ),
                "identity_id": f"eq.{identity_id}",
                "fecha": f"gte.{since}",
                "order": "fecha.asc",
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("meli_api bridge: ads select failed: %s", exc)
        return None
    if not rows:
        return None

    raw = pd.DataFrame(rows)
    # Skip the campaign-level roll-up rows. If we kept them the sum-per-
    # (campaña, mla) would double the metrics: the roll-up already carries
    # the totals the per-ad_group rows break down. See ``sync_ads`` in
    # ``core.meli_api.ingest``.
    if "ad_group_id" in raw.columns:
        raw = raw[raw["ad_group_id"].astype(str) != _ADS_CAMPAIGN_ROLLUP_AGID]
    if raw.empty:
        return None

    raw["fecha"] = pd.to_datetime(raw["fecha"]).dt.date
    raw["campaign_name"] = raw["campaign_name"].fillna("").astype(str).str.strip()
    raw["ad_group_name"] = raw["ad_group_name"].fillna("").astype(str).str.strip()
    raw["mla"] = raw["mla"].fillna("").astype(str).str.strip()
    for col in ("impresiones", "clics"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0).astype("int64")
    for col in ("inversion", "ingresos"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0.0).astype("float64")

    # Drop rows where the campaign name is missing — the schema keys on it
    # and a blank campaign would collapse every stray row into one bucket.
    raw = raw[raw["campaign_name"] != ""]
    if raw.empty:
        return None

    def _first_non_empty(series: pd.Series) -> str:
        for val in series:
            if val:
                return val
        return ""

    aggregate = raw.groupby(
        ["campaign_name", "mla"], as_index=False
    ).agg(
        anuncio=("ad_group_name", _first_non_empty),
        impresiones=("impresiones", "sum"),
        clics=("clics", "sum"),
        inversion=("inversion", "sum"),
        ingresos=("ingresos", "sum"),
    )
    aggregate = aggregate.rename(columns={"campaign_name": "campana"})

    # ACOS and ROAS are recomputed from the aggregated totals — same rule
    # as the Excel parser, because averaging per-day percentages weights
    # small-traffic days the same as big ones. Both stay NaN when the
    # denominator is zero: "no ROAS" is not "ROAS zero".
    inversion = aggregate["inversion"]
    ingresos = aggregate["ingresos"]
    aggregate["acos"] = (inversion / ingresos.where(ingresos > 0)) * 100
    aggregate["roas"] = ingresos / inversion.where(inversion > 0)

    # The DB does not track ``estado`` per ad; keep the column so downstream
    # code that reads it does not KeyError, but leave the values None so it
    # is unmistakable from a real state.
    aggregate["estado"] = pd.Series([None] * len(aggregate), dtype="object")

    start = raw["fecha"].min()
    end = raw["fecha"].max()
    aggregate["desde"] = start.isoformat()
    aggregate["hasta"] = end.isoformat()
    aggregate["origen"] = "api"

    # Column order mirrors the Excel parser output plus the v2-only origen
    # tail, so a downstream diff between the two sources is a straight
    # column-by-column compare.
    return aggregate[[
        "desde", "hasta", "campana", "anuncio", "mla", "estado",
        "impresiones", "clics", "inversion", "ingresos",
        "acos", "roas", "origen",
    ]]


__all__ = [
    "build_rendimiento_snapshot",
    "build_publicaciones_snapshot",
    "build_ads_snapshot",
    "IDENTITIES_TABLE",
    "RENDIMIENTO_TABLE",
    "ITEM_SNAPSHOTS_TABLE",
]
