"""
Modulo: Ordenes de Compra (M37 Supply Chain - B1)
Seccion: Supply Chain
Version: v1

Segunda pantalla del modulo Supply Chain. Alta de ordenes de compra y avance por
su maquina de estados (PROPUESTA -> APROBADA -> OK_FIN -> EMITIDA ->
RECIBIDA_PARCIAL -> CERRADA, con ANULADA como salida desde cualquier estado no
terminal).

Cada avance registra una FECHA DE NEGOCIO. Esa fecha es la materia prima del
lead time medido: el sistema mide desde que la OC se emite hasta la primera
recepcion, y ese numero alimenta el Maestro de Proveedores.

Esta UI no toca disco, no genera codigos y no decide que transicion es legal:
todo sale de core.supply.persistence (CRUD) y core.supply.metrics (codigos,
maquina de estados). Los botones de avance se derivan de TRANSICIONES, asi que
nunca se ofrece una accion que cambiar_estado_oc vaya a rechazar.

B1 no tiene selector de cliente -- Gamboa es el piloto implicito. La
clientizacion va en B2.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from core.supply.metrics import (
    TRANSICIONES,
    cambiar_estado_oc,
    generar_codigo_oc,
)
from core.supply.oc_import import (
    consolidar_duplicados,
    detectar_columnas,
    parsear_lineas,
)
from core.supply.persistence import (
    ESTADOS_OC,
    get_oc,
    get_proveedor,
    list_ocs,
    list_proveedores,
    save_oc,
)

# ── Constants ───────────────────────────────────────────────────────────

MODULE_SLUG = "supply-ordenes"

_NARANJA = "#E84000"
_VERDE = "#1B6B2F"
_ROJO = "#B71C1C"
_GRIS = "#6B7280"
_AZUL = "#1D4B8F"
_VIOLETA = "#6B2D8F"
_AMBAR = "#B26A00"

_COLOR_ESTADO = {
    "PROPUESTA": _GRIS,
    "APROBADA": _AZUL,
    "OK_FIN": _VIOLETA,
    "EMITIDA": _NARANJA,
    "RECIBIDA_PARCIAL": _AMBAR,
    "CERRADA": _VERDE,
    "ANULADA": _ROJO,
}

_ETIQUETA_ESTADO = {
    "PROPUESTA": "Propuesta",
    "APROBADA": "Aprobada",
    "OK_FIN": "OK Finanzas",
    "EMITIDA": "Emitida",
    "RECIBIDA_PARCIAL": "Recibida parcial",
    "CERRADA": "Cerrada",
    "ANULADA": "Anulada",
}

_LABEL_TRANSICION = {
    "APROBADA": "✅ Aprobar",
    "OK_FIN": "💰 OK Finanzas",
    "EMITIDA": "📤 Emitir",
    "RECIBIDA_PARCIAL": "📥 Recibir parcial",
    "CERRADA": "🏁 Cerrar",
    "ANULADA": "🚫 Anular",
}

_ESTADOS_RECEPCION = ("EMITIDA", "RECIBIDA_PARCIAL")
"""Estados desde los que se puede cargar mercaderia recibida."""

_TRANSICIONES_POR_RECEPCION = ("RECIBIDA_PARCIAL", "CERRADA")
"""Destinos que NO se ofrecen como boton suelto cuando la OC esta en un estado
de recepcion: se disparan desde el bloque de recepcion, que ademas actualiza las
cantidades. Ofrecerlos por duplicado permitiria avanzar el estado sin cargar lo
que llego, que es justo el dato que el lead time y el fill rate necesitan."""

_TOPE_LINEAS = 20

_DELIMITADORES_CSV = ",;\t|"
"""Candidatos a separador del CSV. Acotados a proposito: ver `_sep_csv`."""

_ENCODINGS_CSV = ("utf-8-sig", "cp1252", "latin-1")
"""Cascada de decodificacion del CSV, en orden. Ver `_encoding_csv`."""

_BOMS_UTF16 = (b"\xff\xfe", b"\xfe\xff")

_KEY_OC_ABIERTA = "supply_oc_abierta"
_KEY_ALTA_ABIERTA = "supply_oc_alta_abierta"
"""Que dialogo esta abierto, anclado en session_state.

NO se abre un dialogo desde `if st.button(...): _dialog(...)`. Ese patron lo deja
vivo un solo run: en el rerun que trae el valor que el usuario acaba de elegir, el
boton ya devuelve False, el dialogo no se re-renderiza, y Streamlit marca stale y
BORRA el estado de todos sus widgets — con key o sin key. El handler termina
leyendo el default. Es lo que hacia que la fecha elegida no llegara nunca a
cambiar_estado_oc. Anclado en session_state, el dialogo se re-renderiza en cada
run y su estado sobrevive."""

_KEY_IMPORT = "supply_oc_import_preview"
"""Preview del import, anclado en session_state.

Guarda lo YA PARSEADO, no el archivo: Streamlit re-ejecuta el script entero en
cada interaccion, y con el archivo guardado cada click volveria a leer y parsear
las 150 filas."""

_KEY_IMPORT_NONCE = "supply_oc_import_nonce"
"""Contador que va en la key del uploader. Al cancelar o al crear la OC se
incrementa, y eso le da al uploader una key nueva: sin esto el archivo sigue
cargado en el widget y el bloque volveria a entrar en preview solo."""

_KEY_IMPORT_FLASH = "supply_oc_import_flash"
"""Mensaje de exito para el run siguiente. El st.rerun() que refresca la lista
se lleva puesto cualquier st.success escrito antes de llamarlo."""

_SOP_MD = """
Aca se registran las ordenes de compra y se las hace avanzar por sus estados:
**Propuesta → Aprobada → OK Finanzas → Emitida → Recibida (parcial) → Cerrada**.
Desde cualquier estado no terminal se puede **Anular**.

Cada avance pide una **fecha**: es la fecha de negocio del movimiento, no la del
dia en que lo cargas. Se puede backdatear, y conviene hacerlo — el sistema mide
el **lead time real** desde que la OC se emite hasta la primera recepcion, y ese
numero es el que aparece en el Maestro de Proveedores al lado del lead time
declarado. La diferencia entre los dos es el punto de todo esto.

Cuando la OC esta **Emitida** o **Recibida parcial**, el detalle habilita cargar
cuanto llego de cada linea. El total acumulado es lo que alimenta el fill rate.
"""


# ── Helpers de formato ──────────────────────────────────────────────────
# Todo lo que va a pantalla se convierte a string ACA. Ni un None ni un NaN
# llega crudo a un widget o a st.dataframe.


def _num(valor, default: float = 0.0) -> float:
    """Casteo tolerante a float. NaN y basura -> default."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return default
    return default if n != n else n


def _fmt_num(valor) -> str:
    """Numero -> string sin .0 sobrante. '' si no hay dato."""
    if valor is None or valor == "":
        return ""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if f != f:  # NaN
        return ""
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def _celda_planilla(valor):
    """Celda cruda de la planilla -> valor apto para el motor y para pantalla.

    Vacio (None / NaN / NaT) -> ''. Fecha -> string. El resto viaja tal cual:
    el motor del import ya sabe leer int, float y str.
    """
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        # pd.isna sobre algo no escalar: no es un vacio, sigue de largo.
        pass
    if isinstance(valor, (datetime, date)):
        return str(valor)
    return valor


def _encoding_csv(data: bytes) -> str:
    """Encoding con el que hay que leer este CSV.

    Los proveedores exportan desde su propio Excel y su propio locale (Peru,
    Ecuador, Bolivia, China, Pakistan): asumir UTF-8 en todos rechaza archivos
    buenos. La cascada, en orden:

    1. BOM de UTF-16 (`\\xff\\xfe` / `\\xfe\\xff`) -> utf-16. Es lo que escribe
       el "Guardar como" de Excel en algunas variantes, y sin esto el archivo
       ni se abre.
    2. utf-8-sig. Lo mas comun, y se come el BOM de UTF-8 si lo hay.
    3. cp1252. Lo que Excel en Windows escribe de verdad en español.
    4. latin-1, ultimo recurso.

    Por que latin-1 va ULTIMO y no segundo: nunca falla, decodifica cualquier
    byte. Si se lo prueba antes que cp1252, un archivo que fallo UTF-8 por otra
    razon se convierte en mojibake silencioso. cp1252 falla ruidosamente en los
    bytes que no le corresponden, asi que filtra antes del ultimo recurso.

    Args:
        data: Bytes del archivo.

    Returns:
        Nombre del encoding. Siempre devuelve uno: latin-1 no falla.
    """
    if data[:2] in _BOMS_UTF16:
        return "utf-16"
    for encoding in _ENCODINGS_CSV:
        try:
            data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin-1"


def _sep_csv(data: bytes, encoding: str) -> str:
    """Separador del CSV, sniffeado entre los candidatos razonables.

    NO se usa `sep=None` de pandas: su sniffer no acota los delimitadores y con
    un archivo de UNA columna elige cualquier caracter repetido. Con `SKU / A1 /
    A2` elige la letra 'U' y parte los SKU en dos, en silencio y sin fallar.
    Acotado a `, ; tab |`, ese archivo se lee como una sola columna.

    Sin pistas suficientes (una columna, o archivo raro) devuelve ',': un
    separador que no aparece deja la fila entera en una celda, que es
    exactamente lo que se quiere para un archivo de una columna.

    `encoding` lo resuelve `_encoding_csv` y lo comparte con la lectura: si el
    sniffer mirara un texto decodificado distinto del que despues parsea pandas,
    podria elegir un separador que en el otro texto no existe.

    Args:
        data: Bytes del archivo.
        encoding: El que devolvio `_encoding_csv` para estos mismos bytes.

    Returns:
        El caracter separador.
    """
    texto = data.decode(encoding, errors="replace")
    try:
        return csv.Sniffer().sniff(texto[:4096], delimiters=_DELIMITADORES_CSV).delimiter
    except csv.Error:
        return ","


def _leer_planilla(data: bytes, nombre: str) -> list[list]:
    """Archivo subido -> filas crudas para `core.supply.oc_import`.

    Solo LEE. No busca el header, no valida cantidades y no descarta nada: eso
    es del motor. La extension decide el lector; el nombre es el del archivo que
    subio el AM.

    Args:
        data: Bytes del archivo.
        nombre: Nombre del archivo, para la extension y para el mensaje de error.

    Returns:
        Lista de filas, cada una lista de celdas. Sin None ni NaN: la celda
        vacia es '' y las fechas vienen como string.

    Raises:
        ValueError: si la extension no es .xlsx ni .csv, o si el archivo no se
            pudo leer. Nunca escapa una excepcion de la libreria: el AM tiene
            que ver un mensaje, no un traceback.
    """
    low = str(nombre or "").lower()

    if low.endswith(".xlsx"):
        # header=None: el motor busca el header solo, en las primeras 6 filas.
        # Con el default, pandas se come la fila 0 como nombres de columna y esa
        # fila desaparece — justo la que el motor necesita ver.
        # dtype=object: sin esto una columna de SKU toda numerica se castea y
        # '001' se vuelve 1, que ya no matchea ningun SKU del maestro.
        def _leer():
            return pd.read_excel(BytesIO(data), header=None, dtype=object)
    elif low.endswith(".csv"):
        # Mismos dos motivos que arriba para header=None y dtype=object.
        # El encoding se resuelve una vez y lo comparten el sniffer y la
        # lectura: ver `_encoding_csv`.
        def _leer():
            encoding = _encoding_csv(data)
            return pd.read_csv(
                BytesIO(data),
                header=None,
                dtype=object,
                sep=_sep_csv(data, encoding),
                engine="python",
                encoding=encoding,
            )
    else:
        raise ValueError(
            f"No se puede leer «{nombre}»: solo se aceptan archivos .xlsx o .csv."
        )

    try:
        df = _leer()
    except Exception as e:
        # Archivo vacio, corrupto o que no es lo que dice la extension. El
        # detalle de la libreria va al final, entre parentesis, por si sirve.
        raise ValueError(
            f"No se pudo leer «{nombre}». Verificá que sea una planilla válida "
            f"y que no esté vacía ({type(e).__name__}: {e})."
        ) from e

    return [[_celda_planilla(celda) for celda in fila] for fila in df.values.tolist()]


def _fmt_fecha(iso) -> str:
    """ISO del persistence -> 'AAAA-MM-DD'. '—' si falta o esta rota."""
    texto = str(iso or "").strip()
    if len(texto) < 10:
        return "—"
    return texto[:10]


def _totales(oc: dict) -> tuple[int, float, float]:
    """(cantidad de lineas, unidades pedidas, unidades recibidas) de una OC."""
    lineas = [ln for ln in (oc.get("lineas") or []) if isinstance(ln, dict)]
    pedidas = sum(_num(ln.get("qty")) for ln in lineas)
    recibidas = sum(_num(ln.get("recibido")) for ln in lineas)
    return len(lineas), pedidas, recibidas


def _chip(estado: str) -> str:
    color = _COLOR_ESTADO.get(estado, _GRIS)
    etiqueta = _ETIQUETA_ESTADO.get(estado, estado or "—")
    return (
        f"<span style='display:inline-block;font-size:0.7rem;font-weight:700;"
        f"color:{color};background:{color}1A;border:1px solid {color}55;"
        f"border-radius:999px;padding:2px 9px;white-space:nowrap;'>{etiqueta}</span>"
    )


def _celda(texto: str, color: str = "#1F1F1F", bold: bool = False) -> str:
    peso = "700" if bold else "400"
    return (
        f"<div style='font-size:0.85rem;color:{color};font-weight:{peso};"
        f"padding-top:0.35rem;'>{texto}</div>"
    )


def _sub(texto: str) -> str:
    return f"<div style='font-size:0.68rem;color:{_GRIS};'>{texto}</div>"


def _quien() -> str:
    """Quien ejecuto el movimiento, para el log de eventos.

    En modo local (sin login) devuelve '' — el log acepta el campo vacio.
    """
    for clave in ("username", "name"):
        valor = st.session_state.get(clave)
        if valor:
            return str(valor)
    return ""


def _nombres_proveedores() -> dict[str, str]:
    """id -> nombre, incluyendo archivados: una OC vieja puede apuntar a uno."""
    return {
        str(p.get("id")): str(p.get("nombre") or p.get("id") or "")
        for p in list_proveedores(incluir_inactivos=True)
    }


# ── Header y empty state ────────────────────────────────────────────────


def _header() -> None:
    st.markdown("## 📦 Órdenes de Compra")
    st.caption(
        "📥 Alta de OC y avance por sus estados, con la fecha real de cada movimiento · "
        "Output: el lead time medido que alimenta el Maestro de Proveedores"
    )
    st.divider()


def _empty_state() -> None:
    st.markdown(
        "<div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;"
        " text-align: center; background: #FFF8F0;'>"
        f"<h3 style='color: {_NARANJA}; margin-top: 0;'>📂 Todavia no hay ordenes de compra</h3>"
        "<p style='color: #6B7280; margin: 0;'>"
        "Cargá la primera con el boton <strong>➕ Orden nueva</strong>. "
        "El codigo lo genera el sistema."
        "</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Apertura y cierre de dialogos ───────────────────────────────────────


def _abrir(bandera: str, valor=True) -> None:
    """Marca un dialogo como abierto. render() lo renderiza al final del run.

    Baja la otra bandera: Streamlit admite un solo dialogo por script run.
    """
    for otra in (_KEY_OC_ABIERTA, _KEY_ALTA_ABIERTA):
        if otra != bandera:
            st.session_state.pop(otra, None)
    st.session_state[bandera] = valor


def _cerrar_dialogos() -> None:
    """Baja las banderas y refresca. Al no re-renderizarse, el dialogo suelta el
    estado de sus widgets: la proxima apertura arranca limpia."""
    st.session_state.pop(_KEY_OC_ABIERTA, None)
    st.session_state.pop(_KEY_ALTA_ABIERTA, None)
    st.rerun()


# ── Dialogo de alta (@st.dialog — nunca st.form) ────────────────────────
# Los inputs van con value= y SIN key= a proposito: en 1.43.2, un widget con key
# deja el valor pegado en session_state y el modal reabriria con los datos de la
# OC anterior. Sin key, cada apertura arranca limpia. Los botones si llevan key.
# Las etiquetas de las lineas llevan el indice para que dos SKU iguales no
# compartan el id interno del widget.


@st.dialog("Orden de compra nueva")
def _dialog_alta_oc() -> None:
    proveedores = list_proveedores()
    if not proveedores:
        st.warning("Cargá un proveedor primero en el Maestro de Proveedores.")
        if st.button(
            "Entendido", key="supply_oc_alta_sin_prov", use_container_width=True
        ):
            _cerrar_dialogos()
        return

    nombres = {
        str(p.get("id")): str(p.get("nombre") or p.get("id")) for p in proveedores
    }
    prov_id = st.selectbox(
        "Proveedor *",
        options=list(nombres),
        format_func=lambda i: nombres.get(i, i),
    )

    st.caption(
        "Una linea por SKU. Las lineas que queden sin SKU se descartan al guardar."
    )
    n_lineas = st.number_input(
        "Cuantas lineas", min_value=1, max_value=_TOPE_LINEAS, step=1, value=1
    )

    lineas: list[dict] = []
    for i in range(int(n_lineas)):
        col_sku, col_qty = st.columns([3, 1])
        sku = col_sku.text_input(f"SKU #{i + 1}", value="", placeholder="SKU-001")
        qty = col_qty.number_input(f"Cantidad #{i + 1}", min_value=1, step=1, value=1)
        lineas.append({"sku": str(sku).strip(), "qty": int(qty), "recibido": 0})

    st.divider()
    col_cancel, col_ok = st.columns([1, 1])
    if col_cancel.button(
        "Cancelar", key="supply_oc_alta_cancel", use_container_width=True
    ):
        _cerrar_dialogos()
    if col_ok.button(
        "Crear OC",
        key="supply_oc_alta_confirm",
        type="primary",
        use_container_width=True,
    ):
        validas = [ln for ln in lineas if ln["sku"]]
        if not validas:
            st.error("Cargá al menos una linea con SKU.")
            return

        # El codigo lo genera core/supply/metrics.py (secuencia por proveedor y por mes),
        # no esta UI.
        oc = {
            "id": generar_codigo_oc(prov_id),
            "proveedor_id": prov_id,
            "estado": "PROPUESTA",
            "lineas": validas,
        }
        try:
            save_oc(oc)
        except ValueError as e:
            st.error(str(e))
            return

        st.success(f"OC {oc['id']} creada.")
        _cerrar_dialogos()


# ── Dialogo de detalle y acciones ───────────────────────────────────────


def _tabla_lineas(oc: dict) -> list[dict]:
    """Lineas de la OC listas para st.dataframe: todo string, nada de None."""
    filas = []
    for ln in oc.get("lineas") or []:
        if not isinstance(ln, dict):
            continue
        qty = _num(ln.get("qty"))
        recibido = _num(ln.get("recibido"))
        filas.append(
            {
                "SKU": str(ln.get("sku") or ""),
                "Pedido": _fmt_num(qty) or "0",
                "Recibido": _fmt_num(recibido) or "0",
                "Pendiente": _fmt_num(max(0.0, qty - recibido)) or "0",
            }
        )
    return filas


def _transicionar(oc_id: str, destino: str, fecha: date) -> None:
    """Dispara el cambio de estado y cierra el modal.

    El ValueError de metrics (transicion ilegal, OC inexistente) se muestra tal
    cual: ya viene redactado para el usuario.
    """
    try:
        # date_input devuelve un date; cambiar_estado_oc espera un string ISO.
        cambiar_estado_oc(oc_id, destino, quien=_quien(), fecha=fecha.isoformat())
    except ValueError as e:
        st.error(str(e))
        return
    st.success(f"OC {oc_id} → {_ETIQUETA_ESTADO.get(destino, destino)}.")
    _cerrar_dialogos()


def _bloque_avance(oc_id: str, destinos: list[str]) -> None:
    st.markdown("**Avanzar la OC**")
    fecha = st.date_input(
        "Fecha del movimiento",
        value=date.today(),
        help="Fecha de negocio del evento. Es la que alimenta el lead time medido.",
    )
    cols = st.columns(len(destinos))
    for col, destino in zip(cols, destinos):
        if col.button(
            _LABEL_TRANSICION.get(destino, destino),
            key=f"supply_oc_go_{destino}_{oc_id}",
            type="secondary" if destino == "ANULADA" else "primary",
            use_container_width=True,
        ):
            _transicionar(oc_id, destino, fecha)


def _bloque_recepcion(oc: dict) -> None:
    """Carga de lo recibido + transicion.

    Dos escrituras a proposito: primero se guardan las cantidades, despues
    cambiar_estado_oc relee, guarda el estado y escribe el evento en el log.
    """
    oc_id = str(oc.get("id") or "")

    st.markdown("**Registrar recepcion**")
    st.caption(
        "Cargá el total acumulado que llego de cada linea, no solo lo de esta tanda."
    )

    # El checkbox va ARRIBA de las lineas: define si los inputs se miran o no, y
    # asi el usuario lo ve antes de cargarlos en vano.
    completa = st.checkbox("Recepcion completa — cerrar la OC")
    if completa:
        st.caption(
            "☑️ Completa = **llego todo**: se pone recibido = pedido en todas las "
            "lineas y la OC se cierra. Los valores de abajo se ignoran."
        )

    nuevas: list[dict] = []
    for i, ln in enumerate(oc.get("lineas") or []):
        if not isinstance(ln, dict):
            continue
        sku = str(ln.get("sku") or "")
        qty = _num(ln.get("qty"))
        pedidas = _fmt_num(qty) or "0"
        recibido = st.number_input(
            f"{i + 1}. {sku} — pedidas {pedidas}",
            min_value=0,
            step=1,
            value=int(qty) if completa else int(_num(ln.get("recibido"))),
            disabled=completa,
        )
        # "Completa" gana sobre el input: se guarda la cantidad pedida tal cual
        # viene de la OC, sin pasar por el widget.
        nuevas.append({**ln, "recibido": ln.get("qty") if completa else int(recibido)})

    fecha = st.date_input(
        "Fecha de la recepcion",
        value=date.today(),
        help="Fecha de negocio de la llegada. Cierra la ventana del lead time medido.",
    )

    if st.button(
        "📥 Registrar recepcion",
        key=f"supply_oc_recep_{oc_id}",
        type="primary",
        use_container_width=True,
    ):
        if not nuevas:
            st.error("La OC no tiene lineas para recibir.")
            return
        try:
            save_oc({**oc, "lineas": nuevas})
        except ValueError as e:
            st.error(str(e))
            return

        destino = "CERRADA" if completa else "RECIBIDA_PARCIAL"
        try:
            cambiar_estado_oc(oc_id, destino, quien=_quien(), fecha=fecha.isoformat())
        except ValueError as e:
            # Las cantidades ya quedaron guardadas; solo fallo el avance de estado.
            st.error(f"Cantidades guardadas, pero el estado no avanzo: {e}")
            return

        st.success(
            f"Recepcion registrada. OC {oc_id} → "
            f"{_ETIQUETA_ESTADO.get(destino, destino)}."
        )
        _cerrar_dialogos()


@st.dialog("Detalle de la orden")
def _dialog_oc(oc_id: str) -> None:
    oc = get_oc(oc_id)
    if oc is None:
        st.error(f"La OC '{oc_id}' ya no existe.")
        return

    estado = str(oc.get("estado") or "")
    prov_id = str(oc.get("proveedor_id") or "")
    prov = get_proveedor(prov_id)
    prov_nombre = str((prov or {}).get("nombre") or prov_id or "—")

    st.markdown(
        f"<div style='font-size:1.05rem;font-weight:700;'>{oc_id}</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS};margin-bottom:6px;'>"
        f"🚚 {prov_nombre}</div>{_chip(estado)}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Creada {_fmt_fecha(oc.get('creado_en'))} · "
        f"ultimo movimiento {_fmt_fecha(oc.get('actualizado_en'))}"
    )

    n_lineas, pedidas, recibidas = _totales(oc)
    st.caption(
        f"{n_lineas} linea{'s' if n_lineas != 1 else ''} · "
        f"{_fmt_num(recibidas) or '0'} de {_fmt_num(pedidas) or '0'} unidades recibidas"
    )
    st.dataframe(_tabla_lineas(oc), use_container_width=True, hide_index=True)

    st.divider()

    legales = list(TRANSICIONES.get(estado, ()))
    puede_recibir = estado in _ESTADOS_RECEPCION

    if not legales:
        st.info(
            f"La OC esta **{_ETIQUETA_ESTADO.get(estado, estado)}**: es un estado "
            "terminal, no admite mas movimientos. Solo lectura."
        )
    else:
        # Los destinos de recepcion se ofrecen unicamente desde el bloque de
        # recepcion, que ademas actualiza cantidades.
        sueltos = [
            e
            for e in legales
            if not (puede_recibir and e in _TRANSICIONES_POR_RECEPCION)
        ]
        if puede_recibir:
            _bloque_recepcion(oc)
            if sueltos:
                st.divider()
        if sueltos:
            _bloque_avance(oc_id, sueltos)

    st.divider()
    if st.button(
        "Cerrar", key=f"supply_oc_det_cerrar_{oc_id}", use_container_width=True
    ):
        _cerrar_dialogos()


# ── Tabla ───────────────────────────────────────────────────────────────
# Filas armadas con st.columns y no con st.dataframe: hace falta un boton de
# accion por fila, que un dataframe no soporta.

_COLS = [1.9, 2.0, 1.5, 1.1, 0.9, 1.4, 0.8]


def _fila_header() -> None:
    cols = st.columns(_COLS)
    encabezados = ["Codigo", "Proveedor", "Estado", "Creada", "Lineas", "Unidades", ""]
    for col, texto in zip(cols, encabezados):
        col.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:{_GRIS};"
            f"text-transform:uppercase;letter-spacing:0.03em;'>{texto}</div>",
            unsafe_allow_html=True,
        )


def _fila_oc(oc: dict, nombres: dict[str, str]) -> None:
    oc_id = str(oc.get("id") or "")
    prov_id = str(oc.get("proveedor_id") or "")
    estado = str(oc.get("estado") or "")
    n_lineas, pedidas, recibidas = _totales(oc)

    c_id, c_prov, c_est, c_fecha, c_lin, c_uni, c_ver = st.columns(_COLS)

    c_id.markdown(_celda(oc_id, bold=True), unsafe_allow_html=True)
    c_prov.markdown(
        _celda(nombres.get(prov_id, prov_id) or "—"), unsafe_allow_html=True
    )
    c_est.markdown(
        f"<div style='padding-top:0.4rem;'>{_chip(estado)}</div>",
        unsafe_allow_html=True,
    )
    c_fecha.markdown(_celda(_fmt_fecha(oc.get("creado_en"))), unsafe_allow_html=True)
    c_lin.markdown(_celda(str(n_lineas)) + _sub("lineas"), unsafe_allow_html=True)

    # Recibidas / pedidas: el numerador es lo que mueve el fill rate.
    color_uni = _VERDE if pedidas and recibidas >= pedidas else "#1F1F1F"
    c_uni.markdown(
        _celda(
            f"{_fmt_num(recibidas) or '0'} / {_fmt_num(pedidas) or '0'}",
            color=color_uni,
            bold=True,
        )
        + _sub("recibidas / pedidas"),
        unsafe_allow_html=True,
    )

    if c_ver.button("Ver", key=f"supply_oc_ver_{oc_id}", help=f"Abrir {oc_id}"):
        _abrir(_KEY_OC_ABIERTA, oc_id)


# ── Import desde planilla ───────────────────────────────────────────────
# Bloque inline, NO dialogo: no toca el mecanismo de despacho del final de
# render(). El estado vive en _KEY_IMPORT y el flujo tiene dos pantallas —
# subir archivo, y revisar el preview antes de crear la OC.


def _limpiar_import() -> None:
    """Borra el preview y renueva la key del uploader."""
    st.session_state.pop(_KEY_IMPORT, None)
    st.session_state[_KEY_IMPORT_NONCE] = (
        int(st.session_state.get(_KEY_IMPORT_NONCE, 0)) + 1
    )


def _tabla_import(lineas: list[dict]) -> list[dict]:
    """Lineas a cargar, listas para st.dataframe: todo string, nada de None."""
    return [
        {
            "SKU": str(ln.get("sku") or ""),
            "Cantidad": _fmt_num(_num(ln.get("qty"))) or "0",
            "ETA": str(ln.get("eta") or "—"),
        }
        for ln in lineas
    ]


def _tabla_descartadas(descartadas: list[dict]) -> list[dict]:
    """Filas salteadas, con el numero de fila del archivo. Todo string."""
    return [
        {
            "Fila": _fmt_num(_num(d.get("fila"))) or "",
            "SKU": str(d.get("valor") or ""),
            "Motivo": str(d.get("motivo") or ""),
        }
        for d in descartadas
    ]


def _import_subir() -> None:
    """Pantalla 1: subir la planilla y dejar el preview en session_state."""
    st.caption(
        "Busca una columna con SKU y otra con la cantidad en las primeras 6 "
        "filas: el orden de las columnas no importa y los titulos de arriba se "
        "saltean solos. La columna de fecha (o ETA) es opcional."
    )

    nonce = int(st.session_state.get(_KEY_IMPORT_NONCE, 0))
    archivo = st.file_uploader(
        "Planilla de la OC",
        type=["csv", "xlsx"],
        key=f"supply_oc_import_file_{nonce}",
    )
    if archivo is None:
        return

    try:
        filas = _leer_planilla(archivo.getvalue(), archivo.name)
    except ValueError as e:
        st.error(str(e))
        return

    columnas = detectar_columnas(filas)
    if columnas is None:
        st.error(
            "No encontre las columnas de SKU y cantidad en las primeras 6 filas "
            "de la planilla. Revisá que el encabezado diga 'SKU' y 'Cantidad' "
            "(o 'Qty'), y que no haya mas de 6 filas de titulo arriba."
        )
        return

    lineas, descartadas = parsear_lineas(filas, columnas)
    lineas, avisos = consolidar_duplicados(lineas)

    st.session_state[_KEY_IMPORT] = {
        "lineas": lineas,
        "descartadas": descartadas,
        "avisos": avisos,
        "archivo": archivo.name,
    }
    st.rerun()


def _import_avisos(avisos: list[dict]) -> None:
    """Duplicados sumados y SKU que difieren solo en mayusculas."""
    for aviso in avisos:
        if aviso.get("tipo") == "duplicado":
            total = _fmt_num(_num(aviso.get("qty_total"))) or "0"
            st.info(
                f"El SKU **{aviso.get('sku')}** aparecia "
                f"{aviso.get('veces')} veces en la planilla: se sumo en una "
                f"sola linea de {total} unidades."
            )
        elif aviso.get("tipo") == "case":
            skus = ", ".join(str(s) for s in (aviso.get("skus") or []))
            st.warning(
                f"Estos SKU difieren solo en mayusculas y NO se unificaron: "
                f"{skus} — revisá si son el mismo producto."
            )


def _import_crear(prov_id: str, lineas: list[dict]) -> None:
    """Crea la OC con las lineas del preview. Mismo armado que el alta manual.

    El campo 'eta' viaja en la linea: `_validate_oc` solo exige 'sku' y 'qty', y
    `save_oc` conserva el resto de las claves.
    """
    oc = {
        "id": generar_codigo_oc(prov_id),
        "proveedor_id": prov_id,
        "estado": "PROPUESTA",
        "lineas": [
            {
                "sku": str(ln.get("sku") or ""),
                "qty": int(_num(ln.get("qty"))),
                "recibido": 0,
                "eta": str(ln.get("eta") or ""),
            }
            for ln in lineas
        ],
    }
    try:
        save_oc(oc)
    except ValueError as e:
        st.error(str(e))
        return

    _limpiar_import()
    st.session_state[_KEY_IMPORT_FLASH] = (
        f"OC {oc['id']} creada con {len(oc['lineas'])} lineas."
    )
    st.rerun()


def _import_preview(preview: dict) -> None:
    """Pantalla 2: revisar lo parseado y confirmar."""
    lineas = preview.get("lineas") or []
    descartadas = preview.get("descartadas") or []

    unidades = sum(_num(ln.get("qty")) for ln in lineas)
    st.caption(f"Archivo: {preview.get('archivo') or '—'}")
    st.markdown(
        f"**{len(lineas)} linea{'s' if len(lineas) != 1 else ''}** · "
        f"{_fmt_num(unidades) or '0'} unidades"
    )

    if lineas:
        st.dataframe(
            _tabla_import(lineas), use_container_width=True, hide_index=True
        )

    if descartadas:
        st.warning(
            f"{len(descartadas)} fila{'s' if len(descartadas) != 1 else ''} de "
            "la planilla no se van a cargar:"
        )
        st.dataframe(
            _tabla_descartadas(descartadas), use_container_width=True, hide_index=True
        )

    _import_avisos(preview.get("avisos") or [])

    proveedores = list_proveedores()
    activos = {
        str(p.get("id")): str(p.get("nombre") or p.get("id")) for p in proveedores
    }

    if not lineas:
        st.error(
            "Ninguna fila de la planilla quedo cargable. Revisá el detalle de "
            "arriba y volvé a subirla."
        )
    elif not activos:
        st.warning("Cargá un proveedor primero en el Maestro de Proveedores.")
    else:
        prov_id = st.selectbox(
            "Proveedor *",
            options=list(activos),
            format_func=lambda i: activos.get(i, i),
            key="supply_oc_import_prov",
        )

    col_crear, col_cancelar, _sp = st.columns([2, 2, 4])
    if lineas and activos:
        if col_crear.button(
            "Crear orden",
            key="supply_oc_import_crear",
            type="primary",
            use_container_width=True,
        ):
            _import_crear(prov_id, lineas)
    if col_cancelar.button(
        "Cancelar", key="supply_oc_import_cancelar", use_container_width=True
    ):
        _limpiar_import()
        st.rerun()


def _bloque_import() -> None:
    """Import masivo de lineas de OC desde una planilla.

    Colapsado por default: la pantalla que ya usa el AM no cambia hasta que el
    abra el bloque. Adentro NO puede haber otro expander (Streamlit no admite
    anidarlos).
    """
    flash = st.session_state.pop(_KEY_IMPORT_FLASH, None)
    if flash:
        st.success(flash)

    with st.expander("📥 Importar desde planilla", expanded=False):
        preview = st.session_state.get(_KEY_IMPORT)
        if preview:
            _import_preview(preview)
        else:
            _import_subir()


# ── Render principal ────────────────────────────────────────────────────


def render() -> None:
    """Punto de entrada del modulo. Llamado desde app.py.

    Sin early-return: el despacho de dialogos del final tiene que correr siempre,
    incluso con la lista vacia (es cuando se crea la primera OC).
    """
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    nombres = _nombres_proveedores()

    col_add, _sp = st.columns([2, 6])
    if col_add.button(
        "➕ Orden nueva", key="supply_oc_btn_alta", use_container_width=True
    ):
        _abrir(_KEY_ALTA_ABIERTA)

    _bloque_import()

    col_prov, col_est, _sp2 = st.columns([2.5, 2.5, 3])
    filtro_prov = col_prov.selectbox(
        "Proveedor",
        options=["Todos", *nombres],
        format_func=lambda i: "Todos" if i == "Todos" else nombres.get(i, i),
        key="supply_oc_filtro_prov",
    )
    filtro_estado = col_est.selectbox(
        "Estado",
        options=["Todos", *ESTADOS_OC],
        format_func=lambda e: "Todos" if e == "Todos" else _ETIQUETA_ESTADO.get(e, e),
        key="supply_oc_filtro_estado",
    )

    sin_filtros = filtro_prov == "Todos" and filtro_estado == "Todos"
    ocs = list_ocs(
        proveedor_id=None if filtro_prov == "Todos" else filtro_prov,
        estado=None if filtro_estado == "Todos" else filtro_estado,
    )

    st.divider()

    if not ocs:
        if sin_filtros:
            _empty_state()
        else:
            st.info("Ninguna orden coincide con esos filtros.")
    else:
        plural = "es" if len(ocs) != 1 else ""
        st.caption(f"{len(ocs)} orden{plural} de compra")

        _fila_header()
        for oc in ocs:
            _fila_oc(oc, nombres)

        st.divider()
        st.caption(
            "El **lead time medido** del Maestro de Proveedores sale de estas ordenes: "
            "se mide desde el movimiento **Emitida** hasta la **primera recepcion**, "
            "usando la fecha que cargaste en cada avance."
        )

    # Los dialogos se renderizan al FINAL y desde session_state, no desde el
    # `if boton:` que los abre. Va ultimo para que el click en «Ver» de una fila
    # ya se vea reflejado en este mismo run. Sin early-return arriba: el dialogo
    # tiene que seguir vivo aunque la lista quede vacia por los filtros.
    if st.session_state.get(_KEY_ALTA_ABIERTA):
        _dialog_alta_oc()
    elif oc_abierta := st.session_state.get(_KEY_OC_ABIERTA):
        # Streamlit admite un solo dialogo por run; el elif lo garantiza.
        _dialog_oc(str(oc_abierta))
