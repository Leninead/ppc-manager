"""Tests de `resolve_advertiser_id` (core/meli_api/ingest.py).

CERO RED: el cliente de Meli y la capa REST son fakes en memoria.

El caso que motiva este archivo se vio en produccion el 2026-09-09: la llamada
mandaba `X-Product-Id: PADS` solo como header, y la API contesta
`400 product_id param not found in request`. Como la funcion convierte
CUALQUIER error de cliente en "esta cuenta no tiene Product Ads", el 400 se
tragaba y la etapa de ads quedaba registrada como `ok` con 0 filas — un bug
nuestro y un vendedor sin publicidad se veian identicos desde la tabla de
corridas. Por eso el test mira el parametro, no el resultado: es lo unico que
distingue una request bien armada de una que se degrada en silencio.
"""

from __future__ import annotations

import pytest

from core.meli_api import ingest
from core.meli_api.transport import MeliClientError


class _FakeClient:
    """Registra como se arma la request y devuelve un body fijo."""

    def __init__(self, body=None, raise_exc=None):
        self._body = body if body is not None else {"advertisers": []}
        self._raise = raise_exc
        self.calls = []

    def get(self, path, params=None, extra_headers=None):
        self.calls.append({"path": path, "params": params or {},
                           "headers": extra_headers or {}})
        if self._raise:
            raise self._raise
        return self._body


class _FakeRest:
    """Lo minimo de la capa REST que toca resolve_advertiser_id."""

    def __init__(self, cached_rows=None):
        self._cached = cached_rows if cached_rows is not None else [{}]
        self.updates = []

    def select(self, table, params):
        return list(self._cached)

    def update(self, table, where, changes):
        self.updates.append((table, where, changes))

    def upsert(self, table, payload, on_conflict=None):
        self.updates.append((table, on_conflict, payload))


def _advertisers(site="CBT", advertiser_id="999"):
    return {"advertisers": [{"site_id": site, "advertiser_id": advertiser_id}]}


def test_manda_product_id_como_parametro_no_solo_header():
    """La regresion: sin el param la API contesta 400 y la etapa de ads queda vacia."""
    client = _FakeClient(_advertisers())
    ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT")

    assert client.calls, "no se llamo al endpoint de advertisers"
    call = client.calls[0]
    assert call["path"] == "/advertising/advertisers"
    assert call["params"].get("product_id") == "PADS"


def test_sigue_mandando_el_header_tambien():
    """El header mantiene el resto de las llamadas de Product Ads en la superficie correcta."""
    client = _FakeClient(_advertisers())
    ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT")

    assert client.calls[0]["headers"].get("X-Product-Id") == "PADS"


def test_elige_el_advertiser_del_sitio_de_la_cuenta():
    client = _FakeClient(_advertisers(site="CBT", advertiser_id="abc123"))
    got = ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT")
    assert got == "abc123"


def test_un_advertiser_de_otro_sitio_no_se_elige():
    """Una cuenta multi-sitio no debe heredar el advertiser del sitio equivocado."""
    client = _FakeClient(_advertisers(site="MLM", advertiser_id="otro"))
    assert ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT") is None


def test_un_advertiser_ya_cacheado_no_pega_a_la_api():
    """Cache-first: la corrida diaria no debe gastar un round-trip por cuenta."""
    client = _FakeClient(_advertisers())
    rest = _FakeRest(cached_rows=[{"advertiser_id": "cacheado", "user_id": "42"}])

    assert ingest.resolve_advertiser_id(client, rest, 1, "CBT") == "cacheado"
    assert client.calls == [], "no deberia haber llamado a la API"


def test_un_error_de_cliente_se_traga_y_devuelve_none():
    """Documentado a proposito: una cuenta sin Product Ads no es un fallo de la ingesta.

    Es tambien la razon por la que el 400 de produccion fue invisible — ver el
    docstring del modulo.
    """
    client = _FakeClient(raise_exc=MeliClientError("403 sin acceso a Product Ads"))
    assert ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT") is None


def test_sin_advertisers_devuelve_none():
    client = _FakeClient({"advertisers": []})
    assert ingest.resolve_advertiser_id(client, _FakeRest(), 1, "CBT") is None
