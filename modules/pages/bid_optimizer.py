import io

import streamlit as st
import pandas as pd


def _limpiar_num(val):
    """Elimina $, %, comas y convierte a float. Retorna 0.0 si falla."""
    try:
        return float(str(val).replace("$", "").replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def render():
    st.header("🧠 Bid Optimizer")
    st.caption("Calcula bids sugeridos por ASIN usando CVR, precio promedio y target ACoS.")
    st.divider()

    # ── Target ACoS (parte superior) ──────────────────────────────────
    target_acos = st.slider(
        "Target ACoS (%)",
        min_value=5, max_value=80, value=25, step=1,
        key="bid_opt_target_acos"
    )

    st.markdown("---")

    # ── Upload BR by Child ASIN ───────────────────────────────────────
    file_br = st.file_uploader(
        "Sube el Business Report by Child ASIN (.xlsx o .csv)",
        type=["xlsx", "csv"],
        key="bid_opt_br"
    )

    if not file_br:
        return

    df_raw = pd.read_excel(file_br) if file_br.name.endswith(".xlsx") else pd.read_csv(file_br)

    # ── Validar columnas requeridas ───────────────────────────────────
    required = ["(Child) ASIN", "Units Ordered", "Ordered Product Sales"]
    missing = [c for c in required if c not in df_raw.columns]
    if missing:
        st.error(f"Columnas faltantes: {', '.join(missing)}")
        return

    # ── Detectar columna CVR (dos variantes de Amazon) ────────────────
    cvr_col = None
    for candidate in ["Unit Session Percentage", "Order Item Session Percentage"]:
        if candidate in df_raw.columns:
            cvr_col = candidate
            break

    if not cvr_col:
        st.error("No se encontró columna de CVR (Unit Session Percentage o Order Item Session Percentage).")
        return

    sessions_col = None
    for candidate in ["Sessions - Total", "Sessions"]:
        if candidate in df_raw.columns:
            sessions_col = candidate
            break

    # ── Título (opcional) ─────────────────────────────────────────────
    title_col = None
    for candidate in ["Title", "(Child) ASIN Title", "Product Name"]:
        if candidate in df_raw.columns:
            title_col = candidate
            break

    # ── Construir dataframe de trabajo ────────────────────────────────
    df = df_raw.copy()
    df["_units"]    = pd.to_numeric(df["Units Ordered"].apply(_limpiar_num), errors="coerce").fillna(0).astype(int)
    df["_sales"]    = df["Ordered Product Sales"].apply(_limpiar_num)
    df["_cvr"]      = df[cvr_col].apply(_limpiar_num)
    df["_sessions"] = pd.to_numeric(df[sessions_col].apply(_limpiar_num), errors="coerce").fillna(0).astype(int) if sessions_col else 0

    # Precio promedio
    df["_precio"] = df.apply(
        lambda r: r["_sales"] / r["_units"] if r["_units"] > 0 else 0.0, axis=1
    )

    # Bid base
    df["_bid_base"] = df.apply(
        lambda r: (r["_cvr"] / 100) * r["_precio"] * (target_acos / 100) if r["_units"] > 0 else 0.0,
        axis=1
    )

    # Estado semáforo
    def _estado(row):
        if sessions_col and row["_sessions"] == 0:
            return "⚫ SIN DATA"
        if row["_units"] == 0:
            return "🔴 REVISAR"
        if row["_cvr"] < 8:
            return "🔴 REVISAR"
        if row["_cvr"] > 15 and row["_units"] > 5:
            return "🟢 ESCALAR"
        return "🟡 OK"

    df["Estado"] = df.apply(_estado, axis=1)

    # ── Preparar tabla para data_editor ───────────────────────────────
    titulo = df[title_col].astype(str).str[:40] if title_col else ""

    df_editor = pd.DataFrame({
        "Estado":           df["Estado"].values,
        "Child ASIN":       df["(Child) ASIN"].values,
        "Título":           titulo.values if title_col else "",
        "CVR %":            df["_cvr"].round(2).values,
        "Precio Promedio":  df["_precio"].round(2).values,
        "Bid Base ($)":     df["_bid_base"].round(2).values,
        "Ajuste %":         0,
    })

    # Filtrar filas con ASIN válido
    df_editor = df_editor[df_editor["Child ASIN"].astype(str).str.strip() != ""].reset_index(drop=True)

    # ── KPIs resumen ──────────────────────────────────────────────────
    total_asins = len(df_editor)
    bid_promedio = df_editor["Bid Base ($)"].mean() if total_asins > 0 else 0
    asins_revisar = (df_editor["Estado"] == "🔴 REVISAR").sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("Total ASINs analizados", total_asins)
    k2.metric("Bid promedio sugerido", f"${bid_promedio:.2f}")
    k3.metric("ASINs en REVISAR", asins_revisar)

    st.markdown("---")

    # ── Tabla editable ────────────────────────────────────────────────
    st.markdown("#### Tabla de bids por ASIN")
    st.caption("Editá la columna **Ajuste %** para modificar el bid final por ASIN. Rango: -50% a +100%.")

    edited = st.data_editor(
        df_editor,
        column_config={
            "Estado":          st.column_config.TextColumn("Estado", disabled=True),
            "Child ASIN":      st.column_config.TextColumn("Child ASIN", disabled=True),
            "Título":          st.column_config.TextColumn("Título", disabled=True, width="large"),
            "CVR %":           st.column_config.NumberColumn("CVR %", format="%.2f", disabled=True),
            "Precio Promedio": st.column_config.NumberColumn("Precio Promedio", format="$%.2f", disabled=True),
            "Bid Base ($)":    st.column_config.NumberColumn("Bid Base ($)", format="$%.2f", disabled=True),
            "Ajuste %":        st.column_config.NumberColumn("Ajuste %", min_value=-50, max_value=100, step=5),
        },
        use_container_width=True,
        num_rows="fixed",
        key="bid_opt_editor",
        height=500,
    )

    # ── Recalcular Bid Final ──────────────────────────────────────────
    edited["Bid Final ($)"] = (
        edited["Bid Base ($)"] * (1 + edited["Ajuste %"] / 100)
    ).round(2)

    # ── Mostrar tabla con bid final ───────────────────────────────────
    st.markdown("#### Resultado con Bid Final")
    st.dataframe(edited, use_container_width=True, height=400)

    # ── Export Excel ──────────────────────────────────────────────────
    st.markdown("---")
    df_export = edited.copy()
    df_export.insert(4, "Target ACoS", f"{target_acos}%")
    df_export = df_export.rename(columns={"Bid Base ($)": "Bid Sugerido ($)"})

    buf = io.BytesIO()
    df_export.to_excel(buf, index=False)
    st.download_button(
        label=f"📥 Exportar bulk Excel ({len(df_export)} ASINs)",
        data=buf.getvalue(),
        file_name="bid_optimizer_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_bid_opt"
    )
