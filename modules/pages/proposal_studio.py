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

    # ── Listado de blocks de la propuesta ────────────────────────────────
    _render_blocks_section(proposal)

    with st.expander("🔍 Ver propuesta cruda (debug)", expanded=False):
        st.code(json.dumps(proposal, indent=2, ensure_ascii=False), language="json")


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
