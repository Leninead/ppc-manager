"""Tests de persistencia de la biblioteca de casos (M32 Fase 2).

Round-trip vía las funciones module-level de core.persistence (capa client-config),
con `area="sales-director"`, `modulo="case-study"`. Aislamiento: DATA_ROOT redirigido
a tmp_path por monkeypatch (el _LocalBackend lee el global DATA_ROOT en cada llamada,
así que basta el monkeypatch + reset del backend singleton). Se limpian los caches de
lectura (@st.cache_data activo en el entorno de test) para evitar bleed entre tests.
"""

from __future__ import annotations

import pytest

from core import persistence as P

AREA = "sales-director"
MODULE_SLUG = "case-study"
CLIENTE = "lenovo"

CS_SAMPLE = {
    "en": {
        "headline": "10% CTR Lift",
        "subhead": "sub",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body en",
        "approach": "approach body en",
        "approach_steps": [{"title": "Audit", "text": "t"}],
        "results": "results body en",
    },
    "es": {
        "headline": "Aumento 10%",
        "subhead": "sub es",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body es",
        "approach": "approach body es",
        "approach_steps": [],
        "results": "results body es",
    },
    "meta": {"brand": "lenovo", "can_mention": True, "market": ""},
}

_CACHED_READS = (P._load_client_config, P._list_client_configs, P._list_clientes)


def _clear_read_caches() -> None:
    for fn in _CACHED_READS:
        if hasattr(fn, "clear"):
            fn.clear()


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Redirige DATA_ROOT a tmp_path, resetea el backend singleton y limpia caches.

    El _LocalBackend no captura DATA_ROOT en __init__ (lo lee en cada llamada), así
    que el monkeypatch alcanza. Se resetea el singleton por las dudas y se limpian
    los caches de lectura antes y después para hermeticidad total.
    """
    tmp_data = tmp_path / "data"
    monkeypatch.setattr(P, "DATA_ROOT", tmp_data)
    P._set_backend_for_testing(None)
    _clear_read_caches()
    yield tmp_data
    P._set_backend_for_testing(None)
    _clear_read_caches()


def test_save_and_load_roundtrip(isolated_storage):
    """Guardar CS_SAMPLE y cargarlo devuelve el mismo dict."""
    P._save_client_config(CS_SAMPLE, AREA, CLIENTE, MODULE_SLUG, "test")
    loaded = P._load_client_config(AREA, CLIENTE, MODULE_SLUG, "test")
    assert loaded == CS_SAMPLE


def test_list_client_configs(isolated_storage):
    """Guardar 2 casos → list_client_configs devuelve los 2 names ordenados."""
    P._save_client_config(CS_SAMPLE, AREA, CLIENTE, MODULE_SLUG, "caso-b")
    P._save_client_config(CS_SAMPLE, AREA, CLIENTE, MODULE_SLUG, "caso-a")
    names = P._list_client_configs(AREA, CLIENTE, MODULE_SLUG)
    assert names == ["caso-a", "caso-b"]


def test_list_clientes(isolated_storage):
    """Guardar un caso → el cliente aparece en list_clientes."""
    P._save_client_config(CS_SAMPLE, AREA, CLIENTE, MODULE_SLUG, "test")
    assert CLIENTE in P._list_clientes(AREA, MODULE_SLUG)
