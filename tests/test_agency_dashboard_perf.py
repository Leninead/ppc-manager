"""B2b — medición de performance del agregador del dashboard global.

NO corre por default: la suite no puede tardar más por esto. Para medir:

    AGENCY_DASHBOARD_PERF=1 python -m pytest tests/test_agency_dashboard_perf.py -s -q

Imprime dos tablas (mediana de 3 corridas por escenario):
    - `_build_agency_dashboard` puro, 20 / 40 / 80 cuentas × 12 meses.
    - `_load_agency_clients` sobre disco local (tmp), 20 / 40 / 80 clientes,
      con el desglose listar / leer (I/O + parse + cache) / deepcopy.

El tiempo se mide SIN tracemalloc (tracemalloc infla el tiempo) y el pico de
memoria en una corrida aparte CON tracemalloc.

Los clientes sintéticos pasan por el motor real de M31 (`generate_forecast`), así
las filas de forecast y del baseline tienen el shape y el tamaño de producción.
"""
from __future__ import annotations

import copy
import json
import os
import random
import statistics
import time
import tracemalloc

import pytest

from core import agency_dashboard as ad
from core import forecast_persistence as fp
from modules.pages import revenue_forecast as rf

pytestmark = pytest.mark.skipif(
    not os.environ.get("AGENCY_DASHBOARD_PERF"),
    reason="medición de performance; correr con AGENCY_DASHBOARD_PERF=1",
)

_SIZES = (20, 40, 80)
_RUNS = 3
_OPTS = {"horizon": 12, "momWindow": 3, "blend": 50, "useSeasonality": False}
_PERIODS = [f"2026-{m:02d}" for m in range(1, 13)]


# ─────────────────────────────────────────────────────────────────────────────
# Generador de clientes sintéticos
# ─────────────────────────────────────────────────────────────────────────────

def _month_iso(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


def _synthetic_client(idx: int, rng: random.Random) -> dict:
    """Un cliente con 24 meses de historical (2024-01 → 2025-12), 1 mes de
    actual (2026-01, parcial) y un baseline de 12 meses (2026-01 → 2026-12).

    Números plausibles y distintos por cliente: base de revenue entre 5k y 250k,
    tendencia y estacionalidad propias, ACOS 15-45 % y TACOS 4-18 %.
    """
    base = rng.uniform(5_000, 250_000)
    trend = rng.uniform(-0.01, 0.03)
    season = [1 + 0.25 * rng.uniform(-1, 1) for _ in range(12)]
    acos = rng.uniform(15, 45)
    tacos = rng.uniform(4, 18)
    aov = rng.uniform(12, 60)
    cvr = rng.uniform(4, 16)

    def month_row(date: str, i: int, month: int) -> dict:
        revenue = round(base * (1 + trend) ** i * season[month - 1], 2)
        units = max(1, round(revenue / aov))
        sessions = max(1, round(units / (cvr / 100)))
        spend = round(revenue * tacos / 100, 2)
        return {
            "date": date, "revenue": revenue, "units": units,
            "sessions": sessions, "cvr": round(units / sessions * 100, 2),
            "buyBox": round(rng.uniform(85, 100), 1),
            "pageViews": round(sessions * rng.uniform(1.2, 1.8)),
            "revenueB2B": round(revenue * rng.uniform(0, 0.05), 2),
            "spend": spend, "ventasPPC": round(spend / (acos / 100), 2),
        }

    historical = []
    for i in range(24):
        year, month = 2024 + i // 12, i % 12 + 1
        historical.append(month_row(_month_iso(year, month), i, month))

    actual_row = month_row("2026-01-01", 24, 1)
    for k in ("revenue", "units", "sessions", "spend", "ventasPPC"):
        actual_row[k] = round(actual_row[k] * 12 / 31, 2)
    actual_row.update({"partial": True, "days_covered": 12})

    cur = rf._new_client(name=f"Cuenta {idx:03d}", client_id=f"cuenta-{idx:03d}")
    cur["historical"] = historical
    cur["actual"] = [actual_row]
    cur["forecast"] = rf.generate_forecast(
        _OPTS, historical, cur["seasonality"], cur["yoy_mode"],
    )
    snap = rf._save_forecast_snapshot(cur, "Plan 2026", _OPTS)
    rf._set_baseline_snapshot(cur, snap["id"])
    return cur


def _synthetic_clients(n: int, seed: int = 20260915) -> list[dict]:
    rng = random.Random(seed)
    return [_synthetic_client(i, rng) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# Medición
# ─────────────────────────────────────────────────────────────────────────────

def _median_seconds(fn, runs: int = _RUNS) -> float:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def _median_peak_bytes(fn, runs: int = _RUNS) -> float:
    peaks = []
    for _ in range(runs):
        tracemalloc.start()
        fn()
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
    return statistics.median(peaks)


def _mb(n_bytes: float) -> str:
    return f"{n_bytes / 1_048_576:.2f} MB"


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def test_perf_build_agency_dashboard():
    rows = []
    for n in _SIZES:
        clients = _synthetic_clients(n)
        run = lambda: ad._build_agency_dashboard(_PERIODS, clients=clients)  # noqa: E731
        run()  # warm-up de imports / caches de Python
        t = _median_seconds(run)
        peak = _median_peak_bytes(run)
        dash = run()
        assert len(dash["accounts"]) == n
        rows.append((n, t, peak))

    print("\n\n_build_agency_dashboard (puro) — 12 meses, mediana de 3")
    print(f"{'cuentas':>8} | {'tiempo':>10} | {'ms/cuenta':>9} | {'pico mem':>10}")
    for n, t, peak in rows:
        print(f"{n:>8} | {_ms(t):>10} | {t * 1000 / n:>9.2f} | {_mb(peak):>10}")


@pytest.fixture
def local_root(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "DATA_ROOT", tmp_path)
    fp._set_backend_for_testing(fp._LocalBackend())
    yield tmp_path
    fp._set_backend_for_testing(None)
    _clear_caches()


def _clear_caches() -> None:
    for f in (fp._list_forecast_clients, fp._load_forecast_client):
        if hasattr(f, "clear"):
            f.clear()


def _write_clients(root, clients: list[dict]) -> int:
    total = 0
    for c in clients:
        d = root / rf.AREA / c["id"] / rf.MODULE_SLUG
        d.mkdir(parents=True, exist_ok=True)
        text = json.dumps(c, indent=2, ensure_ascii=False)
        (d / "client.json").write_text(text, encoding="utf-8")
        total += len(text.encode("utf-8"))
    return total


def test_perf_load_agency_clients(local_root, tmp_path_factory, monkeypatch):
    rows = []
    for n in _SIZES:
        root = tmp_path_factory.mktemp(f"clients{n}")
        monkeypatch.setattr(fp, "DATA_ROOT", root)
        clients = _synthetic_clients(n)
        disk_bytes = _write_clients(root, clients)

        def cold():
            _clear_caches()
            return ad._load_agency_clients()

        def warm():
            return ad._load_agency_clients()

        cold()
        t_cold = _median_seconds(cold)
        peak_cold = _median_peak_bytes(cold)
        warm()
        t_warm = _median_seconds(warm)

        # Desglose de la corrida en frío: listar, leer (I/O + json + cache_data),
        # y deepcopy de lo leído.
        def list_only():
            _clear_caches()
            return fp._list_forecast_clients(rf.AREA, rf.MODULE_SLUG)

        slugs = [s for s in list_only() if s != "_meta"]

        def read_only():
            _clear_caches()
            return [fp._load_forecast_client(rf.AREA, s, rf.MODULE_SLUG, "client")
                    for s in slugs]

        # Lectura cruda por el backend, sin el wrapper st.cache_data (que
        # serializa el retorno): separa I/O + json del costo de la cache.
        backend = fp._LocalBackend()

        def read_raw():
            return [backend.load_client_config(rf.AREA, s, rf.MODULE_SLUG, "client")
                    for s in slugs]

        loaded = read_only()
        t_list = _median_seconds(list_only)
        t_read = _median_seconds(read_only)
        t_raw = _median_seconds(read_raw)
        t_copy = _median_seconds(lambda: [copy.deepcopy(c) for c in loaded])

        assert len(cold()) == n
        rows.append((n, disk_bytes, t_cold, peak_cold, t_warm, t_list, t_read,
                     t_raw, t_copy))

    print("\n\n_load_agency_clients (disco local tmp) — mediana de 3")
    print(f"{'clientes':>8} | {'JSON':>9} | {'frío':>9} | {'pico mem':>9} | "
          f"{'tibio':>9} | {'listar':>8} | {'leer':>9} | {'crudo':>9} | "
          f"{'deepcopy':>9} | {'% copy':>6}")
    for n, disk, t_cold, peak, t_warm, t_list, t_read, t_raw, t_copy in rows:
        print(f"{n:>8} | {_mb(disk):>9} | {_ms(t_cold):>9} | {_mb(peak):>9} | "
              f"{_ms(t_warm):>9} | {_ms(t_list):>8} | {_ms(t_read):>9} | "
              f"{_ms(t_raw):>9} | {_ms(t_copy):>9} | {t_copy / t_cold * 100:>5.0f}%")
