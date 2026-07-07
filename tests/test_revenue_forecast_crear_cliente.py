"""Tests M31 — UI de creación de cliente (flujo `_create_client_flow`).

Cubre el NÚCLEO testeable de la UI del popover "➕ Nuevo cliente", sin runtime
Streamlit y sin red (persistencia monkeypatcheada a nivel `_persist_clients`):

    1. Crear cliente válido → aparece en el catálogo, queda activo, persist llamado.
    2. Nombre vacío/espacios → no crea, no persiste, warning.
    3. Nombre duplicado (case-insensitive) → no crea el segundo, avisa.
    4. El cliente creado tiene el shape completo de `_new_client`.
    5. Resiliencia: si `_try_persist` falla, el cliente igual queda en session_state.

Estrategia: `_create_client_flow` acepta `state` (dict simulado), igual que los
demás accessors del módulo. La persistencia se monkeypatchea; `st.error` se
silencia en el test de resiliencia para no ensuciar el output.
"""

from __future__ import annotations

from modules.pages import revenue_forecast as rf


def _fresh_state() -> dict:
    return {
        rf._K_CLIENTS: [],
        rf._K_ACTIVE_CLIENT_ID: None,
        rf._K_ACCOUNT_MANAGERS: [],
    }


def test_create_valid_client_added_active_and_persisted(monkeypatch):
    """Crear válido: entra al catálogo, queda activo y persiste."""
    calls: list = []
    monkeypatch.setattr(rf, "_persist_clients", lambda state=None: calls.append(state))

    state = _fresh_state()
    ok, kind, msg = rf._create_client_flow("Acme MX", "MX", state=state)

    assert ok is True
    assert kind == "success"
    assert "Acme MX" in msg
    assert len(state[rf._K_CLIENTS]) == 1
    nuevo = state[rf._K_CLIENTS][0]
    assert nuevo["name"] == "Acme MX"
    assert nuevo["marketplace"] == "MX"
    assert state[rf._K_ACTIVE_CLIENT_ID] == nuevo["id"]
    assert len(calls) == 1  # persistió exactamente una vez


def test_create_empty_name_does_not_create_or_persist(monkeypatch):
    """Nombre vacío (o solo espacios): no crea, no persiste, warning."""
    calls: list = []
    monkeypatch.setattr(rf, "_persist_clients", lambda state=None: calls.append(state))

    state = _fresh_state()
    ok, kind, msg = rf._create_client_flow("   ", "US", state=state)

    assert ok is False
    assert kind == "warning"
    assert state[rf._K_CLIENTS] == []
    assert state[rf._K_ACTIVE_CLIENT_ID] is None
    assert calls == []


def test_create_duplicate_name_case_insensitive(monkeypatch):
    """Nombre duplicado (case-insensitive): no crea el segundo, avisa."""
    monkeypatch.setattr(rf, "_persist_clients", lambda state=None: None)

    state = _fresh_state()
    ok1, _, _ = rf._create_client_flow("Dermaglos", "US", state=state)
    assert ok1 is True
    assert len(state[rf._K_CLIENTS]) == 1

    ok2, kind2, msg2 = rf._create_client_flow("dermaglos", "MX", state=state)
    assert ok2 is False
    assert kind2 == "warning"
    assert "existe" in msg2.lower()
    assert len(state[rf._K_CLIENTS]) == 1


def test_created_client_has_full_shape(monkeypatch):
    """El cliente creado tiene el shape completo del contrato de `_new_client`."""
    monkeypatch.setattr(rf, "_persist_clients", lambda state=None: None)

    state = _fresh_state()
    rf._create_client_flow("Shape Test", "ES", state=state)
    nuevo = state[rf._K_CLIENTS][0]

    expected_keys = {
        "id", "name", "marketplace", "am_id", "margin", "currency", "yoy_mode",
        "historical", "forecast", "snapshots", "seasonality", "asins",
        "selected_asin", "created_at",
    }
    assert expected_keys.issubset(set(nuevo.keys()))
    assert len(nuevo["seasonality"]["indices"]) == 12


def test_persist_failure_keeps_client_in_session(monkeypatch):
    """Resiliencia: si `_try_persist` falla, el cliente igual queda en session_state."""
    def boom(state=None):
        raise RuntimeError("backend caído")

    monkeypatch.setattr(rf, "_persist_clients", boom)
    monkeypatch.setattr(rf.st, "error", lambda *a, **k: None)  # silenciar aviso

    state = _fresh_state()
    ok, kind, msg = rf._create_client_flow("Resiliente", "US", state=state)

    # el flujo NO propaga la excepción (la traga _try_persist)
    assert ok is True
    assert kind == "success"
    # y el cliente sigue en sesión pese al fallo de persistencia
    assert len(state[rf._K_CLIENTS]) == 1
    assert state[rf._K_CLIENTS][0]["name"] == "Resiliente"
    assert state[rf._K_ACTIVE_CLIENT_ID] == state[rf._K_CLIENTS][0]["id"]


def test_persist_skips_demo_client_but_saves_real_and_meta(monkeypatch):
    """`_persist_clients` saltea el cliente demo pero persiste los reales + _meta/active.

    Estrategia: monkeypatchear `_save_forecast_client` a un recorder y ejercitar
    `_persist_clients` sobre un catálogo con demo-client + un cliente real. El demo
    NO debe generar POST; el real SÍ; y el registro _meta/active (fuera del loop)
    debe guardarse igual.
    """
    calls: list = []

    def recorder(config, area, cliente, modulo, name):
        calls.append({"cliente": cliente, "name": name, "config": config})

    monkeypatch.setattr(rf, "_save_forecast_client", recorder)

    demo = rf._new_client(name="Demo Client", client_id="demo-client")
    real = rf._new_client(name="Dermaglos", client_id="dermaglos-1")
    state = {
        rf._K_CLIENTS: [demo, real],
        rf._K_ACTIVE_CLIENT_ID: "dermaglos-1",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    rf._persist_clients(state=state)

    saved_clientes = {c["cliente"] for c in calls}
    # el demo NO se persistió
    assert "demo-client" not in saved_clientes
    # el cliente real SÍ se persistió como "client"
    assert any(c["cliente"] == "dermaglos-1" and c["name"] == "client" for c in calls)
    # el registro _meta/active se guardó igual (no lo afecta el continue)
    meta = [c for c in calls if c["cliente"] == "_meta" and c["name"] == "active"]
    assert len(meta) == 1
    assert meta[0]["config"] == {"active_client_id": "dermaglos-1"}
