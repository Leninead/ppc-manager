import io

import streamlit as st
import pandas as pd

from core.helpers import read_sqp, extract_sqp_brand


def render():
    st.header("🔗 Análisis Cruzado STR vs SQP")
    st.caption("Detectá oportunidades cruzando términos de búsqueda pagos (STR) con orgánicos (SQP).")
    st.divider()
    st.info("Subí ambos archivos para comparar qué términos aparecen en cada reporte y detectar oportunidades.")

    col_str, col_sqp = st.columns(2)
    with col_str:
        file_str_x = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_x")
    with col_sqp:
        file_sqp_x = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp_x")

    if file_str_x and file_sqp_x:
        df_str = pd.read_excel(file_str_x) if file_str_x.name.endswith(".xlsx") else pd.read_csv(file_str_x)
        brand_name = extract_sqp_brand(file_sqp_x)
        df_sqp = read_sqp(file_sqp_x)

        str_col = "Customer Search Term"
        sqp_col = "Search Query"

        if brand_name:
            st.success(f"Marca detectada: **{brand_name.title()}**")
            brand_terms = [t.strip() for t in brand_name.split(",")]
            df_sqp["Tipo"] = df_sqp[sqp_col].str.lower().str.strip().apply(
                lambda q: "Marca" if any(t in q for t in brand_terms) else "Genérica"
            )
        else:
            marca_manual = st.text_input(
                "⚠️ No se detectó la marca automáticamente. Ingresá el nombre (ej: dermaglos):",
                key="marca_manual_input",
                placeholder="ej: dermaglos"
            )
            if marca_manual.strip():
                brand_name = marca_manual.strip().lower()
                brand_terms = [t.strip() for t in brand_name.split(",")]
                df_sqp["Tipo"] = df_sqp[sqp_col].str.lower().str.strip().apply(
                    lambda q: "Marca" if any(t in q for t in brand_terms) else "Genérica"
                )
                st.success(f"Marca configurada manualmente: **{brand_name.title()}**")
            else:
                st.warning("No se detectó la marca en el archivo SQP. Podés ingresarla arriba para clasificar correctamente.")
                df_sqp["Tipo"] = "Genérica"

        if str_col not in df_str.columns:
            st.error(f"El STR no tiene la columna '{str_col}'.")
        elif sqp_col not in df_sqp.columns:
            st.error(f"El SQP no tiene la columna '{sqp_col}'.")
        else:
            terms_str = set(df_str[str_col].dropna().str.lower().str.strip())
            terms_sqp = set(df_sqp[sqp_col].dropna().str.lower().str.strip())

            in_both = terms_str & terms_sqp
            only_str = terms_str - terms_sqp
            only_sqp = terms_sqp - terms_str

            # ── Convertir columnas numéricas del SQP (compartido) ────────
            imp_col   = "Impressions: Total Count"
            score_col = "Search Query Score"
            pur_col   = "Purchases: Total Count"
            prate_col = "Purchases: Purchase Rate %"
            for c in [imp_col, score_col, pur_col, prate_col, "Clicks: Total Count"]:
                if c in df_sqp.columns:
                    df_sqp[c] = pd.to_numeric(df_sqp[c], errors="coerce").fillna(0)

            cruzado_tab1, cruzado_tab2 = st.tabs(["🔗 Análisis Cruzado", "🎯 Plan de Acción"])

            # ══════════════════════════════════════════════════════════════
            # TAB 1 — Análisis Cruzado (contenido original)
            # ══════════════════════════════════════════════════════════════
            with cruzado_tab1:
                c1, c2, c3 = st.columns(3)
                c1.metric("En ambos", len(in_both))
                c2.metric("Solo en STR (no en SQP)", len(only_str))
                c3.metric("Solo en SQP (oportunidades)", len(only_sqp))

                opp_sqp = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)]
                n_marca    = (opp_sqp["Tipo"] == "Marca").sum()
                n_generica = (opp_sqp["Tipo"] == "Genérica").sum()
                m1, m2 = st.columns(2)
                m1.metric("Oportunidades de marca", n_marca)
                m2.metric("Oportunidades genéricas", n_generica)

                # ── Filtros globales ─────────────────────────────────────
                st.markdown("---")
                st.markdown("#### Filtros")
                f1, f2, f3, f4 = st.columns(4)
                min_imp   = f1.number_input("Mínimo de impresiones", min_value=0, value=0, step=100)
                min_score = f2.number_input("Mínimo Search Query Score", min_value=0, value=0, step=1)
                min_pur   = f3.number_input("Mínimo de purchases", min_value=0, value=0, step=1)
                tipo_filtro = f4.selectbox("Tipo de keyword", ["Todas", "Marca", "Genérica"])

                def apply_filters(df):
                    d = df.copy()
                    if imp_col in d.columns:
                        d = d[d[imp_col] >= min_imp]
                    if score_col in d.columns:
                        d = d[d[score_col] >= min_score]
                    if pur_col in d.columns:
                        d = d[d[pur_col] >= min_pur]
                    if "Tipo" in d.columns and tipo_filtro != "Todas":
                        d = d[d["Tipo"] == tipo_filtro]
                    if imp_col in d.columns:
                        d = d.sort_values(imp_col, ascending=False)
                    return d

                st.markdown("---")

                # ── Tabla 1: en ambos ────────────────────────────────────
                st.markdown("#### Términos en ambos reportes")
                sqp_cols_merge = [sqp_col] + [c for c in [score_col, imp_col, "Clicks: Total Count", pur_col] if c in df_sqp.columns]
                sqp_subset = df_sqp[sqp_cols_merge].copy()
                sqp_subset[sqp_col] = sqp_subset[sqp_col].str.lower().str.strip()
                merged = df_str[df_str[str_col].str.lower().str.strip().isin(in_both)].copy()
                merged[str_col] = merged[str_col].str.lower().str.strip()
                merged = merged.merge(sqp_subset, left_on=str_col, right_on=sqp_col, how="left", suffixes=("_STR", "_SQP"))
                st.dataframe(apply_filters(merged), use_container_width=True)

                # ── Tabla 2: solo en SQP (oportunidades) ─────────────────
                st.markdown("#### Términos solo en SQP (sin campaña activa — posibles oportunidades)")
                df_oportunidades = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)].copy()

                score_norm_cols = [c for c in [imp_col, "Clicks: Total Count", prate_col] if c in df_oportunidades.columns]
                if score_norm_cols:
                    norm = df_oportunidades[score_norm_cols].apply(
                        lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() != s.min() else 0
                    )
                    df_oportunidades.insert(1, "Opportunity Score", (norm.sum(axis=1) / len(score_norm_cols) * 100).round(1))

                df_oportunidades_filtrado = apply_filters(df_oportunidades)
                st.dataframe(df_oportunidades_filtrado, use_container_width=True)

                buffer = io.BytesIO()
                df_oportunidades_filtrado.to_excel(buffer, index=False)
                st.download_button(
                    label=f"⬇️ Exportar {len(df_oportunidades_filtrado)} oportunidades a Excel",
                    data=buffer.getvalue(),
                    file_name="oportunidades_sqp.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

                # ── Tabla 3: solo en STR ─────────────────────────────────
                st.markdown("#### Términos solo en STR (sin datos de búsqueda orgánica)")
                df_solo_str = df_str[df_str[str_col].str.lower().str.strip().isin(only_str)].copy()
                st.dataframe(df_solo_str, use_container_width=True)

            # ══════════════════════════════════════════════════════════════
            # TAB 2 — Plan de Acción
            # ══════════════════════════════════════════════════════════════
            with cruzado_tab2:
                st.markdown("### 🎯 Plan de Acción")
                st.caption("Resumen ejecutivo accionable. Cada término clasificado con una acción concreta.")

                # ── Inputs ───────────────────────────────────────────────
                pa1, pa2 = st.columns(2)
                target_acos_pa = pa1.number_input(
                    "Target ACoS (%)",
                    min_value=1.0, max_value=200.0, value=35.0, step=1.0,
                    key="pa_target_acos"
                )
                precio_pa = pa2.number_input(
                    "Precio del producto ($)",
                    min_value=1.0, value=14.99, step=0.50,
                    key="pa_precio"
                )

                st.markdown("---")

                # ── Preparar columnas numéricas del SQP ──────────────────
                pur_brand    = "Purchases: Brand Count"
                pur_share    = "Purchases: Brand Share %"
                clicks_col   = "Clicks: Total Count"
                opp_col      = "Opportunity Score"
                sqp_col_pa   = sqp_col
                str_col_pa   = str_col

                for c in [pur_brand, pur_share, clicks_col]:
                    if c in df_sqp.columns:
                        df_sqp[c] = pd.to_numeric(df_sqp[c], errors="coerce").fillna(0)

                # ── Recuperar columnas STR para cruce ─────────────────────
                spend_col_pa  = next((c for c in df_str.columns if "spend" in c.lower()), None)
                sales_col_pa  = next((c for c in df_str.columns if "sales" in c.lower()
                                      and "other" not in c.lower() and "advertised" not in c.lower()), None)
                orders_col_pa = next((c for c in df_str.columns if "orders" in c.lower()), None)

                for c in [spend_col_pa, sales_col_pa, orders_col_pa]:
                    if c and c in df_str.columns:
                        df_str[c] = pd.to_numeric(df_str[c], errors="coerce").fillna(0)

                # Agrupar STR por término
                str_agg = None
                if spend_col_pa and orders_col_pa:
                    agg_dict = {spend_col_pa: "sum", orders_col_pa: "sum"}
                    if sales_col_pa:
                        agg_dict[sales_col_pa] = "sum"
                    str_agg = (
                        df_str.groupby(str_col_pa, as_index=False)
                        .agg(agg_dict)
                    )
                    str_agg["_term_lower"] = str_agg[str_col_pa].str.lower().str.strip()
                    if sales_col_pa:
                        str_agg["_acos"] = (
                            str_agg[spend_col_pa] / str_agg[sales_col_pa].replace(0, float("nan")) * 100
                        ).fillna(0)

                # ── Función de acción sugerida ────────────────────────────
                def _accion_sugerida(row, terms_str_set, str_agg_df, target_acos, precio):
                    query      = str(row.get(sqp_col_pa, "")).lower().strip()
                    tipo       = row.get("Tipo", "Genérica")
                    purch_tot  = row.get(pur_col, 0)
                    purch_br   = row.get(pur_brand, 0)
                    br_share   = row.get(pur_share, 0)
                    opp_score  = row.get(opp_col, 0)
                    en_str     = query in terms_str_set

                    # Buscar datos STR si existe
                    str_row = None
                    if str_agg_df is not None:
                        match = str_agg_df[str_agg_df["_term_lower"] == query]
                        if not match.empty:
                            str_row = match.iloc[0]

                    acos_str   = str_row["_acos"] if str_row is not None and "_acos" in str_row else None
                    orders_str = str_row[orders_col_pa] if str_row is not None and orders_col_pa else 0

                    # Reglas en orden de prioridad
                    brand_terms_pa = [t.strip().lower() for t in brand_name.split(",")] if brand_name else []
                    es_marca = (tipo == "Marca") or (brand_terms_pa and any(t in query for t in brand_terms_pa))
                    if es_marca and br_share < 70:
                        return "🛡️ DEFENDER marca"
                    if en_str and acos_str is not None and acos_str <= target_acos * 0.7 and orders_str >= 2:
                        return "⚡ ESCALAR"
                    if not en_str and purch_br > 0 and purch_tot > 0:
                        return "➕ AGREGAR keyword"
                    if purch_tot > 500 and br_share == 0:
                        return "🚫 NO ATACAR"
                    if opp_score > 40 and br_share < 5 and purch_tot < 300:
                        return "🔍 INVESTIGAR"
                    if en_str and acos_str is not None and acos_str > target_acos * 2:
                        return "⬇️ BAJAR BID"
                    return "👁️ MONITOREAR"

                # ── Construir tabla de plan de acción ─────────────────────
                terms_str_set_pa = set(df_str[str_col_pa].dropna().str.lower().str.strip())

                df_plan = df_sqp.copy()
                df_plan["Acción"] = df_plan.apply(
                    lambda r: _accion_sugerida(r, terms_str_set_pa, str_agg, target_acos_pa, precio_pa),
                    axis=1
                )
                df_plan["En STR"] = df_plan[sqp_col_pa].str.lower().str.strip().isin(terms_str_set_pa).map(
                    {True: "✅ Sí", False: "❌ No"}
                )

                # ── KPIs por acción ───────────────────────────────────────
                accion_counts = df_plan["Acción"].value_counts()
                st.markdown("#### Resumen de acciones")
                cols_kpi = st.columns(min(len(accion_counts), 7))
                for i, (accion, count) in enumerate(accion_counts.items()):
                    cols_kpi[i % len(cols_kpi)].metric(accion, count)

                st.markdown("---")

                # ── Filtro por acción ─────────────────────────────────────
                opciones_accion = ["Todas"] + sorted(df_plan["Acción"].unique().tolist())
                filtro_accion = st.selectbox("Filtrar por acción", opciones_accion, key="pa_filtro_accion")

                df_plan_show = df_plan if filtro_accion == "Todas" else df_plan[df_plan["Acción"] == filtro_accion]

                # ── Tabla plan de acción ──────────────────────────────────
                plan_cols = ["Acción", sqp_col_pa, "Tipo", "En STR",
                             pur_col, pur_brand, pur_share, opp_col, imp_col]
                plan_cols = [c for c in plan_cols if c in df_plan_show.columns]

                rename_plan = {
                    pur_col:   "Purchases mercado",
                    pur_brand: "Purchases marca",
                    pur_share: "Brand Share %",
                    opp_col:   "Opp. Score",
                    imp_col:   "Impresiones",
                }

                df_plan_tabla = (
                    df_plan_show[plan_cols]
                    .rename(columns=rename_plan)
                    .sort_values("Acción")
                    .reset_index(drop=True)
                )

                # Color por acción
                color_map = {
                    "⚡ ESCALAR":        "background-color: #E8F5E9",
                    "➕ AGREGAR keyword": "background-color: #E3F2FD",
                    "🛡️ DEFENDER marca":  "background-color: #FFF8E1",
                    "⬇️ BAJAR BID":       "background-color: #FFF3E0",
                    "🚫 NO ATACAR":       "background-color: #FFEBEE",
                    "🔍 INVESTIGAR":      "background-color: #F3E5F5",
                    "👁️ MONITOREAR":      "",
                }
                def _color_accion(val):
                    return color_map.get(val, "")

                styled_plan = df_plan_tabla.style.map(_color_accion, subset=["Acción"])
                st.dataframe(styled_plan, use_container_width=True, height=500)

                # ── Export bulk — solo accionables ────────────────────────
                df_exportable = df_plan[
                    df_plan["Acción"].isin(["➕ AGREGAR keyword", "⚡ ESCALAR", "🛡️ DEFENDER marca"])
                ].copy()

                if not df_exportable.empty:
                    st.markdown("---")
                    st.markdown(f"#### 📦 Export bulk — {len(df_exportable)} términos accionables")
                    st.caption("Solo AGREGAR keyword, ESCALAR y DEFENDER marca. Campaign Name y Ad Group Name vacíos — el AM los completa antes de subir.")

                    df_bulk_export = pd.DataFrame({
                        "Product":          "",
                        "Entity":           "Keyword",
                        "Operation":        "Create",
                        "Campaign Name":    "",
                        "Ad Group Name":    "",
                        "Keyword":          df_exportable[sqp_col_pa].values,
                        "Match Type":       "exact",
                        "Max Bid":          "",
                        "Acción sugerida":  df_exportable["Acción"].values,
                        "Brand Share %":    df_exportable[pur_share].values if pur_share in df_exportable.columns else "",
                        "Purchases mercado": df_exportable[pur_col].values if pur_col in df_exportable.columns else "",
                    })

                    st.dataframe(df_bulk_export, use_container_width=True)

                    buf_plan = io.BytesIO()
                    df_bulk_export.to_excel(buf_plan, index=False)
                    st.download_button(
                        label=f"⬇️ Descargar Plan de Acción bulk ({len(df_exportable)} términos)",
                        data=buf_plan.getvalue(),
                        file_name="plan_accion_bulk.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_plan_accion"
                    )
