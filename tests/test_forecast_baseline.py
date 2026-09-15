"""Tests B1b — marca de baseline en los snapshots de forecast de M31.

Los snapshots eran estrategias nombradas libres ("Agresivo", "Conservador")
sin jerarquía. El dashboard global necesita saber cuál es el plan oficial
contra el que se mide el cumplimiento.

Modelo: UN baseline por cliente (no por período). La unicidad la garantiza
`_set_baseline_snapshot`, no la UI. Los snapshots guardados antes de B1b no
tienen la key `is_baseline`: toda lectura va con `.get(..., False)`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf


def _fc_row(date: str, revenue: float = 1000.0) -> dict:
    return {"date": date, "revenue": revenue, "spend": 100.0, "ventasPPC": 400.0}


def _client_with_snapshots(*names: str) -> dict:
    """Cliente con un forecast vivo y un snapshot por nombre."""
    cur = rf._new_client(name="T", client_id="t1")
    cur["forecast"] = [_fc_row("2026-10-01"), _fc_row("2026-11-01")]
    for name in names:
        assert rf._save_forecast_snapshot(cur, name, {"horizon": 2}) is not None
    return cur


def _flags(cur: dict) -> list:
    return [s.get("is_baseline", False) for s in cur["snapshots"]]


# ─────────────────────────────────────────────────────────────────────────────
# Flag en snapshots nuevos
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshot_nuevo_nace_sin_baseline():
    cur = _client_with_snapshots("Agresivo")
    assert cur["snapshots"][0]["is_baseline"] is False


# ─────────────────────────────────────────────────────────────────────────────
# _set_baseline_snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_marcar_uno_lo_marca():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    sid = cur["snapshots"][1]["id"]
    assert rf._set_baseline_snapshot(cur, sid) is True
    assert _flags(cur) == [False, True]


def test_marcar_otro_desmarca_el_primero():
    cur = _client_with_snapshots("Agresivo", "Normal", "Conservador")
    ids = [s["id"] for s in cur["snapshots"]]
    rf._set_baseline_snapshot(cur, ids[0])
    rf._set_baseline_snapshot(cur, ids[2])
    assert _flags(cur) == [False, False, True]
    assert sum(_flags(cur)) == 1


def test_toggle_marcar_el_mismo_dos_veces_deja_sin_baseline():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    sid = cur["snapshots"][0]["id"]
    assert rf._set_baseline_snapshot(cur, sid) is True
    assert rf._set_baseline_snapshot(cur, sid) is True
    assert _flags(cur) == [False, False]
    assert rf._get_baseline_snapshot(cur) is None


def test_unicidad_repara_dato_corrupto_con_dos_marcados():
    cur = _client_with_snapshots("A", "B", "C")
    cur["snapshots"][0]["is_baseline"] = True
    cur["snapshots"][1]["is_baseline"] = True
    rf._set_baseline_snapshot(cur, cur["snapshots"][2]["id"])
    assert _flags(cur) == [False, False, True]


def test_id_inexistente_devuelve_false_sin_mutar():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    rf._set_baseline_snapshot(cur, cur["snapshots"][0]["id"])
    before = copy.deepcopy(cur["snapshots"])
    assert rf._set_baseline_snapshot(cur, "no-existe") is False
    assert cur["snapshots"] == before


def test_cliente_sin_snapshots_devuelve_false():
    cur = rf._new_client(name="T", client_id="t1")
    assert rf._set_baseline_snapshot(cur, "x") is False
    assert cur["snapshots"] == []


# ─────────────────────────────────────────────────────────────────────────────
# _get_baseline_snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_get_baseline_none_cuando_no_hay_ninguno():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    assert rf._get_baseline_snapshot(cur) is None


def test_get_baseline_none_sin_snapshots_ni_key():
    cur = rf._new_client(name="T", client_id="t1")
    del cur["snapshots"]
    assert rf._get_baseline_snapshot(cur) is None


def test_get_baseline_devuelve_el_marcado():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    sid = cur["snapshots"][1]["id"]
    rf._set_baseline_snapshot(cur, sid)
    snap = rf._get_baseline_snapshot(cur)
    assert snap is not None and snap["id"] == sid
    assert snap["name"] == "Conservador"


def test_get_baseline_con_dos_marcados_devuelve_el_primero():
    cur = _client_with_snapshots("A", "B")
    cur["snapshots"][0]["is_baseline"] = True
    cur["snapshots"][1]["is_baseline"] = True
    assert rf._get_baseline_snapshot(cur)["name"] == "A"


# ─────────────────────────────────────────────────────────────────────────────
# Retrocompat — snapshots guardados antes de B1b, sin la key
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_client() -> dict:
    cur = _client_with_snapshots("Viejo 1", "Viejo 2")
    for s in cur["snapshots"]:
        del s["is_baseline"]
    return cur


def test_retrocompat_get_baseline_sin_key():
    cur = _legacy_client()
    assert rf._get_baseline_snapshot(cur) is None


def test_retrocompat_set_baseline_sin_key():
    cur = _legacy_client()
    sid = cur["snapshots"][1]["id"]
    assert rf._set_baseline_snapshot(cur, sid) is True
    assert _flags(cur) == [False, True]
    assert rf._get_baseline_snapshot(cur)["id"] == sid


def test_retrocompat_id_inexistente_no_agrega_la_key():
    cur = _legacy_client()
    before = copy.deepcopy(cur["snapshots"])
    assert rf._set_baseline_snapshot(cur, "no-existe") is False
    assert cur["snapshots"] == before


# ─────────────────────────────────────────────────────────────────────────────
# _render_snapshots_section — botón ⭐ vía AppTest
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = str(Path(__file__).resolve().parents[1])

_SNAP_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

cur = rf._new_client(name="T", client_id="t1")
cur["snapshots"] = __SNAPSHOTS__
st.session_state[rf._K_CLIENTS] = [cur]
st.session_state[rf._K_ACTIVE_CLIENT_ID] = "t1"
st.session_state[rf._K_ACCOUNT_MANAGERS] = []
rf._render_snapshots_section(cur)
"""


def _run_snapshots(snapshots: list) -> AppTest:
    script = (
        _SNAP_APP
        .replace("__REPO_ROOT__", _REPO_ROOT)
        .replace("__SNAPSHOTS__", repr(snapshots))
    )
    at = AppTest.from_string(script)
    at.run()
    return at


def test_render_snapshots_muestra_boton_baseline_y_marca_el_nombre():
    cur = _client_with_snapshots("Agresivo", "Conservador")
    rf._set_baseline_snapshot(cur, cur["snapshots"][0]["id"])
    at = _run_snapshots(cur["snapshots"])
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"

    for s in cur["snapshots"]:
        btn = at.button(key=f"rf_snap_baseline_t1_{s['id']}")
        assert btn.label == "⭐"
        assert btn.help

    names = [m.value for m in at.markdown]
    assert "**⭐ Agresivo**" in names
    assert "**Conservador**" in names


def test_render_snapshots_retrocompat_sin_key_no_rompe():
    cur = _legacy_client()
    at = _run_snapshots(cur["snapshots"])
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    assert "**Viejo 1**" in [m.value for m in at.markdown]
