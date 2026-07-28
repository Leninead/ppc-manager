import io
import re

import streamlit as st
import pandas as pd


@st.cache_data
def _load_file(data, name):
    """Cached reader for uploaded files."""
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


def render():
    st.header("🔻 Análisis de Funnel")
    st.caption("Analizá cobertura de campañas activas, detectá brechas y generá sugerencias de harvesting.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Detectar brechas en el funnel Auto → Broad → Phrase → Exact por ASIN y sugerir campañas faltantes.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("STR (.xlsx/.csv) + Bulk file de campañas (.xlsx).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Bid Optimizer (M9) para recalcular bids de las nuevas campañas.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí STR y Bulk\n"
            "2. Ingresá Target ACoS\n"
            "3. Revisá mapa de funnel actual por ASIN\n"
            "4. Revisá campañas sugeridas con naming Capybaras\n"
            "5. Descargá bulk con nuevas campañas"
        )

    st.info("Subí el Bulk de campañas y el STR para ver cobertura por campaña.")

    col_bulk_f, col_str_f = st.columns(2)
    with col_bulk_f:
        file_bulk_f = st.file_uploader("Bulk de campañas (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk_f")
    with col_str_f:
        file_str_f = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_f")

    if file_bulk_f:
        df_bulk = _load_file(file_bulk_f.getvalue(), file_bulk_f.name)
        df_bulk.columns = df_bulk.columns.str.strip()

        # Columnas reales del bulk de Amazon
        state_col = next((c for c in df_bulk.columns if c.lower() == "state"), None)
        camp_col  = next((c for c in df_bulk.columns if c.lower() == "campaign name"), None)
        type_col  = next((c for c in df_bulk.columns if c.lower() == "type"), None)

        if state_col:
            df_active = df_bulk[df_bulk[state_col].str.upper().str.strip() == "ENABLED"].copy()
        else:
            df_active = df_bulk.copy()

        n_camps = len(df_active)
        n_tipos = df_active[type_col].value_counts() if type_col else None

        m1, m2, m3 = st.columns(3)
        m1.metric("Campañas activas", n_camps)
        m2.metric("Pausadas",  len(df_bulk[df_bulk[state_col].str.upper().str.strip() == "PAUSED"]) if state_col else "—")
        m3.metric("Total en Bulk", len(df_bulk))

        if type_col and n_tipos is not None:
            st.markdown("**Campañas activas por tipo:**  " + "  ·  ".join(f"**{k}**: {v}" for k, v in n_tipos.items()))

        st.markdown("#### Campañas activas")
        display_cols = [c for c in ["Campaign name", "Type", "Portfolio name", "Campaign bid strategy",
                                     "Campaign budget amount", "Impressions", "Clicks", "CTR",
                                     "Total cost", "CPC", "Purchases", "Sales", "ACOS", "ROAS"]
                        if c in df_active.columns]
        st.dataframe(df_active[display_cols] if display_cols else df_active, use_container_width=True)

        st.markdown("---")

        # Cruce con STR por nombre de campaña
        if file_str_f:
            df_str_f_data = _load_file(file_str_f.getvalue(), file_str_f.name)
            df_str_f_data.columns = df_str_f_data.columns.str.strip()

            str_term_col = "Customer Search Term"
            str_camp_col = next((c for c in df_str_f_data.columns if c.lower() == "campaign name"), None)

            if str_term_col not in df_str_f_data.columns:
                st.error(f"El STR no tiene la columna '{str_term_col}'.")
            elif camp_col is None or str_camp_col is None:
                st.error("No se encontró la columna 'Campaign name' en el Bulk o en el STR.")
            else:
                active_camps = set(df_active[camp_col].dropna().str.lower().str.strip())
                df_str_f_data["_camp_norm"] = df_str_f_data[str_camp_col].str.lower().str.strip()

                df_str_activo  = df_str_f_data[df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")
                df_str_inactivo = df_str_f_data[~df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")

                camps_sin_str = active_camps - set(df_str_f_data["_camp_norm"])

                c1, c2, c3 = st.columns(3)
                c1.metric("Términos STR de campañas activas",   len(df_str_activo))
                c2.metric("Términos STR de campañas inactivas", len(df_str_inactivo))
                c3.metric("Campañas activas sin tráfico en STR", len(camps_sin_str))

                st.markdown("#### Términos del STR provenientes de campañas activas")
                st.dataframe(df_str_activo, use_container_width=True)

                st.markdown("#### Términos del STR de campañas pausadas o no encontradas")
                df_gaps = df_str_inactivo
                st.dataframe(df_gaps, use_container_width=True)

                buf_gaps = io.BytesIO()
                df_gaps.to_excel(buf_gaps, index=False)
                st.download_button(
                    label=f"⬇️ Exportar {len(df_gaps)} términos de campañas inactivas",
                    data=buf_gaps.getvalue(),
                    file_name="str_campanas_inactivas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="funnel_dl_inactivas",
                )

                if camps_sin_str:
                    st.markdown("#### Campañas activas sin términos en el STR")
                    st.dataframe(pd.DataFrame(sorted(camps_sin_str), columns=["Campaign name"]), use_container_width=True)

                # ── Campañas Sugeridas ───────────────────────────────────────
                st.markdown("---")
                st.markdown("### Campañas Sugeridas")
                st.info("Nombres generados siguiendo el convention: Producto - ASIN - SP - KW - MatchType - Keyword")

                if str_term_col in df_gaps.columns and str_camp_col in df_gaps.columns and len(df_gaps) > 0:
                    match_type = st.selectbox("Match Type por defecto", ["Phrase", "Exact", "Broad"], key="match_type_sug")

                    def extract_producto_asin(camp_name):
                        """Extrae Producto y ASIN del nombre de campaña (formato: Producto - ASIN - ...)."""
                        m = re.match(r'^(.+?)\s*-\s*(B[0-9A-Z]{9})\b', str(camp_name), re.IGNORECASE)
                        if m:
                            return m.group(1).strip(), m.group(2).upper()
                        return None, None

                    rows = []
                    for _, row in df_gaps[[str_term_col, str_camp_col]].drop_duplicates(subset=str_term_col).iterrows():
                        term = str(row[str_term_col]).strip()
                        producto, asin = extract_producto_asin(row[str_camp_col])
                        if producto and asin:
                            suggested = f"{producto} - {asin} - SP - KW - {match_type} - {term.title()}"
                        else:
                            suggested = f"[Producto] - [ASIN] - SP - KW - {match_type} - {term.title()}"
                        rows.append({
                            "Customer Search Term": term,
                            "Campaña origen (inactiva)": row[str_camp_col],
                            "Producto inferido": producto or "—",
                            "ASIN inferido": asin or "—",
                            "Match Type": match_type,
                            "Nombre sugerido": suggested,
                        })

                    df_sugeridas = pd.DataFrame(rows)
                    st.dataframe(df_sugeridas, use_container_width=True)

                    buf_sug = io.BytesIO()
                    df_sugeridas.to_excel(buf_sug, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_sugeridas)} campañas sugeridas a Excel",
                        data=buf_sug.getvalue(),
                        file_name="campanas_sugeridas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="funnel_dl_sugeridas",
                    )
                else:
                    st.success("No hay términos de campañas inactivas para sugerir.")

                # ── Harvesting ───────────────────────────────────────────────
                st.markdown("---")
                st.markdown("### Harvesting")
                st.info("Términos del STR con ventas suficientes para cosechar como keywords.")

                orders_col  = "7 Day Total Orders (#)"
                sales_col_h = "7 Day Total Sales"
                acos_col_h  = "Total Advertising Cost of Sales (ACOS)"
                cvr_col     = "7 Day Conversion Rate"

                harvest_cols = [c for c in [str_term_col, "Impressions", "Clicks", orders_col,
                                            sales_col_h, "Spend", acos_col_h, cvr_col]
                                if c in df_str_f_data.columns]

                if orders_col not in df_str_f_data.columns:
                    st.warning(f"El STR no tiene la columna '{orders_col}'.")
                else:
                    min_ventas = st.number_input("Mínimo de órdenes para cosechar", min_value=1, value=3, step=1, key="min_harvest")

                    for c in [orders_col, sales_col_h, acos_col_h, cvr_col, "Impressions", "Clicks", "Spend"]:
                        if c in df_str_f_data.columns:
                            df_str_f_data[c] = pd.to_numeric(df_str_f_data[c], errors="coerce").fillna(0)

                    camp_agg = df_str_f_data.groupby(str_term_col)[str_camp_col].apply(
                        lambda x: " | ".join(sorted(x.dropna().unique()))
                    ).reset_index().rename(columns={str_camp_col: "Campaña origen"})

                    df_harvest_agg = (
                        df_str_f_data[harvest_cols]
                        .groupby(str_term_col, as_index=False)
                        .agg({c: "sum" for c in harvest_cols if c != str_term_col})
                        .merge(camp_agg, on=str_term_col, how="left")
                    )

                    # Mover "Campaña origen" como segunda columna
                    cols = df_harvest_agg.columns.tolist()
                    cols.insert(1, cols.pop(cols.index("Campaña origen")))
                    df_harvest_agg = df_harvest_agg[cols]

                    # Recalcular ACoS agregado
                    if sales_col_h in df_harvest_agg.columns and "Spend" in df_harvest_agg.columns:
                        df_harvest_agg[acos_col_h] = (
                            df_harvest_agg["Spend"] / df_harvest_agg[sales_col_h].replace(0, float("nan")) * 100
                        ).round(2)

                    df_harvest_agg = df_harvest_agg[df_harvest_agg[orders_col] >= min_ventas].copy()

                    def suggest_match(row):
                        orders = row[orders_col]
                        acos   = row.get(acos_col_h, 100)
                        if orders >= min_ventas * 3 or (orders >= min_ventas and acos <= 25):
                            return "Exact"
                        return "Phrase"

                    df_harvest_agg["Match Type Sugerido"] = df_harvest_agg.apply(suggest_match, axis=1)
                    df_harvest_agg = df_harvest_agg.sort_values(orders_col, ascending=False)

                    n_exact  = (df_harvest_agg["Match Type Sugerido"] == "Exact").sum()
                    n_phrase = (df_harvest_agg["Match Type Sugerido"] == "Phrase").sum()
                    h1, h2, h3 = st.columns(3)
                    h1.metric("Términos para cosechar", len(df_harvest_agg))
                    h2.metric("→ Exact",  n_exact)
                    h3.metric("→ Phrase", n_phrase)

                    st.markdown(f"**Criterio:** Exact si órdenes ≥ {min_ventas * 3} o (órdenes ≥ {min_ventas} y ACoS ≤ 25%) · Phrase en el resto")
                    st.dataframe(df_harvest_agg, use_container_width=True)

                    buf_harv = io.BytesIO()
                    df_harvest_agg.to_excel(buf_harv, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_harvest_agg)} términos para cosechar",
                        data=buf_harv.getvalue(),
                        file_name="harvesting.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="funnel_dl_harvest",
                    )
        else:
            st.markdown("#### Todas las campañas del Bulk")
            st.dataframe(df_bulk, use_container_width=True)
