"""Recepción de una orden de compra desde planilla (M37 Supply Chain).

Pedido de Fede: una OC Emitida de 109 líneas no se puede recibir a mano SKU por
SKU. La planilla se lee con el mismo motor que el alta masiva
(`core.supply.oc_import`); este módulo arma la plantilla y cruza lo leído
contra las líneas de la OC.

Decisiones, las mismas que la recepción manual de `supply_ordenes.py`:
- La planilla trae el total ACUMULADO recibido por SKU, no la tanda. Subir dos
  veces la misma planilla no duplica nada.
- Un SKU que no está en la OC se rechaza con motivo; nunca se agrega la línea.
- Recibir más de lo pedido se permite y se avisa: `fill_rate` ya lo recorta a
  1.0.
- Las líneas de la OC que no vienen en la planilla no se tocan.
- Dos SKUs que difieren solo en mayúsculas no se unifican: se rechaza y se
  sugiere el de la OC (mismo criterio que `consolidar_duplicados`).

Regla dura, igual que el resto de `core/supply/`: CERO disco, CERO Streamlit,
CERO import de la capa de persistencia. Solo stdlib.

API pública:
    filas_plantilla(lineas_oc)                  -> list[list]
    sin_cantidad_vacia(filas, columnas)         -> list[list]
    cruzar_recepcion(lineas_oc, lineas_planilla) -> dict
    fechas_planilla(lineas_planilla)            -> list[str]
"""

from __future__ import annotations

COLUMNAS_PLANTILLA = ("SKU", "Pedidas", "Ya recibidas", "Cantidad recibida (acumulado)")
"""Header de la plantilla. Solo la última columna puede contener 'cantidad',
'qty' o 'quantity': `detectar_columnas` toma la primera que matchea y, si
«Pedidas» lo hiciera, leería lo pedido como recibido."""

MOTIVO_FUERA_DE_OC = "el SKU no esta en la OC"
MOTIVO_SOLO_MAYUSCULAS = "difiere solo en mayusculas de un SKU de la OC"
MOTIVO_REPETIDO_EN_OC = "el SKU esta repetido en la OC: no se sabe a que linea va"
"""Motivos de rechazo. Literales: la UI los muestra tal cual."""

DESTINO_CERRADA = "CERRADA"
DESTINO_PARCIAL = "RECIBIDA_PARCIAL"


def _num(valor) -> float:
    """Cantidad guardada en la OC a float; lo ilegible cuenta como 0."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if n != n else n


def _entero(valor: float) -> int | float:
    """3.0 -> 3 para que la vista previa no muestre decimales que no existen."""
    return int(valor) if float(valor).is_integer() else valor


def filas_plantilla(lineas_oc: list[dict]) -> list[list]:
    """Plantilla de recepción con las líneas de la OC ya cargadas.

    La columna de cantidad va vacía: lo que no llegó se deja así y
    `sin_cantidad_vacia` lo saltea sin reportarlo.
    """
    filas: list[list] = [list(COLUMNAS_PLANTILLA)]
    for ln in lineas_oc:
        if not isinstance(ln, dict):
            continue
        filas.append(
            [
                str(ln.get("sku") or ""),
                _entero(_num(ln.get("qty"))),
                _entero(_num(ln.get("recibido"))),
                "",
            ]
        )
    return filas


def _celda_vacia(celda) -> bool:
    return celda is None or (isinstance(celda, str) and not celda.strip())


def sin_cantidad_vacia(filas: list[list], columnas: dict) -> list[list]:
    """Vacía las filas de datos cuya celda de cantidad está en blanco.

    `parsear_lineas` descarta una cantidad vacía como 'cantidad no numerica'.
    En el alta eso es un dato que falta; en la recepción es la línea que no
    llegó, y la plantilla trae todas. La fila pasa a [] en vez de borrarse para
    que los números de fila de los descartes sigan siendo los del archivo.
    """
    indice_qty = columnas["qty"]
    resultado: list[list] = []
    for i, fila in enumerate(filas):
        if i > columnas["fila_header"] and fila:
            celda = fila[indice_qty] if indice_qty < len(fila) else None
            if _celda_vacia(celda):
                resultado.append([])
                continue
        resultado.append(fila)
    return resultado


def cruzar_recepcion(lineas_oc: list[dict], lineas_planilla: list[dict]) -> dict:
    """Aplica lo recibido de la planilla sobre las líneas de la OC.

    Args:
        lineas_oc: Líneas de la OC ({sku, qty, recibido, ...}). No se mutan.
        lineas_planilla: Salida de `consolidar_duplicados` ({sku, qty, eta}),
            con 'qty' = total acumulado recibido. No se mutan.

    Returns:
        {
          'lineas': líneas de la OC en su orden, copias, con 'recibido'
              actualizado donde hubo match. Listas para `save_oc`.
          'aplicadas': [{'sku', 'pedidas', 'antes', 'despues', 'excede',
              'baja'}] en el orden de la OC.
          'rechazadas': [{'sku', 'motivo', 'sugerido'}] en el orden de la
              planilla. 'sugerido' es el SKU (o los SKUs) de la OC que difiere
              solo en mayúsculas; '' si no aplica.
          'sin_tocar': líneas de la OC que no vienen en la planilla.
          'destino': 'CERRADA' si todas las líneas quedan con recibido >=
              pedido, si no 'RECIBIDA_PARCIAL'.
        }
    """
    indices_por_sku: dict[str, list[int]] = {}
    for i, ln in enumerate(lineas_oc):
        if isinstance(ln, dict):
            indices_por_sku.setdefault(str(ln.get("sku") or ""), []).append(i)

    skus_por_minuscula: dict[str, list[str]] = {}
    for sku in indices_por_sku:
        skus_por_minuscula.setdefault(sku.lower(), []).append(sku)

    lineas = [dict(ln) if isinstance(ln, dict) else ln for ln in lineas_oc]
    recibido_por_indice: dict[int, int] = {}
    rechazadas: list[dict] = []

    for ln in lineas_planilla:
        sku = str(ln.get("sku") or "")
        indices = indices_por_sku.get(sku)
        if indices is None:
            variantes = skus_por_minuscula.get(sku.lower())
            rechazadas.append(
                {
                    "sku": sku,
                    "motivo": MOTIVO_SOLO_MAYUSCULAS if variantes else MOTIVO_FUERA_DE_OC,
                    "sugerido": ", ".join(sorted(variantes)) if variantes else "",
                }
            )
        elif len(indices) > 1:
            rechazadas.append({"sku": sku, "motivo": MOTIVO_REPETIDO_EN_OC, "sugerido": ""})
        else:
            recibido_por_indice[indices[0]] = ln["qty"]

    aplicadas: list[dict] = []
    for i in sorted(recibido_por_indice):
        pedidas = _num(lineas[i].get("qty"))
        antes = _num(lineas[i].get("recibido"))
        despues = recibido_por_indice[i]
        lineas[i]["recibido"] = despues
        aplicadas.append(
            {
                "sku": lineas[i]["sku"],
                "pedidas": _entero(pedidas),
                "antes": _entero(antes),
                "despues": despues,
                "excede": despues > pedidas,
                "baja": despues < antes,
            }
        )

    con_dict = [ln for ln in lineas if isinstance(ln, dict)]
    todo_llego = all(_num(ln.get("recibido")) >= _num(ln.get("qty")) for ln in con_dict)

    return {
        "lineas": lineas,
        "aplicadas": aplicadas,
        "rechazadas": rechazadas,
        "sin_tocar": len(con_dict) - len(recibido_por_indice),
        "destino": DESTINO_CERRADA if todo_llego else DESTINO_PARCIAL,
    }


def fechas_planilla(lineas_planilla: list[dict]) -> list[str]:
    """Fechas distintas que trae la columna de fecha de la planilla, ordenadas.

    La recepción registra una sola fecha para toda la carga: con una sola
    fecha la pantalla la propone; con varias, avisa y deja elegir.
    """
    return sorted({str(ln.get("eta") or "").strip() for ln in lineas_planilla} - {""})
