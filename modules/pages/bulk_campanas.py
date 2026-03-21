import streamlit as st
import pandas as pd
import io as _io_ca


def render():
    st.header("📁 Bulk File de Campañas")
    st.caption("Archivo bulk exportado desde Amazon Ads con todas las campañas, grupos y keywords.")
    st.divider()
    file_bulk = st.file_uploader("Sube tu Bulk o Campaign CSV (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk")
    if file_bulk:
        df_bulk_raw = pd.read_excel(file_bulk) if file_bulk.name.endswith(".xlsx") else pd.read_csv(file_bulk)
        st.success(f"✅ {len(df_bulk_raw)} filas cargadas")

        bulk_tab1, bulk_tab2 = st.tabs(["📋 Vista General", "🚦 Campaign Analyzer"])

        # ══════════════════════════════════════════════════════════════════
        # TAB 1 — Vista General (raw)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab1:
            st.dataframe(df_bulk_raw, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════
        # TAB 2 — Campaign Analyzer
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab2:
            st.markdown("### 🚦 Campaign Analyzer")
            st.caption("Diagnóstico automático de campañas. Los thresholds los define el AM según el objetivo de la cuenta.")

            # ── Detectar si el archivo tiene columnas de performance ──────
            has_perf = all(c in df_bulk_raw.columns for c in ["Total cost", "Sales", "Purchases", "Impressions"])

            if not has_perf:
                st.warning("⚠️ Este archivo no tiene columnas de performance (Spend, Sales, Purchases, Impressions). Subí el Campaign CSV descargado desde Campaign Manager con métricas incluidas.")
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
                df_ca['_impr']    = pd.to_numeric(df_ca['Impressions'], errors='coerce').fillna(0)
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

                    if impr == 0 and spend == 0:
                        return "👻 FANTASMA"
                    if orders == 0 and spend >= spend_pausar:
                        return "🔴 PAUSAR"
                    if orders > 0 and acos > target_acos_ca * 2:
                        return "🟡 REVISAR"
                    if orders >= min_orders_escalar and acos <= target_acos_ca * 0.5:
                        return "✅ ESCALAR"
                    return "⚪ OK"

                df_ca['Diagnóstico'] = df_ca.apply(_diagnostico, axis=1)

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

                # ── Conteo por diagnóstico ────────────────────────────────
                st.markdown("#### Resumen por diagnóstico")
                diag_counts = df_ca['Diagnóstico'].value_counts()
                dc1, dc2, dc3, dc4, dc5 = st.columns(5)
                dc1.metric("👻 Fantasmas",  diag_counts.get("👻 FANTASMA", 0))
                dc2.metric("🔴 Pausar",     diag_counts.get("🔴 PAUSAR", 0))
                dc3.metric("🟡 Revisar",    diag_counts.get("🟡 REVISAR", 0))
                dc4.metric("✅ Escalar",    diag_counts.get("✅ ESCALAR", 0))
                dc5.metric("⚪ OK",         diag_counts.get("⚪ OK", 0))

                st.markdown("---")

                # ── Filtro por diagnóstico ────────────────────────────────
                opciones_diag = ["Todos"] + sorted(df_ca['Diagnóstico'].unique().tolist())
                filtro_diag = st.selectbox("Filtrar por diagnóstico", opciones_diag, key="ca_filtro_diag")

                df_show = df_ca if filtro_diag == "Todos" else df_ca[df_ca['Diagnóstico'] == filtro_diag]

                # ── Tabla semáforo ────────────────────────────────────────
                show_cols = ['Diagnóstico', 'Campaign name', 'Portfolio name',
                             '_spend', '_sales', '_acos', '_orders', '_impr', '_clicks']
                if 'Campaign start date' in df_show.columns:
                    show_cols.append('Campaign start date')
                if 'Campaign bid strategy' in df_show.columns:
                    show_cols.append('Campaign bid strategy')

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

                styled = df_tabla.style.map(_color_diag, subset=['Diagnóstico'])
                st.dataframe(styled, use_container_width=True, height=500)

                # ── Nota aclaratoria ──────────────────────────────────────
                st.info("💡 **Las pausas se ejecutan manualmente en Campaign Manager.** El bulk update requiere Campaign ID numérico — este diagnóstico es tu guía de acción.")

                # ── Export ────────────────────────────────────────────────
                buf_ca = _io_ca.BytesIO()
                df_tabla.to_excel(buf_ca, index=False)
                st.download_button(
                    label=f"⬇️ Exportar diagnóstico ({len(df_tabla)} campañas)",
                    data=buf_ca.getvalue(),
                    file_name="campaign_analyzer.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_ca"
                )
