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


# Weeks run Sunday to Saturday, like Amazon's Business Report and the Gamboa HTML.
from datetime import date

import pytest

from modules.pages.sku_progress_report import _week_label_es, _week_of


@pytest.mark.parametrize(
    "year, week, label",
    [
        (2026, 2, "Ene 4-10"),
        (2026, 14, "Mar 29-Abr 4"),
        (2026, 33, "Ago 9-15"),
        (2026, 36, "Ago 30-Sep 5"),
        (2026, 53, "Dic 27-Ene 2"),
    ],
)
def test_week_label_va_de_domingo_a_sabado(year, week, label):
    assert _week_label_es(year, week) == label


@pytest.mark.parametrize(
    "day, week",
    [
        (date(2026, 8, 9), (2026, 33)),    # Sunday opens week 33
        (date(2026, 8, 15), (2026, 33)),   # Saturday closes it
        (date(2026, 12, 26), (2026, 52)),
        (date(2027, 1, 1), (2026, 53)),
        (date(2027, 1, 3), (2027, 1)),
        (date(2025, 12, 28), (2026, 1)),
    ],
)
def test_week_of_cuenta_la_semana_desde_el_domingo(day, week):
    assert _week_of(day) == week


def _stored_week(**over) -> dict:
    row = {"sku": "SKU-A", "week_iso": 33, "year": 2026, "week_label": "Ago 10-16",
           "sessions": 100, "units_ordered": 5}
    row.update(over)
    return row


def test_la_tabla_rotula_desde_el_numero_y_el_anio_no_desde_el_texto_guardado():
    from modules.pages.sku_progress_report import _weekly_table

    table = _weekly_table(pd.DataFrame([_stored_week()]))

    assert list(table["Fechas"]) == ["Ago 9-15"]


def test_sin_anio_o_semana_queda_el_rotulo_guardado():
    from modules.pages.sku_progress_report import _with_week_labels

    old = pd.DataFrame([_stored_week(year=None), _stored_week(week_iso=None)])

    assert list(_with_week_labels(old)["week_label"]) == ["Ago 10-16", "Ago 10-16"]
