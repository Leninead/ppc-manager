"""Proposal Studio (M29) — Sesión 2 skeleton.

Módulo de la sección Sales Director del Agency OS. Permite crear y gestionar
propuestas comerciales para leads/prospects usando el catálogo de 37 módulos
(8 FIXED + 29 VARIABLE) y los 4 arquetipos (launch / scale_seo / defense / cvr).

Estado actual (Sesión 2):
- Skeleton con 2 tabs (Listado + Nueva propuesta)
- Sin lógica de storage todavía (placeholders st.info)
- Sin renderer HTML/PDF (eso es S5/S6)

Próximas sesiones:
- S3: 6 CORE Variables funcionales (V1-V6)
- S4: 23 placeholders Tier 2-3 + toggle "Marcar como interesado"
- S5: Templates Jinja2 + renderer HTML
- S6: Playwright PDF + polish

Ver:
- data/_schemas/proposal-v1.json (schema canónico)
- data/sales/_catalog.json (37 módulos)
- data/sales/_templates/ (4 arquetipos)
- core/proposal_persistence.py (capa de I/O)
- notes/brands/agency-os.md (contexto de negocio)
"""

from __future__ import annotations

import json
import streamlit as st
from datetime import datetime, timezone
import core.proposal_persistence as pp
from modules.sales.b7_importer import extract_blocks, merge_blocks

# ─────────────────────────────────────────────────────────────────────────────
# Constantes UI
# ─────────────────────────────────────────────────────────────────────────────

_NARANJA = "#E84000"
_NEGRO = "#1F1F1F"
_GRIS_TXT = "#888888"

# Arquetipos disponibles (coherente con data/sales/_templates/)
_ARQUETIPOS = {
    "launch": {
        "label": "Launch",
        "descripcion": "Marca/ASIN nuevo en Amazon. Foco: setup + ramp inicial.",
        "color": "#2196F3",
    },
    "scale_seo": {
        "label": "Scale + SEO",
        "descripcion": "Marca establecida buscando crecer share orgánico.",
        "color": "#FF9800",
    },
    "defense": {
        "label": "Defense",
        "descripcion": "Protección de brand terms + competidores agresivos.",
        "color": "#9C27B0",
    },
    "cvr": {
        "label": "CVR Optimization",
        "descripcion": "Tráfico OK, conversión deficiente. Foco: listing + creative.",
        "color": "#4CAF50",
    },
}

# Status -> (label, color) para badges
_STATUS_META = {
    "draft":             ("📝 Borrador",     "#9E9E9E"),
    "ready_for_review":  ("👀 En revisión",  "#FF9800"),
    "sent":              ("📤 Enviada",      "#2196F3"),
    "won":               ("🏆 Ganada",       "#4CAF50"),
    "lost":              ("❌ Perdida",      "#F44336"),
    "archived":          ("🗄️ Archivada",   "#757575"),
}

# Mapping para mostrar idioma como bandera
_LANG_META = {"en": "🇺🇸 EN", "es": "🇪🇸 ES"}

# Tier metadata para el preview del paso 2
_TIER_META = {
    "fixed": {
        "label": "FIXED",
        "subtitle": "Aparecen en TODAS las propuestas",
        "color": "#E84000",
        "order": 1,
    },
    "core_variable": {
        "label": "CORE",
        "subtitle": "Backbone de cualquier pitch (4-5 de cada 5)",
        "color": "#FF9800",
        "order": 2,
    },
    "common_variable": {
        "label": "COMMON",
        "subtitle": "PPC audit / forecast / casos (2-3 de cada 5)",
        "color": "#2196F3",
        "order": 3,
    },
    "specialized_variable": {
        "label": "SPECIALIZED",
        "subtitle": "Específicos de cliente o proyecto (1 de cada 5)",
        "color": "#9C27B0",
        "order": 4,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers UI
# ─────────────────────────────────────────────────────────────────────────────


def _render_header() -> None:
    """Header del módulo con título + descripción + badge versión."""
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:1rem;margin-bottom:0.25rem;'>"
        f"<span style='font-size:2rem;'>📋</span>"
        f"<div>"
        f"<div style='font-size:1.5rem;font-weight:800;color:{_NEGRO};'>Proposal Studio</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};'>"
        f"Generador de propuestas comerciales — Sales Director module</div>"
        f"</div>"
        f"<div style='margin-left:auto;background:#1A1A1A;color:{_NARANJA};"
        f"padding:0.4rem 0.8rem;border-radius:8px;font-weight:700;font-size:0.85rem;'>"
        f"M29 · Sesión 2 (skeleton)</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _format_relative_time(iso_str: str) -> str:
    """Convierte ISO 8601 a tiempo relativo legible (ej: 'hace 3h', 'ayer', '12 May')."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        secs = delta.total_seconds()
        if secs < 60:
            return "ahora"
        if secs < 3600:
            return f"hace {int(secs // 60)}m"
        if secs < 86400:
            return f"hace {int(secs // 3600)}h"
        if secs < 172800:
            return "ayer"
        if secs < 604800:
            return f"hace {int(secs // 86400)}d"
        return dt.strftime("%d %b").replace(".", "")
    except (ValueError, AttributeError):
        return iso_str or "—"


@st.cache_data(ttl=300, show_spinner=False)
def _load_catalog_cached() -> dict:
    """Lee el catálogo con cache de 5 minutos. Usado en paso 2 del wizard."""
    return pp.load_catalog()


def _catalog_module_lookup() -> dict[str, dict]:
    """Devuelve {module_id: module_def_completo} para lookup en el paso 2."""
    catalog = _load_catalog_cached()
    return {m["module_id"]: m for m in catalog.get("modules", [])}


def _step1_data_signature() -> tuple:
    """Tupla hashable de los inputs del paso 1 — usada para detectar cambios."""
    d = st.session_state.get("ps_wizard_data", {})
    return (
        d.get("client_name", ""),
        d.get("archetype", ""),
        d.get("language", ""),
        d.get("sales_director", ""),
    )


def _ensure_draft_synced() -> dict | None:
    """Instancia (o re-instancia si cambió input) el draft de Proposal en memoria.

    Returns: el dict Proposal en memoria, o None si los datos del paso 1 están incompletos.
    """
    data = st.session_state.get("ps_wizard_data", {})
    if not all([
        data.get("client_name"),
        data.get("archetype"),
        data.get("language"),
        data.get("sales_director"),
    ]):
        return None

    current_sig = _step1_data_signature()
    cached_sig = st.session_state.get("ps_wizard_draft_signature")
    cached_draft = st.session_state.get("ps_wizard_proposal_draft")

    if cached_draft is not None and cached_sig == current_sig:
        return cached_draft

    # Re-instanciar
    try:
        draft = pp.instantiate_proposal_from_template(
            archetype=data["archetype"],
            client_name=data["client_name"],
            language=data["language"],
            sales_director=data["sales_director"],
        )
    except ValueError as e:
        st.error(f"❌ Error al pre-cargar template: {e}")
        return None

    # Setear industry desde el form (instantiate no lo recibe)
    if data.get("client_industry"):
        draft["client_industry"] = data["client_industry"]

    st.session_state["ps_wizard_proposal_draft"] = draft
    st.session_state["ps_wizard_draft_signature"] = current_sig
    return draft


def _render_empty_state() -> None:
    """Empty state cuando no hay propuestas."""
    st.markdown(
        f"<div style='border:2px dashed #FFD9B3;border-radius:12px;"
        f"padding:3rem 2rem;text-align:center;background:#FFF8F0;margin-top:1rem;'>"
        f"<div style='font-size:3rem;margin-bottom:0.5rem;'>📋</div>"
        f"<div style='font-size:1.1rem;font-weight:700;color:{_NEGRO};margin-bottom:0.4rem;'>"
        f"Todavía no hay propuestas guardadas</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};margin-bottom:1.2rem;'>"
        f"Creá tu primera propuesta desde el tab <strong>✨ Nueva propuesta</strong></div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_proposal_row_actions(proposal: dict) -> None:
    """Acciones por propuesta seleccionada (abrir, duplicar, archivar)."""
    pid = proposal["id"]
    pversion = proposal["version"]
    cliente = proposal["client_name"]

    col_open, col_dup, col_arch = st.columns([1, 1, 1])

    with col_open:
        if st.button("🔎 Abrir", key=f"open_{pid}", use_container_width=True):
            _open_detail(pid)
            st.rerun()

    with col_dup:
        if st.button("📋 Duplicar", key=f"dup_{pid}", use_container_width=True):
            try:
                import uuid as _uuid
                # Generar proposal_id nuevo PRIMERO para mantener consistencia FK
                new_proposal_id = str(_uuid.uuid4())
                duplicate = dict(proposal)
                duplicate["id"] = new_proposal_id
                duplicate["client_name"] = f"{cliente} (copia)"
                duplicate["status"] = "draft"
                duplicate["created_at"] = ""  # save_proposal lo setea
                # Regenerar block.id (UUID nuevo) Y reasignar block.proposal_id al nuevo padre.
                # Ambos cambios en una sola pasada para que el validator FK pase al primer save.
                duplicate["blocks"] = [
                    {
                        **b,
                        "id": str(_uuid.uuid4()),
                        "proposal_id": new_proposal_id,
                    }
                    for b in proposal.get("blocks", [])
                ]
                saved = pp.save_proposal(duplicate)
                st.success(f"✅ Duplicada como '{saved['client_name']}' (v{saved['version']})")
                st.rerun()
            except ValueError as e:
                # Errores de validación del schema
                st.error(f"❌ La copia no pasó validación: {e}")
            except Exception as e:
                st.error(f"❌ Error al duplicar: {type(e).__name__}: {e}")

    with col_arch:
        confirm_key = f"confirm_arch_{pid}"
        if proposal["status"] == "archived":
            st.button("Ya archivada", key=f"arch_disabled_{pid}",
                      disabled=True, use_container_width=True)
        else:
            if st.session_state.get(confirm_key):
                if st.button("⚠️ Confirmar archivar", key=f"arch_{pid}",
                             use_container_width=True, type="primary"):
                    try:
                        ok = pp.delete_proposal(pid, hard_delete=False)
                        if ok:
                            st.success(f"✅ Archivada: {cliente}")
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                        else:
                            st.error("❌ No se pudo archivar")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
            else:
                if st.button("🗄️ Archivar", key=f"arch_pre_{pid}", use_container_width=True):
                    st.session_state[confirm_key] = True
                    st.rerun()


def _tab_listado() -> None:
    """Tab 1 — Listado de propuestas existentes."""
    # Banner verde si venimos de un save exitoso (consume el flag)
    just_saved = st.session_state.pop("ps_just_saved", None)
    if just_saved:
        st.success(
            f"✅ Propuesta creada: **{just_saved['client_name']}** "
            f"(arquetipo `{just_saved['archetype']}`, v{just_saved['version']})"
        )

    st.markdown("### Mis propuestas")

    # Cargar todas (sin filtros server-side todavía)
    try:
        all_proposals = pp.list_proposals()
    except Exception as e:
        st.error(f"❌ Error al cargar propuestas: {e}")
        return

    if not all_proposals:
        _render_empty_state()
        return

    # ── Filtros ────────────────────────────────────────────────────────────
    col_search, col_arq, col_status = st.columns([2, 1, 1])

    with col_search:
        search_text = st.text_input(
            "🔍 Buscar por cliente",
            value="",
            placeholder="Ej: Garland Rug",
            key="ps_search_client",
        )

    archetype_options = ["Todos"] + list(_ARQUETIPOS.keys()) + ["custom"]
    with col_arq:
        sel_arquetipo = st.selectbox(
            "Arquetipo",
            options=archetype_options,
            index=0,
            key="ps_filter_archetype",
        )

    status_options = ["Todos"] + list(_STATUS_META.keys())
    with col_status:
        sel_status = st.selectbox(
            "Status",
            options=status_options,
            index=0,
            key="ps_filter_status",
            format_func=lambda s: _STATUS_META[s][0] if s in _STATUS_META else s,
        )

    # ── Aplicar filtros client-side ───────────────────────────────────────
    filtered = all_proposals
    if search_text:
        st_lower = search_text.lower()
        filtered = [p for p in filtered if st_lower in p.get("client_name", "").lower()]
    if sel_arquetipo != "Todos":
        filtered = [p for p in filtered if p.get("archetype") == sel_arquetipo]
    if sel_status != "Todos":
        filtered = [p for p in filtered if p.get("status") == sel_status]

    # ── Resumen ────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:0.8rem;color:{_GRIS_TXT};margin:0.5rem 0;'>"
        f"Mostrando <strong>{len(filtered)}</strong> de <strong>{len(all_proposals)}</strong> propuestas"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("Ningún resultado con esos filtros. Probá relajar la búsqueda.")
        return

    # ── Render filas como cards (no st.dataframe — necesitamos botones) ──
    for prop in filtered:
        pid = prop["id"]
        cliente = prop.get("client_name", "—")
        version = prop.get("version", 1)
        archetype = prop.get("archetype", "—")
        language = prop.get("language", "—")
        status = prop.get("status", "draft")
        updated = prop.get("updated_at", "")
        created_by = prop.get("created_by", "—")
        block_count = len(prop.get("blocks", []))

        arq_color = _ARQUETIPOS.get(archetype, {}).get("color", "#9E9E9E")
        arq_label = _ARQUETIPOS.get(archetype, {}).get("label", archetype)
        status_label, status_color = _STATUS_META.get(status, (status, "#9E9E9E"))
        lang_label = _LANG_META.get(language, language)

        with st.container(border=True):
            col_info, col_meta = st.columns([3, 1])

            with col_info:
                st.markdown(
                    f"<div style='font-weight:700;font-size:1.1rem;color:{_NEGRO};margin-bottom:0.3rem;'>"
                    f"{cliente}"
                    f"<span style='font-size:0.7rem;color:{_GRIS_TXT};font-weight:400;margin-left:0.5rem;'>"
                    f"v{version}</span></div>"
                    f"<div style='display:flex;gap:0.4rem;flex-wrap:wrap;align-items:center;margin-bottom:0.3rem;'>"
                    f"<span style='background:{arq_color}15;color:{arq_color};border:1px solid {arq_color};"
                    f"font-size:0.7rem;padding:2px 8px;border-radius:4px;font-weight:600;'>{arq_label}</span>"
                    f"<span style='background:{status_color}15;color:{status_color};border:1px solid {status_color};"
                    f"font-size:0.7rem;padding:2px 8px;border-radius:4px;font-weight:600;'>{status_label}</span>"
                    f"<span style='font-size:0.7rem;color:{_GRIS_TXT};'>{lang_label}</span>"
                    f"<span style='font-size:0.7rem;color:{_GRIS_TXT};'>{block_count} bloques</span>"
                    f"</div>"
                    f"<div style='font-size:0.72rem;color:{_GRIS_TXT};'>"
                    f"Editada {_format_relative_time(updated)} · por {created_by}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with col_meta:
                st.markdown(
                    f"<div style='font-size:0.7rem;color:{_GRIS_TXT};text-align:right;'>"
                    f"id: <code>{pid[:8]}...</code></div>",
                    unsafe_allow_html=True,
                )

            _render_proposal_row_actions(prop)


def _init_wizard_state() -> None:
    """Inicializa keys de session_state del wizard si no existen. Idempotente."""
    if "ps_wizard_active" not in st.session_state:
        st.session_state["ps_wizard_active"] = False
    if "ps_wizard_step" not in st.session_state:
        st.session_state["ps_wizard_step"] = 1
    if "ps_wizard_data" not in st.session_state:
        st.session_state["ps_wizard_data"] = {}


def _reset_wizard() -> None:
    """Resetea el wizard al estado inicial (no-activo, paso 1, sin data ni draft)."""
    st.session_state["ps_wizard_active"] = False
    st.session_state["ps_wizard_step"] = 1
    st.session_state["ps_wizard_data"] = {}
    st.session_state.pop("ps_wizard_proposal_draft", None)
    st.session_state.pop("ps_wizard_draft_signature", None)


def _start_wizard() -> None:
    """Activa el wizard en el paso 1, con data y draft limpios."""
    st.session_state["ps_wizard_active"] = True
    st.session_state["ps_wizard_step"] = 1
    st.session_state["ps_wizard_data"] = {}
    st.session_state.pop("ps_wizard_proposal_draft", None)
    st.session_state.pop("ps_wizard_draft_signature", None)


def _go_to_step(step: int) -> None:
    """Navega a un paso específico del wizard (1, 2 o 3). Sin validación de datos."""
    if step in (1, 2, 3):
        st.session_state["ps_wizard_step"] = step


# ─────────────────────────────────────────────────────────────────────────────
# Vista Detalle (S3) — state machine
# ─────────────────────────────────────────────────────────────────────────────


def _init_detail_state() -> None:
    """Inicializa keys de session_state de la vista detalle. Idempotente."""
    if "ps_detail_active" not in st.session_state:
        st.session_state["ps_detail_active"] = None
    if "ps_detail_buffer" not in st.session_state:
        st.session_state["ps_detail_buffer"] = {}


def _open_detail(proposal_id: str) -> None:
    """Activa la vista detalle para una propuesta. Resetea el buffer de edits."""
    # Plan D: si había otra propuesta abierta, invalidar su buffer antes del switch
    old_pid = st.session_state.get("ps_detail_active")
    if old_pid and old_pid != proposal_id:
        _invalidate_proposal_buffer(old_pid)
    st.session_state["ps_detail_active"] = proposal_id
    st.session_state["ps_detail_buffer"] = {}


def _close_detail() -> None:
    """Cierra la vista detalle y descarta cambios en buffer."""
    # Plan D: invalidar buffer de la propuesta que se cierra
    pid = st.session_state.get("ps_detail_active")
    if pid:
        _invalidate_proposal_buffer(pid)
    st.session_state["ps_detail_active"] = None
    st.session_state["ps_detail_buffer"] = {}


def _is_detail_active() -> bool:
    """True si hay una propuesta abierta en vista detalle."""
    return st.session_state.get("ps_detail_active") is not None


def _render_wizard_progress() -> None:
    """Progress bar visual del wizard — 3 dots con highlight del paso actual."""
    current = st.session_state.get("ps_wizard_step", 1)
    steps = [
        (1, "Cliente + arquetipo"),
        (2, "Pre-fill desde template"),
        (3, "Review + guardar"),
    ]

    parts = []
    for n, label in steps:
        is_current = n == current
        is_done = n < current
        if is_done:
            bg, fg, border = "#4CAF50", "#FFFFFF", "#4CAF50"
            dot = "✓"
        elif is_current:
            bg, fg, border = _NARANJA, "#FFFFFF", _NARANJA
            dot = str(n)
        else:
            bg, fg, border = "#FFFFFF", _GRIS_TXT, "#DDDDDD"
            dot = str(n)

        parts.append(
            f"<div style='display:flex;align-items:center;gap:0.5rem;'>"
            f"<div style='width:32px;height:32px;border-radius:50%;background:{bg};"
            f"color:{fg};border:2px solid {border};display:flex;align-items:center;"
            f"justify-content:center;font-weight:700;font-size:0.85rem;'>{dot}</div>"
            f"<div style='font-size:0.8rem;color:{_NEGRO if is_current else _GRIS_TXT};"
            f"font-weight:{'700' if is_current else '500'};'>{label}</div>"
            f"</div>"
        )

    connector = (
        f"<div style='flex:1;height:2px;background:#DDDDDD;margin:0 0.5rem;'></div>"
    )
    html = (
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"padding:1rem;background:#FAFAFA;border-radius:8px;margin-bottom:1.5rem;'>"
        + connector.join(parts)
        + f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _step1_missing_fields() -> list[str]:
    """Devuelve la lista de campos obligatorios faltantes en el paso 1."""
    data = st.session_state.get("ps_wizard_data", {})
    missing = []
    if not (data.get("client_name") or "").strip():
        missing.append("cliente")
    if not data.get("archetype"):
        missing.append("arquetipo")
    if not data.get("language"):
        missing.append("idioma")
    if not (data.get("sales_director") or "").strip():
        missing.append("sales director")
    return missing


def _can_advance_from_step(step: int) -> bool:
    """Decide si el botón 'Siguiente' del paso `step` debe estar habilitado."""
    if step == 1:
        return len(_step1_missing_fields()) == 0
    if step == 2:
        draft = st.session_state.get("ps_wizard_proposal_draft")
        return draft is not None and len(draft.get("blocks", [])) > 0
    if step == 3:
        # Step 3 usa "Crear propuesta" en lugar de "Siguiente".
        # Esta función no se llama desde el botón Crear (que usa _can_save_proposal),
        # pero por coherencia devolvemos True si se puede guardar.
        can_save, _ = _can_save_proposal()
        return can_save
    return True


def _can_save_proposal() -> tuple[bool, str]:
    """Decide si el botón 'Crear propuesta' del paso 3 debe estar habilitado.

    Returns: (can_save, reason). Si can_save=False, reason explica por qué.
    """
    draft = st.session_state.get("ps_wizard_proposal_draft")
    if draft is None:
        return False, "El draft no está instanciado. Volvé al paso 2."
    if not draft.get("blocks"):
        return False, "El draft no tiene blocks."
    # Sanity check de campos obligatorios mínimos
    for field in ("client_name", "archetype", "language", "created_by"):
        if not draft.get(field):
            return False, f"Falta campo obligatorio en el draft: {field}"
    return True, ""


def _do_save_proposal() -> None:
    """Acción del botón 'Crear propuesta'. Persiste y setea flag de éxito."""
    draft = st.session_state.get("ps_wizard_proposal_draft")
    if draft is None:
        st.error("❌ No hay draft para guardar. Volvé al paso 2.")
        return

    try:
        saved = pp.save_proposal(draft)
    except ValueError as e:
        # Errores de validación del schema/FK
        st.error(f"❌ La propuesta no pasó validación:\n\n{e}")
        return
    except Exception as e:
        # Errores de I/O, permisos, etc.
        st.error(f"❌ Error al guardar la propuesta: {type(e).__name__}: {e}")
        return

    # Éxito: flag para mostrar banner verde + reset wizard
    st.session_state["ps_just_saved"] = {
        "id": saved["id"],
        "version": saved["version"],
        "client_name": saved["client_name"],
        "archetype": saved["archetype"],
    }
    _reset_wizard()
    st.rerun()


def _render_wizard_step1() -> None:
    """Paso 1 del wizard — Cliente + arquetipo + idioma + Sales Director."""
    st.markdown("#### Paso 1 — Cliente + arquetipo")

    data = st.session_state.get("ps_wizard_data", {})

    # ── Cliente + industria ──────────────────────────────────────────────
    col_cliente, col_industria = st.columns([2, 1])

    with col_cliente:
        client_name = st.text_input(
            "Nombre del cliente *",
            value=data.get("client_name", ""),
            placeholder="Ej: Garland Rug",
            key="ps_step1_client_name",
            help="Razón social o nombre comercial del lead/prospect.",
        )

    with col_industria:
        client_industry = st.text_input(
            "Industria (opcional)",
            value=data.get("client_industry", ""),
            placeholder="Ej: home_goods",
            key="ps_step1_client_industry",
            help="Categoría libre. Sirve para filtros futuros.",
        )

    # ── Arquetipo ────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:0.85rem;color:{_NEGRO};font-weight:600;"
        f"margin-top:1rem;margin-bottom:0.3rem;'>Arquetipo *</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:0.75rem;color:{_GRIS_TXT};margin-bottom:0.5rem;'>"
        f"Define qué template pre-carga los bloques en el paso 2.</div>",
        unsafe_allow_html=True,
    )

    archetype_slugs = list(_ARQUETIPOS.keys())  # launch, scale_seo, defense, cvr
    current_arq = data.get("archetype")
    default_arq_idx = archetype_slugs.index(current_arq) if current_arq in archetype_slugs else None

    archetype = st.radio(
        "Seleccioná un arquetipo",
        options=archetype_slugs,
        index=default_arq_idx,
        format_func=lambda s: _ARQUETIPOS[s]["label"],
        horizontal=True,
        key="ps_step1_archetype",
        label_visibility="collapsed",
    )

    # Mostrar descripción del arquetipo seleccionado (si hay)
    if archetype:
        arq_meta = _ARQUETIPOS[archetype]
        st.markdown(
            f"<div style='border-left:3px solid {arq_meta['color']};"
            f"padding:0.5rem 0.8rem;background:#FAFAFA;border-radius:4px;"
            f"margin-top:0.3rem;font-size:0.8rem;color:#555;'>"
            f"<strong style='color:{arq_meta['color']};'>{arq_meta['label']}:</strong> "
            f"{arq_meta['descripcion']}</div>",
            unsafe_allow_html=True,
        )

    # ── Idioma ───────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:0.85rem;color:{_NEGRO};font-weight:600;"
        f"margin-top:1rem;margin-bottom:0.3rem;'>Idioma del entregable *</div>",
        unsafe_allow_html=True,
    )

    lang_options = ["en", "es"]
    current_lang = data.get("language", "es")
    default_lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 1

    language = st.radio(
        "Idioma",
        options=lang_options,
        index=default_lang_idx,
        format_func=lambda lg: _LANG_META.get(lg, lg),
        horizontal=True,
        key="ps_step1_language",
        label_visibility="collapsed",
    )

    # ── Sales Director ───────────────────────────────────────────────────
    sales_director = st.text_input(
        "Sales Director responsable *",
        value=data.get("sales_director", "Lenin Acosta"),
        placeholder="Ej: Lenin Acosta",
        key="ps_step1_sales_director",
        help="Quién crea la propuesta. Se guarda en created_by.",
    )

    # ── Guardar en session_state inmediatamente (auto-save mientras tipea) ─
    st.session_state["ps_wizard_data"] = {
        **data,
        "client_name": (client_name or "").strip(),
        "client_industry": (client_industry or "").strip(),
        "archetype": archetype,
        "language": language,
        "sales_director": (sales_director or "").strip(),
    }

    # ── Validación visible para el usuario ───────────────────────────────
    missing = _step1_missing_fields()
    if missing:
        st.markdown(
            f"<div style='font-size:0.75rem;color:#F44336;margin-top:0.8rem;'>"
            f"⚠️ Faltan campos obligatorios: {', '.join(missing)}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_wizard_step2() -> None:
    """Paso 2 del wizard — Preview readonly de blocks pre-cargados desde el template."""
    st.markdown("#### Paso 2 — Pre-fill desde template")

    draft = _ensure_draft_synced()
    if draft is None:
        st.warning(
            "⚠️ Los datos del paso 1 están incompletos. Volvé al paso anterior."
        )
        return

    catalog_lookup = _catalog_module_lookup()
    blocks = draft.get("blocks", [])
    language = draft.get("language", "es")
    archetype = draft.get("archetype", "—")

    if not blocks:
        st.error(
            f"❌ El template para archetype='{archetype}' no tiene blocks definidos. "
            f"Esto es un bug en data/sales/_templates/. Reportar."
        )
        return

    # ── KPIs arriba ──────────────────────────────────────────────────────
    tier_counts: dict[str, int] = {}
    unknown_modules: list[str] = []
    for b in blocks:
        mid = b.get("module_id", "")
        mod_def = catalog_lookup.get(mid)
        if mod_def is None:
            unknown_modules.append(mid)
            continue
        tier = mod_def.get("tier", "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    arq_meta = _ARQUETIPOS.get(archetype, {})
    arq_color = arq_meta.get("color", "#9E9E9E")
    arq_label = arq_meta.get("label", archetype)

    st.markdown(
        f"<div style='display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;"
        f"padding:0.8rem;background:#FAFAFA;border-radius:8px;margin-bottom:1rem;'>"
        f"<div style='font-size:0.75rem;color:{_GRIS_TXT};'>Template</div>"
        f"<span style='background:{arq_color}15;color:{arq_color};border:1px solid {arq_color};"
        f"font-size:0.75rem;padding:3px 10px;border-radius:4px;font-weight:700;'>{arq_label}</span>"
        f"<div style='width:1px;height:20px;background:#DDD;'></div>"
        f"<div style='font-size:0.75rem;color:{_GRIS_TXT};'>Total</div>"
        f"<div style='font-size:1rem;font-weight:700;color:{_NEGRO};'>{len(blocks)} blocks</div>"
        + "".join(
            f"<div style='width:1px;height:20px;background:#DDD;'></div>"
            f"<div style='font-size:0.75rem;color:{_GRIS_TXT};'>{_TIER_META.get(t, {}).get('label', t.upper())}</div>"
            f"<div style='font-size:1rem;font-weight:700;color:{_TIER_META.get(t, {}).get('color', '#666')};'>{n}</div>"
            for t, n in sorted(tier_counts.items(), key=lambda kv: _TIER_META.get(kv[0], {}).get('order', 99))
        )
        + f"</div>",
        unsafe_allow_html=True,
    )

    if unknown_modules:
        st.warning(
            f"⚠️ {len(unknown_modules)} module_id(s) del template no existen en el catálogo: "
            f"{', '.join(unknown_modules[:5])}{'...' if len(unknown_modules) > 5 else ''}"
        )

    # ── Agrupar blocks por tier ──────────────────────────────────────────
    blocks_by_tier: dict[str, list[dict]] = {}
    for b in blocks:
        mid = b.get("module_id", "")
        mod_def = catalog_lookup.get(mid)
        if mod_def is None:
            continue
        tier = mod_def.get("tier", "unknown")
        blocks_by_tier.setdefault(tier, []).append((b, mod_def))

    # Render en orden definido por _TIER_META.order
    tier_order = sorted(
        blocks_by_tier.keys(),
        key=lambda t: _TIER_META.get(t, {}).get("order", 99),
    )

    for tier in tier_order:
        tier_meta = _TIER_META.get(tier, {})
        tier_label = tier_meta.get("label", tier.upper())
        tier_color = tier_meta.get("color", "#9E9E9E")
        tier_subtitle = tier_meta.get("subtitle", "")
        items = blocks_by_tier[tier]

        st.markdown(
            f"<div style='display:flex;align-items:baseline;gap:0.5rem;"
            f"margin-top:1.2rem;margin-bottom:0.5rem;'>"
            f"<span style='font-weight:800;color:{tier_color};font-size:0.95rem;'>{tier_label}</span>"
            f"<span style='font-size:0.75rem;color:{_GRIS_TXT};'>"
            f"({len(items)}) {tier_subtitle}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        for b, mod_def in items:
            mid = b.get("module_id", "—")
            title = mod_def.get("title", {}).get(language, mid)
            desc = mod_def.get("description", {}).get(language, "")
            # Truncar descripción larga
            if len(desc) > 160:
                desc = desc[:157] + "..."

            status = mod_def.get("status", "active")
            is_placeholder = status == "placeholder_coming_soon"

            opacity = "0.6" if is_placeholder else "1"
            badge_html = ""
            if is_placeholder:
                badge_html = (
                    f"<span style='background:#FFC107;color:#5D4037;"
                    f"font-size:0.65rem;padding:1px 6px;border-radius:3px;"
                    f"font-weight:700;margin-left:0.4rem;'>⏳ placeholder</span>"
                )

            st.markdown(
                f"<div style='border-left:3px solid {tier_color};padding:0.5rem 0.8rem;"
                f"background:#FFFFFF;border-radius:4px;margin-bottom:0.4rem;"
                f"opacity:{opacity};'>"
                f"<div style='display:flex;align-items:center;justify-content:space-between;"
                f"margin-bottom:0.2rem;'>"
                f"<div style='font-weight:600;font-size:0.85rem;color:{_NEGRO};'>"
                f"{title}{badge_html}</div>"
                f"<div style='font-size:0.65rem;color:{_GRIS_TXT};font-family:monospace;'>"
                f"{mid}</div>"
                f"</div>"
                f"<div style='font-size:0.72rem;color:#555;line-height:1.4;'>{desc}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Footer info ──────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:1rem;padding:0.6rem 0.8rem;background:#FFF8F0;"
        f"border-left:3px solid {_NARANJA};border-radius:4px;font-size:0.75rem;color:#555;'>"
        f"📌 Edición de cada block queda para <strong>Sesión 3</strong> "
        f"(formularios por tipo de bloque). "
        f"Toggle 'Marcar como interesado' para placeholders, <strong>Sesión 4</strong>."
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_wizard_step3() -> None:
    """Paso 3 del wizard — Review + guardar."""
    st.markdown("#### Paso 3 — Review + guardar")

    draft = st.session_state.get("ps_wizard_proposal_draft")
    if draft is None:
        st.warning(
            "⚠️ No hay draft en memoria. Volvé al paso 2 para regenerarlo."
        )
        return

    catalog_lookup = _catalog_module_lookup()
    blocks = draft.get("blocks", [])
    archetype = draft.get("archetype", "—")
    language = draft.get("language", "—")
    client_name = draft.get("client_name", "—")
    client_industry = draft.get("client_industry") or "—"
    created_by = draft.get("created_by", "—")

    # Contar blocks por tier para el resumen
    tier_counts: dict[str, int] = {}
    for b in blocks:
        mod_def = catalog_lookup.get(b.get("module_id", ""))
        if mod_def is None:
            continue
        tier = mod_def.get("tier", "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    arq_meta = _ARQUETIPOS.get(archetype, {})
    arq_color = arq_meta.get("color", "#9E9E9E")
    arq_label = arq_meta.get("label", archetype)
    lang_label = _LANG_META.get(language, language)

    # ── Resumen humano ───────────────────────────────────────────────────
    st.markdown(
        f"<div style='border:2px solid {_NARANJA};border-radius:8px;"
        f"padding:1.2rem;background:#FFFFFF;margin-bottom:1rem;'>"
        f"<div style='font-size:0.7rem;color:{_GRIS_TXT};text-transform:uppercase;"
        f"letter-spacing:0.05em;margin-bottom:0.3rem;'>Propuesta a crear</div>"
        f"<div style='font-size:1.4rem;font-weight:800;color:{_NEGRO};margin-bottom:0.8rem;'>"
        f"{client_name}</div>"
        f"<div style='display:flex;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.8rem;'>"
        f"<span style='background:{arq_color}15;color:{arq_color};border:1px solid {arq_color};"
        f"font-size:0.75rem;padding:3px 10px;border-radius:4px;font-weight:700;'>{arq_label}</span>"
        f"<span style='background:#9E9E9E15;color:#666;border:1px solid #9E9E9E;"
        f"font-size:0.75rem;padding:3px 10px;border-radius:4px;font-weight:600;'>{lang_label}</span>"
        f"<span style='background:#F5F5F5;color:#555;border:1px solid #DDD;"
        f"font-size:0.75rem;padding:3px 10px;border-radius:4px;'>"
        f"Industria: {client_industry}</span>"
        f"</div>"
        f"<div style='display:flex;gap:1.5rem;flex-wrap:wrap;align-items:baseline;"
        f"padding-top:0.5rem;border-top:1px solid #EEE;'>"
        f"<div><span style='font-size:0.7rem;color:{_GRIS_TXT};'>Total blocks:</span> "
        f"<strong style='font-size:1rem;color:{_NEGRO};'>{len(blocks)}</strong></div>"
        + "".join(
            f"<div><span style='font-size:0.7rem;color:{_GRIS_TXT};'>"
            f"{_TIER_META.get(t, {}).get('label', t.upper())}:</span> "
            f"<strong style='color:{_TIER_META.get(t, {}).get('color', '#666')};font-size:1rem;'>{n}</strong></div>"
            for t, n in sorted(tier_counts.items(), key=lambda kv: _TIER_META.get(kv[0], {}).get('order', 99))
        )
        + f"<div style='margin-left:auto;font-size:0.72rem;color:{_GRIS_TXT};'>"
        f"Sales Director: <strong style='color:{_NEGRO};'>{created_by}</strong></div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Info de qué pasa al guardar ──────────────────────────────────────
    st.markdown(
        f"<div style='padding:0.7rem 1rem;background:#FFF8F0;border-left:3px solid {_NARANJA};"
        f"border-radius:4px;font-size:0.8rem;color:#555;margin-bottom:1rem;'>"
        f"<strong>Al guardar:</strong> se persiste como propuesta nueva en "
        f"<code style='font-size:0.75rem;'>data/sales/proposals/</code> con <strong>versión 1</strong> "
        f"y status <code style='font-size:0.75rem;'>draft</code>. "
        f"Vas a poder editarla más adelante (incrementa la versión automáticamente)."
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Expander con JSON crudo (debug / inspección) ─────────────────────
    with st.expander("🔍 Ver JSON crudo del draft", expanded=False):
        st.code(
            json.dumps(draft, indent=2, ensure_ascii=False),
            language="json",
        )

    # ── Aviso si no se puede guardar (defensivo) ─────────────────────────
    can_save, reason = _can_save_proposal()
    if not can_save:
        st.error(f"❌ No se puede guardar: {reason}")


def _render_wizard_nav() -> None:
    """Barra de navegación del wizard: ← Anterior / Cancelar / Siguiente →."""
    current = st.session_state.get("ps_wizard_step", 1)

    col_prev, col_spacer, col_cancel, col_next = st.columns([1, 2, 1, 1])

    with col_prev:
        if current > 1:
            if st.button("← Anterior", key=f"wiz_prev_{current}", use_container_width=True):
                _go_to_step(current - 1)
                st.rerun()
        else:
            # Spacer invisible para mantener alineación
            st.markdown("&nbsp;", unsafe_allow_html=True)

    with col_cancel:
        if st.button("✖ Cancelar", key=f"wiz_cancel_{current}", use_container_width=True):
            _reset_wizard()
            st.rerun()

    with col_next:
        if current < 3:
            can_advance = _can_advance_from_step(current)
            if st.button("Siguiente →", key=f"wiz_next_{current}",
                         use_container_width=True, type="primary",
                         disabled=not can_advance):
                _go_to_step(current + 1)
                st.rerun()
        else:
            # Paso 3: botón "Crear propuesta" real
            can_save, _reason = _can_save_proposal()
            if st.button("💾 Crear propuesta", key=f"wiz_save_{current}",
                         use_container_width=True, type="primary",
                         disabled=not can_save):
                _do_save_proposal()


def _render_wizard_arquetipo_reference() -> None:
    """Cards de referencia de los 4 arquetipos disponibles (cheat sheet visual)."""
    st.markdown("---")
    st.markdown(
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};margin-bottom:0.5rem;'>"
        f"<strong>Arquetipos disponibles</strong> (referencia):"
        f"</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(_ARQUETIPOS))
    for col, (slug, meta) in zip(cols, _ARQUETIPOS.items()):
        with col:
            st.markdown(
                f"<div style='border:2px solid {meta['color']};border-radius:8px;"
                f"padding:0.8rem;background:#FFFFFF;height:100%;'>"
                f"<div style='font-weight:700;color:{meta['color']};font-size:0.95rem;"
                f"margin-bottom:0.4rem;'>{meta['label']}</div>"
                f"<div style='font-size:0.75rem;color:#555;'>{meta['descripcion']}</div>"
                f"<div style='margin-top:0.5rem;font-size:0.7rem;color:{_GRIS_TXT};'>"
                f"slug: <code>{slug}</code></div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _tab_nuevo() -> None:
    """Tab 2 — Wizard de creación de propuesta nueva."""
    _init_wizard_state()

    # Si hay un save reciente sin consumir, mostrar info que sugiere ir al Listado.
    just_saved_peek = st.session_state.get("ps_just_saved")
    if just_saved_peek:
        st.info(
            f"✅ Última propuesta creada: **{just_saved_peek['client_name']}**. "
            f"Andá al tab <strong>📋 Mis propuestas</strong> para verla."
            ,
        )

    # Landing: el wizard no está activo todavía → mostrar CTA + cards de arquetipos
    if not st.session_state.get("ps_wizard_active", False):
        st.markdown("### Crear propuesta nueva")
        st.markdown(
            f"<div style='font-size:0.9rem;color:#555;margin-bottom:1rem;'>"
            f"El wizard te guía en 3 pasos: elegís cliente + arquetipo, "
            f"revisás los bloques pre-cargados, y guardás la propuesta nueva."
            f"</div>",
            unsafe_allow_html=True,
        )

        col_cta, _ = st.columns([1, 3])
        with col_cta:
            if st.button("✨ Empezar nueva propuesta", key="wiz_start",
                         use_container_width=True, type="primary"):
                _start_wizard()
                st.rerun()

        _render_wizard_arquetipo_reference()
        return

    # Wizard activo: progress bar + paso actual + nav
    st.markdown("### Crear propuesta nueva")
    _render_wizard_progress()

    step = st.session_state.get("ps_wizard_step", 1)
    if step == 1:
        _render_wizard_step1()
    elif step == 2:
        _render_wizard_step2()
    elif step == 3:
        _render_wizard_step3()

    st.markdown("---")
    _render_wizard_nav()

    # Debug helper: ver session_state del wizard (colapsado por default)
    with st.expander("🔧 Debug — session_state del wizard", expanded=False):
        st.json({
            "ps_wizard_active": st.session_state.get("ps_wizard_active"),
            "ps_wizard_step": st.session_state.get("ps_wizard_step"),
            "ps_wizard_data": st.session_state.get("ps_wizard_data", {}),
        })


def _render_block_editor(block, proposal, lang):
    """
    Dispatcher. Devuelve True si renderizó un editor (caso en que el
    caller NO debe renderizar la card readonly). Devuelve False si
    el módulo no tiene editor implementado (caller cae a readonly).
    """
    module_id = block.get("module_id")
    if module_id == "V1_brand_overview":
        _render_v1_brand_overview_editor(block, proposal, lang)
        return True
    elif module_id == "V2_category_overview":
        _render_v2_category_overview_editor(block, proposal, lang)
        return True
    elif module_id == "V3_seo_opportunity":
        _render_v3_seo_opportunity_readonly(block, proposal, lang)
        return True
    elif module_id == "V4_listing_improvements_current_state":
        _render_v4_current_state_readonly(block, proposal, lang)
        return True
    elif module_id == "V5_listing_comparison_competitor":
        _render_v5_listing_comparison_readonly(block, proposal, lang)
        return True
    elif module_id == "V6_growth_plan_phases":
        _render_v6_growth_plan_readonly(block, proposal, lang)
        return True
    return False


_V1_MARKETS_CHOICES = ["US", "MX", "CA", "BR", "ES", "DE", "UK", "FR", "IT", "JP", "AU"]

_V1_ACCOUNT_TYPE_CHOICES = ["", "vendor", "seller_fba", "seller_fbm", "hybrid"]

_V1_REVENUE_BAND_CHOICES = [
    "", "0-10k USD", "10k-50k USD", "50k-100k USD",
    "100k-500k USD", "500k-1M USD", "1M+ USD", "N/A",
]

_V1_ACOS_BAND_CHOICES = [
    "", "0-15%", "15-25%", "25-40%", "40-60%", "60%+", "N/A",
]

_V1_MATURITY_CHOICES = ["", "none", "basic", "intermediate", "advanced"]

# V2_category_overview — choices hardcoded (paradigma discovery-PPC, coherente con V1)
_V2_CATEGORY_SIZE_CHOICES       = ["", "<$1M", "$1-10M", "$10-100M", "$100M+", "N/A"]
_V2_COMPETITION_DENSITY_CHOICES = ["", "low", "medium", "high", "saturated"]
_V2_PRICE_BAND_CHOICES          = ["", "<$10", "$10-25", "$25-50", "$50-100", "$100+", "N/A"]
_V2_REVIEWS_BAND_CHOICES        = ["", "<100", "100-500", "500-2k", "2k+", "N/A"]


def _render_v1_brand_overview_editor(block, proposal, lang):
    """
    B3-b Plan D: editor de V1_brand_overview basado en buffer mutable en
    session_state. Sin st.form, sin widget keys, sin setdefault adyacente.

    Patrón:
      1. _ensure_block_buffer hidrata el sub-dict del block (lazy, una vez).
      2. Cada widget recibe value=<lectura del buffer> SIN key=.
      3. El retorno del widget se asigna inmediatamente de vuelta al buffer.
      4. Click Guardar → _commit_v1_to_disk + invalidate del sub-dict.
      5. Click Descartar → invalidate del sub-dict.
    """
    import streamlit as st

    buf_block = _ensure_block_buffer(proposal, block, lang)
    bd = buf_block["data"]
    bc = buf_block["copy_overrides"][lang]
    bid = block["id"]

    st.markdown("### 📝 V1 Brand Overview")
    st.caption(f"Idioma de la propuesta: {lang}")

    # === Sección 1: Identificación de marca ===
    st.markdown("**Identificación**")
    col1, col2 = st.columns(2)
    with col1:
        v = st.text_input("Nombre de marca", value=bd["brand_name"])
        bd["brand_name"] = v
    with col2:
        v = st.number_input(
            "Cantidad de SKUs",
            min_value=0,
            step=1,
            value=int(bd.get("sku_count") or 0),
        )
        bd["sku_count"] = v

    v = st.text_area(
        "Categorías (una por línea)",
        value=bd["_raw_categories"],
        height=80,
    )
    bd["_raw_categories"] = v

    v = st.multiselect(
        "Mercados",
        options=_V1_MARKETS_CHOICES,
        default=[m for m in bd["markets"] if m in _V1_MARKETS_CHOICES],
    )
    bd["markets"] = list(v)

    # === Sección 2: Setup técnico Amazon ===
    st.markdown("**Setup Amazon**")
    col3, col4 = st.columns(2)
    with col3:
        _curr = bd["amazon_account_type"] if bd["amazon_account_type"] in _V1_ACCOUNT_TYPE_CHOICES else ""
        v = st.selectbox(
            "Tipo de cuenta",
            options=_V1_ACCOUNT_TYPE_CHOICES,
            index=_V1_ACCOUNT_TYPE_CHOICES.index(_curr),
        )
        bd["amazon_account_type"] = v
    with col4:
        _curr = bd["ppc_maturity"] if bd["ppc_maturity"] in _V1_MATURITY_CHOICES else ""
        v = st.selectbox(
            "Madurez PPC",
            options=_V1_MATURITY_CHOICES,
            index=_V1_MATURITY_CHOICES.index(_curr),
        )
        bd["ppc_maturity"] = v

    v = st.text_area(
        "Hero ASINs (uno por línea)",
        value=bd["_raw_hero_asins"],
        height=80,
    )
    bd["_raw_hero_asins"] = v

    # === Sección 3: Bandas financieras ===
    st.markdown("**Bandas financieras**")
    col5, col6 = st.columns(2)
    with col5:
        _curr = bd["monthly_revenue_band"] if bd["monthly_revenue_band"] in _V1_REVENUE_BAND_CHOICES else ""
        v = st.selectbox(
            "Ingresos mensuales (banda)",
            options=_V1_REVENUE_BAND_CHOICES,
            index=_V1_REVENUE_BAND_CHOICES.index(_curr),
        )
        bd["monthly_revenue_band"] = v
    with col6:
        _curr = bd["current_acos_band"] if bd["current_acos_band"] in _V1_ACOS_BAND_CHOICES else ""
        v = st.selectbox(
            "ACoS actual (banda)",
            options=_V1_ACOS_BAND_CHOICES,
            index=_V1_ACOS_BAND_CHOICES.index(_curr),
        )
        bd["current_acos_band"] = v

    # === Sección 4: Copy editable (i18n) ===
    st.markdown(f"**Copy editorial — idioma {lang}**")

    v = st.text_area("Descripción de marca", value=bc["brand_description"], height=100)
    bc["brand_description"] = v
    v = st.text_area("Posicionamiento", value=bc["positioning"], height=80)
    bc["positioning"] = v
    v = st.text_area("Objetivos del cliente", value=bc["goals"], height=80)
    bc["goals"] = v
    v = st.text_area("Restricciones / no-gos", value=bc["constraints"], height=80)
    bc["constraints"] = v

    st.divider()
    col_save, col_discard, _spacer = st.columns([1, 1, 2])
    with col_save:
        if st.button(
            "💾 Guardar cambios",
            key=f"v1_save_{bid}",
            type="primary",
        ):
            _save_v1_brand_overview(block, proposal, lang)
    with col_discard:
        if st.button(
            "↩️ Descartar cambios",
            key=f"v1_discard_{bid}",
        ):
            _discard_v1_brand_overview(proposal, block)


def _proposal_buffer_key(proposal_id: str) -> str:
    """Key de session_state donde vive el buffer mutable de una propuesta."""
    return f"ps_buffer__{proposal_id}"


def _ensure_block_buffer(proposal: dict, block: dict, lang: str) -> dict:
    """Garantiza que el sub-dict del block existe en el buffer.

    Si no existe, lo hidrata desde block["data"] + block["copy_overrides"][lang].
    Si existe, lo preserva (mantiene edits pendientes del usuario).
    Devuelve referencia mutable al sub-dict.
    """
    import streamlit as st
    pid = proposal["id"]
    bid = block["id"]
    buf_key = _proposal_buffer_key(pid)
    if buf_key not in st.session_state:
        st.session_state[buf_key] = {
            "version": proposal.get("version", 0),
            "blocks": {},
        }
    blocks = st.session_state[buf_key]["blocks"]
    if bid not in blocks:
        data_src = block.get("data") or {}
        overrides_all = block.get("copy_overrides") or {}
        overrides_lang = overrides_all.get(lang) or {}
        blocks[bid] = {
            "data": {
                "brand_name": data_src.get("brand_name", "") or "",
                "sku_count": data_src.get("sku_count"),
                "_raw_categories": "\n".join(data_src.get("categories") or []),
                "markets": list(data_src.get("markets") or []),
                "amazon_account_type": data_src.get("amazon_account_type", "") or "",
                "ppc_maturity": data_src.get("ppc_maturity", "") or "",
                "_raw_hero_asins": "\n".join(data_src.get("hero_asins") or []),
                "monthly_revenue_band": data_src.get("monthly_revenue_band", "") or "",
                "current_acos_band": data_src.get("current_acos_band", "") or "",
            },
            "copy_overrides": {
                lang: {
                    "brand_description": overrides_lang.get("brand_description", ""),
                    "positioning": overrides_lang.get("positioning", ""),
                    "goals": overrides_lang.get("goals", ""),
                    "constraints": overrides_lang.get("constraints", ""),
                },
            },
            "dirty": False,
        }
    return blocks[bid]


def _block_buffer(proposal_id: str, block_id: str):
    """Lee el sub-dict de un block del buffer. None si no existe."""
    import streamlit as st
    buf_key = _proposal_buffer_key(proposal_id)
    buf = st.session_state.get(buf_key)
    if buf is None:
        return None
    return buf.get("blocks", {}).get(block_id)


def _invalidate_block_buffer(proposal_id: str, block_id: str) -> None:
    """Pop selectivo del sub-dict de un block. No toca otros blocks."""
    import streamlit as st
    buf_key = _proposal_buffer_key(proposal_id)
    buf = st.session_state.get(buf_key)
    if buf is None:
        return
    buf.get("blocks", {}).pop(block_id, None)


def _invalidate_proposal_buffer(proposal_id: str) -> None:
    """Pop de la key entera del buffer de una propuesta."""
    import streamlit as st
    st.session_state.pop(_proposal_buffer_key(proposal_id), None)


def _build_v1_payload(buf_block: dict, lang: str):
    """Aplica transformaciones diferidas y devuelve (new_data, new_copy_lang).

    Función pura: no toca disco, no toca session_state, no rerun.
    Reutilizable para skip-save check y para commit.

    Transformaciones:
      - _raw_categories (string multilínea) → categories (lista filtrada, trim)
      - _raw_hero_asins (string multilínea) → hero_asins (lista trim + upper)
      - sku_count: 0 / None / negativos / no-numéricos → None
    """
    buf_data = buf_block["data"]

    raw_cats = buf_data.get("_raw_categories", "") or ""
    categories = [c.strip() for c in raw_cats.split("\n") if c.strip()]

    raw_asins = buf_data.get("_raw_hero_asins", "") or ""
    hero_asins = [a.strip().upper() for a in raw_asins.split("\n") if a.strip()]

    sku_raw = buf_data.get("sku_count")
    if sku_raw is None:
        sku_count = None
    else:
        try:
            sku_int = int(sku_raw)
            sku_count = sku_int if sku_int > 0 else None
        except (TypeError, ValueError):
            sku_count = None

    new_data = {
        "brand_name": (buf_data.get("brand_name", "") or "").strip(),
        "sku_count": sku_count,
        "categories": categories,
        "markets": list(buf_data.get("markets") or []),
        "amazon_account_type": buf_data.get("amazon_account_type", "") or "",
        "ppc_maturity": buf_data.get("ppc_maturity", "") or "",
        "hero_asins": hero_asins,
        "monthly_revenue_band": buf_data.get("monthly_revenue_band", "") or "",
        "current_acos_band": buf_data.get("current_acos_band", "") or "",
    }

    new_copy_lang = dict(buf_block.get("copy_overrides", {}).get(lang, {}))

    return new_data, new_copy_lang


def _v1_payload_matches_disk(buf_block: dict, block: dict, lang: str) -> bool:
    """True si el payload del buffer es idéntico al block actual en disco.

    Compara new_data y new_copy_lang contra block['data'] y
    block['copy_overrides'][lang]. Si todo coincide, no hay nada para guardar.

    Nota: la comparación es estricta con ==. Si en disco hay un dict con
    menos keys que el payload nuevo (caso del primer save sobre un block
    con data={}), devuelve False — queremos escribir aunque los valores
    nuevos sean defaults, porque el shape cambia.
    """
    new_data, new_copy_lang = _build_v1_payload(buf_block, lang)

    disk_data = block.get("data") or {}
    disk_overrides_all = block.get("copy_overrides") or {}
    disk_overrides_lang = disk_overrides_all.get(lang) or {}

    if new_data != disk_data:
        return False
    if new_copy_lang != disk_overrides_lang:
        return False
    return True


def _commit_v1_to_disk(buf_block: dict, proposal: dict, block: dict, lang: str) -> dict:
    """Persiste el sub-dict del buffer V1 al disco vía pp.save_proposal.

    NO toca session_state. NO llama st.rerun. NO llama st.toast.
    Devuelve el dict saved con version bumpeada.
    """
    import copy as _copy
    import core.proposal_persistence as pp

    new_data, new_copy_lang = _build_v1_payload(buf_block, lang)

    cloned = _copy.deepcopy(proposal)
    target_block_id = block["id"]
    mutated = False
    for b in cloned.get("blocks", []):
        if b.get("id") == target_block_id:
            b["data"] = new_data
            current_overrides = b.get("copy_overrides") or {}
            current_overrides[lang] = new_copy_lang
            other_lang = "en" if lang == "es" else "es"
            if other_lang not in current_overrides:
                current_overrides[other_lang] = {
                    "brand_description": "",
                    "positioning": "",
                    "goals": "",
                    "constraints": "",
                }
            b["copy_overrides"] = current_overrides
            mutated = True
            break

    if not mutated:
        raise ValueError(f"Block id={target_block_id} no encontrado en proposal")

    saved = pp.save_proposal(cloned)
    return saved


def _save_v1_brand_overview(block, proposal, lang):
    """Persiste cambios del editor V1 (Plan D: buffer → disco).

    Flow:
      1. Lee buf_block del session_state.
      2. _commit_v1_to_disk aplica transformaciones diferidas y persiste.
      3. Invalida solo el sub-dict del block commiteado (otros blocks sobreviven).
      4. Actualiza version snapshot en el buffer global.
      5. Toast + rerun.
    """
    import streamlit as st

    pid = proposal["id"]
    bid = block["id"]
    buf_block = _block_buffer(pid, bid)
    if buf_block is None:
        st.error("Estado inconsistente: el buffer del bloque V1 no existe. Cambios NO guardados.")
        return

    # Skip-save guard: si el payload del buffer es idéntico al disco,
    # no escribimos una versión nueva idéntica.
    if _v1_payload_matches_disk(buf_block, block, lang):
        st.toast("Sin cambios para guardar", icon="ℹ️")
        _invalidate_block_buffer(pid, bid)
        st.rerun()
        return

    try:
        saved = _commit_v1_to_disk(buf_block, proposal, block, lang)
    except ValueError as e:
        st.error(f"❌ No se pudo guardar: {e}")
        return

    _invalidate_block_buffer(pid, bid)

    # Actualizar version snapshot en el buffer global (si todavía existe)
    buf = st.session_state.get(_proposal_buffer_key(pid))
    if buf is not None:
        buf["version"] = saved.get("version", buf.get("version", 0))

    st.toast(
        f"💾 V1 Brand Overview guardado (v{saved.get('version')})",
        icon="✅",
    )
    st.rerun()


def _discard_v1_brand_overview(proposal, block):
    """Descarta cambios del editor V1 invalidando solo su sub-dict del buffer."""
    import streamlit as st
    _invalidate_block_buffer(proposal["id"], block["id"])
    st.toast("↩️ Cambios descartados", icon="🗑️")
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# B3-c — Editor V2_category_overview (Plan D, fiel al patrón B3-b)
# ─────────────────────────────────────────────────────────────────────────────


def _render_v2_category_overview_editor(block, proposal, lang):
    """
    B3-c Plan D: editor de V2_category_overview basado en buffer mutable en
    session_state. Réplica fiel del patrón V1 (B3-b).

    Patrón:
      1. _ensure_block_buffer_v2 hidrata el sub-dict del block (lazy, una vez).
      2. Cada widget recibe value=<lectura del buffer> SIN key=.
      3. El retorno del widget se asigna inmediatamente de vuelta al buffer.
      4. Click Guardar → _save_v2_category_overview.
      5. Click Descartar → _discard_v2_category_overview.
    """
    import streamlit as st

    buf_block = _ensure_block_buffer_v2(proposal, block, lang)
    bd = buf_block["data"]
    bc = buf_block["copy_overrides"][lang]
    bid = block["id"]

    st.markdown("### 📊 V2 Category Overview")
    st.caption(f"Idioma de la propuesta: {lang}")

    # === Sección 1: Identificación de categoría ===
    st.markdown("**Identificación de categoría**")
    v = st.text_input("Nombre de categoría *", value=bd["category_name"])
    bd["category_name"] = v

    # === Sección 2: Bandas de mercado ===
    st.markdown("**Bandas de mercado**")
    col1, col2 = st.columns(2)
    with col1:
        _curr = bd["category_size_band"] if bd["category_size_band"] in _V2_CATEGORY_SIZE_CHOICES else ""
        v = st.selectbox(
            "Tamaño de mercado",
            options=_V2_CATEGORY_SIZE_CHOICES,
            index=_V2_CATEGORY_SIZE_CHOICES.index(_curr),
        )
        bd["category_size_band"] = v
    with col2:
        _curr = bd["competition_density"] if bd["competition_density"] in _V2_COMPETITION_DENSITY_CHOICES else ""
        v = st.selectbox(
            "Densidad competitiva",
            options=_V2_COMPETITION_DENSITY_CHOICES,
            index=_V2_COMPETITION_DENSITY_CHOICES.index(_curr),
        )
        bd["competition_density"] = v

    col3, col4 = st.columns(2)
    with col3:
        _curr = bd["median_price_band"] if bd["median_price_band"] in _V2_PRICE_BAND_CHOICES else ""
        v = st.selectbox(
            "Banda de precio mediano",
            options=_V2_PRICE_BAND_CHOICES,
            index=_V2_PRICE_BAND_CHOICES.index(_curr),
        )
        bd["median_price_band"] = v
    with col4:
        _curr = bd["median_reviews_band"] if bd["median_reviews_band"] in _V2_REVIEWS_BAND_CHOICES else ""
        v = st.selectbox(
            "Banda de reviews mediano",
            options=_V2_REVIEWS_BAND_CHOICES,
            index=_V2_REVIEWS_BAND_CHOICES.index(_curr),
        )
        bd["median_reviews_band"] = v

    # === Sección 3: Competidores y debilidades ===
    st.markdown("**Competidores y debilidades**")
    v = st.text_area(
        "Top competidores (uno por línea)",
        value=bd["_raw_top_competitors"],
        height=80,
    )
    bd["_raw_top_competitors"] = v

    v = st.text_area(
        "Debilidades de la categoría (una por línea)",
        value=bd["_raw_weaknesses"],
        height=80,
    )
    bd["_raw_weaknesses"] = v

    # === Sección 4: Copy editable (i18n) ===
    st.markdown(f"**Copy editorial — idioma {lang}**")

    v = st.text_area("Resumen de categoría", value=bc["category_summary"], height=100)
    bc["category_summary"] = v
    v = st.text_area("Panorama competitivo", value=bc["competitive_landscape"], height=80)
    bc["competitive_landscape"] = v
    v = st.text_area("Oportunidades clave", value=bc["key_opportunities"], height=80)
    bc["key_opportunities"] = v

    st.divider()
    col_save, col_discard, _spacer = st.columns([1, 1, 2])
    with col_save:
        if st.button(
            "💾 Guardar V2",
            key=f"v2_save_{bid}",
            type="primary",
        ):
            _save_v2_category_overview(block, proposal, lang)
    with col_discard:
        if st.button(
            "↩️ Descartar",
            key=f"v2_discard_{bid}",
        ):
            _discard_v2_category_overview(proposal, block)


def _ensure_block_buffer_v2(proposal: dict, block: dict, lang: str) -> dict:
    """Garantiza que el sub-dict del block V2 existe en el buffer.

    Paralelo a _ensure_block_buffer (V1) — defaults distintos por shape.
    Refactor a genérico postponed a B3-d (regla N=3).

    Si no existe, lo hidrata desde block["data"] + block["copy_overrides"][lang].
    Si existe, lo preserva (mantiene edits pendientes del usuario).
    Devuelve referencia mutable al sub-dict.
    """
    import streamlit as st
    pid = proposal["id"]
    bid = block["id"]
    buf_key = _proposal_buffer_key(pid)
    if buf_key not in st.session_state:
        st.session_state[buf_key] = {
            "version": proposal.get("version", 0),
            "blocks": {},
        }
    blocks = st.session_state[buf_key]["blocks"]
    if bid not in blocks:
        data_src = block.get("data") or {}
        overrides_all = block.get("copy_overrides") or {}
        overrides_lang = overrides_all.get(lang) or {}
        blocks[bid] = {
            "data": {
                "category_name": data_src.get("category_name", "") or "",
                "category_size_band": data_src.get("category_size_band", "") or "",
                "competition_density": data_src.get("competition_density", "") or "",
                "median_price_band": data_src.get("median_price_band", "") or "",
                "median_reviews_band": data_src.get("median_reviews_band", "") or "",
                "_raw_top_competitors": "\n".join(data_src.get("top_competitors") or []),
                "_raw_weaknesses": "\n".join(data_src.get("weaknesses") or []),
                "top_competitors": list(data_src.get("top_competitors") or []),
                "weaknesses": list(data_src.get("weaknesses") or []),
            },
            "copy_overrides": {
                lang: {
                    "category_summary": overrides_lang.get("category_summary", ""),
                    "competitive_landscape": overrides_lang.get("competitive_landscape", ""),
                    "key_opportunities": overrides_lang.get("key_opportunities", ""),
                },
            },
            "dirty": False,
        }
    return blocks[bid]


def _build_v2_payload(buf_block: dict, lang: str):
    """Aplica transformaciones diferidas y devuelve (new_data, new_copy_lang).

    Función pura: no toca disco, no toca session_state, no rerun.
    Reutilizable para skip-save check y para commit.

    Transformaciones:
      - _raw_top_competitors (string multilínea) → top_competitors (lista filtrada, trim)
      - _raw_weaknesses      (string multilínea) → weaknesses      (lista filtrada, trim)
      - strings con strip() para evitar whitespace leak
      - NO mete _raw_* en el dict final (son solo de UI)
    """
    buf_data = buf_block["data"]

    raw_competitors = buf_data.get("_raw_top_competitors", "") or ""
    top_competitors = [c.strip() for c in raw_competitors.split("\n") if c.strip()]

    raw_weaknesses = buf_data.get("_raw_weaknesses", "") or ""
    weaknesses = [w.strip() for w in raw_weaknesses.split("\n") if w.strip()]

    new_data = {
        "category_name": (buf_data.get("category_name", "") or "").strip(),
        "category_size_band": buf_data.get("category_size_band", "") or "",
        "competition_density": buf_data.get("competition_density", "") or "",
        "median_price_band": buf_data.get("median_price_band", "") or "",
        "median_reviews_band": buf_data.get("median_reviews_band", "") or "",
        "top_competitors": top_competitors,
        "weaknesses": weaknesses,
    }

    new_copy_lang = dict(buf_block.get("copy_overrides", {}).get(lang, {}))

    return new_data, new_copy_lang


def _v2_payload_matches_disk(buf_block: dict, block: dict, lang: str) -> bool:
    """True si el payload del buffer V2 es idéntico al block actual en disco.

    Compara new_data y new_copy_lang contra block['data'] y
    block['copy_overrides'][lang]. Si todo coincide, no hay nada para guardar.

    Nota: la comparación es estricta con ==. Si en disco hay un dict con
    menos keys que el payload nuevo (caso del primer save sobre un block
    con data={}), devuelve False — queremos escribir aunque los valores
    nuevos sean defaults, porque el shape cambia.
    """
    new_data, new_copy_lang = _build_v2_payload(buf_block, lang)

    disk_data = block.get("data") or {}
    disk_overrides_all = block.get("copy_overrides") or {}
    disk_overrides_lang = disk_overrides_all.get(lang) or {}

    if new_data != disk_data:
        return False
    if new_copy_lang != disk_overrides_lang:
        return False
    return True


def _commit_v2_to_disk(buf_block: dict, proposal: dict, block: dict, lang: str) -> dict:
    """Persiste el sub-dict del buffer V2 al disco vía pp.save_proposal.

    NO toca session_state. NO llama st.rerun. NO llama st.toast.
    Devuelve el dict saved con version bumpeada.
    """
    import copy as _copy
    import core.proposal_persistence as pp

    new_data, new_copy_lang = _build_v2_payload(buf_block, lang)

    cloned = _copy.deepcopy(proposal)
    target_block_id = block["id"]
    mutated = False
    for b in cloned.get("blocks", []):
        if b.get("id") == target_block_id:
            b["data"] = new_data
            current_overrides = b.get("copy_overrides") or {}
            current_overrides[lang] = new_copy_lang
            other_lang = "en" if lang == "es" else "es"
            if other_lang not in current_overrides:
                current_overrides[other_lang] = {
                    "category_summary": "",
                    "competitive_landscape": "",
                    "key_opportunities": "",
                }
            b["copy_overrides"] = current_overrides
            mutated = True
            break

    if not mutated:
        raise ValueError(f"Block id={target_block_id} no encontrado en proposal")

    saved = pp.save_proposal(cloned)
    return saved


def _save_v2_category_overview(block, proposal, lang):
    """Persiste cambios del editor V2 (Plan D: buffer → disco).

    Flow:
      1. Lee buf_block del session_state.
      2. _commit_v2_to_disk aplica transformaciones diferidas y persiste.
      3. Invalida solo el sub-dict del block commiteado (otros blocks sobreviven).
      4. Actualiza version snapshot en el buffer global.
      5. Toast + rerun.
    """
    import streamlit as st

    pid = proposal["id"]
    bid = block["id"]
    buf_block = _block_buffer(pid, bid)
    if buf_block is None:
        st.error("Estado inconsistente: el buffer del bloque V2 no existe. Cambios NO guardados.")
        return

    # Skip-save guard: si el payload del buffer es idéntico al disco,
    # no escribimos una versión nueva idéntica.
    if _v2_payload_matches_disk(buf_block, block, lang):
        st.toast("Sin cambios para guardar", icon="ℹ️")
        _invalidate_block_buffer(pid, bid)
        st.rerun()
        return

    try:
        saved = _commit_v2_to_disk(buf_block, proposal, block, lang)
    except ValueError as e:
        st.error(f"❌ No se pudo guardar: {e}")
        return

    _invalidate_block_buffer(pid, bid)

    # Actualizar version snapshot en el buffer global (si todavía existe)
    buf = st.session_state.get(_proposal_buffer_key(pid))
    if buf is not None:
        buf["version"] = saved.get("version", buf.get("version", 0))

    st.toast(
        f"💾 V2 Category Overview guardado (v{saved.get('version')})",
        icon="✅",
    )
    st.rerun()


def _discard_v2_category_overview(proposal, block):
    """Descarta cambios del editor V2 invalidando solo su sub-dict del buffer."""
    import streamlit as st
    _invalidate_block_buffer(proposal["id"], block["id"])
    st.toast("↩️ Cambios V2 descartados", icon="🗑️")
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# B3-d-bis — Helper compartido de render readonly
# ─────────────────────────────────────────────────────────────────────────────
#
# Bug B3-d-bis (Streamlit 1.43.2): cuando un dict tiene un valor None, pandas
# lo arrastra como NaN/None y al renderizar con st.dataframe la celda muestra
# "None" literal (la serialización Arrow → JSON de Streamlit convierte pd.NA
# a None Python en el bridge al front).
#
# Workaround Opción B (validado 2026-05-19): pre-procesar la lista de dicts
# y reemplazar None por "" (string vacío) ANTES de construir el DataFrame.
# Esto preserva dtype object y deja la celda visualmente vacía sin tocar
# el storage canónico de la propuesta.
#
# Trade-off: para columnas numéricas (ej. current_rank) perdemos el formato
# "18" vs "18.0", pero la columna pasa a object por la mezcla int|str — lo
# cual visualmente muestra "18" porque pandas no aplica float-coerce.


def _none_to_empty_for_render(rows):
    """Reemplaza None por '' en values de cada dict. Preserva dtype object
    para evitar 'None' literal en st.dataframe (workaround Arrow→JSON
    en Streamlit 1.43.2). Aplicar pre-DataFrame.from_records."""
    return [{k: ("" if v is None else v) for k, v in row.items()} for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# B3-d — V3_seo_opportunity (READONLY — viene de importer B7)
# ─────────────────────────────────────────────────────────────────────────────
#
# V3 NO es editor manual. Su schema (arrays de objects con keyword/sv/rank/score)
# está diseñado para ser autohidratado por la skill `amazon-brand-audit` de
# Ramiro vía el módulo importer B7 (HTML drag-drop, pendiente).
#
# Hasta que B7 exista, este renderer muestra:
#  - Banner explicando que la edición manual no aplica
#  - Tabla readonly con missing_keywords si hay data
#  - JSON colapsado para auditoría (launch_score_table, page1_domination_chart_data)
#
# Cuando B7 inyecte data, este renderer la muestra sin tocar nada del flow.


def _render_v3_seo_opportunity_readonly(block, proposal, lang):
    """
    Renderer readonly para V3_seo_opportunity.

    Justificación arquitectónica:
      - Schema V3 = 3 arrays de objects (missing_keywords, launch_score_table,
        page1_domination_chart_data).
      - missing_keywords es required, los otros 2 son optional.
      - V3 NO declara copy_overrides_schema → 0 campos i18n.
      - Caso de uso real: data viene de Data Dive vía skill amazon-brand-audit
        de Ramiro, parseada por importer B7 (drag-drop HTML). No es para tipear
        a mano por un Sales Director.

    Por eso este renderer es READONLY:
      - Banner informativo: edición manual no soportada, viene de B7.
      - Tabla compacta de missing_keywords (si hay data).
      - JSON colapsado para auditoría de los 3 arrays.

    NO usa _ensure_block_buffer ni el patrón Plan D — no hay edits ni save.
    Cuando B7 inyecte data al block via importer, este renderer la rinde tal cual.
    """
    import streamlit as st
    import pandas as pd

    bid = block["id"]
    data = block.get("data") or {}
    missing_kw = data.get("missing_keywords") or []
    launch_score = data.get("launch_score_table") or []
    p1_chart = data.get("page1_domination_chart_data") or []

    st.markdown("### 🔍 V3 SEO Opportunity")
    st.caption(f"Idioma de la propuesta: {lang}")

    # Banner explicativo (siempre visible)
    st.markdown(
        f"<div style='background:#FFF8F0;border-left:3px solid {_NARANJA};"
        f"padding:0.7rem 1rem;border-radius:4px;font-size:0.82rem;"
        f"color:#555;line-height:1.5;margin-bottom:1rem;'>"
        f"⏳ <strong>Edición manual no soportada</strong> — este bloque se popula "
        f"automáticamente vía el importer HTML del módulo <strong>B7</strong> "
        f"(pendiente). Hasta entonces, la data se inyecta directamente al JSON "
        f"de la propuesta vía script o se deja vacío."
        f"</div>",
        unsafe_allow_html=True,
    )

    has_any_data = bool(missing_kw or launch_score or p1_chart)

    if not has_any_data:
        st.info(
            "ℹ️ Sin data poblada en este block. Cuando B7 esté listo, "
            "arrastrá un HTML de Amazon Brand Audit para autollenar."
        )
        return

    # ── Sección 1: missing_keywords como tabla ──────────────────────────────
    if missing_kw:
        st.markdown("**Missing Keywords**")
        st.caption(f"{len(missing_kw)} keywords de alto volumen donde no rankeamos")
        try:
            # Fix B3-d-bis: reemplazar None → "" pre-DataFrame para evitar
            # "None" literal en celdas (Arrow→JSON quirk Streamlit 1.43.2).
            df = pd.DataFrame(_none_to_empty_for_render(missing_kw))
            # Ordenar columnas si vienen con el schema canónico
            canonical_cols = ["keyword", "sv", "current_rank", "opportunity_score"]
            cols_in_df = [c for c in canonical_cols if c in df.columns]
            other_cols = [c for c in df.columns if c not in canonical_cols]
            df = df[cols_in_df + other_cols]
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            # Defensive: si el shape no calza con DataFrame, mostrar JSON
            st.warning(f"⚠️ No se pudo renderizar como tabla: {e}")
            st.json(missing_kw)

    # ── Sección 2: launch_score_table como tabla ────────────────────────────
    if launch_score:
        st.markdown("**Launch Score Table**")
        try:
            # Fix B3-d-bis: mismo workaround None → "" preventivo.
            df_ls = pd.DataFrame(_none_to_empty_for_render(launch_score))
            st.dataframe(df_ls, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"⚠️ No se pudo renderizar como tabla: {e}")
            st.json(launch_score)

    # ── Sección 3: page1_domination_chart_data como JSON colapsado ──────────
    if p1_chart:
        with st.expander(f"Brand Page 1 Domination chart data ({len(p1_chart)} entries)"):
            st.json(p1_chart)


# ─────────────────────────────────────────────────────────────────────────────
# B3-e — V4_listing_improvements_current_state (READONLY — viene de importer B7)
# ─────────────────────────────────────────────────────────────────────────────
#
# V4 NO es editor manual. Su schema (current_state_url string opcional + items
# array<object> con name/status/notes) está diseñado para ser autohidratado por
# las skills `amazon-brand-audit` y `digital-presence-audit` de Ramiro vía el
# módulo importer B7 (HTML drag-drop, pendiente).
#
# Hasta que B7 exista, este renderer muestra:
#  - Banner explicando que la edición manual no aplica
#  - Link al screenshot del listing actual (si current_state_url existe)
#  - Tabla readonly con items {name, status, notes} mapeando status a emoji
#  - JSON colapsado para auditoría
#
# Cuando B7 inyecte data, este renderer la muestra sin tocar nada del flow.


def _render_v4_current_state_readonly(block, proposal, lang):
    """
    Renderer readonly para V4_listing_improvements_current_state.

    Justificación arquitectónica (paralela a V3):
      - Schema V4 = current_state_url (string optional) + items (array<object>
        required) con {name, status: 'missing'|'present'|'weak', notes}.
      - V4 NO declara copy_overrides_schema → 0 campos i18n.
      - Caso de uso real: data viene del análisis del listing actual vía skills
        `amazon-brand-audit` / `digital-presence-audit` de Ramiro, parseada por
        importer B7 (drag-drop HTML). No es para tipear a mano.

    Por eso este renderer es READONLY:
      - Banner informativo: edición manual no soportada, viene de B7.
      - Link al screenshot del listing (si está provisto).
      - Tabla compacta de items con status mapeado a emoji.
      - JSON colapsado para auditoría.

    NO usa _ensure_block_buffer ni el patrón Plan D — no hay edits ni save.
    """
    import streamlit as st
    import pandas as pd

    data = block.get("data") or {}
    current_state_url = data.get("current_state_url") or ""
    items = data.get("items") or []

    st.markdown("### 🖼️ V4 Listing Current State")
    st.caption(f"Idioma de la propuesta: {lang}")

    # Banner explicativo (siempre visible)
    st.markdown(
        f"<div style='background:#FFF8F0;border-left:3px solid {_NARANJA};"
        f"padding:0.7rem 1rem;border-radius:4px;font-size:0.82rem;"
        f"color:#555;line-height:1.5;margin-bottom:1rem;'>"
        f"⏳ <strong>Este bloque se autohidrata vía importer HTML B7</strong> "
        f"(skills <code>amazon-brand-audit</code> / <code>digital-presence-audit</code>). "
        f"No editar manualmente — hasta que B7 esté listo, la data se inyecta vía script."
        f"</div>",
        unsafe_allow_html=True,
    )

    try:
        # ── Sección 1: current_state_url ────────────────────────────────────
        st.markdown("**Screenshot del listing actual**")
        if current_state_url and isinstance(current_state_url, str) and current_state_url.strip():
            st.markdown(f"[Ver screenshot del listing actual]({current_state_url.strip()})")
        else:
            st.markdown(
                f"<div style='color:{_GRIS_TXT};font-size:0.82rem;font-style:italic;"
                f"margin-bottom:0.8rem;'>URL no provista</div>",
                unsafe_allow_html=True,
            )

        # ── Sección 2: items ────────────────────────────────────────────────
        st.markdown("**Checklist de elementos del listing**")

        if not isinstance(items, list) or not items:
            st.info(
                "ℹ️ Sin items cargados. Cuando B7 esté listo, "
                "arrastrá un HTML del audit para autollenar."
            )
        else:
            _STATUS_EMOJI = {"missing": "🔴", "present": "🟢", "weak": "🟡"}
            rows = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                status_raw = (it.get("status") or "").strip().lower()
                emoji = _STATUS_EMOJI.get(status_raw, "⚫")
                rows.append({
                    "name": it.get("name") or "",
                    "status": f"{emoji} {status_raw}" if status_raw else emoji,
                    "notes": it.get("notes"),
                })
            if rows:
                # Fix B3-d-bis: reemplazar None → "" pre-DataFrame para evitar
                # "None" literal en celdas notes (Arrow→JSON quirk Streamlit 1.43.2).
                df_items = pd.DataFrame(_none_to_empty_for_render(rows))
                st.dataframe(df_items, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ items no contiene objetos válidos.")

        # ── Sección 3: JSON raw fallback defensivo ──────────────────────────
        with st.expander("Ver JSON raw del bloque", expanded=False):
            st.json(data)

    except Exception as e:
        st.error(f"⚠️ Error al renderizar V4: {type(e).__name__}: {e}")
        st.json(data)


# ─────────────────────────────────────────────────────────────────────────────
# B3-f — V5_listing_comparison_competitor (READONLY — fuera de contrato B7 v1.0)
# ─────────────────────────────────────────────────────────────────────────────
#
# V5 NO es editor manual. Su schema (comparison_groups array<object> con type
# enum + client_assets/competitor_assets + commentary) está pensado para que
# Capybaras lo emita vía skill de Ramiro a definir post-reunión 22/05.
#
# El contrato Importer B7 v1.0 (notes/sales/contrato-importer-b7-v1.md) dice
# explícitamente: "V5+ bloques: no implementados en M29 al 2026-05-19. Se
# cubrirán en una v2 del contrato cuando los respectivos readonly estén en
# repo." Por eso este renderer es defensivo total respecto del shape de los
# assets — la shape se cierra en v2 del contrato.


def _render_v5_listing_comparison_readonly(block, proposal, lang):
    """
    Renderer readonly para V5_listing_comparison_competitor.

    Schema canónico (catálogo v1):
        comparison_groups: array<object>
            Cada objeto: {
                type: 'main_image' | 'infographics' | 'a_plus',
                client_assets: [],
                competitor_assets: [],
                commentary: str
            }

    Render:
      - Banner B7 (con disclaimer V5 fuera de contrato v1).
      - Si no hay comparison_groups → info "vacío" + JSON expander.
      - Si hay grupos → por grupo: emoji+label del type, commentary,
        2 columnas side-by-side (Cliente / Competidor) con asset lists.
      - JSON fallback expander al final.
      - try/except global que cae a st.json.

    Shape de los assets NO se asume. _render_v5_asset_list es defensivo:
    string → link, dict con key 'url'/'image_url'/'href' → link, else JSON.
    """
    import streamlit as st

    data = block.get("data") or {}
    groups = data.get("comparison_groups") or []

    st.markdown("### ⚖️ V5 Listing — Side-by-Side vs Competidor")
    st.caption(f"Idioma de la propuesta: {lang}")

    # Banner B7 — versión V5: aclara que está FUERA del contrato v1.0
    st.markdown(
        f"""<div style="background:#FFF8F0; border-left:3px solid {_NARANJA};
        padding:12px 16px; border-radius:4px; margin:8px 0 16px;">
        <strong>⏳ Este bloque se autohidrata vía importer HTML B7 (no implementado todavía).</strong><br>
        Capybaras emite el comparativo cliente vs competidor mediante una skill
        a definir. B7 va a parsear HTML con attributes <code>data-proposal-*</code>
        y autohidratar este bloque. Hasta entonces, solo se muestra el contenido
        pre-cargado.<br>
        <em>Nota: V5 está fuera del contrato B7 v1.0 — la shape definitiva de
        los assets se cierra en contrato v2 (post-reunión 22/05).</em>
        </div>""",
        unsafe_allow_html=True,
    )

    try:
        if not groups:
            st.info(
                "📭 No hay grupos de comparación cargados. Cuando B7 esté listo, "
                "se autohidrata desde la skill de Ramiro/Capybaras."
            )
            with st.expander("Ver JSON raw del bloque", expanded=False):
                st.json(data)
            return

        _TYPE_EMOJI = {"main_image": "🖼️", "infographics": "📊", "a_plus": "📄"}
        _TYPE_LABEL = {
            "main_image": "Main Image",
            "infographics": "Infographics",
            "a_plus": "A+ Content",
        }

        for idx, group in enumerate(groups):
            if not isinstance(group, dict):
                st.warning(f"⚠️ Grupo #{idx + 1} no es un objeto válido.")
                st.json(group)
                continue

            gtype = group.get("type") or ""
            commentary = (group.get("commentary") or "").strip()
            client_assets = group.get("client_assets") or []
            competitor_assets = group.get("competitor_assets") or []

            emoji = _TYPE_EMOJI.get(gtype, "📦")
            label = _TYPE_LABEL.get(gtype, gtype or f"Grupo {idx + 1}")

            st.markdown(f"#### {emoji} {label}")
            if commentary:
                st.markdown(f"_{commentary}_")

            col_client, col_competitor = st.columns(2)
            with col_client:
                st.markdown("**Cliente**")
                _render_v5_asset_list(client_assets)
            with col_competitor:
                st.markdown("**Competidor**")
                _render_v5_asset_list(competitor_assets)

            if idx < len(groups) - 1:
                st.divider()

        with st.expander("Ver JSON raw del bloque", expanded=False):
            st.json(data)

    except Exception as e:
        st.error(f"⚠️ Error al renderizar V5: {type(e).__name__}: {e}")
        st.json(data)


def _render_v5_asset_list(assets):
    """
    Helper defensivo para renderizar lista de assets de V5.

    Shape indefinida en contrato v1. Casos manejados:
      - lista vacía → caption "(sin assets)"
      - string → link markdown (truncado a 60 chars si más largo)
      - dict con key 'url'/'image_url'/'href' → link con caption si existe
      - dict sin url conocida → st.json
      - otro tipo → st.json
    """
    import streamlit as st

    if not assets:
        st.caption("_(sin assets)_")
        return

    if not isinstance(assets, list):
        st.warning("⚠️ Assets no es lista.")
        st.json(assets)
        return

    for asset in assets:
        if isinstance(asset, str):
            label = asset if len(asset) <= 60 else asset[:57] + "..."
            st.markdown(f"- [{label}]({asset})")
        elif isinstance(asset, dict):
            url = asset.get("url") or asset.get("image_url") or asset.get("href")
            caption = asset.get("caption") or asset.get("alt") or asset.get("note")
            if url:
                if caption:
                    label = caption
                else:
                    label = url if len(url) <= 60 else url[:57] + "..."
                st.markdown(f"- [{label}]({url})")
            else:
                st.json(asset)
        else:
            st.json(asset)


# ─────────────────────────────────────────────────────────────────────────────
# B3-g — V6_growth_plan_phases (READONLY — emisión TBD, posiblemente Plan D)
# ─────────────────────────────────────────────────────────────────────────────
#
# V6 schema tiene shape más rica que V3/V4/V5: 3 fases exactas (min=max=3),
# cada una con number, name {en,es}, duration, narrative {en,es}.
#
# Decisión arquitectónica DEFERRED a reunión Ramiro 22/05: V6 podría NO
# salir del importer B7 (las skills de Ramiro son amazon-brand-audit y
# digital-presence-audit, que son AUDIT; el growth plan es decisión
# estratégica de Capybaras, no audit). Si Ramiro confirma que no tiene
# skill, V6 se refactoriza a Plan D editor en sesión dedicada post-Ramiro.
#
# HOY: readonly Class B por consistencia (cerrar los 6 CORE editores en
# una sola jornada).


def _render_v6_growth_plan_readonly(block, proposal, lang):
    """
    Renderer readonly para V6_growth_plan_phases.

    Schema canónico (catálogo v1):
        phases: array<object>, min_items=max_items=3
            Cada objeto: {
                number: int,
                name: {en: str, es: str},
                duration: str,
                narrative: {en: str, es: str}
            }

    Render:
      - Banner B7 (con disclaimer V6 fuera de contrato v1, emisión TBD).
      - Si no hay phases → info "vacío" + JSON expander.
      - Si hay phases → 3 cards apiladas (1 por fase) con:
        header (#N + nombre[lang]), duration en caption, narrative[lang]
        como markdown.
      - JSON fallback expander al final.
      - try/except global que cae a st.json.

    Lang handling: cada campo bilingüe usa _v6_pick_lang(field, lang)
    que cae a 'es' si lang no presente, después a primer valor disponible.
    """
    import streamlit as st

    data = block.get("data") or {}
    phases = data.get("phases") or []

    st.markdown("### 🚀 V6 Growth Plan — 3 Fases")
    st.caption(f"Idioma de la propuesta: {lang}")

    # Banner B7 — V6: aclara que la emisión está TBD post-Ramiro
    st.markdown(
        f"""<div style="background:#FFF8F0; border-left:3px solid {_NARANJA};
        padding:12px 16px; border-radius:4px; margin:8px 0 16px;">
        <strong>⏳ Este bloque se autohidrata vía importer HTML B7 (no implementado todavía).</strong><br>
        Plan de crecimiento estructurado en 3 fases (Foundations / Expansion / DSP).
        La emisión definitiva (skill Capybaras manual vs skill de Ramiro) se decide
        en la reunión del 22/05. Hasta entonces, solo se muestra el contenido pre-cargado.<br>
        <em>Nota: V6 está fuera del contrato B7 v1.0 — si la decisión es "skill manual
        Capybaras", V6 se refactoriza a Plan D editor en sesión dedicada.</em>
        </div>""",
        unsafe_allow_html=True,
    )

    try:
        if not phases:
            st.info(
                "📭 No hay fases cargadas. Cuando la skill esté lista, "
                "se autohidrata."
            )
            with st.expander("Ver JSON raw del bloque", expanded=False):
                st.json(data)
            return

        if not isinstance(phases, list):
            st.warning(f"⚠️  phases no es lista (es {type(phases).__name__}).")
            st.json(data)
            return

        for idx, phase in enumerate(phases):
            if not isinstance(phase, dict):
                st.warning(f"⚠️  Fase #{idx + 1} no es un objeto válido.")
                st.json(phase)
                continue

            number = phase.get("number", idx + 1)
            name = _v6_pick_lang(phase.get("name"), lang)
            duration = phase.get("duration") or ""
            narrative = _v6_pick_lang(phase.get("narrative"), lang)

            # Card con header de fase + duración + narrative
            header_label = f"Fase {number}"
            if name:
                header_label += f" — {name}"

            st.markdown(f"#### {header_label}")
            if duration:
                st.caption(f"⏱️  Duración: {duration}")
            if narrative:
                st.markdown(narrative)
            else:
                st.caption("_(sin narrative cargada para este idioma)_")

            if idx < len(phases) - 1:
                st.divider()

        with st.expander("Ver JSON raw del bloque", expanded=False):
            st.json(data)

    except Exception as e:
        st.error(f"⚠️  Error al renderizar V6: {type(e).__name__}: {e}")
        st.json(data)


def _v6_pick_lang(field, lang):
    """
    Helper defensivo para campos bilingües {en, es} de V6.

    Casos manejados:
      - field es None → ""
      - field es str → field (legacy / mal shape, devolver tal cual)
      - field es dict con lang → field[lang]
      - field es dict sin lang pero con 'es' → field['es'] (fallback)
      - field es dict sin lang ni 'es' → primer valor disponible
      - field es dict vacío → ""
    """
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        if lang in field and field[lang]:
            return field[lang]
        if "es" in field and field["es"]:
            return field["es"]
        for v in field.values():
            if v:
                return v
        return ""
    return ""


def _render_blocks_section(proposal: dict) -> None:
    """Render listado readonly de TODOS los blocks de la propuesta.

    Cada block muestra: tier color border, module_id, título bilingüe,
    descripción, y badge de editabilidad (S3-B3 editable / S4 placeholder /
    locked / unknown).

    S3-B2: solo lista visual. Los forms editables llegan en B3-B4.
    """
    blocks = proposal.get("blocks", [])
    language = proposal.get("language", "es")
    catalog_lookup = _catalog_module_lookup()

    if not blocks:
        st.warning("⚠️ La propuesta no tiene bloques. Algo raro pasó al instanciarla.")
        return

    st.markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{_NEGRO};"
        f"margin-bottom:0.8rem;'>Bloques de la propuesta "
        f"<span style='font-size:0.8rem;color:{_GRIS_TXT};font-weight:400;'>"
        f"({len(blocks)} en total)</span></div>",
        unsafe_allow_html=True,
    )

    # Render cada block en orden (NO reordenar — respetar orden del template)
    for idx, block in enumerate(blocks, start=1):
        # B3-b: probar primero el editor (dispatcher). Si renderiza, saltear card readonly.
        if _render_block_editor(block, proposal, language):
            continue
        mid = block.get("module_id", "")
        mod_def = catalog_lookup.get(mid)

        # Edge case: module_id no existe en catálogo
        if mod_def is None:
            st.markdown(
                f"<div style='border:1px solid #F44336;border-left:4px solid #F44336;"
                f"border-radius:6px;padding:0.7rem 1rem;margin-bottom:0.5rem;"
                f"background:#FFF5F5;'>"
                f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                f"<div>"
                f"<div style='font-size:0.7rem;color:#F44336;font-weight:700;'>"
                f"#{idx} · MÓDULO DESCONOCIDO</div>"
                f"<div style='font-family:monospace;font-size:0.85rem;color:{_NEGRO};'>"
                f"{mid or '(sin module_id)'}</div>"
                f"</div>"
                f"<span style='background:#F44336;color:white;font-size:0.7rem;"
                f"padding:3px 10px;border-radius:4px;font-weight:700;'>⚠️ DESCONOCIDO</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )
            continue

        # Resolver datos del catálogo
        tier = mod_def.get("tier", "unknown")
        status = mod_def.get("status", "active")
        tier_meta = _TIER_META.get(tier, {})
        tier_color = tier_meta.get("color", "#9E9E9E")
        tier_label = tier_meta.get("label", tier.upper())

        title = mod_def.get("title", {}).get(language) or mod_def.get("title", {}).get("es") or mid
        desc = mod_def.get("description", {}).get(language) or mod_def.get("description", {}).get("es") or "—"
        if len(desc) > 180:
            desc = desc[:177] + "..."

        # Decidir badge de editabilidad
        if status == "placeholder_coming_soon":
            badge_bg = "#FFC107"
            badge_color = "#5D4037"
            badge_text = "⏳ Próximamente (S4)"
            card_opacity = "0.7"
        elif tier == "core_variable" and status == "active":
            badge_bg = _NARANJA
            badge_color = "white"
            badge_text = "✏️ Editable en S3-B3"
            card_opacity = "1"
        else:
            badge_bg = "#9E9E9E"
            badge_color = "white"
            badge_text = "🔒 Solo lectura"
            card_opacity = "1"

        st.markdown(
            f"<div style='border:1px solid #E0E0E0;border-left:4px solid {tier_color};"
            f"border-radius:6px;padding:0.7rem 1rem;margin-bottom:0.5rem;"
            f"background:#FFFFFF;opacity:{card_opacity};'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;gap:1rem;'>"
            f"<div style='flex:1;min-width:0;'>"
            f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.2rem;'>"
            f"<span style='font-size:0.65rem;color:{_GRIS_TXT};font-weight:600;'>"
            f"#{idx:02d}</span>"
            f"<span style='background:{tier_color}15;color:{tier_color};"
            f"font-size:0.6rem;padding:1px 6px;border-radius:3px;font-weight:700;'>"
            f"{tier_label}</span>"
            f"<span style='font-family:monospace;font-size:0.7rem;color:{_GRIS_TXT};'>"
            f"{mid}</span>"
            f"</div>"
            f"<div style='font-size:0.95rem;font-weight:700;color:{_NEGRO};"
            f"margin-bottom:0.15rem;'>{title}</div>"
            f"<div style='font-size:0.75rem;color:#666;line-height:1.4;'>{desc}</div>"
            f"</div>"
            f"<span style='background:{badge_bg};color:{badge_color};font-size:0.7rem;"
            f"padding:4px 10px;border-radius:4px;font-weight:600;white-space:nowrap;'>"
            f"{badge_text}</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # Footer info: qué pasa en cada tier
    st.markdown(
        f"<div style='margin-top:1.2rem;padding:0.7rem 1rem;background:#FFF8F0;"
        f"border-left:3px solid {_NARANJA};border-radius:4px;font-size:0.78rem;"
        f"color:#555;line-height:1.6;'>"
        f"💡 En <strong>S3-B3</strong> vas a poder editar los bloques marcados como "
        f"<strong>✏️ Editable</strong> (los 6 CORE). "
        f"En <strong>S4</strong> se habilita 'Marcar como interesado' para los "
        f"<strong>⏳ Próximamente</strong>. "
        f"Los <strong>🔒 Solo lectura</strong> se manejan desde el template (no por propuesta)."
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_detail_screen() -> None:
    """Pantalla de vista detalle de una propuesta. Reemplaza los tabs cuando está activa.

    Sesión 3 B1: solo skeleton con header + botón Volver + debug expander.
    La edición de blocks CORE (V1-V6) llega en B3-B4.
    """
    pid = st.session_state.get("ps_detail_active")
    if not pid:
        # Defensa: si el state quedó inconsistente, cerrar y volver al listado
        _close_detail()
        st.rerun()
        return

    # Cargar propuesta desde disco (siempre última versión)
    try:
        proposal = pp.get_proposal(pid)
        if proposal is None:
            raise FileNotFoundError(f"Propuesta {pid} no existe en disco")
    except FileNotFoundError:
        st.error(
            f"❌ Propuesta `{pid[:8]}...` no encontrada. "
            f"Puede haber sido archivada o borrada desde otra pestaña."
        )
        if st.button("← Volver al listado", key="detail_back_error"):
            _close_detail()
            st.rerun()
        return
    except Exception as e:
        st.error(f"❌ Error al cargar propuesta: {type(e).__name__}: {e}")
        if st.button("← Volver al listado", key="detail_back_exc"):
            _close_detail()
            st.rerun()
        return

    # ── Top bar: Volver + título + acciones ──────────────────────────────
    col_back, col_title, col_save = st.columns([1, 4, 1])

    with col_back:
        if st.button("← Volver", key="detail_back", use_container_width=True):
            _close_detail()
            st.rerun()

    cliente = proposal.get("client_name", "—")
    pversion = proposal.get("version", 1)
    archetype = proposal.get("archetype", "—")
    arq_meta = _ARQUETIPOS.get(archetype, {})
    arq_label = arq_meta.get("label", archetype)
    arq_color = arq_meta.get("color", "#9E9E9E")
    status = proposal.get("status", "draft")
    status_label, status_color = _STATUS_META.get(status, (status, "#9E9E9E"))
    language = proposal.get("language", "—")
    lang_label = _LANG_META.get(language, language)
    block_count = len(proposal.get("blocks", []))
    updated = proposal.get("updated_at", "")

    with col_title:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;'>"
            f"<div style='font-size:1.3rem;font-weight:800;color:{_NEGRO};'>{cliente}</div>"
            f"<span style='font-size:0.75rem;color:{_GRIS_TXT};font-weight:400;'>v{pversion}</span>"
            f"<span style='background:{arq_color}15;color:{arq_color};border:1px solid {arq_color};"
            f"font-size:0.7rem;padding:2px 8px;border-radius:4px;font-weight:600;'>{arq_label}</span>"
            f"<span style='background:{status_color}15;color:{status_color};border:1px solid {status_color};"
            f"font-size:0.7rem;padding:2px 8px;border-radius:4px;font-weight:600;'>{status_label}</span>"
            f"<span style='font-size:0.7rem;color:{_GRIS_TXT};'>{lang_label}</span>"
            f"<span style='font-size:0.7rem;color:{_GRIS_TXT};'>{block_count} bloques</span>"
            f"</div>"
            f"<div style='font-size:0.72rem;color:{_GRIS_TXT};margin-top:0.2rem;'>"
            f"Editada {_format_relative_time(updated)} · id: <code>{pid[:8]}...</code>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_save:
        st.button(
            "💾 Guardar",
            key="detail_save",
            use_container_width=True,
            disabled=True,
            help="Edición funcional llega en S3-B4/B5.",
        )

    st.divider()

    # ── B7 Importer (D2: preview readonly, apply llega en D3) ────────────
    _render_b7_importer_section(proposal)

    # ── Listado de blocks de la propuesta ────────────────────────────────
    _render_blocks_section(proposal)

    with st.expander("🔍 Ver propuesta cruda (debug)", expanded=False):
        st.code(json.dumps(proposal, indent=2, ensure_ascii=False), language="json")


# ─────────────────────────────────────────────────────────────────────────────
# B7 Importer — UI dispatcher (D3: preview + apply 2-clicks + save con auto-bump)
# ─────────────────────────────────────────────────────────────────────────────


def _render_b7_importer_section(proposal: dict) -> None:
    """Sección de importer B7 dentro de la vista detalle.

    D2: expander con file_uploader + preview readonly del ImportReport
    (counts + warnings + errors + listado de blocks detectados).
    D3: botón "Aplicar merge" con confirmación 2-clicks + save con
    auto-bump de version + banner de éxito + rerun.

    Args:
        proposal: dict de la propuesta cargada del disco (vista detalle).
    """
    pid = proposal["id"]

    with st.expander("📥 Importar desde HTML (B7)", expanded=False):
        st.caption(
            "Subí un HTML producido por las skills de audit de Ramiro "
            "(`amazon-brand-audit`, `digital-presence-audit`). El importer "
            "lee la convención `data-proposal-*` del contrato B7 v1.0, "
            "preview los bloques detectados y aplica overwrite quirúrgico "
            "del `data` de cada bloque target (preserva id/module_id/is_fixed/"
            "copy_overrides). El save auto-bumpea version."
        )

        uploaded = st.file_uploader(
            "HTML de audit",
            type=["html", "htm"],
            key=f"b7_uploader_{pid}",
            help="Single file v1. Multi-file llega en v1.1.",
        )

        if uploaded is None:
            return

        # Parsear el HTML — función pura, sin side effects.
        try:
            html_bytes = uploaded.getvalue()
            catalog = _load_catalog_cached()
            report = extract_blocks(html_bytes, catalog)
        except Exception as e:
            st.error(
                f"❌ Error al parsear el HTML: {type(e).__name__}: {e}"
            )
            return

        # ── Counts ────────────────────────────────────────────────────────
        n_blocks = len(report.blocks)
        n_warnings = len(report.warnings)
        n_errors = len(report.errors)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Blocks detectados", n_blocks)
        with col_b:
            st.metric("Warnings", n_warnings)
        with col_c:
            st.metric("Errors (bloqueantes)", n_errors)

        # ── Errors: tabla roja, apply bloqueado ───────────────────────────
        if n_errors > 0:
            st.markdown(
                f"<div style='background:#FFF5F5;border-left:3px solid #F44336;"
                f"padding:0.7rem 1rem;border-radius:4px;font-size:0.85rem;"
                f"color:#5D1A1A;line-height:1.5;margin:0.8rem 0;'>"
                f"⛔ <strong>{n_errors} error(es) bloqueante(s)</strong> — el "
                f"merge no se va a poder aplicar hasta resolverlos.</div>",
                unsafe_allow_html=True,
            )
            err_rows = [
                {
                    "code": e.code,
                    "module_id": e.module_id or "—",
                    "block_index": e.block_index if e.block_index is not None else "—",
                    "message": e.message,
                }
                for e in report.errors
            ]
            st.dataframe(err_rows, use_container_width=True, hide_index=True)

        # ── Warnings: tabla amarilla, no bloquea ──────────────────────────
        if n_warnings > 0:
            st.markdown(
                f"<div style='background:#FFFBF0;border-left:3px solid #FFC107;"
                f"padding:0.7rem 1rem;border-radius:4px;font-size:0.85rem;"
                f"color:#5D4037;line-height:1.5;margin:0.8rem 0;'>"
                f"⚠️ <strong>{n_warnings} warning(s)</strong> — no bloquean "
                f"el merge.</div>",
                unsafe_allow_html=True,
            )
            warn_rows = [
                {
                    "code": w.code,
                    "module_id": w.module_id or "—",
                    "block_index": w.block_index if w.block_index is not None else "—",
                    "field_path": w.field_path or "—",
                    "message": w.message,
                }
                for w in report.warnings
            ]
            st.dataframe(warn_rows, use_container_width=True, hide_index=True)

        # ── Blocks detectados: lista compacta con flag apply/skip ─────────
        if n_blocks > 0:
            st.markdown(
                f"<div style='font-size:0.9rem;font-weight:700;color:{_NEGRO};"
                f"margin-top:0.8rem;margin-bottom:0.4rem;'>Blocks detectados "
                f"<span style='font-size:0.75rem;color:{_GRIS_TXT};font-weight:400;'>"
                f"({n_blocks})</span></div>",
                unsafe_allow_html=True,
            )

            # Pre-calcular qué module_ids existen en target_proposal.blocks
            # para marcar visualmente cuáles van a aplicar y cuáles skipean.
            # Mismo criterio que usa merge_blocks (block_not_in_target se
            # warnea pero no aplica).
            target_module_ids = {
                b.get("module_id") for b in proposal.get("blocks", [])
                if isinstance(b, dict)
            }

            for draft in report.blocks:
                will_apply = draft.module_id in target_module_ids
                badge_bg = "#E8F5E9" if will_apply else "#F5F5F5"
                badge_color = "#2E7D32" if will_apply else "#9E9E9E"
                badge_text = "✓ aplicará" if will_apply else "⊘ skip (no está en target)"

                st.markdown(
                    f"<div style='border:1px solid #E0E0E0;border-left:3px solid "
                    f"{_NARANJA};border-radius:4px;padding:0.5rem 0.8rem;"
                    f"margin-bottom:0.35rem;background:#FFFFFF;'>"
                    f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                    f"<div style='font-family:monospace;font-size:0.82rem;color:{_NEGRO};'>"
                    f"#{draft.block_index:02d} · {draft.module_id}</div>"
                    f"<span style='background:{badge_bg};color:{badge_color};"
                    f"font-size:0.7rem;padding:2px 8px;border-radius:3px;font-weight:600;'>"
                    f"{badge_text}</span>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

            # Debug: expander con el data crudo de cada draft (para auditoría).
            with st.expander("🔍 Ver data crudo de los blocks detectados", expanded=False):
                for draft in report.blocks:
                    st.markdown(
                        f"**{draft.module_id}** "
                        f"(contract v{draft.contract_version})"
                    )
                    st.json(draft.data)

        # ── D3: Apply merge con confirmación 2-clicks + save ──────────────
        if report.ok:
            _render_b7_apply_flow(proposal, report, catalog, target_module_ids)


def _render_b7_apply_flow(
    proposal: dict,
    report,
    catalog: dict,
    target_module_ids: set,
) -> None:
    """Botón "Aplicar merge" con confirmación 2-clicks + save con auto-bump.

    Flujo:
      1. Click #1 → setea flag `ps_b7_confirm_apply_{pid}` en session_state,
         el botón muta a "⚠️ Confirmar aplicación".
      2. Click #2 → ejecuta merge_blocks → save_proposal (auto-bumpea version)
         → banner verde con vN → v(N+1) + counts → limpia flag → st.rerun().
      3. Botón "Cancelar" siempre disponible cuando hay flag pendiente.

    El merge se ejecuta SOLO cuando el usuario confirma — si no hay blocks
    aplicables (todos skip por block_not_in_target), igual se muestra el
    botón pero la acción se hace explícita con info al lado.

    Args:
        proposal: dict actual de la propuesta (vista detalle).
        report: ImportReport ya validado (report.ok == True).
        catalog: catálogo cargado, requerido por merge_blocks signature.
        target_module_ids: set de module_ids presentes en proposal.blocks,
            ya pre-calculado por el caller (para mostrar preview-aware).
    """
    pid = proposal["id"]
    flag_key = f"ps_b7_confirm_apply_{pid}"
    confirm_pending = st.session_state.get(flag_key, False)

    # Pre-calcular cuántos blocks van a aplicar vs skipear (preview).
    n_will_apply = sum(
        1 for d in report.blocks if d.module_id in target_module_ids
    )
    n_will_skip = len(report.blocks) - n_will_apply

    st.markdown(
        f"<div style='margin-top:1rem;padding:0.7rem 1rem;"
        f"background:#FFF8F0;border-left:3px solid {_NARANJA};"
        f"border-radius:4px;font-size:0.82rem;color:#5D2D00;line-height:1.5;'>"
        f"✅ <strong>Report válido</strong> — listo para aplicar el merge. "
        f"Se actualizarán <strong>{n_will_apply}</strong> bloque(s) "
        f"<span style='color:#888;'>(skip: {n_will_skip})</span>.</div>",
        unsafe_allow_html=True,
    )

    col_btn, col_cancel = st.columns([3, 1])

    with col_btn:
        if not confirm_pending:
            if st.button(
                "Aplicar merge",
                key=f"b7_apply_btn_{pid}",
                type="primary",
                use_container_width=True,
                disabled=(n_will_apply == 0),
                help=(
                    "Sobrescribe el `data` de cada bloque target con los datos "
                    "del HTML. Auto-bumpea version (snapshot inmutable)."
                    if n_will_apply > 0
                    else "Ningún bloque del HTML matchea con los blocks del target."
                ),
            ):
                st.session_state[flag_key] = True
                st.rerun()
        else:
            if st.button(
                "⚠️ Confirmar aplicación",
                key=f"b7_confirm_btn_{pid}",
                type="primary",
                use_container_width=True,
            ):
                _execute_b7_merge_and_save(proposal, report, catalog, flag_key)

    with col_cancel:
        if confirm_pending:
            if st.button(
                "Cancelar",
                key=f"b7_cancel_btn_{pid}",
                use_container_width=True,
            ):
                st.session_state[flag_key] = False
                st.rerun()


def _execute_b7_merge_and_save(
    proposal: dict,
    report,
    catalog: dict,
    flag_key: str,
) -> None:
    """Ejecuta merge_blocks + save_proposal con manejo de errores.

    En orden:
      1. version_before = proposal['version'] (para banner vN → vN+1)
      2. merge_blocks(report, proposal, catalog) → MergeResult
      3. Si merge_result.errors → banner rojo, NO se guarda, NO se limpia flag.
      4. pp.save_proposal(merge_result.proposal_updated) → auto-bumpea version.
      5. Banner verde con summary + limpia flag + st.rerun().

    Args:
        proposal: dict de la propuesta actual.
        report: ImportReport ya validado.
        catalog: catálogo B7.
        flag_key: clave del session_state a limpiar post-éxito.
    """
    version_before = proposal.get("version", "?")

    try:
        merge_result = merge_blocks(report, proposal, catalog)
    except Exception as e:
        st.error(
            f"❌ Error inesperado durante el merge: "
            f"{type(e).__name__}: {e}"
        )
        return

    # Validar que merge_result no traiga errores bloqueantes.
    if merge_result.errors:
        err_codes = ", ".join(sorted({e.code for e in merge_result.errors}))
        st.error(
            f"❌ El merge no se pudo aplicar: {len(merge_result.errors)} "
            f"error(es) — codes: {err_codes}. La propuesta NO fue modificada."
        )
        # NO limpiamos el flag: el usuario puede volver a intentar o cancelar.
        return

    # Save con auto-bump de version (pp.save_proposal ignora cualquier
    # version del input y escribe max_actual + 1).
    try:
        saved = pp.save_proposal(merge_result.proposal_updated)
    except Exception as e:
        st.error(
            f"❌ Error al persistir la propuesta: "
            f"{type(e).__name__}: {e}. El merge se calculó pero NO se guardó."
        )
        return

    # Éxito: banner verde + limpiar flag + rerun.
    version_after = saved.get("version", "?")
    n_applied = len(merge_result.applied_blocks)
    n_skipped = len(merge_result.skipped_blocks)
    n_warn = len(merge_result.warnings)

    summary_parts = [
        f"<strong>Aplicados:</strong> {n_applied}",
        f"<strong>Skip:</strong> {n_skipped}",
        f"<strong>Warnings:</strong> {n_warn}",
    ]
    if merge_result.applied_blocks:
        applied_preview = ", ".join(merge_result.applied_blocks[:5])
        if n_applied > 5:
            applied_preview += f", ... ({n_applied - 5} más)"
        summary_parts.append(f"<strong>Módulos:</strong> {applied_preview}")

    st.markdown(
        f"<div style='margin-top:0.8rem;padding:0.8rem 1.1rem;"
        f"background:#E8F5E9;border-left:4px solid #2E7D32;"
        f"border-radius:4px;font-size:0.88rem;color:#1B5E20;line-height:1.6;'>"
        f"✅ <strong>Merge aplicado y guardado.</strong> "
        f"<span style='font-family:monospace;background:#FFFFFF;padding:1px 6px;"
        f"border-radius:3px;color:#2E7D32;'>v{version_before} → v{version_after}</span>"
        f"<br>{' · '.join(summary_parts)}</div>",
        unsafe_allow_html=True,
    )

    # Limpiar flag de confirmación.
    st.session_state[flag_key] = False

    # Refrescar la vista detalle con la propuesta nueva.
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    """Entry point del módulo Proposal Studio (M29)."""
    _render_header()

    # Inicializar state machines (idempotente).
    _init_wizard_state()
    _init_detail_state()

    # Branch S3: si hay una propuesta abierta en vista detalle, reemplazar la pantalla.
    if _is_detail_active():
        _render_detail_screen()
        return

    tab_listado, tab_nuevo = st.tabs(["📋 Mis propuestas", "✨ Nueva propuesta"])

    with tab_listado:
        _tab_listado()

    with tab_nuevo:
        _tab_nuevo()
