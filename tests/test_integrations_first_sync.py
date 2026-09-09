"""Tests del primer sync automático al vincular (core/integrations/worker.py).

CERO RED, CERO clave de sellado: `command_grants` corre con sus colaboradores
monkeypatcheados, así que ningún test de acá toca PostgREST, la API de Mercado
Libre ni el volumen del worker.

Lo que se fija es la propiedad que hace segura a la feature: el sync es un extra
que corre DESPUÉS de que el grant quedó canjeado y commiteado, así que su fallo
no puede degradar el resultado del canje. Un sync roto que devolviera exit code
1 haría que el cron reporte como fallida una conexión que quedó funcionando, y
el operador saldría a arreglar algo que no está roto.

`command_ingest` se importa en forma diferida DENTRO de `_first_sync_meli`, por
eso se parchea el atributo en `core.meli_api.worker`: el import se resuelve
recién en la llamada y toma lo que el monkeypatch dejó puesto.
"""

from __future__ import annotations

import pytest

import core.meli_api.worker as meli_worker
from core.integrations import worker as W


class _FakeRest:
    """Lo mínimo de `_Rest` que toca `command_grants`."""

    def __init__(self, pending_rows):
        self._pending = list(pending_rows)
        self.updates = []
        self.audits = []

    def select(self, table, params):
        return list(self._pending)

    def update(self, table, where, changes):
        self.updates.append((table, where, changes))

    def audit(self, event, **kwargs):
        self.audits.append((event, kwargs))


def _pending(slug="mercado_libre", ident=1, cliente="_pending_abc123"):
    return {
        "id": ident,
        "integration_slug": slug,
        "cliente": cliente,
        "marketplace": "",
        "state": f"state{ident}",
        "verifier_sealed": "v1:sealed-verifier",
        "code_sealed": "v1:sealed-code",
    }


@pytest.fixture
def harness(monkeypatch):
    """Deja `command_grants` corriendo en seco y devuelve el registro de eventos.

    `events` guarda el orden real de lo que pasó — es lo que permite afirmar que
    ningún sync arranca antes de que TODOS los canjes hayan terminado.
    """
    events: list[tuple[str, str]] = []
    state = {"rest": None, "exchange": None, "ingest_result": 0}

    def _install(pending_rows, exchange=None, ingest=None):
        rest = _FakeRest(pending_rows)
        state["rest"] = rest

        monkeypatch.setattr(W, "_rest_worker", lambda: rest)
        monkeypatch.setattr(W, "ensure_keys", lambda _rest: "PRIVATE-PEM")
        monkeypatch.setattr(W, "_redirect_uri",
                            lambda: "https://app.example/oauth/callback")
        monkeypatch.setattr(W, "_expire_pending_grants", lambda _rest: None)

        def _default_exchange(_rest, pending, _pem, _uri):
            client = f"cuenta-{pending['id']}"
            events.append(("exchange", client))
            return client

        monkeypatch.setattr(W, "_exchange_grant", exchange or _default_exchange)

        def _default_ingest(client=None):
            events.append(("ingest", client))
            return state["ingest_result"]

        monkeypatch.setattr(meli_worker, "command_ingest", ingest or _default_ingest)
        return rest

    _install.events = events
    _install.state = state
    return _install


def test_vincular_una_cuenta_meli_dispara_el_sync_al_toque(harness):
    """El caso que motiva la feature: conectar y NO esperar al ingest de las 23:30."""
    harness([_pending(ident=7)])

    assert W.command_grants() == 0
    assert ("ingest", "cuenta-7") in harness.events


def test_el_sync_usa_el_slug_resuelto_y_no_el_placeholder(harness):
    """El pending trae `_pending_xxx`; sincronizar eso no encontraría la cuenta."""
    harness([_pending(ident=3, cliente="_pending_zzz")])

    W.command_grants()

    synced = [client for kind, client in harness.events if kind == "ingest"]
    assert synced == ["cuenta-3"]
    assert not any(c.startswith("_pending_") for c in synced)


def test_ningun_sync_arranca_antes_de_canjear_todos_los_grants(harness):
    """Un sync lento no puede dejar una autorización posterior colgada en `recibido`."""
    harness([_pending(ident=1), _pending(ident=2)])

    W.command_grants()

    kinds = [kind for kind, _ in harness.events]
    assert kinds == ["exchange", "exchange", "ingest", "ingest"]


def test_un_sync_que_explota_no_rompe_el_canje(harness):
    """La cuenta YA quedó conectada: el fallo se traga y lo reintenta el cron nocturno."""
    def _boom(client=None):
        harness.events.append(("ingest", client))
        raise RuntimeError("MELI devolvio 500")

    harness([_pending(ident=1)], ingest=_boom)

    assert W.command_grants() == 0
    assert ("ingest", "cuenta-1") in harness.events


def test_un_sync_incompleto_tampoco_mueve_el_exit_code(harness):
    """`command_ingest` devuelve 1 cuando alguna cuenta falló; no es un fallo del canje."""
    h = harness([_pending(ident=1)])
    harness.state["ingest_result"] = 1

    assert W.command_grants() == 0


def test_una_integracion_que_no_es_meli_no_dispara_sync_de_meli(harness):
    """El ingest es específico de MELI; Amazon y Walmart tienen el suyo cuando existan."""
    harness([_pending(slug="amazon_ads", ident=1)])

    assert W.command_grants() == 0
    assert not [k for k, _ in harness.events if k == "ingest"]


def test_un_canje_fallido_no_se_sincroniza_y_si_marca_el_run(harness):
    """Sin conexión no hay nada que sincronizar, y el canje fallido sí es un fallo real."""
    def _boom(_rest, pending, _pem, _uri):
        raise RuntimeError("code vencido")

    rest = harness([_pending(ident=1)], exchange=_boom)

    assert W.command_grants() == 1
    assert not [k for k, _ in harness.events if k == "ingest"]
    assert any(event == "grant_failed" for event, _ in rest.audits)


def test_sin_grants_pendientes_no_se_importa_meli(harness, monkeypatch):
    """El short-circuit evita cargar el pipeline de ingest en cada corrida del cron."""
    def _explode(client=None):
        raise AssertionError("no debería intentar sincronizar nada")

    harness([], ingest=_explode)

    assert W.command_grants() == 0
    assert harness.events == []
