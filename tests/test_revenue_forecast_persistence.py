"""Tests Fase 2 de M31 Revenue Forecast — persistencia encendida + resiliencia.

Cubre lo que es verificable SIN red y SIN disco real:

    1. HYDRATE con backend fake poblado → puebla state[_K_CLIENTS] y setea
       el active correcto; el slug "_meta" NO cae en la lista de clientes.
    2. PERSIST con state controlado → dispara `_save_forecast_client` con el
       payload correcto por cliente + 1 meta (`_meta`, "active",
       {"active_client_id": ...}).
    3. RESILIENCIA PERSIST — si `_save_forecast_client` lanza, `_try_persist`
       devuelve False, NO propaga, y el state queda intacto.
    4. RESILIENCIA HYDRATE — si `_list_forecast_clients` lanza, `_try_hydrate`
       devuelve False, NO propaga, y los clientes preexistentes en state se
       preservan.
    5. WIRING _ensure_state HIDRATA CUANDO EL CATÁLOGO ESTÁ VACÍO — con backend
       fake que devuelve 1 cliente + _meta, `_ensure_state(state={})` deja el
       state poblado.
    6. WIRING _ensure_state NO HIDRATA CON CLIENTES PRESENTES (idempotencia) —
       si ya hay clientes en state, un backend fake que lance excepción NO
       rompe la llamada y los clientes se preservan.
    7. TRANSPORT-LEVEL (opcional) — `_save_forecast_client` a través de un
       `_SupabaseBackend` con transport fake dispara UN post a "forecast_clients"
       con upsert=True y el row shape exacto.

Estrategia: monkeypatchear los nombres importados en `rf`
(`_save_forecast_client`, `_load_forecast_client`, `_list_forecast_clients`)
con fakes en memoria — mismo patrón que los tests de state existentes. Para
el test transport-level, se inyecta el backend directo en `core.forecast_persistence`
vía `_set_backend_for_testing` y se resetea en el teardown.

NINGÚN test pega a red real ni escribe a disco real (data/).
"""

from __future__ import annotations

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers de test
# ─────────────────────────────────────────────────────────────────────────────

def _mute_st_error(monkeypatch) -> list[str]:
    """Silencia `rf.st.error` en tests de resiliencia; devuelve el recorder."""
    errors: list[str] = []
    monkeypatch.setattr(rf.st, "error", lambda msg: errors.append(str(msg)))
    return errors


def _fresh_state() -> dict:
    return {
        rf._K_CLIENTS: [],
        rf._K_ACCOUNT_MANAGERS: [],
        rf._K_ACTIVE_CLIENT_ID: None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. HYDRATE con backend fake poblado
# ─────────────────────────────────────────────────────────────────────────────

def test_hydrate_populates_state_from_fake_backend(monkeypatch):
    """`_hydrate_clients` con backend fake poblado carga 2 clientes + _meta activo."""
    acme = rf._new_client(name="Acme", client_id="acme")
    beta = rf._new_client(name="Beta", client_id="beta")

    def fake_list(area, modulo):
        assert area == rf.AREA
        assert modulo == rf.MODULE_SLUG
        return ["acme", "beta", "_meta"]

    def fake_load(area, cliente, modulo, name):
        assert area == rf.AREA
        assert modulo == rf.MODULE_SLUG
        if cliente == "acme" and name == "client":
            return acme
        if cliente == "beta" and name == "client":
            return beta
        if cliente == "_meta" and name == "active":
            return {"active_client_id": "beta"}
        return None

    monkeypatch.setattr(rf, "_list_forecast_clients", fake_list)
    monkeypatch.setattr(rf, "_load_forecast_client", fake_load)

    state = _fresh_state()
    rf._hydrate_clients(state=state)

    ids = [c["id"] for c in state[rf._K_CLIENTS]]
    assert ids == ["acme", "beta"]
    # El slug "_meta" NO cayó como cliente.
    assert "_meta" not in ids
    assert state[rf._K_ACTIVE_CLIENT_ID] == "beta"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PERSIST — payload correcto por cliente + meta
# ─────────────────────────────────────────────────────────────────────────────

def test_persist_dispatches_save_per_client_plus_meta(monkeypatch):
    """`_persist_clients` dispara N saves de clientes + 1 save del meta."""
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

    acme = rf._new_client(name="Acme", client_id="acme")
    beta = rf._new_client(name="Beta", client_id="beta")
    state = {
        rf._K_CLIENTS: [acme, beta],
        rf._K_ACTIVE_CLIENT_ID: "beta",
        rf._K_ACCOUNT_MANAGERS: [],
    }

    rf._persist_clients(state=state)

    # 2 clientes + 1 meta
    assert len(calls) == 3

    # Saves de clientes
    for i, cliente_id in enumerate(("acme", "beta")):
        c = calls[i]
        assert c["area"] == rf.AREA
        assert c["cliente"] == cliente_id
        assert c["modulo"] == rf.MODULE_SLUG
        assert c["name"] == "client"
        assert c["config"]["id"] == cliente_id

    # Save del meta
    meta = calls[2]
    assert meta["area"] == rf.AREA
    assert meta["cliente"] == "_meta"
    assert meta["modulo"] == rf.MODULE_SLUG
    assert meta["name"] == "active"
    assert meta["config"] == {"active_client_id": "beta"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. RESILIENCIA PERSIST
# ─────────────────────────────────────────────────────────────────────────────

def test_try_persist_swallows_backend_exceptions(monkeypatch):
    """Si `_save_forecast_client` lanza, `_try_persist` devuelve False y NO propaga."""
    errors = _mute_st_error(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("backend caído")

    monkeypatch.setattr(rf, "_save_forecast_client", boom)

    acme = rf._new_client(name="Acme", client_id="acme")
    state = {
        rf._K_CLIENTS: [acme],
        rf._K_ACTIVE_CLIENT_ID: "acme",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    snapshot_ids_before = [c["id"] for c in state[rf._K_CLIENTS]]
    active_before = state[rf._K_ACTIVE_CLIENT_ID]

    result = rf._try_persist(state=state)

    assert result is False
    # State intacto
    assert [c["id"] for c in state[rf._K_CLIENTS]] == snapshot_ids_before
    assert state[rf._K_ACTIVE_CLIENT_ID] == active_before
    # Al menos un aviso al AM
    assert len(errors) >= 1
    assert "backend caído" in errors[0]


# ─────────────────────────────────────────────────────────────────────────────
# 4. RESILIENCIA HYDRATE
# ─────────────────────────────────────────────────────────────────────────────

def test_try_hydrate_swallows_backend_exceptions_and_preserves_state(monkeypatch):
    """Si `_list_forecast_clients` lanza, `_try_hydrate` devuelve False y preserva state."""
    errors = _mute_st_error(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("no hay red")

    monkeypatch.setattr(rf, "_list_forecast_clients", boom)

    # State ya poblado desde memoria (ej. seed demo)
    pre_existing = rf._new_client(name="Pre", client_id="pre")
    state = {
        rf._K_CLIENTS: [pre_existing],
        rf._K_ACTIVE_CLIENT_ID: "pre",
        rf._K_ACCOUNT_MANAGERS: [],
    }

    result = rf._try_hydrate(state=state)

    assert result is False
    # State preservado — los clientes preexistentes siguen ahí
    ids = [c["id"] for c in state[rf._K_CLIENTS]]
    assert ids == ["pre"]
    assert state[rf._K_ACTIVE_CLIENT_ID] == "pre"
    assert len(errors) >= 1
    assert "no hay red" in errors[0]


# ─────────────────────────────────────────────────────────────────────────────
# 5. WIRING _ensure_state — hidrata cuando el catálogo está vacío
# ─────────────────────────────────────────────────────────────────────────────

def test_ensure_state_hydrates_when_catalog_empty(monkeypatch):
    """`_ensure_state(state={})` llama a `_try_hydrate` y deja state poblado."""
    acme = rf._new_client(name="Acme", client_id="acme")

    def fake_list(area, modulo):
        return ["acme", "_meta"]

    def fake_load(area, cliente, modulo, name):
        if cliente == "acme" and name == "client":
            return acme
        if cliente == "_meta" and name == "active":
            return {"active_client_id": "acme"}
        return None

    monkeypatch.setattr(rf, "_list_forecast_clients", fake_list)
    monkeypatch.setattr(rf, "_load_forecast_client", fake_load)

    state: dict = {}
    rf._ensure_state(state=state)

    # `_ensure_state` sembró las 3 keys y encima hidrato desde backend fake.
    assert len(state[rf._K_CLIENTS]) == 1
    assert state[rf._K_CLIENTS][0]["id"] == "acme"
    assert state[rf._K_ACTIVE_CLIENT_ID] == "acme"


# ─────────────────────────────────────────────────────────────────────────────
# 6. WIRING _ensure_state — NO hidrata con clientes ya presentes (idempotencia)
# ─────────────────────────────────────────────────────────────────────────────

def test_ensure_state_does_not_hydrate_when_clients_already_present(monkeypatch):
    """Si el state ya tiene clientes, `_ensure_state` NO llama al backend."""
    errors = _mute_st_error(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("no debería llamarse")

    # Si el guard `if not state[_K_CLIENTS]` fallara, este list() lanzaría
    # y `_try_hydrate` avisaría. Verificamos que NINGUNO se ejecuta.
    monkeypatch.setattr(rf, "_list_forecast_clients", boom)

    pre = rf._new_client(name="Pre", client_id="pre")
    state = {
        rf._K_CLIENTS: [pre],
        rf._K_ACTIVE_CLIENT_ID: "pre",
        rf._K_ACCOUNT_MANAGERS: [],
    }

    # No debe crashear ni cambiar el state.
    rf._ensure_state(state=state)

    assert [c["id"] for c in state[rf._K_CLIENTS]] == ["pre"]
    assert state[rf._K_ACTIVE_CLIENT_ID] == "pre"
    # Nunca hubo aviso (`_try_hydrate` no se ejecutó).
    assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# 7. TRANSPORT-LEVEL — _SupabaseBackend con transport fake dispara post correcto
# ─────────────────────────────────────────────────────────────────────────────

class _FakeTransport:
    """Transport-in-memory para tests: registra get/post/delete sin red."""

    def __init__(self):
        self.calls: list[dict] = []
        self.storage: list[dict] = []  # rows persisted

    def get(self, table, params):
        self.calls.append({"op": "get", "table": table, "params": params})
        # Devuelve todas las rows filtradas por los `eq.` params (mínimo funcional).
        rows = []
        for row in self.storage:
            match = True
            for k, v in params.items():
                if k in ("select", "limit"):
                    continue
                if v.startswith("eq."):
                    expected = v[len("eq."):]
                    if str(row.get(k)) != expected:
                        match = False
                        break
            if match:
                rows.append(row)
        return rows

    def post(self, table, rows, upsert=False):
        self.calls.append({
            "op": "post",
            "table": table,
            "rows": rows,
            "upsert": upsert,
        })
        # Simula upsert por PK (area, cliente, modulo, name).
        if upsert:
            for new_row in rows:
                pk = (
                    new_row.get("area"),
                    new_row.get("cliente"),
                    new_row.get("modulo"),
                    new_row.get("name"),
                )
                self.storage = [
                    r for r in self.storage
                    if (r.get("area"), r.get("cliente"), r.get("modulo"), r.get("name")) != pk
                ]
        self.storage.extend(rows)
        return rows

    def delete(self, table, params):
        self.calls.append({"op": "delete", "table": table, "params": params})
        return []


def test_supabase_backend_save_client_dispatches_post_with_upsert():
    """`_save_forecast_client` a través de `_SupabaseBackend` con transport fake
    dispara UN post a "forecast_clients" con `upsert=True` y el row shape correcto.
    """
    from core import forecast_persistence as fp

    fake = _FakeTransport()
    try:
        fp._set_backend_for_testing(fp._SupabaseBackend(transport=fake))
        # Limpiar caches para que los wrappers cacheados no devuelvan stale.
        if hasattr(fp._list_forecast_clients, "clear"):
            fp._list_forecast_clients.clear()
        if hasattr(fp._load_forecast_client, "clear"):
            fp._load_forecast_client.clear()

        fp._save_forecast_client(
            config={"id": "acme", "name": "Acme"},
            area="account-manager",
            cliente="acme",
            modulo="revenue-forecast",
            name="client",
        )

        # Exactamente 1 POST a "forecast_clients" con upsert=True.
        posts = [c for c in fake.calls if c["op"] == "post"]
        assert len(posts) == 1
        post = posts[0]
        assert post["table"] == "forecast_clients"
        assert post["upsert"] is True

        rows = post["rows"]
        assert isinstance(rows, list) and len(rows) == 1
        row = rows[0]
        # Shape exacto: exactamente las 5 keys esperadas.
        assert set(row.keys()) == {"area", "cliente", "modulo", "name", "data"}
        assert row["area"] == "account-manager"
        assert row["cliente"] == "acme"
        assert row["modulo"] == "revenue-forecast"
        assert row["name"] == "client"
        assert row["data"] == {"id": "acme", "name": "Acme"}
    finally:
        fp._set_backend_for_testing(None)
        if hasattr(fp._list_forecast_clients, "clear"):
            fp._list_forecast_clients.clear()
        if hasattr(fp._load_forecast_client, "clear"):
            fp._load_forecast_client.clear()
