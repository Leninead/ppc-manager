"""Tests Fase 2 de M31 Revenue Forecast — parser by-date + demo + writers.

Cubre lo que es verificable SIN runtime Streamlit:
    1. `_DERMAGLOS_DATA` tiene 23 registros con los campos esperados (jun-2024
       a abr-2026, shape de 8 keys del HTML L1242).
    2. `_parse_business_report` mapea CSV in-memory a filas del shape by-date,
       con `spend` y `ventasPPC` AUSENTES (los pone `_merge_historical`).
    3. `_map_row_by_date` mapea variantes de columnas Amazon (Total, Browser+
       Mobile, dashes unicode, BOM).
    4. `_merge_historical` agrega meses nuevos, actualiza existentes y
       PRESERVA spend/ventasPPC manuales.
    5. `_load_demo_into_active` puebla `historical` con 23 registros + spend/
       ventasPPC None.
    6. `_update_historical_row` escribe spend/ventasPPC al cliente activo.
    7. `_update_account_config` actualiza marketplace/currency/margin/yoy_mode.
    8. `_build_quick_stats` calcula cards con deltas MoM/YoY del último mes.
    9. `_build_history_df` produce un DataFrame con `_idx` y orden DESC.
   10. Helpers de formato (`_fmt_currency`, `_fmt_num`, `_fmt_pct`, `_parse_num`,
       `_delta_pct`, `_same_month_last_year`).

Estrategia: parser cacheado se invoca via `.__wrapped__` para evitar el
@st.cache_data en tests puros sin runtime Streamlit (NO funciona con
session_state tampoco — todos los writers reciben `state=` parametrizable).
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# _DERMAGLOS_DATA — sanity del demo embebido
# ─────────────────────────────────────────────────────────────────────────────

def test_demo_data_has_23_records():
    """Fiel a L1242: 23 meses jun-2024 a abr-2026."""
    assert len(rf._DERMAGLOS_DATA) == 23


def test_demo_data_first_and_last_dates():
    """Primer registro 2024-06, último 2026-04."""
    assert rf._DERMAGLOS_DATA[0]["date"] == "2024-06-01"
    assert rf._DERMAGLOS_DATA[-1]["date"] == "2026-04-01"


def test_demo_data_shape_keys():
    """Cada registro tiene las 8 keys del shape by-date del HTML."""
    expected = {"date", "revenue", "revenueB2B", "units", "sessions", "pageViews", "buyBox", "cvr"}
    for r in rf._DERMAGLOS_DATA:
        assert set(r.keys()) == expected, f"Demo row con shape distinto: {r}"


def test_demo_data_no_spend_or_ventasPPC():
    """Fiel a L5899: el demo en sí NO incluye spend/ventasPPC; los agrega el
    loader al inyectarlo en el cliente activo.
    """
    for r in rf._DERMAGLOS_DATA:
        assert "spend" not in r
        assert "ventasPPC" not in r


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de formato
# ─────────────────────────────────────────────────────────────────────────────

def test_fmt_currency_default_usd():
    assert rf._fmt_currency(1234.56) == "$1,235"
    assert rf._fmt_currency(1234.56, dec=2) == "$1,234.56"


def test_fmt_currency_none_and_nan():
    assert rf._fmt_currency(None) == "—"
    assert rf._fmt_currency(float("nan")) == "—"


def test_fmt_currency_mxn_uses_dollar_sign():
    """MXN también usa '$' (fiel al map L1251)."""
    assert rf._fmt_currency(1000, currency="MXN") == "$1,000"


def test_fmt_num_and_pct():
    assert rf._fmt_num(1234) == "1,234"
    assert rf._fmt_num(1234.5, dec=1) == "1,234.5"
    assert rf._fmt_pct(12.345) == "12.3%"
    assert rf._fmt_pct(12.345, dec=2) == "12.35%"


def test_parse_num_strips_dollar_comma_pct():
    assert rf._parse_num("$1,234.56") == 1234.56
    assert rf._parse_num("12.5%") == 12.5
    assert rf._parse_num("") == 0.0
    assert rf._parse_num(None) == 0.0
    assert rf._parse_num("abc") == 0.0
    assert rf._parse_num(42) == 42.0


def test_delta_pct_zero_or_none_prev_returns_none():
    """Fiel a L1285: si prev es 0 o falsy, devuelve None."""
    assert rf._delta_pct(110, 100) == pytest.approx(10.0)
    assert rf._delta_pct(90, 100) == pytest.approx(-10.0)
    assert rf._delta_pct(100, 0) is None
    assert rf._delta_pct(100, None) is None
    assert rf._delta_pct(None, 100) is None


def test_same_month_last_year_returns_match():
    """Busca el mismo mes/día del año anterior en la lista."""
    rows = [
        {"date": "2024-06-01", "revenue": 100},
        {"date": "2025-06-01", "revenue": 200},
        {"date": "2025-07-01", "revenue": 250},
    ]
    yoy = rf._same_month_last_year("2025-06-01", rows)
    assert yoy is not None and yoy["revenue"] == 100

    # Sin match: devuelve None.
    assert rf._same_month_last_year("2025-07-01", rows) is None


# ─────────────────────────────────────────────────────────────────────────────
# _map_row_by_date — mapeo Amazon BR → shape by-date
# ─────────────────────────────────────────────────────────────────────────────

def test_map_row_by_date_minimal():
    """CSV mínimo con columnas estándar Amazon."""
    row = {
        "Date": "2025-06-15",
        "Ordered Product Sales": "$1,234.56",
        "Units Ordered": "42",
        "Sessions - Total": "1,000",
        "Page Views - Total": "1,500",
        "Buy Box Percentage": "95%",
        "Unit Session Percentage": "8.5%",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["date"] == "2025-06-15"
    assert out["revenue"] == pytest.approx(1234.56)
    assert out["units"] == 42
    assert out["sessions"] == 1000
    assert out["pageViews"] == 1500
    assert out["buyBox"] == pytest.approx(95.0)
    assert out["cvr"] == pytest.approx(8.5)
    # B2B ausente → 0 (parseNum devuelve 0 si findByKeywords no encontró nada).
    assert out["revenueB2B"] == 0


def test_map_row_by_date_us_date_slash_format():
    """Fiel a L1380: M/D/Y (formato US — NO D/M/Y)."""
    row = {
        "Date": "6/15/25",
        "Ordered Product Sales": "100",
        "Units Ordered": "5",
        "Sessions - Total": "100",
        "Page Views - Total": "150",
        "Buy Box Percentage": "90",
        "Unit Session Percentage": "5",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["date"] == "2025-06-15"


def test_map_row_by_date_sessions_browser_plus_mobile_fallback():
    """Sin Sessions - Total, suma Browser + Mobile App. Fiel a L1397-1400."""
    row = {
        "Date": "2025-06-01",
        "Ordered Product Sales": "100",
        "Units Ordered": "5",
        "Sessions - Browser": "300",
        "Sessions - Mobile App": "200",
        "Page Views - Total": "500",
        "Buy Box Percentage": "90",
        "Unit Session Percentage": "5",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["sessions"] == 500  # 300 + 200


def test_map_row_by_date_excludes_b2b_from_revenue():
    """`revenue` excluye B2B; `revenueB2B` lo captura aparte. Fiel a L1388-1389."""
    row = {
        "Date": "2025-06-01",
        "Ordered Product Sales": "1000",
        "Ordered Product Sales B2B": "150",
        "Units Ordered": "50",
        "Sessions - Total": "100",
        "Page Views - Total": "150",
        "Buy Box Percentage": "90",
        "Unit Session Percentage": "5",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["revenue"] == 1000
    assert out["revenueB2B"] == 150


def test_map_row_by_date_returns_none_without_date():
    """Sin date → None (fiel a L1374)."""
    row = {"Ordered Product Sales": "100", "Units Ordered": "5"}
    assert rf._map_row_by_date(row) is None


def test_map_row_by_date_featured_offer_as_buybox():
    """'Featured Offer' es alias de Buy Box. Fiel a L1412."""
    row = {
        "Date": "2025-06-01",
        "Ordered Product Sales": "100",
        "Units Ordered": "5",
        "Sessions - Total": "100",
        "Page Views - Total": "150",
        "Featured Offer Percentage": "88.5",
        "Unit Session Percentage": "5",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["buyBox"] == pytest.approx(88.5)


def test_map_row_by_date_handles_unicode_dashes():
    """En-dash y em-dash en headers se normalizan a espacio. Fiel a L1357."""
    row = {
        "Date": "2025-06-01",
        "Ordered Product Sales": "100",
        "Units Ordered": "5",
        "Sessions – Total": "100",  # en-dash
        "Page Views — Total": "150",  # em-dash
        "Buy Box Percentage": "90",
        "Unit Session Percentage": "5",
    }
    out = rf._map_row_by_date(row)
    assert out is not None
    assert out["sessions"] == 100
    assert out["pageViews"] == 150


# ─────────────────────────────────────────────────────────────────────────────
# _parse_business_report — bytes in, list of dicts out
# ─────────────────────────────────────────────────────────────────────────────

def _make_csv_bytes(rows: list[dict]) -> bytes:
    """Helper para tests: construye un CSV in-memory desde una lista de dicts."""
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


def test_parse_business_report_csv_returns_sorted_rows():
    """Parseo de CSV in-memory: filas mapeadas y ordenadas asc por date."""
    csv = _make_csv_bytes([
        {
            "Date": "2025-08-01", "Ordered Product Sales": "200",
            "Units Ordered": "10", "Sessions - Total": "500",
            "Page Views - Total": "700", "Buy Box Percentage": "95",
            "Unit Session Percentage": "8",
        },
        {
            "Date": "2025-06-01", "Ordered Product Sales": "100",
            "Units Ordered": "5", "Sessions - Total": "300",
            "Page Views - Total": "450", "Buy Box Percentage": "90",
            "Unit Session Percentage": "6",
        },
        {
            "Date": "2025-07-01", "Ordered Product Sales": "150",
            "Units Ordered": "8", "Sessions - Total": "400",
            "Page Views - Total": "600", "Buy Box Percentage": "92",
            "Unit Session Percentage": "7",
        },
    ])
    # Usamos `.__wrapped__` para esquivar el @st.cache_data en tests puros.
    out = rf._parse_business_report.__wrapped__(csv, "test.csv")
    assert len(out) == 3
    assert [r["date"] for r in out] == ["2025-06-01", "2025-07-01", "2025-08-01"]


def test_parse_business_report_no_spend_or_ventasPPC():
    """El parser NO inicializa spend/ventasPPC — lo hace `_merge_historical`."""
    csv = _make_csv_bytes([{
        "Date": "2025-06-01", "Ordered Product Sales": "100",
        "Units Ordered": "5", "Sessions - Total": "300",
        "Page Views - Total": "450", "Buy Box Percentage": "90",
        "Unit Session Percentage": "6",
    }])
    out = rf._parse_business_report.__wrapped__(csv, "test.csv")
    assert len(out) == 1
    assert "spend" not in out[0]
    assert "ventasPPC" not in out[0]


def test_parse_business_report_xlsx():
    """Parseo XLSX in-memory."""
    df = pd.DataFrame([{
        "Date": "2025-06-01", "Ordered Product Sales": 100,
        "Units Ordered": 5, "Sessions - Total": 300,
        "Page Views - Total": 450, "Buy Box Percentage": 90,
        "Unit Session Percentage": 6,
    }])
    buf = BytesIO()
    df.to_excel(buf, index=False)
    out = rf._parse_business_report.__wrapped__(buf.getvalue(), "test.xlsx")
    assert len(out) == 1
    assert out[0]["date"] == "2025-06-01"
    assert out[0]["revenue"] == 100


def test_parse_business_report_unrecognized_raises_sessionless():
    """CSV sin Date NI Sessions → ReportLacksSessionsError.

    Cambio semántico vs versión pre-fix: antes devolvía `[]` silenciosamente,
    ahora prioriza el check de schema (Sessions ausente = reporte equivocado)
    y lanza error claro. Más útil para el AM que un upload sin feedback.
    """
    csv = b"foo,bar\n1,2\n"
    with pytest.raises(rf.ReportLacksSessionsError):
        rf._parse_business_report.__wrapped__(csv, "junk.csv")


# ─────────────────────────────────────────────────────────────────────────────
# _merge_historical
# ─────────────────────────────────────────────────────────────────────────────

def test_merge_historical_adds_new_months():
    """Meses nuevos van con spend/ventasPPC=None."""
    existing = []
    incoming = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "pageViews": 450, "buyBox": 90, "cvr": 6, "revenueB2B": 0},
        {"date": "2025-07-01", "revenue": 150, "units": 8, "sessions": 400, "pageViews": 600, "buyBox": 92, "cvr": 7, "revenueB2B": 0},
    ]
    merged, added, updated = rf._merge_historical(existing, incoming)
    assert added == 2 and updated == 0
    assert len(merged) == 2
    for r in merged:
        assert r["spend"] is None
        assert r["ventasPPC"] is None


def test_merge_historical_preserves_spend_and_ventasPPC():
    """Si un mes ya existe con spend manual, el merge lo PRESERVA."""
    existing = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "pageViews": 450, "buyBox": 90, "cvr": 6, "revenueB2B": 0, "spend": 25.50, "ventasPPC": 60.0},
    ]
    incoming = [
        # Mismo mes con revenue actualizado, pero el CSV no trae spend/ventasPPC.
        {"date": "2025-06-01", "revenue": 110, "units": 6, "sessions": 320, "pageViews": 470, "buyBox": 91, "cvr": 6.5, "revenueB2B": 0},
    ]
    merged, added, updated = rf._merge_historical(existing, incoming)
    assert added == 0 and updated == 1
    assert merged[0]["revenue"] == 110  # actualizado
    assert merged[0]["spend"] == 25.50  # preservado
    assert merged[0]["ventasPPC"] == 60.0  # preservado


def test_merge_historical_sort_asc():
    """Output ordenado asc por date."""
    existing = [
        {"date": "2025-08-01", "revenue": 200, "units": 10, "sessions": 500, "pageViews": 700, "buyBox": 95, "cvr": 8, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    incoming = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "pageViews": 450, "buyBox": 90, "cvr": 6, "revenueB2B": 0},
        {"date": "2025-07-01", "revenue": 150, "units": 8, "sessions": 400, "pageViews": 600, "buyBox": 92, "cvr": 7, "revenueB2B": 0},
    ]
    merged, _, _ = rf._merge_historical(existing, incoming)
    assert [r["date"] for r in merged] == ["2025-06-01", "2025-07-01", "2025-08-01"]


# ─────────────────────────────────────────────────────────────────────────────
# _load_demo_into_active
# ─────────────────────────────────────────────────────────────────────────────

def test_load_demo_into_active_populates_23_months():
    """Carga del demo: 23 meses, spend/ventasPPC None en cada uno."""
    c = rf._new_client(name="Test", client_id="t1")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "t1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    n = rf._load_demo_into_active(state=state)
    assert n == 23
    cur = rf._cur_client(state=state)
    assert len(cur["historical"]) == 23
    for r in cur["historical"]:
        assert r["spend"] is None
        assert r["ventasPPC"] is None


def test_load_demo_into_active_no_client_returns_zero(isolated_data_root):
    """Sin cliente activo: devuelve 0, no modifica state.

    Usa `isolated_data_root` (conftest): sin él, `_ensure_state` hidrata los
    clientes que haya en el `data/` del repo y el test encuentra un cliente
    activo donde esperaba ninguno.
    """
    state: dict = {}
    rf._ensure_state(state=state)
    assert state[rf._K_CLIENTS] == []
    assert rf._load_demo_into_active(state=state) == 0


def test_load_demo_into_active_does_not_mutate_constant():
    """Cargar demo no muta `_DERMAGLOS_DATA` ni comparte referencias con él."""
    snapshot_first = dict(rf._DERMAGLOS_DATA[0])
    c = rf._new_client(name="Test", client_id="t1")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "t1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._load_demo_into_active(state=state)
    # Mutamos en el cliente → no debería afectar la constante.
    rf._cur_client(state=state)["historical"][0]["spend"] = 99.0
    assert rf._DERMAGLOS_DATA[0] == snapshot_first


# ─────────────────────────────────────────────────────────────────────────────
# _update_historical_row / _update_account_config
# ─────────────────────────────────────────────────────────────────────────────

def test_update_historical_row_writes_spend():
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "spend": None, "ventasPPC": None},
    ]
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "t1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    assert rf._update_historical_row(0, "spend", 42.5, state=state) is True
    assert c["historical"][0]["spend"] == 42.5


def test_update_historical_row_empty_becomes_none():
    """Cadena vacía o None → None (fiel a L2044)."""
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = [{"date": "2025-06-01", "spend": 10.0, "ventasPPC": None}]
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "t1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._update_historical_row(0, "spend", "", state=state)
    assert c["historical"][0]["spend"] is None


def test_update_historical_row_invalid_field_returns_false():
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = [{"date": "2025-06-01", "revenue": 100}]
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}
    # Solo spend y ventasPPC son editables.
    assert rf._update_historical_row(0, "revenue", 999, state=state) is False
    assert c["historical"][0]["revenue"] == 100


def test_update_historical_row_out_of_range_returns_false():
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = []
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}
    assert rf._update_historical_row(99, "spend", 10, state=state) is False


def test_update_account_config_writes_marketplace():
    c = rf._new_client(name="Test", client_id="t1")
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}
    assert rf._update_account_config("marketplace", "MX", state=state) is True
    assert c["marketplace"] == "MX"


def test_update_account_config_invalid_field_returns_false():
    c = rf._new_client(name="Test", client_id="t1")
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}
    assert rf._update_account_config("ghost_field", "X", state=state) is False


# ─────────────────────────────────────────────────────────────────────────────
# _build_quick_stats
# ─────────────────────────────────────────────────────────────────────────────

def test_build_quick_stats_empty_returns_empty():
    assert rf._build_quick_stats([]) == []


def test_build_quick_stats_8_cards_minimum():
    """Sin spend en el último mes: 8 cards (Rev/YoY/Sessions/CVR/Units/AOV/Vel/BB)."""
    hist = [
        {"date": "2025-05-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-06-01", "revenue": 120, "units": 6, "sessions": 350, "cvr": 6.5, "buyBox": 91, "pageViews": 500, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    cards = rf._build_quick_stats(hist)
    assert len(cards) == 8
    # Card 0 = revenue último mes, delta MoM ≈ +20%
    assert cards[0]["label"] == "Revenue último mes"
    assert cards[0]["delta"] == pytest.approx(20.0)
    assert cards[0]["delta_label"] == "MoM"


def test_build_quick_stats_adds_spend_acos_tacos():
    """Con spend + ventasPPC en el último mes: 11 cards (8 + Spend + ACOS + TACOS)."""
    hist = [
        {"date": "2025-05-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-06-01", "revenue": 200, "units": 10, "sessions": 500, "cvr": 7, "buyBox": 92, "pageViews": 700, "revenueB2B": 0, "spend": 30.0, "ventasPPC": 100.0},
    ]
    cards = rf._build_quick_stats(hist)
    labels = [c["label"] for c in cards]
    assert "Spend último mes" in labels
    assert "ACOS real" in labels
    assert "TACOS real" in labels


def test_build_quick_stats_yoy_card_when_history_long_enough():
    """Si hay mismo mes año anterior → card YoY tiene valor + delta."""
    hist = [
        {"date": "2024-06-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-05-01", "revenue": 110, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-06-01", "revenue": 150, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    cards = rf._build_quick_stats(hist)
    yoy_card = next(c for c in cards if c["label"] == "Revenue YoY")
    # Año pasado: 100. Actual: 150. Delta = +50%.
    assert yoy_card["delta"] == pytest.approx(50.0)


# ─────────────────────────────────────────────────────────────────────────────
# _build_history_df
# ─────────────────────────────────────────────────────────────────────────────

def test_build_history_df_empty_has_columns():
    """Sin historial: DataFrame vacío con las columnas esperadas."""
    df = rf._build_history_df([])
    expected_cols = {"_idx", "Mes", "Revenue", "Units", "Sessions", "CVR%", "AOV",
                     "Spend", "Ventas PPC", "ACOS%", "TACOS%"}
    assert set(df.columns) == expected_cols


def test_build_history_df_desc_order_with_idx_preserved():
    """DataFrame ordenado DESC por date, pero _idx preserva el orden original."""
    hist = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-07-01", "revenue": 150, "units": 8, "sessions": 400, "cvr": 7, "buyBox": 92, "pageViews": 600, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-08-01", "revenue": 200, "units": 10, "sessions": 500, "cvr": 8, "buyBox": 95, "pageViews": 700, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    df = rf._build_history_df(hist)
    # DESC: 2025-08-01 primero ("Agosto 2025").
    assert df.iloc[0]["Mes"] == "Agosto 2025"
    assert df.iloc[0]["_idx"] == 2  # tercer registro original
    assert df.iloc[2]["Mes"] == "Junio 2025"
    assert df.iloc[2]["_idx"] == 0


def test_build_history_df_spend_none_becomes_nan():
    """spend None → NaN en el DF (NO '': ver test de dtype abajo, bug G1)."""
    hist = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    df = rf._build_history_df(hist)
    assert pd.isna(df.iloc[0]["Spend"])
    assert pd.isna(df.iloc[0]["Ventas PPC"])
    assert df.iloc[0]["Spend"] != ""
    assert df.iloc[0]["Ventas PPC"] != ""


# Regresión bug G1 — el estado PARCIAL (unos meses con spend, otros sin) es el
# que rompía: mezclar float y '' hacía la columna dtype object, y Streamlit
# 1.43.2 DESHABILITA toda columna Arrow-incompatible (data_editor.py:836-843),
# dejando las celdas Spend / Ventas PPC sin aceptar teclado. Estos tests fijan
# el dtype numérico para que el sentinel '' no pueda volver.

_G1_EDITABLE_COLS = ["Spend", "Ventas PPC", "ACOS%", "TACOS%"]


def _g1_partial_hist():
    """3 meses: el del medio con spend/ventasPPC cargados, los otros vacíos."""
    base = dict(revenue=1000.0, units=10, sessions=300, cvr=6,
                buyBox=90, pageViews=450, revenueB2B=0)
    return [
        {"date": "2025-06-01", **base, "spend": None, "ventasPPC": None},
        {"date": "2025-07-01", **base, "spend": 100.0, "ventasPPC": 400.0},
        {"date": "2025-08-01", **base, "spend": None, "ventasPPC": None},
    ]


def test_build_history_df_partial_cols_are_numeric_not_object():
    """Estado parcial: las 4 columnas numéricas NO pueden ser dtype object.

    dtype object == Arrow-incompatible == Streamlit deshabilita la columna.
    """
    df = rf._build_history_df(_g1_partial_hist())
    for col in _G1_EDITABLE_COLS:
        assert df[col].dtype != object, (
            f"'{col}' quedó dtype object en estado parcial — vuelve el bug G1: "
            f"Streamlit deshabilitaría la columna. Valores: {list(df[col])}"
        )
        assert pd.api.types.is_numeric_dtype(df[col]), (
            f"'{col}' no es numérica: dtype={df[col].dtype}"
        )


def test_build_history_df_partial_empty_cells_are_nan_not_empty_string():
    """Las celdas vacías del estado parcial son NaN, nunca ''."""
    df = rf._build_history_df(_g1_partial_hist())
    # DESC: iloc[0]=agosto (vacío), iloc[1]=julio (cargado), iloc[2]=junio (vacío).
    assert df.iloc[1]["Spend"] == pytest.approx(100.0)
    for row in (0, 2):
        for col in _G1_EDITABLE_COLS:
            val = df.iloc[row][col]
            assert not isinstance(val, str), f"'{col}' fila {row} es str: {val!r}"
            assert pd.isna(val), f"'{col}' fila {row} debería ser NaN, es {val!r}"


def test_build_history_df_partial_is_arrow_compatible():
    """La prueba de fuego: el df del estado parcial serializa a Arrow.

    Es exactamente el check que corre Streamlit antes de decidir si deshabilita
    la columna (dataframe_util.is_colum_type_arrow_incompatible).
    """
    pa = pytest.importorskip("pyarrow")
    df = rf._build_history_df(_g1_partial_hist())
    table = pa.Table.from_pandas(df, preserve_index=False)  # no debe levantar
    types = {f.name: str(f.type) for f in table.schema}
    for col in _G1_EDITABLE_COLS:
        assert types[col] in ("double", "float"), (
            f"'{col}' llegó a Arrow como {types[col]} — NumberColumn necesita numérico"
        )


def test_update_historical_row_nan_becomes_none():
    """Vaciar una celda devuelve NaN: no debe entrar NaN al historical.

    NaN rompe json.dumps del path de persistencia (JSON inválido).
    """
    hist = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": 50.0, "ventasPPC": 200.0},
    ]
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = hist
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}

    assert rf._update_historical_row(0, "spend", float("nan"), state=state) is True
    assert c["historical"][0]["spend"] is None
    assert rf._update_historical_row(0, "ventasPPC", float("nan"), state=state) is True
    assert c["historical"][0]["ventasPPC"] is None


def test_build_history_df_computes_acos_tacos():
    """Con spend y ventasPPC: ACOS = spend/vppc*100, TACOS = spend/rev*100."""
    hist = [
        {"date": "2025-06-01", "revenue": 200, "units": 10, "sessions": 500, "cvr": 7, "buyBox": 92, "pageViews": 700, "revenueB2B": 0, "spend": 30.0, "ventasPPC": 100.0},
    ]
    df = rf._build_history_df(hist)
    assert df.iloc[0]["ACOS%"] == pytest.approx(30.0)  # 30/100*100
    assert df.iloc[0]["TACOS%"] == pytest.approx(15.0)  # 30/200*100


# ─────────────────────────────────────────────────────────────────────────────
# _apply_history_edits — round trip
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_history_edits_round_trip():
    """Editar el DF y aplicarlo escribe los spend/ventasPPC al state."""
    hist = [
        {"date": "2025-06-01", "revenue": 100, "units": 5, "sessions": 300, "cvr": 6, "buyBox": 90, "pageViews": 450, "revenueB2B": 0, "spend": None, "ventasPPC": None},
        {"date": "2025-07-01", "revenue": 150, "units": 8, "sessions": 400, "cvr": 7, "buyBox": 92, "pageViews": 600, "revenueB2B": 0, "spend": None, "ventasPPC": None},
    ]
    c = rf._new_client(name="Test", client_id="t1")
    c["historical"] = hist
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "t1", rf._K_ACCOUNT_MANAGERS: []}

    df = rf._build_history_df(hist)
    # El DF está DESC: iloc[0] es julio (_idx=1), iloc[1] es junio (_idx=0).
    df.at[0, "Spend"] = 22.0
    df.at[0, "Ventas PPC"] = 80.0
    df.at[1, "Spend"] = 10.0

    written = rf._apply_history_edits(df, state=state)
    assert written == 2
    # _idx=1 → julio: spend=22, vppc=80.
    assert c["historical"][1]["spend"] == 22.0
    assert c["historical"][1]["ventasPPC"] == 80.0
    # _idx=0 → junio: spend=10, vppc seguía None.
    assert c["historical"][0]["spend"] == 10.0
    assert c["historical"][0]["ventasPPC"] is None
