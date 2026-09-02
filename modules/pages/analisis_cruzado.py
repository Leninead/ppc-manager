import io
import re
import unicodedata

import streamlit as st
import pandas as pd

from core.bulk_export import (
    build_bid_update,
    build_keyword_create,
    write_bulk_excel,
)
from core.bulk_parser import validate_bulk
from core.helpers import read_sqp, extract_sqp_brand
from core.ppc_metrics import acos_series, calc_acos, calc_cvr


# Paridad de conversión contra el mercado (FIX 3).
# Por debajo de este factor se considera que convertís peor que la query.
# 0.8 = tolerás rendir hasta un 20% peor antes de llamarlo problema de listing.
# NO tiene respaldo empírico: el relevamiento de SQP (2026-09) confirmó que no
# existe literatura con umbrales de share ni de paridad de CVR. Es un default
# para mover, no una constante de negocio.
_CVR_PARIDAD_MERCADO = 0.8

# Piso de bid de Amazon (INV-1). Por debajo de esto la subasta no acepta la puja.
_BID_MINIMO_AMAZON = 0.10


def _norm(s) -> str:
    """Normaliza string para matching: lowercase, sin acentos, espacios colapsados."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


# ASIN de Amazon: B0 + 8 alfanuméricos (case-insensitive via lower()).
_ASIN_RE = re.compile(r"^b0[a-z0-9]{8}$")


def _br_num(raw, present) -> float:
    """Convierte un valor del BR a número, NaN→0. Reemplaza el patrón
    'pd.to_numeric(...) or 0' que NO captura NaN (NaN es truthy en Python)."""
    if not present:
        return 0
    v = pd.to_numeric(
        str(raw).replace("$", "").replace(",", "").replace("MX", ""),
        errors="coerce",
    )
    return 0 if pd.isna(v) else v


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _load_str_file(data, name):
    """Cached reader for STR files."""
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


def render():
    st.header("🔗 Análisis Cruzado STR vs SQP")
    st.caption("Detectá oportunidades cruzando términos de búsqueda pagos (STR) con orgánicos (SQP).")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Cruzar tus campañas (STR) contra el mercado (SQP) y generar un Plan de Acción accionable.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("STR (.xlsx) + SQP (.xlsx). Opcional: BR by ASIN (.csv) para Tab 3 PPC Insights.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Campaign Builder (M10) para ejecutar, o Tendencia Multi-Semana (M5) para contexto.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí STR y SQP\n"
            "2. Ingresá brand terms + Target ACoS\n"
            "3. Tab Cruce: revisá En ambos / Solo STR / Solo SQP\n"
            "4. Tab Plan de Acción: revisá columna Acción (AGREGAR / HARVEST / BAJAR BID / ESCALAR / MONITOREAR)\n"
            "5. Descargá Plan de Acción bulk"
        )

    st.info("Subí ambos archivos para comparar qué términos aparecen en cada reporte y detectar oportunidades.")

    col_str, col_sqp = st.columns(2)
    with col_str:
        file_str_x = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_x")
    with col_sqp:
        file_sqp_x = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp_x")

    if file_str_x and file_sqp_x:
        df_str = _load_str_file(file_str_x.getvalue(), file_str_x.name)
        brand_name = extract_sqp_brand(file_sqp_x)
        df_sqp = read_sqp(file_sqp_x)

        str_col = "Customer Search Term"
        sqp_col = "Search Query"

        if brand_name:
            st.success(f"Marca detectada: **{brand_name.title()}**")
            brand_terms = [_norm(t) for t in brand_name.split(",") if _norm(t)]
            df_sqp["Tipo"] = df_sqp[sqp_col].apply(
                lambda q: "Marca" if _norm(q) and any(t in _norm(q) for t in brand_terms) else "Genérica"
            )
        else:
            marca_manual = st.text_input(
                "⚠️ No se detectó la marca automáticamente. Ingresá el nombre (ej: dermaglos):",
                key="marca_manual_input",
                placeholder="ej: dermaglos"
            )
            if marca_manual.strip():
                brand_name = marca_manual.strip().lower()
                brand_terms = [_norm(t) for t in brand_name.split(",") if _norm(t)]
                df_sqp["Tipo"] = df_sqp[sqp_col].apply(
                    lambda q: "Marca" if _norm(q) and any(t in _norm(q) for t in brand_terms) else "Genérica"
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

            # ── Diagnóstico de funnel: CVR propio vs CVR del mercado ──
            # Es lo que separa un problema de LISTING de uno de TARGETING.
            # Convertís en línea con el mercado y tenés poco share → te falta
            # tráfico, y eso SÍ se ataca con PPC. Convertís por debajo → el
            # problema está en el listing, el precio o las reviews, y subir
            # bids ahí sólo compra clicks que no cierran.
            #
            # OJO con el denominador: "Clicks: Brand Count" mezcla orgánico y
            # pago, así que el CVR que sale de acá es el de TU MARCA ENTERA en
            # esa query, NO el de tus ads. Para el diagnóstico de listing eso
            # es lo correcto (es el que compara contra el mercado), pero NO es
            # comparable contra el CVR del STR ni contra el "CVR %" de Tab 3.
            _clicks_tot_col = "Clicks: Total Count"
            _clicks_br_col  = "Clicks: Brand Count"
            _pur_br_col     = "Purchases: Brand Count"

            for _c in [_clicks_br_col, _pur_br_col]:
                if _c in df_sqp.columns:
                    df_sqp[_c] = pd.to_numeric(df_sqp[_c], errors="coerce")

            _tiene_mercado = all(c in df_sqp.columns for c in [pur_col, _clicks_tot_col])
            _tiene_marca   = all(c in df_sqp.columns for c in [_pur_br_col, _clicks_br_col])

            if _tiene_mercado:
                df_sqp["_cvr_mercado"] = [
                    calc_cvr(p, c)
                    for p, c in zip(df_sqp[pur_col], df_sqp[_clicks_tot_col])
                ]
            if _tiene_marca:
                df_sqp["_cvr_marca"] = [
                    calc_cvr(p, c)
                    for p, c in zip(df_sqp[_pur_br_col], df_sqp[_clicks_br_col])
                ]

            if _tiene_mercado and _tiene_marca:
                def _diag_funnel(fila):
                    mercado = fila["_cvr_mercado"]
                    marca = fila["_cvr_marca"]
                    if pd.isna(mercado) or pd.isna(marca):
                        return "Sin datos"
                    if marca >= mercado * _CVR_PARIDAD_MERCADO:
                        return "Convertís como el mercado"
                    return "Convertís por debajo"

                df_sqp["_diagnostico_funnel"] = df_sqp.apply(_diag_funnel, axis=1)

            # Si TODOS los valores salen None la columna queda dtype object y
            # Arrow revienta al renderizar. to_numeric la fuerza a float+NaN.
            for _c in ["_cvr_mercado", "_cvr_marca"]:
                if _c in df_sqp.columns:
                    df_sqp[_c] = pd.to_numeric(df_sqp[_c], errors="coerce").round(2)

            _cols_funnel = [
                c for c in ["_cvr_mercado", "_cvr_marca", "_diagnostico_funnel"]
                if c in df_sqp.columns
            ]

            cruzado_tab1, cruzado_tab2, cruzado_tab3 = st.tabs(["🔗 Análisis Cruzado", "🎯 Plan de Acción", "📊 PPC Insights por ASIN"])

            # ══════════════════════════════════════════════════════════════
            # TAB 1 — Análisis Cruzado (contenido original)
            # ══════════════════════════════════════════════════════════════
            with cruzado_tab1:
                # INV-8: la tab trabaja sobre su propia copia. Antes cada tab
                # mutaba el df compartido (convertia columnas, agregaba _asin_ext,
                # deshacia el fillna del bloque de arriba) y el resultado dependia
                # del orden en que se habian renderizado las tabs.
                df_sqp_t1 = df_sqp.copy()
                df_str_t1 = df_str.copy()

                c1, c2, c3 = st.columns(3)
                c1.metric("En ambos", len(in_both))
                c2.metric("Solo en STR (no en SQP)", len(only_str))
                c3.metric("Solo en SQP (oportunidades)", len(only_sqp))

                opp_sqp = df_sqp_t1[df_sqp_t1[sqp_col].str.lower().str.strip().isin(only_sqp)]
                n_marca    = (opp_sqp["Tipo"] == "Marca").sum()
                n_generica = (opp_sqp["Tipo"] == "Genérica").sum()
                m1, m2 = st.columns(2)
                m1.metric("Oportunidades de marca", n_marca)
                m2.metric("Oportunidades genéricas", n_generica)

                # ── Diagnóstico cobertura STR (mitigación BUG-1) ─────────
                # M4 NO filtra por Match Type — pero si el STR llega filtrado
                # upstream (M2 Winners view o export Amazon recortado), AUTO/PT
                # se pierden. Este panel muestra cuánto spend queda fuera.
                if df_str_t1 is not None and "Match Type" in df_str_t1.columns:
                    with st.expander("📊 Diagnóstico cobertura STR (BUG-1)", expanded=False):
                        spend_col = None
                        for c in ["Spend", "spend", "Cost"]:
                            if c in df_str_t1.columns:
                                spend_col = c
                                break
                        if spend_col is None:  # fallback substring
                            spend_col = next(
                                (c for c in df_str_t1.columns
                                 if "spend" in c.lower() or "cost" in c.lower()),
                                None,
                            )

                        if spend_col is None:
                            st.info("No detecté columna 'Spend' — omito % spend.")
                            _cov = df_str_t1.groupby(
                                df_str_t1["Match Type"].astype(str).str.upper()
                            ).size().reset_index(name="rows")
                            st.dataframe(_cov, use_container_width=True)
                        else:
                            _spend_num = pd.to_numeric(
                                df_str_t1[spend_col].astype(str).str.replace(
                                    r"[MX$,%]", "", regex=True
                                ),
                                errors="coerce",
                            ).fillna(0)
                            _mt = df_str_t1["Match Type"].astype(str).str.upper()
                            cov = pd.DataFrame({"Match Type": _mt, "_spend": _spend_num})
                            cov = cov.groupby("Match Type").agg(
                                rows=("_spend", "size"), spend=("_spend", "sum")
                            ).reset_index()
                            cov["% spend"] = (cov["spend"] / (cov["spend"].sum() + 1e-9) * 100).round(1)
                            st.dataframe(cov, use_container_width=True)

                            non_kw_types = ["AUTO", "PT", "PRODUCT_TARGETING", "-", "", "NAN"]
                            non_kw_spend = _spend_num[_mt.isin(non_kw_types)].sum()
                            non_kw_spend_pct = non_kw_spend / (_spend_num.sum() + 1e-9) * 100

                            if non_kw_spend_pct > 20:
                                st.warning(
                                    f"⚠️ {non_kw_spend_pct:.1f}% del spend está en AUTO/PT/sin "
                                    f"Match Type. Si tu STR viene filtrado upstream (M2 Winners "
                                    f"view), ese spend NO entra al classifier. Verificá el origen "
                                    f"del archivo."
                                )
                            else:
                                st.info(
                                    f"ℹ️ Cobertura: {100 - non_kw_spend_pct:.1f}% del spend en "
                                    f"keywords (EXACT/PHRASE/BROAD)."
                                )

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
                sqp_cols_merge = [sqp_col] + [c for c in [score_col, imp_col, "Clicks: Total Count", pur_col] if c in df_sqp_t1.columns] + _cols_funnel
                sqp_subset = df_sqp_t1[sqp_cols_merge].copy()
                sqp_subset[sqp_col] = sqp_subset[sqp_col].str.lower().str.strip()
                merged = df_str_t1[df_str_t1[str_col].str.lower().str.strip().isin(in_both)].copy()
                merged[str_col] = merged[str_col].str.lower().str.strip()
                merged = merged.merge(sqp_subset, left_on=str_col, right_on=sqp_col, how="left", suffixes=("_STR", "_SQP"))
                st.dataframe(apply_filters(merged), use_container_width=True)
                if _cols_funnel:
                    st.caption(
                        "**Cómo leer `_diagnostico_funnel`.** "
                        "*Convertís como el mercado* + share bajo = problema de **tráfico**: "
                        "no aparecés lo suficiente, y eso se ataca con PPC (subir bid, "
                        "agregar la keyword). "
                        "*Convertís por debajo* = problema de **listing, precio o reviews**: "
                        "subir bids acá compra clicks que no cierran. "
                        f"El umbral de paridad es {_CVR_PARIDAD_MERCADO:.0%} del CVR del mercado "
                        "y no tiene respaldo empírico — ajustalo por categoría. "
                        "Ojo: `_cvr_marca` sale de *Clicks: Brand Count*, que mezcla orgánico "
                        "y pago, así que es el CVR de tu marca entera en esa query, **no el de "
                        "tus ads** — no lo compares contra el CVR del STR ni contra el de Tab 3."
                    )

                # ── Tabla 2: solo en SQP (oportunidades) ─────────────────
                st.markdown("#### Términos solo en SQP (sin campaña activa — posibles oportunidades)")
                df_oportunidades = df_sqp_t1[df_sqp_t1[sqp_col].str.lower().str.strip().isin(only_sqp)].copy()

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
                    key="cruzado_dl_opp",
                )

                # ── Tabla 3: solo en STR ─────────────────────────────────
                st.markdown("#### Términos solo en STR (sin datos de búsqueda orgánica)")
                df_solo_str = df_str_t1[df_str_t1[str_col].str.lower().str.strip().isin(only_str)].copy()
                st.dataframe(df_solo_str, use_container_width=True)

            # ══════════════════════════════════════════════════════════════
            # TAB 2 — Plan de Acción
            # ══════════════════════════════════════════════════════════════
            with cruzado_tab2:
                # INV-8: la tab trabaja sobre su propia copia. Antes cada tab
                # mutaba el df compartido (convertia columnas, agregaba _asin_ext,
                # deshacia el fillna del bloque de arriba) y el resultado dependia
                # del orden en que se habian renderizado las tabs.
                df_sqp_t2 = df_sqp.copy()
                df_str_t2 = df_str.copy()
                st.markdown("### 🎯 Plan de Acción")
                st.caption("Resumen ejecutivo accionable. Cada término clasificado con una acción concreta.")

                # ── Inputs ───────────────────────────────────────────────
                target_acos_pa = st.number_input(
                    "Target ACoS (%)",
                    min_value=1.0, max_value=200.0, value=35.0, step=1.0,
                    key="pa_target_acos"
                )

                cinp1, cinp2 = st.columns(2)
                with cinp1:
                    competidores_raw = st.text_input(
                        "Competidores conocidos (opcional, separados por coma)",
                        value="",
                        help="Ej: 'rayban, meta, oakley'. Si la query menciona tu marca "
                             "+ un competidor → clasifica CONQUEST, no DEFENDER (BUG-8).",
                        key="ac_competidores",
                    )
                with cinp2:
                    catalogo_raw = st.text_input(
                        "ASINs propios del cliente (opcional, separados por coma)",
                        value="",
                        help="Cross-check anti-self-ASIN. Si la query es uno de estos "
                             "ASINs → se excluye del bulk de keywords (BUG-5).",
                        key="ac_catalogo_asins",
                    )

                # Listas normalizadas una sola vez (se cierran sobre el classifier).
                brand_terms_norm = [_norm(t) for t in brand_name.split(",") if _norm(t)] if brand_name else []
                competidores_norm = [_norm(c) for c in competidores_raw.split(",") if _norm(c)]
                catalogo_norm = [_norm(a) for a in catalogo_raw.split(",") if _norm(a)]

                st.markdown("---")

                # ── Preparar columnas numéricas del SQP ──────────────────
                pur_brand    = "Purchases: Brand Count"
                pur_share    = "Purchases: Brand Share %"
                clicks_col   = "Clicks: Total Count"
                opp_col      = "Opportunity Score"
                sqp_col_pa   = sqp_col
                str_col_pa   = str_col

                for c in [pur_brand, pur_share, clicks_col]:
                    if c in df_sqp_t2.columns:
                        # NO .fillna(0) acá — NaN = sin data ≠ 0 = data confirmada cero.
                        # El classifier diferencia NaN para no falsear DEFENDER (BUG-7).
                        # clicks_col / pur_col ya vienen filleados arriba (L99 del bloque
                        # compartido); pur_brand y pur_share quedan NaN-preserving.
                        df_sqp_t2[c] = pd.to_numeric(df_sqp_t2[c], errors="coerce")

                # ── Recuperar columnas STR para cruce ─────────────────────
                spend_col_pa  = next((c for c in df_str_t2.columns if "spend" in c.lower()), None)
                sales_col_pa  = next((c for c in df_str_t2.columns if "sales" in c.lower()
                                      and "other" not in c.lower() and "advertised" not in c.lower()), None)
                orders_col_pa = next((c for c in df_str_t2.columns if "orders" in c.lower()), None)

                for c in [spend_col_pa, sales_col_pa, orders_col_pa]:
                    if c and c in df_str_t2.columns:
                        df_str_t2[c] = pd.to_numeric(df_str_t2[c], errors="coerce").fillna(0)

                # Agrupar STR por término
                str_agg = None
                if spend_col_pa and orders_col_pa:
                    agg_dict = {spend_col_pa: "sum", orders_col_pa: "sum"}
                    if sales_col_pa:
                        agg_dict[sales_col_pa] = "sum"
                    str_agg = (
                        df_str_t2.groupby(str_col_pa, as_index=False)
                        .agg(agg_dict)
                    )
                    str_agg["_term_lower"] = str_agg[str_col_pa].str.lower().str.strip()
                    if sales_col_pa:
                        # INV-7: NaN donde no hubo ventas, NUNCA 0. El .fillna(0)
                        # que estaba acá hacía que el término que gastó sin vender
                        # se leyera como el más eficiente de la tabla, y dejaba
                        # muerta la regla de BAJAR BID justo para esos términos.
                        str_agg["_acos"] = acos_series(
                            str_agg[spend_col_pa], str_agg[sales_col_pa]
                        )

                # ── Función de acción sugerida ────────────────────────────
                def _accion_sugerida(row, terms_str_set, str_agg_df, target_acos):
                    query      = str(row.get(sqp_col_pa, "")).lower().strip()
                    query_norm = _norm(row.get(sqp_col_pa, ""))
                    tipo       = row.get("Tipo", "Genérica")
                    purch_tot  = row.get(pur_col, 0)
                    purch_br   = row.get(pur_brand, 0)
                    br_share   = row.get(pur_share, 0)
                    opp_score  = row.get(opp_col, 0)
                    en_str     = query in terms_str_set

                    # Anti-self-ASIN (BUG-5): si el término ES un ASIN (regex) o aparece
                    # en el catálogo del cliente → no es una keyword accionable (PT).
                    if _ASIN_RE.match(query_norm.replace(" ", "")) or (
                        catalogo_norm and any(a in query_norm for a in catalogo_norm)
                    ):
                        return "⚫ ASIN (PT)"

                    # ─────────────────────────────────────────────────────
                    # Bloque BRAND (alta prioridad — ANTES de ESCALAR/AGREGAR)
                    # Todo término de marca se resuelve acá; no cae al bloque
                    # genéricas. Cierra el bug de AGREGAR/ESCALAR pisando marca.
                    # ─────────────────────────────────────────────────────
                    # Detección de marca normalizada (BUG-4): acentos + espacios colapsados.
                    es_marca = (tipo == "Marca") or (
                        brand_terms_norm and any(t in query_norm for t in brand_terms_norm)
                    )
                    # Cross-brand (BUG-8): menciona tu marca PERO también un competidor.
                    tiene_competidor = bool(competidores_norm) and any(
                        c in query_norm for c in competidores_norm
                    )

                    if es_marca:
                        # Cross-brand: marca propia + competidor en la misma query.
                        if tiene_competidor:
                            return "⚔️ CONQUEST (cross-brand)"
                        # Sin data: brand query sin métrica BS (NaN ≠ 0, BUG-7).
                        if pd.isna(br_share):
                            return "❔ SIN DATA (marca, sin métrica BS)"
                        # Brand perdiendo share → defender activamente.
                        if br_share < 70:
                            return "🛡️ DEFENDER marca"
                        # Brand dominando (BS ≥ 70) → no escalar más, monitorear.
                        return "🏆 BRAND PURE OK"

                    # ─────────────────────────────────────────────────────
                    # Bloque GENÉRICAS (solo términos NO marca llegan acá)
                    # ─────────────────────────────────────────────────────
                    # Buscar datos STR si existe
                    str_row = None
                    if str_agg_df is not None:
                        match = str_agg_df[str_agg_df["_term_lower"] == query]
                        if not match.empty:
                            str_row = match.iloc[0]

                    acos_str   = str_row["_acos"] if str_row is not None and "_acos" in str_row else None
                    orders_str = str_row[orders_col_pa] if str_row is not None and orders_col_pa else 0
                    # Spend y sales crudos: con INV-7 el ACoS es NaN cuando no hubo
                    # ventas, así que ninguna regla basada en acos_str puede ver el
                    # caso "gastó y no vendió". Hace falta mirar los dos números.
                    spend_str  = str_row[spend_col_pa] if (str_row is not None and spend_col_pa) else 0
                    sales_str  = str_row[sales_col_pa] if (str_row is not None and sales_col_pa) else 0

                    # Relevancia CONFIRMADA para ESCALAR (BUG-6, caso edge): exige señal
                    # POSITIVA (BS > 0 o brand purchases > 0). NaN NO basta — sin data ≠
                    # relevancia. Bloquea escalar términos sin tracción de mercado
                    # (gomas/plaquetas/sujetadores Setex con BS NaN y purchases 0).
                    # Trade-off (decisión 2026-05-26): un genérico ganador sin Brand
                    # Analytics cae a MONITOREAR — precisión > recall en cuentas sucias.
                    tiene_relevancia_confirmada = (
                        (pd.notna(br_share) and br_share > 0)
                        or (pd.notna(purch_br) and purch_br > 0)
                    )
                    if (
                        en_str and pd.notna(acos_str)
                        and acos_str <= target_acos * 0.7
                        and orders_str >= 2
                        and tiene_relevancia_confirmada
                    ):
                        return "⚡ ESCALAR"
                    if not en_str and pd.notna(purch_br) and purch_br > 0 and purch_tot > 0:
                        return "➕ AGREGAR keyword"
                    if purch_tot > 500 and (pd.isna(br_share) or br_share == 0):
                        return "🚫 NO ATACAR"
                    if opp_score > 40 and (pd.isna(br_share) or br_share < 5) and purch_tot < 300:
                        return "🔍 INVESTIGAR"
                    # Gasto sin ventas (INV-6: no puede caer en un bucket silencioso).
                    # Va ANTES de la regla de ACoS porque su ACoS es NaN y ninguna
                    # comparación numérica lo alcanza. Misma acción que BAJAR BID:
                    # negativizar acá violaría INV-11 sin el cruce contra el Bulk File.
                    if en_str and spend_str > 0 and sales_str <= 0:
                        return "⬇️ BAJAR BID"
                    if en_str and pd.notna(acos_str) and acos_str > target_acos * 2:
                        return "⬇️ BAJAR BID"
                    return "👁️ MONITOREAR"

                # ── Construir tabla de plan de acción ─────────────────────
                terms_str_set_pa = set(df_str_t2[str_col_pa].dropna().str.lower().str.strip())

                # ── Dedupe SQP por search query (BUG-2 → BUG-3 cae solo) ──
                # El SQP multi-mes puede traer la misma query en N filas. Sin
                # dedupe, el bulk repite KWs (BUG-2) y la misma query cae en 2
                # buckets de acción distintos (BUG-3). Suma volúmenes, promedia
                # share (preserva NaN), toma 'first' para el resto.
                if sqp_col_pa in df_sqp_t2.columns:
                    agg_dict = {}
                    for c in df_sqp_t2.columns:
                        if c == sqp_col_pa:
                            continue
                        if c in [imp_col, pur_col, pur_brand, clicks_col]:
                            agg_dict[c] = "sum"
                        elif c == pur_share:
                            agg_dict[c] = "mean"
                        else:
                            agg_dict[c] = "first"
                    df_sqp_dedup = df_sqp_t2.groupby(sqp_col_pa, as_index=False).agg(agg_dict)
                else:
                    df_sqp_dedup = df_sqp_t2

                df_plan = df_sqp_dedup.copy()

                # ── Opportunity Score en Tab 2 (adicional #1) ─────────────
                # Tab 1 lo calcula solo para only_sqp; sin esto la regla
                # INVESTIGAR del classifier nunca dispara (opp_score=0 siempre).
                if all(c in df_plan.columns for c in [imp_col, clicks_col, pur_share]):
                    _imp = df_plan[imp_col].fillna(0)
                    _clk = df_plan[clicks_col].fillna(0)
                    imp_norm = (_imp - _imp.min()) / (_imp.max() - _imp.min() + 1e-9)
                    click_norm = (_clk - _clk.min()) / (_clk.max() - _clk.min() + 1e-9)
                    share_norm = df_plan[pur_share].fillna(0) / 100
                    df_plan[opp_col] = (
                        imp_norm * 0.4 + click_norm * 0.3 + share_norm * 0.3
                    ).round(3)

                df_plan["Acción"] = df_plan.apply(
                    lambda r: _accion_sugerida(r, terms_str_set_pa, str_agg, target_acos_pa),
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
                    "🏆 BRAND PURE OK":   "background-color: #DCEDC8",
                    "⚔️ CONQUEST (cross-brand)": "background-color: #EDE7F6",
                    "⬇️ BAJAR BID":       "background-color: #FFF3E0",
                    "🚫 NO ATACAR":       "background-color: #FFEBEE",
                    "🔍 INVESTIGAR":      "background-color: #F3E5F5",
                    "❔ SIN DATA (marca, sin métrica BS)": "background-color: #ECEFF1",
                    "⚫ ASIN (PT)":       "background-color: #E0E0E0",
                    "👁️ MONITOREAR":      "",
                }
                def _color_accion(val):
                    return color_map.get(val, "")

                styled_plan = df_plan_tabla.style.map(_color_accion, subset=["Acción"])
                st.dataframe(styled_plan, use_container_width=True, height=500)

                # ── Export ────────────────────────────────────────────────
                # INV-9: la base es df_plan_show, o sea lo que el selectbox de
                # arriba esta mostrando. Antes el export ignoraba ese filtro y
                # mandaba siempre las mismas 3 acciones sin decirlo.
                st.markdown("---")
                st.markdown("#### 📦 Export")

                # Que acciones tienen sentido como fila de bulk y con que
                # operacion. El resto se clasifica igual pero va SOLO a la hoja
                # Metadata: "monitorear" o "no atacar" no son filas de Amazon.
                #
                # ⚔️ CONQUEST queda deliberadamente afuera del bulk: targetear la
                # marca de un competidor es decision explicita del AM por el
                # riesgo de trademark, no un default. Contrato con M10.
                _ACCIONES_CREATE = ("➕ AGREGAR keyword", "🛡️ DEFENDER marca")
                _ACCIONES_UPDATE = ("⚡ ESCALAR", "⬇️ BAJAR BID")
                _MATCH_POR_ACCION = {
                    "➕ AGREGAR keyword": "Phrase",
                    "🛡️ DEFENDER marca": "Exact",
                    "⚡ ESCALAR": "Exact",
                    "⬇️ BAJAR BID": "Exact",
                }

                df_visible = df_plan_show.copy()
                df_bulkeable = df_visible[
                    df_visible["Acción"].isin(_ACCIONES_CREATE + _ACCIONES_UPDATE)
                ].copy()

                # ── Inputs para el bid ────────────────────────────────────
                st.markdown("##### Inputs para el bid")
                col_a, col_b = st.columns(2)
                with col_a:
                    precio_promedio = st.number_input(
                        "Precio promedio producto (USD)",
                        min_value=0.0, value=0.0, step=0.5,
                        help="Bid = (CVR/100) x precio x (target ACoS/100). "
                             "Sin precio no se puede calcular el bid y las filas "
                             "quedan fuera del bulk.",
                        key="ac_precio_prom",
                    )
                with col_b:
                    cvr_default = st.number_input(
                        "CVR default (%) — fallback si no hay data por KW",
                        min_value=0.0, max_value=100.0, value=10.0, step=0.5,
                        help="Se aplica a todas las KWs (no calculamos CVR por KW aún).",
                        key="ac_cvr_default",
                    )

                # INV-1: el techo lo garantiza la formula (CVR <= 100%), pero el
                # PISO hay que aplicarlo a mano: 0.10 es el minimo que acepta la
                # subasta de Amazon. Un bid por debajo no es "barato", es invalido.
                bid_calculado = None
                if precio_promedio > 0:
                    _bid_bruto = (cvr_default / 100) * precio_promedio * (target_acos_pa / 100)
                    bid_calculado = max(_BID_MINIMO_AMAZON, round(_bid_bruto, 2))
                    if _bid_bruto < _BID_MINIMO_AMAZON:
                        st.warning(
                            "El bid que sale de la formula es "
                            f"{_bid_bruto:.4f} USD, por debajo del minimo de Amazon "
                            f"({_BID_MINIMO_AMAZON:.2f} USD). Se exporta al minimo, "
                            "**pero eso rompe tu target**: con un CVR de "
                            f"{cvr_default:.1f}% y un precio de {precio_promedio:.2f} USD "
                            "estos terminos no son rentables a ningun bid que Amazon "
                            "acepte. Revisa precio, CVR o target antes de subir el archivo."
                        )

                # ── Armar las filas para los constructores ────────────────
                # Los IDs numericos NO estan disponibles en este modulo: el SQP no
                # los trae y el STR standalone tampoco. Se mandan vacios a proposito
                # — inventarlos produciria un archivo que Amazon rechaza entero
                # (INV-5.4). Los constructores los marcan invalidos con el motivo.
                filas_create, filas_update = [], []
                for _, _r in df_bulkeable.iterrows():
                    _accion = _r["Acción"]
                    _fila = {
                        "campaign_id": "",
                        "ad_group_id": "",
                        "keyword_text": str(_r.get(sqp_col_pa, "")).strip(),
                        "match_type": _MATCH_POR_ACCION.get(_accion, "Exact"),
                        "bid": bid_calculado,
                    }
                    if _accion in _ACCIONES_UPDATE:
                        _fila["keyword_id"] = ""
                        filas_update.append(_fila)
                    else:
                        filas_create.append(_fila)

                bulk_create, inval_create = build_keyword_create(filas_create)
                bulk_update, inval_update = build_bid_update(filas_update)

                _partes_ok = [d for d in (bulk_create, bulk_update) if not d.empty]
                bulk_df = pd.concat(_partes_ok, ignore_index=True) if _partes_ok else bulk_create
                _partes_mal = [d for d in (inval_create, inval_update) if not d.empty]
                invalid_df = pd.concat(_partes_mal, ignore_index=True) if _partes_mal else inval_create

                # ── Hoja Metadata: TODO lo visible, con su motivo ──────────
                # INV-5.5: las columnas de analisis van aca, nunca en la hoja del
                # bulk. Amazon rechaza el archivo si le metes columnas propias.
                _meta_cols = [c for c in [
                    sqp_col_pa, "Acción", "Tipo", "En STR", pur_col, pur_brand,
                    pur_share, opp_col, imp_col,
                    "_cvr_mercado", "_cvr_marca", "_diagnostico_funnel",
                ] if c in df_visible.columns]
                metadata_df = df_visible[_meta_cols].rename(columns={
                    pur_col: "Purchases mercado",
                    pur_brand: "Purchases marca",
                    pur_share: "Brand Share %",
                    opp_col: "Opp. Score",
                    imp_col: "Impresiones",
                    "_cvr_mercado": "CVR mercado %",
                    "_cvr_marca": "CVR marca %",
                    "_diagnostico_funnel": "Diagnóstico funnel",
                }).copy()

                _no_bulkeables = sorted(
                    df_visible.loc[
                        ~df_visible["Acción"].isin(_ACCIONES_CREATE + _ACCIONES_UPDATE),
                        "Acción",
                    ].unique().tolist()
                )
                metadata_df["Motivo exclusión del bulk"] = [
                    "" if a in _ACCIONES_CREATE + _ACCIONES_UPDATE
                    else "Acción no accionable como fila de bulk"
                    for a in df_visible["Acción"]
                ]

                # ── INV-9: decir exactamente que entra y que no ────────────
                _n_vis, _n_bulk = len(df_visible), len(bulk_df)
                _motivos = []
                if _no_bulkeables:
                    _motivos.append(
                        f"{len(df_visible) - len(df_bulkeable)} por acción no "
                        f"accionable ({', '.join(_no_bulkeables)})"
                    )
                if not invalid_df.empty:
                    _motivos.append(f"{len(invalid_df)} por datos faltantes")
                _txt_motivos = f" ({'; '.join(_motivos)})" if _motivos else ""
                st.info(
                    f"Exportando **{_n_bulk} de {_n_vis}** filas visibles a la hoja del "
                    f"bulk{_txt_motivos}. Las {_n_vis} van completas a la hoja Metadata."
                )

                # ── Gate INV-5.4: Amazon hace rollback total ───────────────
                if bulk_df.empty:
                    st.error(
                        "**No se puede generar un bulk ejecutable con estos archivos.** "
                        "Amazon necesita los IDs numéricos de campaña, ad group y keyword "
                        "para aplicar cualquier fila, y ni el SQP ni el STR standalone los "
                        "traen. Para generar bulks ejecutables hace falta el **Bulk File** "
                        "de Amazon (Campaign Manager → Bulk Operations), que sí los tiene. "
                        "Próximamente."
                    )
                    if not invalid_df.empty:
                        with st.expander(
                            f"Ver el detalle de las {len(invalid_df)} filas rechazadas",
                            expanded=False,
                        ):
                            st.dataframe(
                                invalid_df[["Keyword Text", "Match Type", "_invalid_reason"]],
                                use_container_width=True, hide_index=True,
                            )
                    if not metadata_df.empty:
                        st.caption(
                            "Mientras tanto podés bajar el análisis. **No es un bulk**: no se "
                            "sube a Amazon, es la tabla de decisiones para trabajarla a mano."
                        )
                        _buf_meta = io.BytesIO()
                        metadata_df.to_excel(_buf_meta, index=False)
                        st.download_button(
                            label=f"⬇️ Descargar análisis ({len(metadata_df)} términos, NO subible)",
                            data=_buf_meta.getvalue(),
                            file_name="plan_accion_analisis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_plan_accion_meta",
                        )
                else:
                    _errores_bulk = [
                        e for e in validate_bulk(bulk_df) if e.severidad == "error"
                    ]
                    if _errores_bulk:
                        st.error(
                            f"**El bulk tiene {len(_errores_bulk)} errores y no se puede "
                            "descargar.** Amazon rechaza el archivo COMPLETO si una sola "
                            "fila está mal: una fila mala y las otras tampoco se aplican."
                        )
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Fila": e.fila if e.fila >= 0 else "—",
                                    "Columna": e.columna,
                                    "Valor": e.valor,
                                    "Qué hacer": e.mensaje,
                                }
                                for e in _errores_bulk
                            ]),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.dataframe(bulk_df, use_container_width=True)
                        _xlsx = write_bulk_excel(bulk_df, metadata_df)
                        st.download_button(
                            label=f"⬇️ Descargar Plan de Acción bulk ({_n_bulk} filas)",
                            data=_xlsx,
                            file_name="plan_accion_bulk.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_plan_accion",
                        )

            # ══════════════════════════════════════════════════════════════
            # TAB 3 — PPC Insights por ASIN
            # ══════════════════════════════════════════════════════════════
            with cruzado_tab3:
                # INV-8: la tab trabaja sobre su propia copia. Antes cada tab
                # mutaba el df compartido (convertia columnas, agregaba _asin_ext,
                # deshacia el fillna del bloque de arriba) y el resultado dependia
                # del orden en que se habian renderizado las tabs.
                df_sqp_t3 = df_sqp.copy()
                df_str_t3 = df_str.copy()
                st.markdown("### 📊 PPC Insights por ASIN")
                st.caption("Resumen de performance STR + market share SQP por ASIN. Subí el BR by ASIN para enriquecer.")

                # ── BR por ASIN opcional ──────────────────────────────────
                file_br_asin = st.file_uploader(
                    "Business Report by ASIN (opcional, .csv/.xlsx)",
                    type=["csv", "xlsx"],
                    key="cruzado_br_asin",
                )

                br_asin_data = {}
                if file_br_asin:
                    try:
                        df_br_a = pd.read_excel(file_br_asin) if file_br_asin.name.endswith(".xlsx") else pd.read_csv(file_br_asin)
                        asin_col_br = next((c for c in df_br_a.columns if "asin" in c.lower()), None)
                        title_col_br = next((c for c in df_br_a.columns if "title" in c.lower()), None)
                        sess_col_br = next((c for c in df_br_a.columns if "session" in c.lower() and "total" in c.lower()), None)
                        sales_col_br = next((c for c in df_br_a.columns if "ordered product sales" in c.lower()), None)
                        units_col_br = next((c for c in df_br_a.columns if "units ordered" in c.lower()), None)

                        if asin_col_br:
                            for _, row_br in df_br_a.iterrows():
                                a = str(row_br[asin_col_br]).strip()
                                if not a or a == "nan":
                                    continue
                                br_asin_data[a] = {
                                    "Title": str(row_br[title_col_br])[:50] if title_col_br else "",
                                    # _br_num: NaN→0 robusto (el viejo 'pd.to_numeric() or 0'
                                    # dejaba NaN porque NaN es truthy en Python). Adic #4.
                                    "Sessions": _br_num(row_br.get(sess_col_br, 0), sess_col_br),
                                    "Sales": _br_num(row_br.get(sales_col_br, 0), sales_col_br),
                                    "Units": _br_num(row_br.get(units_col_br, 0), units_col_br),
                                }
                            st.success(f"✅ BR cargado — {len(br_asin_data)} ASINs")
                    except Exception as e:
                        st.warning(f"⚠️ Error leyendo BR: {e}")

                st.markdown("---")

                # ── Detectar ASINs del STR (multi-columna + fallback, BUG-10) ──
                camp_col_str = next((c for c in df_str_t3.columns if "campaign name" in c.lower()), None)
                spend_col_str = next((c for c in df_str_t3.columns if "spend" in c.lower()), None)
                sales_col_str = next((c for c in df_str_t3.columns if "sales" in c.lower()
                                      and "other" not in c.lower() and "advertised" not in c.lower()), None)
                orders_col_str = next((c for c in df_str_t3.columns if "orders" in c.lower()), None)
                clicks_col_str = next((c for c in df_str_t3.columns if "clicks" in c.lower()), None)

                # Probar columnas ASIN explícitas antes del regex sobre Campaign Name.
                asin_cols_candidates = [
                    "Advertised ASIN", "ASIN", "SKU", "Product",
                    "advertised asin", "asin", "sku", "product",
                ]
                asin_col_str = next(
                    (c for c in df_str_t3.columns if "advertised asin" in c.lower()), None
                )
                if asin_col_str is None:
                    for cand in asin_cols_candidates:
                        if cand in df_str_t3.columns:
                            asin_col_str = cand
                            break

                if asin_col_str is None and camp_col_str:
                    df_str_t3["_asin_ext"] = df_str_t3[camp_col_str].astype(str).str.extract(
                        r"(B0[A-Z0-9]{8})", expand=False
                    )
                    asin_col_str = "_asin_ext"
                    st.warning(
                        "⚠️ No se detectó columna 'Advertised ASIN'/'ASIN' explícita. "
                        "Extrayendo ASIN del Campaign Name vía regex. "
                        "Cobertura PARCIAL si tu naming no incluye ASIN."
                    )

                # Cobertura de ASINs (BUG-10): cuántas filas quedan dentro del análisis.
                rows_total = len(df_str_t3)
                rows_con_asin = int(df_str_t3[asin_col_str].notna().sum()) if asin_col_str else 0
                if asin_col_str and spend_col_str and spend_col_str in df_str_t3.columns:
                    _sp_cov = pd.to_numeric(
                        df_str_t3[spend_col_str].astype(str).str.replace(r"[MX$,%]", "", regex=True),
                        errors="coerce",
                    ).fillna(0)
                    spend_total = _sp_cov.sum()
                    spend_con_asin = _sp_cov[df_str_t3[asin_col_str].notna()].sum()
                    cobertura_pct = (spend_con_asin / spend_total * 100) if spend_total > 0 else 0
                else:
                    cobertura_pct = (rows_con_asin / rows_total * 100) if rows_total > 0 else 0

                if asin_col_str and rows_con_asin < rows_total:
                    st.info(
                        f"ℹ️ {rows_con_asin}/{rows_total} filas con ASIN identificable "
                        f"({cobertura_pct:.1f}% del spend cubierto). El resto queda fuera "
                        f"del análisis por ASIN."
                    )

                if not asin_col_str or rows_con_asin == 0:
                    st.warning("⚠️ No se detectó ASIN en el STR. Necesitás 'Advertised ASIN'/'ASIN' o ASIN en el Campaign Name.")
                else:
                    # Limpiar numéricos del STR
                    def _to_num_cr(series):
                        return pd.to_numeric(
                            series.astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
                            errors="coerce"
                        ).fillna(0)

                    for c in [spend_col_str, sales_col_str, orders_col_str, clicks_col_str]:
                        if c and c in df_str_t3.columns:
                            df_str_t3[c] = _to_num_cr(df_str_t3[c])

                    # Agrupar STR por ASIN
                    agg_map_str = {}
                    if spend_col_str: agg_map_str[spend_col_str] = "sum"
                    if sales_col_str: agg_map_str[sales_col_str] = "sum"
                    if orders_col_str: agg_map_str[orders_col_str] = "sum"
                    if clicks_col_str: agg_map_str[clicks_col_str] = "sum"

                    if agg_map_str:
                        df_asin_str = df_str_t3.groupby(asin_col_str, as_index=False).agg(agg_map_str)
                    else:
                        df_asin_str = df_str_t3[[asin_col_str]].drop_duplicates()

                    asins = sorted(df_asin_str[asin_col_str].dropna().unique())

                    if not asins:
                        st.info("No se detectaron ASINs en el STR.")
                    else:
                        st.markdown(f"#### {len(asins)} ASINs detectados")

                        # ── SQP: impression share por ASIN (Brand columns) ───
                        br_imp_col = "Impressions: Brand Count"
                        br_click_col = "Clicks: Brand Count"
                        br_pur_col = "Purchases: Brand Count"
                        for sqp_c in [br_imp_col, br_click_col, br_pur_col]:
                            if sqp_c in df_sqp_t3.columns:
                                df_sqp_t3[sqp_c] = pd.to_numeric(df_sqp_t3[sqp_c], errors="coerce").fillna(0)

                        # Calcular share totales del SQP
                        total_sqp_imps = df_sqp_t3[imp_col].sum() if imp_col in df_sqp_t3.columns else 0
                        brand_sqp_imps = df_sqp_t3[br_imp_col].sum() if br_imp_col in df_sqp_t3.columns else 0
                        imp_share_global = (brand_sqp_imps / total_sqp_imps * 100) if total_sqp_imps > 0 else 0

                        # ── Resumen por ASIN ──────────────────────────────────
                        insights_rows = []
                        for asin in asins:
                            asin_row = df_asin_str[df_asin_str[asin_col_str] == asin]
                            if asin_row.empty:
                                continue
                            ar = asin_row.iloc[0]

                            spend_a = ar.get(spend_col_str, 0) if spend_col_str else 0
                            sales_a = ar.get(sales_col_str, 0) if sales_col_str else 0
                            orders_a = ar.get(orders_col_str, 0) if orders_col_str else 0
                            clicks_a = ar.get(clicks_col_str, 0) if clicks_col_str else 0
                            # INV-7: mismo helper que el classifier de Tab 2. None
                            # cuando no hubo ventas — la columna queda numérica con
                            # NaN, que Arrow renderiza como celda vacía.
                            acos_a = calc_acos(spend_a, sales_a)
                            cvr_a = calc_cvr(orders_a, clicks_a)

                            # BR data
                            br_info = br_asin_data.get(asin, {})
                            title = br_info.get("Title", asin[:20])

                            insights_rows.append({
                                "ASIN": asin,
                                "Producto": title if title else asin,
                                "Ad Spend": round(spend_a, 2),
                                "Ad Sales": round(sales_a, 2),
                                "ACoS %": round(acos_a, 1) if acos_a is not None else None,
                                "Orders": int(orders_a),
                                "CVR %": round(cvr_a, 1) if cvr_a is not None else None,
                                "Sessions (BR)": int(br_info.get("Sessions", 0)),
                                "Total Sales (BR)": round(br_info.get("Sales", 0), 2),
                            })

                        if insights_rows:
                            df_insights = pd.DataFrame(insights_rows)

                            # KPIs
                            i1, i2, i3 = st.columns(3)
                            i1.metric("ASINs con ads", len(df_insights))
                            i2.metric("Impression Share global", f"{imp_share_global:.1f}%")
                            total_ad_spend = df_insights["Ad Spend"].sum()
                            total_ad_sales = df_insights["Ad Sales"].sum()
                            i3.metric("ACoS promedio", f"{total_ad_spend / total_ad_sales * 100:.1f}%" if total_ad_sales > 0 else "—")

                            def _color_acos_insight(val):
                                # NaN = sin ventas (INV-7). Sin color: pintarlo de
                                # verde sería exactamente el error que el helper evita.
                                if pd.isna(val): return ""
                                if val <= 0: return ""
                                if val < 25: return "background-color: #E8F5E9; color: #1B5E20"
                                if val < 50: return "background-color: #FFF8E1; color: #F57F17"
                                return "background-color: #FFEBEE; color: #B71C1C"

                            styled_ins = df_insights.style.map(_color_acos_insight, subset=["ACoS %"])
                            st.dataframe(styled_ins, use_container_width=True, hide_index=True)
                            st.caption(
                                "ACoS y CVR vacíos = el ASIN no registró ventas (o clicks) "
                                "en el período. No es un 0: es ausencia de dato."
                            )

                            # ── Top 5 keywords por ASIN (expanders) ──────────
                            st.markdown("---")
                            st.markdown("#### Top 5 keywords por ASIN")

                            search_term_col = str_col
                            for asin in asins[:15]:  # Limitar a 15 ASINs para no saturar
                                asin_df = df_str_t3[df_str_t3[asin_col_str] == asin].copy()
                                if asin_df.empty:
                                    continue

                                if sales_col_str and sales_col_str in asin_df.columns:
                                    top_kw = asin_df.nlargest(5, sales_col_str)
                                elif spend_col_str and spend_col_str in asin_df.columns:
                                    top_kw = asin_df.nlargest(5, spend_col_str)
                                else:
                                    top_kw = asin_df.head(5)

                                title_label = br_asin_data.get(asin, {}).get("Title", "")
                                label = f"{asin} — {title_label}" if title_label else asin
                                asin_spend = asin_df[spend_col_str].sum() if spend_col_str else 0
                                asin_sales_v = asin_df[sales_col_str].sum() if sales_col_str else 0
                                asin_acos = calc_acos(asin_spend, asin_sales_v)
                                # Título del expander: string, no número. "s/d" en vez
                                # de un 0.0% que se leería como eficiencia perfecta.
                                asin_acos_txt = f"{asin_acos:.1f}%" if asin_acos is not None else "s/d"

                                with st.expander(f"{label} | ACoS {asin_acos_txt} | ${asin_spend:,.2f} spend"):
                                    show_kw_cols = [search_term_col]
                                    if spend_col_str: show_kw_cols.append(spend_col_str)
                                    if sales_col_str: show_kw_cols.append(sales_col_str)
                                    if orders_col_str: show_kw_cols.append(orders_col_str)
                                    if clicks_col_str: show_kw_cols.append(clicks_col_str)
                                    show_kw_cols = [c for c in show_kw_cols if c in top_kw.columns]

                                    # Detectar gaps: keywords en SQP que podrían beneficiar este ASIN
                                    asin_terms = set(asin_df[search_term_col].dropna().str.lower().str.strip())
                                    gaps = terms_sqp - asin_terms
                                    n_gaps = len(gaps)

                                    st.dataframe(top_kw[show_kw_cols], use_container_width=True, hide_index=True)
                                    if n_gaps > 0:
                                        st.caption(f"🔍 {n_gaps} queries del SQP no tienen ads para este ASIN — posibles gaps de cobertura.")

                            # ── Export ────────────────────────────────────────
                            st.markdown("---")
                            buf_ins = io.BytesIO()
                            df_insights.to_excel(buf_ins, index=False)
                            st.download_button(
                                label=f"📥 Exportar Insights por ASIN ({len(df_insights)} ASINs)",
                                data=buf_ins.getvalue(),
                                file_name="ppc_insights_asin.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_insights_asin"
                            )
