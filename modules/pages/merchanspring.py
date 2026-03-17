import streamlit as st
import pandas as pd

from modules.merchanspring.parser import _parse_merchanspring, _parse_merchanspring_pdf
from modules.merchanspring.excel_export import _build_ms_pdf_excel, _build_merchanspring_excel
from modules.merchanspring.style_helpers import _s_acos, _s_margin, _s_delta, _s_eff, _s_stock


def _show_df_if(data, key, caption=None, style_fn=None, style_cols=None):
    """Show a DataFrame from data[key] if non-empty. Returns True if shown."""
    df = data.get(key, pd.DataFrame())
    if isinstance(df, pd.DataFrame) and not df.empty:
        if caption:
            st.caption(caption)
        styled = df.style
        if style_fn and style_cols:
            present = [c for c in style_cols if c in df.columns]
            if present:
                styled = styled.map(style_fn, subset=present)
        st.dataframe(styled, use_container_width=True, hide_index=True)
        return True
    return False


def _show_dict_metrics(data, key, n_cols=4):
    """Show a dict as metric cards if any value is not '-'."""
    d = data.get(key, {})
    if not d or not any(v != "-" for v in d.values()):
        return False
    cols = st.columns(n_cols)
    for i, (k, v) in enumerate(d.items()):
        with cols[i % n_cols]:
            st.metric(label=k, value=v)
    return True


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
                ms_t1, ms_t2, ms_t3, ms_t4, ms_t5 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventory & Health", "📈 WoW Comparison", "🔎 Details"]
                )

                with ms_t1:
                    st.caption("Productos más vendidos en el período")
                    df = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No se encontraron datos de top sellers.")

                    # Parent products
                    if _show_df_if(ms_data, "parent_products_df", "Productos Parent (agrupados)"):
                        pass  # shown

                with ms_t2:
                    # Show real advertising data if available
                    adv_sum = ms_data.get("adv_summary", {})
                    has_adv = any(v != "-" for v in adv_sum.values()) if adv_sum else False

                    if has_adv:
                        st.caption("Resumen de Advertising")
                        adv_kpi_items = [(k, v) for k, v in adv_sum.items() if v != "-"]
                        adv_kpi_cols = st.columns(min(4, len(adv_kpi_items)))
                        for i, (k, v) in enumerate(adv_kpi_items[:8]):
                            with adv_kpi_cols[i % len(adv_kpi_cols)]:
                                st.metric(label=k, value=v)
                        st.divider()

                        _show_df_if(ms_data, "adv_by_type_df", "Por tipo de campaña")
                        _show_df_if(ms_data, "adv_df", "Productos publicitados")
                        _show_df_if(ms_data, "campaigns_df", "Campañas")
                        _show_df_if(ms_data, "top_product_ads_df", "Top Product Ads")
                        _show_df_if(ms_data, "top_keywords_df", "Top Keywords")
                    else:
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
                    if pnl_m_tab and any(v != "-" for v in pnl_m_tab.values()):
                        m_cols = st.columns(4)
                        for i, (k, v) in enumerate(pnl_m_tab.items()):
                            with m_cols[i % 4]:
                                st.metric(label=k, value=v)
                    _show_df_if(ms_data, "pnl_df", "P&L — Estado de Resultados")
                    _show_df_if(ms_data, "prod_profit_df", "Rentabilidad por producto")
                    st.divider()

                    # Health
                    health_tab = ms_data.get("health_data", {})
                    if health_tab and any(v != "-" for v in health_tab.values()):
                        st.caption("Salud del Catálogo")
                        h_cols = st.columns(3)
                        for i, (k, v) in enumerate(health_tab.items()):
                            with h_cols[i % 3]:
                                st.metric(label=k, value=v)
                    st.divider()

                    # Cancellations by product
                    _show_df_if(ms_data, "cancellations_by_product_df", "Cancelaciones y Devoluciones por Producto")

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

                with ms_t5:
                    st.caption("Secciones adicionales detectadas en el PDF")

                    # Traffic & Conversion Summary
                    ts = ms_data.get("traffic_summary", {})
                    _ts_vals = {k: v for k, v in ts.items() if not k.endswith(" delta") and v != "-"}
                    if _ts_vals:
                        st.subheader("Traffic & Conversion Summary")
                        tc_cols = st.columns(min(5, len(_ts_vals)))
                        for i, (k, v) in enumerate(_ts_vals.items()):
                            delta = ts.get(k + " delta", "-")
                            with tc_cols[i % len(tc_cols)]:
                                st.metric(label=k, value=v, delta=delta if delta != "-" else None)
                        st.divider()

                    # Traffic by Product - Parent / Child
                    if _show_df_if(ms_data, "tc_parent_df", None):
                        st.caption("Traffic by Product - Parent")
                        st.divider()
                    if _show_df_if(ms_data, "tc_child_df", None):
                        st.caption("Traffic by Product - Child")
                        st.divider()

                    # Cancellations Summary
                    cr = ms_data.get("cancellations_data", {})
                    if cr and any(v != "-" for v in cr.values()):
                        st.subheader("Cancellations & Refunds Summary")
                        cr_cols = st.columns(3)
                        for i, (k, v) in enumerate(cr.items()):
                            with cr_cols[i % 3]:
                                st.metric(label=k, value=v)
                        st.divider()

                    # Sales breakdowns
                    for label, key in [("Sales by Category", "sales_by_category_df"),
                                       ("Sales by Country", "sales_by_country_df"),
                                       ("Sales by Brand", "sales_by_brand_df")]:
                        if _show_df_if(ms_data, key, label):
                            st.divider()

                    # Top Products by BSR
                    if _show_df_if(ms_data, "top_bsr_df", "Top Products by BSR"):
                        st.divider()

                    # Buybox Winning / Losing
                    if _show_df_if(ms_data, "buybox_winning_df", "Buybox - Winning"):
                        st.divider()
                    if _show_df_if(ms_data, "buybox_losing_df", "Buybox - Losing"):
                        st.divider()

                    # Buy Box Summary
                    bb = ms_data.get("buybox_snapshot", {})
                    if bb and any(v != "-" for v in bb.values()):
                        st.subheader("Buy Box Summary")
                        bb_cols = st.columns(4)
                        for i, (k, v) in enumerate(bb.items()):
                            with bb_cols[i % 4]:
                                st.metric(label=k, value=v)
                        st.divider()

                    # Shipping Performance
                    ship = ms_data.get("shipping_data", {})
                    if ship and any(v != "-" for v in ship.values()):
                        st.subheader("Shipping Performance")
                        sp_cols = st.columns(3)
                        for i, (k, v) in enumerate(ship.items()):
                            with sp_cols[i % 3]:
                                st.metric(label=k, value=v)
                        st.divider()

                    # Review Status
                    rev = ms_data.get("review_data", {})
                    if rev and any(v != "-" for v in rev.values()):
                        st.subheader("Review Status")
                        rv_cols = st.columns(4)
                        for i, (k, v) in enumerate(rev.items()):
                            with rv_cols[i % 4]:
                                st.metric(label=k, value=v)

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
