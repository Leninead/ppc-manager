import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ── Helpers BR — detección tolerante a variantes Amazon (dashes unicode, splits, B2B) ──
_DASHES_UNICODE = ("–", "—", "−")  # en-dash, em-dash, minus sign


def _normalizar_col_br(s):
    """Normaliza nombre de columna del BR: lowercase + dashes unicode → '-' + collapse spaces + strip."""
    if s is None:
        return ""
    s = str(s)
    for d in _DASHES_UNICODE:
        s = s.replace(d, "-")
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _detectar_columnas_br(df, tipo):
    """
    Detecta columnas del BR de manera tolerante a variantes Amazon.

    tipo: 'by_date' (BR diario By Date) | 'by_child' (BR Detail Page By Child Item)

    Retorna dict con columnas reales encontradas + flags de opcionales.
    Filtra B2B uniformemente en ambos tipos — info B2B disponible vía flag b2b_disponible.
    CVR fallback uniforme: Unit Session Percentage → Order Item Session Percentage.
    """
    cols = list(df.columns)
    norm_pairs = [(_normalizar_col_br(c), c) for c in cols]

    def _find(needle, exclude_b2b=True):
        """Match por substring sobre columnas normalizadas. Excluye B2B por default."""
        needle_n = _normalizar_col_br(needle)
        for col_n, col_real in norm_pairs:
            if needle_n in col_n:
                if exclude_b2b and "b2b" in col_n:
                    continue
                return col_real
        return None

    # Sessions — Total directo o splits Mobile App + Browser
    sessions_total   = _find("sessions - total") or _find("sessions total")
    sessions_mobile  = _find("sessions - mobile app") or _find("sessions mobile app")
    sessions_browser = _find("sessions - browser") or _find("sessions browser")

    # Page Views (opcional)
    page_views_total   = _find("page views - total") or _find("page views total")
    page_views_mobile  = _find("page views - mobile app") or _find("page views mobile app")
    page_views_browser = _find("page views - browser") or _find("page views browser")

    # CVR — fallback uniforme en ambos tipos
    cvr = _find("unit session percentage") or _find("order item session percentage")

    # BuyBox
    buybox = (
        _find("featured offer (buy box) percentage")
        or _find("buy box percentage")
        or _find("featured offer")
    )

    # Métricas core + opcionales
    units_ordered         = _find("units ordered")
    ordered_product_sales = _find("ordered product sales")
    total_order_items     = _find("total order items")
    units_refunded        = _find("units refunded")
    refund_rate           = _find("refund rate")
    shipped_product_sales = _find("shipped product sales")
    units_shipped         = _find("units shipped")
    orders_shipped        = _find("orders shipped")

    detect = {
        "sessions_total":         sessions_total,
        "sessions_mobile":        sessions_mobile,
        "sessions_browser":       sessions_browser,
        "page_views_total":       page_views_total,
        "page_views_mobile":      page_views_mobile,
        "page_views_browser":     page_views_browser,
        "cvr":                    cvr,
        "buybox":                 buybox,
        "units_ordered":          units_ordered,
        "ordered_product_sales":  ordered_product_sales,
        "total_order_items":      total_order_items,
        "units_refunded":         units_refunded,
        "refund_rate":            refund_rate,
        "shipped_product_sales":  shipped_product_sales,
        "units_shipped":          units_shipped,
        "orders_shipped":         orders_shipped,
        # Flags
        "b2b_disponible":           any("b2b" in _normalizar_col_br(c) for c in cols),
        "sessions_split_presente":  bool(sessions_mobile and sessions_browser),
        "page_views_disponibles":   bool(page_views_total or (page_views_mobile and page_views_browser)),
        "refunds_disponibles":      bool(units_refunded or refund_rate),
        "shipped_disponible":       bool(shipped_product_sales or units_shipped or orders_shipped),
    }

    if tipo == "by_date":
        detect["date"] = next((c for c in cols if "date" in c.lower()), None)

    elif tipo == "by_child":
        # ASIN child + parent + title (nunca filtrar B2B en estos campos)
        asin_child = None
        asin_parent = None
        title_col = None
        for col_n, col_real in norm_pairs:
            if asin_child is None and ("(child) asin" in col_n or "child asin" in col_n):
                asin_child = col_real
            if asin_parent is None and ("(parent) asin" in col_n or "parent asin" in col_n):
                asin_parent = col_real
            if title_col is None and "title" in col_n:
                title_col = col_real
        # Fallback: cualquier "asin" suelto si no hubo child específico
        if asin_child is None:
            for col_n, col_real in norm_pairs:
                if "asin" in col_n:
                    asin_child = col_real
                    break
        detect["asin_child"]  = asin_child
        detect["asin_parent"] = asin_parent
        detect["title"]       = title_col

    return detect


def _validar_cols_core_br(detect, tipo):
    """Retorna lista de nombres canónicos faltantes. Vacía si OK."""
    faltantes = []
    if tipo == "by_date":
        if not detect.get("date"):
            faltantes.append("Date")
        if not detect.get("sessions_total") and not detect.get("sessions_split_presente"):
            faltantes.append("Sessions - Total (o Sessions - Mobile App + Sessions - Browser)")
        if not detect.get("units_ordered"):
            faltantes.append("Units Ordered")
        if not detect.get("ordered_product_sales"):
            faltantes.append("Ordered Product Sales")
    elif tipo == "by_child":
        if not detect.get("asin_child"):
            faltantes.append("(Child) ASIN")
        if not detect.get("ordered_product_sales"):
            faltantes.append("Ordered Product Sales")
        if not detect.get("units_ordered"):
            faltantes.append("Units Ordered")
        if not detect.get("sessions_total") and not detect.get("sessions_split_presente"):
            faltantes.append("Sessions - Total (o Sessions - Mobile App + Sessions - Browser)")
    return faltantes


_UMBRAL_ESTABLE = 2.0  # ±2%: el mismo que usa el resto del ejecutivo

_MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic")
_MESES_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _rango_legible(period, lang="es"):
    """{'start','end'} ISO -> '03-09 ago' | '28 jul - 03 ago'. None si no hay dato.

    El encabezado tiene que decir de que fechas habla cada columna: con
    "Esta semana: 10-16 ago" al lado de montos de 14 dias, el bug original se
    veia a simple vista, sin auditoria.
    """
    if not period or not period.get("start") or not period.get("end"):
        return None
    meses = _MESES_ES if lang == "es" else _MESES_EN

    def _partes(iso):
        try:
            y, m, d = str(iso)[:10].split("-")
            return int(m), int(d)
        except (ValueError, AttributeError):
            return None
    p_ini, p_fin = _partes(period["start"]), _partes(period["end"])
    if not p_ini or not p_fin:
        return None
    (m1, d1), (m2, d2) = p_ini, p_fin

    if lang == "es":
        if m1 == m2:
            return f"{d1:02d}–{d2:02d} {meses[m1 - 1]}"
        return f"{d1:02d} {meses[m1 - 1]} – {d2:02d} {meses[m2 - 1]}"
    if m1 == m2:
        return f"{meses[m1 - 1]} {d1:02d}–{d2:02d}"
    return f"{meses[m1 - 1]} {d1:02d} – {meses[m2 - 1]} {d2:02d}"


def _sufijo_periodo(modo_wow, period_child_tw, period_child_pw, br_daily, t, lang="es"):
    """Sufijo del titulo con el periodo real de las columnas. '' si no hay dato."""
    if modo_wow:
        r_tw = _rango_legible(period_child_tw, lang)
        r_pw = _rango_legible(period_child_pw, lang)
        if r_tw and r_pw:
            return f" · {t['tw']}: {r_tw} · {t['pw']}: {r_pw}"
        return ""

    full = period_child_tw
    if not full and br_daily:
        _p_tw = br_daily.get("period_tw") or {}
        _p_pw = br_daily.get("period_pw") or {}
        dias = _p_tw.get("days", 0) + _p_pw.get("days", 0)
        if dias:
            full = {"start": _p_pw.get("start") or _p_tw.get("start"),
                    "end": _p_tw.get("end") or _p_pw.get("end"), "days": dias}
    rango = _rango_legible(full, lang)
    if not rango:
        return ""
    dias = (full or {}).get("days")
    etiqueta = t["full_period"].format(days=dias) if dias else t["full_period_nodays"]
    return f" · {etiqueta}: {rango}"


def _calificar_trafico(se_d, cvr_d):
    """Cruza el delta de sesiones con el de conversion antes de calificar.

    Devuelve la clave del dict de traducciones a usar. Mirar solo las sesiones
    hacia felicitar un alza de trafico que convierte peor: en el WoW real de
    Setex el trafico subio 43,9% mientras el CVR caia 39,7% y las ventas 20,1%,
    y el reporte lo presentaba como logro. Mas gente que compra menos es un
    diagnostico de CALIDAD de trafico, no un exito.

    Sin CVR disponible cae al texto neutro: describe el movimiento sin calificarlo.
    """
    if se_d is None:
        return None
    sube = se_d > _UMBRAL_ESTABLE
    baja = se_d < -_UMBRAL_ESTABLE
    if not (sube or baja):
        return None  # dentro del rango estable: no amerita frase propia

    if cvr_d is None:
        return "sess_up_neutro" if sube else "sess_down"

    cvr_sube = cvr_d > _UMBRAL_ESTABLE
    cvr_baja = cvr_d < -_UMBRAL_ESTABLE
    if sube:
        if cvr_baja:
            return "sess_up_cvr_down"   # el caso Setex: NO felicitar
        return "sess_up" if cvr_sube else "sess_up_neutro"
    if cvr_sube:
        return "sess_down_cvr_up"       # menos trafico, mejor calificado
    return "sess_down"


def _trend_ejecutivo(s_d, u_d, se_d):
    """Veredicto de la semana. Devuelve 'pos' | 'neg' | 'flat'.

    REGLA: el trend lo deciden VENTAS y UNIDADES, que son resultados. Las sesiones
    son un input y NO computan como senal positiva por si solas — antes las tres
    metricas votaban igual, asi que un alza de trafico sin ventas empujaba el
    veredicto a "Semana positiva".

    Las sesiones entran solo como desempate cuando ventas y unidades se
    contradicen entre si, y ahi solo pueden inclinar hacia negativo (trafico
    cayendo confirma el problema), nunca hacia positivo.
    """
    resultados = [d for d in (s_d, u_d) if d is not None]
    if not resultados:
        return "flat"
    pos = sum(1 for d in resultados if d > _UMBRAL_ESTABLE)
    neg = sum(1 for d in resultados if d < -_UMBRAL_ESTABLE)

    if pos and not neg:
        return "pos"
    if neg and not pos:
        return "neg"
    if neg and pos:
        # ventas y unidades en direcciones opuestas: el trafico desempata, pero
        # solo puede confirmar el lado negativo.
        if se_d is not None and se_d < -_UMBRAL_ESTABLE:
            return "neg"
        return "flat"
    return "flat"


def _es_modo_wow(period_child_tw, period_child_pw):
    """Unica fuente de verdad del modo: dos periodos by-Child de 7 dias exactos.

    Se mira `days`, no la mera presencia del dato: un periodo informado de 14d NO
    habilita la comparacion semanal. La usan _build_weekly_excel y render(), para
    que la UI y el Excel no puedan discrepar sobre en que modo esta el reporte.
    """
    return bool(
        period_child_tw and period_child_tw.get("days") == 7
        and period_child_pw and period_child_pw.get("days") == 7
    )


def _derivar_periodos(br_daily, hay_child_pw):
    """-> (period_child_tw, period_child_pw). El by-Child no trae fechas propias.

    Las unicas fechas reales del reporte estan en el BR diario, asi que de ahi se
    derivan. Sin BR diario NO se inventa nada: se devuelve (None, None) y el
    reporte degrada a MODO PERIODO COMPLETO.

    Vivia dentro de render(), donde ningun test lo veia. Extraido porque es
    aritmetica pura sobre dos dicts y ahi es donde entro el bug de dos by-Child
    sin diario.
    """
    if not br_daily:
        return None, None
    p_tw = br_daily.get("period_tw") or {}
    p_pw = br_daily.get("period_pw") or {}

    if hay_child_pw:
        # Un archivo por semana: cada by-Child hereda la mitad que le corresponde.
        return br_daily.get("period_tw"), br_daily.get("period_pw")

    # Un solo archivo: cubre el periodo COMPLETO del diario.
    dias = p_tw.get("days", 0) + p_pw.get("days", 0)
    if not dias:
        return None, None
    return {
        "start": p_pw.get("start") or p_tw.get("start"),
        "end":   p_tw.get("end")   or p_pw.get("end"),
        "days":  dias,
    }, None


def _chequear_coherencia_child(br_child, total_diario, etiqueta, tol=0.01):
    """Compara la suma de Sales de un by-Child contra el total del BR diario.

    Devuelve None si cuadran dentro de la tolerancia (1% por defecto), o un dict
    {'etiqueta','suma','esperado','delta','delta_pct'} si se pasan.

    Es la verificacion que se hizo a mano contra los datos de Setex y que destapo
    el bug: si el AM exporta el by-Child con un rango distinto al del BR diario,
    los numeros por producto no corresponden al periodo que dice la columna.
    Automatizarla es lo que vuelve el fix verificable y no solo posible.
    """
    if not br_child or total_diario is None:
        return None
    suma = sum(v.get("Sales", 0) for v in br_child.values())
    esperado = float(total_diario)

    if esperado <= 0:
        # Antes se retornaba None aca, que silenciaba el caso mas grave: un BR
        # diario de 7 fechas deja Sales_PW en 0, y un by-Child con ventas contra
        # 0 es divergencia total, no coherencia. Sin denominador no hay %.
        if suma <= 0:
            return None
        return {
            "etiqueta": etiqueta, "suma": suma, "esperado": esperado,
            "delta": suma, "delta_pct": None,
        }

    delta = suma - esperado
    delta_pct = delta / esperado * 100
    if abs(delta) / esperado <= tol:
        return None
    return {
        "etiqueta": etiqueta, "suma": suma, "esperado": esperado,
        "delta": delta, "delta_pct": delta_pct,
    }


def _periodo(fechas):
    """[str ISO] -> {'start','end','days'} | None si la lista viene vacia.

    `days` es la cantidad de fechas DISTINTAS presentes, no el delta calendario:
    un export con huecos tiene menos dias de dato que dias de rango, y lo que
    define si una columna es "semanal" es cuantos dias de dato la respaldan.
    """
    if not fechas:
        return None
    distintas = sorted(set(fechas))
    return {"start": distintas[0], "end": distintas[-1], "days": len(distintas)}


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_br_daily_wow(file):
    fname = file.name if hasattr(file, "name") else ""
    df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)

    detect = _detectar_columnas_br(df, tipo="by_date")
    faltantes = _validar_cols_core_br(detect, tipo="by_date")
    if faltantes:
        raise ValueError(
            "Falta(n) columna(s) requerida(s) en el BR diario: "
            + ", ".join(faltantes)
            + ". Re-exportá el reporte con esas columnas activadas en "
            "Seller Central → Reports → Business Reports → By Date → Sales and Traffic."
        )

    def _clean(series):
        return pd.to_numeric(
            series.astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce").fillna(0)

    df["_date"] = pd.to_datetime(df[detect["date"]], format="mixed", dayfirst=False)
    df = df.sort_values("_date")
    dates = sorted(df["_date"].unique())
    if len(dates) < 7:
        raise ValueError(f"BR diario: solo {len(dates)} fechas, se necesitan al menos 7")
    split_date = dates[-7]
    pw_df = df[df["_date"] < split_date]
    tw_df = df[df["_date"] >= split_date]

    # Sessions: Total directo o sumar split Mobile App + Browser
    def _sessions_sum(d):
        if detect["sessions_total"]:
            return round(_clean(d[detect["sessions_total"]]).sum(), 2)
        return round(
            (_clean(d[detect["sessions_mobile"]]) + _clean(d[detect["sessions_browser"]])).sum(),
            2,
        )

    def _s(d, col): return round(_clean(d[col]).sum(), 2) if col else 0
    def _a(d, col): return round(_clean(d[col]).mean(), 2) if col else 0

    sales_col = detect["ordered_product_sales"]
    units_col = detect["units_ordered"]
    cvr_col   = detect["cvr"]
    bb_col    = detect["buybox"]

    # CVR de cuenta PONDERADO por sesiones, calculado UNA VEZ en el origen.
    # `_a(cvr_col)` promedia los porcentajes DIARIOS: un dia de 3 sesiones pesa
    # igual que uno de 500 (medido: 1,43% contra 9,65% real). Lo leen cinco
    # consumidores — la fila CUENTA TOTAL (valor TW, valor PW y su delta), el
    # Reporte Ejecutivo y el prompt de IA — asi que ponderar aca y no en cada uno
    # es lo que evita que el proximo consumidor reintroduzca el defecto.
    # Bonus: ya no depende de que Amazon exporte la columna de CVR.
    _u_tw, _u_pw = _s(tw_df, units_col), _s(pw_df, units_col)
    _se_tw, _se_pw = _sessions_sum(tw_df), _sessions_sum(pw_df)

    def _cvr(units, sessions):
        return round(units / sessions * 100, 2) if sessions else 0

    return {
        "Sales_TW":    _s(tw_df, sales_col), "Sales_PW":    _s(pw_df, sales_col),
        "Units_TW":    _u_tw,                "Units_PW":    _u_pw,
        "Sessions_TW": _se_tw,               "Sessions_PW": _se_pw,
        "CVR_TW":      _cvr(_u_tw, _se_tw),  "CVR_PW":      _cvr(_u_pw, _se_pw),
        "BuyBox_TW":   _a(tw_df, bb_col) if bb_col else None,
        "BuyBox_PW":   _a(pw_df, bb_col) if bb_col else None,
        "dates_pw": [str(d.date()) for d in sorted(pw_df["_date"].unique())],
        "dates_tw": [str(d.date()) for d in sorted(tw_df["_date"].unique())],
        # Periodo explicito de cada mitad: lo que permite a _build_weekly_excel
        # decidir si puede rotular una columna como semanal.
        "period_pw": _periodo([str(d.date()) for d in sorted(pw_df["_date"].unique())]),
        "period_tw": _periodo([str(d.date()) for d in sorted(tw_df["_date"].unique())]),
    }


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_br_wow(file):
    fname = file.name if hasattr(file, "name") else ""
    df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)

    detect = _detectar_columnas_br(df, tipo="by_child")
    faltantes = _validar_cols_core_br(detect, tipo="by_child")
    if faltantes:
        raise ValueError(
            "Falta(n) columna(s) requerida(s) en el BR by Child: "
            + ", ".join(faltantes)
            + ". Re-exporta el reporte con esas columnas activadas en "
            "Seller Central > Reports > Business Reports > By ASIN > Detail Page Sales and Traffic By Child Item."
        )

    def _to_float(series):
        return pd.to_numeric(
            series.astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce").fillna(0)

    asin_col  = detect["asin_child"]
    title_col = detect["title"]
    cvr_col   = detect["cvr"]
    bb_col    = detect["buybox"]

    df = df.dropna(subset=[asin_col])

    # Sessions: Total directo o sumar split Mobile App + Browser
    if detect["sessions_total"]:
        df["_sessions"] = _to_float(df[detect["sessions_total"]])
    elif detect["sessions_split_presente"]:
        df["_sessions"] = (
            _to_float(df[detect["sessions_mobile"]]) + _to_float(df[detect["sessions_browser"]])
        )
    else:
        df["_sessions"] = 0  # cubierto por _validar_cols_core_br, defensivo

    df["_units"] = _to_float(df[detect["units_ordered"]]) if detect["units_ordered"] else 0
    df["_sales"] = _to_float(df[detect["ordered_product_sales"]]) if detect["ordered_product_sales"] else 0
    df["_cvr"]   = _to_float(df[cvr_col]) if cvr_col else None
    df["_bb"]    = _to_float(df[bb_col])  if bb_col  else None

    # Consolidacion por child ASIN. Amazon lista el MISMO (Child) ASIN bajo parents
    # distintos despues de merges de variaciones, y el `result[asin] = {...}` anterior
    # pisaba la primera fila (last-wins). En Setex se perdian MX$3.480 en silencio.
    parent_col = detect["asin_parent"]
    acc = {}
    for _, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        if not asin or asin == "nan": continue
        title = str(row[title_col]).strip() if title_col else ""

        sessions_val = float(row["_sessions"])

        bb_raw = row.get("_bb")
        bb_val = float(bb_raw) if bb_raw is not None and str(bb_raw) != "nan" else None
        if bb_val is not None and sessions_val == 0:
            bb_val = None

        a = acc.setdefault(asin, {
            "title": "", "sessions": 0.0, "units": 0.0, "sales": 0.0,
            "bb_num": 0.0, "bb_sessions": 0.0, "rows": 0, "parents": [],
        })
        if not a["title"] and title:
            a["title"] = title
        a["sessions"] += sessions_val
        a["units"]    += float(row["_units"])
        a["sales"]    += float(row["_sales"])
        # BuyBox se pondera por sesiones: solo acumulan las filas con bb no-nulo.
        if bb_val is not None:
            a["bb_num"]      += bb_val * sessions_val
            a["bb_sessions"] += sessions_val
        a["rows"] += 1
        if parent_col:
            parent = str(row[parent_col]).strip()
            if parent and parent != "nan" and parent not in a["parents"]:
                a["parents"].append(parent)

    result = {}
    for asin, a in acc.items():
        title = a["title"]
        # CVR SIEMPRE recalculado desde los totales consolidados, incluso para ASINs
        # de una sola fila. Verificado contra 34 filas reales de Setex: el
        # `Unit Session Percentage` de Amazon ES units/sessions redondeado a 2
        # decimales (desvio maximo 0.0044). Un solo camino evita drift entre ASINs
        # con y sin duplicados; la columna CVR del BR ya no define el valor final.
        cvr_val = (a["units"] / a["sessions"] * 100) if a["sessions"] > 0 else None
        bb_val  = (a["bb_num"] / a["bb_sessions"]) if a["bb_sessions"] > 0 else None

        result[asin] = {
            "Title":    title[:60] + ("\u2026" if len(title) > 60 else ""),
            "Sessions": a["sessions"],
            "Units":    a["units"],
            "Sales":    a["sales"],
            "CVR":      cvr_val,
            "BuyBox":   bb_val,
            # Trazabilidad de la consolidacion (claves con guion bajo: _build_weekly_excel
            # accede por .get de claves especificas, no itera el dict).
            "_rows_merged": a["rows"],
            "_parents":     a["parents"],
        }
    return result


def _parse_atom11_wow(file):
    wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
    ws = wb["Asin"] if "Asin" in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    if len(rows) < 4:
        raise ValueError("Atom 11 ASIN: archivo con menos de 4 filas")
    row0, row1 = rows[0], rows[1]
    cur_metric = None
    col_map = []
    for i, (m, d) in enumerate(zip(row0, row1)):
        if m and str(m).strip(): cur_metric = str(m).strip()
        if d and str(d).startswith("20"): col_map.append((i, cur_metric, str(d).strip()))
    dates = sorted(set(c[2] for c in col_map))
    if not dates: raise ValueError("Atom 11 ASIN: no se encontraron fechas")
    tw_dates = set(dates[-7:])
    pw_dates = set(dates[:-7])
    METRICS = ["Impressions", "Clicks", "Spend", "Sales", "Orders"]
    result = {}
    for row in rows[3:]:
        asin = row[0]
        if not asin or str(asin).strip() in ("", "nan", "None"): continue
        asin = str(asin).strip()
        rec = {}
        for metric in METRICS:
            pw_vals = [row[i] or 0 for i, m, d in col_map if m == metric and d in pw_dates]
            tw_vals = [row[i] or 0 for i, m, d in col_map if m == metric and d in tw_dates]
            rec[f"{metric}_PW"] = round(sum(float(v) for v in pw_vals), 2)
            rec[f"{metric}_TW"] = round(sum(float(v) for v in tw_vals), 2)
        result[asin] = rec
    return result


def _parse_campaign_csv(file):
    """Parse Campaign Manager CSV → dict con métricas agregadas + lista de campañas."""
    df = pd.read_csv(file)

    def _n(col):
        for c in df.columns:
            if col.lower() in c.lower():
                return c
        return None

    def _to_float(series):
        return pd.to_numeric(
            series.astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce").fillna(0)

    imp_col   = _n("Impressions")
    click_col = _n("Clicks")
    ctr_col   = _n("Click-Through Rate") or _n("CTR")
    spend_col = _n("Spend") or _n("Total cost") or _n("Cost")
    sales_col = _n("Sales") or _n("Total Sales")
    orders_col = _n("Orders") or _n("Purchases")
    acos_col  = _n("ACOS") or _n("ACoS")
    camp_col  = _n("Campaign Name") or _n("Campaign name")
    port_col  = _n("Portfolio name") or _n("Portfolio")
    dpv_col   = _n("Detail Page View") or _n("DPV")
    ntb_orders_col = _n("New-to-brand orders") or _n("NTB orders")
    ntb_sales_col  = _n("New-to-brand sales") or _n("NTB sales")

    if imp_col:   df["_imp"]   = _to_float(df[imp_col])
    if click_col: df["_click"] = _to_float(df[click_col])
    if spend_col: df["_spend"] = _to_float(df[spend_col])
    if sales_col: df["_sales"] = _to_float(df[sales_col])
    if orders_col: df["_orders"] = _to_float(df[orders_col])
    if dpv_col:   df["_dpv"]   = _to_float(df[dpv_col])
    if ntb_orders_col: df["_ntb_orders"] = _to_float(df[ntb_orders_col])
    if ntb_sales_col:  df["_ntb_sales"]  = _to_float(df[ntb_sales_col])

    totals = {
        "Impressions": df["_imp"].sum()   if "_imp"   in df else 0,
        "Clicks":      df["_click"].sum() if "_click" in df else 0,
        "Spend":       df["_spend"].sum() if "_spend" in df else 0,
        "Sales":       df["_sales"].sum() if "_sales" in df else 0,
        "Orders":      df["_orders"].sum() if "_orders" in df else 0,
        "DPV":         df["_dpv"].sum()   if "_dpv"   in df else 0,
        "NTB_Orders":  df["_ntb_orders"].sum() if "_ntb_orders" in df else 0,
        "NTB_Sales":   df["_ntb_sales"].sum()  if "_ntb_sales"  in df else 0,
    }
    totals["CTR"] = (totals["Clicks"] / totals["Impressions"] * 100) if totals["Impressions"] > 0 else 0
    totals["ACoS"] = (totals["Spend"] / totals["Sales"] * 100) if totals["Sales"] > 0 else 0
    totals["CPC"] = (totals["Spend"] / totals["Clicks"]) if totals["Clicks"] > 0 else 0
    totals["NTB_Pct"] = (totals["NTB_Orders"] / totals["Orders"] * 100) if totals["Orders"] > 0 and totals["NTB_Orders"] > 0 else 0

    # Top campaigns by spend
    campaigns = []
    if camp_col and "_spend" in df:
        grp_cols = [camp_col]
        agg_map = {"_spend": "sum"}
        if "_imp"    in df: agg_map["_imp"]    = "sum"
        if "_click"  in df: agg_map["_click"]  = "sum"
        if "_sales"  in df: agg_map["_sales"]  = "sum"
        if "_orders" in df: agg_map["_orders"] = "sum"
        camp_df = df.groupby(camp_col, as_index=False).agg(agg_map)
        camp_df = camp_df.sort_values("_spend", ascending=False).head(15)
        for _, r in camp_df.iterrows():
            imp_v = r.get("_imp", 0)
            clk_v = r.get("_click", 0)
            sal_v = r.get("_sales", 0)
            spd_v = r.get("_spend", 0)
            campaigns.append({
                "Campaign": str(r[camp_col])[:60],
                "Impressions": int(imp_v),
                "Clicks": int(clk_v),
                "CTR": round(clk_v / imp_v * 100, 2) if imp_v > 0 else 0,
                "Spend": round(spd_v, 2),
                "Sales": round(sal_v, 2),
                "ACoS": round(spd_v / sal_v * 100, 1) if sal_v > 0 else 0,
                "Orders": int(r.get("_orders", 0)),
            })

    # Portfolios
    portfolios = []
    if port_col and "_spend" in df:
        port_df = df.groupby(port_col, as_index=False).agg(agg_map)
        port_df = port_df.sort_values("_spend", ascending=False)
        for _, r in port_df.iterrows():
            pname = str(r[port_col]).strip()
            if not pname or pname in ("nan", "None", ""): pname = "(Sin Portfolio)"
            imp_v = r.get("_imp", 0)
            sal_v = r.get("_sales", 0)
            spd_v = r.get("_spend", 0)
            portfolios.append({
                "Portfolio": pname[:40],
                "Spend": round(spd_v, 2),
                "Sales": round(sal_v, 2),
                "ACoS": round(spd_v / sal_v * 100, 1) if sal_v > 0 else 0,
            })

    return {"totals": totals, "campaigns": campaigns, "portfolios": portfolios}


# Textos del Reporte Ejecutivo. A nivel de modulo para que la narrativa sea
# testeable sin tener que generar el Excel entero.
_L_EXEC = {
    "es": {
        "title_wow": "Reporte Semanal WoW", "product": "Producto", "asin": "ASIN",
        "tw": "Esta semana", "pw": "Semana anterior", "delta": "Variaci\u00f3n %",
        "full_period": "Período completo ({days}d)", "full_period_nodays": "Período completo",
            "warn_full": ("⚠️ Sin comparación semanal por producto ({days}d de datos). "
                          "Los montos por ASIN son del período completo. La comparación "
                      "semanal de la cuenta está en la hoja Reporte Ejecutivo."),
        "note": "* ACoS = Gasto Ads / Ventas Ads  |  TACoS = Gasto Ads / Ventas Totales  |  \u2014 = dato no disponible",
        "exec_title": "RESUMEN EJECUTIVO SEMANAL", "generated": "Generado por Capybaras Agency PPC Manager",
        "intro": "An\u00e1lisis comparativo semana a semana (WoW) del rendimiento en Amazon:",
        "sec_sales": "VENTAS TOTALES", "sec_traffic": "TR\u00c1FICO Y CONVERSI\u00d3N",
        "exec_no_weekly": ("Sin BR diario no hay comparación semanal de la cuenta. "
                           "Los montos por producto corresponden al período completo del archivo cargado."),
        "sec_ads": "PUBLICIDAD (ADS)", "sec_bb": "BUY BOX", "sec_conclusion": "CONCLUSI\u00d3N",
        "sales_up":   "Las ventas totales aumentaron un {d}%, de MX${pw} a MX${tw}.",
        "sales_down": "Las ventas totales cayeron un {d}%, de MX${pw} a MX${tw}.",
        "sales_flat": "Las ventas totales se mantuvieron estables (MX${tw}).",
        "units_up":   "Las unidades crecieron un {d}%, de {pw} a {tw} unidades.",
            "units_flat": "Las unidades se mantuvieron estables ({tw} vs {pw} la semana anterior).",
        "units_down": "Las unidades bajaron un {d}%, de {pw} a {tw} unidades.",
        "sess_up":    "El tr\u00e1fico aument\u00f3 un {d}%, se\u00f1al positiva de visibilidad org\u00e1nica y/o ads.",
        "sess_down":  "El tr\u00e1fico cay\u00f3 un {d}%. Revisar ranking org\u00e1nico y presupuesto de campa\u00f1as.",
        "sess_up_neutro": "El tráfico aumentó un {d}%.",
        "sess_up_cvr_down": ("El tráfico aumentó un {d}% pero la conversión cayó: entró más gente y compró una proporción menor. Revisar calidad del tráfico (términos de búsqueda y targeting de campañas) y el listing antes de sumar más presupuesto."),
        "sess_down_cvr_up": ("El tráfico cayó un {d}%, pero la conversión mejoró: menos visitas y mejor calificadas. Revisar ranking orgánico y presupuesto para recuperar volumen sin perder esa calidad."),
        "cvr_up":     "La tasa de conversi\u00f3n mejor\u00f3 a {tw}% (anterior: {pw}%).",
        "cvr_down":   "La tasa de conversi\u00f3n baj\u00f3 a {tw}% (anterior: {pw}%). Revisar listing y precio.",
            "cvr_down_ya_visto": "La tasa de conversión bajó a {tw}% (anterior: {pw}%) — ver el punto anterior sobre calidad del tráfico.",
        "acos_ok":    "ACoS global en {v}% \u2014 dentro del rango objetivo.",
        "acos_warn":  "ACoS global en {v}% \u2014 por encima del objetivo. Revisar bids.",
        "tacos_line": "TACoS: {v}%",
        "bb_warn":    "\u26a0\ufe0f {asin}: BuyBox en {bb}% \u2014 acci\u00f3n requerida.",
        "bb_ok":      "BuyBox promedio en {bb}% \u2014 saludable.",
        "conclusion": "{trend}. Recomendaci\u00f3n: {action}",
        "trend_pos": "Semana positiva", "trend_neg": "Semana con \u00e1reas de mejora", "trend_flat": "Semana estable",
        "act_pos": "mantener estrategia y escalar campa\u00f1as top.",
        "act_neg": "revisar keywords de bajo rendimiento, ajustar bids y verificar stock.",
        "act_flat": "monitorear conversi\u00f3n y explorar nuevas keywords.",
    },
    "en": {
        "title_wow": "Weekly WoW Report", "product": "Product", "asin": "ASIN",
        "tw": "This Week", "pw": "Prior Week", "delta": "Change %",
        "full_period": "Full period ({days}d)", "full_period_nodays": "Full period",
            "warn_full": ("⚠️ No weekly comparison per product ({days}d of data). "
                          "Per-ASIN amounts cover the full period. The account's "
                      "weekly comparison is in the Executive Report sheet."),
        "note": "* ACoS = Ad Spend / Ad Sales  |  TACoS = Ad Spend / Total Sales  |  \u2014 = not available",
        "exec_title": "WEEKLY EXECUTIVE SUMMARY", "generated": "Generated by Capybaras Agency PPC Manager",
        "intro": "Week-over-week (WoW) performance comparison for Amazon:",
        "sec_sales": "TOTAL SALES", "sec_traffic": "TRAFFIC & CONVERSION",
        "exec_no_weekly": ("Without the daily BR there is no weekly account comparison. "
                           "Per-product amounts cover the full period of the uploaded file."),
        "sec_ads": "ADVERTISING", "sec_bb": "BUY BOX", "sec_conclusion": "CONCLUSION",
        "sales_up":   "Total sales increased by {d}%, from MX${pw} to MX${tw}.",
        "sales_down": "Total sales dropped by {d}%, from MX${pw} to MX${tw}.",
        "sales_flat": "Total sales remained stable (MX${tw}).",
        "units_up":   "Units sold grew by {d}%, from {pw} to {tw} units.",
            "units_flat": "Units held steady ({tw} vs {pw} the prior week).",
        "units_down": "Units sold dropped by {d}%, from {pw} to {tw} units.",
        "sess_up":    "Traffic increased by {d}%, a positive visibility signal.",
        "sess_down":  "Traffic dropped by {d}%. Review organic ranking and campaign budgets.",
        "sess_up_neutro": "Traffic increased by {d}%.",
        "sess_up_cvr_down": ("Traffic increased by {d}% but conversion dropped: more visitors bought at a lower rate. Review traffic quality (search terms and campaign targeting) and the listing before adding budget."),
        "sess_down_cvr_up": ("Traffic dropped by {d}%, but conversion improved: fewer, better qualified visits. Review organic ranking and budget to recover volume without losing that quality."),
        "cvr_up":     "Conversion rate improved to {tw}% (prior: {pw}%).",
        "cvr_down":   "Conversion rate dropped to {tw}% (prior: {pw}%). Review listing and pricing.",
            "cvr_down_ya_visto": "Conversion rate dropped to {tw}% (prior: {pw}%) — see the traffic quality note above.",
        "acos_ok":    "Global ACoS at {v}% \u2014 within target range.",
        "acos_warn":  "Global ACoS at {v}% \u2014 above target. Review bids.",
        "tacos_line": "TACoS: {v}%",
        "bb_warn":    "\u26a0\ufe0f {asin}: BuyBox at {bb}% \u2014 action required.",
        "bb_ok":      "Average BuyBox at {bb}% \u2014 healthy.",
        "conclusion": "{trend}. Recommended action: {action}",
        "trend_pos": "Positive week", "trend_neg": "Mixed week", "trend_flat": "Stable week",
        "act_pos": "maintain current strategy and scale top campaigns.",
        "act_neg": "review low-performing keywords, adjust bids, and check stock.",
        "act_flat": "monitor conversion metrics and explore new keywords.",
    },
}

def _build_weekly_excel(br_tw, br_pw, atom_tw, atom_pw, client_name="", lang="es", br_daily=None, camp_data=None, changelog_text="",
                        period_child_tw=None, period_child_pw=None):
    """
    period_child_tw / period_child_pw: periodo DECLARADO de los archivos by-Child.

    El export by-Child de Amazon no trae columna de fecha (es un agregado del
    rango pedido), asi que su periodo se declara desde afuera. Solo con dos
    periodos de 7 dias exactos el reporte entra en MODO WOW y puede rotular una
    columna "Esta semana"; en cualquier otro caso degrada a MODO PERIODO COMPLETO
    y lo dice explicitamente. Una misma columna nunca mezcla periodos.
    """
    NAVY="0D1B3E"; WHITE="FFFFFF"; LGRAY="F7FAFC"; DGRAY="2D3748"; MGRAY="CBD5E0"
    GRN_L="C6EFCE"; GRN_D="276221"; RED_L="FFC7CE"; RED_D="9C0006"
    YEL_L="FFEB9C"; YEL_D="9C5700"; ORG_L="FFE0B2"; ORG_D="BF360C"
    BLUE_L="DBEAFE"; BLUE_D="1E3A8A"

    def _fill(c): return PatternFill("solid", fgColor=c)
    def _font(bold=False, color="000000", size=9, name="Arial"):
        return Font(bold=bold, color=color, size=size, name=name)
    def _bd():
        s = Side(style="thin", color=MGRAY)
        return Border(left=s, right=s, top=s, bottom=s)
    def _al(h="center", v="center", wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)
    def _cell(ws, r, c, val, bg=None, fg="000000", bold=False, fmt=None, size=9, left=False):
        cell = ws.cell(row=r, column=c, value=val)
        if bg: cell.fill = _fill(bg)
        cell.font = _font(bold=bold, color=fg, size=size)
        cell.alignment = _al("left" if left else "center")
        cell.border = _bd()
        if fmt: cell.number_format = fmt
        return cell
    def _pct(tw, pw):
        try:
            if not pw or float(pw) == 0: return None
            return (float(tw) - float(pw)) / float(pw) * 100
        except: return None
    def _delta_bg(val):
        if val is None: return None, "000000"
        if val > 5:   return GRN_L, GRN_D
        if val < -5:  return RED_L, RED_D
        return YEL_L, YEL_D
    def _hdr(ws, rn, cols, h=14):
        for i, col in enumerate(cols, 1):
            c = ws.cell(row=rn, column=i, value=col)
            c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 8)
            c.alignment = _al(); c.border = _bd()
        ws.row_dimensions[rn].height = h
    def _sec(ws, rn, text, ncols, bg=DGRAY, fg=WHITE, h=16):
        ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=ncols)
        c = ws.cell(row=rn, column=1, value=text)
        c.fill = _fill(bg); c.font = _font(True, fg, 10)
        c.alignment = _al("left"); c.border = _bd()
        ws.row_dimensions[rn].height = h
        return rn + 1

    L = _L_EXEC
    t = L.get(lang, L["es"])

    # ── Contrato de periodo ───────────────────────────────────────────────────
    # MODO WOW exige DOS periodos declarados de 7 dias exactos en los by-Child.
    # Cualquier otra cosa es MODO PERIODO COMPLETO y se rotula como tal.
    modo_wow = _es_modo_wow(period_child_tw, period_child_pw)

    # Dias que respaldan las columnas de producto, para rotularlas con la verdad.
    if period_child_tw and period_child_tw.get("days"):
        _dias_full = period_child_tw["days"]
    elif br_daily:
        _dias_full = sum(
            (br_daily.get(k) or {}).get("days", 0) for k in ("period_tw", "period_pw")
        ) or None
    else:
        _dias_full = None
    lbl_full = (
        t["full_period"].format(days=_dias_full) if _dias_full else t["full_period_nodays"]
    )

    # El MODO manda tambien sobre los VALORES, no solo sobre los rotulos. Antes
    # `has_pw = bool(br_pw)` decidia en paralelo a `modo_wow`, y dos by-Child sin
    # BR diario producian montos PW y deltas debajo de columnas rotuladas "—":
    # el error de la deuda #24 espejado. Si el modo dice que no hay comparacion
    # semanal, no se escribe ninguna, venga br_pw lleno o vacio.
    has_pw = modo_wow and bool(br_pw)
    # `all_asins` respeta has_pw: si el PW no se usa, tampoco aporta ASINs. Sin
    # esto, un ASIN que solo existia en el archivo descartado generaba una fila
    # entera de MX$0,00 / 0 / — diciendo que ese producto vendio cero.
    all_asins = sorted(set(br_tw) | (set(br_pw) if has_pw else set()))
    rows_data = []
    for asin in all_asins:
        tw = br_tw.get(asin, {}); pw = br_pw.get(asin, {})
        at = atom_tw.get(asin, {}) if atom_tw else {}
        title    = tw.get("Title") or pw.get("Title") or asin
        sales_tw = tw.get("Sales", 0);    sales_pw = pw.get("Sales", 0)    if has_pw else None
        units_tw = tw.get("Units", 0);    units_pw = pw.get("Units", 0)    if has_pw else None
        sess_tw  = tw.get("Sessions", 0); sess_pw  = pw.get("Sessions", 0) if has_pw else None
        cvr_tw   = tw.get("CVR", 0);      cvr_pw   = pw.get("CVR", 0)      if has_pw else None
        bb       = tw.get("BuyBox")
        ad_sales_tw = at.get("Sales_TW", 0); ad_sales_pw = at.get("Sales_PW", 0)
        ad_spend_tw = at.get("Spend_TW", 0); ad_spend_pw = at.get("Spend_PW", 0)
        acos  = (ad_spend_tw / ad_sales_tw * 100) if ad_sales_tw > 0 else None
        # TACoS por producto solo en MODO WOW: el numerador (Atom 11) es siempre de
        # 7d, pero el denominador (by-Child) solo lo es cuando el periodo lo declara.
        # Fuera de MODO WOW seria 7d de gasto sobre 14d de venta -> no significa nada.
        tacos = (ad_spend_tw / sales_tw * 100) if (modo_wow and sales_tw > 0 and ad_spend_tw > 0) else None
        rows_data.append({
            "asin": asin, "title": title,
            "sales_tw": sales_tw, "sales_pw": sales_pw, "sales_d": _pct(sales_tw, sales_pw) if has_pw else None,
            "units_tw": units_tw, "units_pw": units_pw, "units_d": _pct(units_tw, units_pw) if has_pw else None,
            "sess_tw": sess_tw,   "sess_pw": sess_pw,   "sess_d":  _pct(sess_tw, sess_pw)   if has_pw else None,
            "cvr_tw": cvr_tw,     "cvr_pw": cvr_pw,     "cvr_d":   _pct(cvr_tw, cvr_pw)     if has_pw else None,
            "bb": bb,
            "ad_sales_tw": ad_sales_tw, "ad_sales_pw": ad_sales_pw, "ad_sales_d": _pct(ad_sales_tw, ad_sales_pw),
            "ad_spend_tw": ad_spend_tw, "ad_spend_pw": ad_spend_pw, "ad_spend_d": _pct(ad_spend_tw, ad_spend_pw),
            "acos": acos, "tacos": tacos,
        })

    wb_out = Workbook()
    wb_out.remove(wb_out.active)

    # ── SHEET 1: WoW Comparison ──────────────────────────────
    ws1 = wb_out.create_sheet("\U0001f4c8 WoW Comparison")
    ws1.sheet_view.showGridLines = False
    WOW_GROUPS = [
        ("SALES",    False, [t["tw"], t["pw"], t["delta"]]),
        ("UNITS",    False, [t["tw"], t["pw"], t["delta"]]),
        ("SESSIONS", False, [t["tw"], t["pw"], t["delta"]]),
        ("CVR",      False, [t["tw"], t["pw"], t["delta"]]),
        ("BUY BOX",  False, [t["tw"]]),
        ("AD SALES", True,  [t["tw"], t["pw"], t["delta"]]),
        ("AD SPEND", True,  [t["tw"], t["pw"], t["delta"]]),
        ("ACoS",     True,  [t["tw"]]),
        ("TACoS",    True,  [t["tw"]]),
    ]
    total_cols = 2 + sum(len(g[2]) for g in WOW_GROUPS)

    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    _suf = _sufijo_periodo(modo_wow, period_child_tw, period_child_pw, br_daily, t, lang)
    c = ws1.cell(row=1, column=1, value=f"{client_name} — {t['title_wow']}{_suf}")
    c.fill = _fill(NAVY); c.font = _font(True, WHITE, 14)
    c.alignment = _al("left"); c.border = _bd()
    ws1.row_dimensions[1].height = 28

    for ci_fix, lbl in ((1, t["product"]), (2, t["asin"])):
        c = ws1.cell(row=2, column=ci_fix, value=lbl)
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 9)
        c.alignment = _al(); c.border = _bd()
    ws1.row_dimensions[2].height = 16

    ci = 3
    for grp_name, is_orange, subs in WOW_GROUPS:
        span = len(subs)
        bg_g = ORG_L if is_orange else DGRAY
        fg_g = ORG_D if is_orange else WHITE
        if span > 1:
            ws1.merge_cells(start_row=2, start_column=ci, end_row=2, end_column=ci + span - 1)
        c = ws1.cell(row=2, column=ci, value=grp_name)
        c.fill = _fill(bg_g); c.font = _font(True, fg_g, 9)
        c.alignment = _al(); c.border = _bd()
        ci += span

    ws1.row_dimensions[3].height = 14
    sub_hdrs = [t["product"], t["asin"]]
    # Fuera de MODO WOW, las 4 metricas que salen del by-Child no pueden decir
    # "Esta semana": llevan el periodo completo. AD SALES y AD SPEND vienen de
    # Atom 11, que si trae desglose diario, asi que conservan su WoW.
    _grupos_by_child = {"SALES", "UNITS", "SESSIONS", "CVR"}
    for grp_name, _, subs in WOW_GROUPS:
        if not modo_wow and grp_name in _grupos_by_child:
            sub_hdrs.extend([lbl_full] + ["—"] * (len(subs) - 1))
        else:
            sub_hdrs.extend(subs)
    for ci, h in enumerate(sub_hdrs, 1):
        c = ws1.cell(row=3, column=ci, value=h)
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 8)
        c.alignment = _al(); c.border = _bd()

    offset = 0
    BLUE_L_TOT = "DBEAFE"; BLUE_D_TOT = "1E3A8A"
    if br_daily:
        offset = 1
        rn = 4; ws1.row_dimensions[rn].height = 18
        bd = br_daily

        def _tot(col_i, val, fmt=None, bg_ov=None, fg_ov=None, bold=True):
            bg = bg_ov or BLUE_L_TOT; fg = fg_ov or BLUE_D_TOT
            _cell(ws1, rn, col_i, val, bg=bg, fg=fg, bold=bold, fmt=fmt)

        def _tot_delta(col_i, val, inv=False):
            if val is None: _cell(ws1, rn, col_i, "\u2014", bg=BLUE_L_TOT, fg=BLUE_D_TOT); return
            bg_d, fg_d = _delta_bg(-val if inv else val)
            _cell(ws1, rn, col_i, round(val, 1), bg=bg_d, fg=fg_d, fmt="0.0", bold=True)

        ws1.cell(rn, 1).value = "\u25b6 CUENTA TOTAL"
        for ci_t in range(1, 3):
            ws1.cell(rn, ci_t).fill = _fill(BLUE_L_TOT)
            ws1.cell(rn, ci_t).font = _font(True, BLUE_D_TOT, 9)
            ws1.cell(rn, ci_t).alignment = _al("left" if ci_t == 1 else "center")
            ws1.cell(rn, ci_t).border = _bd()
        ws1.cell(rn, 2).value = "\u2014"

        if modo_wow:
            _tot(3,  bd["Sales_TW"],    '"MX$"#,##0.00')
            _tot(4,  bd["Sales_PW"],    '"MX$"#,##0.00')
            _tot_delta(5, _pct(bd["Sales_TW"], bd["Sales_PW"]))
            _tot(6,  bd["Units_TW"],    "#,##0")
            _tot(7,  bd["Units_PW"],    "#,##0")
            _tot_delta(8, _pct(bd["Units_TW"], bd["Units_PW"]))
            _tot(9,  bd["Sessions_TW"], "#,##0")
            _tot(10, bd["Sessions_PW"], "#,##0")
            _tot_delta(11, _pct(bd["Sessions_TW"], bd["Sessions_PW"]))
            _tot(12, bd["CVR_TW"],      '0.00')
            _tot(13, bd["CVR_PW"],      '0.00')
            _tot_delta(14, _pct(bd["CVR_TW"], bd["CVR_PW"]))
        else:
            # Los productos de esta columna van al periodo completo, asi que la
            # cuenta tambien: una columna nunca mezcla periodos. Sin esto la fila
            # CUENTA TOTAL quedaria en 7d contra productos en 14d — el bug original.
            _sales_full = bd["Sales_TW"] + bd["Sales_PW"]
            _units_full = bd["Units_TW"] + bd["Units_PW"]
            _sess_full  = bd["Sessions_TW"] + bd["Sessions_PW"]
            # CVR del agregado: cociente de los totales, NO el promedio de los dos
            # CVR semanales (ponderaria mal si las semanas tienen distinto trafico).
            _cvr_full = (_units_full / _sess_full * 100) if _sess_full > 0 else None

            _tot(3,  _sales_full, '"MX$"#,##0.00')
            _tot(4,  "—")
            _tot(5,  "—")
            _tot(6,  _units_full, "#,##0")
            _tot(7,  "—")
            _tot(8,  "—")
            _tot(9,  _sess_full,  "#,##0")
            _tot(10, "—")
            _tot(11, "—")
            _tot(12, _cvr_full if _cvr_full is not None else "—", '0.00' if _cvr_full is not None else None)
            _tot(13, "—")
            _tot(14, "—")
        bb_tot = bd["BuyBox_TW"]
        if bb_tot is not None:
            bg_bb = GRN_L if bb_tot >= 99 else (YEL_L if bb_tot >= 95 else RED_L)
            fg_bb = GRN_D if bb_tot >= 99 else (YEL_D if bb_tot >= 95 else RED_D)
            _cell(ws1, rn, 15, bb_tot, bg=bg_bb, fg=fg_bb, fmt='0.0', bold=True)
        else:
            _cell(ws1, rn, 15, "\u2014", bg=BLUE_L_TOT, fg=BLUE_D_TOT)

        atom_adsal_tw = sum(v.get("Sales_TW", 0) for v in (atom_tw or {}).values())
        atom_adsal_pw = sum(v.get("Sales_PW", 0) for v in (atom_tw or {}).values())
        atom_adsp_tw  = sum(v.get("Spend_TW", 0) for v in (atom_tw or {}).values())
        atom_adsp_pw  = sum(v.get("Spend_PW", 0) for v in (atom_tw or {}).values())
        _tot(16, round(atom_adsal_tw, 2), '"MX$"#,##0.00')
        _tot(17, round(atom_adsal_pw, 2), '"MX$"#,##0.00')
        _tot_delta(18, _pct(atom_adsal_tw, atom_adsal_pw))
        _tot(19, round(atom_adsp_tw, 2),  '"MX$"#,##0.00')
        _tot(20, round(atom_adsp_pw, 2),  '"MX$"#,##0.00')
        _tot_delta(21, _pct(atom_adsp_tw, atom_adsp_pw))
        g_acos  = (atom_adsp_tw / atom_adsal_tw * 100) if atom_adsal_tw > 0 else None
        g_tacos = (atom_adsp_tw / bd["Sales_TW"] * 100) if bd["Sales_TW"] > 0 and atom_adsp_tw > 0 else None
        if g_acos is not None:
            bg_a = GRN_L if g_acos < 30 else (YEL_L if g_acos < 60 else RED_L)
            fg_a = GRN_D if g_acos < 30 else (YEL_D if g_acos < 60 else RED_D)
            _cell(ws1, rn, 22, round(g_acos, 1), bg=bg_a, fg=fg_a, fmt="0.0", bold=True)
        else:
            _cell(ws1, rn, 22, "\u2014", bg=BLUE_L_TOT, fg=BLUE_D_TOT)
        if g_tacos is not None:
            bg_t = GRN_L if g_tacos < 15 else (YEL_L if g_tacos < 25 else RED_L)
            fg_t = GRN_D if g_tacos < 15 else (YEL_D if g_tacos < 25 else RED_D)
            _cell(ws1, rn, 23, round(g_tacos, 1), bg=bg_t, fg=fg_t, fmt="0.0", bold=True)
        else:
            _cell(ws1, rn, 23, "\u2014", bg=BLUE_L_TOT, fg=BLUE_D_TOT)

    for ri, row in enumerate(rows_data):
        rn = 4 + offset + ri
        ws1.row_dimensions[rn].height = 16
        row_bg = WHITE if ri % 2 == 0 else LGRAY

        def dc(col_i, val, fmt=None, is_delta=False, left=False, no_data=False):
            if no_data or val is None:
                _cell(ws1, rn, col_i, "\u2014", bg=row_bg, left=left); return
            if is_delta and isinstance(val, float):
                bg_d, fg_d = _delta_bg(val)
                _cell(ws1, rn, col_i, val, bg=bg_d, fg=fg_d, fmt=fmt or "0.0")
            else:
                _cell(ws1, rn, col_i, val, bg=row_bg, fmt=fmt, left=left)

        no_sess = (row["sess_tw"] == 0 and (row["sess_pw"] is None or row["sess_pw"] == 0))
        no_cvr  = (row["cvr_tw"]  == 0 and (row["cvr_pw"]  is None or row["cvr_pw"]  == 0))
        no_ads  = (row["ad_sales_tw"] == 0 and row["ad_sales_pw"] == 0
                   and row["ad_spend_tw"] == 0 and row["ad_spend_pw"] == 0)

        dc(1,  row["title"],     left=True)
        dc(2,  row["asin"],      left=True)
        dc(3,  row["sales_tw"],  '"MX$"#,##0.00')
        dc(4,  row["sales_pw"],  '"MX$"#,##0.00', no_data=row["sales_pw"] is None)
        dc(5,  row["sales_d"],   "0.0", is_delta=True, no_data=row["sales_d"] is None)
        dc(6,  row["units_tw"],  "#,##0")
        dc(7,  row["units_pw"],  "#,##0", no_data=row["units_pw"] is None)
        dc(8,  row["units_d"],   "0.0", is_delta=True, no_data=row["units_d"] is None)
        dc(9,  row["sess_tw"],   "#,##0", no_data=no_sess)
        dc(10, row["sess_pw"],   "#,##0", no_data=no_sess)
        dc(11, row["sess_d"],    "0.0", is_delta=True, no_data=(no_sess or row["sess_d"] is None))
        dc(12, row["cvr_tw"],    '0.00', no_data=no_cvr)
        dc(13, row["cvr_pw"],    '0.00', no_data=no_cvr)
        dc(14, row["cvr_d"],     "0.0", is_delta=True, no_data=(no_cvr or row["cvr_d"] is None))
        bb_v = row["bb"]
        if bb_v is not None:
            bg_bb = GRN_L if bb_v >= 99 else (YEL_L if bb_v >= 95 else RED_L)
            fg_bb = GRN_D if bb_v >= 99 else (YEL_D if bb_v >= 95 else RED_D)
            _cell(ws1, rn, 15, bb_v, bg=bg_bb, fg=fg_bb, fmt='0.00')
        else:
            dc(15, None)
        dc(16, row["ad_sales_tw"], '"MX$"#,##0.00', no_data=no_ads)
        dc(17, row["ad_sales_pw"], '"MX$"#,##0.00', no_data=no_ads)
        dc(18, row["ad_sales_d"],  "0.0", is_delta=True, no_data=(no_ads or row["ad_sales_d"] is None))
        dc(19, row["ad_spend_tw"], '"MX$"#,##0.00', no_data=no_ads)
        dc(20, row["ad_spend_pw"], '"MX$"#,##0.00', no_data=no_ads)
        dc(21, row["ad_spend_d"],  "0.0", is_delta=True, no_data=(no_ads or row["ad_spend_d"] is None))
        if row["acos"] is not None:
            bg_a = GRN_L if row["acos"] < 30 else (YEL_L if row["acos"] < 60 else RED_L)
            fg_a = GRN_D if row["acos"] < 30 else (YEL_D if row["acos"] < 60 else RED_D)
            _cell(ws1, rn, 22, round(row["acos"], 1), bg=bg_a, fg=fg_a, fmt="0.0")
        else:
            dc(22, None)
        if row["tacos"] is not None:
            bg_t = GRN_L if row["tacos"] < 15 else (YEL_L if row["tacos"] < 25 else RED_L)
            fg_t = GRN_D if row["tacos"] < 15 else (YEL_D if row["tacos"] < 25 else RED_D)
            _cell(ws1, rn, 23, round(row["tacos"], 1), bg=bg_t, fg=fg_t, fmt="0.0")
        else:
            dc(23, None)

    note_rn = 4 + offset + len(rows_data) + 1
    ws1.merge_cells(start_row=note_rn, start_column=1, end_row=note_rn, end_column=total_cols)
    nc = ws1.cell(row=note_rn, column=1, value=t["note"])
    nc.fill = _fill(YEL_L); nc.font = _font(False, YEL_D, 8)
    nc.alignment = _al("left"); nc.border = _bd()
    ws1.row_dimensions[note_rn].height = 14

    # Banda de aviso del modo degradado. Va DEBAJO de la nota y no arriba del
    # titulo a proposito: insertarla en la fila 2 correria todas las filas fijas
    # de esta hoja (headers 1-3, CUENTA TOTAL en 4, datos en 4+offset, freeze
    # panes "C4"), que es la parte mas fragil de la funcion.
    if not modo_wow:
        warn_rn = note_rn + 1
        ws1.merge_cells(start_row=warn_rn, start_column=1, end_row=warn_rn, end_column=total_cols)
        wc = ws1.cell(row=warn_rn, column=1, value=t["warn_full"].format(days=_dias_full or "?"))
        wc.fill = _fill(YEL_L); wc.font = _font(True, YEL_D, 9)
        wc.alignment = _al("left"); wc.border = _bd()
        ws1.row_dimensions[warn_rn].height = 28
    ws1.column_dimensions["A"].width = 40
    ws1.column_dimensions["B"].width = 14
    for ci_w in range(3, total_cols + 1):
        ws1.column_dimensions[get_column_letter(ci_w)].width = 12
    ws1.freeze_panes = "C4"

    # ── SHEET 2: Advertising ──────────────────────────────────
    ws_ad = wb_out.create_sheet("\U0001f4e3 Advertising")
    ws_ad.sheet_view.showGridLines = False
    if camp_data:
        ct = camp_data["totals"]
        AD_COLS = 8
        # Title
        ws_ad.merge_cells(start_row=1, start_column=1, end_row=1, end_column=AD_COLS)
        c = ws_ad.cell(row=1, column=1, value=f"{client_name} — Advertising Overview")
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 14)
        c.alignment = _al("left"); c.border = _bd()
        ws_ad.row_dimensions[1].height = 28

        # KPI cards row
        ad_kpis = [
            ("Impressions", f"{ct['Impressions']:,.0f}"),
            ("Clicks", f"{ct['Clicks']:,.0f}"),
            ("CTR", f"{ct['CTR']:.2f}%"),
            ("CPC", f"${ct['CPC']:.2f}"),
            ("Spend", f"${ct['Spend']:,.2f}"),
            ("Sales", f"${ct['Sales']:,.2f}"),
            ("ACoS", f"{ct['ACoS']:.1f}%"),
            ("Orders", f"{ct['Orders']:,.0f}"),
        ]
        for ki, (kn, kv) in enumerate(ad_kpis, 1):
            _cell(ws_ad, 2, ki, kn, bg=DGRAY, fg=WHITE, bold=True, size=8)
            _cell(ws_ad, 3, ki, kv, bg=LGRAY, bold=True, size=9)
        ws_ad.row_dimensions[2].height = 14
        ws_ad.row_dimensions[3].height = 18

        # NTB row if available
        ad_rn = 4
        if ct.get("NTB_Orders", 0) > 0 or ct.get("DPV", 0) > 0:
            ws_ad.merge_cells(start_row=ad_rn, start_column=1, end_row=ad_rn, end_column=AD_COLS)
            ntb_txt = []
            if ct["DPV"] > 0: ntb_txt.append(f"DPV: {ct['DPV']:,.0f}")
            if ct["NTB_Orders"] > 0: ntb_txt.append(f"NTB Orders: {ct['NTB_Orders']:,.0f} ({ct['NTB_Pct']:.1f}%)")
            if ct["NTB_Sales"] > 0: ntb_txt.append(f"NTB Sales: ${ct['NTB_Sales']:,.2f}")
            c = ws_ad.cell(row=ad_rn, column=1, value="  ".join(ntb_txt))
            c.fill = _fill(BLUE_L); c.font = _font(True, BLUE_D, 9)
            c.alignment = _al("left"); c.border = _bd()
            ad_rn += 1

        # Top campaigns
        ad_rn += 1
        camps = camp_data.get("campaigns", [])
        if camps:
            ad_rn = _sec(ws_ad, ad_rn, f"TOP {len(camps)} CAMPAIGNS BY SPEND", AD_COLS, bg=ORG_L, fg=ORG_D)
            camp_hdrs = ["Campaign", "Impressions", "Clicks", "CTR%", "Spend", "Sales", "ACoS%", "Orders"]
            _hdr(ws_ad, ad_rn, camp_hdrs)
            ad_rn += 1
            for ci_c, camp in enumerate(camps):
                row_bg = WHITE if ci_c % 2 == 0 else LGRAY
                _cell(ws_ad, ad_rn, 1, camp["Campaign"], bg=row_bg, left=True)
                _cell(ws_ad, ad_rn, 2, camp["Impressions"], bg=row_bg, fmt="#,##0")
                _cell(ws_ad, ad_rn, 3, camp["Clicks"], bg=row_bg, fmt="#,##0")
                _cell(ws_ad, ad_rn, 4, camp["CTR"], bg=row_bg, fmt="0.00")
                _cell(ws_ad, ad_rn, 5, camp["Spend"], bg=row_bg, fmt='"$"#,##0.00')
                _cell(ws_ad, ad_rn, 6, camp["Sales"], bg=row_bg, fmt='"$"#,##0.00')
                acos_v = camp["ACoS"]
                bg_a = GRN_L if acos_v < 30 else (YEL_L if acos_v < 60 else RED_L)
                fg_a = GRN_D if acos_v < 30 else (YEL_D if acos_v < 60 else RED_D)
                _cell(ws_ad, ad_rn, 7, acos_v, bg=bg_a, fg=fg_a, fmt="0.0")
                _cell(ws_ad, ad_rn, 8, camp["Orders"], bg=row_bg, fmt="#,##0")
                ws_ad.row_dimensions[ad_rn].height = 16
                ad_rn += 1

            # Alarmas ACoS > 60%
            alarm_camps = [c for c in camps if c["ACoS"] > 60 and c["Spend"] > 0]
            if alarm_camps:
                ad_rn += 1
                ad_rn = _sec(ws_ad, ad_rn, f"\u26a0\ufe0f ALARMAS — {len(alarm_camps)} CAMPAÑAS CON ACoS > 60%", AD_COLS, bg=RED_L, fg=RED_D)
                for ac in alarm_camps:
                    ws_ad.merge_cells(start_row=ad_rn, start_column=1, end_row=ad_rn, end_column=AD_COLS)
                    c = ws_ad.cell(row=ad_rn, column=1,
                                   value=f"  {ac['Campaign']} — ACoS {ac['ACoS']:.1f}% | Spend ${ac['Spend']:,.2f} | Sales ${ac['Sales']:,.2f}")
                    c.fill = _fill(RED_L); c.font = _font(False, RED_D, 9)
                    c.alignment = _al("left"); c.border = _bd()
                    ws_ad.row_dimensions[ad_rn].height = 16
                    ad_rn += 1

        # Portfolios
        ports = camp_data.get("portfolios", [])
        if ports:
            ad_rn += 1
            ad_rn = _sec(ws_ad, ad_rn, "PORTFOLIOS", AD_COLS, bg=DGRAY, fg=WHITE)
            port_hdrs = ["Portfolio", "Spend", "Sales", "ACoS%", "", "", "", ""]
            _hdr(ws_ad, ad_rn, port_hdrs)
            ad_rn += 1
            for pi, port in enumerate(ports):
                row_bg = WHITE if pi % 2 == 0 else LGRAY
                _cell(ws_ad, ad_rn, 1, port["Portfolio"], bg=row_bg, left=True)
                _cell(ws_ad, ad_rn, 2, port["Spend"], bg=row_bg, fmt='"$"#,##0.00')
                _cell(ws_ad, ad_rn, 3, port["Sales"], bg=row_bg, fmt='"$"#,##0.00')
                pa = port["ACoS"]
                bg_p = GRN_L if pa < 30 else (YEL_L if pa < 60 else RED_L)
                fg_p = GRN_D if pa < 30 else (YEL_D if pa < 60 else RED_D)
                _cell(ws_ad, ad_rn, 4, pa, bg=bg_p, fg=fg_p, fmt="0.0")
                ws_ad.row_dimensions[ad_rn].height = 16
                ad_rn += 1

        ws_ad.column_dimensions["A"].width = 50
        for ci_w in range(2, AD_COLS + 1):
            ws_ad.column_dimensions[get_column_letter(ci_w)].width = 14
    else:
        # No campaign data — show placeholder
        ws_ad.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
        c = ws_ad.cell(row=1, column=1, value="⚠️ No se cargó Campaign CSV — sube el archivo para ver métricas de Advertising")
        c.fill = _fill(YEL_L); c.font = _font(True, YEL_D, 11)
        c.alignment = _al("left"); c.border = _bd()
        ws_ad.column_dimensions["A"].width = 80

    # ── SHEET 3: Reporte Ejecutivo ───────────────────────────
    ws2 = wb_out.create_sheet("\U0001f4cb Reporte Ejecutivo")
    ws2.sheet_view.showGridLines = False
    ws2.column_dimensions["A"].width = 80

    def _erow(rn, text, bg=None, fg="000000", bold=False, size=10, h=18, wrap=True):
        ws2.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=6)
        c = ws2.cell(row=rn, column=1, value=text)
        if bg: c.fill = _fill(bg)
        c.font = _font(bold=bold, color=fg, size=size)
        c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=wrap)
        c.border = _bd()
        ws2.row_dimensions[rn].height = h
        return rn + 1

    # Totales de cuenta del ejecutivo. Solo son SEMANALES si hay BR diario (7d por
    # construccion) o si estamos en MODO WOW (las filas de producto son de 7d
    # declarados). Sin ninguna de las dos, sumar filas de periodo DESCONOCIDO y
    # presentarlas como "esta semana" es el bug original entrando de costado.
    if br_daily:
        totales_semanales = True
        ts_tw = br_daily["Sales_TW"];    ts_pw = br_daily["Sales_PW"]
        tu_tw = br_daily["Units_TW"];    tu_pw = br_daily["Units_PW"]
        tse_tw = br_daily["Sessions_TW"]; tse_pw = br_daily["Sessions_PW"]
        # `CVR_TW`/`CVR_PW` ya vienen ponderados por sesiones desde el parser
        # (_parse_br_daily_wow). Recalcularlos aca seria una segunda forma de
        # obtener el mismo numero, que es como el defecto sobrevivio dos fases.
        avg_cvr_tw = br_daily["CVR_TW"]; avg_cvr_pw = br_daily["CVR_PW"]
    elif modo_wow:
        totales_semanales = True
        ts_tw = sum(r["sales_tw"] for r in rows_data)
        ts_pw = sum(r["sales_pw"] or 0 for r in rows_data)
        tu_tw = sum(r["units_tw"] for r in rows_data)
        tu_pw = sum(r["units_pw"] or 0 for r in rows_data)
        tse_tw = sum(r["sess_tw"] for r in rows_data)
        tse_pw = sum(r["sess_pw"] or 0 for r in rows_data)
        # CVR PONDERADO por sesiones, no promedio simple por ASIN: con el promedio
        # simple un ASIN de 3 sesiones pesaba igual que uno de 500.
        avg_cvr_tw = (tu_tw / tse_tw * 100) if tse_tw > 0 else 0
        avg_cvr_pw = (tu_pw / tse_pw * 100) if tse_pw > 0 else 0
    else:
        totales_semanales = False
        ts_tw = ts_pw = tu_tw = tu_pw = tse_tw = tse_pw = 0
        avg_cvr_tw = avg_cvr_pw = 0

    tsp_tw = sum(r["ad_spend_tw"] for r in rows_data)
    tad_tw = sum(r["ad_sales_tw"] for r in rows_data)
    g_acos  = (tsp_tw / tad_tw * 100) if tad_tw > 0 else None
    g_tacos = (tsp_tw / ts_tw * 100)   if ts_tw > 0 and tsp_tw > 0 else None
    s_d  = _pct(ts_tw, ts_pw)   if ts_pw  else None
    u_d  = _pct(tu_tw, tu_pw)   if tu_pw  else None
    se_d = _pct(tse_tw, tse_pw) if tse_pw else None
    cvr_d = _pct(avg_cvr_tw, avg_cvr_pw) if avg_cvr_pw else None

    _trend = _trend_ejecutivo(s_d, u_d, se_d)
    trend, action = {
        "pos":  (t["trend_pos"],  t["act_pos"]),
        "neg":  (t["trend_neg"],  t["act_neg"]),
        "flat": (t["trend_flat"], t["act_flat"]),
    }[_trend]

    cur = 1
    cur = _erow(cur, f'{t["exec_title"]}{_suf}', bg=NAVY, fg=WHITE, bold=True, size=14, h=30)
    cur = _erow(cur, t["generated"],     bg=DGRAY,  fg=WHITE, size=8,  h=14)
    cur = _erow(cur, f"  {client_name}", bg=BLUE_L, fg=BLUE_D, bold=True, size=11, h=22)
    ws2.row_dimensions[cur].height = 6; cur += 1
    cur = _erow(cur, t["intro"], size=10, h=20)
    ws2.row_dimensions[cur].height = 6; cur += 1

    cur = _erow(cur, f"\U0001f4e6 {t['sec_sales']}", bg=DGRAY, fg=WHITE, bold=True, h=18)
    if not totales_semanales:
        # Sin BR diario y sin MODO WOW no hay de donde sacar totales de 7d.
        # Se dice, en vez de fabricarlos sumando filas de periodo desconocido.
        cur = _erow(cur, f"  {t['exec_no_weekly']}", bg=YEL_L, h=34, wrap=True)
    if totales_semanales and s_d is not None:
        if s_d > 2:    stxt = t["sales_up"].format(d=f"{s_d:.1f}", pw=f"{ts_pw:,.0f}", tw=f"{ts_tw:,.0f}")
        elif s_d < -2: stxt = t["sales_down"].format(d=f"{abs(s_d):.1f}", pw=f"{ts_pw:,.0f}", tw=f"{ts_tw:,.0f}")
        else:          stxt = t["sales_flat"].format(tw=f"{ts_tw:,.0f}")
        bg_s, _ = _delta_bg(s_d)
        cur = _erow(cur, f"  {stxt}", bg=bg_s, h=24, wrap=True)
    if totales_semanales and u_d is not None:
        # Tres ramas, como ventas. Sin la rama flat un +1.5% caia en el `else` y
        # salia "Las unidades bajaron un 1.5%, de 100 a 101 unidades".
        if u_d > _UMBRAL_ESTABLE:
            utxt = t["units_up"].format(d=f"{u_d:.1f}", pw=int(tu_pw), tw=int(tu_tw))
        elif u_d < -_UMBRAL_ESTABLE:
            utxt = t["units_down"].format(d=f"{abs(u_d):.1f}", pw=int(tu_pw), tw=int(tu_tw))
        else:
            utxt = t["units_flat"].format(d=f"{abs(u_d):.1f}", pw=int(tu_pw), tw=int(tu_tw))
        bg_u, _ = _delta_bg(u_d)
        cur = _erow(cur, f"  {utxt}", bg=bg_u, h=24, wrap=True)
    ws2.row_dimensions[cur].height = 6; cur += 1

    cur = _erow(cur, f"\U0001f50d {t['sec_traffic']}", bg=DGRAY, fg=WHITE, bold=True, h=18)
    _k_traf = _calificar_trafico(se_d, cvr_d) if totales_semanales else None
    if totales_semanales and se_d is not None:
        if _k_traf:
            stxt2 = t[_k_traf].format(d=f"{abs(se_d):.1f}")
            bg_se, _ = _delta_bg(se_d if _k_traf != "sess_up_cvr_down" else -1.0)
            cur = _erow(cur, f"  {stxt2}", bg=bg_se, h=34, wrap=True)
    elif totales_semanales and tse_tw > 0:
        cur = _erow(cur, f"  Sesiones TW: {int(tse_tw):,}", h=20)
    if totales_semanales and avg_cvr_tw > 0 and avg_cvr_pw > 0:
        if cvr_d and cvr_d > 0:
            ctxt = t["cvr_up"].format(tw=f"{avg_cvr_tw:.2f}", pw=f"{avg_cvr_pw:.2f}")
        elif _k_traf == "sess_up_cvr_down":
            # La seccion de trafico ya diagnostico calidad de trafico para ESTE
            # mismo hecho. Repetir "revisar listing y precio" seria dar dos causas
            # distintas al mismo sintoma: se reporta el dato y se remite arriba.
            ctxt = t["cvr_down_ya_visto"].format(tw=f"{avg_cvr_tw:.2f}", pw=f"{avg_cvr_pw:.2f}")
        else:
            ctxt = t["cvr_down"].format(tw=f"{avg_cvr_tw:.2f}", pw=f"{avg_cvr_pw:.2f}")
        bg_c, _ = _delta_bg(cvr_d)
        cur = _erow(cur, f"  {ctxt}", bg=bg_c, h=24, wrap=True)
    elif avg_cvr_tw > 0:
        cur = _erow(cur, f"  CVR TW: {avg_cvr_tw:.2f}%", h=20)
    ws2.row_dimensions[cur].height = 6; cur += 1

    cur = _erow(cur, f"\U0001f4e3 {t['sec_ads']}", bg=ORG_L, fg=ORG_D, bold=True, h=18)
    if g_acos is not None:
        if g_acos < 30: atxt = t["acos_ok"].format(v=f"{g_acos:.1f}")
        else:           atxt = t["acos_warn"].format(v=f"{g_acos:.1f}")
        bg_ac = GRN_L if g_acos < 30 else YEL_L
        cur = _erow(cur, f"  {atxt}", bg=bg_ac, h=22, wrap=True)
    if g_tacos is not None:
        cur = _erow(cur, f"  {t['tacos_line'].format(v=f'{g_tacos:.1f}')}", h=20)
    ws2.row_dimensions[cur].height = 6; cur += 1

    bb_rows = [(r["asin"], r["bb"]) for r in rows_data
               if r["bb"] is not None and r["bb"] > 0 and r["sess_tw"] and r["sess_tw"] > 0]
    if bb_rows:
        cur = _erow(cur, f"\U0001f6d2 {t['sec_bb']}", bg=DGRAY, fg=WHITE, bold=True, h=18)
        bb_warn = [(a, b) for a, b in bb_rows if b < 95]
        avg_bb = sum(b for _, b in bb_rows) / len(bb_rows)
        if bb_warn:
            for aw, bw in bb_warn:
                cur = _erow(cur, t["bb_warn"].format(asin=aw, bb=f"{bw:.1f}"), bg=RED_L, fg=RED_D, h=20)
        else:
            cur = _erow(cur, f"  {t['bb_ok'].format(bb=f'{avg_bb:.1f}')}", bg=GRN_L, fg=GRN_D, h=20)
        ws2.row_dimensions[cur].height = 6; cur += 1

    cur = _erow(cur, f"\u2705 {t['sec_conclusion']}", bg=NAVY, fg=WHITE, bold=True, h=18)
    cur = _erow(cur, f"  {t['conclusion'].format(trend=trend, action=action)}", h=30, wrap=True)

    # ── SHEET 4: Changelog (opcional) ──────────────────────────────
    if changelog_text and changelog_text.strip():
        ws_cl = wb_out.create_sheet("\U0001f4dd Changelog")
        ws_cl.sheet_view.showGridLines = False
        ws_cl.column_dimensions["A"].width = 20
        ws_cl.column_dimensions["B"].width = 80

        ws_cl.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
        c = ws_cl.cell(row=1, column=1, value=f"{client_name} — Changelog")
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 14)
        c.alignment = _al("left"); c.border = _bd()
        ws_cl.row_dimensions[1].height = 28

        from datetime import date as _date
        _cell(ws_cl, 2, 1, "Fecha", bg=DGRAY, fg=WHITE, bold=True)
        _cell(ws_cl, 2, 2, "Cambios realizados", bg=DGRAY, fg=WHITE, bold=True)
        ws_cl.row_dimensions[2].height = 16

        _cell(ws_cl, 3, 1, str(_date.today()), bg=LGRAY, left=True)
        c_txt = ws_cl.cell(row=3, column=2, value=changelog_text.strip())
        c_txt.fill = _fill(LGRAY)
        c_txt.font = _font(size=9)
        c_txt.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        c_txt.border = _bd()
        ws_cl.row_dimensions[3].height = max(30, min(200, 15 * changelog_text.count("\n") + 30))

    buf = io.BytesIO()
    wb_out.save(buf)
    buf.seek(0)
    return buf


def render():
    wlang = st.radio("\U0001f310 Idioma / Language", ["Espa\u00f1ol", "English"], horizontal=True, key="wlang")
    lang_w = "es" if wlang == "Espa\u00f1ol" else "en"

    st.header("\U0001f4ca Weekly Client Report")
    st.caption("BR diario + BR by Child (1 o 2 semanas) + Atom 11 ASIN + Campaign CSV → Excel 3 hojas" if lang_w == "es"
               else "Daily BR + BR by Child (1 or 2 weeks) + Atom 11 ASIN + Campaign CSV → 3-sheet Excel")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Generar el reporte semanal para el cliente con comparación WoW automática (CUENTA TOTAL + desglose por ASIN).")
        with col2:
            st.markdown("**📂 Archivos necesarios**")
            st.caption("BR diario 14d (By Date) + BR by Child de esta semana + BR by Child de la "
                       "semana anterior (opcional) + Atom 11 ASIN 14d + Campaign CSV. "
                       "Todos con el mismo date range.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Enviar al cliente vía Slack/email. Usar el botón de changelog para comunicación técnica.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Seleccioná idioma (ES/EN) e ingresá nombre del cliente\n"
            "2. Subí los archivos (mismo date range de 14 días)\n"
            "3. Para tener comparación semanal POR PRODUCTO, subí también el by-Child de la "
            "semana anterior (3º uploader). Sin ese archivo el reporte sale igual, pero los "
            "montos por ASIN van etiquetados como período completo\n"
            "4. Agregá changelog técnico opcional (se suma como hoja extra)\n"
            "5. Descargá el Excel con 3 hojas: WoW Comparison + Advertising + Reporte Ejecutivo"
        )

    client_w = st.text_input("Nombre del cliente / Client name",
                              placeholder="Ej: Love To Dream MX", key="weekly_client")

    with st.expander("\U0001f4cb Columnas requeridas / opcionales del BR", expanded=False):
        st.markdown(
            "**BR diario (By Date \u2014 Sales and Traffic) \u2014 core m\u00ednimo:**\n"
            "- `Date`\n"
            "- `Sessions - Total` (o `Sessions - Mobile App` + `Sessions - Browser`)\n"
            "- `Units Ordered`\n"
            "- `Ordered Product Sales`\n\n"
            "**BR by Child (Detail Page Sales and Traffic By Child Item) \u2014 core m\u00ednimo:**\n"
            "- `(Child) ASIN`\n"
            "- `Sessions - Total` (o split Mobile App + Browser)\n"
            "- `Units Ordered`\n"
            "- `Ordered Product Sales`\n\n"
            "**Opcionales (se incluyen si vienen, se omiten si no):**\n"
            "- `Featured Offer (Buy Box) Percentage` \u2014 recomendado para WoW\n"
            "- `Unit Session Percentage` o `Order Item Session Percentage` (CVR \u2014 fallback autom\u00e1tico)\n"
            "- `(Parent) ASIN`, `Title`\n"
            "- `Page Views - Total` y splits Mobile/Browser\n"
            "- `Total Order Items`, `Units Refunded`, `Refund Rate`\n"
            "- `Shipped Product Sales`, `Units Shipped`, `Orders Shipped`\n"
            "- Variantes B2B de cualquier columna (filtradas por defecto, info disponible v\u00eda flag)\n\n"
            "**Tip:** el parser tolera dashes unicode (`\u2013`, `\u2014`), doble espacio, falta de gui\u00f3n y splits Mobile/Browser sin Total."
        )

    st.markdown("#### 1\ufe0f\u20e3 Business Report \u2014 " + ("14 d\u00edas diario" if lang_w == "es" else "14-day daily"))
    st.caption("Sales Dashboard \u2192 By Date \u2192 Sales and Traffic \u00b7 Rango: 14 d\u00edas")
    br_daily_file = st.file_uploader("BR diario 14 d\u00edas (.csv/.xlsx)", type=["csv","xlsx"], key="br_daily")

    st.markdown("#### 2\ufe0f\u20e3 Business Report — By Child Item — "
                + ("esta semana" if lang_w == "es" else "this week"))
    st.caption("By ASIN → Detail Page Sales and Traffic By Child Item · Rango: los últimos 7 días")
    br_child_file = st.file_uploader("BR by Child Item — esta semana (.csv/.xlsx)", type=["csv","xlsx"], key="br_child")

    st.markdown("#### 3\ufe0f\u20e3 Business Report — By Child Item — "
                + ("semana anterior" if lang_w == "es" else "prior week"))
    st.caption("Opcional. Sin este archivo no hay comparación semanal por producto: Amazon no manda "
               "fechas en el by-Child, así que un solo export no se puede partir en dos semanas. "
               "Mismo reporte, rango de los 7 días previos.")
    br_child_pw_file = st.file_uploader("BR by Child Item — semana anterior (.csv/.xlsx)", type=["csv","xlsx"], key="br_child_pw")

    st.markdown("#### 4\ufe0f\u20e3 Atom 11 \u2014 ASIN (14 d\u00edas)")
    st.caption("Atom 11 \u2192 ASIN \u2192 DateRange 14 d\u00edas. Split autom\u00e1tico 7+7.")
    atom_file = st.file_uploader("Atom 11 ASIN (.xlsx)", type=["xlsx"], key="atom_wow")

    st.markdown("#### 5\ufe0f\u20e3 Campaign Report")
    st.caption("Campaign Manager \u2192 Advertising \u2192 Campaign Manager \u2192 mismo date range de 14 d\u00edas")
    camp_file = st.file_uploader("Campaign CSV (.csv)", type=["csv"], key="wcr_campaign")

    st.markdown("#### 📝 Changelog (opcional)")
    st.caption("Cambios técnicos realizados esta semana — se agrega como hoja extra al Excel.")
    changelog_input = st.text_area(
        "Cambios técnicos realizados esta semana",
        placeholder="Ej:\n- Pausadas 5 campañas DISCOVERY con ACoS >100%\n- Nuevas rules Atom11 para DEFENSIVE\n- Ajuste bids -15% en CONQUEST",
        key="wcr_changelog",
        height=100,
    )

    if changelog_input:
        st.markdown("---")
        st.markdown("#### 📋 Formato para Slack")
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")
        slack_msg = (
            f"🦫 {client_w or 'Cliente'} — Update {fecha_hoy}\n\n"
            f"📋 Cambios realizados:\n{changelog_input}\n\n"
            f"📎 Reporte semanal adjunto en Excel."
        )
        st.code(slack_msg, language=None)
        st.caption("👆 Hacé click en el ícono de copiar arriba a la derecha del bloque para copiarlo.")

    if br_daily_file or br_child_file or br_child_pw_file or atom_file or camp_file:
        st.divider()
        try:
            br_daily_data    = _parse_br_daily_wow(br_daily_file) if br_daily_file else None
            br_child_data    = _parse_br_wow(br_child_file)       if br_child_file else {}
            br_child_pw_data = _parse_br_wow(br_child_pw_file)    if br_child_pw_file else {}
            atom_data     = _parse_atom11_wow(atom_file)        if atom_file     else {}
            camp_data     = _parse_campaign_csv(camp_file)      if camp_file     else None

            # El by-Child no trae fechas: los periodos se DERIVAN del BR diario
            # (ver _derivar_periodos, extraido y testeado directo).
            period_child_tw, period_child_pw = _derivar_periodos(
                br_daily_data, hay_child_pw=bool(br_child_pw_data)
            )

            # El PW solo se usa si el modo lo habilita. Preguntarle al MODO y no al
            # conteo de fechas cubre tambien el diario de 21 fechas, que apagaba
            # modo_wow en silencio porque 21 no es < 14.

            msgs = []
            if br_daily_data: msgs.append(f"BR diario \u2713 TW={br_daily_data['dates_tw'][-1]}")
            if br_child_data: msgs.append(f"{len(br_child_data)} ASINs BR child \u2713")
            if atom_data:     msgs.append(f"{len(atom_data)} ASINs Atom 11 \u2713")
            if camp_data:     msgs.append(f"{len(camp_data.get('campaigns',[]))} camps · {camp_data['totals']['Impressions']:,.0f} imps \u2713")
            _pw_usable = _es_modo_wow(period_child_tw, period_child_pw)
            if _pw_usable:
                msgs.append(f"{len(br_child_pw_data)} ASINs BR child PW ✓")
            elif br_child_pw_data:
                _n = sum((br_daily_data or {}).get(k, {}).get("days", 0)
                         for k in ("period_tw", "period_pw"))
                st.warning(
                    "⚠️ Se cargó el BR by Child de la **semana anterior**, pero no se puede "
                    "usar: las fechas salen del BR diario, y "
                    + (f"el que subiste trae **{_n} fechas** en vez de 14. "
                        if br_daily_data else "no subiste el BR diario. ")
                    + "Sin eso no hay comparación semanal por producto y ese archivo se "
                    "descarta. Subí el BR diario con un rango de 14 días."
                )
            st.success("\u2705 " + " \u00b7 ".join(msgs))

            # Aviso de consolidacion: Amazon repite el mismo child ASIN bajo parents
            # distintos, y el AM tiene que saber que esas filas se sumaron.
            dups = {a: v for a, v in (br_child_data or {}).items() if v.get("_rows_merged", 1) > 1}
            if dups:
                filas = sum(v["_rows_merged"] for v in dups.values())
                st.info(
                    f"\u2139\ufe0f El BR by Child trae {len(dups)} ASIN(s) repetidos bajo parents "
                    f"distintos: {filas} filas consolidadas en {len(dups)}. "
                    "Se sumaron sesiones, unidades y ventas."
                )

            if br_daily_data:
                def _dp(tw, pw):
                    try:
                        if not pw or float(pw) == 0: return None
                        return (float(tw) - float(pw)) / float(pw) * 100
                    except: return None

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("\U0001f4b0 Sales TW", f"MX${br_daily_data['Sales_TW']:,.0f}",
                          f"{_dp(br_daily_data['Sales_TW'], br_daily_data['Sales_PW']):+.1f}%"
                          if _dp(br_daily_data['Sales_TW'], br_daily_data['Sales_PW']) else None)
                c2.metric("\U0001f4e6 Units TW", f"{int(br_daily_data['Units_TW']):,}",
                          f"{_dp(br_daily_data['Units_TW'], br_daily_data['Units_PW']):+.1f}%"
                          if _dp(br_daily_data['Units_TW'], br_daily_data['Units_PW']) else None)
                c3.metric("\U0001f50d Sessions TW", f"{int(br_daily_data['Sessions_TW']):,}",
                          f"{_dp(br_daily_data['Sessions_TW'], br_daily_data['Sessions_PW']):+.1f}%"
                          if _dp(br_daily_data['Sessions_TW'], br_daily_data['Sessions_PW']) else None)
                tsp = sum(v.get("Spend_TW", 0) for v in atom_data.values())
                tad = sum(v.get("Sales_TW", 0) for v in atom_data.values())
                c4.metric("\U0001f4e3 Ad Spend TW", f"MX${tsp:,.0f}" if tsp else "\u2014")
                c5.metric("\U0001f3af ACoS", f"{tsp/tad*100:.1f}%" if tad > 0 else "\u2014")


            if br_daily_data:
                # Control de coherencia: el by-Child tiene que sumar lo mismo que el
                # BR diario de su semana. Si el AM exporto con otro rango, los montos
                # por producto no corresponden al periodo que dice la columna.
                if _pw_usable:
                    _desvios = [
                        d for d in (
                            _chequear_coherencia_child(br_child_data, br_daily_data.get("Sales_TW"), "esta semana"),
                            _chequear_coherencia_child(br_child_pw_data, br_daily_data.get("Sales_PW"), "semana anterior"),
                        ) if d
                    ]
                    _ok_msg = "✅ Los dos BR by Child cuadran con el BR diario (dentro del 1%)."
                    _causa = ("Suele pasar cuando ese archivo se exportó con un rango de fechas distinto "
                              "al del BR diario. Revisá el rango y volvé a exportarlo.")
                elif br_child_data:
                    # Un solo archivo: tiene que cubrir el periodo COMPLETO del BR
                    # diario. Es el chequeo que hubiese cazado el bug original —
                    # con los datos de Setex habria cuadrado (123.045 vs 123.045),
                    # confirmando que el by-Child era de 14d y no de 7.
                    _total_full = br_daily_data.get("Sales_TW", 0) + br_daily_data.get("Sales_PW", 0)
                    _desvios = [
                        d for d in (
                            _chequear_coherencia_child(br_child_data, _total_full, "período completo"),
                        ) if d
                    ]
                    _ok_msg = "✅ El BR by Child cuadra con el período completo del BR diario (dentro del 1%)."
                    _causa = ("Con un solo archivo, el by-Child debería cubrir el período COMPLETO del BR "
                              "diario (las dos semanas). Revisá el rango de fechas y volvé a exportarlo, "
                              "o subí un by-Child por semana en los uploaders 2 y 3.")
                else:
                    _desvios, _ok_msg, _causa = None, None, None

                if _desvios is not None:
                    if _desvios:
                        for _d in _desvios:
                            st.warning(
                                f"⚠️ El BR by Child de **{_d['etiqueta']}** no cuadra con el BR diario: "
                                f"suma MX\\${_d['suma']:,.2f} contra MX\\${_d['esperado']:,.2f} "
                                f"(diferencia MX\\${_d['delta']:,.2f}"
                                + (f" · {_d['delta_pct']:+.1f}%" if _d["delta_pct"] is not None else "")
                                + "). "
                                + _causa
                            )
                    else:
                        st.success(_ok_msg)

            modo_wow_ui = _es_modo_wow(period_child_tw, period_child_pw)

            if br_child_data or atom_data:
                preview = []
                # El rotulo tiene que decir de que periodo son los numeros:
                # fuera de MODO WOW son del periodo completo, no de una semana.
                _lbl_sales = "Sales TW" if modo_wow_ui else "Sales (periodo completo)"
                _lbl_sess  = "Sessions TW" if modo_wow_ui else "Sessions (periodo completo)"
                _dash = "\u2014"
                for asin, d in list(br_child_data.items())[:20]:
                    at = atom_data.get(asin, {})
                    preview.append({
                        "ASIN": asin,
                        "Producto": d.get("Title","")[:40],
                        _lbl_sales: f"MX${d.get('Sales',0):,.0f}",
                        _lbl_sess: int(d.get("Sessions",0)),
                        "CVR%": (f"{d['CVR']:.2f}%" if d.get('CVR') is not None else "—"),
                        "BuyBox%": "{}%".format(d.get("BuyBox", "—")) if d.get("BuyBox") else "—",
                        "AdSpend TW": f"MX${at.get('Spend_TW',0):,.2f}" if at else "\u2014",
                        "ACoS": f"{at.get('Spend_TW',0)/at.get('Sales_TW',1)*100:.1f}%"
                                if at and at.get("Sales_TW",0) > 0 else "\u2014",
                    })
                if preview:
                    st.dataframe(pd.DataFrame(preview), use_container_width=True)

            st.divider()

            excel_buf = _build_weekly_excel(
                br_tw=br_child_data, br_pw=br_child_pw_data,
                atom_tw=atom_data, atom_pw={},
                client_name=client_w or "Client",
                lang=lang_w, br_daily=br_daily_data,
                camp_data=camp_data,
                changelog_text=changelog_input,
                period_child_tw=period_child_tw,
                period_child_pw=period_child_pw,
            )
            safe_n = (client_w or "report").replace(" ", "_")[:30]
            st.download_button(
                label="\u2b07\ufe0f Descargar Weekly Report (.xlsx)" if lang_w == "es" else "\u2b07\ufe0f Download Weekly Report (.xlsx)",
                data=excel_buf.getvalue(),
                file_name=f"weekly_report_{safe_n}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key="weekly_dl",
            )

            # ── Análisis IA ────────────────────────────────────────
            st.divider()
            if st.button("🤖 Generar análisis IA", key="btn_weekly_ai", use_container_width=True):
                if not (client_w or "").strip():
                    st.warning("Ingresá el nombre del cliente primero.")
                elif not br_daily_data:
                    st.warning("Cargá al menos el BR diario para generar el análisis.")
                else:
                    with st.spinner("Analizando con Claude..."):
                        from core.ai_analyze import _claude_analyze

                        # Métricas cuenta total
                        sales_tw = br_daily_data.get("Sales_TW", 0)
                        sales_pw = br_daily_data.get("Sales_PW", 0)
                        sessions_tw = br_daily_data.get("Sessions_TW", 0)
                        sessions_pw = br_daily_data.get("Sessions_PW", 0)
                        cvr_tw = br_daily_data.get("CVR_TW", 0)
                        cvr_pw = br_daily_data.get("CVR_PW", 0)
                        buybox_tw = br_daily_data.get("BuyBox_TW", None)

                        sales_wow = ((sales_tw - sales_pw) / sales_pw * 100) if sales_pw else 0
                        sessions_wow = ((sessions_tw - sessions_pw) / sessions_pw * 100) if sessions_pw else 0
                        cvr_wow = ((cvr_tw - cvr_pw) / cvr_pw * 100) if cvr_pw else 0

                        # Ad metrics
                        spend_tw = sum(v.get("Spend_TW", 0) for v in atom_data.values()) if atom_data else 0
                        spend_pw = sum(v.get("Spend_PW", 0) for v in atom_data.values()) if atom_data else 0
                        ad_sales_tw = sum(v.get("Sales_TW", 0) for v in atom_data.values()) if atom_data else 0
                        ad_sales_pw = sum(v.get("Sales_PW", 0) for v in atom_data.values()) if atom_data else 0
                        acos_tw = (spend_tw / ad_sales_tw * 100) if ad_sales_tw else 0
                        tacos_tw = (spend_tw / sales_tw * 100) if sales_tw else 0

                        # Alarmas de campañas
                        alarmas = []
                        if camp_data:
                            for camp in camp_data.get("campaigns", []):
                                if camp.get("ACoS", 0) > 60:
                                    alarmas.append(f"{camp.get('Campaign', '')} — ACoS {camp.get('ACoS', 0):.1f}%")
                        alarmas_txt = "\n".join(alarmas[:5]) if alarmas else "Sin alarmas críticas"

                        # Contexto que el modelo no puede deducir de los numeros:
                        # en que periodo esta parado y como leer trafico vs conversion.
                        _p_tw = (br_daily_data or {}).get("period_tw") or {}
                        _p_pw = (br_daily_data or {}).get("period_pw") or {}
                        _rango = (f"{_p_pw.get('start', '?')} a {_p_tw.get('end', '?')}"
                                  if _p_tw or _p_pw else "sin fechas declaradas")
                        if modo_wow_ui:
                            _ctx_periodo = (
                                f"PERIODO: comparacion semanal real ({_rango}). "
                                "Los numeros por producto son de 7 dias contra los 7 previos."
                            )
                        else:
                            _ctx_periodo = (
                                f"PERIODO: {_rango}. ATENCION: este reporte NO trae comparacion "
                                "semanal por producto: los montos por ASIN cubren el periodo completo. "
                                "Los totales de cuenta si tienen comparacion semanal. "
                                "NO escribas variaciones semanales por ASIN: no existen en estos datos."
                            )

                        _ctx_lectura = (
                            "COMO INTERPRETAR: si las sesiones suben y el CVR baja, NO es un logro — "
                            "es un problema de calidad de trafico (terminos de busqueda, targeting) "
                            "o del listing, y se reporta como tal. Las sesiones son un input, "
                            "no un resultado: no las presentes como exito si no se tradujeron en ventas."
                        )

                        prompt = f"""Sos un experto senior en Amazon PPC redactando el reporte semanal de {client_w}.

{_ctx_periodo}

{_ctx_lectura}

MÉTRICAS CUENTA TOTAL (PW vs TW):
- Ventas TW: ${sales_tw:,.2f} | PW: ${sales_pw:,.2f} | WoW: {sales_wow:+.1f}%
- Sesiones TW: {sessions_tw:,} | PW: {sessions_pw:,} | WoW: {sessions_wow:+.1f}%
- CVR TW: {cvr_tw:.2f}% | PW: {cvr_pw:.2f}% | WoW: {cvr_wow:+.1f}%
- BuyBox TW: {f"{buybox_tw:.1f}%" if buybox_tw else "—"}

PUBLICIDAD:
- Ad Spend TW: ${spend_tw:,.2f} | PW: ${spend_pw:,.2f}
- Ad Sales TW: ${ad_sales_tw:,.2f} | PW: ${ad_sales_pw:,.2f}
- ACoS TW: {acos_tw:.1f}%
- TACoS TW: {tacos_tw:.1f}%

ALARMAS DE CAMPAÑAS (ACoS > 60%):
{alarmas_txt}

Redactá un resumen ejecutivo semanal en español para enviar al cliente.
Formato exacto:

📊 RESUMEN SEMANAL — {client_w}

📍 SITUACIÓN GENERAL
[2-3 líneas con el estado de la semana — si fue buena/mala y el driver principal]

📈 HIGHLIGHTS
[2-3 bullets con los logros más importantes de la semana]

⚠️ ATENCIÓN
[1-2 bullets con alertas o acciones que el cliente debe conocer]

🎯 PRÓXIMOS PASOS
[2-3 acciones concretas que el equipo va a ejecutar la semana que viene]

Tono: profesional pero cercano. Máximo 200 palabras.
Usá los números reales. No inventes métricas ni variaciones que no estén arriba.
"""
                        analisis = _claude_analyze(prompt)

                    st.markdown("---")
                    st.markdown(analisis)
                    st.markdown("---")

                    wai_a, wai_b = st.columns(2)
                    with wai_a:
                        st.download_button(
                            "⬇️ Descargar resumen (.txt)",
                            data=analisis,
                            file_name=f"resumen_semanal_{(client_w or 'report').replace(' ', '_')}.txt",
                            mime="text/plain",
                            use_container_width=True, key="dl_weekly_ai",
                        )
                    with wai_b:
                        st.markdown("**📋 Copiar para Slack:**")
                        st.code(analisis, language=None)

        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())
