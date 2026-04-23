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
    """
    Genera bulk SB (Sponsored Brands) con soporte SBV + SBH + Brand Entity ID (2026).
    Consume los helpers _build_sb_bulk_rows y _SB_COLS_2026.
    """

    # ── Paso 0 — Selector SBV vs SBH ─────────────────────────────────────────
    st.markdown("### Tipo de Sponsored Brand")
    sb_type_label = st.radio(
        "¿Qué formato de SB querés generar?",
        options=[
            "📹 SBV — Sponsored Brand Video",
            "🖼️ SBH — Sponsored Brand Headlines",
        ],
        horizontal=True,
        key="cb_sb_v2_type",
        help=(
            "SBV: video ad en resultados de búsqueda. Requiere Video Asset ID. "
            "SBH: banner con imagen, headline y productos arriba de los resultados. "
            "Requiere Brand Logo Asset ID."
        ),
    )
    sb_type = "SBV" if "SBV" in sb_type_label else "SBH"

    # Descripción visual del tipo elegido
    if sb_type == "SBV":
        st.caption(
            "📹 **Sponsored Brand Video** — ad de video que aparece en la primera página de resultados. "
            "Requiere un Video Asset ID generado en Amazon Ads Console."
        )
    else:
        st.caption(
            "🖼️ **Sponsored Brand Headlines** — banner con logo, headline custom y 3+ productos que aparece arriba "
            "de los resultados orgánicos. Requiere Brand Logo Asset ID y headline corto."
        )

    st.markdown("---")

    # ── Paso 1 — Keywords (flujo idéntico al anterior) ───────────────────────
    st.markdown("### Paso 1 — Keywords para SB")
    st.caption("Subí el Plan de Acción o ingresá keywords manualmente.")

    input_mode = st.radio(
        "Fuente de keywords",
        ["📄 Plan de Acción bulk", "✏️ Input manual"],
        horizontal=True,
        key="cb_sb_v2_input_mode",
    )

    keywords_list = []
    if input_mode == "📄 Plan de Acción bulk":
        file_plan = st.file_uploader(
            "Plan de Acción (.xlsx)",
            type=["xlsx"],
            key="cb_sb_v2_plan",
        )
        if not file_plan:
            st.markdown(
                "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
                "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
                "<div style='font-size:1.5rem;'>📂</div>"
                "<div style='font-weight:600;margin-top:0.5rem;'>Subí el Plan de Acción bulk</div>"
                "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
                "Generalo en: Análisis Cruzado → Plan de Acción → Descargar bulk</div>"
                "</div>",
                unsafe_allow_html=True,
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
            "Keywords (una por línea)",
            height=150,
            key="cb_sb_v2_kw_manual",
            placeholder="vitamin a cream\ncrema hidratante\ndermaglos lotion",
        )
        if kw_text.strip():
            keywords_list = [k.strip() for k in kw_text.strip().splitlines() if k.strip()]
            st.success(f"✅ {len(keywords_list)} keywords ingresadas")

    if not keywords_list:
        return

    st.markdown("---")

    # ── Paso 2 — Datos del producto + Brand Entity ID + TOS% ────────────────
    st.markdown("### Paso 2 — Datos del producto y configuración")

    p1, p2, p3 = st.columns(3)
    marca = p1.text_input("Nombre de marca", key="cb_sb_v2_marca")
    asin = p2.text_input("ASIN principal", key="cb_sb_v2_asin")
    sku = p3.text_input("SKU principal", key="cb_sb_v2_sku")

    p4, p5, p6 = st.columns(3)
    precio = p4.number_input(
        "Precio ($)", min_value=1.0, value=9.99, step=0.50, key="cb_sb_v2_precio"
    )
    cvr = p5.number_input(
        "CVR estimado (%)", min_value=1.0, value=10.0, step=0.5, key="cb_sb_v2_cvr"
    )
    target_acos = p6.number_input(
        "Target ACoS (%)", min_value=1.0, value=20.0, step=1.0, key="cb_sb_v2_tacos"
    )

    p7, p8, p9 = st.columns(3)
    portfolio_id = p7.text_input(
        "Portfolio ID (opcional)",
        key="cb_sb_v2_portfolio",
        help="ID numérico del portfolio Amazon Ads. Dejar vacío si no usás portfolios.",
    )
    budget = p8.number_input(
        "Budget diario ($)",
        min_value=1.0,
        value=15.0,
        step=1.0,
        key="cb_sb_v2_budget",
    )
    tos_pct = p9.number_input(
        "TOS % (Placement Top of Search)",
        min_value=0.0,
        max_value=900.0,
        value=50.0,
        step=5.0,
        key="cb_sb_v2_tos",
        help="Bid boost % para Top of Search placement. Default 50% es el recomendado.",
    )

    # Brand Entity ID — NUEVO campo obligatorio Amazon 2026
    brand_entity_id = st.text_input(
        "🔑 Brand Entity ID (obligatorio — Amazon Ads 2026)",
        key="cb_sb_v2_brand_entity_id",
        help=(
            "ID único de la marca en Amazon Ads. Obtenelo en: Amazon Ads Console → "
            "Account settings → Brand Entity. Sin este campo, Amazon rechaza los bulks SB en 2026."
        ),
        placeholder="ENTITY1ABC2DEF3",
    )

    bid_calculado = round((cvr / 100) * precio * (target_acos / 100), 2)
    st.info(
        f"💡 **Bid calculado: \\${bid_calculado}** "
        f"(CVR {cvr}% × precio \\${precio} × target ACoS {target_acos}%)"
    )

    if not marca or not asin:
        st.warning("Completá marca y ASIN para continuar.")
        return

    if not brand_entity_id:
        st.warning("⚠️ Brand Entity ID es obligatorio en bulks SB 2026.")
        return

    st.markdown("---")

    # ── Paso 3 — Creatividad (campos específicos SBV o SBH) ──────────────────
    st.markdown(f"### Paso 3 — Creatividad {sb_type}")

    # Campos compartidos SBV + SBH
    brand_name = st.text_input(
        "Brand Name (como aparece en Amazon)",
        key="cb_sb_v2_brand_name",
        help="Nombre exacto de la marca registrada en Amazon. Case-sensitive.",
    )

    creative_headline = st.text_input(
        f"Creative Headline (máx 50 caracteres)",
        max_chars=50,
        key="cb_sb_v2_creative_headline",
        help="Texto que aparece en el ad. Máximo 50 caracteres. No usar mayúsculas gratuitas ni promociones agresivas.",
    )
    if creative_headline:
        st.caption(f"{len(creative_headline)}/50 caracteres")

    landing_page_type = st.selectbox(
        "Landing Page Type",
        options=["Product Collection", "Store Spotlight", "Custom URL"],
        key="cb_sb_v2_landing_type",
    )
    landing_page_url = ""
    if landing_page_type == "Custom URL":
        landing_page_url = st.text_input(
            "Landing Page URL",
            key="cb_sb_v2_landing_url",
            placeholder="https://www.amazon.com/stores/page/...",
        )

    creative_asins_input = st.text_input(
        "Creative ASINs (mín 3, separados por coma)",
        key="cb_sb_v2_creative_asins",
        placeholder="B0CYLMJJJC, B0CYLM4L23, B0CYLDSQ5L",
        help="Sponsored Brands requiere mínimo 3 productos en la creatividad.",
    )
    creative_asins = [a.strip() for a in creative_asins_input.split(",") if a.strip()]

    # Campos específicos según tipo
    video_asset_id = ""
    brand_logo_asset_id = ""
    brand_logo_url = ""
    brand_logo_crop = "Square"

    if sb_type == "SBV":
        st.markdown("#### 📹 Campos SBV (Sponsored Brand Video)")
        video_asset_id = st.text_input(
            "Video Asset ID (obligatorio)",
            key="cb_sb_v2_video_asset_id",
            placeholder="amzn1.assetlibrary.asset.xxxxxxxxxxxx",
            help=(
                "ID del video subido a Amazon Ads Console → Creative Assets → Video. "
                "Sin esto, el bulk SBV se rechaza."
            ),
        )
    else:  # SBH
        st.markdown("#### 🖼️ Campos SBH (Sponsored Brand Headlines)")
        sbh_c1, sbh_c2 = st.columns([2, 1])
        brand_logo_asset_id = sbh_c1.text_input(
            "Brand Logo Asset ID (obligatorio)",
            key="cb_sb_v2_brand_logo_asset_id",
            placeholder="amzn1.assetlibrary.asset.xxxxxxxxxxxx",
            help=(
                "ID del logo de la marca subido a Amazon Ads Console → Creative Assets → Image. "
                "Sin esto, el bulk SBH se rechaza."
            ),
        )
        brand_logo_crop = sbh_c2.selectbox(
            "Logo Crop",
            options=["Square", "Rectangle"],
            key="cb_sb_v2_brand_logo_crop",
            help="Forma del logo en el banner. Square = 1:1, Rectangle = horizontal.",
        )
        brand_logo_url = st.text_input(
            "Brand Logo URL (opcional, informativo)",
            key="cb_sb_v2_brand_logo_url",
            help="URL del logo — campo informativo para referencia del AM, no lo usa Amazon.",
            placeholder="https://...",
        )

    st.markdown("---")

    # ── Paso 4 — Preview + validación + descarga ─────────────────────────────
    st.markdown("### Paso 4 — Preview y descarga")

    # Validaciones estrictas ANTES de generar el bulk
    errores = []
    if not brand_name:
        errores.append("Brand Name vacío")
    if not creative_headline:
        errores.append("Creative Headline vacío")
    if len(creative_asins) < 3:
        errores.append(f"Creative ASINs insuficientes ({len(creative_asins)}/3 mínimo)")
    if sb_type == "SBV" and not video_asset_id:
        errores.append("Video Asset ID vacío (obligatorio en SBV)")
    if sb_type == "SBH" and not brand_logo_asset_id:
        errores.append("Brand Logo Asset ID vacío (obligatorio en SBH)")
    if landing_page_type == "Custom URL" and not landing_page_url:
        errores.append("Landing Page URL vacío (requerido para Custom URL)")

    if errores:
        st.error(
            "⚠️ Completá lo siguiente antes de descargar:\n\n"
            + "\n".join(f"- {e}" for e in errores)
        )
        return

    # Generar bulk — agrupar keywords en campañas de MAX 5 KWs (regla Capybaras)
    MAX_KW_POR_CAMPANA = 5
    start_date = datetime.now().strftime("%Y%m%d")

    # Split keywords en grupos de 5
    grupos = [
        keywords_list[i:i + MAX_KW_POR_CAMPANA]
        for i in range(0, len(keywords_list), MAX_KW_POR_CAMPANA)
    ]

    all_rows = []
    for num, grupo in enumerate(grupos, start=1):
        camp_name = _generar_nombre_campana_sb(marca, asin, "Brand", "exact", num)
        ag_name = f"AG - Brand {num}"

        rows = _build_sb_bulk_rows(
            campaign_name=camp_name,
            ag_name=ag_name,
            keywords=grupo,
            bid=bid_calculado,
            budget=budget,
            tos_pct=tos_pct,
            sb_type=sb_type,
            brand_entity_id=brand_entity_id,
            portfolio_id=portfolio_id,
            video_asset_id=video_asset_id,
            brand_logo_asset_id=brand_logo_asset_id,
            brand_logo_url=brand_logo_url,
            brand_logo_crop=brand_logo_crop,
            creative_headline=creative_headline,
            creative_asins=creative_asins,
            brand_name=brand_name,
            landing_page_type=landing_page_type,
            landing_page_url=landing_page_url,
            start_date=start_date,
        )
        all_rows.extend(rows)

    df_bulk = pd.DataFrame(all_rows, columns=_SB_COLS_2026)

    # KPI cards
    n_campanas = df_bulk[df_bulk["Entity"] == "Campaign"].shape[0]
    n_keywords = df_bulk[df_bulk["Entity"] == "Keyword"].shape[0]
    n_ads = df_bulk[df_bulk["Entity"].isin(["Brand Video Ad", "Headline Ad"])].shape[0]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card(f"Campañas {sb_type}", str(n_campanas)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Keywords", str(n_keywords)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Ads", str(n_ads)), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Bid", f"${bid_calculado}"), unsafe_allow_html=True)

    # Preview
    st.markdown("#### Preview del bulk SB")
    cols_show = ["Entity", "Campaign Name", "Keyword Text", "Match Type", "Bid", "Budget"]
    df_preview = df_bulk[cols_show].reset_index(drop=True)
    st.dataframe(df_preview, use_container_width=True, height=400)

    # Descarga
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_bulk.to_excel(writer, sheet_name="Sponsored Brands Campaigns", index=False)

    st.download_button(
        label=f"⬇️ Descargar bulk {sb_type} ({n_campanas} campañas, {n_keywords} keywords)",
        data=buf.getvalue(),
        file_name=f"campaign_bulk_{sb_type}_{marca}_{asin}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="cb_sb_v2_dl",
    )

    st.success(
        f"✅ Bulk {sb_type} listo: **{n_campanas} campañas** con **{n_keywords} keywords** "
        f"(max {MAX_KW_POR_CAMPANA} KWs/campaña · naming Capybaras · 29 columnas Amazon 2026)."
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
    st.info(f"💡 **Bid calculado: \\${bid_calculado}**")

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


# ══════════════════════════════════════════════════════════════════════════════
# SB 2026 — Columnas y helpers para bulk Sponsored Brands (SBV + SBH)
# ══════════════════════════════════════════════════════════════════════════════

# ⚠️ "Ad Group ID" tiene un espacio delante — es un bug conocido de Amazon,
# NO quitar el espacio, los bulks se rechazan sin él.
_SB_COLS_2026 = [
    "Product", "Entity", "Operation", "Campaign ID", "Portfolio ID", " Ad Group ID",
    "Campaign Name", "Ad Group Name", "Ad Name", "Start Date", "End Date", "State",
    "Brand Entity ID", "Budget Type", "Budget", "Bid Optimization", "Bid",
    "Placement", "Percentage", "Keyword Text", "Match Type",
    "Landing Page URL", "Landing Page Type", "Brand Name",
    "Brand Logo Asset ID", "Brand Logo URL (Informational only)", "Brand Logo Crop",
    "Creative Headline", "Creative ASINs", "Video Asset IDs",
]


def _sb_row_factory(**kwargs) -> dict:
    """Genera una fila bulk SB con las 29 columnas Amazon 2026. kwargs sobrescriben valores específicos."""
    row = {col: None for col in _SB_COLS_2026}
    row.update(kwargs)
    return row


def _build_sb_bulk_rows(
    campaign_name: str,
    ag_name: str,
    keywords: list,
    bid: float,
    budget: float,
    tos_pct: float,
    sb_type: str,  # "SBV" o "SBH"
    brand_entity_id: str,
    portfolio_id: str = "",
    # SBV fields
    video_asset_id: str = "",
    # SBH fields
    brand_logo_asset_id: str = "",
    brand_logo_url: str = "",
    brand_logo_crop: str = "Square",
    # Shared creative
    creative_headline: str = "",
    creative_asins: list = None,
    brand_name: str = "",
    landing_page_type: str = "Product Collection",
    landing_page_url: str = "",
    start_date: str = "",
) -> list:
    """
    Genera las filas bulk para una campaña SB (SBV o SBH).
    Retorna lista de dicts con las 29 columnas SB 2026.

    Estructura: Campaign → Bidding Adjustment → Ad Group → Ad(s) → Keyword(s)
    """
    creative_asins = creative_asins or []
    creative_asins_str = ", ".join(creative_asins) if creative_asins else ""
    ad_entity = "Brand Video Ad" if sb_type == "SBV" else "Headline Ad"
    rows = []

    # 1. Campaign
    rows.append(_sb_row_factory(**{
        "Product": "Sponsored Brands",
        "Entity": "Campaign",
        "Operation": "Create",
        "Campaign ID": campaign_name,
        "Portfolio ID": portfolio_id,
        "Campaign Name": campaign_name,
        "Start Date": start_date,
        "State": "enabled",
        "Brand Entity ID": brand_entity_id,
        "Budget Type": "Daily",
        "Budget": float(budget),
        "Bid Optimization": False,
    }))

    # 2. Bidding Adjustment by Placement
    rows.append(_sb_row_factory(**{
        "Product": "Sponsored Brands",
        "Entity": "Bidding Adjustment by Placement",
        "Operation": "Create",
        "Campaign ID": campaign_name,
        "State": "enabled",
        "Placement": "Top of Search",
        "Percentage": float(tos_pct),
    }))

    # 3. Ad Group (1 por campaña)
    rows.append(_sb_row_factory(**{
        "Product": "Sponsored Brands",
        "Entity": "Ad Group",
        "Operation": "Create",
        "Campaign ID": campaign_name,
        " Ad Group ID": ag_name,
        "Ad Group Name": ag_name,
        "State": "enabled",
    }))

    # 4. Ad (1 por campaña — SBV o SBH según tipo)
    ad_row = {
        "Product": "Sponsored Brands",
        "Entity": ad_entity,
        "Operation": "Create",
        "Campaign ID": campaign_name,
        " Ad Group ID": ag_name,
        "Ad Name": creative_headline or "[HEADLINE]",
        "State": "enabled",
        "Landing Page URL": landing_page_url,
        "Landing Page Type": landing_page_type,
        "Brand Name": brand_name,
        "Creative Headline": creative_headline or "[HEADLINE]",
        "Creative ASINs": creative_asins_str,
    }
    if sb_type == "SBV":
        ad_row["Video Asset IDs"] = video_asset_id
    else:  # SBH
        ad_row["Brand Logo Asset ID"] = brand_logo_asset_id
        ad_row["Brand Logo URL (Informational only)"] = brand_logo_url
        ad_row["Brand Logo Crop"] = brand_logo_crop
    rows.append(_sb_row_factory(**ad_row))

    # 5. Keywords (1 fila por keyword)
    for kw in keywords:
        rows.append(_sb_row_factory(**{
            "Product": "Sponsored Brands",
            "Entity": "Keyword",
            "Operation": "Create",
            "Campaign ID": campaign_name,
            " Ad Group ID": ag_name,
            "State": "enabled",
            "Bid": float(bid),
            "Keyword Text": kw,
            "Match Type": "Exact",
        }))

    return rows


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
    st.info(
        f"💡 **Bid calculado automáticamente: \\${bid_calculado}** "
        f"(CVR {cvr}% × precio \\${precio} × target ACoS {target_acos}%)"
    )

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
