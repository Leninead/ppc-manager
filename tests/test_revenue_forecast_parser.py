"""Tests del FIX del parser de ingesta de M31 con datos reales (Setex MX +
Dermaglos US) y casos sintéticos para reproducibilidad.

Contexto: el parser F2 original solo se probó contra el demo limpio ISO
mensual. Con BRs reales fallaba:
    - Moneda MX$ (Setex): `re.sub(r"[$,%]", "", "MX$5,121.00")` → "MX5121.00"
      → ValueError → 0.0 (bug L1273 del HTML, heredado al port).
    - Granularidad diaria (Amazon by-date export = 1 fila/día) — el motor
      necesita mensual.
    - Reporte sin Sessions (Sales and Orders by Month) — el parser ingería
      a medias con sessions=0, lo que rompía el motor F3 silenciosamente.

Estrategia de tests:
    1. **Helper puro** (`_parse_num`): strings inline con valores clavados,
       100% reproducible.
    2. **Fixtures reales** (`tests/fixtures/real/*.csv`): gitignored (datos
       de clientes). Se usan con `skipif(not path.exists())` para que la
       suite no rompa donde falten. Los valores esperados se DERIVAN
       INDEPENDIENTEMENTE del parser bajo test (leyendo el CSV con pandas
       crudo + suma manual) — NO usamos el output del propio parser como
       golden (sería placebo).
    3. **Mini-CSVs sintéticos** (inline) que reproducen los formatos reales
       (MX$, comas, comillas, diario) sin depender de los gitignored.
    4. **Regresión demo** (`_DERMAGLOS_DATA`): el path del demo limpio
       (ISO mensual) sigue produciendo 23 meses con shape correcto.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures path (gitignored — skip si no están)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real"
_SETEX_BYDATE = _FIXTURES_DIR / "setex_mx_bydate.csv"
_DERMAGLOS_BYDATE = _FIXTURES_DIR / "dermaglos_us_bydate.csv"
_DERMAGLOS_BYMONTH = _FIXTURES_DIR / "dermaglos_us_bymonth.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Helper de derivación INDEPENDIENTE (no usa el parser bajo test).
# ─────────────────────────────────────────────────────────────────────────────

def _clean_money_independent(v) -> float:
    """Limpia string monetario sin usar el parser de M31. Para derivar
    golden values en tests de agregación.

    Reglas idénticas conceptualmente a _parse_num pero implementación
    distinta para validar el contrato, no la implementación.
    """
    import re as _re
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    s = str(v).strip().replace('"', "").replace(",", "")
    s = _re.sub(r"^[A-Za-z]*\$", "", s)
    s = s.replace("$", "").replace("%", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _parse_num — helper puro, valores inline clavados
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_num_handles_dermaglos_us_simple_dollar():
    """Dermaglos US: precios diarios chicos sin coma de miles."""
    assert rf._parse_num("$210.76") == pytest.approx(210.76)


def test_parse_num_handles_dermaglos_us_with_thousands_comma():
    """Dermaglos US: BR by-month suma de mayo+junio chica → $3,672.17."""
    assert rf._parse_num("$3,672.17") == pytest.approx(3672.17)


def test_parse_num_handles_dermaglos_us_revenue_total_month():
    """Dermaglos US: total mensual ~ $6,513.61 con coma de miles."""
    assert rf._parse_num("$6,513.61") == pytest.approx(6513.61)


def test_parse_num_handles_mexican_peso_prefix():
    """Setex MX: bug del HTML original — 'MX$5,121.00' → ValueError → 0.0.
    Tras el fix debe devolver 5121.0.
    """
    assert rf._parse_num("MX$5,121.00") == pytest.approx(5121.0)


def test_parse_num_handles_mexican_peso_no_thousands():
    """Setex MX: valor chico MX$ sin coma."""
    assert rf._parse_num("MX$265.53") == pytest.approx(265.53)


def test_parse_num_handles_zero_dollar():
    """B2B en cero: '$0.00' debe dar 0.0 (no NaN, no error)."""
    assert rf._parse_num("$0.00") == 0.0


def test_parse_num_handles_empty_string():
    """String vacío → 0.0 (no error)."""
    assert rf._parse_num("") == 0.0


def test_parse_num_handles_pct():
    """CVR de Amazon viene como '7.07%' — el % se quita."""
    assert rf._parse_num("7.07%") == pytest.approx(7.07)


def test_parse_num_handles_quoted_value():
    """Algunos CSV de Amazon citan valores con coma: '"$3,672.17"'."""
    assert rf._parse_num('"$3,672.17"') == pytest.approx(3672.17)


def test_parse_num_handles_quoted_mxn():
    """Setex MX: comillas + MX$ + coma de miles, los tres juntos."""
    assert rf._parse_num('"MX$5,310.54"') == pytest.approx(5310.54)


def test_parse_num_none_and_nan_and_int():
    """None / NaN / int nativo: comportamiento legado preservado."""
    assert rf._parse_num(None) == 0.0
    assert rf._parse_num(float("nan")) == 0.0
    assert rf._parse_num(42) == 42.0
    assert rf._parse_num(42.5) == pytest.approx(42.5)


# ─────────────────────────────────────────────────────────────────────────────
# Mini-CSVs sintéticos (inline) — formatos reales sin depender de gitignored
# ─────────────────────────────────────────────────────────────────────────────

_SYNTH_BYDATE_MXN = """\
Date,Ordered Product Sales,Ordered Product Sales - B2B,Units Ordered,Units Ordered - B2B,Sessions - Total,Sessions - Total - B2B,Order Item Session Percentage
5/1/26,"MX$5,310.54",MX$0.00,20,0,216,1,9.26%
5/2/26,"MX$5,072.00",MX$0.00,19,0,234,4,8.12%
5/3/26,"MX$8,310.35",MX$288.00,30,1,225,1,13.33%
6/1/26,"MX$3,000.00",MX$0.00,10,0,100,0,10.00%
6/2/26,"MX$2,000.00",MX$0.00,8,0,80,0,10.00%
"""


def test_parse_business_report_synthetic_mxn_aggregates_to_monthly():
    """Sintético: 5 filas diarias MX$ (3 mayo + 2 junio) → 2 filas mensuales.
    Verifica que la limpieza MX$ funciona + agregación día→mes.

    Esperados (derivados INDEPENDIENTEMENTE — suma manual):
        Mayo: 5310.54 + 5072.00 + 8310.35 = 18692.89
        Junio: 3000.00 + 2000.00 = 5000.00
    """
    out = rf._parse_business_report.__wrapped__(
        _SYNTH_BYDATE_MXN.encode("utf-8"), "synth_mxn.csv"
    )
    assert len(out) == 2, f"Esperaba 2 meses, obtuve {len(out)}"
    assert out[0]["date"] == "2026-05-01"
    assert out[1]["date"] == "2026-06-01"
    assert out[0]["revenue"] == pytest.approx(18692.89, rel=1e-6)
    assert out[1]["revenue"] == pytest.approx(5000.00, rel=1e-6)
    # Sessions: suma directa.
    assert out[0]["sessions"] == 675  # 216 + 234 + 225
    assert out[1]["sessions"] == 180  # 100 + 80
    # Units excluye B2B → mayo: 20+19+30 = 69
    assert out[0]["units"] == 69
    # CVR mayo recalculado: 69 / 675 * 100 = 10.222...
    assert out[0]["cvr"] == pytest.approx(69 / 675 * 100, rel=1e-6)


_SYNTH_BYMONTH_ISO = """\
Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage
2026-01-01,$10000.00,500,5000,10.00%
2026-02-01,$12000.00,600,6000,10.00%
"""


def test_parse_business_report_synthetic_monthly_iso_not_re_aggregated():
    """BR mensual ISO con sessions: detecta como mensual, no re-agrega.
    Mantiene el camino legacy que el demo asumía implícitamente.
    """
    out = rf._parse_business_report.__wrapped__(
        _SYNTH_BYMONTH_ISO.encode("utf-8"), "synth_monthly.csv"
    )
    assert len(out) == 2
    assert out[0]["date"] == "2026-01-01"
    assert out[1]["date"] == "2026-02-01"
    assert out[0]["revenue"] == pytest.approx(10000.0)
    # CVR: mensual ya viene calculado, NO se recalcula (granularidad mensual
    # detectada → no agrega → toma el cvr del map row).
    assert out[0]["cvr"] == pytest.approx(10.0)


_SYNTH_SESSIONLESS = """\
Date,Ordered Product Sales,Units Ordered,Shipped Product Sales
6/1/26,"$6,513.61",520,"$6,135.69"
"""


def test_parse_business_report_rejects_sessionless_report():
    """Reporte sin Sessions (típico: Sales and Orders by Month) → rechazo
    explícito con ReportLacksSessionsError. NO ingerir a medias.
    """
    with pytest.raises(rf.ReportLacksSessionsError) as exc:
        rf._parse_business_report.__wrapped__(
            _SYNTH_SESSIONLESS.encode("utf-8"), "synth_sessionless.csv"
        )
    # Mensaje claro para el AM.
    msg = str(exc.value)
    assert "Sessions" in msg or "tráfico" in msg or "Traffic" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reales — skipif gitignored
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _DERMAGLOS_BYDATE.exists(),
    reason=f"Fixture gitignored ausente: {_DERMAGLOS_BYDATE.name}",
)
def test_parse_real_dermaglos_bydate_aggregates_to_2_months():
    """Dermaglos US by-date real: 59 filas (5/1/26 a 6/28/26, mayo+junio) →
    exactamente 2 filas mensuales tras agregación.

    Valores derivados INDEPENDIENTEMENTE (leyendo el CSV con pandas crudo y
    limpiando con `_clean_money_independent`, no con el parser de M31):
        Mayo 2026: revenue=6066.63, units=459, sessions=4017
        Junio 2026: revenue=6250.04, units=503, sessions=3164

    Estos valores se calcularon ejecutando:
        df = pd.read_csv(fixture, encoding='utf-8-sig')
        df['rev'] = df['Ordered Product Sales'].map(_clean_money_independent)
        df.groupby([year, month]).agg(rev='sum', units='sum', sess='sum')
    """
    data = _DERMAGLOS_BYDATE.read_bytes()
    out = rf._parse_business_report.__wrapped__(data, _DERMAGLOS_BYDATE.name)
    assert len(out) == 2, f"Esperaba 2 meses (mayo+junio), obtuve {len(out)}"
    by_date = {r["date"]: r for r in out}
    assert "2026-05-01" in by_date
    assert "2026-06-01" in by_date
    assert by_date["2026-05-01"]["revenue"] == pytest.approx(6066.63, rel=1e-6)
    assert by_date["2026-06-01"]["revenue"] == pytest.approx(6250.04, rel=1e-6)
    assert by_date["2026-05-01"]["units"] == 459
    assert by_date["2026-06-01"]["units"] == 503
    assert by_date["2026-05-01"]["sessions"] == 4017
    assert by_date["2026-06-01"]["sessions"] == 3164


@pytest.mark.skipif(
    not _DERMAGLOS_BYDATE.exists(),
    reason=f"Fixture gitignored ausente: {_DERMAGLOS_BYDATE.name}",
)
def test_parse_real_dermaglos_independent_derivation_matches():
    """Doble check: derivamos los valores esperados leyendo el fixture
    desde cero con pandas crudo y los comparamos con el output del parser.
    Esto blinda contra placebos (si tocaramos el parser por error, este test
    seguiría detectando divergencia).
    """
    df = pd.read_csv(_DERMAGLOS_BYDATE, encoding="utf-8-sig")
    df["rev_ind"] = df["Ordered Product Sales"].map(_clean_money_independent)
    df["units_ind"] = pd.to_numeric(df["Units Ordered"], errors="coerce").fillna(0)
    df["sess_ind"] = pd.to_numeric(df["Sessions - Total"], errors="coerce").fillna(0)
    # Date es M/D/Y → primer grupo es el MES, no el año.
    extracted = df["Date"].str.extract(r"(?P<month>\d+)/(?P<day>\d+)/(?P<year>\d+)")
    df["month"] = extracted["month"].astype(int)
    expected = df.groupby("month").agg(
        rev=("rev_ind", "sum"),
        units=("units_ind", "sum"),
        sess=("sess_ind", "sum"),
    ).to_dict("index")

    out = rf._parse_business_report.__wrapped__(
        _DERMAGLOS_BYDATE.read_bytes(), _DERMAGLOS_BYDATE.name
    )
    for r in out:
        m = int(r["date"].split("-")[1])
        assert r["revenue"] == pytest.approx(expected[m]["rev"], rel=1e-6)
        assert r["units"] == expected[m]["units"]
        assert r["sessions"] == expected[m]["sess"]


@pytest.mark.skipif(
    not _SETEX_BYDATE.exists(),
    reason=f"Fixture gitignored ausente: {_SETEX_BYDATE.name}",
)
def test_parse_real_setex_mxn_currency_cleaned_correctly():
    """Setex MX by-date real: 44 filas diarias MX$ → revenue del primer día
    se mapea correctamente, NO se pierde por el bug MX$.

    Primer día (5/1/26): "MX$5,310.54" → debe limpiarse a 5310.54 ANTES de
    agregar. El total de mayo derivado independientemente es 193723.99.
    """
    out = rf._parse_business_report.__wrapped__(
        _SETEX_BYDATE.read_bytes(), _SETEX_BYDATE.name
    )
    # Setex MX: 44 filas (5/1 a 6/13 aprox) → mayo (31) + junio (13) = 2 meses.
    by_date = {r["date"]: r for r in out}
    assert "2026-05-01" in by_date, f"Falta mayo, claves: {list(by_date.keys())}"
    # Revenue de mayo derivado independientemente (suma manual de los 31 días
    # con _clean_money_independent): 193723.99 (verificado con pandas crudo).
    assert by_date["2026-05-01"]["revenue"] == pytest.approx(193723.99, rel=1e-6)
    # Si MX$ NO se hubiera limpiado, revenue daría 0 → test falla.
    assert by_date["2026-05-01"]["revenue"] > 100_000


@pytest.mark.skipif(
    not _SETEX_BYDATE.exists(),
    reason=f"Fixture gitignored ausente: {_SETEX_BYDATE.name}",
)
def test_parse_real_setex_independent_derivation_matches():
    """Doble check para Setex: derivar mayo+junio leyendo el CSV crudo y
    comparar con el parser. Defensa anti-placebo igual que Dermaglos.
    """
    df = pd.read_csv(_SETEX_BYDATE, encoding="utf-8-sig")
    df["rev_ind"] = df["Ordered Product Sales"].map(_clean_money_independent)
    df["units_ind"] = pd.to_numeric(df["Units Ordered"], errors="coerce").fillna(0)
    df["sess_ind"] = pd.to_numeric(df["Sessions - Total"], errors="coerce").fillna(0)
    df[["month_str"]] = df["Date"].str.extract(r"(\d+)/")
    df["month"] = df["month_str"].astype(int)
    expected = df.groupby("month").agg(
        rev=("rev_ind", "sum"),
        units=("units_ind", "sum"),
        sess=("sess_ind", "sum"),
    ).to_dict("index")

    out = rf._parse_business_report.__wrapped__(
        _SETEX_BYDATE.read_bytes(), _SETEX_BYDATE.name
    )
    for r in out:
        m = int(r["date"].split("-")[1])
        assert r["revenue"] == pytest.approx(expected[m]["rev"], rel=1e-6), (
            f"Mes {m}: parser={r['revenue']} vs derivado={expected[m]['rev']}"
        )
        assert r["units"] == expected[m]["units"]
        assert r["sessions"] == expected[m]["sess"]


@pytest.mark.skipif(
    not _DERMAGLOS_BYMONTH.exists(),
    reason=f"Fixture gitignored ausente: {_DERMAGLOS_BYMONTH.name}",
)
def test_parse_real_dermaglos_bymonth_rejected_no_sessions():
    """Dermaglos US by-month real: el reporte 'Sales and Orders by Month'
    NO tiene columna Sessions. Debe ser RECHAZADO con
    ReportLacksSessionsError, no ingerido con sessions=0.
    """
    data = _DERMAGLOS_BYMONTH.read_bytes()
    with pytest.raises(rf.ReportLacksSessionsError):
        rf._parse_business_report.__wrapped__(data, _DERMAGLOS_BYMONTH.name)


# ─────────────────────────────────────────────────────────────────────────────
# Regresión: el demo embebido (ISO mensual limpio) sigue funcionando
# ─────────────────────────────────────────────────────────────────────────────

def test_demo_still_loads_23_months_with_correct_shape():
    """Regresión: _DERMAGLOS_DATA sigue siendo 23 meses con shape correcto.
    Defiende el camino del demo ante el refactor del parser.
    """
    assert len(rf._DERMAGLOS_DATA) == 23
    assert rf._DERMAGLOS_DATA[0]["date"] == "2024-06-01"
    assert rf._DERMAGLOS_DATA[-1]["date"] == "2026-04-01"
    expected_keys = {
        "date", "revenue", "revenueB2B", "units",
        "sessions", "pageViews", "buyBox", "cvr",
    }
    for r in rf._DERMAGLOS_DATA:
        assert set(r.keys()) == expected_keys


def test_demo_known_value_preserved():
    """Valor conocido del demo (octubre 2024): revenue=2989.18 — NO debe
    cambiar tras el refactor del parser.
    """
    by_date = {r["date"]: r for r in rf._DERMAGLOS_DATA}
    assert by_date["2024-10-01"]["revenue"] == pytest.approx(2989.18)
    assert by_date["2024-10-01"]["sessions"] == 2382


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de granularidad y agregación (unit puro)
# ─────────────────────────────────────────────────────────────────────────────

def test_detect_granularity_daily():
    """Multiples filas dentro del mismo (año, mes) → 'daily'."""
    rows = [
        {"date": "2026-05-01"}, {"date": "2026-05-02"}, {"date": "2026-05-03"},
    ]
    assert rf._detect_granularity(rows) == "daily"


def test_detect_granularity_monthly():
    """Una fila por (año, mes) → 'monthly'."""
    rows = [
        {"date": "2026-05-01"}, {"date": "2026-06-01"}, {"date": "2026-07-01"},
    ]
    assert rf._detect_granularity(rows) == "monthly"


def test_detect_granularity_edge_cases():
    """0 o 1 fila → 'monthly' (asumir no agregar)."""
    assert rf._detect_granularity([]) == "monthly"
    assert rf._detect_granularity([{"date": "2026-05-01"}]) == "monthly"


def test_aggregate_daily_to_monthly_recalculates_cvr():
    """CVR del mes se RECALCULA como units/sessions*100, NO promedio simple
    de los % diarios (más fiel + evita sesgo).
    """
    rows = [
        # Día 1: 10 units, 100 sessions → cvr individual 10%
        {"date": "2026-05-01", "revenue": 100, "revenueB2B": 0, "units": 10,
         "sessions": 100, "pageViews": 150, "buyBox": 90, "cvr": 10.0},
        # Día 2: 5 units, 200 sessions → cvr individual 2.5%
        {"date": "2026-05-02", "revenue": 50, "revenueB2B": 0, "units": 5,
         "sessions": 200, "pageViews": 300, "buyBox": 95, "cvr": 2.5},
    ]
    out = rf._aggregate_daily_to_monthly(rows)
    assert len(out) == 1
    m = out[0]
    assert m["date"] == "2026-05-01"
    assert m["revenue"] == 150
    assert m["units"] == 15
    assert m["sessions"] == 300
    # CVR recalc: 15 / 300 * 100 = 5.0 (NO promedio simple = (10+2.5)/2 = 6.25).
    assert m["cvr"] == pytest.approx(5.0)
    # BuyBox: promedio simple = (90 + 95) / 2 = 92.5
    assert m["buyBox"] == pytest.approx(92.5)


def test_aggregate_daily_zero_sessions_safe():
    """Si el mes no tiene sessions, cvr=0 (no división por cero)."""
    rows = [
        {"date": "2026-05-01", "revenue": 100, "revenueB2B": 0, "units": 5,
         "sessions": 0, "pageViews": 0, "buyBox": 0, "cvr": 0},
    ]
    out = rf._aggregate_daily_to_monthly(rows)
    assert len(out) == 1
    assert out[0]["cvr"] == 0
