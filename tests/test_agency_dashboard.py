"""Tests B2 — agregador cross-cuenta del dashboard global de agencia.

`_build_agency_dashboard(periods, clients)` es una función PURA: recibe los
clientes ya cargados y la ventana de meses, y devuelve por cuenta y por mes el
actual, el forecast (del baseline) y el cumplimiento por métrica. Ningún test de
esta sección toca disco.

`_load_agency_clients()` es la única función del módulo que toca disco; sus
tests la aíslan en un tmp_path.
"""
from __future__ import annotations

import copy
import json

import pytest

from core import agency_dashboard as ad
from core import forecast_persistence as fp
from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Builders de clientes (sin disco)
# ─────────────────────────────────────────────────────────────────────────────

def _hist(date: str, revenue=1000.0, spend=None, ventas_ppc=None, **extra) -> dict:
    return {"date": date, "revenue": revenue, "units": 10, "sessions": 300,
            "cvr": 3.3, "spend": spend, "ventasPPC": ventas_ppc, **extra}


def _fc(date: str, revenue=1000.0, spend=100.0, ventas_ppc=400.0,
        acos=25.0, tacos=10.0, acos_target=25.0, tacos_target=None) -> dict:
    return {"date": date, "revenue": revenue, "spend": spend,
            "ventasPPC": ventas_ppc, "acos": acos, "tacos": tacos,
            "acosTarget": acos_target, "tacosTarget": tacos_target}


def _client(name: str, client_id: str | None = None, historical=None, actual=None,
            baseline_rows=None, currency="USD") -> dict:
    cur = rf._new_client(name=name, client_id=client_id or name.lower(),
                         currency=currency)
    cur["historical"] = historical or []
    cur["actual"] = actual or []
    if baseline_rows is not None:
        cur["forecast"] = baseline_rows
        snap = rf._save_forecast_snapshot(cur, "Plan oficial", {"horizon": 12})
        rf._set_baseline_snapshot(cur, snap["id"])
        cur["forecast"] = []   # el agregador NO lee el forecast vivo
    return cur


def _cell(dash: dict, name: str, period: str) -> dict:
    acc = next(a for a in dash["accounts"] if a["name"] == name)
    return acc["months"][period]


_ACC_KEYS = {"revenue", "ventasPPC", "spend", "acos", "tacos"}


# ─────────────────────────────────────────────────────────────────────────────
# Estructura
# ─────────────────────────────────────────────────────────────────────────────

def test_periods_vacio_devuelve_estructura_vacia_sin_romper():
    c = _client("Dermaglos", baseline_rows=[_fc("2026-08-01")])
    dash = ad._build_agency_dashboard([], clients=[c])
    assert dash["periods"] == []
    assert len(dash["accounts"]) == 1
    assert dash["accounts"][0]["months"] == {}


def test_clients_vacio_devuelve_accounts_vacio():
    dash = ad._build_agency_dashboard(["2026-08"], clients=[])
    assert dash == {"periods": ["2026-08"], "accounts": []}


def test_periods_se_devuelven_tal_cual_entraron():
    periods = ["2026-09", "2026-07", "2026-08"]
    dash = ad._build_agency_dashboard(periods, clients=[_client("A")])
    assert dash["periods"] == periods
    assert dash["periods"] is not periods          # copia, no la misma lista
    assert list(dash["accounts"][0]["months"]) == periods


def test_shape_de_cuenta_y_celda():
    c = _client("Dermaglos", client_id="derm-1", currency="MXN",
                historical=[_hist("2026-08-01", revenue=900.0, spend=90.0,
                                  ventas_ppc=300.0)],
                baseline_rows=[_fc("2026-08-01")])
    dash = ad._build_agency_dashboard(["2026-08"], clients=[c])
    acc = dash["accounts"][0]
    assert set(acc) == {"client_id", "name", "currency", "has_baseline",
                        "baseline_name", "baseline_created_at", "months"}
    assert (acc["client_id"], acc["name"], acc["currency"]) == ("derm-1", "Dermaglos", "MXN")
    assert acc["has_baseline"] is True
    assert acc["baseline_name"] == "Plan oficial"
    assert acc["baseline_created_at"] == rf._get_baseline_snapshot(c)["created_at"]
    cell = acc["months"]["2026-08"]
    assert set(cell) == {"actual", "forecast", "accomplishment", "partial"}
    assert set(cell["accomplishment"]) == _ACC_KEYS


def test_no_muta_los_clientes_de_entrada():
    c = _client("A", historical=[_hist("2026-08-01", spend=10.0, ventas_ppc=40.0)],
                baseline_rows=[_fc("2026-08-01", acos=0.0, acos_target=None)])
    before = copy.deepcopy(c)
    ad._build_agency_dashboard(["2026-08"], clients=[c])
    assert c == before


def test_determinismo_dos_corridas_mismo_output():
    clients = [
        _client("Zeta", historical=[_hist("2026-08-01", spend=5.0)],
                baseline_rows=[_fc("2026-08-01")]),
        _client("alfa", baseline_rows=[_fc("2026-08-01")]),
    ]
    a = ad._build_agency_dashboard(["2026-08"], clients=clients)
    b = ad._build_agency_dashboard(["2026-08"], clients=list(reversed(clients)))
    assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# Regla 1 — accomplishment % de revenue / ad sales / spend
# ─────────────────────────────────────────────────────────────────────────────

def test_accomplishment_revenue_ad_sales_spend():
    c = _client("A",
                historical=[_hist("2026-08-01", revenue=900.0, spend=120.0,
                                  ventas_ppc=300.0)],
                baseline_rows=[_fc("2026-08-01", revenue=1000.0, spend=100.0,
                                   ventas_ppc=400.0)])
    acc = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A",
                "2026-08")["accomplishment"]
    assert acc["revenue"] == 90.0
    assert acc["spend"] == 120.0
    assert acc["ventasPPC"] == 75.0


def test_accomplishment_forecast_cero_es_none():
    c = _client("A",
                historical=[_hist("2026-08-01", revenue=900.0, spend=50.0,
                                  ventas_ppc=200.0)],
                baseline_rows=[_fc("2026-08-01", revenue=0.0, spend=0.0,
                                   ventas_ppc=0.0)])
    acc = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A",
                "2026-08")["accomplishment"]
    assert acc["revenue"] is None
    assert acc["spend"] is None
    assert acc["ventasPPC"] is None


def test_accomplishment_actual_none_es_none():
    c = _client("A", baseline_rows=[_fc("2026-08-01")])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["actual"] is None
    assert cell["forecast"] is not None
    assert all(v is None for v in cell["accomplishment"].values())


def test_accomplishment_forecast_none_es_none():
    c = _client("A", historical=[_hist("2026-08-01", spend=10.0, ventas_ppc=40.0)],
                baseline_rows=[_fc("2026-09-01")])     # baseline no cubre agosto
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["actual"] is not None
    assert cell["forecast"] is None
    assert all(v is None for v in cell["accomplishment"].values())


def test_accomplishment_metrica_faltante_en_el_real_es_none():
    """Spend cargado pero ventasPPC no: spend se mide, ad sales no."""
    c = _client("A", historical=[_hist("2026-08-01", revenue=900.0, spend=50.0,
                                       ventas_ppc=None)],
                baseline_rows=[_fc("2026-08-01", revenue=1000.0, spend=100.0)])
    acc = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A",
                "2026-08")["accomplishment"]
    assert acc["spend"] == 50.0
    assert acc["ventasPPC"] is None
    assert acc["acos"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Regla 2 — ACOS / TACOS en delta de puntos, signo crudo
# ─────────────────────────────────────────────────────────────────────────────

def test_acos_delta_en_puntos_no_porcentaje():
    """Real 31 vs target 30 → +1.0 punto. NO 103.33."""
    c = _client("A", historical=[_hist("2026-08-01", revenue=10000.0, spend=310.0,
                                       ventas_ppc=1000.0)],        # ACOS real 31
                baseline_rows=[_fc("2026-08-01", acos=30.0, acos_target=30.0)])
    acc = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A",
                "2026-08")["accomplishment"]
    assert acc["acos"] == pytest.approx(1.0)
    assert acc["acos"] != pytest.approx(31.0 / 30.0 * 100)


def test_acos_signo_positivo_es_real_por_encima_negativo_por_debajo():
    """Signo crudo real - forecast. Positivo en ACOS es PEOR; el agregador no lo
    invierte (lo colorea B3)."""
    arriba = _client("Arriba", historical=[_hist("2026-08-01", spend=35.0,
                                                 ventas_ppc=100.0)],   # 35
                     baseline_rows=[_fc("2026-08-01", acos=30.0, acos_target=30.0)])
    abajo = _client("Abajo", historical=[_hist("2026-08-01", spend=25.0,
                                               ventas_ppc=100.0)],     # 25
                    baseline_rows=[_fc("2026-08-01", acos=30.0, acos_target=30.0)])
    dash = ad._build_agency_dashboard(["2026-08"], clients=[arriba, abajo])
    assert _cell(dash, "Arriba", "2026-08")["accomplishment"]["acos"] == pytest.approx(5.0)
    assert _cell(dash, "Abajo", "2026-08")["accomplishment"]["acos"] == pytest.approx(-5.0)


def test_tacos_delta_en_puntos_no_porcentaje():
    """TACOS real 11 vs forecast 10 → +1.0 punto, y -2 cuando va por debajo."""
    arriba = _client("Arriba", historical=[_hist("2026-08-01", revenue=1000.0,
                                                 spend=110.0, ventas_ppc=400.0)],
                     baseline_rows=[_fc("2026-08-01", tacos=10.0)])
    abajo = _client("Abajo", historical=[_hist("2026-08-01", revenue=1000.0,
                                               spend=80.0, ventas_ppc=400.0)],
                    baseline_rows=[_fc("2026-08-01", tacos=10.0)])
    dash = ad._build_agency_dashboard(["2026-08"], clients=[arriba, abajo])
    up = _cell(dash, "Arriba", "2026-08")["accomplishment"]["tacos"]
    down = _cell(dash, "Abajo", "2026-08")["accomplishment"]["tacos"]
    assert up == pytest.approx(1.0) and up != pytest.approx(110.0)
    assert down == pytest.approx(-2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Regla 3 — ACOS / TACOS proyectado 0.0 sin target cargado → None
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sin_target", [None, "", float("nan"), "__absent__"])
def test_acos_forecast_cero_sin_acos_target_es_none(sin_target):
    row = _fc("2026-08-01", acos=0.0, acos_target=sin_target)
    if sin_target == "__absent__":
        del row["acosTarget"]
    c = _client("A", historical=[_hist("2026-08-01", spend=30.0, ventas_ppc=100.0)],
                baseline_rows=[row])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["forecast"]["acos"] is None
    assert cell["accomplishment"]["acos"] is None
    # El resto del forecast no se toca.
    assert cell["forecast"]["revenue"] == 1000.0


def test_acos_forecast_cero_con_acos_target_cero_explicito_se_respeta():
    c = _client("A", historical=[_hist("2026-08-01", spend=30.0, ventas_ppc=100.0)],
                baseline_rows=[_fc("2026-08-01", acos=0.0, acos_target=0.0)])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["forecast"]["acos"] == 0.0
    assert cell["accomplishment"]["acos"] == pytest.approx(30.0)


def test_acos_forecast_distinto_de_cero_sin_target_no_se_toca():
    """La regla es SOLO para el 0.0: un valor no nulo es un número real."""
    c = _client("A", historical=[_hist("2026-08-01", spend=30.0, ventas_ppc=100.0)],
                baseline_rows=[_fc("2026-08-01", acos=25.0, acos_target=None)])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["forecast"]["acos"] == 25.0


def test_tacos_forecast_cero_sin_tacos_target_es_none():
    c = _client("A", historical=[_hist("2026-08-01", revenue=1000.0, spend=30.0,
                                       ventas_ppc=100.0)],
                baseline_rows=[_fc("2026-08-01", tacos=0.0, tacos_target=None)])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["forecast"]["tacos"] is None
    assert cell["accomplishment"]["tacos"] is None


def test_tacos_forecast_cero_con_tacos_target_cero_explicito_se_respeta():
    c = _client("A", historical=[_hist("2026-08-01", revenue=1000.0, spend=30.0,
                                       ventas_ppc=100.0)],
                baseline_rows=[_fc("2026-08-01", tacos=0.0, tacos_target=0.0)])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["forecast"]["tacos"] == 0.0
    assert cell["accomplishment"]["tacos"] == pytest.approx(3.0)


# ─────────────────────────────────────────────────────────────────────────────
# Regla 4 — MtD parcial crudo, sin prorrateo
# ─────────────────────────────────────────────────────────────────────────────

def test_partial_viaja_a_la_celda_y_no_se_prorratea():
    c = _client("A",
                actual=[_hist("2026-08-01", revenue=400.0, spend=40.0,
                              ventas_ppc=160.0, partial=True, days_covered=12)],
                baseline_rows=[_fc("2026-08-01", revenue=1000.0, spend=100.0,
                                   ventas_ppc=400.0)])
    cell = _cell(ad._build_agency_dashboard(["2026-08"], clients=[c]), "A", "2026-08")
    assert cell["partial"] is True
    # Crudo: 400 / 1000, NO 400 / (1000 * 12/31).
    assert cell["accomplishment"]["revenue"] == 40.0
    assert cell["accomplishment"]["spend"] == 40.0


def test_partial_de_historical_es_false_y_sin_actual_es_none():
    c = _client("A", historical=[_hist("2026-07-01", spend=10.0)],
                baseline_rows=[_fc("2026-07-01")])
    dash = ad._build_agency_dashboard(["2026-07", "2026-08"], clients=[c])
    assert _cell(dash, "A", "2026-07")["partial"] is False
    assert _cell(dash, "A", "2026-08")["partial"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Cuentas sin baseline, orden, mes sin datos
# ─────────────────────────────────────────────────────────────────────────────

def test_cuenta_sin_baseline_entra_con_todo_en_none():
    c = _client("SinPlan", historical=[_hist("2026-08-01", spend=10.0,
                                             ventas_ppc=40.0)])
    dash = ad._build_agency_dashboard(["2026-08", "2026-09"], clients=[c])
    acc = dash["accounts"][0]
    assert acc["has_baseline"] is False
    assert acc["baseline_name"] is None and acc["baseline_created_at"] is None
    for period in ("2026-08", "2026-09"):
        cell = acc["months"][period]
        assert cell["forecast"] is None
        assert all(v is None for v in cell["accomplishment"].values())
    assert acc["months"]["2026-08"]["actual"]["spend"] == 10.0


def test_accounts_ordenadas_alfabeticamente_por_nombre():
    clients = [_client("setex"), _client("Dermaglos"), _client("LTD"),
               _client("mott & bow")]
    dash = ad._build_agency_dashboard(["2026-08"], clients=clients)
    assert [a["name"] for a in dash["accounts"]] == [
        "Dermaglos", "LTD", "mott & bow", "setex",
    ]


def test_mes_en_ninguna_capa_celda_vacia():
    c = _client("A", historical=[_hist("2026-06-01", spend=10.0)],
                baseline_rows=[_fc("2026-06-01")])
    cell = _cell(ad._build_agency_dashboard(["2026-11"], clients=[c]), "A", "2026-11")
    assert cell["actual"] is None
    assert cell["forecast"] is None
    assert cell["partial"] is None
    assert all(v is None for v in cell["accomplishment"].values())


# ─────────────────────────────────────────────────────────────────────────────
# _load_agency_clients — la única que toca disco (aislada en tmp_path)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def local_forecast_root(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "DATA_ROOT", tmp_path)
    fp._set_backend_for_testing(fp._LocalBackend())
    for f in (fp._list_forecast_clients, fp._load_forecast_client):
        if hasattr(f, "clear"):
            f.clear()
    yield tmp_path
    fp._set_backend_for_testing(None)
    for f in (fp._list_forecast_clients, fp._load_forecast_client):
        if hasattr(f, "clear"):
            f.clear()


def _write_client(root, slug: str, payload) -> None:
    d = root / rf.AREA / slug / rf.MODULE_SLUG
    d.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (d / "client.json").write_text(text, encoding="utf-8")


def test_load_agency_clients_saltea_meta_vacios_y_corruptos(local_forecast_root):
    _write_client(local_forecast_root, "beta", _client("Beta", client_id="beta"))
    _write_client(local_forecast_root, "alfa", _client("Alfa", client_id="alfa"))
    _write_client(local_forecast_root, "vacio", {})
    _write_client(local_forecast_root, "roto", "{no es json")
    meta = local_forecast_root / rf.AREA / "_meta" / rf.MODULE_SLUG
    meta.mkdir(parents=True)
    (meta / "active.json").write_text('{"active_client_id": "alfa"}', encoding="utf-8")
    # Carpeta de cliente sin client.json (solo otro archivo).
    _write_client(local_forecast_root, "sin_client", {"x": 1})
    (local_forecast_root / rf.AREA / "sin_client" / rf.MODULE_SLUG / "client.json").rename(
        local_forecast_root / rf.AREA / "sin_client" / rf.MODULE_SLUG / "otro.json")

    loaded = ad._load_agency_clients()
    assert sorted(c["id"] for c in loaded) == ["alfa", "beta"]


def test_load_agency_clients_sin_datos_devuelve_lista_vacia(local_forecast_root):
    assert ad._load_agency_clients() == []


def test_build_sin_clients_carga_desde_disco(local_forecast_root):
    _write_client(local_forecast_root, "alfa",
                  _client("Alfa", client_id="alfa",
                          baseline_rows=[_fc("2026-08-01")]))
    dash = ad._build_agency_dashboard(["2026-08"])
    assert [a["client_id"] for a in dash["accounts"]] == ["alfa"]
    assert dash["accounts"][0]["has_baseline"] is True
