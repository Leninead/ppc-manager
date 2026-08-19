"""M14 Weekly Client Report — red de seguridad F0 del bug de período (deuda #24).

Contexto: `notes/state/STATE-agencia.md` → Deuda técnica **#24** (🔴 P0, verificado
2026-08-18). El reporte semanal presenta las **filas por producto** con el agregado
del **período completo (14 días)** bajo la columna rotulada **"esta semana" (7d)**.
En Setex los montos por ASIN salieron ~2× lo real (2,19× ventas, 2,23× unidades).

Lo que **NO** está roto y estos tests blindan que siga así: el **total de cuenta**
(fila `▶ CUENTA TOTAL`, alimentada por el BR diario) y la hoja Advertising.

Causa raíz: el export por ASIN de Amazon (`Detail Page Sales and Traffic By Child
Item`) **no trae columna de fecha** — es un único agregado del período pedido. El
generador lo vuelca en "esta semana" porque no tiene con qué partirlo.

Este archivo es **F0: solo red de seguridad**. Los 6 tests rojos capturan los bugs
ANTES de arreglarlos; NO se toca código de producción para que pasen. Cada uno está
marcado con `# FALLA HOY - F<n>` según la fase que lo va a poner en verde:

    F1 — dedup: `_parse_br_wow` hace `result[asin] = {...}` (L275) dentro del loop
         de filas → **last-wins**. Un child ASIN que aparece bajo dos parents pierde
         una de sus filas. Patología real de Setex (B09HVXDH7M bajo B0F3Q54GJK y
         bajo sí mismo).  → tests 1, 2, 3, 4
    F2/F3 — período: las filas por producto llevan 14d bajo rótulo de 7d.
         → test 5 (el test central: la invariante que hubiese cazado el bug el día 1)
    F4 — TACoS cross-period: numerador de 7d (Atom11) sobre denominador de 14d (BR
         by child) → el número no significa nada.  → test 6

Los 3 tests verdes (7, 8, 9) son **regresión** de los parsers BR tolerantes
(dashes unicode, split Mobile/Browser, doble espacio, mínimo de 7 fechas). Deben
pasar hoy y después de todas las fases.

Convenciones seguidas del repo: datos sintéticos inline + `BytesIO` (el repo no
versiona fixtures CSV — `tests/fixtures/` tiene solo HTML del importer B7), y
acceso a la función cruda vía `.__wrapped__` para saltear `@st.cache_data`
(patrón de `test_forecast_actual_series.py:111`).
"""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from modules.pages import weekly_client_report as wcr

# `.__wrapped__` saltea @st.cache_data: Streamlit está instalado, así que el
# decorador cachea de verdad y un BytesIO idéntico entre tests haría bleed.
_parse_br_wow = wcr._parse_br_wow.__wrapped__
_parse_br_daily_wow = wcr._parse_br_daily_wow.__wrapped__

EM_DASH = "—"  # el "sin dato" que escribe _build_weekly_excel
EN_DASH = "–"  # el separador raro que Amazon a veces mete en los headers


# ─────────────────────────────────────────────────────────────────────────────
# Datos sintéticos — inventados, NO de cliente. Aritmética verificable a mano.
# ─────────────────────────────────────────────────────────────────────────────

# BR by child, 14 días agregados. `B0TEST0001` aparece DOS VECES bajo parents
# distintos — la patología que dispara el last-wins.
#
# Consolidación correcta de B0TEST0001:
#   sessions 100 + 50 = 150
#   units     25 +  5 =  30
#   sales   2000 + 1000 = 3000
#   CVR   = 30/150      = 20.00   (recalculado; NO 10.00 heredado, NI 17.5 promedio)
#   BuyBox = (100.00*100 + 90.00*50) / 150 = 96.67  (ponderado por sesiones)
#
# Total del fixture: 3000 + 4000 = 7000  → coincide con el BR diario de 14d.
_BR_BY_CHILD_DUP = """\
(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,Featured Offer (Buy Box) Percentage,Units Ordered,Unit Session Percentage,Ordered Product Sales,Total Order Items
B0PARENT001,B0TEST0001,Producto Uno Variante A,100,100.00%,25,25.00%,"MX$2,000.00",25
B0TEST0001,B0TEST0001,Producto Uno Variante A,50,90.00%,5,10.00%,"MX$1,000.00",5
B0PARENT002,B0TEST0002,Producto Dos,200,100.00%,40,20.00%,"MX$4,000.00",40
"""

# BR by date, 14 días (8/3/26 → 8/16/26), todos idénticos.
#   por día: sales 500, units 5, sessions 25
#   PW (8/3–8/9)  = 3500 / 35 / 175
#   TW (8/10–8/16) = 3500 / 35 / 175
#   total 14d      = 7000 / 70 / 350
_BR_BY_DATE_14D = "".join(
    ["Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage\n"]
    + [f'8/{d}/26,"MX$500.00",5,25,20.00%\n' for d in range(3, 17)]
)

# Solo 5 fechas → por debajo del mínimo de 7 que exige el split PW/TW.
_BR_BY_DATE_5D = "".join(
    ["Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage\n"]
    + [f'8/{d}/26,"MX$500.00",5,25,20.00%\n' for d in range(3, 8)]
)

# Variantes de export de Amazon, sin ASIN duplicado:
#   - sin "Sessions - Total": split "Sessions – Mobile App" + "Sessions – Browser"
#   - EN-DASH (U+2013) en vez de guión ASCII
#   - "Ordered  Product  Sales" con doble espacio
# Sessions esperadas: 60 + 40 = 100 · units 20 · sales 2000.
_BR_BY_CHILD_VARIANTES = (
    "(Parent) ASIN,(Child) ASIN,Title,"
    f"Sessions {EN_DASH} Mobile App,Sessions {EN_DASH} Browser,"
    "Featured Offer (Buy Box) Percentage,Units Ordered,Unit Session Percentage,"
    "Ordered  Product  Sales\n"
    'B0PARENT003,B0TEST0003,Producto Tres,60,40,100.00%,20,20.00%,"MX$2,000.00"\n'
)


# ── by-Child partido en dos semanas ──────────────────────────────────────────
# El par que habilita MODO WOW: dos archivos de 7d, uno por semana. Es lo que en
# F3 va a cargar el AM por el 5º uploader, así que estos fixtures se reusan ahí.
# Cada uno suma exactamente lo que el BR diario reporta para su mitad:
#   sales 3500 · units 35 · sessions 175
#
# El TW mantiene el ASIN duplicado (B0TEST0001 bajo dos parents) para que el
# invariante se pruebe CON consolidación de por medio, no sobre un caso trivial.
#   B0TEST0001: 50+25 = 75 sesiones · 10+5 = 15 units · 1000+500 = 1500 sales
#   B0TEST0002: 100 sesiones · 20 units · 2000 sales
_BR_BY_CHILD_TW_7D = """\
(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,Featured Offer (Buy Box) Percentage,Units Ordered,Unit Session Percentage,Ordered Product Sales
B0PARENT001,B0TEST0001,Producto Uno Variante A,50,100.00%,10,20.00%,"MX$1,000.00"
B0TEST0001,B0TEST0001,Producto Uno Variante A,25,90.00%,5,20.00%,"MX$500.00"
B0PARENT002,B0TEST0002,Producto Dos,100,100.00%,20,20.00%,"MX$2,000.00"
"""

# La semana anterior, mismos totales, sin duplicado.
#   B0TEST0001: 75 sesiones · 15 units · 1500 sales
#   B0TEST0002: 100 sesiones · 20 units · 2000 sales
_BR_BY_CHILD_PW_7D = """\
(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,Featured Offer (Buy Box) Percentage,Units Ordered,Unit Session Percentage,Ordered Product Sales
B0PARENT001,B0TEST0001,Producto Uno Variante A,75,100.00%,15,20.00%,"MX$1,500.00"
B0PARENT002,B0TEST0002,Producto Dos,100,100.00%,20,20.00%,"MX$2,000.00"
"""


def _b(text: str) -> io.BytesIO:
    """CSV como file-like. Sin `.name` → el parser cae a `pd.read_csv` (hasattr)."""
    return io.BytesIO(text.encode("utf-8"))


def _wow_sheet(buf):
    """Hoja 'WoW Comparison' del Excel generado (el título lleva un emoji)."""
    wb = load_workbook(buf)
    for ws in wb.worksheets:
        if ws.title.endswith("WoW Comparison"):
            return ws
    raise AssertionError(f"No se encontró la hoja WoW. Hojas: {wb.sheetnames}")


# ─────────────────────────────────────────────────────────────────────────────
# ROJOS — capturan el bug. DEBEN FALLAR hasta que se arregle producción.
# ─────────────────────────────────────────────────────────────────────────────

def test_dedup_no_pisa_asin_duplicado():
    # FALLA HOY - F1
    # Hoy devuelve 1000 / 5 / 50: la segunda fila pisa a la primera.
    out = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    d = out["B0TEST0001"]
    assert d["Sales"] == 3000.0
    assert d["Units"] == 30.0
    assert d["Sessions"] == 150.0


def test_dedup_cvr_recalculado_no_heredado():
    # FALLA HOY - F1
    # Hoy devuelve 10.00: hereda el CVR de la última fila en vez de recalcular.
    out = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    cvr = out["B0TEST0001"]["CVR"]
    assert cvr == pytest.approx(20.00, abs=0.01)  # = 30 units / 150 sessions
    # 17.5 = (25.00 + 10.00) / 2 → promedio aritmético de los CVR reportados por
    # fila. Es la otra implementación incorrecta posible, y este assert la descarta:
    # el CVR consolidado tiene que salir del cociente de los totales, no de
    # promediar porcentajes de filas con distinto peso en sesiones.
    assert cvr != pytest.approx(17.5, abs=0.01)


def test_dedup_buybox_ponderado_por_sesiones():
    # FALLA HOY - F1
    # Hoy devuelve 90.0 (el de la última fila) en vez del ponderado por sesiones.
    out = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    assert out["B0TEST0001"]["BuyBox"] == pytest.approx(96.67, abs=0.01)


def test_dedup_total_by_child_igual_a_total_by_date():
    # FALLA HOY - F1
    # Hoy la suma da 5000: perdió los 2000 de la fila pisada.
    out = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    daily = _parse_br_daily_wow(_b(_BR_BY_DATE_14D))

    total_14d = daily["Sales_PW"] + daily["Sales_TW"]
    assert total_14d == 7000.0, "guarda del fixture: el BR diario debe sumar 7000 en 14d"

    assert sum(v["Sales"] for v in out.values()) == total_14d


@pytest.mark.parametrize(
    "modo, src_tw, src_pw, p_tw, p_pw, cuenta_esperada",
    [
        # El caso que produjo el bug: un solo by-Child de 14d.
        ("completo", _BR_BY_CHILD_DUP, None, {"start": "2026-08-03", "end": "2026-08-16", "days": 14}, None, 7000.0),
        # El caso sano: dos by-Child de 7d, uno por semana.
        ("wow", _BR_BY_CHILD_TW_7D, _BR_BY_CHILD_PW_7D,
         {"start": "2026-08-10", "end": "2026-08-16", "days": 7},
         {"start": "2026-08-03", "end": "2026-08-09", "days": 7}, 3500.0),
    ],
    # Sin ids explícitos pytest usa el CSV entero como identificador del caso.
    ids=["modo_periodo_completo", "modo_wow"],
)
def test_invariante_suma_productos_no_supera_cuenta_total(
    modo, src_tw, src_pw, p_tw, p_pw, cuenta_esperada
):
    # EL TEST CENTRAL. Invariante de sentido común que ningún reporte puede violar:
    # la suma de las filas de producto no puede superar el total de la cuenta, en
    # la MISMA columna. Antes de F2 daba 5000 (productos, 14d) contra 3500 (cuenta,
    # 7d) — este es el test que hubiese cazado el bug el día 1.
    #
    # Se verifica en LOS DOS modos: el invariante no depende del modo, y correrlo
    # en ambos evita que un futuro cambio lo satisfaga solo en el camino feliz.
    br_tw = _parse_br_wow(_b(src_tw))
    br_pw = _parse_br_wow(_b(src_pw)) if src_pw else {}
    br_daily = _parse_br_daily_wow(_b(_BR_BY_DATE_14D))

    buf = wcr._build_weekly_excel(
        br_tw, br_pw, {}, {}, "TEST", "es", br_daily,
        period_child_tw=p_tw, period_child_pw=p_pw,
    )
    ws = _wow_sheet(buf)

    # Guardas de layout: si el Excel cambia de forma, que falle por eso y no por
    # comparar celdas equivocadas en silencio. Se verifica el GRUPO de la fila 2,
    # que es "SALES" en ambos modos — el subheader de la fila 3 ya no sirve de
    # ancla porque cambia de rótulo según el modo, que es justo lo que F2 arregló.
    assert "CUENTA TOTAL" in str(ws.cell(4, 1).value), "la fila 4 debe ser CUENTA TOTAL"
    assert ws.cell(2, 3).value == "SALES", "la col 3 debe pertenecer al grupo SALES"

    # Guarda de valor por modo: el test sigue sabiendo qué número espera.
    # En MODO PERÍODO COMPLETO la cuenta muestra el agregado de 14d (7000); en
    # MODO WOW muestra solo la semana (3500).
    cuenta_total = ws.cell(4, 3).value
    assert cuenta_total == cuenta_esperada, f"guarda del fixture (modo {modo})"

    primera_fila_producto = 5  # 4 (CUENTA TOTAL) + 1
    suma_productos = sum(
        ws.cell(r, 3).value or 0
        for r in range(primera_fila_producto, primera_fila_producto + len(br_tw))
    )

    assert suma_productos <= cuenta_total, (
        f"la suma de productos ({suma_productos}) supera el total de cuenta "
        f"({cuenta_total}) en la misma columna 'esta semana'"
    )


def test_tacos_none_si_periodos_no_coinciden():
    # FALLA HOY - F4
    # Hoy escribe 2.5 = 100 (Spend_TW, 7d de Atom11) / 4000 (Sales, 14d del BR by
    # child) * 100. Numerador y denominador son de períodos distintos, así que el
    # número no significa nada: corresponde "—".
    br_tw = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    br_daily = _parse_br_daily_wow(_b(_BR_BY_DATE_14D))
    atom_tw = {
        "B0TEST0002": {
            "Sales_TW": 500.0, "Sales_PW": 400.0,
            "Spend_TW": 100.0, "Spend_PW": 80.0,
        }
    }

    buf = wcr._build_weekly_excel(br_tw, {}, atom_tw, {}, "TEST", "es", br_daily)
    ws = _wow_sheet(buf)

    primera_fila_producto = 5
    fila = next(
        r
        for r in range(primera_fila_producto, primera_fila_producto + len(br_tw))
        if ws.cell(r, 2).value == "B0TEST0002"
    )
    assert ws.cell(3, 23).value == "Esta semana", "guarda: la col 23 debe ser TACoS"

    assert ws.cell(fila, 23).value == EM_DASH


# ─────────────────────────────────────────────────────────────────────────────
# VERDES — regresión de los parsers BR tolerantes. Deben pasar hoy y siempre.
# ─────────────────────────────────────────────────────────────────────────────

def test_variantes_dashes_unicode_y_split_sessions():
    out = _parse_br_wow(_b(_BR_BY_CHILD_VARIANTES))
    d = out["B0TEST0003"]
    assert d["Sessions"] == 100.0  # 60 Mobile App + 40 Browser
    assert d["Sales"] == 2000.0    # header con doble espacio


def test_br_daily_split_7_7_correcto():
    d = _parse_br_daily_wow(_b(_BR_BY_DATE_14D))
    assert d["Sales_TW"] == 3500.0
    assert d["Sales_PW"] == 3500.0
    assert d["Units_TW"] == 35.0
    assert d["Sessions_TW"] == 175.0
    assert len(d["dates_tw"]) == 7
    assert len(d["dates_pw"]) == 7


def test_br_daily_rechaza_menos_de_7_fechas():
    with pytest.raises(ValueError):
        _parse_br_daily_wow(_b(_BR_BY_DATE_5D))


# ─────────────────────────────────────────────────────────────────────────────
# F1 — contrato de la consolidación. Verdes desde el fix de dedup.
# ─────────────────────────────────────────────────────────────────────────────

def test_dedup_expone_metadata_de_consolidacion():
    """La consolidación tiene que ser auditable: cuántas filas se fusionaron y
    bajo qué parents venían. Sin esto el AM no puede explicar por qué el número
    del reporte no coincide con una lectura ingenua del CSV."""
    out = _parse_br_wow(_b(_BR_BY_CHILD_DUP))

    assert out["B0TEST0001"]["_rows_merged"] == 2
    assert set(out["B0TEST0001"]["_parents"]) == {"B0PARENT001", "B0TEST0001"}

    # Sin duplicado: 1 fila, y la metadata igual está presente (no es opcional).
    assert out["B0TEST0002"]["_rows_merged"] == 1
    assert out["B0TEST0002"]["_parents"] == ["B0PARENT002"]


def test_cvr_recalculado_coincide_con_amazon_en_filas_unicas():
    """Recalcular el CVR SIEMPRE no debe introducir drift en el caso normal.

    El fixture de variantes no tiene duplicados y su `Unit Session Percentage`
    (20.00%) es consistente con units/sessions (20/100). Si el recálculo se
    desviara del valor que reporta Amazon, este test lo caza.
    """
    csv_cvr = 20.00  # el Unit Session Percentage del fixture
    out = _parse_br_wow(_b(_BR_BY_CHILD_VARIANTES))
    d = out["B0TEST0003"]

    assert d["_rows_merged"] == 1, "guarda: este fixture no debe tener duplicados"
    assert d["CVR"] == pytest.approx(csv_cvr, abs=0.01)
    assert d["CVR"] == pytest.approx(d["Units"] / d["Sessions"] * 100, abs=0.01)


# Dos filas del mismo ASIN, ambas con 0 sesiones pero con BuyBox informado.
# Caso degenerado real: ASIN sin tráfico en la ventana. El ponderado por sesiones
# divide por cero si no se guarda.
_BR_BY_CHILD_SIN_SESIONES = """\
(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,Featured Offer (Buy Box) Percentage,Units Ordered,Unit Session Percentage,Ordered Product Sales
B0PARENT004,B0TEST0004,Producto Cuatro,0,100.00%,0,0.00%,"MX$0.00"
B0PARENT005,B0TEST0004,Producto Cuatro,0,80.00%,0,0.00%,"MX$0.00"
"""


def test_buybox_none_si_todas_las_sesiones_son_cero():
    out = _parse_br_wow(_b(_BR_BY_CHILD_SIN_SESIONES))
    d = out["B0TEST0004"]

    assert d["_rows_merged"] == 2
    assert d["Sessions"] == 0.0
    assert d["BuyBox"] is None  # sin sesiones no hay ponderación posible
    assert d["CVR"] is None     # y el cociente no está definido


# ─────────────────────────────────────────────────────────────────────────────
# F2 — contrato de período. El rótulo de una columna tiene que corresponderse
# con los días de dato que la respaldan, y una columna nunca mezcla períodos.
# ─────────────────────────────────────────────────────────────────────────────

_P7_A = {"start": "2026-08-03", "end": "2026-08-09", "days": 7}
_P7_B = {"start": "2026-08-10", "end": "2026-08-16", "days": 7}
_P14 = {"start": "2026-08-03", "end": "2026-08-16", "days": 14}


def _excel(period_child_tw=None, period_child_pw=None, atom_tw=None):
    br_tw = _parse_br_wow(_b(_BR_BY_CHILD_DUP))
    br_daily = _parse_br_daily_wow(_b(_BR_BY_DATE_14D))
    buf = wcr._build_weekly_excel(
        br_tw, {}, atom_tw or {}, {}, "TEST", "es", br_daily,
        period_child_tw=period_child_tw, period_child_pw=period_child_pw,
    )
    return _wow_sheet(buf), br_tw


def test_modo_wow_rotula_esta_semana():
    """Con dos períodos de 7d declarados, el reporte puede comparar semanas."""
    ws, _ = _excel(period_child_tw=_P7_B, period_child_pw=_P7_A)

    assert ws.cell(3, 3).value == "Esta semana"
    assert ws.cell(3, 4).value == "Semana anterior"
    assert ws.cell(3, 5).value == "Variación %"


def test_modo_degradado_rotula_periodo_completo():
    """Sin período para la semana anterior no hay WoW posible: hay que decirlo."""
    ws, _ = _excel(period_child_tw=_P14, period_child_pw=None)

    encabezado = str(ws.cell(3, 3).value)
    assert "completo" in encabezado.lower()
    assert "14" in encabezado
    assert ws.cell(3, 4).value == "—"
    assert ws.cell(3, 5).value == "—"


def test_modo_degradado_cuenta_total_coherente_con_productos():
    """La raíz del bug: cuenta en 7d y productos en 14d, en la misma columna."""
    ws, br_tw = _excel(period_child_tw=_P14, period_child_pw=None)

    cuenta_total = ws.cell(4, 3).value
    suma_productos = sum(ws.cell(r, 3).value or 0 for r in range(5, 5 + len(br_tw)))

    assert cuenta_total == 7000.0, "la cuenta debe mostrar el agregado de 14d, no 3500"
    assert suma_productos == 7000.0
    assert suma_productos == cuenta_total


def test_periodo_de_14_dias_no_habilita_modo_wow():
    """La guarda mira `days`, no la mera presencia del período declarado.

    Es el caso que produjo el bug: había un período, pero de 14 días. Si la
    condición fuera `if period_child_tw:` el reporte volvería a rotular mal.
    """
    ws, _ = _excel(period_child_tw=_P14, period_child_pw=_P14)

    assert ws.cell(3, 3).value != "Esta semana"
    assert "completo" in str(ws.cell(3, 3).value).lower()
