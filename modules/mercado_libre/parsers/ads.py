"""Parser del reporte de publicidad (Product Ads) de Mercado Libre.

Estructura: tres hojas, los datos están en 'Reporte por Anuncios'. La fila 0
es un título agrupador, los nombres de columna están en la fila 1 y traen
saltos de línea con la definición de cada métrica. Los datos arrancan en la
fila 2, con las fechas del período en cada fila.

Los anuncios sin actividad exportan '-' en las métricas derivadas (CPC, CTR,
ACOS, ROAS). Ese guión se conserva como dato faltante y no se convierte a
cero: un anuncio sin impresiones no tiene un ROAS de 0, no tiene ROAS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .common import a_decimal, a_entero, normalizar_mla, normalizar_texto

HOJA = "Reporte por Anuncios"
FILA_ENCABEZADOS = 1

_MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_COLUMNAS_REQUERIDAS = {"campana", "numero de publicacion", "impresiones", "clics"}


@dataclass
class ReporteAds:
    datos: pd.DataFrame
    desde: date | None
    hasta: date | None


class ErrorFormato(Exception):
    """El archivo no tiene la forma esperada del reporte de publicidad."""


def _parsear_fecha(valor) -> date | None:
    """Convierte el formato '09-jul-2026' que usa el reporte de ads."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    texto = normalizar_texto(valor)
    match = re.match(r"(\d{1,2})-([a-z]{3})-(\d{4})", texto)
    if not match:
        return None
    dia, mes, anio = match.groups()
    numero_mes = _MESES_ABREV.get(mes)
    if numero_mes is None:
        return None
    return date(int(anio), numero_mes, int(dia))


def _acortar(nombre) -> str:
    """Limpia el encabezado, que trae la definición de la métrica en la celda.

    Los saltos de línea aparecen tanto separando la definición ('ACOS\\n(Inversión
    / Ingresos)') como partiendo el propio nombre ('Número de \\npublicación'),
    así que se descarta lo que está entre paréntesis en vez de cortar por el
    salto de línea.
    """
    texto = str(nombre).replace("\n", " ")
    texto = re.sub(r"\(.*?\)?$", "", texto)
    return normalizar_texto(texto)


def parsear(archivo) -> ReporteAds:
    try:
        crudo = pd.read_excel(archivo, sheet_name=HOJA, header=None)
    except ValueError as exc:
        raise ErrorFormato(
            f"El archivo no tiene una hoja llamada '{HOJA}'. Verificá que sea "
            "el reporte de publicidad sin modificar."
        ) from exc

    encabezados = [_acortar(c) for c in crudo.iloc[FILA_ENCABEZADOS].tolist()]
    faltantes = _COLUMNAS_REQUERIDAS - set(encabezados)
    if faltantes:
        raise ErrorFormato(
            "Al reporte de ads le faltan columnas esperadas: "
            + ", ".join(sorted(faltantes))
        )

    df = crudo.iloc[FILA_ENCABEZADOS + 1:].copy()
    df.columns = encabezados

    limpio = pd.DataFrame()
    limpio["desde"] = df["desde"].map(_parsear_fecha)
    limpio["hasta"] = df["hasta"].map(_parsear_fecha)
    limpio["campana"] = df["campana"].astype(str).str.strip()
    limpio["anuncio"] = df.get("titulo de anuncio", pd.Series(dtype=object)).astype(str).str.strip()
    limpio["mla"] = df["numero de publicacion"].map(normalizar_mla)
    limpio["estado"] = df.get("estado", pd.Series(dtype=object)).map(normalizar_texto)
    limpio["impresiones"] = df["impresiones"].map(a_entero).fillna(0).astype(int)
    limpio["clics"] = df["clics"].map(a_entero).fillna(0).astype(int)
    limpio["inversion"] = df.get("inversion", pd.Series(dtype=object)).map(a_decimal)
    limpio["ingresos"] = df.get("ingresos", pd.Series(dtype=object)).map(a_decimal)

    # ACOS y ROAS se recalculan desde inversión e ingresos en vez de leer las
    # columnas del reporte: así el criterio es el mismo al agregar por campaña,
    # donde no se pueden promediar los porcentajes de cada anuncio.
    inversion = limpio["inversion"].fillna(0)
    ingresos = limpio["ingresos"].fillna(0)
    limpio["acos"] = (inversion / ingresos.where(ingresos > 0)) * 100
    limpio["roas"] = ingresos / inversion.where(inversion > 0)

    limpio = limpio[limpio["campana"].notna() & (limpio["campana"] != "nan")].copy()

    fechas_desde = limpio["desde"].dropna()
    fechas_hasta = limpio["hasta"].dropna()
    return ReporteAds(
        datos=limpio.reset_index(drop=True),
        desde=fechas_desde.min() if len(fechas_desde) else None,
        hasta=fechas_hasta.max() if len(fechas_hasta) else None,
    )
