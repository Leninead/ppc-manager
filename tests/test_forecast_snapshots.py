"""Tests de los snapshots de forecast nombrados (M31).

Cubre las 5 funciones PURAS (`_save_forecast_snapshot`, `_list_forecast_snapshots`,
`_load_forecast_snapshot`, `_delete_forecast_snapshot`,
`_build_snapshot_comparison_df`) + el roundtrip de persistencia.

Lo que se blinda acá:

    1. DEEP COPY al guardar — mutar `cur["forecast"]` después NO le cambia los
       números al snapshot. Es la razón de ser del feature: el AM guarda
       "Agresivo", sigue editando overrides, y "Agresivo" tiene que quedar como
       estaba.
    2. Guards de guardado — forecast vacío o nombre vacío → None, nada se
       appendea.
    3. Cargar restaura forecast + seasonality (también por copia: cargar dos
       veces seguidas tiene que dar lo mismo).
    4. Borrar saca de la lista y no toca el forecast activo.
    5. La tabla de comparación tiene 1 fila por snapshot y las 8 columnas de
       totales de `_build_forecast_summary_cards`.
    6. ROUNDTRIP de persistencia — un cliente con snapshots sobrevive a
       `_persist_clients` → `_hydrate_clients` con backend fake en memoria, y el
       payload es JSON-serializable (requisito duro de la tabla
       `forecast_clients`, que guarda el cliente entero como JSON).

NINGÚN test pega a red real ni escribe a disco real (data/).
"""

from __future__ import annotations

import json

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fc_row(date_iso: str, revenue: float, units: float = 10.0,
            sessions: float = 100.0, spend: float = 50.0,
            ventas_ppc: float = 200.0) -> dict:
    """Fila de forecast mínima con lo que leen los summary cards."""
    return {
        "date": date_iso,
        "revenue": revenue,
        "units": units,
        "sessions": sessions,
        "spend": spend,
        "ventasPPC": ventas_ppc,
    }


def _client_con_forecast(client_id: str = "acme") -> dict:
    cur = rf._new_client(name="Acme", client_id=client_id)
    cur["forecast"] = [
        _fc_row("2026-09-01", 1000.0),
        _fc_row("2026-10-01", 1100.0),
    ]
    cur["seasonality"] = {"enabled": True, "indices": [1.0] * 11 + [1.4]}
    return cur


_OPTS = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": False}


# ─────────────────────────────────────────────────────────────────────────────
# 0. Shape — `snapshots` existe en el cliente nuevo
# ─────────────────────────────────────────────────────────────────────────────

def test_new_client_trae_snapshots_vacio():
    """El shape del cliente ya reserva `snapshots` — no hay que migrarlo."""
    assert rf._new_client(name="X", client_id="x")["snapshots"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 1. Guardar — deep copy
# ─────────────────────────────────────────────────────────────────────────────

def test_save_snapshot_deep_copea_el_forecast():
    """🔴 Mutar el forecast activo NO puede tocar un snapshot ya guardado."""
    cur = _client_con_forecast()
    snap = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)
    assert snap is not None

    # El AM sigue editando overrides después de guardar.
    cur["forecast"][0]["revenue"] = 999999.0
    cur["forecast"].append(_fc_row("2026-11-01", 1200.0))

    assert snap["forecast"][0]["revenue"] == 1000.0
    assert len(snap["forecast"]) == 2


def test_save_snapshot_deep_copea_seasonality_y_opts():
    """La estacionalidad y los opts también se congelan al guardar."""
    cur = _client_con_forecast()
    opts = dict(_OPTS)
    snap = rf._save_forecast_snapshot(cur, "Normal", opts)

    cur["seasonality"]["indices"][11] = 2.0
    cur["seasonality"]["enabled"] = False
    opts["horizon"] = 12

    assert snap["seasonality"]["indices"][11] == 1.4
    assert snap["seasonality"]["enabled"] is True
    assert snap["opts"]["horizon"] == 3


def test_save_snapshot_shape_y_append():
    """El snapshot trae las 6 keys del contrato y queda en la lista del cliente."""
    cur = _client_con_forecast()
    snap = rf._save_forecast_snapshot(cur, "  Conservador  ", _OPTS)

    assert set(snap.keys()) == {
        "id", "name", "created_at", "opts", "forecast", "seasonality",
    }
    assert snap["name"] == "Conservador"       # se trimea
    assert snap["id"].startswith("conservador-")
    assert cur["snapshots"] == [snap]


def test_save_snapshot_ids_unicos_con_mismo_nombre():
    """Dos snapshots con el mismo nombre el mismo día NO colisionan de id."""
    cur = _client_con_forecast()
    a = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)
    b = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)

    assert a["id"] != b["id"]
    assert len(cur["snapshots"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Guards
# ─────────────────────────────────────────────────────────────────────────────

def test_save_snapshot_con_forecast_vacio_devuelve_none():
    """Sin forecast no hay nada que guardar — None y lista intacta."""
    cur = rf._new_client(name="Acme", client_id="acme")
    assert rf._save_forecast_snapshot(cur, "Agresivo", _OPTS) is None
    assert cur["snapshots"] == []


def test_save_snapshot_con_nombre_vacio_devuelve_none():
    """Nombre vacío (o sólo espacios) → None, nada se appendea."""
    cur = _client_con_forecast()
    assert rf._save_forecast_snapshot(cur, "", _OPTS) is None
    assert rf._save_forecast_snapshot(cur, "   ", _OPTS) is None
    assert cur["snapshots"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Listar / cargar
# ─────────────────────────────────────────────────────────────────────────────

def test_list_snapshots_vacio_y_poblado():
    cur = _client_con_forecast()
    assert rf._list_forecast_snapshots(cur) == []
    rf._save_forecast_snapshot(cur, "A", _OPTS)
    rf._save_forecast_snapshot(cur, "B", _OPTS)
    assert [s["name"] for s in rf._list_forecast_snapshots(cur)] == ["A", "B"]


def test_load_snapshot_restaura_forecast_y_seasonality():
    cur = _client_con_forecast()
    snap = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)

    # El AM destruye el forecast activo y la estacionalidad.
    cur["forecast"] = [_fc_row("2027-01-01", 5.0)]
    cur["seasonality"] = {"enabled": False, "indices": [1.0] * 12}

    assert rf._load_forecast_snapshot(cur, snap["id"]) is True
    assert len(cur["forecast"]) == 2
    assert cur["forecast"][0]["revenue"] == 1000.0
    assert cur["seasonality"]["enabled"] is True
    assert cur["seasonality"]["indices"][11] == 1.4


def test_load_snapshot_restaura_por_copia():
    """Cargar y después editar el forecast activo NO corrompe el snapshot."""
    cur = _client_con_forecast()
    snap = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)

    rf._load_forecast_snapshot(cur, snap["id"])
    cur["forecast"][0]["revenue"] = 42.0

    assert snap["forecast"][0]["revenue"] == 1000.0
    # Y se puede volver a cargar limpio.
    rf._load_forecast_snapshot(cur, snap["id"])
    assert cur["forecast"][0]["revenue"] == 1000.0


def test_load_snapshot_id_inexistente_devuelve_false():
    cur = _client_con_forecast()
    original = list(cur["forecast"])
    assert rf._load_forecast_snapshot(cur, "no-existe") is False
    assert cur["forecast"] == original


# ─────────────────────────────────────────────────────────────────────────────
# 4. Borrar
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_snapshot_saca_de_la_lista():
    cur = _client_con_forecast()
    a = rf._save_forecast_snapshot(cur, "A", _OPTS)
    b = rf._save_forecast_snapshot(cur, "B", _OPTS)

    assert rf._delete_forecast_snapshot(cur, a["id"]) is True
    assert [s["id"] for s in cur["snapshots"]] == [b["id"]]
    # El forecast activo no se toca.
    assert len(cur["forecast"]) == 2


def test_delete_snapshot_id_inexistente_devuelve_false():
    cur = _client_con_forecast()
    rf._save_forecast_snapshot(cur, "A", _OPTS)
    assert rf._delete_forecast_snapshot(cur, "no-existe") is False
    assert len(cur["snapshots"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Comparación
# ─────────────────────────────────────────────────────────────────────────────

_COLS_TOTALES = [
    "Revenue total", "Units totales", "Sessions totales", "Spend total",
    "Ventas PPC totales", "ACOS prom.", "TACOS prom.", "AOV prom.",
]


def test_comparison_df_una_fila_por_snapshot_y_8_columnas():
    cur = _client_con_forecast()
    a = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)
    cur["forecast"][0]["revenue"] = 3000.0
    b = rf._save_forecast_snapshot(cur, "Conservador", _OPTS)

    df = rf._build_snapshot_comparison_df(cur, [a["id"], b["id"]])

    assert len(df) == 2
    assert list(df.columns) == ["Snapshot"] + _COLS_TOTALES
    assert list(df["Snapshot"]) == ["Agresivo", "Conservador"]
    # Los totales difieren: el snapshot congeló números distintos.
    assert df.loc[0, "Revenue total"] != df.loc[1, "Revenue total"]


def test_comparison_df_ignora_ids_inexistentes():
    cur = _client_con_forecast()
    a = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)
    df = rf._build_snapshot_comparison_df(cur, [a["id"], "fantasma"])
    assert len(df) == 1


def test_comparison_df_sin_matches_devuelve_vacio():
    cur = _client_con_forecast()
    df = rf._build_snapshot_comparison_df(cur, ["fantasma"])
    assert df.empty
    assert list(df.columns) == ["Snapshot"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Roundtrip de persistencia
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshots_sobreviven_roundtrip_de_persistencia(monkeypatch):
    """🔴 `snapshots` viaja dentro del JSON del cliente — sin tabla nueva.

    Persist → hydrate con backend fake en memoria. Si el shape del snapshot
    dejara de ser serializable (ej. un objeto date crudo), este test lo caza:
    se hace `json.dumps` del payload que sale hacia el backend, igual que haría
    Supabase con la columna JSON de `forecast_clients`.
    """
    store: dict = {}

    def fake_save(config, area, cliente, modulo, name):
        assert area == rf.AREA
        assert modulo == rf.MODULE_SLUG
        # Contrato duro de la tabla: el cliente entero tiene que ser JSON.
        store[(cliente, name)] = json.loads(json.dumps(config))

    def fake_list(area, modulo):
        return sorted({c for (c, _n) in store})

    def fake_load(area, cliente, modulo, name):
        return store.get((cliente, name))

    monkeypatch.setattr(rf, "_save_forecast_client", fake_save)
    monkeypatch.setattr(rf, "_list_forecast_clients", fake_list)
    monkeypatch.setattr(rf, "_load_forecast_client", fake_load)

    cur = _client_con_forecast()
    snap = rf._save_forecast_snapshot(cur, "Agresivo", _OPTS)

    state = {
        rf._K_CLIENTS: [cur],
        rf._K_ACTIVE_CLIENT_ID: cur["id"],
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._persist_clients(state=state)

    fresh: dict = {
        rf._K_CLIENTS: [],
        rf._K_ACTIVE_CLIENT_ID: None,
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._hydrate_clients(state=fresh)

    (hidratado,) = fresh[rf._K_CLIENTS]
    assert len(hidratado["snapshots"]) == 1
    rehidratado = hidratado["snapshots"][0]
    assert rehidratado["id"] == snap["id"]
    assert rehidratado["name"] == "Agresivo"
    assert rehidratado["created_at"] == snap["created_at"]
    assert rehidratado["opts"] == _OPTS
    assert len(rehidratado["forecast"]) == 2
    assert rehidratado["forecast"][0]["revenue"] == 1000.0
    assert rehidratado["seasonality"]["indices"][11] == 1.4

    # Y se puede cargar el snapshot rehidratado sobre el cliente rehidratado.
    hidratado["forecast"] = []
    assert rf._load_forecast_snapshot(hidratado, snap["id"]) is True
    assert len(hidratado["forecast"]) == 2
