"""Política de stock (R, s, S) del módulo Supply Chain (M37 punto 2).

Responde las dos preguntas de compras: cuándo pedir (punto de pedido) y hasta
dónde (objetivo). El nivel de servicio se fija por clase ABC y es explícito:
"de cada 100 reposiciones, en cuántas acepto no quebrar". La variabilidad del
lead time entra al stock de seguridad desde su rango mín/típico/máx.

Port del motor del Laboratorio de Compras de Fede. Fuente de verdad, línea por
línea: `notes/supply-chain/originales/laboratorio-compras-2026-08-17.html`
L302-365 (`zInv`, `poissonQ`, `computeABC`, `calcPolicy`). Cada fórmula cita la
línea de la que sale. Se portea verbatim, con sus redondeos y sus bordes: una
"mejora" acá cambia qué se compra y deja de ser comparable con el Lab.

Regla dura, igual que `core/supply_seasonality.py` y `core/supply_indices.py`:
- CERO acceso a disco, CERO Streamlit, CERO import de la capa de persistencia.
  La demanda, el lead time y la posición entran por parámetro; este archivo no
  sabe de dónde salieron.
- Solo stdlib. La inversa de la Normal y el cuantil de Poisson se calculan acá,
  con los mismos algoritmos del HTML, para no sumar una dependencia al build.

Ausencia de dato NO es cero: `diagnosticar_posicion` con `posicion_actual=None`
devuelve None. La plataforma todavía no ingesta inventario on-hand de forma
completa, y una señal calculada contra cero diría COMPRAR a todo el catálogo.

API pública:
    clasificar_abc(revenues, corte_a, corte_b)              -> dict[str, str]
    calcular_politica(demanda_semanal, desvio_semanal, lead_time,
                      periodo_revision, nivel_servicio, indice_estacional)
                                                            -> dict
    diagnosticar_posicion(politica, posicion_actual, periodo_revision)
                                                            -> dict | None
"""

from __future__ import annotations

import math

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

REGIMEN_FLUIDO = "fluido"
REGIMEN_ESPACIADO = "espaciado"
REGIMEN_SIN_DEMANDA = "sin demanda"
"""Los tres regímenes de demanda (HTML L348-350). Deciden qué fórmula de stock
de seguridad aplica: Normal para venta continua, Poisson para venta salteada."""

SENAL_COMPRAR = "COMPRAR"
SENAL_EXCESO = "EXCESO"
SENAL_OK = "OK"
SENAL_SIN_DEMANDA = "SIN DEMANDA"
SENAL_VACIA = "—"
"""Señales de diagnóstico, literales del HTML L358-361. `SENAL_VACIA` es un em
dash: SKU sin demanda y sin stock, no hay nada que decir."""

_UMBRAL_FLUIDO = 2.0
_UMBRAL_ESPACIADO = 0.05
"""Unidades por semana (dw). dw >= 2 es fluido; dw > 0.05 es espaciado; el resto
sin demanda. Las comparaciones son >= y > respectivamente (HTML L348-349), así
que dw == 0.05 exacto cae en sin demanda."""

_DFWD_MINIMO = 0.001
"""Demanda diaria por debajo de la cual una cobertura en días no significa nada
y se reporta como infinita (HTML L356, L363)."""

_Z_CLAMP = 8.0
_Z_P_LOW = 0.02425
_Z_A = (
    -3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
    1.38357751867269e2, -3.066479806614716e1, 2.506628277459239,
)
_Z_B = (
    -5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
    6.680131188771972e1, -1.328068155288572e1,
)
_Z_C = (
    -7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838,
    -2.549732539343734, 4.374664141464968, 2.938163982698783,
)
_Z_D = (
    7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996,
    3.754408661907416,
)
"""Coeficientes de Acklam para la inversa de la Normal estándar, copiados
exactos del HTML L303-306. No redondear: la paridad con el Lab depende de ellos."""

_POISSON_MAX_K = 3000
"""Tope de iteraciones del cuantil de Poisson (HTML L310)."""


# ─────────────────────────────────────────────────────────────────────────────
# Estadística — sin dependencias fuera de stdlib
# ─────────────────────────────────────────────────────────────────────────────


def _z_inv(p: float) -> float:
    """Inversa de la Normal estándar: el z tal que P(Z <= z) = p.

    Algoritmo de Acklam, port verbatim de `zInv` (HTML L302-309). Tres ramas:
    cola baja, zona central y cola alta. Fuera de (0, 1) clampea a ±8, igual que
    el HTML, en vez de lanzar.

    Args:
        p: Probabilidad acumulada. En uso normal, el nivel de servicio (0-1).

    Returns:
        El cuantil z. -8.0 si p <= 0, 8.0 si p >= 1.
    """
    # HTML L302
    if p <= 0:
        return -_Z_CLAMP
    if p >= 1:
        return _Z_CLAMP

    a, b, c, d = _Z_A, _Z_B, _Z_C, _Z_D

    # HTML L307 — cola baja
    if p < _Z_P_LOW:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )

    # HTML L308 — cola alta
    if p > 1 - _Z_P_LOW:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )

    # HTML L309 — zona central
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
    )


def _poisson_inv(ns: float, lam: float) -> int:
    """Cuantil de Poisson: el menor k tal que P(X <= k) >= ns, con X ~ Poisson(lam).

    Port verbatim de `poissonQ` (HTML L310): acumula la función de masa desde
    k=0 hasta alcanzar `ns`, con tope de 3000 iteraciones.

    Args:
        ns: Nivel de servicio (0-1).
        lam: Media de la Poisson (unidades esperadas en la ventana).

    Returns:
        k entero >= 0. 0 si lam <= 0.
    """
    # HTML L310
    if lam <= 0:
        return 0
    k = 0
    p = math.exp(-lam)
    cum = p
    while cum < ns and k < _POISSON_MAX_K:
        k += 1
        p *= lam / k
        cum += p
    return k


# ─────────────────────────────────────────────────────────────────────────────
# Clasificación ABC
# ─────────────────────────────────────────────────────────────────────────────


def clasificar_abc(
    revenues: dict[str, float],
    corte_a: float = 0.80,
    corte_b: float = 0.95,
) -> dict[str, str]:
    """Clase ABC por Pareto sobre el revenue acumulado.

    Port de `computeABC` (HTML L324-328). Ordena los SKUs por revenue
    descendente y acumula. El acumulado es INCLUSIVO: el revenue del SKU se suma
    ANTES de comparar contra el corte.

    Consecuencia intencional de esa regla, NO un bug: el último SKU del ranking
    llega con acumulado == total, y total > total*corte_b, así que siempre es
    'C'. Con un solo SKU con revenue, ese SKU es primero y último a la vez y
    sale 'C'. Se mantiene por paridad con el Lab.

    Empates de revenue: el orden es estable (se respeta el orden de entrada del
    dict), igual que el `sort` del HTML.

    Args:
        revenues: {sku: revenue} del período que se quiera clasificar.
        corte_a: Fracción del revenue acumulado que cierra la clase A.
        corte_b: Fracción del revenue acumulado que cierra la clase B.

    Returns:
        {sku: 'A' | 'B' | 'C'}, una entrada por SKU de entrada.
    """
    # HTML L326 — ranking por revenue descendente
    ranking = sorted(revenues.items(), key=lambda item: item[1], reverse=True)

    # HTML L327 — `||1`: sin revenue total se divide por 1, no por cero
    total = sum(revenue for _, revenue in ranking) or 1

    # HTML L328 — acumulado inclusivo: se suma y después se compara
    clases: dict[str, str] = {}
    acumulado = 0.0
    for sku, revenue in ranking:
        acumulado += revenue
        if acumulado <= total * corte_a:
            clases[sku] = "A"
        elif acumulado <= total * corte_b:
            clases[sku] = "B"
        else:
            clases[sku] = "C"
    return clases


# ─────────────────────────────────────────────────────────────────────────────
# Política por SKU
# ─────────────────────────────────────────────────────────────────────────────


def calcular_politica(
    demanda_semanal: float,
    desvio_semanal: float,
    lead_time: tuple[float, float, float],
    periodo_revision: float = 7,
    nivel_servicio: float = 0.94,
    indice_estacional: float = 1.0,
) -> dict:
    """Stock de seguridad, punto de pedido y objetivo de un SKU.

    Port de `calcPolicy` (HTML L338-352), sin la parte de posición y señal, que
    vive en `diagnosticar_posicion` porque depende de un dato de inventario que
    puede no existir.

    El índice estacional entra ya resuelto: es el del mes centro de la ventana
    futura (HTML L343), y elegir ese mes es trabajo del caller.

    Args:
        demanda_semanal: dw, unidades/semana desestacionalizadas y corregidas
            por quiebres.
        desvio_semanal: sw, desvío de la demanda semanal.
        lead_time: (mínimo, típico, máximo) en días.
        periodo_revision: R, días entre revisiones.
        nivel_servicio: NS, fracción 0-1.
        indice_estacional: Índice del mes centro de la ventana LT+R.

    Returns:
        dict con:
            "regimen": 'fluido' | 'espaciado' | 'sin demanda'.
            "ss": stock de seguridad (int, redondeado hacia arriba).
            "rop": punto de pedido (int).
            "objetivo_s": objetivo S (int).
            "dias_cobertura_objetivo": S / dfwd, o inf si dfwd <= 0.001.
            "dfwd": demanda diaria esperada en la ventana, reestacionalizada.
            "periodo_proteccion": P = lead time típico + R.
            "sigma_lt": desvío del lead time.
            "meta": parámetros de entrada y valores intermedios.
    """
    lt_min, lt_tip, lt_max = lead_time
    dw = demanda_semanal

    # HTML L340 — variabilidad del lead time desde el rango (rango ≈ 4 sigmas)
    sigma_lt = (lt_max - lt_min) / 4

    # HTML L341 — pasaje a diario. El desvío semanal se divide por sqrt(7),
    # no se usa a secas: es el desvío de la demanda de UN día.
    d_des = dw / 7
    sigma_d = desvio_semanal / math.sqrt(7)

    # HTML L345 — demanda diaria esperada en la ventana, reestacionalizada
    dfwd = d_des * indice_estacional

    # HTML L346 — período de protección
    periodo_proteccion = lt_tip + periodo_revision

    # HTML L348-350 — régimen y stock de seguridad. El orden importa.
    if dw >= _UMBRAL_FLUIDO:
        regimen = REGIMEN_FLUIDO
        # HTML L348 — Normal: demanda y lead time variables
        sigma_p = math.sqrt(
            periodo_proteccion * sigma_d * sigma_d + dfwd * dfwd * sigma_lt * sigma_lt
        )
        ss_crudo = _z_inv(nivel_servicio) * sigma_p
    elif dw > _UMBRAL_ESPACIADO:
        regimen = REGIMEN_ESPACIADO
        # HTML L349 — Poisson para venta intermitente
        lam = dfwd * (periodo_proteccion + sigma_lt)
        ss_crudo = max(0, _poisson_inv(nivel_servicio, lam) - lam)
    else:
        regimen = REGIMEN_SIN_DEMANDA
        # HTML L350
        ss_crudo = 0

    # HTML L351 — el stock de seguridad se redondea hacia arriba
    ss = math.ceil(ss_crudo)

    # HTML L352 — punto de pedido y objetivo, también hacia arriba
    rop = math.ceil(ss + dfwd * lt_tip)
    objetivo_s = math.ceil(ss + dfwd * periodo_proteccion)

    dias_cobertura_objetivo = (
        objetivo_s / dfwd if dfwd > _DFWD_MINIMO else float("inf")
    )

    return {
        "regimen": regimen,
        "ss": ss,
        "rop": rop,
        "objetivo_s": objetivo_s,
        "dias_cobertura_objetivo": dias_cobertura_objetivo,
        "dfwd": dfwd,
        "periodo_proteccion": periodo_proteccion,
        "sigma_lt": sigma_lt,
        "meta": {
            "demanda_semanal": demanda_semanal,
            "desvio_semanal": desvio_semanal,
            "lead_time": (lt_min, lt_tip, lt_max),
            "periodo_revision": periodo_revision,
            "nivel_servicio": nivel_servicio,
            "indice_estacional": indice_estacional,
            "demanda_diaria_desestacionalizada": d_des,
            "sigma_d": sigma_d,
            "ss_crudo": ss_crudo,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Diagnóstico contra la posición actual
# ─────────────────────────────────────────────────────────────────────────────


def diagnosticar_posicion(
    politica: dict,
    posicion_actual: float | None,
    periodo_revision: float | None = None,
) -> dict | None:
    """Señal de compra de un SKU según su posición de inventario.

    Port de HTML L356-361. La posición es todo lo disponible o en camino; cómo
    se arma (FBA, depósitos, órdenes abiertas) es trabajo del caller.

    Args:
        politica: Retorno de `calcular_politica`.
        posicion_actual: Unidades en posición, o None si no hay dato de
            inventario.
        periodo_revision: R, días entre revisiones. Entra al umbral de EXCESO.
            Default None: se usa el R con el que se calculó la política
            (`politica["meta"]["periodo_revision"]`), para que el umbral sea
            coherente con el S que produjo ese mismo R. Pasar un valor explícito
            es un override consciente.

    Returns:
        None si `posicion_actual` es None. Si no, dict con:
            "senal": 'COMPRAR' | 'EXCESO' | 'OK' | 'SIN DEMANDA' | '—'.
            "need": unidades a pedir (>= 1 si COMPRAR, 0 en el resto).
            "cobertura_dias": posición / dfwd, o inf si dfwd <= 0.001.
    """
    if posicion_actual is None:
        # Sin dato de inventario no hay diagnóstico. Una señal contra cero
        # diría COMPRAR a todo el catálogo.
        return None

    pos = posicion_actual
    dfwd = politica["dfwd"]
    rop = politica["rop"]
    objetivo_s = politica["objetivo_s"]
    # En el HTML el umbral usa G.rev, el mismo R que armó S (L346, L360).
    if periodo_revision is None:
        periodo_revision = politica["meta"]["periodo_revision"]

    # HTML L356 — cobertura en días de la posición
    cobertura_dias = pos / dfwd if dfwd > _DFWD_MINIMO else float("inf")

    need = 0
    # HTML L358 — 'sin demanda' se evalúa ANTES que el resto
    if politica["regimen"] == REGIMEN_SIN_DEMANDA:
        senal = SENAL_SIN_DEMANDA if pos > 0 else SENAL_VACIA
    # HTML L359 — la condición es <=
    elif pos <= rop:
        senal = SENAL_COMPRAR
        need = max(1, objetivo_s - pos)
    # HTML L360 — umbral de exceso
    elif pos > objetivo_s + max(2 * dfwd * periodo_revision, 0.15 * objetivo_s):
        senal = SENAL_EXCESO
    # HTML L361
    else:
        senal = SENAL_OK

    return {
        "senal": senal,
        "need": need,
        "cobertura_dias": cobertura_dias,
    }
