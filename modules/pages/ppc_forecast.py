import io

import numpy as np
import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


# ── Helpers numéricos ────────────────────────────────────────────────────────

def _clean_num(series):
    """Limpia $, %, comas y convierte a float."""
    return (
        pd.to_numeric(
            series.astype(str)
            .str.replace(r"[\$%,]", "", regex=True)
            .str.strip(),
            errors="coerce",
        ).fillna(0.0)
    )


# ── Parsers ──────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _parse_br_daily(file_bytes, fname):
    """Parsea BR diario. Retorna DataFrame con columnas _date, _sales, _units, _sess."""
    df = pd.read_excel(io.BytesIO(file_bytes)) if fname.endswith(".xlsx") else pd.read_csv(io.BytesIO(file_bytes))
    df.columns = df.columns.str.strip()

    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    sales_col = next(
        (c for c in df.columns if "ordered product sales" in c.lower() and "b2b" not in c.lower()),
        None,
    )
    units_col = next(
        (c for c in df.columns if "units ordered" in c.lower() and "b2b" not in c.lower()),
        None,
    )
    sess_col = next(
        (c for c in df.columns if "sessions" in c.lower() and "total" in c.lower() and "b2b" not in c.lower()),
        None,
    )

    if not date_col:
        raise ValueError("No se encontró columna Date en el archivo.")
    if not sales_col:
        raise ValueError("No se encontró columna Ordered Product Sales en el archivo.")

    df["_date"] = pd.to_datetime(df[date_col], format="mixed", dayfirst=False, errors="coerce")
    df = df.dropna(subset=["_date"])
    df["_sales"] = _clean_num(df[sales_col])
    df["_units"] = _clean_num(df[units_col]) if units_col else 0.0
    df["_sess"] = _clean_num(df[sess_col]) if sess_col else 0.0

    df = df.sort_values("_date").reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def _parse_campaigns(file_bytes, fname):
    """Parsea Campaign CSV. Retorna (df, spend_col, sales_col)."""
    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = df.columns.str.strip()

    spend_col = next((c for c in df.columns if "spend" in c.lower() or "cost" in c.lower()), None)
    sales_col = next((c for c in df.columns if "sales" in c.lower()), None)
    return df, spend_col, sales_col


# ── Core logic ───────────────────────────────────────────────────────────────

def _linear_forecast(values, horizon):
    """Ajusta tendencia lineal y proyecta 'horizon' días hacia adelante."""
    n = len(values)
    x = np.arange(n, dtype=float)
    coeffs = np.polyfit(x, values, 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])

    future_x = np.arange(n, n + horizon, dtype=float)
    projected = slope * future_x + intercept
    projected = np.maximum(projected, 0.0)

    return projected, slope, intercept


def _detect_seasonality(df):
    """Detecta efecto finde de semana vs días laborales."""
    df = df.copy()
    df["_dow"] = df["_date"].dt.dayofweek  # 0=Mon … 6=Sun
    weekday_avg = df[df["_dow"] < 5]["_sales"].mean() or 0.0
    weekend_avg = df[df["_dow"] >= 5]["_sales"].mean() or 0.0
    weekend_ratio = (weekend_avg / weekday_avg) if weekday_avg > 0 else 1.0
    return float(weekend_ratio), float(weekday_avg), float(weekend_avg)


def _build_projection(df, horizon, weekend_ratio):
    """Genera DataFrame de proyección diaria con ajuste por estacionalidad."""
    sales_values = df["_sales"].values.astype(float)
    projected_sales, slope, intercept = _linear_forecast(sales_values, horizon)

    last_date = df["_date"].max()
    rows = []
    for i in range(horizon):
        proj_date = last_date + pd.Timedelta(days=i + 1)
        dow = proj_date.dayofweek
        base = projected_sales[i]
        adjusted = base * weekend_ratio if dow >= 5 else base
        rows.append(
            {
                "Fecha": proj_date.strftime("%Y-%m-%d"),
                "Día": proj_date.strftime("%A"),
                "Ventas Proyectadas ($)": round(adjusted, 2),
                "Tipo": "Fin de semana" if dow >= 5 else "Laboral",
            }
        )

    return pd.DataFrame(rows), slope, intercept


def _budget_recommendation(current_spend, current_sales, target_sales):
    """Estima spend necesario para alcanzar target_sales."""
    if current_sales > 0:
        return target_sales * (current_spend / current_sales)
    return current_spend


# ── Excel export ─────────────────────────────────────────────────────────────

def _build_forecast_excel(hist_df, proj_df, metrics, client_name):
    """Construye Excel con 2 hojas: Resumen + Proyección Diaria."""
    HDR_FILL = PatternFill("solid", fgColor="E84000")
    HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL = PatternFill("solid", fgColor="FFF3E0")
    CENTER = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="DDDDDD")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()

    # ── Hoja 1: Resumen ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"

    # Título branding
    ws.merge_cells("A1:D1")
    title_cell = ws["A1"]
    titulo = f"PPC Forecast — {client_name}" if client_name else "PPC Forecast"
    title_cell.value = titulo
    title_cell.fill = HDR_FILL
    title_cell.font = Font(bold=True, color="FFFFFF", size=13)
    title_cell.alignment = CENTER
    ws.row_dimensions[1].height = 24

    ws.append([])  # blank row

    # Métricas históricas
    ws.append(["Métrica", "Valor"])
    for cell in ws[ws.max_row]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER

    metric_rows = [
        ("Días de datos", metrics["n_days"]),
        ("Ventas promedio/día ($)", f"${metrics['avg_daily']:.2f}"),
        ("Tendencia (slope $/día)", f"{metrics['slope']:+.2f}"),
        ("Ratio Finde/Laboral", f"{metrics['weekend_ratio']:.2f}x"),
        ("Horizonte de proyección (días)", metrics["horizon"]),
        ("Total ventas proyectadas ($)", f"${metrics['total_proj']:.2f}"),
        ("Total ventas con crecimiento objetivo ($)", f"${metrics['total_with_growth']:.2f}"),
        ("Spend estimado para objetivo ($)", f"${metrics['needed_spend']:.2f}"),
    ]

    for i, (label, val) in enumerate(metric_rows):
        ws.append([label, val])
        row_idx = ws.max_row
        for cell in ws[row_idx]:
            cell.border = BORDER
            if i % 2 == 1:
                cell.fill = ALT_FILL

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 24

    # ── Hoja 2: Proyección Diaria ────────────────────────────────────────────
    ws2 = wb.create_sheet("Proyección Diaria")

    headers = list(proj_df.columns)
    ws2.append(headers)
    for cell in ws2[1]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER

    for i, row in proj_df.iterrows():
        ws2.append(list(row))
        row_idx = ws2.max_row
        for cell in ws2[row_idx]:
            cell.border = BORDER
            if i % 2 == 1:
                cell.fill = ALT_FILL
        # Color tipo finde
        tipo_cell = ws2.cell(row=row_idx, column=4)
        if tipo_cell.value == "Fin de semana":
            tipo_cell.fill = PatternFill("solid", fgColor="FFF3E0")

    for col_idx, col in enumerate(["A", "B", "C", "D"], start=1):
        ws2.column_dimensions[col].width = 22

    ws2.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── Render ───────────────────────────────────────────────────────────────────

def render():
    st.header("Forecast PPC")
    st.caption("Proyección de ventas y spend basada en tendencia histórica + estacionalidad.")
    st.divider()

    # ── Inputs globales ──────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        target_growth = st.slider(
            "Crecimiento objetivo (%)",
            min_value=0, max_value=100, value=10, step=5,
            help="Cuánto quieres crecer sobre la proyección de tendencia base.",
        )
    with col_b:
        horizon = st.selectbox(
            "Horizonte de proyección (días)",
            options=[7, 14, 30],
            index=1,
        )
    with col_c:
        client_name = st.text_input("Nombre del cliente (para el Excel)", value="")

    st.markdown("---")

    # ── Uploaders ────────────────────────────────────────────────────────────
    file_br = st.file_uploader(
        "BR Diario (.csv o .xlsx) — requerido",
        type=["csv", "xlsx"],
        key="forecast_br",
        help="Business Report > By Date > Sales and Traffic. Mínimo 14 días.",
    )
    file_camp = st.file_uploader(
        "Campaign CSV (.csv) — opcional, para separar orgánico vs paid",
        type=["csv"],
        key="forecast_camp",
    )

    if not file_br:
        st.info("Sube el BR Diario para comenzar.")
        return

    # ── Parseo BR ────────────────────────────────────────────────────────────
    try:
        br_bytes = file_br.read()
        df = _parse_br_daily(br_bytes, file_br.name)
    except Exception as e:
        st.error(f"Error al leer BR Diario: {e}")
        return

    n_days = len(df)
    if n_days < 7:
        st.error("El archivo tiene menos de 7 días de datos. Se necesitan al menos 7 días para proyectar.")
        return
    if n_days < 14:
        st.warning(f"Sólo hay {n_days} días de datos. La proyección será menos precisa. Se recomiendan al menos 14 días.")

    # ── Botón principal ──────────────────────────────────────────────────────
    if not st.button("Generar Forecast", type="primary"):
        st.info(f"Archivo cargado: {file_br.name} ({n_days} días). Haz clic en 'Generar Forecast' para continuar.")
        return

    # ── Cálculos ─────────────────────────────────────────────────────────────
    avg_daily = float(df["_sales"].mean())
    weekend_ratio, weekday_avg, weekend_avg = _detect_seasonality(df)
    proj_df, slope, intercept = _build_projection(df, horizon, weekend_ratio)
    total_proj = float(proj_df["Ventas Proyectadas ($)"].sum())
    total_with_growth = total_proj * (1 + target_growth / 100)

    # Spend y ACoS del Campaign CSV
    total_spend = 0.0
    total_ad_sales = 0.0
    acos_pct = 0.0
    organic_sales = 0.0

    camp_loaded = False
    if file_camp:
        try:
            camp_bytes = file_camp.read()
            camp_df, spend_col, sales_col_camp = _parse_campaigns(camp_bytes, file_camp.name)
            if spend_col:
                total_spend = float(_clean_num(camp_df[spend_col]).sum())
            if sales_col_camp:
                total_ad_sales = float(_clean_num(camp_df[sales_col_camp]).sum())
            if total_ad_sales > 0:
                acos_pct = (total_spend / total_ad_sales) * 100
            hist_total_sales = float(df["_sales"].sum())
            organic_sales = max(hist_total_sales - total_ad_sales, 0.0)
            camp_loaded = True
        except Exception as e:
            st.warning(f"No se pudo leer el Campaign CSV: {e}. Continuando sin datos de campaña.")

    needed_spend = _budget_recommendation(total_spend, float(df["_sales"].sum()), total_with_growth)

    metrics = {
        "n_days": n_days,
        "avg_daily": avg_daily,
        "slope": slope,
        "weekend_ratio": weekend_ratio,
        "horizon": horizon,
        "total_proj": total_proj,
        "total_with_growth": total_with_growth,
        "needed_spend": needed_spend,
    }

    # ── SECCIÓN 1: Métricas históricas ───────────────────────────────────────
    st.subheader("Métricas Históricas")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Días de datos", f"{n_days}")
    c2.metric("Ventas promedio/día", f"${avg_daily:.2f}")
    trend_sign = "+" if slope >= 0 else ""
    c3.metric("Tendencia", f"{trend_sign}{slope:.2f} $/día")
    c4.metric("Ratio Finde/Laboral", f"{weekend_ratio:.2f}x")

    # ── SECCIÓN 2: Gráfico ───────────────────────────────────────────────────
    st.subheader("Tendencia Histórica + Proyección")

    hist_dates = [d.strftime("%Y-%m-%d") for d in df["_date"]]
    hist_sales = df["_sales"].tolist()
    proj_dates = proj_df["Fecha"].tolist()
    proj_sales = proj_df["Ventas Proyectadas ($)"].tolist()

    all_dates = hist_dates + proj_dates
    chart_df = pd.DataFrame(
        {
            "Ventas Reales ($)": hist_sales + [None] * horizon,
            "Ventas Proyectadas ($)": [None] * len(hist_sales) + proj_sales,
        },
        index=all_dates,
    )
    # Añadir el último punto histórico como primer punto proyectado para continuidad visual
    if hist_sales:
        chart_df.loc[hist_dates[-1], "Ventas Proyectadas ($)"] = hist_sales[-1]

    st.line_chart(chart_df)

    # ── SECCIÓN 3: Resumen de proyección ─────────────────────────────────────
    st.subheader(f"Resumen — Próximos {horizon} días")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        f"Ventas proyectadas ({horizon}d)",
        f"${total_proj:,.2f}",
    )
    c2.metric(
        f"Con crecimiento +{target_growth}%",
        f"${total_with_growth:,.2f}",
        delta=f"+${total_with_growth - total_proj:,.2f}",
    )
    c3.metric(
        "Spend estimado para objetivo",
        f"${needed_spend:,.2f}",
        help="Estimado basado en el ratio spend/ventas histórico del Campaign CSV." if camp_loaded else "Sube el Campaign CSV para calcular.",
    )

    # ── SECCIÓN 4: Tabla de proyección diaria ────────────────────────────────
    with st.expander("Ver tabla de proyección diaria"):
        st.dataframe(
            proj_df,
            use_container_width=True,
            column_config={
                "Ventas Proyectadas ($)": st.column_config.NumberColumn(
                    "Ventas Proyectadas ($)", format="$%.2f"
                ),
            },
        )

    # ── SECCIÓN 5: Campaign split ────────────────────────────────────────────
    if camp_loaded:
        st.subheader("Desglose Orgánico vs Paid")
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Total Ad Spend", f"${total_spend:,.2f}")
        cc2.metric("Total Ad Sales", f"${total_ad_sales:,.2f}")
        cc3.metric("ACoS histórico", f"{acos_pct:.1f}%")
        cc4.metric("Ventas orgánicas estimadas", f"${organic_sales:,.2f}")

        hist_total_sales = float(df["_sales"].sum())
        if hist_total_sales > 0:
            paid_pct = min((total_ad_sales / hist_total_sales) * 100, 100.0)
            organic_pct = 100.0 - paid_pct
            split_df = pd.DataFrame(
                {
                    "Canal": ["Paid (Ads)", "Orgánico"],
                    "Ventas ($)": [round(total_ad_sales, 2), round(organic_sales, 2)],
                    "% del Total": [round(paid_pct, 1), round(organic_pct, 1)],
                }
            )
            st.dataframe(split_df, use_container_width=True, hide_index=True)

    # ── Export Excel ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Exportar")
    try:
        excel_buf = _build_forecast_excel(df, proj_df, metrics, client_name)
        fname_out = f"PPC_Forecast_{client_name.replace(' ', '_') + '_' if client_name else ''}{horizon}d.xlsx"
        st.download_button(
            label="Descargar Forecast Excel",
            data=excel_buf,
            file_name=fname_out,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.error(f"Error al generar Excel: {e}")
