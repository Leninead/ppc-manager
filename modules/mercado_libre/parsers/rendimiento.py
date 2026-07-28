"""Parser del reporte de rendimiento de publicaciones de Mercado Libre.

Estructura del archivo: las primeras 5 filas son encabezado descriptivo (la
fila 2 contiene el período en prosa) y los nombres de columna están en la
fila 5. Los datos arrancan en la fila 6.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .common import (a_decimal, a_entero, extraer_periodo, normalizar_mla,
                     normalizar_texto)

FILA_ENCABEZADOS = 5
FILA_PERIODO = 2

_COLUMNAS_REQUERIDAS = {
    "id de la publicacion", "publicacion", "estado actual",
    "visitas unicas", "cantidad de ventas", "unidades vendidas",
}


@dataclass
class ReporteRendimiento:
    """Resultado del parseo: los datos más el período que cubren."""
    datos: pd.DataFrame
    desde: date
    hasta: date

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1


class ErrorFormato(Exception):
    """El archivo no tiene la forma esperada de un reporte de rendimiento."""


def parsear(archivo) -> ReporteRendimiento:
    crudo = pd.read_excel(archivo, sheet_name=0, header=None)

    periodo = extraer_periodo(crudo.iloc[FILA_PERIODO, 0]) if len(crudo) > FILA_PERIODO else None
    if periodo is None:
        raise ErrorFormato(
            "No se pudo leer el período del reporte. Verificá que sea el export "
            "de 'Métricas del rendimiento de tus publicaciones' sin modificar."
        )
    desde, hasta = periodo

    archivo.seek(0) if hasattr(archivo, "seek") else None
    df = pd.read_excel(archivo, sheet_name=0, header=FILA_ENCABEZADOS)
    df.columns = [normalizar_texto(c) for c in df.columns]

    faltantes = _COLUMNAS_REQUERIDAS - set(df.columns)
    if faltantes:
        raise ErrorFormato(
            "Al reporte le faltan columnas esperadas: "
            + ", ".join(sorted(faltantes))
            + ". Puede que Mercado Libre haya cambiado el formato del export."
        )

    limpio = pd.DataFrame()
    limpio["mla"] = df["id de la publicacion"].map(normalizar_mla)
    limpio["titulo"] = df["publicacion"].astype(str).str.strip()
    limpio["estado"] = df["estado actual"].map(normalizar_texto)
    limpio["variante"] = df.get("variante", pd.Series(dtype=object))
    limpio["sku"] = df.get("sku", pd.Series(dtype=object))
    limpio["visitas"] = df["visitas unicas"].map(a_entero)
    limpio["ventas"] = df["cantidad de ventas"].map(a_entero)
    limpio["unidades"] = df["unidades vendidas"].map(a_entero)

    if "ventas brutas (ars)" in df.columns:
        limpio["facturacion"] = df["ventas brutas (ars)"].map(a_decimal)
    else:
        limpio["facturacion"] = None

    limpio = limpio[limpio["mla"].notna()].copy()

    # El reporte trae una fila por variante. El seguimiento se definió a nivel
    # publicación, así que se agregan las variantes antes de cualquier cálculo.
    agregado = (
        limpio.groupby("mla", as_index=False)
        .agg(
            titulo=("titulo", "first"),
            estado=("estado", "first"),
            visitas=("visitas", "sum"),
            ventas=("ventas", "sum"),
            unidades=("unidades", "sum"),
            facturacion=("facturacion", "sum"),
            variantes=("mla", "size"),
        )
    )

    # La conversión se recalcula en vez de promediar la columna del reporte:
    # promediar porcentajes de variantes con distinto tráfico da un número que
    # no representa la publicación.
    visitas_validas = agregado["visitas"].where(agregado["visitas"] > 0)
    agregado["conversion"] = agregado["ventas"] / visitas_validas

    agregado["desde"] = desde
    agregado["hasta"] = hasta

    return ReporteRendimiento(datos=agregado, desde=desde, hasta=hasta)
