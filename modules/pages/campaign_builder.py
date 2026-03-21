import io
import re
from datetime import datetime

import streamlit as st
import pandas as pd


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


def render():
    st.header("🚀 Campaign Builder")
    st.caption("Genera el bulk listo para subir a Amazon desde el Plan de Acción. Naming convention Capybaras automático.")
    st.divider()

    # ── PASO 1 — Upload Plan de Acción ────────────────────────────────────────
    st.markdown("### Paso 1 — Subí el Plan de Acción bulk")
    st.caption("El archivo generado en Análisis Cruzado → Plan de Acción → Descargar bulk.")

    file_plan = st.file_uploader(
        "Plan de Acción bulk (.xlsx)",
        type=["xlsx"],
        key="cb_plan"
    )

    if not file_plan:
        st.info("📂 Generalo en: Análisis Cruzado → tab Plan de Acción → Descargar Plan de Acción bulk")
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
    fc1.metric("✅ LANZAR AHORA", n_lanzar)
    fc2.metric("⚠️ PROBAR", n_probar)

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
    cols_cl = st.columns(len(cluster_counts))
    for i, (cluster, count) in enumerate(cluster_counts.items()):
        cols_cl[i].metric(cluster, count)

    st.markdown("---")

    # ── PASO 4 — Generar bulk ─────────────────────────────────────────────────
    # Agrupar en campañas de MAX 5 keywords por cluster
    MAX_KW_POR_CAMPANA = 5
    start_date = datetime.now().strftime("%m/%d/%Y")

    rows = []
    for cluster in df_kw["Cluster"].unique():
        df_cluster = df_kw[df_kw["Cluster"] == cluster].copy()
        keywords = df_cluster["Keyword"].tolist()

        # Dividir en grupos de MAX 5
        grupos = [keywords[i:i+MAX_KW_POR_CAMPANA]
                  for i in range(0, len(keywords), MAX_KW_POR_CAMPANA)]

        for num, grupo in enumerate(grupos, start=1):
            camp_name = _generar_nombre_campana(marca, asin, cluster, "exact", num)
            ag_name   = _generar_nombre_adgroup(cluster, num)

            # Fila Campaign
            rows.append({
                "Product":         "Sponsored Products",
                "Entity":          "Campaign",
                "Operation":       "create",
                "Campaign ID":     "",
                "Ad Group ID":     "",
                "Portfolio ID":    portfolio_id,
                "Ad ID":           "",
                "Keyword ID":      "",
                "Product Targeting ID": "",
                "Campaign Name":   camp_name,
                "Ad Group Name":   "",
                "Start Date":      start_date,
                "End Date":        "",
                "Targeting Type":  "MANUAL",
                "State":           "enabled",
                "Daily Budget":    budget,
                "SKU":             "",
                "Ad Group Default Bid": "",
                "Bid":             "",
                "Keyword Text":    "",
                "Match Type":      "",
                "Bidding Strategy": "Dynamic bidding (down only)",
            })

            # Fila Ad Group
            rows.append({
                "Product":         "Sponsored Products",
                "Entity":          "Ad Group",
                "Operation":       "create",
                "Campaign ID":     "",
                "Ad Group ID":     "",
                "Portfolio ID":    "",
                "Ad ID":           "",
                "Keyword ID":      "",
                "Product Targeting ID": "",
                "Campaign Name":   camp_name,
                "Ad Group Name":   ag_name,
                "Start Date":      "",
                "End Date":        "",
                "Targeting Type":  "",
                "State":           "enabled",
                "Daily Budget":    "",
                "SKU":             "",
                "Ad Group Default Bid": bid_calculado,
                "Bid":             "",
                "Keyword Text":    "",
                "Match Type":      "",
                "Bidding Strategy": "",
            })

            # Fila Product Ad (SKU)
            if sku:
                rows.append({
                    "Product":         "Sponsored Products",
                    "Entity":          "Product Ad",
                    "Operation":       "create",
                    "Campaign ID":     "",
                    "Ad Group ID":     "",
                    "Portfolio ID":    "",
                    "Ad ID":           "",
                    "Keyword ID":      "",
                    "Product Targeting ID": "",
                    "Campaign Name":   camp_name,
                    "Ad Group Name":   ag_name,
                    "Start Date":      "",
                    "End Date":        "",
                    "Targeting Type":  "",
                    "State":           "enabled",
                    "Daily Budget":    "",
                    "SKU":             sku,
                    "Ad Group Default Bid": "",
                    "Bid":             "",
                    "Keyword Text":    "",
                    "Match Type":      "",
                    "Bidding Strategy": "",
                })

            # Filas Keywords
            for kw in grupo:
                rows.append({
                    "Product":         "Sponsored Products",
                    "Entity":          "Keyword",
                    "Operation":       "create",
                    "Campaign ID":     "",
                    "Ad Group ID":     "",
                    "Portfolio ID":    "",
                    "Ad ID":           "",
                    "Keyword ID":      "",
                    "Product Targeting ID": "",
                    "Campaign Name":   camp_name,
                    "Ad Group Name":   ag_name,
                    "Start Date":      "",
                    "End Date":        "",
                    "Targeting Type":  "",
                    "State":           "enabled",
                    "Daily Budget":    "",
                    "SKU":             "",
                    "Ad Group Default Bid": "",
                    "Bid":             bid_calculado,
                    "Keyword Text":    kw,
                    "Match Type":      "exact",
                    "Bidding Strategy": "",
                })

            # Separador vacío entre campañas
            rows.append({col: "" for col in rows[0].keys()})

    df_bulk = pd.DataFrame(rows)

    # ── Preview tabla ─────────────────────────────────────────────────────────
    n_campanas = df_bulk[df_bulk["Entity"] == "Campaign"].shape[0]
    n_keywords = df_bulk[df_bulk["Entity"] == "Keyword"].shape[0]

    b1, b2, b3 = st.columns(3)
    b1.metric("Campañas a crear", n_campanas)
    b2.metric("Keywords totales", n_keywords)
    b3.metric("Bid por keyword", f"${bid_calculado}")

    st.markdown("#### Preview del bulk")
    st.caption("Revisá antes de descargar. Campaign Name y Ad Group Name ya están completos.")
    df_preview = df_bulk[df_bulk["Entity"].isin(["Campaign", "Keyword"])][
        ["Entity", "Campaign Name", "Ad Group Name", "Keyword Text", "Match Type", "Bid", "Daily Budget"]
    ].dropna(how="all").reset_index(drop=True)
    st.dataframe(df_preview, use_container_width=True, height=400)

    st.markdown("---")

    # ── Export en formato exacto Amazon ──────────────────────────────────────
    st.markdown("#### 📦 Export bulk — formato exacto Amazon")
    st.caption("Listo para subir directo a Campaign Manager. Columnas en el orden exacto que Amazon requiere.")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_bulk.to_excel(writer, sheet_name="Sponsored Products Campaigns", index=False)

    st.download_button(
        label=f"⬇️ Descargar bulk Amazon ({n_campanas} campañas, {n_keywords} keywords)",
        data=buf.getvalue(),
        file_name=f"campaign_bulk_{marca}_{asin}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_campaign_bulk"
    )

    st.warning("⚠️ Revisá el Campaign Name y Ad Group Name antes de subir. Las operaciones UPDATE (pausar existentes) requieren Campaign ID numérico — hacelas manualmente en Campaign Manager.")
