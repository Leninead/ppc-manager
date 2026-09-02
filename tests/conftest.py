"""Configuración pytest para tests del Agency OS.

Asegura que la raíz del repo está en sys.path antes de cualquier import de tests,
y expone el fixture `isolated_data_root` para aislar los tests del `data/` real.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Aislamiento del `data/` real
# ─────────────────────────────────────────────────────────────────────────────
#
# Varios módulos hidratan su catálogo desde disco al sembrar el state (M31:
# `_ensure_state` → `_try_hydrate` → `_hydrate_clients`). Eso hace que cualquier
# cliente que un AM haya dejado persistido validando en la app se cuele en el
# `state` de los tests que esperan un catálogo vacío, y los ponga rojos sin que
# haya cambiado una línea de código.
#
# Pasó de verdad (2026-08-25): validar una feature en la app dejó un cliente en
# `data/account-manager/` y volvió rojo un test intacto. Al borrar el cliente
# quedó además huérfano el puntero `_meta/.../active.json`, que siguió
# rompiendo otro test distinto.
#
# Todo test que llame a un `_ensure_state` (o equivalente que hidrate de disco)
# debe pedir este fixture.

@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    """DATA_ROOT → tmp_path: el test deja de depender del `data/` del repo.

    Los lectores de la capa de persistencia son `@st.cache_data`, así que además
    del monkeypatch hay que limpiar sus caches y resetear el singleton del
    backend — si no, un resultado cacheado del `data/` real sobrevive al patch.

    Yields:
        Path del data root temporal (por si el test quiere escribir en él).
    """
    import core.forecast_persistence as P

    def _reset():
        P._set_backend_for_testing(None)
        for fn in (P._load_forecast_client, P._list_forecast_clients):
            clear = getattr(fn, "clear", None)
            if clear is not None:
                clear()

    tmp_data = tmp_path / "data"
    monkeypatch.setattr(P, "DATA_ROOT", tmp_data)
    _reset()
    yield tmp_data
    _reset()


@pytest.fixture(autouse=True)
def _ai_log_in_tmp(tmp_path, monkeypatch):
    """Keep the AI call log (ai/client._log) out of the developer's data/."""
    import ai.config as ai_config
    monkeypatch.setattr(ai_config, "LOG_DIR", str(tmp_path / "ai-log"))
