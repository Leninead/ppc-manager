"""Utilidades compartidas por los parsers de Mercado Libre.

El problema central que resuelve este módulo: los exports de MELI vienen en
formato numérico español (punto = separador de miles, coma = decimal). Pandas
los interpreta al revés, así que una publicación con 1.564 visitas se lee como
1,564 visitas. Sin esta normalización, todos los cálculos de conversión,
velocidad de venta y alertas salen mal por un factor de 1000.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalizar_texto(valor) -> str:
    """Minúsculas, sin acentos y sin espacios duplicados."""
    if pd.isna(valor):
        return ""
    txt = unicodedata.normalize("NFKD", str(valor))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def a_entero(valor) -> int | None:
    """Convierte un valor de MELI a entero respetando el formato español.

    Acepta lo que ya viene numérico y lo que viene como texto con separadores.
    Devuelve None si el valor está vacío o no es interpretable, para poder
    distinguir "sin dato" de "cero" más adelante.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int,)) and not isinstance(valor, bool):
        return int(valor)

    if isinstance(valor, float):
        # Pandas ya rompió el número: 1.564 era en realidad 1564.
        # Un float con parte decimal en una columna de conteos siempre es
        # un separador de miles mal interpretado.
        if valor.is_integer():
            return int(valor)
        texto = f"{valor!r}"
    else:
        texto = str(valor)

    texto = texto.strip()
    if texto in ("", "-", "—", "N/A", "n/a"):
        return None

    texto = re.sub(r"[^\d,.\-]", "", texto)
    if not texto:
        return None

    # Formato español: el punto separa miles y la coma decimales.
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return int(round(float(texto)))
    except ValueError:
        return None


def a_decimal(valor) -> float | None:
    """Convierte importes y porcentajes ('$ 221.658', '3,8%') a float."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)

    texto = str(valor).strip()
    if texto in ("", "-", "—", "N/A", "n/a"):
        return None

    es_porcentaje = "%" in texto
    texto = re.sub(r"[^\d,.\-]", "", texto)
    if not texto:
        return None

    texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero / 100 if es_porcentaje else numero


def normalizar_mla(valor) -> str | None:
    """Unifica el ID de publicación al formato MLA1234567890.

    El reporte de rendimiento exporta el ID sin prefijo (869673559) mientras
    que Publicaciones y Ads lo traen completo (MLA869673559). Sin esta
    normalización el cruce entre reportes no encuentra ninguna coincidencia.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip().upper().replace(" ", "")
    if not texto or texto in ("-", "—"):
        return None
    if texto.endswith(".0"):
        texto = texto[:-2]
    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return None
    return f"MLA{digitos}"


def extraer_periodo(texto) -> tuple[date, date] | None:
    """Lee el rango de fechas del encabezado del reporte de rendimiento.

    MELI escribe el período en prosa: "...desde el 2 de julio de 2026 hasta el
    17 de julio de 2026." Extraerlo evita pedirle las fechas al usuario y hace
    que cada carga se guarde con su ventana real.
    """
    limpio = normalizar_texto(texto)
    patron = r"(\d{1,2}) de ([a-z]+) de (\d{4})"
    encontrados = re.findall(patron, limpio)
    if len(encontrados) < 2:
        return None

    fechas = []
    for dia, mes, anio in encontrados[:2]:
        numero_mes = _MESES.get(mes)
        if numero_mes is None:
            return None
        fechas.append(date(int(anio), numero_mes, int(dia)))

    desde, hasta = sorted(fechas)
    return desde, hasta
