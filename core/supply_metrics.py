"""Lógica de negocio del módulo Supply Chain (M37).

Contrapartida exacta de `core/supply_persistence.py`: allá va el CRUD y la
validación de forma, acá va todo lo que decide *qué es legal* y *qué significan*
los datos — máquina de estados, secuencia de códigos de OC, lead time medido y
fill rate.

Regla dura, inversa a la del persistence:
- CERO acceso a disco. Este archivo no importa json, ni parquet, ni pathlib, ni
  abre archivos. Todo dato entra y sale por la API pública de supply_persistence.
- Si hace falta un dato nuevo, se pide por esa API; nunca se lee el archivo.

API pública:
    TRANSICIONES                                    -> dict[str, tuple[str, ...]]
    transicion_valida(estado_actual, estado_nuevo)  -> bool
    generar_codigo_oc(proveedor_id)                 -> str
    cambiar_estado_oc(oc_id, estado_nuevo, quien, fecha) -> dict
    lead_time_medido(proveedor_id)                  -> float | None
    fill_rate(proveedor_id)                         -> float | None
    resumen_proveedor(proveedor_id)                 -> dict
"""

from __future__ import annotations

import re
from datetime import datetime
from statistics import median

from core.supply_persistence import (
    ESTADOS_OC,
    get_oc,
    leer_eventos,
    list_ocs,
    registrar_evento,
    save_oc,
)

# ─────────────────────────────────────────────────────────────────────────────
# Máquina de estados
# ─────────────────────────────────────────────────────────────────────────────

TRANSICIONES: dict[str, tuple[str, ...]] = {
    "PROPUESTA": ("APROBADA", "ANULADA"),
    "APROBADA": ("OK_FIN", "ANULADA"),
    "OK_FIN": ("EMITIDA", "ANULADA"),
    "EMITIDA": ("RECIBIDA_PARCIAL", "CERRADA", "ANULADA"),
    # RECIBIDA_PARCIAL -> RECIBIDA_PARCIAL a propósito: se puede recibir en varias tandas.
    "RECIBIDA_PARCIAL": ("RECIBIDA_PARCIAL", "CERRADA", "ANULADA"),
    "CERRADA": (),  # terminal
    "ANULADA": (),  # terminal
}
"""Transiciones legales de una OC. La fuente de verdad de qué estados EXISTEN es
`ESTADOS_OC` (en supply_persistence); acá solo se decide cuál puede seguir a cuál."""


def _verificar_cobertura_estados() -> None:
    """Guard de import: TRANSICIONES y ESTADOS_OC no pueden divergir.

    Falla fuerte y temprano si alguien agrega un estado en persistence y se
    olvida de declarar sus transiciones acá (o al revés). Es un error de
    programación, no de datos: mejor romper al importar que en producción.
    """
    validos = set(ESTADOS_OC)
    declarados = set(TRANSICIONES)
    destinos = {d for ds in TRANSICIONES.values() for d in ds}

    desconocidos = (declarados | destinos) - validos
    if desconocidos:
        raise ValueError(
            f"TRANSICIONES usa estados que no están en ESTADOS_OC: {sorted(desconocidos)}"
        )
    sin_declarar = validos - declarados
    if sin_declarar:
        raise ValueError(
            f"ESTADOS_OC tiene estados sin transiciones declaradas: {sorted(sin_declarar)}"
        )


_verificar_cobertura_estados()


def transicion_valida(estado_actual: str, estado_nuevo: str) -> bool:
    """True si la OC puede pasar de `estado_actual` a `estado_nuevo`.

    Un estado desconocido (o terminal) no habilita ninguna transición: False.
    """
    return estado_nuevo in TRANSICIONES.get(estado_actual, ())


# ─────────────────────────────────────────────────────────────────────────────
# Secuencia de códigos de OC
# ─────────────────────────────────────────────────────────────────────────────

_PREFIJO_LEN = 3
"""Largo fijo del token de proveedor dentro del código. Fijo a propósito: es lo
que permite parsear el <NN> por posición sin ambigüedad."""


def _token_proveedor(proveedor_id: str) -> str:
    """Primeras 3 letras alfanuméricas del id, en mayúsculas.

    'shenzhen' -> 'SHE' · 'gina-miriam' -> 'GIN' (el guión no cuenta).
    Si hay menos de 3 alfanuméricos, se rellena con 'X' para mantener el largo
    fijo: 'ab' -> 'ABX', '' -> 'XXX'.
    """
    limpio = re.sub(r"[^A-Za-z0-9]", "", str(proveedor_id or ""))
    return limpio[:_PREFIJO_LEN].upper().ljust(_PREFIJO_LEN, "X")


def generar_codigo_oc(proveedor_id: str) -> str:
    """Devuelve el próximo código libre para ese proveedor en el mes actual.

    Formato: `OC-<PROV>-<AAMM>-<NN>` (ej. `OC-SHE-2609-01`).
    La secuencia <NN> es por proveedor Y por mes: arranca en 01 cada mes y dos
    proveedores distintos nunca la comparten.

    NO crea la OC ni reserva el código — solo lo calcula. Si dos llamadas ocurren
    antes de que la primera OC se guarde, ambas devuelven el mismo número.
    """
    prefijo = f"OC-{_token_proveedor(proveedor_id)}-{datetime.now().strftime('%y%m')}-"

    usados: list[int] = []
    for oc in list_ocs(proveedor_id=proveedor_id):
        oc_id = str(oc.get("id") or "")
        if not oc_id.startswith(prefijo):
            continue
        sufijo = oc_id[len(prefijo):]
        try:
            usados.append(int(sufijo))
        except ValueError:
            # Código con sufijo no numérico: no participa de la secuencia.
            continue

    return f"{prefijo}{(max(usados) + 1) if usados else 1:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Cambio de estado — el único punto que escribe
# ─────────────────────────────────────────────────────────────────────────────


def cambiar_estado_oc(
    oc_id: str,
    estado_nuevo: str,
    quien: str = "",
    fecha: str | None = None,
) -> dict:
    """Orquesta una transición de estado: valida, persiste y deja rastro.

    `fecha` es la fecha de NEGOCIO del evento (backdateable por el AM); si no
    viene, el log usa el momento actual. Es la fecha que alimenta el lead time.

    Raises:
        ValueError: si la OC no existe o la transición no es legal. En ambos
            casos no se escribió nada: la validación va antes que el save.

    Returns:
        La OC ya actualizada.
    """
    oc = get_oc(oc_id)
    if oc is None:
        raise ValueError(f"cambiar_estado_oc: la OC '{oc_id}' no existe")

    actual = oc.get("estado")
    if not transicion_valida(actual, estado_nuevo):
        legales = TRANSICIONES.get(actual, ())
        detalle = ", ".join(legales) if legales else "ninguna (estado terminal)"
        raise ValueError(
            f"OC '{oc_id}': transición ilegal '{actual}' -> '{estado_nuevo}'. "
            f"Desde '{actual}' solo se puede pasar a: {detalle}"
        )

    oc["estado"] = estado_nuevo
    actualizada = save_oc(oc)

    # El estado se guarda primero: es lo que gobierna la próxima transición y lo
    # que ve la UI. El log es derivado (alimenta métricas) y se puede backfillear
    # a mano. En Fase 1 no hay transacción entre los dos archivos — limitación
    # conocida, se cierra cuando el backend sea Supabase.
    registrar_evento(oc_id, estado_nuevo, fecha=fecha, quien=quien)

    return actualizada


# ─────────────────────────────────────────────────────────────────────────────
# Lead time medido y fill rate
# ─────────────────────────────────────────────────────────────────────────────

LT_DESDE = "EMITIDA"
# NO convertir a string: tiene que seguir siendo tupla/conjunto. El chequeo de
# _muestra_lead_time es `not in`, o sea membresia exacta sobre la coleccion. Con
# un string, `not in` pasa a ser test de SUBSTRING y el bug vuelve peor: cualquier
# evento contenido en el texto cerraria la ventana, en silencio y sin fallar.
LT_HASTA = ("RECIBIDA_PARCIAL", "CERRADA")
"""Ventana del lead time medido: desde que se emite la OC hasta la PRIMERA
recepción. Se compara contra el lead time del maestro de proveedores, que es
compra -> llegada.

LT_HASTA es un CONJUNTO de eventos de cierre, no uno solo: una recepción completa
en un solo envío va EMITIDA -> CERRADA y nunca pasa por RECIBIDA_PARCIAL. Con un
único evento de cierre esas OC no cerraban la ventana y no aportaban muestra —
justo las que llegan de una, las mejores del proveedor. Cierra el PRIMERO de
estos eventos que aparezca; si hubo parcial, la parcial gana por ser anterior."""

_ESTADOS_FILL_RATE = ("CERRADA", "RECIBIDA_PARCIAL")
"""OC que ya recibieron algo y por lo tanto pueden aportar al fill rate."""

_ESTADO_EXCLUIDO_LT = "ANULADA"
"""Estado cuyas OC NO aportan muestra de lead time. Contrapartida de
_ESTADOS_FILL_RATE: las dos metricas tienen que filtrar por estado, si no una OC
anulada corre la mediana del proveedor. Regla sin excepciones — anulada es
anulada, aunque su log tenga la ventana EMITIDA -> recepcion completa."""


def _parse_fecha(valor) -> datetime | None:
    """Fecha ISO del log -> datetime. None si falta o está malformada.

    Nunca lanza: una fila con fecha rota hace que esa OC no aporte muestra, no
    que la métrica entera explote.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "nat", "none", "<na>"):
        return None
    try:
        return datetime.fromisoformat(texto)
    except (ValueError, TypeError):
        return None


def _muestra_lead_time(oc_id: str) -> int | None:
    """Días entre el primer LT_DESDE y el primer evento de LT_HASTA posterior.

    Cierra con CUALQUIERA de los eventos de LT_HASTA — el primero que aparezca.
    Una OC recibida completa de una sola vez cierra en CERRADA; una que llegó en
    tandas cierra en su primera RECIBIDA_PARCIAL, y el CERRADA posterior ya no
    mueve la muestra.

    "Posterior" es por posición en el log (orden de escritura), no por fecha: la
    fecha es backdateable y puede desordenarse. Si aun así el delta da negativo,
    el dato es inconsistente y la OC no aporta muestra.

    Returns:
        Días (>= 0), o None si la OC no completó la ventana.
    """
    df = leer_eventos(oc_id)
    if df.empty:
        return None

    filas = df.to_dict("records")

    desde = None
    for i, fila in enumerate(filas):
        if str(fila.get("evento")) == LT_DESDE:
            desde = (i, _parse_fecha(fila.get("fecha")))
            break
    if desde is None or desde[1] is None:
        return None

    idx_desde, fecha_desde = desde
    for fila in filas[idx_desde + 1:]:
        if str(fila.get("evento")) not in LT_HASTA:
            continue
        fecha_hasta = _parse_fecha(fila.get("fecha"))
        if fecha_hasta is None:
            return None
        dias = (fecha_hasta - fecha_desde).days
        return dias if dias >= 0 else None

    return None


def lead_time_medido(proveedor_id: str) -> float | None:
    """Mediana, en días, del lead time real de las OC de un proveedor.

    Mediana y no promedio: una OC atrasada por aduana no debe correr el número
    que se usa para planificar.

    Las OC en _ESTADO_EXCLUIDO_LT quedan fuera: no son performance del proveedor.
    El filtro va ANTES del walrus, asi que de esas OC ni se lee el log.

    Returns:
        Días (float), o None si ninguna OC aplicable completó la ventana
        LT_DESDE -> LT_HASTA.
    """
    muestras = [
        d
        for oc in list_ocs(proveedor_id=proveedor_id)
        if oc.get("estado") != _ESTADO_EXCLUIDO_LT
        and (d := _muestra_lead_time(str(oc.get("id") or ""))) is not None
    ]
    return float(median(muestras)) if muestras else None


def _num(valor, default: float = 0.0) -> float:
    """Casteo tolerante a float. El persistence ya validó qty al guardar; esto
    cubre el resto (recibido cargado a mano, datos viejos)."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return default
    return default if n != n else n  # NaN -> default


def fill_rate(proveedor_id: str) -> float | None:
    """Proporción de lo pedido que efectivamente llegó, sobre las OC que ya
    recibieron algo (CERRADA o RECIBIDA_PARCIAL).

    Returns:
        Float en [0, 1], o None si no hay OC aplicables o la cantidad pedida es 0.
        Se recorta a 1.0: una sobre-recepción sigue siendo "llegó todo".
    """
    qty_total = 0.0
    recibido_total = 0.0
    aplicables = 0

    for oc in list_ocs(proveedor_id=proveedor_id):
        if oc.get("estado") not in _ESTADOS_FILL_RATE:
            continue
        aplicables += 1
        for linea in oc.get("lineas") or []:
            if not isinstance(linea, dict):
                continue
            qty_total += _num(linea.get("qty"))
            recibido_total += _num(linea.get("recibido"))

    if not aplicables or qty_total <= 0:
        return None
    return min(1.0, recibido_total / qty_total)


def resumen_proveedor(proveedor_id: str) -> dict:
    """Métricas de un proveedor en un solo dict, listo para la UI.

    Los None se propagan tal cual — un proveedor sin OC registradas devuelve
    lt_medido=None y fill_rate=None, que es la respuesta correcta, no un cero.
    """
    ocs = list_ocs(proveedor_id=proveedor_id)
    return {
        "proveedor_id": proveedor_id,
        "lt_medido": lead_time_medido(proveedor_id),
        "fill_rate": fill_rate(proveedor_id),
        "n_ocs": len(ocs),
        "n_ocs_cerradas": sum(1 for oc in ocs if oc.get("estado") == "CERRADA"),
    }
