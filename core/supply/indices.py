"""Cálculo de la tabla de índices estacionales (M37 B2.1b).

Contraparte de `core/supply/seasonality.py`: allá se CONSUME una tabla de
índices (desestacionalizar, reestacionalizar, validar), acá se CALCULA desde
historia de ventas. La tabla que sale de este módulo es exactamente la que
entra allá — mismo shape `dict[grupo, list[float]]` de 12 posiciones.

Por qué se calcula en vez de heredarse: los índices de Fede son del pool USA de
Gamboa y no sirven para Dermaglos, LTD ni ninguna otra cuenta. Sus tablas quedan
como caso de prueba, no como fuente. Ver
`notes/supply-chain/hallazgos-tablas-indices.md`.

Regla dura, la misma de `supply_seasonality`:
- CERO acceso a disco, CERO Streamlit, CERO import de `supply_persistence`.
  La historia entra como DataFrame por parámetro; de dónde salió es problema
  del caller.
- La normalización y el clamp NO se reimplementan: se delegan en
  `normalizar_tabla` de `supply_seasonality`, que es su dueño.

Dos cosas se declaran en vez de quedar mudas, porque el consumidor no puede
distinguirlas mirando el número:
- `meta["corregido_por_quiebres"]` es SIEMPRE False. La plataforma no tiene
  fuente de inventario histórico (verificado 2026-09-14), así que estos índices
  miden venta, no demanda. Un mes quebrado se ve como un mes flojo.
- `meses_estimados` lista los meses que quedaron en 1.0 por falta de datos. Es
  el mismo relleno que hizo el Forecast v3 de Fede, con la diferencia de que
  allá quedaba mudo y nadie podía saber después si un 1.0 era medido o inventado.

API pública:
    agregar_a_mensual(historia)                          -> pd.DataFrame
    calcular_indices(historia, agrupar_por, minimo_meses, pesos_anios) -> dict
    indices_por_sku(historia, minimo_meses, pesos_anios) -> dict
    resolver_indice(tablas, sku, categoria, mes)         -> tuple[float, str]
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from core.supply.seasonality import INDICE_NEUTRO, MESES, normalizar_tabla

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

_PERIOD_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")
"""Formato canónico del período de M28: '2026-W14'. Cualquier otra cosa es dato
sucio y su fila se descarta — nunca se intenta adivinar la intención."""

_DIA_ANCLA_ISO = 4
"""Jueves. Es el día que decide a qué mes y año pertenece una semana ISO; el
porqué está en el docstring de `agregar_a_mensual`."""

_COLS_MENSUAL = ("anio", "mes", "sku", "category", "units_ordered")
"""Shape de salida de `agregar_a_mensual`. Fijo aunque el resultado sea vacío:
un DataFrame sin columnas rompe a cualquier consumidor que filtre por nombre."""

_CLAVES_AGRUPACION = ("anio", "mes", "sku", "category")

ORIGEN_SKU = "sku"
ORIGEN_CATEGORIA = "category"
ORIGEN_NEUTRO = "neutro"
"""Los tres orígenes posibles de un índice resuelto. Viajan junto al valor
porque un 1.0 puede significar 'este mes es promedio' o 'no tengo idea', y el
consumidor tiene que poder distinguirlos."""


# ─────────────────────────────────────────────────────────────────────────────
# Semana ISO -> mes calendario
# ─────────────────────────────────────────────────────────────────────────────


def _periodo_a_anio_mes(period) -> tuple[int, int] | None:
    """'2026-W14' -> (2026, 4), por el jueves de esa semana. None si es inválido.

    Nunca lanza: una fila con período roto no aporta, pero no tumba la corrida.
    """
    m = _PERIOD_RE.match(str(period).strip())
    if m is None:
        return None
    anio, semana = int(m.group(1)), int(m.group(2))
    try:
        jueves = date.fromisocalendar(anio, semana, _DIA_ANCLA_ISO)
    except ValueError:
        # Semana 0, 53 en un año que no la tiene, o fuera de rango.
        return None
    return jueves.year, jueves.month


def agregar_a_mensual(historia: pd.DataFrame) -> pd.DataFrame:
    """Colapsa la historia semanal de M28 a totales mensuales por SKU.

    **La regla del jueves.** Una semana ISO no respeta los meses: puede empezar
    en uno y terminar en otro, e incluso cruzar el año. ISO 8601 resuelve la
    ambigüedad con el jueves, que es el día del medio y por lo tanto garantiza
    que la mayoría de la semana cae del mismo lado que él. Se aplica igual acá
    para que la misma historia produzca siempre los mismos índices, sin depender
    de quién la agregue.

    Los dos casos borde que rompen cualquier implementación que parsee el año
    del string y después mire el lunes:

    - `2026-W01` empieza el 29-dic-**2025** y su jueves es el 1-ene-2026, así
      que la semana entera cuenta para **enero de 2026**.
    - `2026-W53` termina el 3-ene-**2027** y su jueves es el 31-dic-2026, así
      que cuenta para **diciembre de 2026**.

    Args:
        historia: DataFrame con columnas `period` ('2026-W14'), `sku`,
            `category`, `units_ordered`. Es el shape que persiste M28 en
            `data/account-health/<cliente>/sku-progress/<YYYY-WW>.parquet`.

    Returns:
        DataFrame con `anio`, `mes` (1-12), `sku`, `category` y `units_ordered`
        sumado. Las filas con `period` inválido se descartan en silencio; si no
        queda ninguna, el DataFrame vuelve vacío pero con sus columnas.
    """
    filas: list[dict] = []

    for registro in historia.to_dict("records"):
        anio_mes = _periodo_a_anio_mes(registro.get("period"))
        if anio_mes is None:
            continue
        anio, mes = anio_mes
        filas.append(
            {
                "anio": anio,
                "mes": mes,
                "sku": registro.get("sku"),
                "category": registro.get("category"),
                "units_ordered": pd.to_numeric(
                    registro.get("units_ordered"), errors="coerce"
                ),
            }
        )

    df = pd.DataFrame(filas, columns=list(_COLS_MENSUAL))
    if df.empty:
        return df

    df["units_ordered"] = df["units_ordered"].fillna(0)
    return df.groupby(list(_CLAVES_AGRUPACION), as_index=False)["units_ordered"].sum()


# ─────────────────────────────────────────────────────────────────────────────
# Perfil mensual de un grupo
# ─────────────────────────────────────────────────────────────────────────────


def _promedio_ponderado(por_anio: pd.Series, pesos_anios: tuple[float, ...]) -> float:
    """Combina las observaciones de un mismo mes en distintos años.

    El año más reciente pesa `pesos_anios[0]`, el anterior `pesos_anios[1]`, y
    así. Sobran años -> se descartan los más viejos. Faltan años -> los pesos
    disponibles se renormalizan para que sigan sumando 1, si no la serie entera
    quedaría escalada hacia abajo.
    """
    anios = list(por_anio.sort_index(ascending=False).index)[: len(pesos_anios)]
    pesos = list(pesos_anios[: len(anios)])

    total_peso = sum(pesos)
    if not anios or total_peso <= 0:
        return float(por_anio.mean())

    return float(
        sum(peso * por_anio[anio] for peso, anio in zip(pesos, anios)) / total_peso
    )


def _perfil_de_grupo(
    sub: pd.DataFrame, pesos_anios: tuple[float, ...]
) -> tuple[list[float], list[int]]:
    """Índices 0-11 de un grupo, más los meses que hubo que estimar.

    El orden importa y es el que evita romper la tabla: primero se calcula el
    índice de cada mes CON datos (valor ponderado / promedio de los medidos),
    después se rellenan con 1.0 los meses sin datos, y recién ahí se normaliza.
    Rellenar después de normalizar dejaría la tabla sin sumar 12.

    Efecto secundario útil de dividir por el promedio de los medidos: los meses
    medidos suman exactamente su propia cantidad, así que al completar con 1.0
    el total ya da 12 y la normalización posterior no mueve los rellenos.
    """
    por_mes = sub.groupby(["mes", "anio"])["units_ordered"].sum()

    medidos: dict[int, float] = {}
    for mes in range(1, MESES + 1):
        if mes not in por_mes.index.get_level_values("mes"):
            continue
        medidos[mes] = _promedio_ponderado(por_mes.xs(mes, level="mes"), pesos_anios)

    estimados = [mes for mes in range(1, MESES + 1) if mes not in medidos]

    promedio = sum(medidos.values()) / len(medidos) if medidos else 0.0
    if promedio <= 0:
        # Grupo sin volumen: no hay estacionalidad que medir, todo neutro.
        return [INDICE_NEUTRO] * MESES, estimados

    perfil = [
        medidos[mes] / promedio if mes in medidos else INDICE_NEUTRO
        for mes in range(1, MESES + 1)
    ]
    return perfil, estimados


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de las tablas
# ─────────────────────────────────────────────────────────────────────────────


def calcular_indices(
    historia: pd.DataFrame,
    agrupar_por: str = "category",
    minimo_meses: int = MESES,
    pesos_anios: tuple[float, ...] = (0.6, 0.4),
) -> dict:
    """Calcula una tabla de índices estacionales por grupo, desde la historia.

    Un grupo con menos de `minimo_meses` distintos NO recibe índice: se va a
    `descartados` con su razón. Doce valores derivados de cuatro meses no son un
    perfil estacional, son ruido con forma de perfil — y una vez en la tabla
    nadie los distingue de los buenos.

    Args:
        historia: shape semanal de M28 (ver `agregar_a_mensual`).
        agrupar_por: columna que define el grupo ('category' o 'sku').
        minimo_meses: meses distintos necesarios para calificar.
        pesos_anios: ponderación por recencia, del año más nuevo al más viejo.

    Returns:
        dict con cuatro claves:
            "tablas": {grupo: [12 índices]} ya normalizados y clampeados.
            "descartados": {grupo: razón} de los que no calificaron.
            "meses_estimados": {grupo: [meses en 1.0]} — solo los grupos que
                tuvieron alguno. Un mes acá es relleno, no medición.
            "meta": corregido_por_quiebres (siempre False), grupos_con_indice,
                meses_cubiertos (pares año-mes distintos en la historia) y
                agrupado_por.
    """
    mensual = agregar_a_mensual(historia)

    tablas: dict[str, list[float]] = {}
    descartados: dict[str, str] = {}
    meses_estimados: dict[str, list[int]] = {}
    meses_cubiertos = 0

    if not mensual.empty:
        meses_cubiertos = len(mensual[["anio", "mes"]].drop_duplicates())

        for grupo, sub in mensual.groupby(agrupar_por):
            distintos = sub["mes"].nunique()
            if distintos < minimo_meses:
                descartados[grupo] = (
                    f"solo {distintos} meses con datos, se requieren {minimo_meses}"
                )
                continue

            perfil, estimados = _perfil_de_grupo(sub, pesos_anios)
            tablas[grupo] = perfil
            if estimados:
                meses_estimados[grupo] = estimados

        tablas = normalizar_tabla(tablas)

    return {
        "tablas": tablas,
        "descartados": descartados,
        "meses_estimados": meses_estimados,
        "meta": {
            "corregido_por_quiebres": False,
            "grupos_con_indice": len(tablas),
            "meses_cubiertos": meses_cubiertos,
            "agrupado_por": agrupar_por,
        },
    }


def indices_por_sku(
    historia: pd.DataFrame,
    minimo_meses: int = MESES,
    pesos_anios: tuple[float, ...] = (0.6, 0.4),
) -> dict:
    """Igual que `calcular_indices` pero con el SKU como grupo.

    Existe porque dos SKUs de la misma categoría pueden tener temporadas
    distintas, y agruparlos los promedia hasta borrar la diferencia. El costo es
    que muchos SKUs no van a tener 12 meses propios y van a caer a `descartados`
    — para eso está la cascada de `resolver_indice`.
    """
    return calcular_indices(
        historia,
        agrupar_por="sku",
        minimo_meses=minimo_meses,
        pesos_anios=pesos_anios,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Resolución en cascada
# ─────────────────────────────────────────────────────────────────────────────


def _tabla_de(resultado, grupo: str) -> list[float] | None:
    """Fila de 12 valores de un grupo dentro de un retorno de `calcular_indices`.

    None si el resultado no tiene esa forma, si el grupo no está, o si su fila
    no mide 12 — en cualquiera de los tres casos la cascada sigue de largo.
    """
    if not isinstance(resultado, dict):
        return None
    fila = (resultado.get("tablas") or {}).get(grupo)
    if fila is None or len(fila) != MESES:
        return None
    return fila


def resolver_indice(
    tablas: dict,
    sku: str,
    categoria: str,
    mes: int,
) -> tuple[float, str]:
    """Índice aplicable a un SKU en un mes, con el origen del que salió.

    Cascada: índice propio del SKU -> índice de su categoría -> 1.0 neutro. Lo
    específico gana sobre lo general, y el neutro es el piso: sin datos el mes
    no corrige, no se anula.

    El `origen` es parte del contrato, no un extra de diagnóstico: quien recibe
    un 1.0 necesita saber si significa 'este mes vende como el promedio' o 'no
    tengo con qué estimarlo'.

    Args:
        tablas: {'sku': <retorno de indices_por_sku>,
                 'category': <retorno de calcular_indices>}.
        sku: SKU a resolver.
        categoria: su categoría, para el segundo escalón.
        mes: 1-12 (enero = 1).

    Returns:
        (indice, origen) con origen en {'sku', 'category', 'neutro'}.

    Raises:
        ValueError: si `mes` está fuera de 1-12.
    """
    if not 1 <= mes <= MESES:
        raise ValueError(f"resolver_indice: mes debe estar entre 1 y {MESES}, llegó {mes}")

    propia = _tabla_de(tablas.get(ORIGEN_SKU), sku)
    if propia is not None:
        return float(propia[mes - 1]), ORIGEN_SKU

    de_categoria = _tabla_de(tablas.get(ORIGEN_CATEGORIA), categoria)
    if de_categoria is not None:
        return float(de_categoria[mes - 1]), ORIGEN_CATEGORIA

    return INDICE_NEUTRO, ORIGEN_NEUTRO
