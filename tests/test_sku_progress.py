"""Tests de M28 SKU Progress Report — coalesce de category en eventos de optimización.

Primer test de M28. Cubre el helper puro `_coalesce_category`, que rellena la
columna `category` ausente/nula/vacía con SIN_CATEGORIA en LECTURA (sin reescribir
el parquet). Filas viejas (pre-Bloque 1) no tienen la columna; este coalesce las
completa al cargarlas.

Asierta SIEMPRE sobre el valor RETORNADO por el helper.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.pages.sku_progress_report import _coalesce_category, SIN_CATEGORIA


def test_coalesce_category_columna_ausente():
    """Caso 1: df SIN columna 'category' → tras helper, la columna existe y todo == SIN_CATEGORIA."""
    df = pd.DataFrame(
        {
            "sku": ["SKU-A", "SKU-B"],
            "week_iso": [10, 11],
            "year": [2026, 2026],
            "label": ["Cambio de imagenes", "Update bullets"],
        }
    )
    assert "category" not in df.columns  # precondición: fila vieja sin la columna

    out = _coalesce_category(df)

    assert "category" in out.columns
    assert list(out["category"]) == [SIN_CATEGORIA, SIN_CATEGORIA]


def test_coalesce_category_nulos_y_vacios():
    """Caso 2: 'category' con NaN, None y "" mezclados con válidos →
    NaN/None/"" se vuelven SIN_CATEGORIA; los válidos quedan intactos."""
    df = pd.DataFrame(
        {
            "sku": ["A", "B", "C", "D", "E"],
            "label": ["l1", "l2", "l3", "l4", "l5"],
            "category": ["Main Image", None, np.nan, "", "Bullets"],
        }
    )

    out = _coalesce_category(df)

    assert list(out["category"]) == [
        "Main Image",      # válido → intacto
        SIN_CATEGORIA,     # None → coalesce
        SIN_CATEGORIA,     # NaN → coalesce
        SIN_CATEGORIA,     # "" → coalesce
        "Bullets",         # válido → intacto
    ]


def test_coalesce_category_df_vacio():
    """Caso 3: df vacío (optimizations.empty) → no rompe, retorna vacío."""
    df = pd.DataFrame()

    out = _coalesce_category(df)

    assert isinstance(out, pd.DataFrame)
    assert out.empty
