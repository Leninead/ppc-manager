"""
Module: Mercado Libre (M36)
Section: Marketplaces
Version: v1
Author: Lenin Acosta
Created: 2026-07-24

Operations module for Mercado Libre accounts. Three features requested by
the accounts team:

  1. Listing change tracking — the MELI equivalent of the SKU Progress
     Report: measures the impact of each modification on visits and
     conversion.
  2. Stock restock suggestions — projects coverage over the sales velocity
     and subtracts what is already in transit.
  3. Campaign alerts — semaphore by ACOS and ROAS over the ads report.

Persists via core.persistence:
  - Snapshots at data/marketplaces/<cuenta>/meli-{rendimiento,publicaciones,ads}/<YYYY-MM-DD>.parquet
  - Change log at meli-rendimiento/cambios.parquet
  - In-transit log at meli-publicaciones/transito.parquet

Validated schemas: data/_schemas/meli-{rendimiento,stock,ads}-v1.json

The period is the end date of the report (YYYY-MM-DD) and not the ISO week:
the periods Mercado Libre exports do not align with calendar weeks.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
import streamlit as st

from modules.mercado_libre import api_bridge, config
from core.integrations import roles
from core.integrations.store import _Rest, _rest_credentials, open_stores
from core.persistence import (_delete_cliente, _delete_snapshot, _list_clientes,
                              _list_periods, _load_snapshot, _rebuild_history,
                              _save_client_config, _save_snapshot,
                              _validate_against_schema)
from modules.mercado_libre.parsers import ads as parser_ads
from modules.mercado_libre.parsers import publicaciones as parser_publicaciones
from modules.mercado_libre.parsers import rendimiento as parser_rendimiento
from modules.mercado_libre.views import alerts as vista_alertas
from modules.mercado_libre.views import stock as vista_stock
from modules.mercado_libre.views import tracker as vista_tracker
from modules.mercado_libre.views.helpers import empty_state

# Dispatch from module id to the ``api_bridge`` attribute name that builds
# the API snapshot for that module. We keep the attribute name (not the
# resolved function) so ``monkeypatch.setattr(meli_main.api_bridge, ...)``
# in tests actually reaches the caller. All three builders (rendimiento,
# publicaciones, ads) return either a DataFrame consolidating the last
# 30 days of API rows or ``None``; on ``None`` the router falls back to the
# newest local Parquet snapshot.
_API_BUILDER_NAMES = {
    config.MODULO_RENDIMIENTO: "build_rendimiento_snapshot",
    config.MODULO_PUBLICACIONES: "build_publicaciones_snapshot",
    config.MODULO_ADS: "build_ads_snapshot",
}

# (table_name, date_column) per module, used by _latest_api_ingest_date to
# fetch the freshest ingest timestamp so the source caption can show
# "🔌 datos vía API · 2026-09-03" instead of a bare "datos vía API".
_API_MAX_DATE_QUERY = {
    config.MODULO_RENDIMIENTO: ("meli_rendimiento_diario", "fecha"),
    config.MODULO_PUBLICACIONES: ("meli_item_snapshots", "captured_on"),
    config.MODULO_ADS: ("meli_ads_daily", "fecha"),
}

# Integration slug this module talks to. Keeping it as a constant here (rather
# than reading from the catalog on every render) makes it obvious that this
# module is Mercado Libre-only.
MELI_SLUG = "mercado_libre"

# The connect-account dialog itself lives in modules/pages/cuentas.py — a
# marketplace-agnostic screen so a single vendor session can serve every
# module that talks to the same provider.

_SOP_MD = """
**Qué resuelve este módulo**

Concentra la operación de las cuentas de Mercado Libre en tres frentes:
seguimiento del impacto de los cambios en publicaciones, sugerencia de
reposición de stock y alertas de campañas de Product Ads.

**Cómo se usa**

1. **Importar** — subí los tres exports de Mercado Libre en la pestaña de
   importación. Cada uno alimenta una feature distinta y se pueden cargar por
   separado.
2. **Cambios** — registrá cada modificación que le hagas a una publicación con
   su fecha real. El módulo la compara contra los reportes anteriores y
   posteriores para medir si funcionó.
3. **Stock** — la sugerencia sale del cruce entre velocidad de venta y stock
   disponible. Cargá los envíos en tránsito con su fecha estimada de llegada
   para que no recomiende de más.
4. **Ads** — subí el reporte semanal y revisá primero los anuncios en rojo y los
   que gastaron sin generar ingresos.

**De dónde salen los archivos**

- Rendimiento: Mercado Libre → Métricas → Publicaciones → Descargar reporte
- Publicaciones: Mercado Libre → Publicaciones → Modificar masivamente → Descargar
- Ads: Mercado Libre Ads → Reportes → Reporte por anuncios

**Importante sobre el seguimiento de cambios**

La comparación necesita al menos dos reportes de rendimiento cargados. Con uno
solo no hay contra qué medir, así que los cambios aparecen como pendientes
hasta la segunda carga.
"""


def _upload_seq(name: str) -> int:
    """Version of the uploader `name`. The `st.file_uploader` key includes it
    so a successful save can invalidate it and remount an empty uploader.

    Streamlit persists the `UploadedFile` in `st.session_state[key]` under a
    fixed key; after `st.rerun()` it stays there and the preview + save block
    is drawn again (with the overwrite warning suggesting the user is about
    to write over the just-saved snapshot). Rotating the suffix changes the
    key and Streamlit treats the uploader as brand new. `del st.session_state[key]`
    is not allowed in the same run: the API forbids it while the widget is alive."""
    return st.session_state.get(f"meli_up_seq_{name}", 0)


def _rotate_uploader(name: str) -> None:
    st.session_state[f"meli_up_seq_{name}"] = _upload_seq(name) + 1


def _slug(text: str) -> str:
    """Turn the account name into a kebab-case slug."""
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-")
    return normalized.lower()


def _header() -> None:
    st.markdown("## 🛒 Mercado Libre")
    st.caption(
        "📥 Inputs: reporte de rendimiento, export de publicaciones y reporte de "
        "Product Ads · Output: seguimiento de cambios, sugerencia de stock y "
        "alertas de campañas"
    )
    st.divider()


def _list_accounts() -> list[dict]:
    """Merge OAuth connections with legacy local slugs into one selector list.

    An account with BOTH an OAuth connection and a local directory shows up
    once, tagged `oauth` — the API path takes precedence over Excel uploads.
    """
    local_slugs = set(_list_clientes(config.AREA, config.MODULO_RENDIMIENTO))
    oauth_by_slug: dict[str, dict] = {}
    stores = open_stores()
    if stores is not None:
        _, connection_store, _ = stores
        connections = connection_store.by_integration_slug().get(MELI_SLUG, [])
        for conn in connections:
            client = (conn.client or "").strip()
            status = (conn.status or "").strip().lower()
            # In-flight OAuth grants live in a different table, but a race or
            # a partial exchange could leave a `_pending_...` placeholder here.
            # Revoked stay in the DB for audit, not in the selector.
            if not client or client.startswith("_pending_") or status == "revocado":
                continue
            oauth_by_slug[client] = {
                "slug": client,
                "source": "oauth",
                "marketplace": (conn.marketplace or "").strip(),
                "estado": (conn.status or "").strip(),
            }
    rows: list[dict] = []
    for slug in sorted(set(local_slugs) | set(oauth_by_slug)):
        if slug in oauth_by_slug:
            rows.append(oauth_by_slug[slug])
        else:
            rows.append({"slug": slug, "source": "local", "marketplace": "", "estado": ""})
    return rows


def _account_label(slug: str, accounts: list[dict]) -> str:
    row = next((a for a in accounts if a["slug"] == slug), None)
    if row is None:
        return f"🛒 {slug}"
    if row["source"] == "oauth":
        mp = row.get("marketplace") or ""
        return f"🛒 {slug} · {mp}" if mp else f"🛒 {slug}"
    return f"🛒 {slug} · manual"


def _ensure_client_dir(slug: str) -> None:
    """Create `data/marketplaces/<slug>/` on first render of an OAuth-only account.

    A fresh OAuth connection has no local directory yet — the first Excel
    upload would fail with `directory missing` otherwise.
    """
    if slug in _list_clientes(config.AREA, config.MODULO_RENDIMIENTO):
        return
    _save_client_config(
        {"version": 1, "cuenta": slug, "nombre": slug, "origen": "oauth"},
        config.AREA, slug, config.MODULO_RENDIMIENTO, "cuenta",
    )




@st.dialog("Cuenta manual de Mercado Libre")
def _dialog_manual_account() -> None:
    """Create a client slug for the Excel-upload path.

    Connecting through the portal is the normal way in, but M36 shipped
    working with nothing but three Excel exports and it has to keep working
    that way: no database, no OAuth app, no credential. This is the only
    entry point for that, and for a dev running the app with no infra.
    """
    name = st.text_input(
        "Nombre de la cuenta", key="meli_manual_name",
        placeholder="Ej: nombre del cliente o de la tienda",
    )
    taken = _list_clientes(config.AREA, config.MODULO_RENDIMIENTO)
    if name.strip():
        st.caption(f"Slug generado: `{_slug(name)}`")
        if _slug(name) in taken:
            st.warning(f"La cuenta '{_slug(name)}' ya existe.")

    col_cancel, col_create = st.columns(2)
    if col_cancel.button("Cancelar", key="meli_manual_cancel",
                         use_container_width=True):
        st.rerun()
    if col_create.button("Crear cuenta", key="meli_manual_ok", type="primary",
                         use_container_width=True):
        if not name.strip():
            st.error("El nombre es obligatorio.")
            return
        slug = _slug(name)
        if slug in taken:
            st.error(f"La cuenta '{slug}' ya existe.")
            return
        _save_client_config(
            {"version": 1, "cuenta": slug, "nombre": name.strip()},
            config.AREA, slug, config.MODULO_RENDIMIENTO, "cuenta",
        )
        st.success(f"Cuenta '{slug}' creada. Ya podés importar sus reportes.")
        st.rerun()



def _import_tab(account: str) -> None:
    """Import tab for the three reports."""
    st.markdown("### 📤 Importar reportes")
    st.caption(
        "Cada reporte se guarda como un snapshot con su propio período. "
        "Subir el mismo archivo dos veces sobrescribe el snapshot, no lo duplica."
    )

    st.markdown("#### 1. Rendimiento de publicaciones")
    performance_file = st.file_uploader(
        "Reporte de métricas de publicaciones", type=["xlsx"],
        key=f"meli_up_rendimiento_{_upload_seq('rendimiento')}",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre → Métricas → Publicaciones → Descargar reporte.",
    )
    if performance_file:
        try:
            report = parser_rendimiento.parse(performance_file)
        except parser_rendimiento.FormatError as error:
            st.error(f"⚠ {error}")
        else:
            period = report.hasta.isoformat()
            data = report.datos.copy()
            data["desde"] = data["desde"].map(lambda f: f.isoformat())
            data["hasta"] = data["hasta"].map(lambda f: f.isoformat())
            data["dias"] = report.dias

            st.success(
                f"✓ {len(data)} publicaciones · período {report.desde} → "
                f"{report.hasta} ({report.dias} días)"
            )
            st.dataframe(data.head(8), use_container_width=True, hide_index=True)

            if period in _list_periods(config.AREA, account, config.MODULO_RENDIMIENTO):
                st.warning(f"Ya existe un snapshot para {period}: se sobrescribe.")

            if st.button("✓ Guardar rendimiento", type="primary",
                         key="meli_guardar_rendimiento"):
                errors = _validate_against_schema(
                    data, config.MODULO_RENDIMIENTO,
                    config.SCHEMA_VERSION_RENDIMIENTO
                )
                if errors:
                    st.error("El snapshot no respeta el schema:")
                    for detail in errors:
                        st.caption(f"• {detail}")
                else:
                    _save_snapshot(data, config.AREA, account,
                                   config.MODULO_RENDIMIENTO, period)
                    try:
                        _rebuild_history(config.AREA, account,
                                         config.MODULO_RENDIMIENTO)
                    except FileNotFoundError:
                        pass
                    _rotate_uploader("rendimiento")
                    st.success(f"✓ Snapshot {period} guardado.")
                    st.rerun()

    st.divider()
    st.markdown("#### 2. Publicaciones y stock")
    listings_file = st.file_uploader(
        "Export de 'Modifica tus publicaciones'", type=["xlsx"],
        key=f"meli_up_publicaciones_{_upload_seq('publicaciones')}",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre → Publicaciones → Modificar masivamente → Descargar.",
    )
    if listings_file:
        try:
            listings = parser_publicaciones.parse(listings_file)
        except parser_publicaciones.FormatError as error:
            st.error(f"⚠ {error}")
        else:
            st.success(
                f"✓ {len(listings)} publicaciones activas · "
                f"{int(listings['stock'].sum()):,} unidades en stock"
                .replace(",", ".")
            )
            st.dataframe(listings.head(8), use_container_width=True,
                         hide_index=True)
            period = st.date_input(
                "Fecha del export", key="meli_fecha_publicaciones",
                help="Se usa como período del snapshot.",
            ).isoformat()

            if st.button("✓ Guardar publicaciones", type="primary",
                         key="meli_guardar_publicaciones"):
                errors = _validate_against_schema(
                    listings, config.MODULO_PUBLICACIONES,
                    config.SCHEMA_VERSION_PUBLICACIONES,
                )
                if errors:
                    st.error("El snapshot no respeta el schema:")
                    for detail in errors:
                        st.caption(f"• {detail}")
                else:
                    _save_snapshot(listings, config.AREA, account,
                                   config.MODULO_PUBLICACIONES, period)
                    try:
                        _rebuild_history(config.AREA, account,
                                         config.MODULO_PUBLICACIONES)
                    except FileNotFoundError:
                        pass
                    _rotate_uploader("publicaciones")
                    st.success(f"✓ Snapshot {period} guardado.")
                    st.rerun()

    st.divider()
    st.markdown("#### 3. Reporte de Product Ads")
    ads_file = st.file_uploader(
        "Reporte por anuncios", type=["xlsx"],
        key=f"meli_up_ads_{_upload_seq('ads')}",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre Ads → Reportes → Reporte por anuncios.",
    )
    if ads_file:
        try:
            ads_report = parser_ads.parse(ads_file)
        except parser_ads.FormatError as error:
            st.error(f"⚠ {error}")
        else:
            data = ads_report.datos.copy()
            data["desde"] = data["desde"].map(
                lambda f: f.isoformat() if f else None)
            data["hasta"] = data["hasta"].map(
                lambda f: f.isoformat() if f else None)
            period = (ads_report.hasta or pd.Timestamp.today().date()).isoformat()

            st.success(
                f"✓ {len(data)} anuncios · {data['campana'].nunique()} campañas "
                f"· período {ads_report.desde} → {ads_report.hasta}"
            )
            st.dataframe(data.head(8), use_container_width=True, hide_index=True)

            if st.button("✓ Guardar ads", type="primary", key="meli_guardar_ads"):
                # Ads used to save without a schema check, unlike rendimiento
                # and publicaciones. An export with a shifted column landed on
                # disk and blew up later in ads_alerts. Same gate as the other
                # two now.
                errors = _validate_against_schema(
                    data, config.MODULO_ADS, config.SCHEMA_VERSION_ADS
                )
                if errors:
                    st.error("El snapshot no respeta el schema:")
                    for detail in errors:
                        st.caption(f"• {detail}")
                else:
                    _save_snapshot(data, config.AREA, account, config.MODULO_ADS,
                                   period)
                    try:
                        _rebuild_history(config.AREA, account, config.MODULO_ADS)
                    except FileNotFoundError:
                        pass
                    _rotate_uploader("ads")
                    st.success(f"✓ Snapshot {period} guardado.")
                    st.rerun()


def _admin_tab(account: str, username: str = "") -> None:
    """Admin tab for per-module snapshot management.

    Only admins reach it (see `render()`). `username` is kept so we can
    audit who deleted what in the H1 migration.
    """
    st.markdown("### ⚙️ Administrar snapshots")
    modules_list = [
        ("Rendimiento", config.MODULO_RENDIMIENTO),
        ("Stock", config.MODULO_PUBLICACIONES),
        ("Ads", config.MODULO_ADS),
    ]
    # Before: `st.columns([3, 1])` per row left the delete button ~150 px
    # from the period with empty space and no visual link. With [1, 1] (and
    # the `#### h4` replaced by a small caption) the button sits next to the
    # value and the column reads as a compact row.
    columns_row = st.columns(3)
    for column, (label, module) in zip(columns_row, modules_list):
        with column:
            st.caption(label.upper())
            periods = _list_periods(config.AREA, account, module)
            if not periods:
                st.caption("Sin snapshots todavía.")
                continue
            for period in periods:
                col_info, col_delete = st.columns([1, 1])
                col_info.markdown(f"**{period}**")
                if col_delete.button(
                    "", icon=":material/delete:",
                    key=f"meli_del_{module}_{period}",
                    help="Borrar este snapshot",
                ):
                    if _delete_snapshot(config.AREA, account, module, period):
                        try:
                            _rebuild_history(config.AREA, account, module)
                        except FileNotFoundError:
                            pass
                        st.success(f"Snapshot {period} eliminado.")
                        st.rerun()

    st.divider()
    _delete_account_section(account)


def _delete_account_section(account: str) -> None:
    """Remove a manual account and every snapshot it holds, in the three modules.

    Deleting only `MODULO_RENDIMIENTO` — the one the selector keys off — would
    take the account off screen and strand its stock and ads rows, invisible and
    unreachable. So all three go.

    An OAuth-backed account is deliberately NOT offered here: its entry comes
    from `integration_connections`, so wiping the local rows would leave it on
    screen and make the button look broken. That one ends in Sistema → Cuentas
    conectadas, which is also where the audit trail lives.
    """
    st.markdown("### 🗑️ Eliminar cuenta")
    row = next((a for a in _list_accounts() if a["slug"] == account), None)
    if row is not None and row["source"] == "oauth":
        st.info(
            f"**{account}** está conectada por API. Para sacarla del selector "
            "hay que desconectarla en ⚙️ Sistema → 🔑 Cuentas conectadas: "
            "mientras la conexión siga viva, la cuenta vuelve a aparecer acá."
        )
        return
    st.caption(
        "Saca la cuenta del selector y borra sus snapshots de rendimiento, "
        "stock y ads. No se puede deshacer."
    )
    if st.button("Eliminar cuenta", icon=":material/delete_forever:",
                 key="meli_del_account", type="primary"):
        _dialog_delete_account(account)


def _dialog_delete_account(account: str) -> None:
    """Same reason the portal wraps its dialogs: the decorator would freeze the
    title at import time, before the language is known."""
    st.dialog("Eliminar cuenta de Mercado Libre")(_delete_account_body)(account)


def _delete_account_body(account: str) -> None:
    st.markdown(
        f"Vas a borrar **{account}** y todos sus snapshots de los tres módulos. "
        "Escribí el nombre de la cuenta para confirmar."
    )
    typed = st.text_input("Nombre de la cuenta", key="meli_del_account_confirm")
    col_cancel, col_ok = st.columns(2)
    if col_cancel.button("Cancelar", key="meli_del_account_cancel",
                         use_container_width=True):
        st.rerun()
    if col_ok.button("Eliminar", key="meli_del_account_ok", type="primary",
                     use_container_width=True,
                     disabled=typed.strip() != account):
        borrados = [
            modulo for modulo in (config.MODULO_RENDIMIENTO,
                                  config.MODULO_PUBLICACIONES,
                                  config.MODULO_ADS)
            if _delete_cliente(config.AREA, account, modulo)
        ]
        # The selectbox remembers the slug that no longer exists; leaving it
        # set makes Streamlit raise on the next render instead of falling back
        # to the first remaining account.
        st.session_state.pop("meli_cuenta", None)
        if borrados:
            st.success(f"Cuenta {account} eliminada ({len(borrados)} módulos).")
        else:
            st.info(f"La cuenta {account} no tenía datos que borrar.")
        st.rerun()


def _open_rest():
    """Return a ``_Rest`` bound to the same env credentials the portal uses.

    Wrapped as a helper so it can be monkeypatched in tests. Returns ``None``
    when the portal DB is not configured (dev machines without SUPABASE_URL)
    so the module keeps working from disk only.
    """
    creds = _rest_credentials()
    if creds is None:
        return None
    try:
        return _Rest(*creds)
    except Exception:  # noqa: BLE001 — bridge availability must not take UI down
        return None


def _record_snapshot_source(
    module: str, source: str | None, period: str | None
) -> None:
    """Stash where the snapshot came from so ``render()`` can caption it."""
    st.session_state[f"_meli_last_source_{module}"] = source
    st.session_state[f"_meli_last_source_period_{module}"] = period


_MODULE_LABEL = {
    config.MODULO_RENDIMIENTO: "Rendimiento",
    config.MODULO_PUBLICACIONES: "Publicaciones",
    config.MODULO_ADS: "Ads",
}


def _render_source_captions() -> None:
    """Emit one caption per module explaining where the snapshot came from.

    Reads flags stashed by ``_latest_snapshot`` in session state. Uses a
    single line per module so the top of the page stays compact.
    """
    lines: list[str] = []
    for module, label in _MODULE_LABEL.items():
        source = st.session_state.get(f"_meli_last_source_{module}")
        period = st.session_state.get(f"_meli_last_source_period_{module}")
        if source == "api" and period:
            lines.append(f"**{label}** · 🔌 datos vía API · actualizado {period}")
        elif source == "api":
            lines.append(f"**{label}** · 🔌 datos vía API")
        elif source == "excel" and period:
            lines.append(f"**{label}** · 📄 último Excel · {period}")
        elif source == "excel":
            lines.append(f"**{label}** · 📄 último Excel")
    if lines:
        st.caption(" · ".join(lines))


def _latest_api_ingest_date(rest, cliente: str, module: str) -> str | None:
    """Ask the DB for the freshest ingest date for this module + client.

    Returns the ISO date (``2026-09-03``) of the newest row the worker wrote
    to the module's data table, or ``None`` if nothing has been ingested yet.
    Read-only, no writes; failures degrade to ``None`` so a stale DB never
    breaks the source caption.
    """
    entry = _API_MAX_DATE_QUERY.get(module)
    if entry is None:
        return None
    table, date_col = entry
    try:
        # Resolve identity id from the connection row; kept narrow so a
        # missing/inactive identity yields no date instead of raising.
        conx_rows = rest.select(
            "integration_connections",
            {
                "select": "cuenta_externa_id",
                "integration_slug": "eq.mercado_libre",
                "cliente": f"eq.{cliente}",
                "estado": "eq.activo",
                "limit": "1",
            },
        )
        if not conx_rows:
            return None
        external_id = str(conx_rows[0].get("cuenta_externa_id") or "").strip()
        if not external_id:
            return None
        ident_rows = rest.select(
            "meli_auth_identities",
            {"select": "id", "user_id": f"eq.{external_id}", "limit": "1"},
        )
        if not ident_rows:
            return None
        identity_id = ident_rows[0]["id"]
        rows = rest.select(
            table,
            {
                "select": date_col,
                "identity_id": f"eq.{identity_id}",
                "order": f"{date_col}.desc",
                "limit": "1",
            },
        )
    except Exception:  # noqa: BLE001 — never let a stale DB break the caption
        return None
    if not rows:
        return None
    return str(rows[0].get(date_col) or "") or None


def _latest_snapshot(account: str, module: str) -> pd.DataFrame | None:
    """Return the freshest snapshot for (account, module), or ``None``.

    Sourcing preference:
      1. API bridge (``origen='api'``) when the portal DB is reachable AND an
         active ``meli_auth_identity`` exists for the cliente AND the bridge
         returns a non-empty DataFrame.
      2. Local Parquet snapshot on disk (``origen='excel'``) as a fallback.

    The chosen source is recorded in ``st.session_state`` so ``render()`` can
    show a small "🔌 datos vía API" / "📄 último Excel · <fecha>" caption at
    the top of every tab. The DataFrame contract stays intact — the ``origen``
    column tells downstream which rows came from where when frames grow the
    ability to blend both sources (not the case today).
    """
    rest = _open_rest()
    if rest is not None:
        builder_name = _API_BUILDER_NAMES.get(module)
        builder = getattr(api_bridge, builder_name, None) if builder_name else None
        if builder is not None:
            try:
                df = builder(rest, account, "")
            except Exception:  # noqa: BLE001 — never let the bridge break UI
                df = None
            if df is not None and not df.empty:
                # Show the freshest row date so the caption reads
                # "🔌 datos vía API · actualizado 2026-09-03".
                _record_snapshot_source(
                    module, "api", _latest_api_ingest_date(rest, account, module)
                )
                return df

    periods = _list_periods(config.AREA, account, module)
    if not periods:
        _record_snapshot_source(module, None, None)
        return None
    _record_snapshot_source(module, "excel", periods[-1])
    return _load_snapshot(config.AREA, account, module, periods[-1])


def render(username: str = "", role: str = roles.USER) -> None:
    """Module entry point. Called from app.py with user and role.

    All five tabs (Cambios, Stock, Ads, Importar, Admin) are open to every
    employee: the AM sits with the seller at onboarding and any AM may
    need to fix a bad snapshot. ``role`` is still accepted so future
    read-only variants can flip a subset off without changing the caller.
    """
    _ = role  # future: gate a read-only variant here
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    # Account management lives in Sistema → Cuentas so a single vendor
    # session serves every module that touches the same marketplace. Here
    # we only pick from what is already connected.
    accounts = _list_accounts()
    col_pick, col_new = st.columns([5, 1], vertical_alignment="bottom")
    if accounts:
        account = col_pick.selectbox(
            "Cuenta", options=[a["slug"] for a in accounts], key="meli_cuenta",
            format_func=lambda slug: _account_label(slug, accounts),
            label_visibility="collapsed",
        )
    else:
        account = None
        col_pick.caption("Todavía no hay cuentas.")
    if col_new.button("➕ Manual", key="meli_btn_manual",
                      use_container_width=True,
                      help="Crear una cuenta para subir los Excel a mano, sin "
                           "conectar el vendedor por OAuth."):
        _dialog_manual_account()

    st.caption(
        "Para conectar el vendedor y traer los datos por API, andá a "
        "**⚙️ Sistema → 🔑 Cuentas conectadas**."
    )

    if not account:
        empty_state(
            "📂 No hay cuentas de Mercado Libre",
            "Dos caminos: conectá el vendedor desde **⚙️ Sistema → "
            "🔑 Cuentas conectadas** para que los datos lleguen solos por "
            "API, o creá una **cuenta manual** acá arriba y subí los tres "
            "Excel a mano.",
        )
        return

    # Onboarding safety net: a fresh OAuth connection has no `data/marketplaces/<slug>/`
    # directory yet. Create the client-config so the first Excel upload doesn't
    # fail on "directory missing".
    _ensure_client_dir(account)

    st.divider()

    performance = _latest_snapshot(account, config.MODULO_RENDIMIENTO)
    listings = _latest_snapshot(account, config.MODULO_PUBLICACIONES)
    ads = _latest_snapshot(account, config.MODULO_ADS)

    # Small source caption per module. Tells the AM at a glance whether the
    # numbers below came from the live API or the last Excel upload — the
    # difference matters when the account has been silent for a while and
    # the Excel side is stale.
    _render_source_captions()

    days_in_period = None
    if performance is not None and not performance.empty and "dias" in performance:
        days_in_period = int(performance["dias"].iloc[0])

    # Admin is now open to every employee (the seller sits with them at
    # onboarding and any AM may need to fix a bad snapshot). `_admin_tab`
    # deletes snapshots without an extra confirmation step, so the label
    # keeps the ⚙️ prefix as a visual cue that this is where destructive
    # actions live.
    tab_labels = ["📈 Cambios", "📦 Stock", "🎯 Ads", "📤 Importar", "⚙️ Admin"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        vista_tracker.render(account, listings)
    with tabs[1]:
        vista_stock.render(account, performance, listings, days_in_period)
    with tabs[2]:
        vista_alertas.render(account, ads)
    with tabs[3]:
        _import_tab(account)
    with tabs[4]:
        _admin_tab(account, username)
