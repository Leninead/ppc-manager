"""
Modulo: Maestro de Proveedores (M37 Supply Chain - B1)
Seccion: Supply Chain
Version: v1

Primera pantalla del modulo Supply Chain. Alta, edicion y archivado de
proveedores, con el lead time DECLARADO (lo que dice el proveedor) al lado del
lead time MEDIDO (lo que tardo de verdad, calculado sobre las ordenes de compra).
Ese gap es el punto de la pantalla.

Esta UI no toca disco ni calcula metricas: todo sale de core.supply_persistence
(CRUD) y core.supply_metrics (lead time medido, fill rate).

B1 no tiene selector de cliente -- Gamboa es el piloto implicito. La
clientizacion va en B2.
"""
from __future__ import annotations

import streamlit as st

from core.supply_metrics import resumen_proveedor
from core.supply_persistence import (
    archivar_proveedor,
    get_proveedor,
    list_proveedores,
    save_proveedor,
)

# ── Constants ───────────────────────────────────────────────────────────

MODULE_SLUG = "supply-proveedores"

_NARANJA = "#E84000"
_VERDE = "#1B6B2F"
_ROJO = "#B71C1C"
_GRIS = "#6B7280"

_SOP_MD = """
Aca se carga el maestro de proveedores: quien es, de donde despacha y en cuanto
tiempo dice que entrega (lead time minimo / tipico / maximo, en dias).

El **LT medido** y el **fill rate** no se cargan a mano: el sistema los calcula
solo a partir de las ordenes de compra, midiendo desde que la OC se emite hasta
la primera recepcion. Hasta que no haya OC registradas van a mostrar "—".

Archivar un proveedor no lo borra: deja de aparecer en las listas, pero su
historial se conserva.
"""

_KEY_ALTA_ABIERTA = "supply_prov_alta_abierta"
_KEY_EDITAR_ABIERTA = "supply_prov_editar_abierta"
_KEY_ARCHIVAR_ABIERTA = "supply_prov_archivar_abierta"
"""Que dialogo esta abierto, anclado en session_state.

NO se abre un dialogo desde `if st.button(...): _dialog(...)`. Ese patron lo deja
vivo un solo run: en el rerun que trae el valor que el usuario acaba de tipear, el
boton ya devuelve False, el dialogo no se re-renderiza, y Streamlit lo marca stale
y BORRA el estado de todos sus widgets — con key o sin key. El sintoma es el modal
que se cierra solo al tocar un input, o el campo editado que vuelve al valor
anterior al confirmar. Anclado en session_state, el dialogo se re-renderiza en cada
run y su estado sobrevive. Mismo mecanismo que supply_ordenes.py.

Las dos banderas de detalle guardan el `prov_id`; la de alta, True."""


# ── Helpers de formato ──────────────────────────────────────────────────
# Todo lo que va a pantalla se convierte a string ACA. Las metricas devuelven
# None cuando no hay muestras y ningun None debe llegar a un widget.


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


def _fmt_lt_declarado(prov: dict) -> str:
    """Los tres lead times del maestro en una celda: '7 / 10 / 14 d'.

    Un tramo sin cargar se muestra como '·'. Si no hay ninguno, '—'.
    """
    partes = [_fmt_num(prov.get(k)) for k in ("lt_min", "lt_tip", "lt_max")]
    if not any(partes):
        return "—"
    return " / ".join(p or "·" for p in partes) + " d"


def _fmt_lt_medido(lt_medido, lt_tip) -> tuple[str, str, str]:
    """Lead time real + su desvio contra el declarado.

    Returns:
        (texto, delta, color) — listos para pintar. Sin datos: ('—', '', gris).
    """
    if lt_medido is None:
        return "—", "", _GRIS

    texto = f"{_fmt_num(lt_medido)} d"

    try:
        tip = float(lt_tip)
    except (TypeError, ValueError):
        return texto, "", _NARANJA

    delta = float(lt_medido) - tip
    if abs(delta) < 0.5:
        return texto, "en linea", _VERDE
    signo = "+" if delta > 0 else ""
    # Tardar mas de lo declarado es el caso malo; llegar antes, el bueno.
    color = _ROJO if delta > 0 else _VERDE
    return texto, f"{signo}{_fmt_num(delta)} vs {_fmt_num(tip)}", color


def _fmt_fill_rate(fill_rate) -> tuple[str, str]:
    """Fill rate como porcentaje + color de semaforo. Sin datos: ('—', gris)."""
    if fill_rate is None:
        return "—", _GRIS
    pct = float(fill_rate) * 100
    color = _VERDE if pct >= 95 else (_NARANJA if pct >= 80 else _ROJO)
    return f"{pct:.0f}%", color


def _celda(texto: str, color: str = "#1F1F1F", bold: bool = False) -> str:
    peso = "700" if bold else "400"
    return (
        f"<div style='font-size:0.85rem;color:{color};font-weight:{peso};"
        f"padding-top:0.35rem;'>{texto}</div>"
    )


# ── Header y empty state ────────────────────────────────────────────────


def _header() -> None:
    st.markdown("## 🚚 Maestro de Proveedores")
    st.caption(
        "📥 Alta y edicion de proveedores con su lead time declarado · "
        "Output: LT medido y fill rate reales, calculados sobre las ordenes de compra"
    )
    st.divider()


def _empty_state() -> None:
    st.markdown(
        "<div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;"
        " text-align: center; background: #FFF8F0;'>"
        f"<h3 style='color: {_NARANJA}; margin-top: 0;'>📂 Todavia no hay proveedores</h3>"
        "<p style='color: #6B7280; margin: 0;'>"
        "Cargá el primero con el boton <strong>➕ Proveedor nuevo</strong>. "
        "Con los lead times declarados alcanza para empezar."
        "</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Apertura y cierre de dialogos ───────────────────────────────────────


def _abrir(bandera: str, valor=True) -> None:
    """Marca un dialogo como abierto. render() lo renderiza al final del run.

    Baja las otras banderas: Streamlit admite un solo dialogo por script run.
    """
    for otra in (_KEY_ALTA_ABIERTA, _KEY_EDITAR_ABIERTA, _KEY_ARCHIVAR_ABIERTA):
        if otra != bandera:
            st.session_state.pop(otra, None)
    st.session_state[bandera] = valor


def _cerrar_dialogos() -> None:
    """Baja las banderas y refresca. Al no re-renderizarse, el dialogo suelta el
    estado de sus widgets: la proxima apertura arranca limpia."""
    for bandera in (_KEY_ALTA_ABIERTA, _KEY_EDITAR_ABIERTA, _KEY_ARCHIVAR_ABIERTA):
        st.session_state.pop(bandera, None)
    st.rerun()


# ── Dialogos (@st.dialog — nunca st.form) ───────────────────────────────
# Los inputs van con value= y SIN key= a proposito: en 1.43.2, un widget con key
# deja el valor pegado en session_state y el modal de alta reabriria con los
# datos del proveedor anterior. Sin key, cada apertura arranca limpia. Los
# botones si llevan key, para no colisionar entre si.


def _campos_proveedor(prov: dict | None = None) -> dict:
    """Pinta los campos del formulario y devuelve lo cargado.

    Compartido por alta y edicion: `prov` precarga los valores en el editar.
    """
    prov = prov or {}

    nombre = st.text_input(
        "Nombre *",
        value=str(prov.get("nombre") or ""),
        placeholder="Shenzhen Tools",
    )
    pais = st.text_input(
        "Pais",
        value=str(prov.get("pais") or ""),
        placeholder="China",
    )

    st.caption("Lead time declarado por el proveedor, en dias. Dejá 0 si no lo sabés.")
    col_min, col_tip, col_max = st.columns(3)
    lt_min = col_min.number_input(
        "LT minimo", min_value=0, step=1, value=int(float(prov.get("lt_min") or 0))
    )
    lt_tip = col_tip.number_input(
        "LT tipico", min_value=0, step=1, value=int(float(prov.get("lt_tip") or 0))
    )
    lt_max = col_max.number_input(
        "LT maximo", min_value=0, step=1, value=int(float(prov.get("lt_max") or 0))
    )

    revision = st.number_input(
        "Revision (dias)",
        min_value=1,
        step=1,
        value=int(float(prov.get("revision_dias") or 7)),
        help="Cada cuantos dias se revisa si hay que reponer.",
    )

    return {
        "nombre": nombre,
        "pais": pais,
        # 0 significa "no lo sé", no un lead time de cero dias: se guarda como
        # ausente para que el maestro no quede con ceros espurios.
        "lt_min": lt_min or None,
        "lt_tip": lt_tip or None,
        "lt_max": lt_max or None,
        "revision_dias": revision,
    }


def _guardar(datos: dict) -> bool:
    """save_proveedor con el ValueError del persistence traducido a st.error.

    El persistence valida lt_min <= lt_tip <= lt_max y avisa con un mensaje ya
    redactado para el usuario: se muestra tal cual en vez de reventar.

    Returns:
        True si guardo. False si hay que quedarse en el modal.
    """
    if not str(datos.get("nombre") or "").strip():
        st.error("El nombre es obligatorio.")
        return False
    try:
        save_proveedor(datos)
    except ValueError as e:
        st.error(str(e))
        return False
    return True


@st.dialog("Proveedor nuevo")
def _dialog_alta() -> None:
    datos = _campos_proveedor()

    col_cancel, col_ok = st.columns([1, 1])
    if col_cancel.button(
        "Cancelar", key="supply_prov_alta_cancel", use_container_width=True
    ):
        _cerrar_dialogos()
    if col_ok.button(
        "Guardar",
        key="supply_prov_alta_confirm",
        type="primary",
        use_container_width=True,
    ):
        # Si _guardar devuelve False ya pinto el st.error: el dialogo se queda
        # abierto (no se baja la bandera) para poder corregir sin reabrir.
        if _guardar(datos):
            st.success(f"Proveedor '{datos['nombre'].strip()}' guardado.")
            _cerrar_dialogos()


@st.dialog("Editar proveedor")
def _dialog_editar(prov_id: str) -> None:
    prov = get_proveedor(prov_id)
    if prov is None:
        st.error(f"El proveedor '{prov_id}' ya no existe.")
        if st.button(
            "Entendido",
            key=f"supply_prov_edit_inexistente_{prov_id}",
            use_container_width=True,
        ):
            _cerrar_dialogos()
        return

    datos = _campos_proveedor(prov)
    # El id manda el upsert: sin el, save_proveedor crearia uno nuevo desde el
    # slug del nombre. Se preservan tambien los campos que este modal no edita.
    datos = {**prov, **datos, "id": prov["id"]}

    col_cancel, col_ok = st.columns([1, 1])
    if col_cancel.button(
        "Cancelar", key=f"supply_prov_edit_cancel_{prov_id}", use_container_width=True
    ):
        _cerrar_dialogos()
    if col_ok.button(
        "Guardar cambios",
        key=f"supply_prov_edit_confirm_{prov_id}",
        type="primary",
        use_container_width=True,
    ):
        if _guardar(datos):
            st.success("Cambios guardados.")
            _cerrar_dialogos()


@st.dialog("Archivar proveedor")
def _dialog_archivar(prov_id: str) -> None:
    # El nombre se resuelve aca y no se pasa por la bandera: en session_state
    # viaja solo el prov_id, igual que en supply_ordenes.py.
    prov = get_proveedor(prov_id)
    if prov is None:
        st.error(f"El proveedor '{prov_id}' ya no existe.")
        if st.button(
            "Entendido",
            key=f"supply_prov_arch_inexistente_{prov_id}",
            use_container_width=True,
        ):
            _cerrar_dialogos()
        return

    nombre = str(prov.get("nombre") or prov_id)
    st.markdown(f"Vas a archivar **{nombre}**.")
    st.caption(
        "No se borra nada: deja de aparecer en la lista y su historial de ordenes "
        "se conserva. Para volver a verlo, marcá 'Mostrar archivados'."
    )

    col_cancel, col_ok = st.columns([1, 1])
    if col_cancel.button(
        "Cancelar", key=f"supply_prov_arch_cancel_{prov_id}", use_container_width=True
    ):
        _cerrar_dialogos()
    if col_ok.button(
        "Archivar",
        key=f"supply_prov_arch_confirm_{prov_id}",
        type="primary",
        use_container_width=True,
    ):
        if archivar_proveedor(prov_id):
            st.success(f"'{nombre}' archivado.")
        else:
            st.error(f"El proveedor '{prov_id}' ya no existe.")
        _cerrar_dialogos()


# ── Tabla ───────────────────────────────────────────────────────────────
# Filas armadas con st.columns y no con st.dataframe: hacen falta botones de
# accion por fila, que un dataframe no soporta.

_COLS = [2.4, 1.2, 1.5, 1.9, 1.1, 1.0, 0.6, 0.6]


def _fila_header() -> None:
    cols = st.columns(_COLS)
    encabezados = [
        "Proveedor",
        "Pais",
        "LT declarado",
        "LT medido",
        "Fill rate",
        "Revision",
        "",
        "",
    ]
    for col, texto in zip(cols, encabezados):
        col.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:{_GRIS};"
            f"text-transform:uppercase;letter-spacing:0.03em;'>{texto}</div>",
            unsafe_allow_html=True,
        )


def _fila_proveedor(prov: dict) -> None:
    prov_id = str(prov.get("id") or "")
    nombre = str(prov.get("nombre") or prov_id)
    activo = bool(prov.get("activo", True))

    # Las metricas las calcula supply_metrics; aca solo se formatean.
    resumen = resumen_proveedor(prov_id)
    lt_txt, lt_delta, lt_color = _fmt_lt_medido(
        resumen["lt_medido"], prov.get("lt_tip")
    )
    fr_txt, fr_color = _fmt_fill_rate(resumen["fill_rate"])

    c_nom, c_pais, c_ltd, c_ltm, c_fr, c_rev, c_edit, c_arch = st.columns(_COLS)

    etiqueta = nombre if activo else f"{nombre} 🗄️"
    c_nom.markdown(
        _celda(etiqueta, bold=True)
        + f"<div style='font-size:0.68rem;color:{_GRIS};'>"
        f"{resumen['n_ocs']} OC · {resumen['n_ocs_cerradas']} cerradas</div>",
        unsafe_allow_html=True,
    )
    c_pais.markdown(_celda(str(prov.get("pais") or "—")), unsafe_allow_html=True)
    c_ltd.markdown(_celda(_fmt_lt_declarado(prov)), unsafe_allow_html=True)

    medido = _celda(lt_txt, color=lt_color, bold=True)
    if lt_delta:
        medido += (
            f"<div style='font-size:0.68rem;color:{lt_color};'>{lt_delta}</div>"
        )
    c_ltm.markdown(medido, unsafe_allow_html=True)

    c_fr.markdown(_celda(fr_txt, color=fr_color, bold=True), unsafe_allow_html=True)
    rev = _fmt_num(prov.get("revision_dias"))
    c_rev.markdown(_celda(f"{rev} d" if rev else "—"), unsafe_allow_html=True)

    if c_edit.button(
        "✏️", key=f"supply_prov_edit_{prov_id}", help=f"Editar {nombre}"
    ):
        _abrir(_KEY_EDITAR_ABIERTA, prov_id)

    if activo:
        if c_arch.button(
            "🗄️", key=f"supply_prov_arch_{prov_id}", help=f"Archivar {nombre}"
        ):
            _abrir(_KEY_ARCHIVAR_ABIERTA, prov_id)
    else:
        c_arch.markdown(
            f"<div style='font-size:0.68rem;color:{_GRIS};padding-top:0.5rem;'>"
            f"archivado</div>",
            unsafe_allow_html=True,
        )


# ── Render principal ────────────────────────────────────────────────────


def render() -> None:
    """Punto de entrada del modulo. Llamado desde app.py.

    Sin early-return: el despacho de dialogos del final tiene que correr siempre,
    incluso con la lista vacia — es justo cuando se da de alta el primero.
    """
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    col_add, col_ver, _ = st.columns([2, 2, 4])
    if col_add.button(
        "➕ Proveedor nuevo", key="supply_prov_btn_alta", use_container_width=True
    ):
        _abrir(_KEY_ALTA_ABIERTA)
    ver_inactivos = col_ver.checkbox(
        "Mostrar archivados",
        key="supply_prov_ver_inactivos",
        help="Incluye en la lista los proveedores archivados.",
    )

    proveedores = list_proveedores(incluir_inactivos=ver_inactivos)

    st.divider()

    if not proveedores:
        _empty_state()
    else:
        activos = sum(1 for p in proveedores if p.get("activo", True))
        resumen_txt = f"{activos} proveedor{'es' if activos != 1 else ''} activo"
        if ver_inactivos and len(proveedores) > activos:
            resumen_txt += f" · {len(proveedores) - activos} archivado"
        st.caption(resumen_txt)

        _fila_header()
        for prov in proveedores:
            _fila_proveedor(prov)

        st.divider()
        st.caption(
            "El **LT medido** sale de las ordenes de compra: se mide desde que la OC "
            "se emite hasta la primera recepcion. Mientras no haya OC registradas, "
            "esa columna y el fill rate muestran «—»."
        )

    # Los dialogos se renderizan al FINAL y desde session_state, no desde el
    # `if boton:` que los abre. Va ultimo para que el click en «✏️» de una fila
    # ya se vea reflejado en este mismo run. Sin early-return arriba: el alta
    # tiene que seguir viva aunque la lista este vacia.
    if st.session_state.get(_KEY_ALTA_ABIERTA):
        _dialog_alta()
    elif prov_editar := st.session_state.get(_KEY_EDITAR_ABIERTA):
        # Streamlit admite un solo dialogo por run; el elif lo garantiza.
        _dialog_editar(str(prov_editar))
    elif prov_archivar := st.session_state.get(_KEY_ARCHIVAR_ABIERTA):
        _dialog_archivar(str(prov_archivar))
