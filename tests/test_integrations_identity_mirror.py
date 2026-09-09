"""Tests del espejado de estado sobre la identidad de Mercado Libre.

CERO RED: `_Rest` es un fake en memoria.

El bug que motiva esto se vio en produccion el 2026-09-09. Dar de baja una
cuenta desde el portal dejaba las dos tablas contradiciendose:

    integration_connections.estado = 'revocado'
    meli_auth_identities.estado    = 'activo'

Solo los caminos de FALLO del worker de ingesta llamaban al espejado; la baja
desde la UI no. Hoy no rompe nada porque la ingesta filtra por la conexion,
pero `meli_job_queue` — la base del modo push, declarada y todavia sin
consumer — agenda sobre la identidad: el dia que alguien la drene, va a
reintentar cuentas dadas de baja con un token que no puede funcionar.

Se testea en `set_status` y no en el dialogo de la UI a proposito: es el punto
unico por el que pasa todo cambio de estado, asi que cubrirlo ahi cubre tambien
a cualquier consumidor futuro.
"""

from __future__ import annotations

import pytest

from core.integrations import store as S
from core.meli_api import ingest


class _FakeRest:
    def __init__(self, rows=None, fail_on=None):
        self._rows = rows if rows is not None else [{"cuenta_externa_id": "2689413638"}]
        self._fail_on = fail_on or set()
        self.updates = []
        self.audits = []
        self.selects = []

    def select(self, table, params):
        self.selects.append((table, params))
        if "select" in self._fail_on:
            raise RuntimeError("PostgREST caido")
        return list(self._rows)

    def update(self, table, params, changes, stamp=True):
        if table in self._fail_on:
            raise RuntimeError(f"no se pudo escribir {table}")
        self.updates.append((table, params, changes))

    def audit(self, action, *, slug=None, actor="", detail=None):
        self.audits.append(action)


# ── mirror_identity_status, la pieza del lado Mercado Libre ─────────────────

def test_escribe_sobre_la_identidad_correcta():
    rest = _FakeRest()
    assert ingest.mirror_identity_status(rest, "2689413638", "revocado") is True

    table, params, changes = rest.updates[0]
    assert table == ingest.IDENTITIES_TABLE
    assert params == {"user_id": "eq.2689413638"}
    assert changes == {"estado": "revocado"}


def test_sin_external_id_no_escribe_nada():
    """Una conexion sin cuenta_externa_id no tiene identidad que espejar."""
    rest = _FakeRest()
    assert ingest.mirror_identity_status(rest, "", "revocado") is False
    assert rest.updates == []


def test_un_fallo_de_escritura_no_propaga():
    """La baja ya se commiteó: un espejo desactualizado es mejor que un error."""
    rest = _FakeRest(fail_on={ingest.IDENTITIES_TABLE})
    assert ingest.mirror_identity_status(rest, "123", "revocado") is False


# ── set_status, el punto unico del lado generico ────────────────────────────

def _identity_writes(rest):
    return [u for u in rest.updates if u[0] == ingest.IDENTITIES_TABLE]


def test_revocar_una_cuenta_de_meli_espeja_la_identidad():
    """El bug exacto de produccion: revocado en una tabla, activo en la otra."""
    rest = _FakeRest()
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="revocado", user="juanvargas", slug="mercado_libre")

    escrituras = _identity_writes(rest)
    assert escrituras, "la identidad quedo sin espejar"
    assert escrituras[0][2] == {"estado": "revocado"}


def test_la_conexion_se_actualiza_igual():
    """El espejado es un extra; no debe alterar lo que ya hacia set_status."""
    rest = _FakeRest()
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="revocado", user="juanvargas", slug="mercado_libre")

    conexiones = [u for u in rest.updates if u[0] == S.CONNECTIONS_TABLE]
    assert conexiones[0][1] == {"id": "eq.1"}
    assert conexiones[0][2] == {"estado": "revocado"}
    assert "connection_revocado" in rest.audits


def test_otro_proveedor_no_toca_tablas_de_meli():
    """Este modulo es agnostico del proveedor: una credencial de Walmart no
    debe arrastrar el pipeline de Mercado Libre."""
    rest = _FakeRest()
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="revocado", user="juanvargas", slug="walmart")

    assert _identity_writes(rest) == []
    assert rest.selects == [], "ni siquiera deberia buscar el external id"


def test_un_fallo_del_espejo_no_rompe_la_baja():
    """El operador pidio desconectar: no puede fallarle por una escritura secundaria."""
    rest = _FakeRest(fail_on={ingest.IDENTITIES_TABLE})
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="revocado", user="juanvargas", slug="mercado_libre")

    conexiones = [u for u in rest.updates if u[0] == S.CONNECTIONS_TABLE]
    assert conexiones, "la baja en si tenia que quedar hecha"


def test_un_fallo_leyendo_el_external_id_tampoco_rompe():
    rest = _FakeRest(fail_on={"select"})
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="revocado", user="juanvargas", slug="mercado_libre")

    conexiones = [u for u in rest.updates if u[0] == S.CONNECTIONS_TABLE]
    assert conexiones


def test_reactivar_tambien_espeja():
    """El espejo sigue al estado, sea cual sea — no solo a la baja."""
    rest = _FakeRest()
    S.ConnectionStore(rest).set_status(
        connection_id=1, status="activo", user="juanvargas", slug="mercado_libre")

    assert _identity_writes(rest)[0][2] == {"estado": "activo"}
