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
            st.info(
                f"🚧 Vista detalle pendiente para Sesión 3.\n\n"
                f"Propuesta: **{cliente}** (v{pversion}) — id: `{pid[:8]}...`"
            )

    with col_dup:
        if st.button("📋 Duplicar", key=f"dup_{pid}", use_container_width=True):
            try:
                duplicate = dict(proposal)
                duplicate["id"] = ""  # save_proposal asignará uuid nuevo
                duplicate["client_name"] = f"{cliente} (copia)"
                duplicate["status"] = "draft"
                duplicate["created_at"] = ""  # save_proposal lo setea
                # Regenerar block ids para que no pisen los originales
                import uuid as _uuid
                duplicate["blocks"] = [
                    {**b, "id": str(_uuid.uuid4())} for b in proposal.get("blocks", [])
                ]
                saved = pp.save_proposal(duplicate)
                # Bumpear proposal_id de los blocks al id real generado
                saved["blocks"] = [{**b, "proposal_id": saved["id"]} for b in saved["blocks"]]
                saved = pp.save_proposal(saved)
                st.success(f"✅ Duplicada como '{saved['client_name']}' (v{saved['version']})")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al duplicar: {e}")

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


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    """Entry point del módulo Proposal Studio (M29)."""
    _render_header()

    tab_listado, tab_nuevo = st.tabs(["📋 Mis propuestas", "✨ Nueva propuesta"])

    with tab_listado:
        _tab_listado()

    with tab_nuevo:
        _tab_nuevo()
