"""Feature 3 — alertas de rendimiento de campañas de Product Ads.

Separa el reporte en dos poblaciones que necesitan lecturas distintas: los
anuncios con tráfico suficiente, donde el ACOS y el ROAS son señales confiables,
y los que no tuvieron impresiones, donde el problema no es la eficiencia sino
la falta de exposición.
"""
from __future__ import annotations

import pandas as pd

from modules.mercado_libre import config

NIVEL_ROJO = "rojo"
NIVEL_AMARILLO = "amarillo"
NIVEL_OK = "ok"

ETIQUETA_NIVEL = {
    NIVEL_ROJO: f"Rojo — ROAS < {config.ROAS_ALERTA_ROJA:g}",
    NIVEL_AMARILLO: f"Amarillo — ACOS > {config.ACOS_ALERTA_AMARILLA:g}%",
    NIVEL_OK: "Sin alerta",
}

COLOR_NIVEL = {
    NIVEL_ROJO: config.COLOR_EMPEORO,
    NIVEL_AMARILLO: config.COLOR_AMARILLO,
    NIVEL_OK: config.COLOR_MEJORO,
}


def _nivel(acos, roas) -> str:
    """El rojo tiene prioridad: un anuncio puede disparar las dos condiciones."""
    if roas is not None and not pd.isna(roas) and roas < config.ROAS_ALERTA_ROJA:
        return NIVEL_ROJO
    if acos is not None and not pd.isna(acos) and acos > config.ACOS_ALERTA_AMARILLA:
        return NIVEL_AMARILLO
    return NIVEL_OK


def alertas_por_anuncio(ads: pd.DataFrame) -> pd.DataFrame:
    """Anuncios con clics suficientes, clasificados por nivel de alerta.

    Se filtra por volumen de clics porque debajo de ese umbral el ACOS y el ROAS
    se mueven por una sola conversión: alertar ahí genera revisiones que no
    llevan a ninguna decisión.
    """
    if ads.empty:
        return pd.DataFrame()

    activos = ads[ads["clics"] >= config.MIN_CLICS_ALERTA].copy()
    if activos.empty:
        return pd.DataFrame()

    activos["nivel"] = activos.apply(
        lambda fila: _nivel(fila["acos"], fila["roas"]), axis=1
    )

    columnas = [
        "campana", "anuncio", "mla", "estado", "impresiones", "clics",
        "inversion", "ingresos", "acos", "roas", "nivel",
    ]
    columnas = [c for c in columnas if c in activos.columns]

    orden_nivel = {NIVEL_ROJO: 0, NIVEL_AMARILLO: 1, NIVEL_OK: 2}
    activos["_orden"] = activos["nivel"].map(orden_nivel)

    return (
        activos.sort_values(["_orden", "inversion"], ascending=[True, False])
        [columnas]
        .reset_index(drop=True)
    )


def alertas_por_campana(ads: pd.DataFrame) -> pd.DataFrame:
    """Agregado por campaña sobre el total invertido, no sobre los anuncios filtrados.

    El ACOS y el ROAS de la campaña se recalculan desde la suma de inversión e
    ingresos. Promediar los porcentajes de cada anuncio daría un número distinto
    y engañoso, porque pesaría igual un anuncio de mil pesos que uno de cien mil.
    """
    if ads.empty:
        return pd.DataFrame()

    agregado = (
        ads.groupby("campana", as_index=False)
        .agg(
            anuncios=("mla", "size"),
            impresiones=("impresiones", "sum"),
            clics=("clics", "sum"),
            inversion=("inversion", "sum"),
            ingresos=("ingresos", "sum"),
        )
    )

    agregado["acos"] = (
        agregado["inversion"] / agregado["ingresos"].where(agregado["ingresos"] > 0)
    ) * 100
    agregado["roas"] = (
        agregado["ingresos"] / agregado["inversion"].where(agregado["inversion"] > 0)
    )
    agregado["nivel"] = agregado.apply(
        lambda fila: _nivel(fila["acos"], fila["roas"]), axis=1
    )

    return agregado.sort_values("inversion", ascending=False).reset_index(drop=True)


def anuncios_sin_impresiones(ads: pd.DataFrame) -> pd.DataFrame:
    """Anuncios que no se mostraron en el período.

    Es una lista de revisión distinta a la de eficiencia: acá el problema es de
    puja, presupuesto o estado del anuncio, no de rentabilidad. Se reportan
    aparte por pedido del equipo de cuentas.
    """
    if ads.empty:
        return pd.DataFrame()

    sin_impresiones = ads[ads["impresiones"] == 0].copy()
    if sin_impresiones.empty:
        return pd.DataFrame()

    columnas = ["campana", "anuncio", "mla", "estado", "impresiones", "clics"]
    columnas = [c for c in columnas if c in sin_impresiones.columns]
    return (
        sin_impresiones[columnas]
        .sort_values(["campana", "anuncio"])
        .reset_index(drop=True)
    )


def anuncios_con_pocos_clics(ads: pd.DataFrame) -> pd.DataFrame:
    """Anuncios con actividad pero por debajo del mínimo para alertar.

    No entran en la tabla de alertas ni en la de cero impresiones. Se listan
    para que quede claro que el módulo no los ignoró: simplemente todavía no
    tienen datos suficientes para juzgarlos.
    """
    if ads.empty:
        return pd.DataFrame()

    zona_gris = ads[
        (ads["impresiones"] > 0) & (ads["clics"] < config.MIN_CLICS_ALERTA)
    ].copy()
    if zona_gris.empty:
        return pd.DataFrame()

    columnas = ["campana", "anuncio", "mla", "impresiones", "clics",
                "inversion", "ingresos"]
    columnas = [c for c in columnas if c in zona_gris.columns]
    return (
        zona_gris[columnas]
        .sort_values("clics", ascending=False)
        .reset_index(drop=True)
    )


def resumen(ads: pd.DataFrame) -> dict:
    """Totales del período para las KPI cards."""
    if ads.empty:
        return {
            "anuncios": 0, "con_trafico": 0, "rojos": 0, "amarillos": 0,
            "sin_impresiones": 0, "inversion": 0.0, "ingresos": 0.0,
            "acos": None, "roas": None,
        }

    alertas = alertas_por_anuncio(ads)
    inversion = float(ads["inversion"].fillna(0).sum())
    ingresos = float(ads["ingresos"].fillna(0).sum())

    return {
        "anuncios": len(ads),
        "con_trafico": len(alertas),
        "rojos": int((alertas["nivel"] == NIVEL_ROJO).sum()) if not alertas.empty else 0,
        "amarillos": int((alertas["nivel"] == NIVEL_AMARILLO).sum()) if not alertas.empty else 0,
        "sin_impresiones": int((ads["impresiones"] == 0).sum()),
        "inversion": inversion,
        "ingresos": ingresos,
        "acos": (inversion / ingresos * 100) if ingresos > 0 else None,
        "roas": (ingresos / inversion) if inversion > 0 else None,
    }
