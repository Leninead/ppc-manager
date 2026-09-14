"""Índices estacionales del módulo Supply Chain (M37 B2.1).

Capa de estacionalidad: convierte venta observada en demanda comparable entre
meses, y de vuelta. Dos operaciones que se usan en cadena — desestacionalizar
para medir el nivel de base de un SKU sin que el mes lo contamine, y
reestacionalizar para proyectar ese nivel sobre el mes que viene.

Incluye la corrección por quiebres de stock: un SKU que estuvo sin inventario
no vendió porque no podía, no porque no hubiera demanda. Sin esa corrección el
modelo lee el quiebre como caída de demanda, compra de menos, y el quiebre se
repite. Es el error más caro de la cadena.

Regla dura, igual que `core/supply_metrics.py` pero por otro motivo:
- CERO acceso a disco, CERO Streamlit, CERO import de `supply_persistence`.
  Este archivo no lee tablas, no las guarda y no sabe de dónde salieron: las
  recibe por parámetro. Es lógica pura y testeable sin fixtures de I/O.
- La tabla de índices es un input, no una constante del módulo. Cada cliente
  (y cada pool) tiene la suya; hardcodear la de uno es romper a los demás.

Ausencia de dato NO es cero. Un `None` que entra sale como `None`, y un caso
sin evidencia suficiente devuelve `None` en vez de un número inventado. El
cero está reservado para el hecho real "tuvo stock y no vendió".

API pública:
    MESES                                           -> int
    demanda_corregida(unidades, dias_periodo, dias_sin_stock, piso, minimo_dias)
                                                    -> float | None
    indice_mes(tabla, subcat, mes)                  -> float
    desestacionalizar(demanda, indice)              -> float | None
    reestacionalizar(demanda_base, indice)          -> float
    normalizar_tabla(tabla, clamp)                  -> dict[str, list[float]]
    validar_tabla(tabla)                            -> dict
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

MESES = 12
"""Largo canónico de una fila de índices. Una lista que no mide exactamente 12
no es una tabla estacional: se trata como dato roto, no se intenta arreglar."""

INDICE_NEUTRO = 1.0
"""Índice que no corrige nada. Es el fallback para toda subcategoría sin fila
propia — misma decisión que el JS del Laboratorio de Fede
(`IDX[s.sub] || new Array(12).fill(1)`). Neutro y no cero: sin índice el mes
no se ajusta, no se anula."""

CLAMP_DEFAULT = (0.25, 3.0)
"""Techo y piso de un índice, en el orden (mínimo, máximo). Acota el daño de
una subcategoría con pocos meses observados: sin clamp, un mes con una venta
excepcional multiplica el forecast por 8 y dispara una compra que nadie pidió.
Son los mismos límites que se ven en las tablas de Gamboa."""

TOLERANCIA_NORMALIZACION = 0.01
"""Cuánto puede apartarse de 12 la suma de una fila antes de considerarla sin
normalizar. No es cero porque redondear 12 floats a 3 decimales nunca suma
exactamente 12; es chico porque una fila realmente sin normalizar se aparta
por unidades enteras, no por centésimas."""

_PISO_DEFAULT = 3
_MINIMO_DIAS_DEFAULT = 4


# ─────────────────────────────────────────────────────────────────────────────
# Corrección por quiebres de stock
# ─────────────────────────────────────────────────────────────────────────────


def demanda_corregida(
    unidades: int,
    dias_periodo: int = 7,
    dias_sin_stock: int | None = None,
    piso: int = _PISO_DEFAULT,
    minimo_dias: int = _MINIMO_DIAS_DEFAULT,
) -> float | None:
    """Venta diaria del período, corregida por los días que el SKU no tuvo stock.

    Vendió 20 unidades en una semana, pero 2 días estuvo quebrado: su demanda
    no es 20/7 = 2.9 por día, es 20/5 = 4.0. Esa diferencia es la que decide si
    el próximo pedido alcanza o vuelve a quebrar.

    `dias_sin_stock=None` significa "no hay observación de inventario para este
    período", NO "no hubo quiebres". Son ramas distintas a propósito: con None
    se devuelve la venta cruda sin evaluar nada, con un 0 explícito se aplica
    el mismo criterio de evidencia que a cualquier otro valor.

    Sobre `piso` y `minimo_dias`: con los defaults semanales el piso NUNCA
    llega a actuar, y eso es correcto, no dead code. Todo caso que sobrevive a
    `minimo_dias=4` tiene `dias_con_stock >= 4`, que ya es mayor que
    `piso=3`, así que `max()` devuelve siempre los días reales. El piso existe
    para la ventana MENSUAL que consume B2.3, donde se llama con
    `piso=10, minimo_dias=1` y reproduce el `u30 / max(10, 30 - dias_sin_stock)`
    del SCS: ahí sí muerde, y es lo que evita que un SKU quebrado 27 de 30 días
    divida por 3 y proyecte una demanda absurda. NO borrar por parecer inútil.

    Args:
        unidades: Unidades vendidas en el período.
        dias_periodo: Largo del período en días (7 = semanal, 30 = mensual).
        dias_sin_stock: Días sin inventario, o None si no hay observación.
        piso: Divisor mínimo. Acota el ratio cuando quedan muy pocos días.
        minimo_dias: Días con stock necesarios para que el dato valga.

    Returns:
        Unidades por día (float), o None si no hay evidencia suficiente. El 0.0
        es un valor legítimo: tuvo stock y no vendió.

    Raises:
        ValueError: si `dias_periodo` no es positivo, o si `dias_sin_stock` es
            negativo o mayor que el período.
    """
    if dias_periodo <= 0:
        raise ValueError(
            f"demanda_corregida: dias_periodo debe ser positivo, llegó {dias_periodo}"
        )

    if dias_sin_stock is None:
        # Sin observación de inventario no hay nada que corregir ni que validar:
        # se devuelve la venta cruda y el caller sabe que no está corregida.
        return unidades / dias_periodo

    if dias_sin_stock < 0:
        raise ValueError(
            f"demanda_corregida: dias_sin_stock no puede ser negativo, llegó {dias_sin_stock}"
        )
    if dias_sin_stock > dias_periodo:
        raise ValueError(
            f"demanda_corregida: dias_sin_stock ({dias_sin_stock}) no puede superar "
            f"dias_periodo ({dias_periodo})"
        )

    dias_con_stock = dias_periodo - dias_sin_stock
    if dias_con_stock < minimo_dias:
        # Evidencia insuficiente. Devolver un número acá es el bug del
        # `sw = 0.8 × dw` del Lab: un SKU con una sola observación recibía una
        # cifra fabricada que después nadie distinguía de una medida.
        return None

    return unidades / max(piso, dias_con_stock)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de la tabla de índices
# ─────────────────────────────────────────────────────────────────────────────


def indice_mes(tabla: dict[str, list[float]], subcat: str, mes: int) -> float:
    """Índice estacional de una subcategoría para un mes.

    El mes es 1-12 (enero = 1) y la fila es una lista 0-indexada (enero =
    posición 0). La conversión vive acá y en ningún otro lado: es el off-by-one
    más fácil de cometer de todo el módulo.

    Una subcategoría sin fila propia devuelve `INDICE_NEUTRO` en vez de lanzar.
    Un catálogo real siempre tiene subcategorías nuevas o mal tipeadas, y que
    el forecast entero explote por eso es peor que proyectar ese SKU sin
    estacionalidad. Lo mismo para una fila con largo inválido: dato roto ->
    neutro, y `validar_tabla` es el que lo reporta.

    Returns:
        El índice del mes, o 1.0 si la subcategoría no está o su fila es
        inválida.

    Raises:
        ValueError: si `mes` está fuera de 1-12. Acá sí se lanza: un mes
            inválido es un error de programación del caller, no un dato sucio.
    """
    if not 1 <= mes <= MESES:
        raise ValueError(f"indice_mes: mes debe estar entre 1 y {MESES}, llegó {mes}")

    valores = tabla.get(subcat)
    if valores is None or len(valores) != MESES:
        return INDICE_NEUTRO

    return float(valores[mes - 1])


# ─────────────────────────────────────────────────────────────────────────────
# Ida y vuelta estacional
# ─────────────────────────────────────────────────────────────────────────────


def desestacionalizar(demanda: float | None, indice: float) -> float | None:
    """Saca el efecto del mes: demanda observada -> nivel de base del SKU.

    Es la operación que permite comparar julio contra diciembre. Sin esto, un
    pico de temporada se lee como crecimiento y un valle como caída.

    Returns:
        La demanda a nivel de base, o None si no hay con qué calcularla: o la
        demanda ya venía sin evidencia (None se propaga), o el índice no es
        positivo, y ni dividir por cero ni devolver una demanda negativa son
        respuestas útiles.
    """
    if demanda is None:
        return None
    if indice <= 0:
        return None
    return demanda / indice


def reestacionalizar(demanda_base: float, indice: float) -> float:
    """Vuelve a aplicar el efecto del mes: nivel de base -> demanda esperada.

    Inversa exacta de `desestacionalizar` con el mismo índice: proyectar el
    nivel de base sobre el mes objetivo es lo que hace que un pedido llegue
    dimensionado para la temporada en que se va a vender, no para la temporada
    en que se midió.
    """
    return demanda_base * indice


# ─────────────────────────────────────────────────────────────────────────────
# Normalización y diagnóstico de una tabla
# ─────────────────────────────────────────────────────────────────────────────


def normalizar_tabla(
    tabla: dict[str, list[float]],
    clamp: tuple[float, float] = CLAMP_DEFAULT,
) -> dict[str, list[float]]:
    """Lleva cada fila a media 1.0 (suma 12) y después la acota al clamp.

    El ORDEN importa y es la razón por la que las tablas de Fede tienen filas
    que ya no suman 12: se normaliza primero y se clampea después, así que un
    mes que post-escalado supera el techo queda recortado y rompe la suma. Si
    se clampeara antes, toda fila terminaría sumando 12 y filas como
    `Tela - bandera USA` (suma 8.5) no podrían existir. Ver
    `notes/supply-chain/hallazgos-tablas-indices.md`.

    Corolario: NO es idempotente sobre una fila ya clampeada. Renormalizarla
    vuelve a empujar el pico contra el techo y tampoco llega a 12. Una fila
    clampeada no se recupera escalándola; hace falta el dato crudo.

    Filas que no miden 12 se copian sin tocar: `validar_tabla` es quien las
    reporta, este no es el lugar para decidir qué hacer con dato roto. Filas
    que suman 0 (o menos) quedan en doce 1.0: sin señal no se inventa
    estacionalidad.

    No muta la entrada — la tabla original suele ser dato de otro módulo.

    Returns:
        Una tabla nueva, con las mismas claves.
    """
    minimo, maximo = clamp
    resultado: dict[str, list[float]] = {}

    for subcat, valores in tabla.items():
        if len(valores) != MESES:
            resultado[subcat] = list(valores)
            continue

        total = sum(valores)
        if total <= 0:
            resultado[subcat] = [INDICE_NEUTRO] * MESES
            continue

        factor = MESES / total
        resultado[subcat] = [
            min(maximo, max(minimo, v * factor)) for v in valores
        ]

    return resultado


def _fila_invalida(valores: list[float]) -> bool:
    """True si la fila no tiene el largo canónico. Único criterio de 'rota'."""
    return len(valores) != MESES


def validar_tabla(tabla: dict[str, list[float]]) -> dict:
    """Diagnostica una tabla de índices sin modificarla.

    Pensado para mostrarle al AM qué le pasa a la tabla que cargó, y para
    decidir si una tabla importada de afuera se puede usar tal cual. Cada
    problema va en su propia lista: son independientes y una fila puede caer en
    varias.

    Una fila con largo inválido se reporta SOLO en `largo_invalido` y no se
    evalúa por suma ni por clamp — sus valores no son índices mensuales, así
    que medirlos contra 12 no significaría nada.

    `con_meses_neutros` marca el 1.0 exacto porque es la huella de un mes
    rellenado por un filtro de disponibilidad, no de un mes que casualmente
    dio 1.0. En las tablas del Forecast v3 hay 57 de esos.

    Returns:
        dict con cinco claves:
            "ok": bool — True si ninguna lista tiene contenido.
            "sin_normalizar": subcats cuya suma se aparta de 12 en más de
                `TOLERANCIA_NORMALIZACION`.
            "con_meses_neutros": subcats con algún valor exactamente 1.0.
            "fuera_de_clamp": subcats con algún valor fuera de `CLAMP_DEFAULT`.
                El chequeo es estricto: 0.25 y 3.0 están EN el borde, no fuera.
            "largo_invalido": subcats cuya fila no mide 12.
    """
    minimo, maximo = CLAMP_DEFAULT

    sin_normalizar: list[str] = []
    con_meses_neutros: list[str] = []
    fuera_de_clamp: list[str] = []
    largo_invalido: list[str] = []

    for subcat, valores in tabla.items():
        if _fila_invalida(valores):
            largo_invalido.append(subcat)
            continue

        if abs(sum(valores) - MESES) > TOLERANCIA_NORMALIZACION:
            sin_normalizar.append(subcat)
        if any(v == INDICE_NEUTRO for v in valores):
            con_meses_neutros.append(subcat)
        if any(v < minimo or v > maximo for v in valores):
            fuera_de_clamp.append(subcat)

    return {
        "ok": not (
            sin_normalizar or con_meses_neutros or fuera_de_clamp or largo_invalido
        ),
        "sin_normalizar": sin_normalizar,
        "con_meses_neutros": con_meses_neutros,
        "fuera_de_clamp": fuera_de_clamp,
        "largo_invalido": largo_invalido,
    }
