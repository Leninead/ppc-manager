"""Feature 1 — evaluación del impacto de los cambios en publicaciones.

Equivalente en Mercado Libre del SKU Progress Report de Amazon. Para cada
cambio registrado busca el snapshot que cubre la ventana previa y el que cubre
la posterior, y clasifica el resultado sobre visitas y conversión.

La comparación se apoya en el histórico de snapshots, no en un único archivo:
el reporte que sube el equipo es una foto de un período, así que sin acumular
períodos no hay contra qué comparar. La consecuencia práctica es que el tracker
recién muestra resultados a partir de la segunda o tercera carga.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from modules.mercado_libre import config


def _a_fecha(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, date) and not isinstance(valor, pd.Timestamp):
        return valor
    convertido = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(convertido) else convertido.date()


def _variacion(antes, despues) -> float | None:
    """Variación relativa entre dos valores. None si no se puede calcular."""
    if antes is None or despues is None:
        return None
    if pd.isna(antes) or pd.isna(despues):
        return None
    if antes == 0:
        return None
    return (despues - antes) / antes


def _clasificar(variacion) -> str:
    if variacion is None:
        return config.RESULTADO_SIN_DATOS
    if variacion >= config.UMBRAL_MEJORA:
        return config.RESULTADO_MEJORO
    if variacion <= config.UMBRAL_EMPEORO:
        return config.RESULTADO_EMPEORO
    return config.RESULTADO_NEUTRO


def _ventana_previa(historia: pd.DataFrame, mla: str, fecha_cambio: date):
    """Último snapshot que termina antes o el mismo día del cambio."""
    candidatos = historia[
        (historia["mla"] == mla) & (historia["_hasta"] <= fecha_cambio)
    ]
    if candidatos.empty:
        return None
    return candidatos.sort_values("_hasta").iloc[-1]


def _ventana_posterior(historia: pd.DataFrame, mla: str, fecha_cambio: date):
    """Primer snapshot que arranca después del cambio y ya está completo.

    Se exige que el snapshot empiece el día del cambio o después para que el
    período no mezcle días previos y posteriores, lo que diluiría el efecto.
    """
    candidatos = historia[
        (historia["mla"] == mla) & (historia["_desde"] >= fecha_cambio)
    ]
    if candidatos.empty:
        return None
    return candidatos.sort_values("_desde").iloc[0]


def evaluar_cambios(
    historia: pd.DataFrame,
    cambios: pd.DataFrame,
    hoy: date | None = None,
) -> pd.DataFrame:
    """Cruza el log de cambios contra el histórico de snapshots.

    Args:
        historia: salida de _load_history del módulo de rendimiento. Una fila
            por MLA y período, con las columnas desde/hasta/visitas/conversion.
        cambios: log append-only de cambios aplicados.
        hoy: fecha de referencia para distinguir un cambio pendiente de
            evaluación de uno que ya debería tener datos.

    Returns:
        Un DataFrame con una fila por cambio registrado, con el resultado sobre
        visitas y conversión. Nunca descarta filas: un cambio sin datos aparece
        con su motivo, para que el equipo no crea que se perdió.
    """
    hoy = hoy or date.today()

    if cambios.empty:
        return pd.DataFrame()

    if historia.empty:
        historia = pd.DataFrame(columns=["mla", "desde", "hasta", "visitas",
                                         "ventas", "conversion"])

    historia = historia.copy()
    historia["_desde"] = historia["desde"].map(_a_fecha)
    historia["_hasta"] = historia["hasta"].map(_a_fecha)
    historia = historia[historia["_desde"].notna() & historia["_hasta"].notna()]

    filas = []
    for cambio in cambios.itertuples(index=False):
        mla = getattr(cambio, "mla", None)
        fecha_cambio = _a_fecha(getattr(cambio, "fecha_cambio", None))
        if not mla or fecha_cambio is None:
            continue

        tipo = getattr(cambio, "tipo_cambio", "otro") or "otro"
        previa = _ventana_previa(historia, mla, fecha_cambio)
        posterior = _ventana_posterior(historia, mla, fecha_cambio)

        fila = {
            "mla": mla,
            "titulo": getattr(cambio, "descripcion", "") or "",
            "fecha_cambio": fecha_cambio,
            "tipo_cambio": tipo,
            "metrica_principal": config.METRICA_PRINCIPAL.get(tipo, "conversion"),
        }

        if previa is None or posterior is None:
            # Un cambio reciente todavía no tiene período posterior cargado: eso
            # es normal y se marca como pendiente. Si ya pasó el tiempo y sigue
            # sin datos, el motivo es otro y conviene distinguirlo.
            dias_transcurridos = (hoy - fecha_cambio).days
            if posterior is None and dias_transcurridos < config.VENTANA_DIAS:
                fila["resultado"] = config.RESULTADO_PENDIENTE
                fila["motivo"] = (
                    f"El cambio tiene {dias_transcurridos} días. Se necesita un "
                    f"reporte que cubra al menos {config.VENTANA_DIAS} días "
                    "posteriores."
                )
            else:
                falta = "previo" if previa is None else "posterior"
                fila["resultado"] = config.RESULTADO_PENDIENTE
                fila["motivo"] = f"Falta el reporte {falta} a la fecha del cambio."
            fila.update({
                "visitas_antes": None, "visitas_despues": None, "var_visitas": None,
                "conv_antes": None, "conv_despues": None, "var_conversion": None,
                "resultado_visitas": config.RESULTADO_PENDIENTE,
                "resultado_conversion": config.RESULTADO_PENDIENTE,
                "periodo_antes": None, "periodo_despues": None,
            })
            filas.append(fila)
            continue

        visitas_antes = previa["visitas"]
        visitas_despues = posterior["visitas"]
        conv_antes = previa["conversion"]
        conv_despues = posterior["conversion"]

        sin_trafico = (
            pd.isna(visitas_antes) or pd.isna(visitas_despues)
            or visitas_antes < config.MIN_VISITAS_EVALUACION
            or visitas_despues < config.MIN_VISITAS_EVALUACION
        )

        var_visitas = _variacion(visitas_antes, visitas_despues)
        var_conversion = _variacion(conv_antes, conv_despues)

        if sin_trafico:
            resultado_visitas = config.RESULTADO_SIN_DATOS
            resultado_conversion = config.RESULTADO_SIN_DATOS
            motivo = (
                f"Menos de {config.MIN_VISITAS_EVALUACION} visitas en alguna de "
                "las dos ventanas."
            )
        else:
            resultado_visitas = _clasificar(var_visitas)
            resultado_conversion = _clasificar(var_conversion)
            motivo = ""

        principal = fila["metrica_principal"]
        resultado = (
            resultado_visitas if principal == "visitas" else resultado_conversion
        )

        fila.update({
            "visitas_antes": visitas_antes,
            "visitas_despues": visitas_despues,
            "var_visitas": var_visitas,
            "conv_antes": conv_antes,
            "conv_despues": conv_despues,
            "var_conversion": var_conversion,
            "resultado_visitas": resultado_visitas,
            "resultado_conversion": resultado_conversion,
            "resultado": resultado,
            "motivo": motivo,
            "periodo_antes": f"{previa['_desde']} → {previa['_hasta']}",
            "periodo_despues": f"{posterior['_desde']} → {posterior['_hasta']}",
        })
        filas.append(fila)

    resultado_df = pd.DataFrame(filas)
    if resultado_df.empty:
        return resultado_df

    return resultado_df.sort_values(
        ["fecha_cambio", "mla"], ascending=[False, True]
    ).reset_index(drop=True)


def marcar_solapamientos(evaluacion: pd.DataFrame) -> pd.DataFrame:
    """Señala cambios demasiado próximos entre sí sobre la misma publicación.

    Si dos cambios sobre el mismo MLA ocurren a menos de una ventana de
    distancia, sus períodos de comparación se pisan y el segundo arrastra el
    efecto del primero. No se puede corregir con los datos disponibles, pero sí
    advertirlo para que nadie atribuya el resultado al cambio equivocado.
    """
    if evaluacion.empty:
        return evaluacion

    evaluacion = evaluacion.copy()
    evaluacion["solapado"] = False

    for mla, grupo in evaluacion.groupby("mla"):
        fechas = grupo.sort_values("fecha_cambio")
        anterior = None
        for idx, fila in fechas.iterrows():
            if anterior is not None:
                distancia = (fila["fecha_cambio"] - anterior).days
                if distancia < config.VENTANA_DIAS:
                    evaluacion.loc[idx, "solapado"] = True
            anterior = fila["fecha_cambio"]

    return evaluacion


def resumen(evaluacion: pd.DataFrame) -> dict:
    """Conteo por resultado, para las KPI cards de la vista."""
    if evaluacion.empty:
        return {clave: 0 for clave in config.ETIQUETA_RESULTADO}
    conteo = evaluacion["resultado"].value_counts().to_dict()
    return {clave: int(conteo.get(clave, 0)) for clave in config.ETIQUETA_RESULTADO}
