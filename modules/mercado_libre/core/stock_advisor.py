"""Feature 2 — sugerencia de reposición de stock.

Cruza la velocidad de venta del reporte de rendimiento con el stock en depósito
del export de publicaciones, y descuenta lo que ya viene en camino. El objetivo
es que no se quede sin stock lo que más se vende, sin sobre-stockear el resto.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from modules.mercado_libre import config


def _a_fecha(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, date) and not isinstance(valor, pd.Timestamp):
        return valor
    convertido = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(convertido) else convertido.date()


def _transito_util(transito: pd.DataFrame, hoy: date) -> pd.DataFrame:
    """Suma por MLA solo lo que llega dentro del horizonte de cobertura.

    Una unidad que arriba dentro de los 30 días efectivamente cubre el período
    y hay que descontarla de la sugerencia. Una que llega en 40 no sirve para
    cubrirlo: si se descontara igual, el sistema recomendaría de menos y la
    publicación se quedaría sin stock antes de que llegue el envío.
    """
    if transito is None or transito.empty:
        return pd.DataFrame(columns=["mla", "en_transito", "transito_tardio"])

    datos = transito.copy()
    datos["_llegada"] = datos["fecha_llegada"].map(_a_fecha)
    datos["unidades"] = pd.to_numeric(datos["unidades"], errors="coerce").fillna(0)

    limite = config.DIAS_COBERTURA_OBJETIVO
    datos["_dias"] = datos["_llegada"].map(
        lambda f: (f - hoy).days if f is not None else None
    )
    # Sin fecha se asume que llega dentro del horizonte: es el criterio
    # conservador para no sugerir un envío que ya está en camino.
    datos["_a_tiempo"] = datos["_dias"].map(
        lambda d: True if d is None else d <= limite
    )

    a_tiempo = (
        datos[datos["_a_tiempo"]]
        .groupby("mla", as_index=False)["unidades"].sum()
        .rename(columns={"unidades": "en_transito"})
    )
    tardio = (
        datos[~datos["_a_tiempo"]]
        .groupby("mla", as_index=False)["unidades"].sum()
        .rename(columns={"unidades": "transito_tardio"})
    )
    return a_tiempo.merge(tardio, on="mla", how="outer").fillna(0)


def sugerir_reposicion(
    rendimiento: pd.DataFrame,
    publicaciones: pd.DataFrame,
    transito: pd.DataFrame | None = None,
    hoy: date | None = None,
    dias_periodo: int | None = None,
) -> pd.DataFrame:
    """Calcula cuántas unidades enviar por publicación.

    Args:
        rendimiento: snapshot del reporte de rendimiento (unidades vendidas).
        publicaciones: export de publicaciones con stock y estado.
        transito: opcional, unidades en camino con su fecha estimada de llegada.
        dias_periodo: días que cubre el reporte de rendimiento. Si el reporte no
            cubre exactamente la ventana de referencia, la velocidad se normaliza
            con los días reales en vez de asumir el valor configurado.

    Returns:
        Una fila por publicación, ordenada por facturación descendente: lo que
        más factura es lo que más caro sale quedarse sin stock.
    """
    hoy = hoy or date.today()
    dias_periodo = dias_periodo or config.DIAS_VELOCIDAD_VENTA

    if rendimiento.empty or publicaciones.empty:
        return pd.DataFrame()

    ventas = rendimiento[["mla", "unidades", "facturacion"]].copy()
    stock = publicaciones[["mla", "titulo", "stock", "estado", "precio"]].copy()

    # El título sale del export de publicaciones: es el que las chicas ven en
    # el panel de MELI, y existe también para las que no tuvieron visitas.
    datos = stock.merge(ventas, on="mla", how="left")
    datos["unidades"] = datos["unidades"].fillna(0)
    datos["facturacion"] = datos["facturacion"].fillna(0)

    # Las publicaciones que no pueden vender no generan necesidad de reposición.
    datos = datos[~datos["estado"].isin(config.ESTADOS_EXCLUIDOS_STOCK)].copy()

    datos["velocidad_diaria"] = datos["unidades"] / dias_periodo
    datos["necesidad"] = datos["velocidad_diaria"] * config.DIAS_COBERTURA_OBJETIVO

    en_transito = _transito_util(transito, hoy)
    if not en_transito.empty:
        datos = datos.merge(en_transito, on="mla", how="left")
    else:
        datos["en_transito"] = 0.0
        datos["transito_tardio"] = 0.0
    datos["en_transito"] = datos["en_transito"].fillna(0)
    datos["transito_tardio"] = datos["transito_tardio"].fillna(0)

    disponible = datos["stock"] + datos["en_transito"]
    datos["sugerido"] = (datos["necesidad"] - disponible).clip(lower=0).round()

    # Días de cobertura con lo que hay hoy: es el número que ordena la urgencia.
    datos["dias_cobertura"] = disponible / datos["velocidad_diaria"].where(
        datos["velocidad_diaria"] > 0
    )

    datos["urgencia"] = datos.apply(_clasificar_urgencia, axis=1)

    columnas = [
        "mla", "titulo", "estado", "stock", "en_transito", "transito_tardio",
        "unidades", "velocidad_diaria", "dias_cobertura", "necesidad",
        "sugerido", "facturacion", "precio", "urgencia",
    ]
    return (
        datos[columnas]
        .sort_values(["facturacion", "sugerido"], ascending=False)
        .reset_index(drop=True)
    )


def _clasificar_urgencia(fila) -> str:
    """Prioriza por cuánto falta para quedarse sin stock, no por cantidad."""
    if fila["velocidad_diaria"] <= 0:
        return "sin_ventas"
    cobertura = fila["dias_cobertura"]
    if pd.isna(cobertura):
        return "sin_ventas"
    if cobertura <= 7:
        return "critico"
    if cobertura <= 15:
        return "alto"
    if cobertura <= config.DIAS_COBERTURA_OBJETIVO:
        return "medio"
    return "ok"


def resumen(sugerencias: pd.DataFrame) -> dict:
    """Totales para las KPI cards de la vista."""
    if sugerencias.empty:
        return {
            "publicaciones": 0, "a_reponer": 0, "unidades_sugeridas": 0,
            "criticos": 0, "sin_ventas": 0,
        }
    return {
        "publicaciones": len(sugerencias),
        "a_reponer": int((sugerencias["sugerido"] > 0).sum()),
        "unidades_sugeridas": int(sugerencias["sugerido"].sum()),
        "criticos": int((sugerencias["urgencia"] == "critico").sum()),
        "sin_ventas": int((sugerencias["urgencia"] == "sin_ventas").sum()),
    }
