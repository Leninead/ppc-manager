"""
Modulo: Mercado Libre (M36)
Seccion: Marketplaces
Version: v1
Autor: Lenin Acosta
Creado: 2026-07-24

Módulo de operación de cuentas de Mercado Libre. Tres features pedidas por el
equipo de cuentas:

  1. Seguimiento de cambios en publicaciones — equivalente MELI del SKU Progress
     Report: mide el impacto de cada modificación sobre visitas y conversión.
  2. Sugerencia de reposición de stock — proyecta cobertura sobre la velocidad
     de venta y descuenta lo que ya viene en camino.
  3. Alertas de campañas — semáforo por ACOS y ROAS sobre el reporte de ads.

Persiste vía core.persistence:
  - Snapshots en data/marketplaces/<cuenta>/meli-{rendimiento,publicaciones,ads}/<YYYY-MM-DD>.parquet
  - Log de cambios en meli-rendimiento/cambios.parquet
  - Log de tránsito en meli-publicaciones/transito.parquet

Schemas validados: data/_schemas/meli-{rendimiento,stock,ads}-v1.json

El period es la fecha de fin del reporte (YYYY-MM-DD) y no la semana ISO: los
períodos que exporta Mercado Libre no caen en semanas calendario.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
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


def _slug(texto: str) -> str:
    """Convierte el nombre de la cuenta en un slug kebab-case."""
    normalizado = unicodedata.normalize("NFKD", str(texto))
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    normalizado = re.sub(r"[^a-zA-Z0-9]+", "-", normalizado).strip("-")
    return normalizado.lower()


def _header() -> None:
    st.markdown("## 🛒 Mercado Libre")
    st.caption(
        "📥 Inputs: reporte de rendimiento, export de publicaciones y reporte de "
        "Product Ads · Output: seguimiento de cambios, sugerencia de stock y "
        "alertas de campañas"
    )
    st.divider()


@st.dialog("Agregar cuenta de Mercado Libre")
def _dialogo_agregar_cuenta() -> None:
    nombre = st.text_input(
        "Nombre de la cuenta", key="meli_alta_cuenta",
        placeholder="Ej: nombre del cliente o de la tienda",
    )
    if nombre.strip():
        slug = _slug(nombre)
        st.caption(f"Slug generado: `{slug}`")
        if slug in _list_clientes(config.AREA, config.MODULO_RENDIMIENTO):
            st.warning(f"La cuenta '{slug}' ya existe.")

    col_cancelar, col_crear = st.columns(2)
    if col_cancelar.button("Cancelar", key="meli_alta_cancel",
                           use_container_width=True):
        st.rerun()
    if col_crear.button("Crear cuenta", key="meli_alta_ok", type="primary",
                        use_container_width=True):
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
            return
        slug = _slug(nombre)
        if slug in _list_clientes(config.AREA, config.MODULO_RENDIMIENTO):
            st.error(f"La cuenta '{slug}' ya existe.")
            return
        _save_client_config(
            {"version": 1, "cuenta": slug, "nombre": nombre.strip()},
            config.AREA, slug, config.MODULO_RENDIMIENTO, "cuenta",
        )
        st.success(f"Cuenta '{slug}' creada. Ya podés importar sus reportes.")
        st.rerun()


def _importar(cuenta: str) -> None:
    """Pestaña de carga de los tres reportes."""
    st.markdown("### 📤 Importar reportes")
    st.caption(
        "Cada reporte se guarda como un snapshot con su propio período. "
        "Subir el mismo archivo dos veces sobrescribe el snapshot, no lo duplica."
    )

    st.markdown("#### 1. Rendimiento de publicaciones")
    archivo_rendimiento = st.file_uploader(
        "Reporte de métricas de publicaciones", type=["xlsx"],
        key="meli_up_rendimiento",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre → Métricas → Publicaciones → Descargar reporte.",
    )
    if archivo_rendimiento:
        try:
            reporte = parser_rendimiento.parsear(archivo_rendimiento)
        except parser_rendimiento.ErrorFormato as error:
            st.error(f"⚠ {error}")
        else:
            period = reporte.hasta.isoformat()
            datos = reporte.datos.copy()
            datos["desde"] = datos["desde"].map(lambda f: f.isoformat())
            datos["hasta"] = datos["hasta"].map(lambda f: f.isoformat())
            datos["dias"] = reporte.dias

            st.success(
                f"✓ {len(datos)} publicaciones · período {reporte.desde} → "
                f"{reporte.hasta} ({reporte.dias} días)"
            )
            st.dataframe(datos.head(8), use_container_width=True, hide_index=True)

            if period in _list_periods(config.AREA, cuenta, config.MODULO_RENDIMIENTO):
                st.warning(f"Ya existe un snapshot para {period}: se sobrescribe.")

            if st.button("✓ Guardar rendimiento", type="primary",
                         key="meli_guardar_rendimiento"):
                errores = _validate_against_schema(
                    datos, config.MODULO_RENDIMIENTO, config.SCHEMA_VERSION
                )
                if errores:
                    st.error("El snapshot no respeta el schema:")
                    for detalle in errores:
                        st.caption(f"• {detalle}")
                else:
                    _save_snapshot(datos, config.AREA, cuenta,
                                   config.MODULO_RENDIMIENTO, period)
                    try:
                        _rebuild_history(config.AREA, cuenta,
                                         config.MODULO_RENDIMIENTO)
                    except FileNotFoundError:
                        pass
                    st.success(f"✓ Snapshot {period} guardado.")
                    st.rerun()

    st.divider()
    st.markdown("#### 2. Publicaciones y stock")
    archivo_publicaciones = st.file_uploader(
        "Export de 'Modifica tus publicaciones'", type=["xlsx"],
        key="meli_up_publicaciones",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre → Publicaciones → Modificar masivamente → Descargar.",
    )
    if archivo_publicaciones:
        try:
            publicaciones = parser_publicaciones.parsear(archivo_publicaciones)
        except parser_publicaciones.ErrorFormato as error:
            st.error(f"⚠ {error}")
        else:
            st.success(
                f"✓ {len(publicaciones)} publicaciones activas · "
                f"{int(publicaciones['stock'].sum()):,} unidades en stock"
                .replace(",", ".")
            )
            st.dataframe(publicaciones.head(8), use_container_width=True,
                         hide_index=True)
            period = st.date_input(
                "Fecha del export", key="meli_fecha_publicaciones",
                help="Se usa como período del snapshot.",
            ).isoformat()

            if st.button("✓ Guardar publicaciones", type="primary",
                         key="meli_guardar_publicaciones"):
                errores = _validate_against_schema(
                    publicaciones, config.MODULO_PUBLICACIONES,
                    config.SCHEMA_VERSION
                )
                if errores:
                    st.error("El snapshot no respeta el schema:")
                    for detalle in errores:
                        st.caption(f"• {detalle}")
                else:
                    _save_snapshot(publicaciones, config.AREA, cuenta,
                                   config.MODULO_PUBLICACIONES, period)
                    try:
                        _rebuild_history(config.AREA, cuenta,
                                         config.MODULO_PUBLICACIONES)
                    except FileNotFoundError:
                        pass
                    st.success(f"✓ Snapshot {period} guardado.")
                    st.rerun()

    st.divider()
    st.markdown("#### 3. Reporte de Product Ads")
    archivo_ads = st.file_uploader(
        "Reporte por anuncios", type=["xlsx"], key="meli_up_ads",
        help="Arrastrá o elegí el archivo .xlsx (máximo 200 MB por archivo). "
             "Sale de Mercado Libre Ads → Reportes → Reporte por anuncios.",
    )
    if archivo_ads:
        try:
            reporte_ads = parser_ads.parsear(archivo_ads)
        except parser_ads.ErrorFormato as error:
            st.error(f"⚠ {error}")
        else:
            datos = reporte_ads.datos.copy()
            datos["desde"] = datos["desde"].map(
                lambda f: f.isoformat() if f else None)
            datos["hasta"] = datos["hasta"].map(
                lambda f: f.isoformat() if f else None)
            period = (reporte_ads.hasta or pd.Timestamp.today().date()).isoformat()

            st.success(
                f"✓ {len(datos)} anuncios · {datos['campana'].nunique()} campañas "
                f"· período {reporte_ads.desde} → {reporte_ads.hasta}"
            )
            st.dataframe(datos.head(8), use_container_width=True, hide_index=True)

            if st.button("✓ Guardar ads", type="primary", key="meli_guardar_ads"):
                _save_snapshot(datos, config.AREA, cuenta, config.MODULO_ADS,
                               period)
                try:
                    _rebuild_history(config.AREA, cuenta, config.MODULO_ADS)
                except FileNotFoundError:
                    pass
                st.success(f"✓ Snapshot {period} guardado.")
                st.rerun()


def _administrar(cuenta: str) -> None:
    """Pestaña de administración de snapshots por módulo."""
    st.markdown("### ⚙️ Administrar snapshots")
    modulos = [
        ("Rendimiento", config.MODULO_RENDIMIENTO),
        ("Stock", config.MODULO_PUBLICACIONES),
        ("Ads", config.MODULO_ADS),
    ]
    columnas = st.columns(3)
    for columna, (etiqueta, modulo) in zip(columnas, modulos):
        with columna:
            st.markdown(f"#### {etiqueta}")
            periodos = _list_periods(config.AREA, cuenta, modulo)
            if not periodos:
                st.caption("Sin snapshots todavía.")
                continue
            for period in periodos:
                col_info, col_borrar = st.columns([3, 1])
                col_info.markdown(f"**{period}**")
                if col_borrar.button("🗑️", key=f"meli_del_{modulo}_{period}",
                                      help="Borrar este snapshot"):
                    if _delete_snapshot(config.AREA, cuenta, modulo, period):
                        try:
                            _rebuild_history(config.AREA, cuenta, modulo)
                        except FileNotFoundError:
                            pass
                        st.success(f"Snapshot {period} eliminado.")
                        st.rerun()


def _ultimo_snapshot(cuenta: str, modulo: str) -> pd.DataFrame | None:
    """Devuelve el snapshot más reciente del módulo, o None si no hay ninguno."""
    periodos = _list_periods(config.AREA, cuenta, modulo)
    if not periodos:
        return None
    return _load_snapshot(config.AREA, cuenta, modulo, periodos[-1])


def render() -> None:
    """Punto de entrada del módulo. Llamado desde app.py."""
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    cuentas = _list_clientes(config.AREA, config.MODULO_RENDIMIENTO)
    col_selector, col_alta = st.columns([5, 2])
    with col_selector:
        if cuentas:
            cuenta = st.selectbox(
                "Cuenta", options=cuentas, key="meli_cuenta",
                format_func=lambda valor: f"🛒 {valor}",
            )
        else:
            cuenta = None
            st.caption("Todavía no hay cuentas cargadas.")
    with col_alta:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("➕ Cuenta nueva", key="meli_btn_alta",
                     use_container_width=True):
            _dialogo_agregar_cuenta()

    if not cuenta:
        empty_state(
            "📂 No hay cuentas de Mercado Libre cargadas",
            "Creá la primera cuenta para empezar a importar sus reportes.",
        )
        return

    st.divider()

    rendimiento = _ultimo_snapshot(cuenta, config.MODULO_RENDIMIENTO)
    publicaciones = _ultimo_snapshot(cuenta, config.MODULO_PUBLICACIONES)
    ads = _ultimo_snapshot(cuenta, config.MODULO_ADS)

    dias_periodo = None
    if rendimiento is not None and not rendimiento.empty and "dias" in rendimiento:
        dias_periodo = int(rendimiento["dias"].iloc[0])

    pestanas = st.tabs([
        "📈 Cambios", "📦 Stock", "🎯 Ads", "📤 Importar", "⚙️ Admin",
    ])

    with pestanas[0]:
        vista_tracker.render(cuenta, publicaciones)
    with pestanas[1]:
        vista_stock.render(cuenta, rendimiento, publicaciones, dias_periodo)
    with pestanas[2]:
        vista_alertas.render(cuenta, ads)
    with pestanas[3]:
        _importar(cuenta)
    with pestanas[4]:
        _administrar(cuenta)
