import io
import streamlit as st
import pandas as pd


def _limpiar_num(val):
    """Limpia $, %, comas y convierte a float. Retorna 0.0 si falla."""
    try:
        return float(str(val).replace("$", "").replace("%", "").replace(",", "").strip())
    except Exception:
        return 0.0


def render():
    st.header("🧠 Bid Optimizer")
    st.caption("Bids sugeridos por ASIN calculados desde STR. CVR y precio de ads — más preciso que el Business Report.")
    st.divider()

    # ── Input global ──────────────────────────────────────────────────────
    target_acos = st.slider(
        "Target ACoS (%)",
        min_value=5, max_value=80, value=25, step=1,
        help="ACoS objetivo. Usado para calcular bid_base = CVR_ads × precio_ads × target_ACoS"
    )

    st.markdown("---")

    # ── Upload ────────────────────────────────────────────────────────────
    file_str = st.file_uploader(
        "Subí el Search Term Report (.xlsx o .csv)",
        type=["csv", "xlsx"],
        key="bid_opt_str"
    )

    file_inv = st.file_uploader(
        "Inventory Report (.txt o .csv) — opcional, para precio de lista exacto",
        type=["txt", "csv"],
        key="bid_opt_inv",
        help="Reports → Fulfillment → Inventory → All Listings Report. Si no lo subís, se usa el precio promedio del STR."
    )

    if not file_str:
        st.info("📂 Descargalo desde Amazon Ads → Reports → Search Term Report. Usamos CVR y precio real de ads por ASIN.")
        return

    # ── Parsear archivo ───────────────────────────────────────────────────
    df = pd.read_csv(file_str) if file_str.name.endswith(".csv") else pd.read_excel(file_str)
    st.success(f"✅ {len(df)} filas cargadas")

    # ── Detectar columnas ─────────────────────────────────────────────────
    col_asin    = next((c for c in df.columns if "advertised asin" in c.lower()), None)
    col_campaign = next((c for c in df.columns if "campaign name" in c.lower()), None)

    # Si no hay Advertised ASIN, extraerlo del Campaign Name
    if col_asin is None and col_campaign is not None:
        import re as _re
        df["_extracted_asin"] = df[col_campaign].str.extract(r'(B0[A-Z0-9]{8})', expand=False)
        if df["_extracted_asin"].notna().any():
            col_asin = "_extracted_asin"
            st.info("ℹ️ Columna 'Advertised ASIN' no encontrada — ASIN extraído automáticamente del Campaign Name.")

    col_clicks  = next((c for c in df.columns if "clicks" in c.lower()), None)
    col_orders  = next((c for c in df.columns if "orders" in c.lower()), None)
    col_sales   = next((c for c in df.columns if "sales" in c.lower()
                        and "other" not in c.lower() and "advertised" not in c.lower()), None)
    col_spend   = next((c for c in df.columns if "spend" in c.lower()), None)

    missing = [n for n, c in [
        ("Advertised ASIN", col_asin),
        ("Clicks", col_clicks),
        ("Orders", col_orders),
        ("Sales", col_sales),
        ("Spend", col_spend),
    ] if c is None]

    if missing:
        st.error(f"❌ Columnas no encontradas: {', '.join(missing)}. Verificá que sea el Search Term Report de Amazon Ads.")
        return

    # ── Normalizar numéricos ──────────────────────────────────────────────
    for c in [col_clicks, col_orders, col_sales, col_spend]:
        df[c] = df[c].apply(_limpiar_num)

    # ── Agrupar por ASIN ──────────────────────────────────────────────────
    df_asin = (
        df.groupby(col_asin, as_index=False)
        .agg({
            col_clicks: "sum",
            col_orders: "sum",
            col_sales:  "sum",
            col_spend:  "sum",
        })
    )

    # ── Cruzar con Inventory Report si está disponible ────────────────
    precio_map = {}
    if file_inv:
        try:
            df_inv = pd.read_csv(file_inv, sep="\t")
            # normalizar nombre de columnas
            df_inv.columns = [c.strip().lower() for c in df_inv.columns]
            if "asin" in df_inv.columns and "price" in df_inv.columns:
                df_inv["price"] = df_inv["price"].apply(_limpiar_num)
                precio_map = dict(zip(df_inv["asin"], df_inv["price"]))
                st.success(f"✅ Inventory Report cargado — {len(precio_map)} precios de lista encontrados")
        except Exception as e:
            st.warning(f"⚠️ No se pudo leer el Inventory Report: {e}")

    # ── Calcular métricas por ASIN ────────────────────────────────────────
    df_asin["_cvr"]    = df_asin.apply(
        lambda r: (r[col_orders] / r[col_clicks] * 100) if r[col_clicks] > 0 else 0.0, axis=1
    )

    def _get_precio(row):
        asin = str(row[col_asin]).strip()
        if precio_map and asin in precio_map and precio_map[asin] > 0:
            return precio_map[asin]
        return (row[col_sales] / row[col_orders]) if row[col_orders] > 0 else 0.0

    df_asin["_precio"] = df_asin.apply(_get_precio, axis=1)
    df_asin["_acos"]   = df_asin.apply(
        lambda r: (r[col_spend] / r[col_sales] * 100) if r[col_sales] > 0 else 0.0, axis=1
    )
    df_asin["_bid_base"] = df_asin.apply(
        lambda r: round((r["_cvr"] / 100) * r["_precio"] * (target_acos / 100), 2)
        if r[col_orders] > 0 else 0.0,
        axis=1
    )

    # ── Semáforo ──────────────────────────────────────────────────────────
    def _estado(row):
        if row[col_clicks] == 0:
            return "⚫ SIN DATA"
        if row["_cvr"] > 15 and row[col_orders] > 5:
            return "🟢 ESCALAR"
        if 8 <= row["_cvr"] <= 15:
            return "🟡 OK"
        return "🔴 REVISAR"

    df_asin["Estado"] = df_asin.apply(_estado, axis=1)

    # ── Session state para ajuste manual ─────────────────────────────────
    key_ajuste = "bid_opt_ajustes"
    if key_ajuste not in st.session_state:
        st.session_state[key_ajuste] = {}

    # ── KPIs resumen ──────────────────────────────────────────────────────
    total_asins  = len(df_asin)
    bid_prom     = df_asin[df_asin["_bid_base"] > 0]["_bid_base"].mean()
    n_revisar    = (df_asin["Estado"] == "🔴 REVISAR").sum()
    n_escalar    = (df_asin["Estado"] == "🟢 ESCALAR").sum()
    acos_cuenta  = (df_asin[col_spend].sum() / df_asin[col_sales].sum() * 100) if df_asin[col_sales].sum() > 0 else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("ASINs analizados", total_asins)
    k2.metric("Bid promedio sugerido", f"${bid_prom:.2f}" if bid_prom > 0 else "—")
    k3.metric("ACoS cuenta", f"{acos_cuenta:.1f}%")
    k4.metric("🟢 Escalar", n_escalar)
    k5.metric("🔴 Revisar", n_revisar)

    st.markdown("---")

    # ── Tabla editable ────────────────────────────────────────────────────
    st.markdown("#### Bids sugeridos por ASIN")
    precio_fuente = "Inventory Report (precio de lista)" if precio_map else "STR (precio promedio de venta)"
    st.caption(f"CVR de ads reales del STR. Precio desde: {precio_fuente}. Ajustá el % por ASIN si querés afinar el bid.")

    df_tabla = pd.DataFrame({
        "Estado":          df_asin["Estado"].values,
        "ASIN":            df_asin[col_asin].values,
        "Clicks":          df_asin[col_clicks].astype(int).values,
        "Orders":          df_asin[col_orders].astype(int).values,
        "CVR % (ads)":     df_asin["_cvr"].round(2).values,
        "Precio prom ($)": df_asin["_precio"].round(2).values,
        "ACoS actual (%)": df_asin["_acos"].round(1).values,
        "Bid Base ($)":    df_asin["_bid_base"].values,
        "Ajuste %":        [st.session_state[key_ajuste].get(str(a), 0) for a in df_asin[col_asin].values],
    })

    df_editada = st.data_editor(
        df_tabla,
        column_config={
            "Ajuste %": st.column_config.NumberColumn(
                "Ajuste %",
                help="Ej: +20 sube el bid 20%, -30 lo baja 30%.",
                min_value=-50,
                max_value=100,
                step=5,
                format="%d%%",
            ),
            "Estado": st.column_config.TextColumn("Estado", width="small"),
            "ASIN":   st.column_config.TextColumn("ASIN",   width="medium"),
        },
        disabled=["Estado", "ASIN", "Clicks", "Orders", "CVR % (ads)",
                  "Precio prom ($)", "ACoS actual (%)", "Bid Base ($)"],
        use_container_width=True,
        key="bid_editor"
    )

    # Guardar ajustes en session_state
    for _, row in df_editada.iterrows():
        st.session_state[key_ajuste][str(row["ASIN"])] = row["Ajuste %"]

    # Calcular Bid Final
    df_editada["Bid Final ($)"] = df_editada.apply(
        lambda r: round(r["Bid Base ($)"] * (1 + r["Ajuste %"] / 100), 2), axis=1
    )

    # ── Resultado con Bid Final ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Resultado con Bid Final")
    st.dataframe(df_editada, use_container_width=True)

    # ── Export ────────────────────────────────────────────────────────────
    st.markdown("---")
    df_export = df_editada.copy()
    df_export["Target ACoS %"] = target_acos

    buf = io.BytesIO()
    df_export.to_excel(buf, index=False)
    st.download_button(
        label=f"📥 Exportar bulk bids ({len(df_export)} ASINs)",
        data=buf.getvalue(),
        file_name="bid_optimizer.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_bid_opt"
    )
