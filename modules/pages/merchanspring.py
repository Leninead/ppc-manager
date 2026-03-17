import streamlit as st
import pandas as pd

from modules.merchanspring.parser import _parse_merchanspring, _parse_merchanspring_pdf
from modules.merchanspring.excel_export import _build_ms_pdf_excel, _build_merchanspring_excel
from modules.merchanspring.style_helpers import _s_acos, _s_margin, _s_delta, _s_eff, _s_stock


def render():
    st.header("🛡️ Reportes MerchanSpring")
    st.caption("Subí el reporte semanal de MerchanSpring (.xlsx o .pdf) para ver el dashboard y exportar el informe profesional.")
    st.divider()

    ms_client = st.text_input(
        "Nombre del cliente (aparece en el Excel)",
        placeholder="Ej: Love To Dream",
        key="ms_client",
    )
    ms_file = st.file_uploader(
        "Arrastrá el archivo MerchanSpring (.xlsx o .pdf)",
        type=["xlsx", "pdf"],
        key="ms_upload",
    )

    if ms_file:
        try:
            is_pdf = ms_file.name.lower().endswith(".pdf")

            if is_pdf:
                ms_data = _parse_merchanspring_pdf(ms_file)
            else:
                ms_data = _parse_merchanspring(ms_file)

            st.markdown(f"### {ms_data.get('title', '')}")
            st.caption(ms_data.get("period", ""))

            # ── KPI cards ────────────────────────────────────────────────
            kpis = ms_data.get("kpis", [])
            if kpis:
                _ms_chunk_size = 4
                for _ms_start in range(0, len(kpis), _ms_chunk_size):
                    _ms_chunk = kpis[_ms_start:_ms_start + _ms_chunk_size]
                    kpi_cols = st.columns(len(_ms_chunk))
                    for ki, kpi in enumerate(_ms_chunk):
                        delta_str = kpi["delta"].replace("vs prior: ", "")
                        with kpi_cols[ki]:
                            st.metric(label=kpi["name"], value=kpi["val"], delta=delta_str)

            st.divider()

            if is_pdf:
                # ── Section detection log ──────────────────────────────────
                _slog = ms_data.get("sections_log", [])
                if _slog:
                    _all_ok  = all(ic == "✅" for ic, _, _ in _slog)
                    _has_err = any(ic == "❌" for ic, _, _ in _slog)
                    _exp_icon = "✅" if _all_ok else ("❌" if _has_err else "⚠️")
                    with st.expander(f"{_exp_icon} Secciones detectadas en el PDF ({len(_slog)} analizadas)", expanded=_has_err):
                        for _ic, _sec, _det in _slog:
                            st.markdown(f"{_ic} &nbsp; **{_sec}** — {_det}")

                # ── PDF dashboard ─────────────────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventory & Health", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Productos más vendidos en el período")
                    df = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No se encontraron datos de top sellers.")

                with ms_t2:
                    st.warning("⚠️ Advertising no conectado en MerchantSpring")
                    st.info(
                        "Para ver datos de advertising, conectá tu cuenta de Amazon Ads en MerchantSpring:\n\n"
                        "**MerchantSpring → Settings → Integrations → Amazon Advertising**\n\n"
                        "Una vez conectado, los datos aparecerán automáticamente en el próximo reporte."
                    )

                with ms_t3:
                    # Inventario
                    df = ms_data.get("inv_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.caption("Inventario de productos")
                        style = df.style
                        if "Stock Status" in df.columns:
                            style = style.map(_s_stock, subset=["Stock Status"])
                        st.dataframe(style, use_container_width=True, hide_index=True)
                    st.divider()
                    # P&L métricas
                    pnl_m_tab = ms_data.get("pnl_metrics", {})
                    if pnl_m_tab:
                        m_cols = st.columns(4)
                        for i, (k, v) in enumerate(pnl_m_tab.items()):
                            with m_cols[i]:
                                st.metric(label=k, value=v)
                    pnl_df_tab = ms_data.get("pnl_df", pd.DataFrame())
                    if not pnl_df_tab.empty:
                        st.caption("P&L — Estado de Resultados")
                        st.dataframe(pnl_df_tab, use_container_width=True, hide_index=True)
                    pp_df_tab = ms_data.get("prod_profit_df", pd.DataFrame())
                    if not pp_df_tab.empty:
                        st.caption("Rentabilidad por producto")
                        st.dataframe(pp_df_tab, use_container_width=True, hide_index=True)
                    st.divider()
                    # Health
                    health_tab = ms_data.get("health_data", {})
                    if health_tab:
                        st.caption("Salud del Catálogo")
                        h_cols = st.columns(3)
                        for i, (k, v) in enumerate(health_tab.items()):
                            with h_cols[i % 3]:
                                st.metric(label=k, value=v)

                with ms_t4:
                    st.caption("Comparación semana a semana — Sales y Units disponibles desde PDF. TACoS / Ad Sales / Ad Spend requieren conexión de Amazon Ads.")
                    sum_wow = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not sum_wow.empty:
                        def _pw(tw, ws):
                            try:
                                p = float(str(ws).replace("%","").replace("+","").strip())
                                d = 1 + p / 100
                                if d == 0: return "-"
                                v = float(str(tw).replace("$","").replace(",","").strip())
                                return round(v / d, 2) if v else "-"
                            except: return "-"
                        wow_rows = []
                        for _, r in sum_wow.iterrows():
                            wow_rows.append({
                                "Product":            r.get("Product",""),
                                "ASIN":               r.get("ASIN",""),
                                "Sales (This Week)":  r.get("Total Sales ($)",""),
                                "Sales (Prior Week)": _pw(r.get("Total Sales ($)",0), r.get("Sales WoW (%)","−")),
                                "Sales Δ %":          r.get("Sales WoW (%)","-"),
                                "Units (This Week)":  r.get("Units Sold",""),
                                "Units (Prior Week)": _pw(r.get("Units Sold",0), r.get("Units WoW (%)","−")),
                                "Units Δ %":          r.get("Units WoW (%)","-"),
                                "Sessions":           "-",
                                "CVR":                "-",
                                "TACoS":              "—",
                                "Ad Sales":           "—",
                                "Organic Sales":      r.get("Total Sales ($)",""),
                                "Ad Spend":           "—",
                                "Profit Δ %":         "-",
                            })
                        wow_display = pd.DataFrame(wow_rows)
                        delta_cols_wow = ["Sales Δ %", "Units Δ %"]
                        style_wow = wow_display.style
                        for dc in delta_cols_wow:
                            if dc in wow_display.columns:
                                style_wow = style_wow.map(_s_delta, subset=[dc])
                        st.dataframe(style_wow, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay datos de WoW disponibles.")

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_ms_pdf_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export_pdf",
                    use_container_width=True,
                )

            else:
                # ── Excel dashboard (original) ────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventario & Salud", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Tabla de productos — resumen de la semana analizada")
                    df = ms_data["summary_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "TACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["TACoS (%)"])
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t2:
                    st.caption("Análisis de publicidad por producto")
                    df = ms_data["adv_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "Ad Efficiency" in df.columns:
                        style = style.map(_s_eff, subset=["Ad Efficiency"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t3:
                    st.caption("Inventario y salud del producto")
                    df = ms_data["inv_df"].copy()
                    style = df.style
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    if "Stock Status" in df.columns:
                        style = style.map(_s_stock, subset=["Stock Status"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t4:
                    st.caption("Comparación semana a semana por producto")
                    df = ms_data["wow_df"].copy()
                    delta_cols = [c for c in df.columns if c.endswith("|Δ %")]
                    style = df.style
                    if delta_cols:
                        style = style.map(_s_delta, subset=delta_cols)
                    st.dataframe(style, use_container_width=True, hide_index=True)

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_merchanspring_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export",
                    use_container_width=True,
                )

        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            import traceback
            st.code(traceback.format_exc())
