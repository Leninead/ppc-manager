"""Lógica de negocio del módulo Supply Chain (M37).

Contrapartida exacta de `core/supply/persistence.py`: allá va el CRUD y la
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

from core.supply.persistence import (
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

MOTIVO_OK = "ok"
MOTIVO_SIN_EVENTOS = "sin_eventos"
MOTIVO_SIN_EMITIDA = "sin_emitida"
MOTIVO_EMITIDA_DUPLICADA = "emitida_duplicada"
MOTIVO_FECHA_ILEGIBLE = "fecha_ilegible"
MOTIVO_SIN_RECEPCION = "sin_recepcion"
MOTIVO_FECHAS_INVERTIDAS = "fechas_invertidas"
"""Motivos de `diagnosticar_lead_time`. Literales: viajan a la UI y el AM los
lee traducidos, pero el contrato es el string."""

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


def diagnosticar_lead_time(eventos: list[dict]) -> dict:
    """Lead time de UNA OC, con el motivo cuando no se puede medir.

    Es la version explicada de `_muestra_lead_time`: mismas reglas de calculo,
    pero en vez de un `None` mudo devuelve por que. Hoy una OC con dos EMITIDA,
    o con una fecha que no parsea, simplemente desaparece de la mediana del
    proveedor y nadie se entera.

    Las dos conviven a proposito en esta tanda: `_muestra_lead_time` sigue
    alimentando `lead_time_medido` sin tocarse. El refactor para que una use a
    la otra va aparte.

    NO detecta una fecha mal cargada. Si el AM backdateo la emision y dejo el
    default de hoy en la recepcion, el delta entre esas dos fechas es real y el
    motivo es 'ok': un dato mal cargado es indistinguible de uno bueno. Eso lo
    ataja el preview del lead time antes de confirmar la recepcion, no esta
    funcion.

    Motivos, en el orden en que se chequean:

    | motivo              | cuando |
    |---------------------|--------|
    | `sin_eventos`       | la lista viene vacia |
    | `sin_emitida`       | no hay ningun evento EMITIDA |
    | `emitida_duplicada` | hay mas de un EMITIDA — se reporta AUNQUE el calculo hubiera dado un numero |
    | `fecha_ilegible`    | la fecha de la emision o la de la recepcion no parsea |
    | `sin_recepcion`     | no hay RECIBIDA_PARCIAL ni CERRADA despues de la emision (por posicion) |
    | `fechas_invertidas` | el delta da negativo |
    | `ok`                | midio |

    Args:
        eventos: Eventos de UNA OC, en ORDEN DE ESCRITURA (el que devuelve
            `leer_eventos`), como lista de dicts con 'evento' y 'fecha'. Las
            demas claves se ignoran.

    Returns:
        {'dias': int | None, 'motivo': str}. 'dias' es int >= 0 solo con
        motivo 'ok'; en todos los demas es None.
    """
    if not eventos:
        return {"dias": None, "motivo": MOTIVO_SIN_EVENTOS}

    emitidas = [
        i for i, ev in enumerate(eventos) if str(ev.get("evento")) == LT_DESDE
    ]
    if not emitidas:
        return {"dias": None, "motivo": MOTIVO_SIN_EMITIDA}
    if len(emitidas) > 1:
        # Antes que cualquier otro chequeo: con dos emisiones el numero no es
        # confiable ni cuando sale, porque se mide contra la PRIMERA por
        # posicion, que puede ser la cargada por error.
        return {"dias": None, "motivo": MOTIVO_EMITIDA_DUPLICADA}

    idx_desde = emitidas[0]
    fecha_desde = _parse_fecha(eventos[idx_desde].get("fecha"))
    if fecha_desde is None:
        return {"dias": None, "motivo": MOTIVO_FECHA_ILEGIBLE}

    recepcion = next(
        (
            ev
            for ev in eventos[idx_desde + 1:]
            if str(ev.get("evento")) in LT_HASTA
        ),
        None,
    )
    if recepcion is None:
        return {"dias": None, "motivo": MOTIVO_SIN_RECEPCION}

    fecha_hasta = _parse_fecha(recepcion.get("fecha"))
    if fecha_hasta is None:
        return {"dias": None, "motivo": MOTIVO_FECHA_ILEGIBLE}

    # DEUDA heredada de _muestra_lead_time, mantenida a proposito para no
    # divergir: si una fecha trae hora y la otra es medianoche, `.days` trunca y
    # descuenta un dia. Pasa cuando un evento se registro sin fecha explicita
    # (el log usa _now_iso(), con hora) y el otro vino del date_input, que
    # llega a medianoche. 2026-07-20T10:30 -> 2026-08-25 da 35, no 36.
    dias = (fecha_hasta - fecha_desde).days
    if dias < 0:
        return {"dias": None, "motivo": MOTIVO_FECHAS_INVERTIDAS}

    return {"dias": dias, "motivo": MOTIVO_OK}


def previsualizar_lead_time(
    eventos: list[dict],
    fecha_recepcion: str,
    lt_min: float | None = None,
    lt_max: float | None = None,
) -> dict:
    """Lead time que va a quedar registrado si se confirma esta recepcion.

    Para que sirve: muestra el numero ANTES de confirmar la recepcion. Es lo
    que hubiera atajado el caso de Fede (54 dias en Tarik por dejar la fecha de
    hoy en la recepcion): `diagnosticar_lead_time` no lo ve, porque un dato mal
    cargado es indistinguible de uno bueno; el AM si, si lo tiene enfrente
    contra el rango del proveedor.

    Reglas:

    1. Simulacion: arma una copia de `eventos` con un RECIBIDA_PARCIAL
       hipotetico en `fecha_recepcion` AL FINAL y la pasa por
       `diagnosticar_lead_time`. 'dias' y 'motivo' salen de ahi. Para el lead
       time da igual PARCIAL o CERRADA: los dos estan en LT_HASTA. La lista
       recibida nunca se muta.
    2. 'ya_medido': en los eventos ACTUALES ya hay un evento de LT_HASTA
       despues, por posicion, del primer EMITIDA. Esta recepcion no cierra la
       ventana. Sin EMITIDA -> False.
    3. 'fecha_emision': fecha del PRIMER EMITIDA por posicion, 'YYYY-MM-DD'.
       None si no hay EMITIDA o su fecha no parsea.
    4. 'fuera_de_rango': solo si el motivo es 'ok' y no esta ya medido (es el
       numero que el AM esta por registrar); si no, None. 'arriba' si
       dias > lt_max, 'abajo' si dias < lt_min, bordes inclusivos. Con
       lt_max None nunca 'arriba'; con lt_min None nunca 'abajo'.
    5. 'bloquear': `fecha_recepcion`, a nivel DIA, es anterior a la emision
       MAS TEMPRANA entre los EMITIDA con fecha parseable. Se evalua siempre,
       este o no ya medido. La mas temprana y no la primera: si el AM cargo un
       EMITIDA por error con la fecha de hoy y despues el correcto, comparar
       contra el primero le impediria registrar una recepcion legitima. Solo
       se bloquea lo fisicamente imposible. Sin EMITIDA parseable -> False.

    `fecha_recepcion` que no parsea -> bloquear False: algo que no es fecha no
    es anterior a nada. El date_input de la pantalla nunca da vacio.

    DEUDA heredada del truncamiento de `.days`: si el EMITIDA trae hora y la
    recepcion es el mismo dia a medianoche, el motivo sale 'fechas_invertidas'
    pero bloquear es False (a nivel dia no es anterior). No pasa con datos
    cargados desde la pantalla, que siempre escribe fechas sin hora. El arreglo
    de fondo va aparte.

    Args:
        eventos: Eventos de UNA OC, en ORDEN DE ESCRITURA (el que devuelve
            `leer_eventos`), como lista de dicts con 'evento' y 'fecha'.
        fecha_recepcion: Fecha de la recepcion a confirmar, 'YYYY-MM-DD'
            (lo que da el date_input).
        lt_min: Lead time minimo declarado del proveedor, en dias. None si no
            hay.
        lt_max: Lead time maximo declarado del proveedor, en dias. None si no
            hay.

    Returns:
        {'dias': int | None, 'motivo': str, 'ya_medido': bool,
         'fecha_emision': str | None, 'fuera_de_rango': None | 'arriba' |
         'abajo', 'bloquear': bool}
    """
    simulados = list(eventos) + [
        {"evento": "RECIBIDA_PARCIAL", "fecha": fecha_recepcion}
    ]
    diagnostico = diagnosticar_lead_time(simulados)
    dias = diagnostico["dias"]
    motivo = diagnostico["motivo"]

    idx_emitidas = [
        i for i, ev in enumerate(eventos) if str(ev.get("evento")) == LT_DESDE
    ]

    ya_medido = False
    fecha_emision = None
    if idx_emitidas:
        primera = idx_emitidas[0]
        ya_medido = any(
            str(ev.get("evento")) in LT_HASTA for ev in eventos[primera + 1:]
        )
        emision = _parse_fecha(eventos[primera].get("fecha"))
        if emision is not None:
            fecha_emision = emision.date().isoformat()

    fuera_de_rango = None
    if motivo == MOTIVO_OK and not ya_medido:
        if lt_max is not None and dias > lt_max:
            fuera_de_rango = "arriba"
        elif lt_min is not None and dias < lt_min:
            fuera_de_rango = "abajo"

    emisiones = [
        f
        for f in (_parse_fecha(eventos[i].get("fecha")) for i in idx_emitidas)
        if f is not None
    ]
    recepcion = _parse_fecha(fecha_recepcion)
    bloquear = bool(
        emisiones
        and recepcion is not None
        and recepcion.date() < min(f.date() for f in emisiones)
    )

    return {
        "dias": dias,
        "motivo": motivo,
        "ya_medido": ya_medido,
        "fecha_emision": fecha_emision,
        "fuera_de_rango": fuera_de_rango,
        "bloquear": bloquear,
    }


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
