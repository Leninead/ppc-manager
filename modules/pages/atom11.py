import os

import streamlit as st
import pandas as pd

from core.i18n import _I18N
from core.constants import _BR_OPTIONAL_COLS
from core.helpers import _color_pct
from core.business_report import _BIZ_DIR, _parse_business_report_map
from modules.atom11.parser import (_parse_atom11, _detect_atom11_type, _extract_period_df,
                                   _summarize_daterange, _split_two_weeks)
from modules.atom11.analysis import _kpis, _generate_summary
from modules.atom11.parent_evolution import _build_parent_evolution, _generate_parent_evo_summary
from modules.atom11.excel_export import _build_atom11_excel


def render():
    st.header("🔬 Reportes Atom 11")
    st.caption("Subí 1 archivo para el resumen del periodo, o 2 archivos para comparación automática WoW / MoM.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Analizar performance de campañas con el formato de Atom 11 (WoW, MoM, DateRange) y generar informe ejecutivo con branding.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Atom 11 → Reports → Export (.xlsx). 1 archivo para single period / 2 archivos para comparación cross-period.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Weekly Client Report (M14) para cruzar con BR y armar el reporte semanal al cliente.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Ingresá nombre del cliente y seleccioná idioma (ES/EN)\n"
            "2. Subí 1 archivo (single period) o 2 archivos (comparación)\n"
            "3. Revisá KPIs, top 3, diagnóstico y recomendaciones\n"
            "4. Descargá el Excel con 3-4 hojas (Informe Cliente + KPIs + Datos + Parent Evolution)"
        )

    _cfg_col1, _cfg_col2 = st.columns([3, 1])
    with _cfg_col1:
        client_name = st.text_input("Nombre del cliente (aparece en el Excel)", placeholder="Ej: Dermaglos Argentina", key="atom11_client")
    with _cfg_col2:
        _lang_opt = st.radio("Idioma del Excel", ["Español", "English"], horizontal=True, key="atom11_lang")
    lang_code = "en" if _lang_opt == "English" else "es"

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        file_a1 = st.file_uploader("Periodo 1 \u2014 anterior (o unico archivo)", type=["xlsx"], key="atom11_f1")
    with col_u2:
        file_a2 = st.file_uploader("Periodo 2 \u2014 actual (opcional, para comparacion)", type=["xlsx"], key="atom11_f2")

    if file_a1:
        try:
            df1, ec1, cm1, fmt1 = _parse_atom11(file_a1)
            tipo = _detect_atom11_type(ec1)
            metrics1 = list(dict.fromkeys(m for _, m, _ in cm1))
            periods1 = list(dict.fromkeys(p for _, _, p in cm1))

            # ── Two-file comparison ───────────────────────────────────────────
            if file_a2:
                df2, ec2, cm2, fmt2 = _parse_atom11(file_a2)
                tipo2 = _detect_atom11_type(ec2)
                metrics2 = list(dict.fromkeys(m for _, m, _ in cm2))
                periods2 = list(dict.fromkeys(p for _, _, p in cm2))

                if ec1[0].lower() != ec2[0].lower():
                    st.error(f"Los archivos son de tipos distintos ({tipo} vs {tipo2}). Subi dos archivos del mismo tipo.")
                else:
                    # Collapse each file to a single-period df
                    if fmt1 == "DateRange":
                        df1_s, per1 = _summarize_daterange(df1, ec1, cm1)
                    else:
                        per1 = periods1[-1] if fmt1 == "WoW" else periods1[0]
                        df1_s = _extract_period_df(df1, ec1, cm1, per1)

                    if fmt2 == "DateRange":
                        df2_s, per2 = _summarize_daterange(df2, ec2, cm2)
                    else:
                        per2 = periods2[-1] if fmt2 == "WoW" else periods2[0]
                        df2_s = _extract_period_df(df2, ec2, cm2, per2)

                    comp_lbl = "WoW" if "week" in per1.lower() or "week" in per2.lower() else "MoM"
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Comparacion {comp_lbl}:** {per1}  \u2192  {per2}")

                    merged = df1_s.merge(df2_s, on=ec1, how="outer",
                                         suffixes=(f" ({per1})", f" ({per2})"))
                    for c in merged.columns:
                        if c not in ec1:
                            merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)

                    display = merged[ec1].copy()
                    delta_cols = []
                    for metric in list(dict.fromkeys(metrics1 + metrics2)):
                        pc = f"{metric} ({per1})"; cc = f"{metric} ({per2})"
                        if pc in merged.columns and cc in merged.columns:
                            display[pc] = merged[pc]
                            display[cc] = merged[cc]
                            pct_v = ((merged[cc] - merged[pc]) / merged[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    # Derived ACoS & CPC
                    for suf in [per1, per2]:
                        sp_c = f"Spend ({suf})"; sl_c = f"Sales ({suf})"; cl_c = f"Clicks ({suf})"
                        if sp_c in display.columns and sl_c in display.columns:
                            display[f"ACoS ({suf})"] = (display[sp_c] / display[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in display.columns and cl_c in display.columns:
                            display[f"CPC ({suf})"] = (display[sp_c] / display[cl_c].replace(0, float("nan"))).round(2)

                    kc = _kpis(df2_s); kp = _kpis(df1_s)
                    per_c = per2; per_p = per1
                    df_curr = df2_s

            # ── Single file ───────────────────────────────────────────────────
            else:
                if fmt1 == "WoW":
                    prev_p = periods1[0]; curr_p = periods1[-1]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **WoW:** {prev_p}  \u2192  {curr_p}")
                    display = df1[ec1].copy()
                    delta_cols = []
                    for metric in metrics1:
                        pc = f"{metric}|{prev_p}"; cc = f"{metric}|{curr_p}"
                        if pc in df1.columns and cc in df1.columns:
                            display[f"{metric} ({prev_p})"] = df1[pc]
                            display[f"{metric} ({curr_p})"] = df1[cc]
                            pct_v = ((df1[cc] - df1[pc]) / df1[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    for period in [prev_p, curr_p]:
                        sp_c = f"Spend|{period}"; sl_c = f"Sales|{period}"; cl_c = f"Clicks|{period}"
                        if sp_c in df1.columns and sl_c in df1.columns:
                            display[f"ACoS ({period})"] = (df1[sp_c] / df1[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in df1.columns and cl_c in df1.columns:
                            display[f"CPC ({period})"] = (df1[sp_c] / df1[cl_c].replace(0, float("nan"))).round(2)
                    df_curr = _extract_period_df(df1, ec1, cm1, curr_p)
                    df_prev = _extract_period_df(df1, ec1, cm1, prev_p)
                    kc = _kpis(df_curr); kp = _kpis(df_prev)
                    per_c = curr_p; per_p = prev_p

                elif fmt1 == "MoM":
                    period = periods1[0]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **MoM:** {period}")
                    df_curr = _extract_period_df(df1, ec1, cm1, period)
                    display = df_curr.copy()
                    if "Spend" in display.columns and "Sales" in display.columns:
                        display["ACoS"] = (display["Spend"] / display["Sales"].replace(0, float("nan")) * 100).round(2)
                    if "Spend" in display.columns and "Clicks" in display.columns:
                        display["CPC"] = (display["Spend"] / display["Clicks"].replace(0, float("nan"))).round(2)
                    delta_cols = []
                    kc = _kpis(df_curr); kp = None
                    per_c = period; per_p = ""

                else:  # DateRange
                    two_weeks = _split_two_weeks(df1, ec1, cm1)
                    if two_weeks:
                        df_prev, df_curr, per_p, per_c = two_weeks
                        st.info(
                            f"**Tipo detectado:** {tipo}  \u00b7  "
                            f"**WoW auto-detectado (2 semanas):**  "
                            f"Sem 1: {per_p}  \u2192  Sem 2: {per_c}"
                        )
                        _sfx_prev = _I18N[lang_code]["col_prev_sfx"]
                        _sfx_curr = _I18N[lang_code]["col_curr_sfx"]
                        display    = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            if metric in df_prev.columns and metric in df_curr.columns:
                                display[f"{metric} {_sfx_prev}"] = df_prev[metric]
                                display[f"{metric} {_sfx_curr}"] = df_curr[metric]
                                pct_v = (
                                    (df_curr[metric] - df_prev[metric])
                                    / df_prev[metric].replace(0, float("nan")) * 100
                                ).round(1)
                                d_col = f"{metric} \u0394%"
                                display[d_col] = pct_v
                                delta_cols.append(d_col)
                        for suffix, df_s in [(_sfx_prev, df_prev), (_sfx_curr, df_curr)]:
                            if "Spend" in df_s.columns and "Sales" in df_s.columns:
                                display[f"ACoS {suffix}"] = (
                                    df_s["Spend"] / df_s["Sales"].replace(0, float("nan")) * 100
                                ).round(2)
                            if "Spend" in df_s.columns and "Clicks" in df_s.columns:
                                display[f"CPC {suffix}"] = (
                                    df_s["Spend"] / df_s["Clicks"].replace(0, float("nan"))
                                ).round(2)
                        kc = _kpis(df_curr)
                        kp = _kpis(df_prev)
                    else:
                        df_curr, period_lbl = _summarize_daterange(df1, ec1, cm1)
                        st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Date Range:** {period_lbl}")
                        dates = periods1
                        display = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            for date in dates:
                                col = f"{metric}|{date}"
                                if col in df1.columns:
                                    display[f"{metric} {date}"] = df1[col]
                            date_cols = [f"{metric}|{d}" for d in dates if f"{metric}|{d}" in df1.columns]
                            if date_cols:
                                display[f"{metric} Total"] = df1[date_cols].sum(axis=1)
                            if len(dates) >= 2:
                                fc = f"{metric}|{dates[0]}"; lc = f"{metric}|{dates[-1]}"
                                if fc in df1.columns and lc in df1.columns:
                                    d_col = f"{metric} \u0394%"
                                    display[d_col] = ((df1[lc] - df1[fc]) / df1[fc].replace(0, float("nan")) * 100).round(1)
                                    delta_cols.append(d_col)
                        kc = _kpis(df_curr); kp = None
                        per_c = period_lbl; per_p = ""

            # ── KPI cards ─────────────────────────────────────────────────────
            st.markdown("---")
            kpi_defs_display = [
                ("Impressions", "{:,.0f}",  False),
                ("Clicks",      "{:,.0f}",  False),
                ("Spend",       "${:,.2f}", False),
                ("Sales",       "${:,.2f}", False),
                ("ACoS",        "{:.1f}%",  True),
                ("ROAS",        "{:.2f}x",  False),
                ("CTR",         "{:.2f}%",  False),
                ("CVR",         "{:.2f}%",  False),
            ]
            _kpi_chunk_size = 4
            for _kpi_start in range(0, len(kpi_defs_display), _kpi_chunk_size):
                _kpi_chunk = kpi_defs_display[_kpi_start:_kpi_start + _kpi_chunk_size]
                kpi_row = st.columns(len(_kpi_chunk))
                for i, (label, fmt_str, lower_better) in enumerate(_kpi_chunk):
                    cv = kc.get(label, 0) or 0
                    val_str = fmt_str.format(cv)
                    if kp is not None:
                        pv = kp.get(label, 0) or 0
                        if pv != 0:
                            d = (cv - pv) / pv * 100
                            kpi_row[i].metric(label, val_str, delta=f"{d:+.1f}%",
                                              delta_color="inverse" if lower_better else "normal")
                        else:
                            kpi_row[i].metric(label, val_str)
                    else:
                        kpi_row[i].metric(label, val_str)

            # ── Comparison table ──────────────────────────────────────────────
            st.markdown("---")
            if delta_cols:
                styled = display.style.map(_color_pct, subset=delta_cols)
                st.dataframe(styled, use_container_width=True)
            else:
                st.dataframe(display, use_container_width=True)

            # ── Executive summary ─────────────────────────────────────────────
            top_rows = None
            if "Sales" in df_curr.columns and len(df_curr) > 0:
                top_rows = df_curr.nlargest(3, "Sales").to_dict("records")

            summary_text = _generate_summary(tipo, ec1[0], kc, kp or None, per_c, per_p, top_rows, lang=lang_code)

            _expander_lbl = "View Executive Summary" if lang_code == "en" else "Ver Resumen Ejecutivo del cliente"
            st.markdown("---")
            with st.expander(_expander_lbl, expanded=True):
                st.text(summary_text)

            # ── Parent Evolution — compute before export ───────────────────────
            _pe_df  = None
            _pe_err = None
            if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
                _pe_df, _pe_err = _build_parent_evolution(
                    df1, ec1, cm1, fmt1,
                    st.session_state["parent_child_map"],
                    st.session_state.get("parent_child_names", {}),
                    br_df=st.session_state.get("br_extra_df"),
                    lang=lang_code,
                )

            # ── Export ────────────────────────────────────────────────────────
            buf = _build_atom11_excel(display, kc, kp, tipo, per_c, per_p or "", delta_cols,
                                      client_name=client_name, entity_col=ec1[0], top_rows=top_rows,
                                      lang=lang_code, parent_evo_df=_pe_df)
            safe_name = per_c[:15].replace(" ", "_").replace(",", "").replace("\u2192", "-")
            st.download_button(
                label="⬇️ Descargar análisis completo — Excel con KPIs + Tabla + Resumen Ejecutivo",
                data=buf.getvalue(),
                file_name=f"atom11_{tipo.lower().replace(' ', '_')}_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="atom11_export",
                use_container_width=True,
            )

            # ── 🧬 Evolución por Parent ASIN ─────────────────────────────────
            st.markdown("---")
            st.markdown("### 🧬 Evolución por Parent ASIN")
            _t_pe = _I18N.get(lang_code, _I18N["es"])
            if "parent_child_map" not in st.session_state or not st.session_state["parent_child_map"]:
                st.info(_t_pe["pe_no_map"])
            elif _pe_err:
                st.warning(_pe_err)
            elif _pe_df is not None and not _pe_df.empty:
                st.caption(f"{len(_pe_df)} {_t_pe['pe_caption']}")
                _pe_pct_cols = [c for c in _pe_df.columns if "%" in c]
                _pe_styled = _pe_df.style.map(_color_pct, subset=_pe_pct_cols) if _pe_pct_cols else _pe_df.style
                st.dataframe(_pe_styled, use_container_width=True, hide_index=True)
                with st.expander(_t_pe["pe_expander_lbl"]):
                    st.code(_generate_parent_evo_summary(_pe_df, lang=lang_code), language=None)
            else:
                st.info(_t_pe["pe_no_rows"])

        except Exception as e:
            st.error(f"Error al procesar los archivos: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ── Business Report — mapeo activo + input opcional para marca nueva ─────
    st.markdown("---")
    st.markdown("### 📂 Mapeo Parent-Child")

    # Estado del mapeo activo
    if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
        _n_ch = len(st.session_state["parent_child_map"])
        _n_pr = len(set(st.session_state["parent_child_map"].values()))
        _src  = st.session_state.get("_cat_source_file", "archivo desconocido")
        _has_br_extra = (
            st.session_state.get("br_extra_df") is not None
            and not st.session_state["br_extra_df"].empty
        )
        _extra_note = f" · {len([c for c in _BR_OPTIONAL_COLS if c in st.session_state['br_extra_df'].columns])} métricas BR" if _has_br_extra else ""
        st.caption(f"📂 Mapeo activo: `{_src}` — {_n_pr} parents · {_n_ch} children{_extra_note}")
        _map_df = pd.DataFrame(
            [{"Child ASIN": k, "Parent ASIN": v}
             for k, v in st.session_state["parent_child_map"].items()]
        )
        _map_names = st.session_state.get("parent_child_names", {})
        if _map_names:
            _map_df["Título"] = _map_df["Child ASIN"].map(_map_names).fillna("")
        with st.expander(f"Ver mapeo completo ({len(_map_df)} children)", expanded=False):
            st.dataframe(_map_df, use_container_width=True, hide_index=True)
    else:
        st.warning(
            "No se encontró mapeo automático. "
            "Colocá el Business Report CSV en `data/business_report/` o subilo abajo."
        )

    # ── Input opcional para marca nueva ──────────────────────────────────────
    st.markdown("**¿Marca nueva?** Subí el Business Report aquí")
    _new_br_file = st.file_uploader(
        "Business Report (.csv o .xlsx)",
        type=["csv", "xlsx"],
        key="atom11_new_br",
        label_visibility="collapsed",
    )

    if _new_br_file:
        try:
            _new_bytes = _new_br_file.getvalue()
            _new_c_map, _new_n_map, _new_br_df = _parse_business_report_map(_new_br_file)

            # Actualizar mapeo en session_state
            st.session_state["parent_child_map"]   = _new_c_map
            st.session_state["parent_child_names"] = _new_n_map
            st.session_state["br_extra_df"]        = _new_br_df
            st.session_state["_cat_source_file"]   = _new_br_file.name

            _new_n_pr = len(set(_new_c_map.values()))
            _new_n_ch = len(_new_c_map)
            st.success(f"✅ Nuevo mapeo cargado: {_new_n_pr} parents · {_new_n_ch} children")

            # Proponer guardar permanentemente
            _save_ext    = os.path.splitext(_new_br_file.name)[1].lower() or ".csv"
            _save_prefix = (client_name.strip().replace(" ", "") if client_name.strip() else "Cliente")
            _save_name   = f"{_save_prefix}_Business_Report{_save_ext}"
            _save_path   = os.path.join(_BIZ_DIR, _save_name)

            st.info(
                f"¿Querés guardar este archivo en `data/business_report/` "
                f"para que quede permanente para esta marca?"
            )
            st.caption(f"Se guardaría como: `{_save_name}`")

            _btn_yes, _btn_no, _ = st.columns([1, 1, 3])

            if _btn_yes.button("💾 Sí, guardar", key="br_save_yes", use_container_width=True):
                os.makedirs(_BIZ_DIR, exist_ok=True)
                with open(_save_path, "wb") as _fout:
                    _fout.write(_new_bytes)
                st.session_state["_cat_source_file"] = _save_name
                st.success(f"✅ Guardado como `{_save_name}` en `data/business_report/`")

            if _btn_no.button("🚫 Solo esta sesión", key="br_save_no", use_container_width=True):
                st.info("Mapeo activo solo para esta sesión, no se guardó en disco.")

        except Exception as _new_e:
            st.error(f"Error al parsear el Business Report: {_new_e}")
