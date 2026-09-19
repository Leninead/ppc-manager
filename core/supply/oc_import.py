"""Carga masiva de órdenes de compra desde planilla (M37 Supply Chain).

Pedido de Fede tras testear el punto 1: arma OCs de ~150 SKUs y el alta manual
tiene tope de 20 líneas. Esta es la capa pura del import: recibe las filas de la
planilla como listas de Python y devuelve líneas con la forma que espera
`save_oc` ({sku, qty, eta}). Leer el Excel o el CSV es trabajo de la página.

Port de las reglas del Laboratorio de Compras de Fede. Fuente, línea por línea:
`notes/supply-chain/originales/laboratorio-compras-2026-08-17.html`
L637 (`normDate`), L645 (`findHeader`) y L745-756 (`mergeOCsLab`). Cada regla
cita la línea de la que sale. Donde este módulo se aparta del HTML es a
propósito y está marcado como DESVÍO.

Regla dura, igual que el resto de `core/supply/`:
- CERO acceso a disco, CERO Streamlit, CERO import de la capa de persistencia.
  Las filas entran por parámetro y las líneas salen por retorno; guardar la OC
  es trabajo del caller.
- Solo stdlib.

Dos criterios que ordenan todo el archivo:
- Lo descartado se explica; lo vacío no. Una fila de ejemplo o con cantidad
  inválida vuelve en `descartadas` con motivo y número de fila del archivo. Una
  fila vacía o sin SKU se saltea en silencio: es el final de la planilla, no un
  error.
- Se avisa, no se decide. Un SKU repetido idéntico se suma; dos SKUs que solo
  difieren en mayúsculas quedan separados y se avisan, porque en el maestro de
  Gamboa hay 34 casos así y no se sabe si son productos distintos.

API pública:
    detectar_columnas(filas)                    -> dict | None
    parsear_lineas(filas, columnas)             -> tuple[list[dict], list[dict]]
    consolidar_duplicados(lineas)               -> tuple[list[dict], list[dict]]
"""

from __future__ import annotations

import math
import re

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

VENTANA_HEADER = 6
"""Cuántas filas del principio se revisan buscando el header (HTML L645,
`Math.min(M.length, 6)`). Alcanza para los títulos que un proveedor pone arriba
de la tabla sin confundir un dato con un header más abajo."""

_CLAVES_SKU = ("sku",)
_CLAVES_QTY = ("cantidad", "qty", "quantity")
_CLAVES_FECHA = ("fecha", "eta")
"""Substrings que identifican cada columna, comparados en minúsculas. El HTML
(L747) solo reconoce 'sku', 'cantidad' y 'fecha'; 'qty', 'quantity' y 'eta' son
sinónimos agregados para planillas de proveedores en inglés."""

MOTIVO_EJEMPLO = "fila de ejemplo"
MOTIVO_NO_NUMERICA = "cantidad no numerica"
MOTIVO_NO_POSITIVA = "cantidad <= 0"
"""Motivos de descarte. Literales: la UI los muestra tal cual al usuario."""

TIPO_DUPLICADO = "duplicado"
TIPO_CASE = "case"
"""Tipos de aviso de `consolidar_duplicados`."""

_MARCA_EJEMPLO = "ejemplo"

_RE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_RE_DMY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
"""Regex de `normDate` (HTML L637). La de D/M/Y no está anclada, igual que el
`s.match` del HTML: encuentra la fecha aunque venga rodeada de texto."""

_LARGO_FECHA = 10

_RE_CANTIDAD = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?$")
"""Formato aceptado para una cantidad escrita como texto, ya sin espacios y con
la coma pasada a punto: dígitos 0-9, punto decimal opcional y signo opcional. Es
la regla explícita; no se delega en lo que `float()` tolere.

`[0-9]` y no `\\d`: `\\d` matchea también dígitos Unicode no latinos (el
árabe-índico '٥' pasaría como 5), y eso nadie lo tipea a propósito en una
planilla de compras. Se rechazan a propósito."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de celda
# ─────────────────────────────────────────────────────────────────────────────


def _texto(celda) -> str:
    """Celda a string. None -> ''. Equivale al `String(c || '')` del HTML para
    todo lo que no sea None, sin convertir el 0 numérico en vacío."""
    return "" if celda is None else str(celda)


def _celda(fila: list, indice: int | None):
    """Celda en `indice`, o None si la columna no existe o la fila es más corta.

    Las filas de una planilla no siempre traen todas las columnas del header:
    una celda que falta se trata igual que una vacía.
    """
    if indice is None or indice < 0 or indice >= len(fila):
        return None
    return fila[indice]


def _indice_con(
    celdas: list[str],
    claves: tuple[str, ...],
    excluir: tuple[int, ...] = (),
) -> int | None:
    """Primer índice cuya celda contiene alguna de las claves. None si ninguna.

    `celdas` ya viene en minúsculas. Es el `findIndex(x => x.includes(...))` del
    HTML (L747): gana la primera columna que matchea, de izquierda a derecha.
    Los índices de `excluir` no se consideran aunque matcheen.
    """
    for i, celda in enumerate(celdas):
        if i in excluir:
            continue
        if any(clave in celda for clave in claves):
            return i
    return None


def _a_numero(celda) -> float | None:
    """Cantidad a float, o None si no es un número finito.

    Paridad PARCIAL con `NUMX` (HTML L636). Se porta:
    - sacar TODOS los espacios, incluidos tab y el espacio duro (\\xa0) que
      Excel mete como separador;
    - la coma decimal: ',' pasa a '.' ("1,5" -> 1.5).

    DESVÍOS del HTML, a propósito:
    - `NUMX` convierte lo no numérico en 0 y la fila se saltea en silencio. Acá
      vacío, None, solo espacios o texto devuelven None y la fila se descarta
      como 'cantidad no numerica': un dato que falta tiene que verse.
    - No se porta el `parseFloat` que toma el prefijo numérico de un texto
      ("12 u" -> 12, "12-15 cajas" -> 12). Adivina sobre un dato ambiguo; mejor
      que lo mire una persona.
    - Separador de miles NO soportado. Con coma Y punto ("1.500,25",
      "1,500.25") o más de un punto tras el reemplazo, devuelve None. No se
      adivina cuál es cuál: un error acá mete un factor 1000 en la OC.

    Formato aceptado para un texto (ya sin espacios y con la coma pasada a
    punto): dígitos, con un punto decimal opcional y signo opcional
    (`_RE_CANTIDAD`). Se rechazan a propósito la notación científica ("1e3"),
    los guiones bajos ("1_000", que Python acepta y el HTML leería como 1) y los
    literales especiales de Python ("inf", "nan"). Un int o float nativo (como
    los devuelve el lector de Excel) no pasa por esta validación.

    Limitación conocida, NO resuelta: "1.500" (solo punto) se lee como 1.5 y
    redondea a 2, aunque en planillas en español pueda significar mil
    quinientos. Es ambiguo y se deja pasar así.
    """
    if celda is None or isinstance(celda, bool):
        return None
    if isinstance(celda, (int, float)):
        valor = float(celda)
    else:
        # HTML L636 — `.replace(/\s/g, '')`: fuera todos los espacios
        texto = re.sub(r"\s", "", str(celda))
        if not texto:
            return None
        # Separador de miles: coma y punto juntos es ambiguo
        if "," in texto and "." in texto:
            return None
        # HTML L636 — `.replace(',', '.')`: coma decimal
        texto = texto.replace(",", ".")
        if texto.count(".") > 1:
            return None
        # Formato explícito antes de convertir: cierra 1e3, 1_000, inf, nan, 0x10
        if not _RE_CANTIDAD.match(texto):
            return None
        try:
            valor = float(texto)
        except ValueError:
            return None
    return valor if math.isfinite(valor) else None


def _redondear(valor: float) -> int:
    """Redondeo de mitades hacia arriba: floor(v + 0.5).

    Paridad con el `Math.round` del HTML (L752). NO se usa `round()`: Python
    redondea las mitades al par (2.5 -> 2) y el HTML hacia arriba (2.5 -> 3).
    """
    return math.floor(valor + 0.5)


def _normalizar_fecha(celda) -> str:
    """Fecha de la planilla a 'YYYY-MM-DD'. Port de `normDate` (HTML L637).

    - 'YYYY-MM-DD...' se corta a los primeros 10 caracteres.
    - 'D/M/YYYY' o 'D/M/YY' pasa a ISO con el DÍA PRIMERO (formato latino); un
      año de menos de 4 dígitos se prefija con '20'.
    - Cualquier otra cosa devuelve sus primeros 10 caracteres tal cual.

    Args:
        celda: Valor de la celda de fecha. None se trata como vacío.

    Returns:
        La fecha normalizada, o '' si la celda viene vacía.
    """
    # HTML L637 — `(s==null?'':s).toString().trim()`
    texto = _texto(celda).strip()

    # HTML L637 — ISO: se corta
    if _RE_ISO.match(texto):
        return texto[:_LARGO_FECHA]

    # HTML L637 — D/M/Y, día primero
    m = _RE_DMY.search(texto)
    if m:
        dia, mes, anio = m.group(1), m.group(2), m.group(3)
        if len(anio) < 4:
            anio = "20" + anio
        return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"

    # HTML L637 — cualquier otra cosa: primeros 10 caracteres
    return texto[:_LARGO_FECHA]


# ─────────────────────────────────────────────────────────────────────────────
# Detección del header
# ─────────────────────────────────────────────────────────────────────────────


def detectar_columnas(filas: list[list]) -> dict | None:
    """Ubica el header de la planilla y los índices de sus columnas.

    Port de `findHeader` (HTML L645) más la resolución de columnas de
    `mergeOCsLab` (L747). Se revisan las primeras 6 filas; es header la primera
    que tenga una celda con 'sku' y otra con 'cantidad' | 'qty' | 'quantity',
    comparando en minúsculas y por substring.

    Args:
        filas: Filas de la planilla, cada una una lista de celdas.

    Returns:
        {'fila_header': int, 'sku': int, 'qty': int, 'fecha': int | None} con
        índices base 0, o None si no hay header en la ventana. 'fecha' es la
        primera columna con 'fecha' | 'eta' que no sea la de SKU ni la de
        cantidad, o None si no hay.
    """
    # HTML L645 — ventana de 6 filas
    for i in range(min(len(filas), VENTANA_HEADER)):
        # HTML L645 — `(M[i] || []).map(c => String(c || '').toLowerCase())`
        celdas = [_texto(c).lower() for c in (filas[i] or [])]

        # HTML L747 — primera columna que matchea cada clave
        indice_sku = _indice_con(celdas, _CLAVES_SKU)
        indice_qty = _indice_con(celdas, _CLAVES_QTY)
        if indice_sku is None or indice_qty is None:
            continue

        # La fecha no puede caer sobre la columna de SKU o de cantidad: un header
        # "SKU ETA" la haría apuntar al SKU. Si el único candidato es una de
        # esas dos, no hay columna de fecha.
        return {
            "fila_header": i,
            "sku": indice_sku,
            "qty": indice_qty,
            "fecha": _indice_con(celdas, _CLAVES_FECHA, excluir=(indice_sku, indice_qty)),
        }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Parseo de líneas
# ─────────────────────────────────────────────────────────────────────────────


def parsear_lineas(filas: list[list], columnas: dict) -> tuple[list[dict], list[dict]]:
    """Convierte las filas debajo del header en líneas de OC.

    Port de `mergeOCsLab` (HTML L749-754). El orden de las reglas importa y es
    el del HTML: SKU vacío se saltea antes de mirar si la fila es de ejemplo, y
    la fila de ejemplo se descarta antes de mirar la cantidad.

    Args:
        filas: Filas de la planilla completa, header incluido.
        columnas: Retorno de `detectar_columnas`.

    Returns:
        (lineas_ok, descartadas):
            lineas_ok: [{'sku': str, 'qty': int, 'eta': str}, ...] en orden de
                aparición. Sin 'recibido': lo agrega quien guarda la OC.
            descartadas: [{'fila': int, 'valor': str, 'motivo': str}, ...].
                'fila' es el número de fila del archivo, base 1 (lo que el
                usuario ve en Excel). 'valor' es la celda de SKU, porque es por
                donde el usuario busca la fila.
    """
    indice_sku = columnas["sku"]
    indice_qty = columnas["qty"]
    indice_fecha = columnas.get("fecha")

    lineas_ok: list[dict] = []
    descartadas: list[dict] = []

    # HTML L749 — desde la fila siguiente al header
    for i in range(columnas["fila_header"] + 1, len(filas)):
        fila = filas[i]
        # HTML L749 — `if(!r) continue`
        if not fila:
            continue

        # HTML L750 — SKU vacío tras trim: se saltea sin registrar
        sku = _texto(_celda(fila, indice_sku)).strip()
        if not sku:
            continue

        numero_fila = i + 1

        # HTML L751 — 'ejemplo' en cualquier celda
        if any(_MARCA_EJEMPLO in _texto(c).lower() for c in fila):
            descartadas.append(
                {"fila": numero_fila, "valor": sku, "motivo": MOTIVO_EJEMPLO}
            )
            continue

        # HTML L752 — cantidad. DESVÍO: lo no numérico se descarta con motivo
        # propio en vez de volverse 0 (ver _a_numero).
        valor = _a_numero(_celda(fila, indice_qty))
        if valor is None:
            descartadas.append(
                {"fila": numero_fila, "valor": sku, "motivo": MOTIVO_NO_NUMERICA}
            )
            continue

        # HTML L752 — `Math.round(...)`, y `if(q<=0)` después de redondear
        qty = _redondear(valor)
        if qty <= 0:
            descartadas.append(
                {"fila": numero_fila, "valor": sku, "motivo": MOTIVO_NO_POSITIVA}
            )
            continue

        # HTML L754 — `eta: cf>=0 ? normDate(r[cf]) : ''`
        eta = _normalizar_fecha(_celda(fila, indice_fecha)) if indice_fecha is not None else ""

        lineas_ok.append({"sku": sku, "qty": qty, "eta": eta})

    return lineas_ok, descartadas


# ─────────────────────────────────────────────────────────────────────────────
# Consolidación de duplicados
# ─────────────────────────────────────────────────────────────────────────────


def consolidar_duplicados(lineas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Suma los SKUs repetidos idénticos y avisa los que difieren en mayúsculas.

    No está en el HTML: el Lab guarda cada fila por separado y suma recién al
    calcular la posición. Una OC necesita una línea por SKU.

    - SKU idéntico (case-sensitive): una sola línea con la qty sumada, en la
      posición de su primera aparición y con la ETA de esa primera aparición,
      aunque venga vacía. No se completan huecos con ETAs de filas posteriores.
    - SKUs que difieren solo en mayúsculas: NO se consolidan. Quedan como líneas
      separadas y se avisa, porque pueden ser productos distintos.

    Args:
        lineas: Retorno de `parsear_lineas` (lineas_ok). No se muta.

    Returns:
        (lineas_consolidadas, avisos). Avisos, primero los de duplicado y después
        los de mayúsculas, cada grupo en orden de primera aparición:
            {'tipo': 'duplicado', 'sku': str, 'veces': int, 'qty_total': int}
            {'tipo': 'case', 'skus': list[str]}   # skus ordenado con sorted()
    """
    por_sku: dict[str, dict] = {}
    veces: dict[str, int] = {}
    orden: list[str] = []

    for linea in lineas:
        sku = linea["sku"]
        if sku in por_sku:
            por_sku[sku]["qty"] += linea["qty"]
            veces[sku] += 1
        else:
            # Copia: la ETA y el resto de los campos quedan los de la primera
            # aparición, y la línea del caller no se toca.
            por_sku[sku] = dict(linea)
            veces[sku] = 1
            orden.append(sku)

    consolidadas = [por_sku[sku] for sku in orden]

    avisos: list[dict] = [
        {
            "tipo": TIPO_DUPLICADO,
            "sku": sku,
            "veces": veces[sku],
            "qty_total": por_sku[sku]["qty"],
        }
        for sku in orden
        if veces[sku] > 1
    ]

    # SKUs distintos que colapsan al pasarlos a minúsculas
    grupos: dict[str, list[str]] = {}
    for sku in orden:
        grupos.setdefault(sku.lower(), []).append(sku)
    avisos.extend(
        {"tipo": TIPO_CASE, "skus": sorted(variantes)}
        for variantes in grupos.values()
        if len(variantes) > 1
    )

    return consolidadas, avisos
