import io
import re

import streamlit as st
import pandas as pd


@st.cache_data
def _load_bulk(data, name):
    """Cached reader for Bulk/Campaign CSV files."""
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


# ── Naming convention Capybaras: [Marca] | [ASIN] | [MKT] | [Tipo] | [Match] | [Cluster]
_NAMING_PATTERN = re.compile(
    r'^[^|]+\|'    # Marca
    r'\s*B0[A-Z0-9]{8}\s*\|'  # ASIN
    r'[^|]+\|'    # MKT (SP/SB/SD)
    r'[^|]+\|'    # Tipo (KW/PAT/AUTO)
    r'[^|]+\|'    # Match (Exact/Broad/Phrase)
    r'.+$',       # Cluster
    re.IGNORECASE
)

_NAMING_LOOSE = re.compile(r'B0[A-Z0-9]{8}', re.IGNORECASE)


def _check_naming(name):
    """Retorna (is_capybaras, has_asin) para un campaign name."""
    n = str(name).strip()
    is_capy = bool(_NAMING_PATTERN.match(n))
    has_asin = bool(_NAMING_LOOSE.search(n))
    return is_capy, has_asin


def render():
    st.header("📁 Bulk File de Campañas")
    st.caption("Archivo bulk exportado desde Amazon Ads con todas las campañas, grupos y keywords.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Ver estructura de campañas y diagnosticar estado con semáforo automático (pausar/revisar/escalar/fantasmas).")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Campaign CSV → Amazon Ads → Campaign Manager → Export con todas las métricas (.csv).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Business Report (M7) para cruzar con salud del catálogo.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el Campaign CSV\n"
            "2. Ingresá Target ACoS + precio promedio\n"
            "3. Tab Campaign Analyzer: revisá semáforo (PAUSAR, REVISAR, ESCALAR, FANTASMA)\n"
            "4. Tab Auditoría: revisá naming convention y target graduation\n"
            "5. Descargá el Excel y pausá manualmente en Campaign Manager las rojas"
        )

    file_bulk = st.file_uploader("Sube tu Bulk o Campaign CSV (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk")
    if file_bulk:
        df_bulk_raw = _load_bulk(file_bulk.getvalue(), file_bulk.name)
        st.success(f"✅ {len(df_bulk_raw)} filas cargadas")

        bulk_tab1, bulk_tab2 = st.tabs(["📋 Vista General", "🚦 Campaign Analyzer"])

        # ══════════════════════════════════════════════════════════════════
        # TAB 1 — Vista General (raw)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab1:
            st.dataframe(df_bulk_raw, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════
        # TAB 2 — Campaign Analyzer (Auditoría PPC)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab2:
            st.markdown("### 🚦 Campaign Analyzer")
            st.caption("Diagnóstico automático de campañas. Los thresholds los define el AM según el objetivo de la cuenta.")

            # ── Detectar si el archivo tiene columnas de performance ──────
            _REQUIRED_PERF = ["Total cost", "Sales", "Purchases"]
            _missing_perf = [c for c in _REQUIRED_PERF if c not in df_bulk_raw.columns]
            has_perf = not _missing_perf
            _has_impr = "Impressions" in df_bulk_raw.columns

            if not has_perf:
                st.warning(
                    f"⚠️ Este archivo no tiene columnas de performance ({', '.join(_missing_perf)}). "
                    "Subí el Campaign CSV descargado desde Campaign Manager con métricas incluidas."
                )
            else:
                # ── Preparar dataframe limpio ─────────────────────────────
                df_ca = df_bulk_raw.copy()

                def _clean_money(series):
                    return pd.to_numeric(
                        series.astype(str).str.replace(r'[\$,]', '', regex=True),
                        errors='coerce'
                    ).fillna(0)

                df_ca['_spend']   = _clean_money(df_ca['Total cost'])
                df_ca['_sales']   = _clean_money(df_ca['Sales'])
                df_ca['_acos']    = pd.to_numeric(df_ca['ACOS'], errors='coerce').fillna(0) * 100
                df_ca['_orders']  = pd.to_numeric(df_ca['Purchases'], errors='coerce').fillna(0)
                df_ca['_impr']    = (
                    pd.to_numeric(df_ca['Impressions'], errors='coerce').fillna(0)
                    if _has_impr else None
                )
                df_ca['_clicks']  = pd.to_numeric(df_ca['Clicks'], errors='coerce').fillna(0) if 'Clicks' in df_ca.columns else 0

                # Solo campañas ENABLED
                df_ca = df_ca[df_ca['State'].str.upper() == 'ENABLED'].copy()

                # ── Inputs del AM ─────────────────────────────────────────
                st.markdown("#### ⚙️ Configuración de la cuenta")
                cfg1, cfg2, cfg3 = st.columns(3)
                target_acos_ca = cfg1.number_input(
                    "Target ACoS (%)",
                    min_value=1.0, max_value=200.0, value=35.0, step=1.0,
                    help="ACoS objetivo para esta cuenta. Define los umbrales de REVISAR y ESCALAR."
                )
                spend_pausar = cfg2.number_input(
                    "Spend mínimo para PAUSAR ($)",
                    min_value=1.0, value=20.0, step=1.0,
                    help="Spend acumulado sin órdenes a partir del cual se recomienda pausar. El AM lo ajusta según el objetivo de la cuenta."
                )
                min_orders_escalar = cfg3.number_input(
                    "Mínimo de órdenes para ESCALAR",
                    min_value=1, value=2, step=1,
                    help="Órdenes mínimas confirmadas para recomendar escalar."
                )

                st.markdown("---")

                # ── Función de diagnóstico ────────────────────────────────
                def _diagnostico(row):
                    spend   = row['_spend']
                    acos    = row['_acos']
                    orders  = row['_orders']
                    impr    = row['_impr']

                    if spend == 0 and (impr == 0 if _has_impr else row['_clicks'] == 0):
                        return "👻 FANTASMA"
                    if orders == 0 and spend >= spend_pausar:
                        return "🔴 PAUSAR"
                    if orders > 0 and acos > target_acos_ca * 2:
                        return "🟡 REVISAR"
                    if orders >= min_orders_escalar and acos <= target_acos_ca * 0.5:
                        return "✅ ESCALAR"
                    return "⚪ OK"

                df_ca['Diagnóstico'] = df_ca.apply(_diagnostico, axis=1)

                # ── Naming convention check ──────────────────────────────
                camp_col = 'Campaign name'
                if camp_col in df_ca.columns:
                    naming_results = df_ca[camp_col].apply(_check_naming)
                    df_ca['_naming_capy'] = naming_results.apply(lambda x: x[0])
                    df_ca['_naming_asin'] = naming_results.apply(lambda x: x[1])

                    n_capy = df_ca['_naming_capy'].sum()
                    n_asin_only = (~df_ca['_naming_capy'] & df_ca['_naming_asin']).sum()
                    n_bad = (~df_ca['_naming_capy'] & ~df_ca['_naming_asin']).sum()

                    df_ca['Naming'] = df_ca.apply(
                        lambda r: "✅ Capybaras" if r['_naming_capy']
                        else ("🟡 Tiene ASIN" if r['_naming_asin'] else "🔴 Sin estándar"),
                        axis=1
                    )

                # ── Target Graduation (si hay columna Targeting) ─────────
                tgt_col = next((c for c in df_ca.columns if 'targeting' in c.lower() and 'type' not in c.lower()), None)
                has_tgt_graduation = False
                df_tgt_dead = pd.DataFrame()
                if tgt_col and _has_impr:
                    # Targets con 0 impresiones = candidatos a pausar
                    tgt_rows = df_ca[df_ca[tgt_col].notna() & (df_ca[tgt_col].astype(str).str.strip() != "")]
                    if not tgt_rows.empty:
                        df_tgt_dead = tgt_rows[tgt_rows['_impr'] == 0].copy()
                        has_tgt_graduation = len(df_tgt_dead) > 0

                # ── KPIs globales ─────────────────────────────────────────
                total_spend   = df_ca['_spend'].sum()
                total_sales   = df_ca['_sales'].sum()
                total_acos    = (total_spend / total_sales * 100) if total_sales > 0 else 0
                spend_recup   = df_ca[df_ca['Diagnóstico'] == '🔴 PAUSAR']['_spend'].sum()

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Campañas analizadas", len(df_ca))
                k2.metric("Total Spend", f"${total_spend:,.2f}")
                k3.metric("Total Sales", f"${total_sales:,.2f}")
                k4.metric("ACoS cuenta", f"{total_acos:.1f}%")
                k5.metric("💰 Spend recuperable", f"${spend_recup:,.2f}",
                          help="Spend acumulado en campañas marcadas como PAUSAR")

                if not _has_impr:
                    st.caption(
                        "ℹ️ El archivo no incluye la columna **Impressions**. "
                        "El diagnóstico FANTASMA se calcula con Clicks y la sección "
                        "Target Graduation queda desactivada. El resto del análisis no cambia."
                    )

                # ── Conteo por diagnóstico ────────────────────────────────
                st.markdown("#### Resumen por diagnóstico")
                diag_counts = df_ca['Diagnóstico'].value_counts()
                dc1, dc2, dc3, dc4, dc5 = st.columns(5)
                dc1.metric("👻 Fantasmas",  diag_counts.get("👻 FANTASMA", 0))
                dc2.metric("🔴 Pausar",     diag_counts.get("🔴 PAUSAR", 0))
                dc3.metric("🟡 Revisar",    diag_counts.get("🟡 REVISAR", 0))
                dc4.metric("✅ Escalar",    diag_counts.get("✅ ESCALAR", 0))
                dc5.metric("⚪ OK",         diag_counts.get("⚪ OK", 0))

                # ── Naming convention resumen ────────────────────────────
                if camp_col in df_ca.columns:
                    st.markdown("#### Naming Convention")
                    nc1, nc2, nc3 = st.columns(3)
                    nc1.metric("✅ Capybaras estándar", int(n_capy))
                    nc2.metric("🟡 Tiene ASIN (parcial)", int(n_asin_only))
                    nc3.metric("🔴 Sin estándar", int(n_bad))

                    if n_bad > 0:
                        with st.expander(f"Ver {int(n_bad)} campañas sin naming estándar"):
                            df_bad_naming = df_ca[~df_ca['_naming_capy'] & ~df_ca['_naming_asin']][[camp_col, '_spend', '_orders']].copy()
                            df_bad_naming.columns = ['Campaign', 'Spend', 'Orders']
                            st.dataframe(df_bad_naming.sort_values('Spend', ascending=False), use_container_width=True, hide_index=True)

                # ── Target Graduation ─────────────────────────────────────
                if has_tgt_graduation:
                    st.markdown("#### Target Graduation")
                    st.caption(f"**{len(df_tgt_dead)} targets** con 0 impresiones en el período completo. Candidatos a pausar.")
                    with st.expander(f"Ver {len(df_tgt_dead)} targets sin impresiones"):
                        tgt_show_cols = [camp_col, tgt_col, '_spend', '_clicks']
                        tgt_show_cols = [c for c in tgt_show_cols if c in df_tgt_dead.columns]
                        st.dataframe(
                            df_tgt_dead[tgt_show_cols].rename(columns={'_spend': 'Spend', '_clicks': 'Clicks'}),
                            use_container_width=True, hide_index=True
                        )

                st.markdown("---")

                # ── Filtro por diagnóstico ────────────────────────────────
                opciones_diag = ["Todos"] + sorted(df_ca['Diagnóstico'].unique().tolist())
                filtro_diag = st.selectbox("Filtrar por diagnóstico", opciones_diag, key="ca_filtro_diag")

                df_show = df_ca if filtro_diag == "Todos" else df_ca[df_ca['Diagnóstico'] == filtro_diag]

                # ── Tabla semáforo ────────────────────────────────────────
                show_cols = ['Diagnóstico', 'Campaign name', 'Portfolio name',
                             '_spend', '_sales', '_acos', '_orders', '_impr', '_clicks']
                if camp_col in df_ca.columns and '_naming_capy' in df_ca.columns:
                    show_cols.insert(2, 'Naming')
                if 'Campaign start date' in df_show.columns:
                    show_cols.append('Campaign start date')
                if 'Campaign bid strategy' in df_show.columns:
                    show_cols.append('Campaign bid strategy')

                if not _has_impr:
                    show_cols = [c for c in show_cols if c != '_impr']

                rename_map = {
                    '_spend': 'Spend ($)',
                    '_sales': 'Sales ($)',
                    '_acos': 'ACoS (%)',
                    '_orders': 'Purchases',
                    '_impr': 'Impressions',
                    '_clicks': 'Clicks',
                }

                df_tabla = (
                    df_show[[c for c in show_cols if c in df_show.columns]]
                    .rename(columns=rename_map)
                    .sort_values('Diagnóstico')
                    .reset_index(drop=True)
                )

                # Color de fondo por diagnóstico
                def _color_diag(val):
                    colors = {
                        "🔴 PAUSAR":  "background-color: #FFEBEE",
                        "🟡 REVISAR": "background-color: #FFFDE7",
                        "✅ ESCALAR": "background-color: #E8F5E9",
                        "👻 FANTASMA":"background-color: #F5F5F5",
                        "⚪ OK":      "",
                    }
                    return colors.get(val, "")

                style_subsets = ['Diagnóstico']
                styled = df_tabla.style.map(_color_diag, subset=style_subsets)
                st.dataframe(styled, use_container_width=True, height=500)

                # ── Nota aclaratoria ──────────────────────────────────────
                st.info("💡 **Las pausas se ejecutan manualmente en Campaign Manager.** El bulk update requiere Campaign ID numérico — este diagnóstico es tu guía de acción.")

                # ── Export ────────────────────────────────────────────────
                buf_ca = io.BytesIO()
                with pd.ExcelWriter(buf_ca, engine="openpyxl") as writer:
                    df_tabla.to_excel(writer, sheet_name="Diagnóstico", index=False)
                    if has_tgt_graduation and not df_tgt_dead.empty:
                        tgt_export = df_tgt_dead[tgt_show_cols].rename(columns={'_spend': 'Spend', '_clicks': 'Clicks'})
                        tgt_export.to_excel(writer, sheet_name="Targets 0 Impr", index=False)
                st.download_button(
                    label=f"⬇️ Exportar diagnóstico ({len(df_tabla)} campañas)",
                    data=buf_ca.getvalue(),
                    file_name="campaign_analyzer.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_ca"
                )
