"""Parser del export 'Modifica tus publicaciones' (stock y estado).

Estructura del archivo: tres hojas, los datos están en 'Publicaciones'. La
fila 0 trae los nombres técnicos de columna (ITEM_ID, STOCK_FLEX, STATUS) y
las filas 1 a 5 son texto de ayuda de Mercado Libre. Los datos arrancan en la
fila 6.

Se usan los nombres técnicos y no los rótulos en español porque los primeros
son estables entre exports mientras que los segundos cambian con el idioma de
la cuenta.
"""
from __future__ import annotations

import pandas as pd

from .common import a_decimal, a_entero, normalizar_mla, normalizar_texto

HOJA = "Publicaciones"
FILA_TECNICOS = 0
PRIMERA_FILA_DATOS = 6

_COLUMNAS_REQUERIDAS = {"ITEM_ID", "STOCK_FLEX", "STATUS"}

# El seguimiento excluye publicaciones que no pueden vender.
_ESTADOS_EXCLUIDOS = {"pausada", "inactiva", "finalizada", "cerrada", "bajo revision"}


class ErrorFormato(Exception):
    """El archivo no tiene la forma esperada del export de publicaciones."""


def parsear(archivo, excluir_inactivas: bool = True) -> pd.DataFrame:
    try:
        crudo = pd.read_excel(archivo, sheet_name=HOJA, header=None)
    except ValueError as exc:
        raise ErrorFormato(
            f"El archivo no tiene una hoja llamada '{HOJA}'. Verificá que sea "
            "el export de 'Modifica tus publicaciones' sin modificar."
        ) from exc

    tecnicos = [str(c).strip() for c in crudo.iloc[FILA_TECNICOS].tolist()]
    faltantes = _COLUMNAS_REQUERIDAS - set(tecnicos)
    if faltantes:
        raise ErrorFormato(
            "Al export le faltan columnas esperadas: " + ", ".join(sorted(faltantes))
        )

    df = crudo.iloc[PRIMERA_FILA_DATOS:].copy()
    df.columns = tecnicos

    limpio = pd.DataFrame()
    limpio["mla"] = df["ITEM_ID"].map(normalizar_mla)
    limpio["variacion"] = df.get("VARIATION_ID")
    limpio["sku"] = df.get("SKU")
    limpio["titulo"] = df.get("TITLE", pd.Series(dtype=object)).astype(str).str.strip()
    limpio["stock"] = df["STOCK_FLEX"].map(a_entero)
    limpio["precio"] = df.get("PRICE", pd.Series(dtype=object)).map(a_decimal)
    limpio["estado"] = df["STATUS"].map(normalizar_texto)

    limpio = limpio[limpio["mla"].notna()].copy()
    limpio["stock"] = limpio["stock"].fillna(0)

    if excluir_inactivas:
        limpio = limpio[~limpio["estado"].isin(_ESTADOS_EXCLUIDOS)].copy()

    # El export desglosa por variante; el resto del módulo trabaja a nivel
    # publicación, así que el stock se suma y se conserva el detalle aparte.
    agregado = (
        limpio.groupby("mla", as_index=False)
        .agg(
            titulo=("titulo", "first"),
            estado=("estado", "first"),
            stock=("stock", "sum"),
            precio=("precio", "median"),
            variantes=("mla", "size"),
        )
    )
    return agregado
