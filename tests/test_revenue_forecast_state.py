"""Tests Fase 1 de M31 Revenue Forecast — state + accessors + persistencia dormida.

Cubre lo que es verificable SIN runtime Streamlit:
    1. `_new_client` shape + defaults + indices len 12 + created_at runtime.
    2. `_ensure_state` idempotente.
    3. `_set_active_client` / `_cur_client` (con state simulado vía dict).
    4. Getters `_get_historical` / `_get_forecast` / `_get_seasonality` /
       `_get_asins` / `_get_selected_asin`.
    5. `_PERSISTENCE_ENABLED is False` (sanity: la persistencia debe estar
       dormida en F1; si Fase 2+ la enciende, este test ROMPE a propósito
       y obliga a revisar el wiring de hidratación / persistencia).
    6. `_persist_clients` / `_hydrate_clients` son no-op cuando el flag está
       en False (no tocan disco, no llaman a core.persistence).

Estrategia: los accessors aceptan `state` como parámetro opcional con default
`st.session_state`. En tests pasamos un dict simulado — esto elimina la
dependencia de runtime Streamlit y mantiene los tests puros.
"""

from __future__ import annotations

from datetime import date

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# _new_client — shape + defaults
# ─────────────────────────────────────────────────────────────────────────────

def test_new_client_shape_keys():
    """Shape completo: 15 keys del contrato F1."""
    c = rf._new_client(name="Acme")
    expected_keys = {
        "id", "name", "marketplace", "am_id", "margin", "currency", "yoy_mode",
        "historical", "forecast", "snapshots", "seasonality", "asins",
        "selected_asin", "created_at",
    }
    # Permitimos extra keys si Fase 2+ agrega, pero todas las del contrato F1
    # deben estar presentes.
    assert expected_keys.issubset(set(c.keys())), (
        f"Faltan keys: {expected_keys - set(c.keys())}"
    )


def test_new_client_defaults_neutros():
    """Defaults neutros: margin 0.30, USD, US, yoy_mode auto, sin am, etc."""
    c = rf._new_client(name="Acme")
    assert c["name"] == "Acme"
    assert c["marketplace"] == "US"
    assert c["am_id"] is None
    assert c["margin"] == 0.30
    assert c["currency"] == "USD"
    assert c["yoy_mode"] == "auto"
    assert c["historical"] == []
    assert c["forecast"] == []
    assert c["snapshots"] == []
    assert c["asins"] == []
    assert c["selected_asin"] is None


def test_new_client_seasonality_default():
    """seasonality: dict con `enabled` False + 12 indices neutros (1.0)."""
    c = rf._new_client(name="Acme")
    s = c["seasonality"]
    assert s["enabled"] is False
    assert isinstance(s["indices"], list)
    assert len(s["indices"]) == 12
    assert all(x == 1.0 for x in s["indices"])


def test_new_client_created_at_is_today_iso():
    """created_at se genera al call-time (no en import-time).

    Validación: matchea la fecha de hoy en ISO. Si el constructor cacheara la
    fecha de import del módulo, fallaría tras un cambio de día.
    """
    c = rf._new_client(name="Acme")
    assert c["created_at"] == date.today().isoformat()


def test_new_client_explicit_id():
    """client_id explícito se respeta (útil para tests determinísticos)."""
    c = rf._new_client(name="Acme", client_id="my-fixed-id")
    assert c["id"] == "my-fixed-id"


def test_new_client_generated_id_uses_slug():
    """Sin client_id explícito, se genera del slug del name + fecha."""
    c = rf._new_client(name="Acme Brand")
    today = date.today().isoformat()
    assert c["id"] == f"acme-brand-{today}"


def test_new_client_custom_params():
    """Custom params se reflejan en el shape (marketplace, currency, margin, yoy_mode)."""
    c = rf._new_client(
        name="MX Brand",
        marketplace="MX",
        am_id="am-007",
        margin=0.45,
        currency="MXN",
        yoy_mode="manual",
    )
    assert c["marketplace"] == "MX"
    assert c["am_id"] == "am-007"
    assert c["margin"] == 0.45
    assert c["currency"] == "MXN"
    assert c["yoy_mode"] == "manual"


# ─────────────────────────────────────────────────────────────────────────────
# _ensure_state — idempotencia
# ─────────────────────────────────────────────────────────────────────────────

def test_ensure_state_seeds_empty_keys(isolated_data_root):
    """Sobre un dict vacío, siembra las 3 keys con defaults.

    Usa `isolated_data_root` (conftest): `_ensure_state` hidrata desde disco, y
    un cliente —o incluso sólo el puntero huérfano `_meta/.../active.json`—
    dejado por una validación en la app hace que `active_client_id` NO sea None.
    """
    state: dict = {}
    rf._ensure_state(state=state)
    assert state[rf._K_CLIENTS] == []
    assert state[rf._K_ACCOUNT_MANAGERS] == []
    assert state[rf._K_ACTIVE_CLIENT_ID] is None


def test_ensure_state_idempotente_no_pisa_existentes():
    """Si una key ya existe (aunque sea con datos), NO se pisa."""
    existing_client = rf._new_client(name="Pre-existing", client_id="pre-1")
    state = {
        rf._K_CLIENTS: [existing_client],
        rf._K_ACTIVE_CLIENT_ID: "pre-1",
    }
    rf._ensure_state(state=state)
    assert state[rf._K_CLIENTS] == [existing_client]
    assert state[rf._K_ACTIVE_CLIENT_ID] == "pre-1"
    # account_managers no existía → se debe haber seedeado vacío
    assert state[rf._K_ACCOUNT_MANAGERS] == []


def test_ensure_state_multiple_calls_no_op():
    """Llamar N veces no acumula ni muta."""
    state: dict = {}
    rf._ensure_state(state=state)
    snapshot = {k: list(v) if isinstance(v, list) else v for k, v in state.items()}
    rf._ensure_state(state=state)
    rf._ensure_state(state=state)
    for k, v in snapshot.items():
        assert state[k] == v


# ─────────────────────────────────────────────────────────────────────────────
# _set_active_client / _cur_client
# ─────────────────────────────────────────────────────────────────────────────

def test_cur_client_returns_none_when_no_active():
    """Sin id activo seteado, _cur_client devuelve None."""
    state: dict = {}
    rf._ensure_state(state=state)
    assert rf._cur_client(state=state) is None


def test_cur_client_returns_none_when_id_not_found():
    """Si el id activo no matchea ningún cliente, devuelve None (fail-soft)."""
    state = {
        rf._K_CLIENTS: [rf._new_client(name="A", client_id="a")],
        rf._K_ACTIVE_CLIENT_ID: "ghost-id",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    assert rf._cur_client(state=state) is None


def test_cur_client_returns_active():
    """Devuelve el dict del cliente cuyo id matchea el activo."""
    c1 = rf._new_client(name="A", client_id="a")
    c2 = rf._new_client(name="B", client_id="b")
    state = {
        rf._K_CLIENTS: [c1, c2],
        rf._K_ACTIVE_CLIENT_ID: "b",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    cur = rf._cur_client(state=state)
    assert cur is c2  # mismo objeto (no copy)


def test_set_active_client_success():
    """Setear un id válido devuelve True y aplica el cambio."""
    c = rf._new_client(name="A", client_id="a")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: None,
        rf._K_ACCOUNT_MANAGERS: [],
    }
    result = rf._set_active_client("a", state=state)
    assert result is True
    assert state[rf._K_ACTIVE_CLIENT_ID] == "a"


def test_set_active_client_invalid_id_fail_soft():
    """Setear un id inexistente devuelve False y NO cambia el activo."""
    c = rf._new_client(name="A", client_id="a")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "a",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    result = rf._set_active_client("ghost", state=state)
    assert result is False
    assert state[rf._K_ACTIVE_CLIENT_ID] == "a"


def test_set_active_client_none_clears_selection():
    """Setear None desactiva la selección (devuelve True)."""
    c = rf._new_client(name="A", client_id="a")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "a",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    result = rf._set_active_client(None, state=state)
    assert result is True
    assert state[rf._K_ACTIVE_CLIENT_ID] is None


# ─────────────────────────────────────────────────────────────────────────────
# Getters dedicados — devuelven defaults vacíos cuando no hay activo
# ─────────────────────────────────────────────────────────────────────────────

def test_getters_with_no_active_return_safe_defaults():
    """Sin cliente activo: getters devuelven defaults vacíos (no exceptions)."""
    state: dict = {}
    rf._ensure_state(state=state)
    assert rf._get_historical(state=state) == []
    assert rf._get_forecast(state=state) == []
    assert rf._get_asins(state=state) == []
    assert rf._get_selected_asin(state=state) is None
    # seasonality default neutro
    s = rf._get_seasonality(state=state)
    assert s == {"enabled": False, "indices": [1.0] * 12}


def test_getters_with_active_return_client_fields():
    """Con cliente activo: getters devuelven los campos del cliente."""
    c = rf._new_client(name="A", client_id="a")
    c["historical"] = [{"date": "2026-01-01", "revenue": 100}]
    c["forecast"] = [{"date": "2026-02-01", "projected_revenue": 110}]
    c["asins"] = [{"asin": "B0TEST", "share": 1.0}]
    c["selected_asin"] = "B0TEST"
    c["seasonality"] = {"enabled": True, "indices": [1.2] * 12}

    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "a",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    assert rf._get_historical(state=state) == [{"date": "2026-01-01", "revenue": 100}]
    assert rf._get_forecast(state=state) == [{"date": "2026-02-01", "projected_revenue": 110}]
    assert rf._get_asins(state=state) == [{"asin": "B0TEST", "share": 1.0}]
    assert rf._get_selected_asin(state=state) == "B0TEST"
    assert rf._get_seasonality(state=state) == {"enabled": True, "indices": [1.2] * 12}


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia dormida — sanity Fase 1
# ─────────────────────────────────────────────────────────────────────────────

def test_persistence_enabled_is_true_in_phase_2():
    """SANITY: la persistencia está ENCENDIDA en F2.

    Este test blindea el wiring: si alguien apaga el flag de vuelta sin
    quitar los call-sites (`_try_hydrate` en `_ensure_state`, botón
    "💾 Guardar cliente", autosave en demo-load y forecast-gen), el
    módulo pierde la persistencia silenciosamente.
    """
    assert rf._PERSISTENCE_ENABLED is True


def test_persist_clients_saves_when_enabled(monkeypatch):
    """Con el flag True, `_persist_clients` invoca `_save_forecast_client`.

    Estrategia: monkeypatchear el nombre importado en `rf` a un RECORDER,
    ejercitar el helper con un state controlado, y asertar las N+1 llamadas
    esperadas (N clientes + 1 meta con `active_client_id`).
    """
    calls: list[dict] = []

    def recorder(config, area, cliente, modulo, name):
        calls.append({
            "config": config,
            "area": area,
            "cliente": cliente,
            "modulo": modulo,
            "name": name,
        })

    monkeypatch.setattr(rf, "_save_forecast_client", recorder)

    c = rf._new_client(name="A", client_id="a")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "a",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._persist_clients(state=state)

    # 1 save del cliente + 1 save del meta.
    assert len(calls) == 2

    cliente_save = calls[0]
    assert cliente_save["area"] == rf.AREA
    assert cliente_save["cliente"] == "a"
    assert cliente_save["modulo"] == rf.MODULE_SLUG
    assert cliente_save["name"] == "client"
    assert cliente_save["config"]["id"] == "a"

    meta_save = calls[1]
    assert meta_save["area"] == rf.AREA
    assert meta_save["cliente"] == "_meta"
    assert meta_save["modulo"] == rf.MODULE_SLUG
    assert meta_save["name"] == "active"
    assert meta_save["config"] == {"active_client_id": "a"}


def test_hydrate_clients_loads_when_enabled(monkeypatch):
    """Con el flag True, `_hydrate_clients` puebla state desde el backend fake."""
    fake_client_acme = rf._new_client(name="Acme", client_id="acme")

    def fake_list(area, modulo):
        assert area == rf.AREA
        assert modulo == rf.MODULE_SLUG
        return ["acme", "_meta"]

    def fake_load(area, cliente, modulo, name):
        assert area == rf.AREA
        assert modulo == rf.MODULE_SLUG
        if cliente == "acme" and name == "client":
            return fake_client_acme
        if cliente == "_meta" and name == "active":
            return {"active_client_id": "acme"}
        return None

    monkeypatch.setattr(rf, "_list_forecast_clients", fake_list)
    monkeypatch.setattr(rf, "_load_forecast_client", fake_load)

    state: dict = {
        rf._K_CLIENTS: [],
        rf._K_ACTIVE_CLIENT_ID: None,
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._hydrate_clients(state=state)

    assert len(state[rf._K_CLIENTS]) == 1
    assert state[rf._K_CLIENTS][0]["id"] == "acme"
    assert state[rf._K_ACTIVE_CLIENT_ID] == "acme"


# ─────────────────────────────────────────────────────────────────────────────
# _seed_demo_client_if_empty
# ─────────────────────────────────────────────────────────────────────────────

def test_seed_demo_when_empty():
    """Con catálogo vacío, siembra un cliente demo y lo deja activo."""
    state: dict = {}
    rf._ensure_state(state=state)
    rf._seed_demo_client_if_empty(state=state)
    assert len(state[rf._K_CLIENTS]) == 1
    demo = state[rf._K_CLIENTS][0]
    assert demo["name"] == "Demo Client"
    assert state[rf._K_ACTIVE_CLIENT_ID] == demo["id"]


def test_seed_demo_is_noop_when_clients_exist():
    """Con clientes ya cargados, NO siembra demo ni pisa el activo."""
    c = rf._new_client(name="Existing", client_id="existing-1")
    state = {
        rf._K_CLIENTS: [c],
        rf._K_ACTIVE_CLIENT_ID: "existing-1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._seed_demo_client_if_empty(state=state)
    assert len(state[rf._K_CLIENTS]) == 1
    assert state[rf._K_CLIENTS][0]["id"] == "existing-1"
    assert state[rf._K_ACTIVE_CLIENT_ID] == "existing-1"
