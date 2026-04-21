import io
import re
from datetime import datetime

import streamlit as st
import pandas as pd

from core.helpers import kpi_card


# ── Palabras clave para clustering ───────────────────────────────────────────
_SPANISH_WORDS = [
    "crema", "locion", "vitamina", "hidratante", "corporal", "facial",
    "para", "piel", "cuerpo", "cara", "serum", "agua", "micelar",
    "estrias", "embarazo", "nutritiva", "humectante", "suavizante",
    "blanqueadora", "aclarante", "antiarrugas", "antiedad"
]

_VITAMIN_A_WORDS = [
    "vitamin a", "vitamina a", "allantoin", "alantoin", "alantoina",
    "retinol", "retinoid", "retinoide", "vitamin e", "vitamina e",
    "vitamin a and e", "vitamin a cream", "vitamin a lotion"
]

_BRAND_EXCLUSIONS = []  # se llena dinámicamente con el nombre de marca


def _detectar_cluster(keyword: str, brand_terms: list) -> str:
    """Detecta el cluster de intención de una keyword."""
    kw = keyword.lower().strip()

    # PAT — es un ASIN
    if re.match(r'^b0[a-z0-9]{8}', kw, re.IGNORECASE):
        return "PAT"

    # Spanish — va ANTES que Brand (mercado hispano USA)
    # Si tiene palabras en español, es Spanish aunque mencione la marca
    if any(s in kw for s in _SPANISH_WORDS):
        return "Spanish"

    # Vitamin A — cluster ganador antes de Brand genérico
    if any(v in kw for v in _VITAMIN_A_WORDS):
        return "Vitamin A"

    # Brand puro — marca en inglés o marca sola
    if any(t in kw for t in brand_terms):
        return "Brand"

    # Discovery — todo lo demás
    return "Discovery"


def _generar_nombre_campana(marca: str, asin: str, cluster: str,
                             match_type: str, numero: int) -> str:
    """Genera naming convention Capybaras: Marca - ASIN - SP - KW - MATCH - Cluster N"""
    match_upper = match_type.upper()
    if cluster == "PAT":
        return f"{marca} - {asin} - SP - PT - ASIN - {cluster} {numero}"
    return f"{marca} - {asin} - SP - KW - {match_upper} - {cluster} {numero}"


def _generar_nombre_adgroup(cluster: str, numero: int) -> str:
    return f"AG - {cluster} {numero}"


def _generar_nombre_campana_sb(marca: str, asin: str, cluster: str,
                                match_type: str, numero: int) -> str:
    """Naming SB: Marca - ASIN - SB - KW - MATCH - Cluster N"""
    return f"{marca} - {asin} - SB - KW - {match_type.upper()} - {cluster} {numero}"


def _generar_nombre_campana_sd(marca: str, asin: str, targeting_type: str,
                                subtipo: str, numero: int) -> str:
    """Naming SD: Marca - ASIN - SD - TargetType - SubTipo N"""
    return f"{marca} - {asin} - SD - {targeting_type} - {subtipo} {numero}"


# ── Bulk Amazon 2026 — 31 columnas exactas en orden ──────────────────────────
# Ref: AmazonBulkUploadGuide.md · Regla #2 · Última columna "Sites" agregada Q2 2026
_BULK_COLUMNS_2026 = [
    "Product", "Entity", "Operation", "Campaign ID", "Ad Group ID",
    "Portfolio ID", "Ad ID", "Keyword ID", "Product Targeting ID",
    "Campaign Name", "Ad Group Name", "Start Date", "End Date",
    "Targeting Type", "State", "Daily Budget", "SKU",
    "Ad Group Default Bid", "Bid", "Keyword Text",
    "Native Language Keyword", "Native Language Locale", "Match Type",
    "Bidding Strategy", "Placement", "Percentage",
    "Product Targeting Expression", "Audience ID",
    "Shopper Cohort Percentage", "Shopper Cohort Type", "Sites",
]


def _fila_vacia_bulk() -> dict:
    """Retorna un dict con las 31 columnas del bulk Amazon, todas vacías."""
    return {col: "" for col in _BULK_COLUMNS_2026}


# ── SB Render ────────────────────────────────────────────────────────────────

def _render_sb():
    """Genera bulk de campañas Sponsored Brands."""

    # ── Paso 1 — Keywords ────────────────────────────────────────────────────
    st.markdown("### Paso 1 — Keywords para SB")
    st.caption("Subí el Plan de Acción o ingresá keywords manualmente.")

    input_mode = st.radio(
        "Fuente de keywords",
        ["📄 Plan de Acción bulk", "✏️ Input manual"],
        horizontal=True, key="cb_sb_input_mode",
    )

    keywords_list = []
    if input_mode == "📄 Plan de Acción bulk":
        file_plan = st.file_uploader("Plan de Acción (.xlsx)", type=["xlsx"], key="cb_plan_sb")
        if not file_plan:
            st.markdown(
                "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
                "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
                "<div style='font-size:1.5rem;'>📂</div>"
                "<div style='font-weight:600;margin-top:0.5rem;'>Subí el Plan de Acción bulk</div>"
                "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
                "Generalo en: Análisis Cruzado → Plan de Acción → Descargar bulk</div>"
                "</div>", unsafe_allow_html=True,
            )
            return
        df_plan = pd.read_excel(file_plan)
        if "Keyword" not in df_plan.columns:
            st.error("❌ El archivo no tiene columna 'Keyword'.")
            return
        keywords_list = df_plan["Keyword"].dropna().unique().tolist()
        st.success(f"✅ {len(keywords_list)} keywords cargadas")
    else:
        kw_text = st.text_area(
            "Keywords (una por línea)", height=150, key="cb_sb_kw_manual",
            placeholder="vitamin a cream\ncrema hidratante\ndermaglos lotion",
        )
        if kw_text.strip():
            keywords_list = [k.strip() for k in kw_text.strip().splitlines() if k.strip()]
            st.success(f"✅ {len(keywords_list)} keywords ingresadas")

    if not keywords_list:
        return

    st.markdown("---")

    # ── Paso 2 — Datos del producto + campos SB ──────────────────────────────
    st.markdown("### Paso 2 — Datos del producto y creatividad SB")

    p1, p2, p3 = st.columns(3)
    marca    = p1.text_input("Nombre de marca", key="cb_sb_marca")
    asin     = p2.text_input("ASIN principal", key="cb_sb_asin")
    sku      = p3.text_input("SKU principal", key="cb_sb_sku")

    p4, p5, p6 = st.columns(3)
    precio      = p4.number_input("Precio ($)", min_value=1.0, value=9.99, step=0.50, key="cb_sb_precio")
    cvr         = p5.number_input("CVR estimado (%)", min_value=1.0, value=10.0, step=0.5, key="cb_sb_cvr")
    target_acos = p6.number_input("Target ACoS (%)", min_value=1.0, value=20.0, step=1.0, key="cb_sb_tacos")

    p7, p8 = st.columns(2)
    portfolio_id = p7.text_input("Portfolio ID (opcional)", key="cb_sb_portfolio")
    budget       = p8.number_input("Budget diario ($)", min_value=1.0, value=15.0, step=1.0, key="cb_sb_budget")

    bid_calculado = round((cvr / 100) * precio * (target_acos / 100), 2)
    st.info(f"💡 Bid calculado: **${bid_calculado}**")

    st.markdown("#### Creatividad SB")
    brand_name = st.text_input("Brand Name (como aparece en Amazon)", key="cb_sb_brand_name")
    headline = st.text_input("Headline (máx 50 caracteres)", max_chars=50, key="cb_sb_headline")
    if headline:
        st.caption(f"{len(headline)}/50 caracteres")

    landing_page_type = st.selectbox(
        "Tipo de Landing Page",
        ["Product Collection", "Store Spotlight", "Custom URL"],
        key="cb_sb_landing_type",
    )
    landing_page_url = ""
    if landing_page_type == "Custom URL":
        landing_page_url = st.text_input("URL de la landing page", key="cb_sb_landing_url")

    creative_asins_input = st.text_input(
        "ASINs creativos (mín 3, separados por coma)",
        key="cb_sb_creative_asins",
        placeholder="B0CYLMJJJC, B0CYLM4L23, B0CYLDSQ5L",
        help="Sponsored Brands requiere mínimo 3 productos en la creatividad.",
    )
    creative_asins = [a.strip() for a in creative_asins_input.split(",") if a.strip()]
    if creative_asins and len(creative_asins) < 3:
        st.warning("⚠️ SB requiere mínimo 3 ASINs creativos.")

    if not brand_name or not headline:
        st.warning("Completá Brand Name y Headline para continuar.")
        return

    st.markdown("---")

    # ── Paso 3 — Clustering + naming ─────────────────────────────────────────
    st.markdown("### Paso 3 — Preview de campañas SB")

    brand_terms = [t.strip().lower() for t in marca.split(",")]
    df_kw = pd.DataFrame({"Keyword": keywords_list})
    df_kw["Cluster"] = df_kw["Keyword"].apply(lambda k: _detectar_cluster(str(k), brand_terms))

    cluster_counts = df_kw["Cluster"].value_counts()
    st.markdown("#### Distribución por cluster")
    cols_cl = st.columns(min(len(cluster_counts), 5))
    for i, (cluster, count) in enumerate(cluster_counts.items()):
        with cols_cl[i % len(cols_cl)]:
            st.markdown(kpi_card(cluster, str(count)), unsafe_allow_html=True)

    st.markdown("---")

    # ── Paso 4 — Generar bulk SB ─────────────────────────────────────────────
    st.markdown("### Paso 4 — Generar bulk SB")

    MAX_KW = 5
    start_date = datetime.now().strftime("%Y%m%d")
    creative_asin_1 = creative_asins[0] if len(creative_asins) > 0 else ""
    creative_asin_2 = creative_asins[1] if len(creative_asins) > 1 else ""
    creative_asin_3 = creative_asins[2] if len(creative_asins) > 2 else ""

    rows = []
    for cluster in df_kw["Cluster"].unique():
        kws = df_kw[df_kw["Cluster"] == cluster]["Keyword"].tolist()
        grupos = [kws[i:i+MAX_KW] for i in range(0, len(kws), MAX_KW)]

        for num, grupo in enumerate(grupos, 1):
            camp_name = _generar_nombre_campana_sb(marca, asin, cluster, "exact", num)
            ag_name = f"AG - {cluster} {num}"

            # Campaign row
            rows.append({
                "Product": "Sponsored Brands", "Entity": "Campaign", "Operation": "create",
                "Campaign ID": camp_name, "Ad Group ID": "", "Portfolio ID": portfolio_id,
                "Campaign Name": camp_name, "Ad Group Name": "",
                "Start Date": start_date, "End Date": "", "State": "enabled",
                "Daily Budget": budget, "Bidding Strategy": "Dynamic bidding (down only)",
                "Bid": "", "Keyword Text": "", "Match Type": "",
                "Creative Type": "Product Collection", "Brand Name": brand_name,
                "Headline": headline,
                "Creative ASIN 1": creative_asin_1,
                "Creative ASIN 2": creative_asin_2,
                "Creative ASIN 3": creative_asin_3,
                "Landing Page URL": landing_page_url if landing_page_type == "Custom URL" else "",
                "Landing Page Type": landing_page_type,
            })

            # Ad Group row
            rows.append({
                "Product": "Sponsored Brands", "Entity": "Ad Group", "Operation": "create",
                "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                "Campaign Name": camp_name, "Ad Group Name": ag_name,
                "Start Date": "", "End Date": "", "State": "enabled",
                "Daily Budget": "", "Bidding Strategy": "",
                "Bid": bid_calculado, "Keyword Text": "", "Match Type": "",
                "Creative Type": "", "Brand Name": "", "Headline": "",
                "Creative ASIN 1": "", "Creative ASIN 2": "", "Creative ASIN 3": "",
                "Landing Page URL": "", "Landing Page Type": "",
            })

            # Ad row
            rows.append({
                "Product": "Sponsored Brands", "Entity": "Ad", "Operation": "create",
                "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                "Campaign Name": camp_name, "Ad Group Name": ag_name,
                "Start Date": "", "End Date": "", "State": "enabled",
                "Daily Budget": "", "Bidding Strategy": "",
                "Bid": "", "Keyword Text": "", "Match Type": "",
                "Creative Type": "Product Collection", "Brand Name": brand_name,
                "Headline": headline,
                "Creative ASIN 1": creative_asin_1,
                "Creative ASIN 2": creative_asin_2,
                "Creative ASIN 3": creative_asin_3,
                "Landing Page URL": landing_page_url if landing_page_type == "Custom URL" else "",
                "Landing Page Type": landing_page_type,
            })

            # Keyword rows
            for kw in grupo:
                rows.append({
                    "Product": "Sponsored Brands", "Entity": "Keyword", "Operation": "create",
                    "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                    "Campaign Name": camp_name, "Ad Group Name": ag_name,
                    "Start Date": "", "End Date": "", "State": "enabled",
                    "Daily Budget": "", "Bidding Strategy": "",
                    "Bid": bid_calculado, "Keyword Text": kw, "Match Type": "exact",
                    "Creative Type": "", "Brand Name": "", "Headline": "",
                    "Creative ASIN 1": "", "Creative ASIN 2": "", "Creative ASIN 3": "",
                    "Landing Page URL": "", "Landing Page Type": "",
                })

    df_bulk = pd.DataFrame(rows)

    n_campanas = df_bulk[df_bulk["Entity"] == "Campaign"].shape[0]
    n_keywords = df_bulk[df_bulk["Entity"] == "Keyword"].shape[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card("Campañas SB", str(n_campanas)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Keywords", str(n_keywords)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Bid", f"${bid_calculado}"), unsafe_allow_html=True)

    st.markdown("#### Preview del bulk SB")
    df_preview = df_bulk[df_bulk["Entity"].isin(["Campaign", "Keyword"])][
        ["Entity", "Campaign Name", "Keyword Text", "Match Type", "Bid", "Daily Budget"]
    ].reset_index(drop=True)
    st.dataframe(df_preview, use_container_width=True, height=400)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_bulk.to_excel(writer, sheet_name="Sponsored Brands Campaigns", index=False)

    st.download_button(
        label=f"⬇️ Descargar bulk SB ({n_campanas} campañas, {n_keywords} keywords)",
        data=buf.getvalue(),
        file_name=f"campaign_bulk_SB_{marca}_{asin}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="cb_dl_sb",
    )


# ── SD Render ────────────────────────────────────────────────────────────────

def _render_sd():
    """Genera bulk de campañas Sponsored Display."""

    # ── Paso 1 — Targeting type ──────────────────────────────────────────────
    st.markdown("### Paso 1 — Tipo de targeting SD")
    targeting_type = st.radio(
        "¿Qué tipo de targeting?",
        ["🎯 Product Targeting", "👥 Audience Targeting"],
        horizontal=True, key="cb_sd_targeting_type",
    )
    is_pt = "Product" in targeting_type

    # ── Paso 2 — Datos del producto + campos SD ─────────────────────────────
    st.markdown("### Paso 2 — Datos del producto")

    p1, p2, p3 = st.columns(3)
    marca    = p1.text_input("Nombre de marca", key="cb_sd_marca")
    asin     = p2.text_input("ASIN principal", key="cb_sd_asin")
    sku      = p3.text_input("SKU principal", key="cb_sd_sku")

    p4, p5, p6 = st.columns(3)
    precio      = p4.number_input("Precio ($)", min_value=1.0, value=9.99, step=0.50, key="cb_sd_precio")
    cvr         = p5.number_input("CVR estimado (%)", min_value=1.0, value=10.0, step=0.5, key="cb_sd_cvr")
    target_acos = p6.number_input("Target ACoS (%)", min_value=1.0, value=20.0, step=1.0, key="cb_sd_tacos")

    p7, p8 = st.columns(2)
    portfolio_id = p7.text_input("Portfolio ID (opcional)", key="cb_sd_portfolio")
    budget       = p8.number_input("Budget diario ($)", min_value=1.0, value=10.0, step=1.0, key="cb_sd_budget")

    bid_calculado = round((cvr / 100) * precio * (target_acos / 100), 2)
    st.info(f"💡 Bid calculado: **${bid_calculado}**")

    bid_optimization = st.selectbox(
        "Bid Optimization",
        ["Conversions", "Page visits", "Reach"],
        key="cb_sd_bid_opt",
        help="Conversions = optimiza para compras. Page visits = optimiza para clicks. Reach = máxima visibilidad.",
    )

    st.markdown("---")

    # ── Targets ──────────────────────────────────────────────────────────────
    targets = []
    subtipo = ""
    if is_pt:
        st.markdown("### Targets — Product Targeting")
        pt_mode = st.radio(
            "Tipo de target",
            ["ASINs competidores", "Categorías"],
            horizontal=True, key="cb_sd_pt_mode",
        )
        if pt_mode == "ASINs competidores":
            subtipo = "Competitor ASIN"
            asins_text = st.text_area(
                "ASINs competidores (uno por línea)", height=150, key="cb_sd_asins",
                placeholder="B0XXXXXXX1\nB0XXXXXXX2\nB0XXXXXXX3",
            )
            if asins_text.strip():
                targets = [a.strip() for a in asins_text.strip().splitlines() if a.strip()]
                st.success(f"✅ {len(targets)} ASINs cargados")
        else:
            subtipo = "Category"
            cats_text = st.text_area(
                "Category IDs (uno por línea)", height=150, key="cb_sd_cats",
                placeholder="12345678\n87654321",
                help="Encontrá el Category ID en la URL de la categoría de Amazon.",
            )
            if cats_text.strip():
                targets = [c.strip() for c in cats_text.strip().splitlines() if c.strip()]
                st.success(f"✅ {len(targets)} categorías cargadas")
    else:
        st.markdown("### Targets — Audience Targeting")
        audience_type = st.selectbox(
            "Tipo de audiencia",
            ["Views Remarketing", "Purchases Remarketing", "Similar Products"],
            key="cb_sd_audience_type",
        )
        subtipo = audience_type.replace(" ", "_")
        # For audiences, we create one campaign per audience type
        targets = [audience_type]
        st.info(f"Se creará 1 campaña SD con audiencia **{audience_type}**")

    if not targets:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>📂</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Ingresá los targets para continuar</div>"
            "</div>", unsafe_allow_html=True,
        )
        return

    st.markdown("---")

    # ── Paso 3 — Generar bulk SD ─────────────────────────────────────────────
    st.markdown("### Paso 3 — Preview de campañas SD")

    MAX_TARGETS = 5
    start_date = datetime.now().strftime("%Y%m%d")
    tgt_type_label = "PT" if is_pt else "AUD"

    rows = []
    grupos = [targets[i:i+MAX_TARGETS] for i in range(0, len(targets), MAX_TARGETS)]

    for num, grupo in enumerate(grupos, 1):
        camp_name = _generar_nombre_campana_sd(marca, asin, tgt_type_label, subtipo, num)
        ag_name = f"AG - {subtipo} {num}"

        # Campaign row
        rows.append({
            "Product": "Sponsored Display", "Entity": "Campaign", "Operation": "create",
            "Campaign ID": camp_name, "Ad Group ID": "", "Portfolio ID": portfolio_id,
            "Campaign Name": camp_name, "Ad Group Name": "",
            "Start Date": start_date, "End Date": "", "State": "enabled",
            "Daily Budget": budget, "Bidding Strategy": "",
            "Bid": "", "Bid Optimization": bid_optimization.lower(),
            "SKU": "", "Product Targeting Expression": "", "Audience ID": "",
        })

        # Ad Group row
        rows.append({
            "Product": "Sponsored Display", "Entity": "Ad Group", "Operation": "create",
            "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
            "Campaign Name": camp_name, "Ad Group Name": ag_name,
            "Start Date": "", "End Date": "", "State": "enabled",
            "Daily Budget": "", "Bidding Strategy": "",
            "Bid": bid_calculado, "Bid Optimization": "",
            "SKU": "", "Product Targeting Expression": "", "Audience ID": "",
        })

        # Product Ad row
        if sku:
            rows.append({
                "Product": "Sponsored Display", "Entity": "Product Ad", "Operation": "create",
                "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                "Campaign Name": camp_name, "Ad Group Name": ag_name,
                "Start Date": "", "End Date": "", "State": "enabled",
                "Daily Budget": "", "Bidding Strategy": "",
                "Bid": "", "Bid Optimization": "",
                "SKU": sku, "Product Targeting Expression": "", "Audience ID": "",
            })

        # Target rows
        for target in grupo:
            if is_pt:
                if subtipo == "Competitor ASIN":
                    expression = f'asin="{target.upper()}"'
                else:
                    expression = f'category="{target}"'
                rows.append({
                    "Product": "Sponsored Display", "Entity": "Product Targeting",
                    "Operation": "create",
                    "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                    "Campaign Name": camp_name, "Ad Group Name": ag_name,
                    "Start Date": "", "End Date": "", "State": "enabled",
                    "Daily Budget": "", "Bidding Strategy": "",
                    "Bid": bid_calculado, "Bid Optimization": "",
                    "SKU": "", "Product Targeting Expression": expression, "Audience ID": "",
                })
            else:
                rows.append({
                    "Product": "Sponsored Display", "Entity": "Audience",
                    "Operation": "create",
                    "Campaign ID": camp_name, "Ad Group ID": ag_name, "Portfolio ID": "",
                    "Campaign Name": camp_name, "Ad Group Name": ag_name,
                    "Start Date": "", "End Date": "", "State": "enabled",
                    "Daily Budget": "", "Bidding Strategy": "",
                    "Bid": bid_calculado, "Bid Optimization": "",
                    "SKU": "", "Product Targeting Expression": "",
                    "Audience ID": target.lower().replace(" ", "-"),
                })

    df_bulk = pd.DataFrame(rows)

    n_campanas = df_bulk[df_bulk["Entity"] == "Campaign"].shape[0]
    n_targets = df_bulk[df_bulk["Entity"].isin(["Product Targeting", "Audience"])].shape[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card("Campañas SD", str(n_campanas)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Targets", str(n_targets)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Bid", f"${bid_calculado}"), unsafe_allow_html=True)

    st.markdown("#### Preview del bulk SD")
    entity_filter = ["Campaign", "Product Targeting", "Audience"]
    cols_show = ["Entity", "Campaign Name", "Product Targeting Expression", "Audience ID", "Bid", "Daily Budget"]
    cols_show = [c for c in cols_show if c in df_bulk.columns]
    df_preview = df_bulk[df_bulk["Entity"].isin(entity_filter)][cols_show].reset_index(drop=True)
    st.dataframe(df_preview, use_container_width=True, height=400)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_bulk.to_excel(writer, sheet_name="Sponsored Display Campaigns", index=False)

    st.download_button(
        label=f"⬇️ Descargar bulk SD ({n_campanas} campañas, {n_targets} targets)",
        data=buf.getvalue(),
        file_name=f"campaign_bulk_SD_{marca}_{asin}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="cb_dl_sd",
    )


# ── Render principal ─────────────────────────────────────────────────────────

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🚀</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>Campaign Builder</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Genera bulks SP, SB y SD listos para subir a Amazon</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Generar bulk listo para subir a Amazon con campañas SP nuevas clusterizadas por intención.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Plan de Acción bulk (output del Análisis Cruzado M4, .xlsx).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Atom11 Rules Builder (M11) para automatizar las campañas nuevas.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el Plan de Acción bulk\n"
            "2. Completá datos del producto: marca, ASIN, SKU, precio, CVR, target ACoS, budget\n"
            "3. Revisá preview de campañas clusterizadas (PAT / Spanish / Brand / Discovery)\n"
            "4. Validá naming y max 5 KWs por campaña\n"
            "5. Descargá bulk formato exacto Amazon"
        )

    # ── Selector de tipo de campaña ──────────────────────────────────────────
    st.markdown("### Tipo de campaña")
    campaign_type = st.radio(
        "¿Qué tipo de campañas querés generar?",
        options=["🎯 Sponsored Products (SP)", "📢 Sponsored Brands (SB)", "🖥️ Sponsored Display (SD)"],
        horizontal=True,
        key="cb_campaign_type",
    )

    st.markdown("---")

    if "SB" in campaign_type:
        _render_sb()
        return
    if "SD" in campaign_type:
        _render_sd()
        return

    # ── SP flow (lógica original) ────────────────────────────────────────────
    st.markdown("### Paso 1 — Subí el Plan de Acción bulk")
    st.caption("El archivo generado en Análisis Cruzado → Plan de Acción → Descargar bulk.")

    file_plan = st.file_uploader(
        "Plan de Acción bulk (.xlsx)",
        type=["xlsx"],
        key="cb_plan_sp"
    )

    if not file_plan:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>📂</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Subí el Plan de Acción bulk</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
            "Generalo en: Análisis Cruzado → tab Plan de Acción → Descargar bulk</div>"
            "</div>", unsafe_allow_html=True,
        )
        return

    df_plan = pd.read_excel(file_plan)
    st.success(f"✅ {len(df_plan)} keywords cargadas")

    # Validar columnas mínimas
    if "Keyword" not in df_plan.columns:
        st.error("❌ El archivo no tiene columna 'Keyword'. Verificá que sea el Plan de Acción bulk.")
        return

    st.markdown("---")

    # ── PASO 2 — Datos del producto ───────────────────────────────────────────
    st.markdown("### Paso 2 — Datos del producto")

    p1, p2, p3 = st.columns(3)
    marca    = p1.text_input("Nombre de marca", value="Dermaglos", key="cb_marca")
    asin     = p2.text_input("ASIN principal", value="B0CYLMJJJC", key="cb_asin")
    sku      = p3.text_input("SKU principal", value="", key="cb_sku")

    p4, p5, p6 = st.columns(3)
    precio       = p4.number_input("Precio ($)", min_value=1.0, value=9.99, step=0.50, key="cb_precio")
    cvr          = p5.number_input("CVR estimado (%)", min_value=1.0, value=10.0, step=0.5, key="cb_cvr")
    target_acos  = p6.number_input("Target ACoS (%)", min_value=1.0, value=20.0, step=1.0, key="cb_tacos")

    p7, p8 = st.columns(2)
    portfolio_id = p7.text_input("Portfolio ID (opcional)", value="", key="cb_portfolio",
                                  help="ID numérico del portfolio en Amazon Ads. Dejalo vacío si no usás portfolios.")
    budget       = p8.number_input("Budget diario por campaña ($)", min_value=1.0, value=10.0, step=1.0, key="cb_budget")

    bid_calculado = round((cvr / 100) * precio * (target_acos / 100), 2)
    st.info(f"💡 Bid calculado automáticamente: **${bid_calculado}** (CVR {cvr}% × precio ${precio} × target ACoS {target_acos}%)")

    st.markdown("---")

    # ── PASO 3 — Filtrar y clusterizar ───────────────────────────────────────
    st.markdown("### Paso 3 — Preview de campañas generadas")

    # Filtrar solo accionables (excluir NO ATACAR y MONITOREAR)
    acciones_incluir = ["⚡ ESCALAR", "➕ AGREGAR keyword", "🛡️ DEFENDER marca"]
    if "Acción sugerida" in df_plan.columns:
        df_kw = df_plan[df_plan["Acción sugerida"].isin(acciones_incluir)].copy()
        n_excluidas = len(df_plan) - len(df_kw)
        if n_excluidas > 0:
            st.caption(f"ℹ️ {n_excluidas} keywords excluidas (NO ATACAR / MONITOREAR / BAJAR BID)")
    else:
        df_kw = df_plan.copy()

    if df_kw.empty:
        st.warning("No hay keywords accionables en el Plan de Acción.")
        return

    # ── Clasificar por confianza ──────────────────────────────────────────
    def _confianza(row):
        accion       = str(row.get("Acción sugerida", ""))
        brand_count  = float(row.get("Purchases mercado", 0) or 0)
        brand_share  = float(row.get("Brand Share %", 0) or 0)

        # ESCALAR y DEFENDER siempre van — ya tienen historial
        if accion in ["⚡ ESCALAR", "🛡️ DEFENDER marca"]:
            return "✅ LANZAR AHORA"

        # AGREGAR — clasificar por evidencia
        if accion == "➕ AGREGAR keyword":
            if brand_share > 0:
                return "✅ LANZAR AHORA"   # ya aparecemos orgánicamente
            if brand_count >= 1:
                return "✅ LANZAR AHORA"   # el mercado ya nos compra por esta query
            return "⚠️ PROBAR"             # oportunidad sin historial propio

        return "⚠️ PROBAR"

    df_kw["Confianza"] = df_kw.apply(_confianza, axis=1)

    # ── Selector de confianza ─────────────────────────────────────────────
    st.markdown("#### Filtro de confianza")
    st.caption("**✅ LANZAR AHORA** — keywords con historial propio (ESCALAR, DEFENDER, o AGREGAR con Brand Share > 0). **⚠️ PROBAR** — oportunidades sin historial propio, lanzar con bid conservador.")

    n_lanzar = (df_kw["Confianza"] == "✅ LANZAR AHORA").sum()
    n_probar = (df_kw["Confianza"] == "⚠️ PROBAR").sum()

    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown(kpi_card("LANZAR AHORA", str(n_lanzar)), unsafe_allow_html=True)
    with fc2:
        st.markdown(kpi_card("PROBAR", str(n_probar)), unsafe_allow_html=True)

    incluir_confianza = st.multiselect(
        "¿Qué keywords incluir en el bulk?",
        options=["✅ LANZAR AHORA", "⚠️ PROBAR"],
        default=["✅ LANZAR AHORA"],
        key="cb_confianza",
        help="LANZAR AHORA = historial propio confirmado. PROBAR = oportunidad nueva sin historial — usar bid conservador."
    )

    df_kw = df_kw[df_kw["Confianza"].isin(incluir_confianza)].copy()

    if df_kw.empty:
        st.warning("No hay keywords con el nivel de confianza seleccionado.")
        return

    st.caption(f"→ {len(df_kw)} keywords incluidas en el bulk")
    st.markdown("---")

    # Detectar cluster por keyword
    brand_terms = [t.strip().lower() for t in marca.split(",")]
    df_kw["Cluster"] = df_kw["Keyword"].apply(
        lambda k: _detectar_cluster(str(k), brand_terms)
    )

    # Mostrar distribución de clusters
    cluster_counts = df_kw["Cluster"].value_counts()
    st.markdown("#### Distribución por cluster")
    cols_cl = st.columns(min(len(cluster_counts), 5))
    for i, (cluster, count) in enumerate(cluster_counts.items()):
        with cols_cl[i % len(cols_cl)]:
            st.markdown(kpi_card(cluster, str(count)), unsafe_allow_html=True)

    st.markdown("---")

    # ── PASO 4 — Generar bulk ─────────────────────────────────────────────────
    # Agrupar en campañas de MAX 5 keywords por cluster
    MAX_KW_POR_CAMPANA = 5
    start_date = datetime.now().strftime("%Y%m%d")

    rows = []
    for cluster in df_kw["Cluster"].unique():
        df_cluster = df_kw[df_kw["Cluster"] == cluster].copy()
        keywords = df_cluster["Keyword"].tolist()
        is_pat = cluster == "PAT"

        # Dividir en grupos de MAX 5
        grupos = [keywords[i:i+MAX_KW_POR_CAMPANA]
                  for i in range(0, len(keywords), MAX_KW_POR_CAMPANA)]

        for num, grupo in enumerate(grupos, start=1):
            camp_name = _generar_nombre_campana(marca, asin, cluster, "exact", num)
            ag_name   = _generar_nombre_adgroup(cluster, num)

            # Fila Campaign — Regla #3: Campaign ID = Campaign Name
            fila_camp = _fila_vacia_bulk()
            fila_camp.update({
                "Product":          "Sponsored Products",
                "Entity":           "Campaign",
                "Operation":        "create",
                "Campaign ID":      camp_name,
                "Portfolio ID":     portfolio_id,
                "Campaign Name":    camp_name,
                "Start Date":       start_date,       # Regla #4: yyyyMMdd
                "Targeting Type":   "MANUAL",         # Regla #8
                "State":            "enabled",
                "Daily Budget":     budget,
                "Bidding Strategy": "Dynamic bids - down only",  # Regla #5
            })
            rows.append(fila_camp)

            # Fila Ad Group — Regla #3: Campaign ID y Ad Group ID = nombres
            fila_ag = _fila_vacia_bulk()
            fila_ag.update({
                "Product":              "Sponsored Products",
                "Entity":               "Ad Group",
                "Operation":            "create",
                "Campaign ID":          camp_name,
                "Ad Group ID":          ag_name,
                "Campaign Name":        camp_name,
                "Ad Group Name":        ag_name,
                "State":                "enabled",
                "Ad Group Default Bid": bid_calculado,
            })
            rows.append(fila_ag)

            # Fila Product Ad (SKU) — Regla #3: Campaign ID y Ad Group ID = nombres
            if sku:
                fila_ad = _fila_vacia_bulk()
                fila_ad.update({
                    "Product":       "Sponsored Products",
                    "Entity":        "Product Ad",
                    "Operation":     "create",
                    "Campaign ID":   camp_name,
                    "Ad Group ID":   ag_name,
                    "Campaign Name": camp_name,
                    "Ad Group Name": ag_name,
                    "State":         "enabled",
                    "SKU":           sku,
                })
                rows.append(fila_ad)

            # Filas de targets (Keywords o Product Targeting para PAT)
            for kw in grupo:
                fila_target = _fila_vacia_bulk()
                if is_pat:
                    # Regla #6: usar Product Targeting Expression, NO Product Targeting ID
                    fila_target.update({
                        "Product":                      "Sponsored Products",
                        "Entity":                       "Product Targeting",
                        "Operation":                    "create",
                        "Campaign ID":                  camp_name,
                        "Ad Group ID":                  ag_name,
                        "Campaign Name":                camp_name,
                        "Ad Group Name":                ag_name,
                        "State":                        "enabled",
                        "Bid":                          bid_calculado,
                        "Product Targeting Expression": f'asin="{kw.upper()}"',
                    })
                else:
                    fila_target.update({
                        "Product":       "Sponsored Products",
                        "Entity":        "Keyword",
                        "Operation":     "create",
                        "Campaign ID":   camp_name,
                        "Ad Group ID":   ag_name,
                        "Campaign Name": camp_name,
                        "Ad Group Name": ag_name,
                        "State":         "enabled",
                        "Bid":           bid_calculado,
                        "Keyword Text":  kw,
                        "Match Type":    "exact",
                    })
                rows.append(fila_target)

    # Orden exacto de columnas Amazon 2026 (31 columnas) — ver _BULK_COLUMNS_2026
    df_bulk = pd.DataFrame(rows, columns=_BULK_COLUMNS_2026)

    # ── Preview tabla ─────────────────────────────────────────────────────────
    n_campanas = df_bulk[df_bulk["Entity"] == "Campaign"].shape[0]
    n_keywords = df_bulk[df_bulk["Entity"].isin(["Keyword", "Product Targeting"])].shape[0]

    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown(kpi_card("Campañas a crear", str(n_campanas)), unsafe_allow_html=True)
    with b2:
        st.markdown(kpi_card("Keywords / targets", str(n_keywords)), unsafe_allow_html=True)
    with b3:
        st.markdown(kpi_card("Bid por keyword", f"${bid_calculado}"), unsafe_allow_html=True)

    st.markdown("#### Preview del bulk")
    st.caption("Revisá antes de descargar. Campaign Name y Ad Group Name ya están completos.")
    df_preview = df_bulk[df_bulk["Entity"].isin(["Campaign", "Keyword", "Product Targeting"])][
        ["Entity", "Campaign Name", "Ad Group Name", "Keyword Text", "Product Targeting Expression", "Match Type", "Bid", "Daily Budget"]
    ].dropna(how="all").reset_index(drop=True)
    st.dataframe(df_preview, use_container_width=True, height=400)

    st.markdown("---")

    # ── Export en formato exacto Amazon ──────────────────────────────────────
    st.markdown("#### Export bulk — formato exacto Amazon")
    st.caption("Listo para subir directo a Campaign Manager. 31 columnas (incluye 'Sites' Q2 2026) en el orden exacto que Amazon requiere.")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_bulk.to_excel(writer, sheet_name="Sponsored Products Campaigns", index=False)

    st.download_button(
        label=f"Descargar bulk Amazon ({n_campanas} campañas, {n_keywords} keywords)",
        data=buf.getvalue(),
        file_name=f"campaign_bulk_{marca}_{asin}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="cb_dl_sp"
    )

    st.warning("Revisá el Campaign Name y Ad Group Name antes de subir. Las operaciones UPDATE (pausar existentes) requieren Campaign ID numérico — hacelas manualmente en Campaign Manager.")
