import io
import re
from datetime import datetime

import streamlit as st
import pandas as pd

from streamlit.components.v1 import html as st_html

from core.helpers import kpi_card
from core.innovation_persistence import (
    _add_comentario,
    _add_prototipo,
    _create_idea,
    _get_prototipo,
    _list_comentarios,
    _list_ideas,
    _list_prototipos,
    _list_votos,
    _toggle_destacado,
    _update_idea,
    _upsert_voto,
)


def _parse_md_file(data, name):
    """Parse a markdown file, extract headers, tags, and date from filename."""
    text = data.decode("utf-8", errors="replace")

    # Extract date from filename patterns: YYYY-MM-DD, YYYY_MM_DD, etc.
    date_match = re.search(r'(\d{4})[-_](\d{2})[-_](\d{2})', name)
    file_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else None

    # Extract H1/H2 headers
    headers = re.findall(r'^#{1,3}\s+(.+)$', text, re.MULTILINE)

    # Extract tags (#word patterns in text)
    tags = set(re.findall(r'(?<!\S)#([a-zA-Z][a-zA-Z0-9_-]{1,30})(?!\S)', text))

    # Infer category from tags or headers
    categories = {
        "ppc": ["ppc", "ads", "advertising", "campaign", "acos", "tacos", "bid"],
        "amazon": ["amazon", "seller", "listing", "asin", "buybox"],
        "ai": ["ai", "claude", "gpt", "llm", "rufus"],
        "strategy": ["strategy", "launch", "ranking", "sop"],
        "client": ["client", "cliente", "dermaglos", "ltd", "mb", "setex"],
    }
    detected_cats = set()
    all_text_lower = text.lower()
    for cat, keywords in categories.items():
        if any(kw in all_text_lower for kw in keywords):
            detected_cats.add(cat)
    if not detected_cats:
        detected_cats.add("general")

    title = headers[0] if headers else name.replace(".md", "").replace("_", " ").replace("-", " ").title()

    return {
        "title": title,
        "headers": headers,
        "tags": sorted(tags),
        "categories": sorted(detected_cats),
        "date": file_date,
        "text": text,
        "filename": name,
        "word_count": len(text.split()),
    }


def render(user_name=None, user_slug=None):
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📚</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>Knowledge Base</div>"
        "<div style='font-size:0.82rem;color:#888;'>Repositorio de notas, aprendizajes y documentación del equipo.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Repositorio de notas y documentación del equipo. Buscar, filtrar y crear notas .md (SOPs, learnings, research).")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Archivos .md o .txt. Parsea headers, tags, categorías y fecha del filename (YYYY-MM-DD-tema).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Sincronizar con notes/knowledge/ en el repo para que el equipo las consulte.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Tab 1: subí archivos .md → buscá por texto, filtrá por tags y categorías\n"
            "2. Tab 2: creá una nota nueva con preview en vivo\n"
            "3. Descargá el .md generado y guardalo en notes/knowledge/"
        )

    tab1, tab2, tab3 = st.tabs(["📖 Explorar notas", "✏️ Agregar nota", "💡 Innovation Board"])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — Explore notes
    # ══════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("📖 Explorar notas")
        st.caption("Subí archivos .md para explorarlos, buscar por texto y filtrar por tags.")

        files_md = st.file_uploader(
            "Subí archivos .md", type=["md", "txt"],
            accept_multiple_files=True, key="kb_files",
        )

        if not files_md:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí uno o más archivos .md para explorar tu knowledge base.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Parse all files
            notes = []
            all_tags = set()
            all_cats = set()
            for f in files_md:
                note = _parse_md_file(f.getvalue(), f.name)
                notes.append(note)
                all_tags.update(note["tags"])
                all_cats.update(note["categories"])

            st.success(f"✅ {len(notes)} notas cargadas · {sum(n['word_count'] for n in notes):,} palabras totales")

            # ── Filters ──────────────────────────────────────────────
            fc1, fc2, fc3 = st.columns([2, 1, 1])
            search_text = fc1.text_input(
                "Buscar por texto", placeholder="Ej: harvesting, acos, rufus...", key="kb_search",
            )
            filter_tags = fc2.multiselect("Tags", sorted(all_tags), key="kb_tags")
            filter_cats = fc3.multiselect("Categorías", sorted(all_cats), key="kb_cats")

            # Apply filters
            filtered = notes
            if search_text:
                search_lower = search_text.lower()
                filtered = [n for n in filtered if search_lower in n["text"].lower()]
            if filter_tags:
                filtered = [n for n in filtered if any(t in n["tags"] for t in filter_tags)]
            if filter_cats:
                filtered = [n for n in filtered if any(c in n["categories"] for c in filter_cats)]

            # Sort by date (newest first)
            filtered.sort(key=lambda n: n["date"] or "0000-00-00", reverse=True)

            st.markdown(f"**{len(filtered)}** notas encontradas")

            # ── Notes list ───────────────────────────────────────────
            for note in filtered:
                tags_html = " ".join(
                    f"`#{t}`" for t in note["tags"][:8]
                ) if note["tags"] else ""
                date_label = note["date"] or "sin fecha"
                cats_badges = " ".join(
                    f"<span style='background:#FFF3E0;color:#E84000;font-size:0.65rem;"
                    f"padding:1px 6px;border-radius:4px;font-weight:600;'>{c}</span>"
                    for c in note["categories"]
                )

                label = f"📄 {note['title']}  —  {date_label}  ({note['word_count']} palabras)"

                with st.expander(label):
                    if tags_html:
                        st.markdown(f"**Tags:** {tags_html}")
                    st.markdown(f"**Categorías:** {cats_badges}", unsafe_allow_html=True)
                    st.markdown(f"**Archivo:** `{note['filename']}`")
                    st.markdown("---")

                    # Show content (truncate if very long)
                    content = note["text"]
                    if len(content) > 10000:
                        st.markdown(content[:10000])
                        st.caption(f"... (truncado, {note['word_count']} palabras totales)")
                    else:
                        st.markdown(content)

            # ── Summary table ────────────────────────────────────────
            if len(filtered) > 1:
                st.markdown("---")
                st.markdown("#### Resumen")
                summary_rows = [{
                    "Título": n["title"][:50],
                    "Fecha": n["date"] or "—",
                    "Tags": ", ".join(n["tags"][:5]),
                    "Categorías": ", ".join(n["categories"]),
                    "Palabras": n["word_count"],
                } for n in filtered]
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — Add note
    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("✏️ Agregar nota")
        st.caption("Escribí una nota nueva y descargala como .md para agregarla al repo.")

        nc1, nc2 = st.columns(2)
        note_title = nc1.text_input("Título", placeholder="Ej: Aprendizaje harvesting Dermaglos", key="kb_title")
        note_tags = nc2.text_input("Tags (separados por coma)", placeholder="ppc, harvesting, dermaglos", key="kb_note_tags")

        note_category = st.selectbox(
            "Categoría", ["ppc", "amazon", "strategy", "ai", "client", "general"],
            key="kb_note_cat",
        )

        note_content = st.text_area(
            "Contenido (Markdown)",
            height=300,
            placeholder="# Mi nota\n\nContenido aquí...\n\n## Sección 2\n\n- Punto 1\n- Punto 2",
            key="kb_note_content",
        )

        if note_title and note_content:
            # Build markdown file
            today = datetime.now().strftime("%Y-%m-%d")
            tags_str = ", ".join(f"#{t.strip()}" for t in note_tags.split(",") if t.strip()) if note_tags else ""

            md_content = f"# {note_title}\n\n"
            if tags_str:
                md_content += f"**Tags:** {tags_str}\n\n"
            md_content += f"**Categoría:** {note_category} · **Fecha:** {today}\n\n---\n\n"
            md_content += note_content

            filename = f"{today}-{note_title.lower().replace(' ', '-')[:40]}.md"
            filename = re.sub(r'[^a-z0-9\-.]', '', filename)

            st.markdown("---")
            st.markdown("#### Preview")
            st.markdown(md_content)

            st.download_button(
                f"⬇️ Descargar {filename}",
                data=md_content.encode("utf-8"),
                file_name=filename,
                mime="text/markdown",
                key="kb_note_dl",
            )
        else:
            st.info("Completá el título y contenido para previsualizar y descargar.")

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — Innovation Board (M24)
    # ══════════════════════════════════════════════════════════════════
    with tab3:
        _render_innovation_board(user_name, user_slug)


# ══════════════════════════════════════════════════════════════════════════
# Innovation Board (M24) — helpers module-level
# ══════════════════════════════════════════════════════════════════════════

_IB_AREAS = ["ppc", "account", "sales", "research", "ops"]
_IB_NIVELES = ["alto", "medio", "bajo"]
_IB_ESTADOS = ["nueva", "en revisión", "aprobada", "descartada"]

# Pesos para el desempate por cuadrante impacto/esfuerzo.
_IB_IMPACTO_W = {"alto": 2, "medio": 1, "bajo": 0}
_IB_ESFUERZO_W = {"bajo": 2, "medio": 1, "alto": 0}  # menor esfuerzo = mejor


def _ib_usuarios():
    """Nombres del equipo desde secrets; fallback mínimo si no hay secrets."""
    try:
        creds = st.secrets["credentials"]["usernames"]
        nombres = sorted(v.get("name", k) for k, v in creds.items())
        if nombres:
            return nombres
    except Exception:
        pass
    return ["Usuario local"]


def _ib_score(votos):
    """Score de una idea = suma de los valores de sus votos."""
    return sum(int(v.get("valor", 0) or 0) for v in votos)


def _ib_quadrant_rank(idea):
    """Ranking de cuadrante (mayor = mejor). Quick Win (alto/bajo) queda arriba."""
    imp = _IB_IMPACTO_W.get(idea.get("impacto", "medio"), 1)
    esf = _IB_ESFUERZO_W.get(idea.get("esfuerzo", "medio"), 1)
    return imp + esf


def _ib_is_quick_win(idea):
    return idea.get("impacto") == "alto" and idea.get("esfuerzo") == "bajo"


def _ib_badge(text, bg, fg):
    return (
        f"<span style='background:{bg};color:{fg};font-size:0.65rem;"
        f"padding:2px 8px;border-radius:6px;font-weight:700;"
        f"margin-right:4px;'>{text}</span>"
    )


# Colores del badge de estado (pipeline).
_IB_ESTADO_COLORS = {
    "nueva": ("#E3F2FD", "#1565C0"),
    "en revisión": ("#FFF3E0", "#E84000"),
    "aprobada": ("#E8F5E9", "#1B6B2F"),
    "descartada": ("#EEEEEE", "#888888"),
}


def _ib_estado_badge(estado):
    bg, fg = _IB_ESTADO_COLORS.get(estado, ("#EEEEEE", "#888888"))
    return _ib_badge(estado, bg, fg)


def _ib_on_estado_change(idea_id, state_key):
    """Callback on_change del selectbox de estado — persiste el nuevo estado."""
    nuevo = st.session_state.get(state_key)
    if nuevo:
        _update_idea(idea_id, {"estado": nuevo})


def _render_innovation_board(user_name=None, user_slug=None):
    st.subheader("💡 Innovation Board")
    st.caption(
        "Proponé ideas de mejora para el Agency OS, votá las de tus compañeros "
        "y priorizá por impacto vs esfuerzo."
    )

    # ── Resolución de autor / votante ────────────────────────────────────
    if user_name:
        autor = user_name
        st.caption(f"👤 Publicando y votando como **{autor}**")
    else:
        autor = st.selectbox("👤 ¿Quién sos?", _ib_usuarios(), key="ib_autor")
    votante_id = user_slug or autor

    # ── Sub-sección: Nueva idea ──────────────────────────────────────────
    st.markdown("#### ➕ Nueva idea")
    ic1, ic2 = st.columns([3, 2])
    ic1.text_input(
        "Título", placeholder="Ej: Auto-negativizar términos sin conversión",
        key="ib_new_titulo",
    )
    ic2.text_input(
        "Módulo destino (opcional)", placeholder="Ej: STR, Campaign Builder...",
        key="ib_new_modulo",
    )
    st.text_area(
        "Descripción", placeholder="¿Qué es la idea y cómo funcionaría?",
        key="ib_new_desc", height=90,
    )
    st.text_area(
        "Problema — ¿qué duele hoy?",
        placeholder="El dolor concreto que esta idea resuelve.",
        key="ib_new_problema", height=70,
    )
    mc1, mc2, mc3 = st.columns(3)
    mc1.selectbox("Área", _IB_AREAS, key="ib_new_area")
    mc2.selectbox("Impacto", _IB_NIVELES, key="ib_new_impacto")
    mc3.selectbox("Esfuerzo", _IB_NIVELES, key="ib_new_esfuerzo")

    if st.button("🚀 Publicar idea", key="ib_publicar", type="primary"):
        titulo = st.session_state.get("ib_new_titulo", "").strip()
        if not titulo:
            st.warning("El título es obligatorio.")
        else:
            _create_idea(
                {
                    "titulo": titulo,
                    "descripcion": st.session_state.get("ib_new_desc", "").strip(),
                    "problema": st.session_state.get("ib_new_problema", "").strip(),
                    "area": st.session_state.get("ib_new_area", "ops"),
                    "impacto": st.session_state.get("ib_new_impacto", "medio"),
                    "esfuerzo": st.session_state.get("ib_new_esfuerzo", "medio"),
                    "modulo_destino": st.session_state.get("ib_new_modulo", "").strip(),
                    "autor": autor,
                }
            )
            st.success(f"✅ Idea publicada: {titulo}")
            st.rerun()

    st.divider()

    # ── Sub-sección: Board ───────────────────────────────────────────────
    st.markdown("#### 🗂️ Board")

    fc1, fc2 = st.columns(2)
    filtro_area = fc1.selectbox(
        "Filtrar por área", ["(todas)"] + _IB_AREAS, key="ib_filtro_area"
    )
    filtro_estado = fc2.selectbox(
        "Filtrar por estado", ["(todos)"] + _IB_ESTADOS, key="ib_filtro_estado"
    )

    area_arg = None if filtro_area == "(todas)" else filtro_area
    estado_arg = None if filtro_estado == "(todos)" else filtro_estado
    ideas = _list_ideas(area_arg, estado_arg)

    # Enriquecer con votos + score
    enriched = []
    for idea in ideas:
        votos = _list_votos(idea["id"])
        enriched.append({"idea": idea, "votos": votos, "score": _ib_score(votos)})

    # Orden: score desc, luego cuadrante (quick win primero), luego título
    enriched.sort(
        key=lambda e: (
            -e["score"],
            -_ib_quadrant_rank(e["idea"]),
            e["idea"].get("titulo", "").lower(),
        )
    )

    # ── Métricas ─────────────────────────────────────────────────────────
    total_ideas = len(enriched)
    ideas_votadas = sum(1 for e in enriched if e["votos"])
    quick_wins = sum(1 for e in enriched if _ib_is_quick_win(e["idea"]))
    aprobadas = sum(1 for e in enriched if e["idea"].get("estado") == "aprobada")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(kpi_card("Total ideas", str(total_ideas)), unsafe_allow_html=True)
    k2.markdown(kpi_card("Ideas votadas", str(ideas_votadas)), unsafe_allow_html=True)
    k3.markdown(kpi_card("Quick Wins", str(quick_wins)), unsafe_allow_html=True)
    k4.markdown(kpi_card("Aprobadas", str(aprobadas)), unsafe_allow_html=True)

    if not enriched:
        st.markdown(
            "<div style='text-align:center;padding:2.5rem 1rem;border:2px dashed #FFD9B3;"
            "border-radius:12px;margin:1rem 0;'>"
            "<div style='font-size:2.5rem;margin-bottom:0.4rem;'>💡</div>"
            "<div style='font-size:0.95rem;color:#666;font-weight:600;'>"
            "Todavía no hay ideas con estos filtros.</div>"
            "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
            "Publicá la primera con el formulario de arriba.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Cards ────────────────────────────────────────────────────────────
    for e in enriched:
        idea = e["idea"]
        votos = e["votos"]
        idea_id = idea["id"]
        qw = " ⚡ Quick Win" if _ib_is_quick_win(idea) else ""

        badges = (
            _ib_estado_badge(idea.get("estado", "nueva"))
            + _ib_badge(idea.get("area", "—"), "#E3F2FD", "#1565C0")
            + _ib_badge("Impacto " + idea.get("impacto", "—"), "#FFF3E0", "#E84000")
            + _ib_badge("Esfuerzo " + idea.get("esfuerzo", "—"), "#F3E5F5", "#6A1B9A")
        )
        modulo = idea.get("modulo_destino", "")
        modulo_html = (
            _ib_badge("→ " + modulo, "#E8F5E9", "#1B6B2F") if modulo else ""
        )

        st.markdown(
            "<div style='border:1px solid #EEE;border-left:4px solid #E84000;"
            "border-radius:10px;padding:0.85rem 1rem;margin:0.6rem 0;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div style='font-size:1.05rem;font-weight:800;color:#1F1F1F;'>{idea.get('titulo','')}{qw}</div>"
            f"<div style='font-size:1.1rem;font-weight:800;color:#E84000;'>★ {e['score']}</div>"
            "</div>"
            f"<div style='font-size:0.72rem;color:#888;margin:0.2rem 0 0.5rem;'>por {idea.get('autor','—')} · {len(votos)} voto(s)</div>"
            f"<div style='margin-bottom:0.5rem;'>{badges}{modulo_html}</div>"
            + (
                f"<div style='font-size:0.9rem;color:#333;margin-bottom:0.3rem;'>{idea.get('descripcion','')}</div>"
                if idea.get("descripcion") else ""
            )
            + (
                f"<div style='font-size:0.82rem;color:#B71C1C;'>🔴 <b>Duele:</b> {idea.get('problema','')}</div>"
                if idea.get("problema") else ""
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        # Voto existente de este usuario (para precarga)
        mi_voto = next((v for v in votos if v.get("votante") == votante_id), None)

        # Pipeline de estado — on_change persiste (sin polling).
        state_key = f"ib_estado_{idea_id}"
        cur_estado = idea.get("estado", "nueva")
        cur_idx = _IB_ESTADOS.index(cur_estado) if cur_estado in _IB_ESTADOS else 0
        sc1, sc2 = st.columns([1, 3])
        sc1.caption("Estado")
        sc2.selectbox(
            "Estado", _IB_ESTADOS, index=cur_idx, key=state_key,
            on_change=_ib_on_estado_change, args=(idea_id, state_key),
            label_visibility="collapsed",
        )

        pc1, pc2, pc3, pc4 = st.columns(4)
        with pc1:
            _ib_vote_popover(idea_id, votante_id, mi_voto)
        with pc2:
            with st.popover(f"👀 Votos ({len(votos)})", use_container_width=True):
                if not votos:
                    st.caption("Sin votos todavía.")
                for v in votos:
                    signo = "➕" if v.get("valor", 0) > 0 else ("➖" if v.get("valor", 0) < 0 else "•")
                    st.markdown(
                        f"**{v.get('votante','—')}** · {signo} {v.get('valor',0)}"
                    )
                    st.caption(v.get("razon", "") or "—")
        with pc3:
            _ib_proto_popover(idea_id, autor)
        with pc4:
            _ib_coment_popover(idea_id, autor, idea)

    # ── Render del prototipo activo — FUERA de todo popover ──────────────
    # Decisión: st.components.v1.html vive en el flujo principal (no dentro del
    # popover). Un iframe de 700px dentro de un popover es mala UX y su render
    # no es validable headless; acá es full-width y seguro. La idea/proto activo
    # se elige vía session_state["ib_active_proto"].
    _ib_render_active_prototype()


def _ib_vote_popover(idea_id, votante_id, mi_voto):
    """Popover de votación con radio (+1/0/-1) + razón obligatoria.

    Precarga el voto existente vía buffers en session_state (patrón Plan D:
    se siembra el key ANTES de crear el widget, sin pasar value=).
    """
    val_key = f"ib_vote_val_{idea_id}"
    razon_key = f"ib_vote_razon_{idea_id}"

    # Sembrado único: solo si el buffer aún no existe en esta sesión.
    if val_key not in st.session_state:
        st.session_state[val_key] = int(mi_voto["valor"]) if mi_voto else 0
    if razon_key not in st.session_state:
        st.session_state[razon_key] = mi_voto.get("razon", "") if mi_voto else ""

    btn_label = "✏️ Actualizar voto" if mi_voto else "🗳️ Votar"
    with st.popover(btn_label, use_container_width=True):
        st.radio(
            "Tu voto",
            options=[1, 0, -1],
            format_func=lambda x: {1: "➕ A favor (+1)", 0: "• Neutral (0)", -1: "➖ En contra (−1)"}[x],
            key=val_key,
            horizontal=True,
        )
        st.text_area("Razón (obligatoria)", key=razon_key, height=80)
        if st.button("Guardar voto", key=f"ib_vote_btn_{idea_id}", type="primary"):
            razon_val = str(st.session_state.get(razon_key, "")).strip()
            if not razon_val:
                st.warning("La razón es obligatoria — no se guardó el voto.")
            else:
                _upsert_voto(
                    idea_id, votante_id, int(st.session_state[val_key]), razon_val
                )
                st.success("✅ Voto registrado.")
                st.rerun()


def _ib_proto_popover(idea_id, autor):
    """Popover de prototipos HTML: subida (versionada) + selección para ver.

    El render del HTML NO va acá (ver `_ib_render_active_prototype`) — solo
    subida y selección. El versionado lo maneja la capa de persistencia.
    """
    protos = _list_prototipos(idea_id)
    with st.popover(f"🧪 Prototipos ({len(protos)})", use_container_width=True):
        st.caption(
            "⚠️ El HTML es de terceros y ejecuta JS en un iframe. "
            "Subí solo prototipos de gente del equipo."
        )
        up = st.file_uploader(
            "Subir prototipo (.html)", type=["html"], key=f"ib_proto_up_{idea_id}"
        )
        if up is not None:
            data = up.getvalue()
            sig = f"{up.name}:{len(data)}"
            sig_key = f"ib_proto_sig_{idea_id}"
            # Guarda anti-duplicado: el uploader retorna el archivo en cada rerun.
            if st.session_state.get(sig_key) != sig:
                st.session_state[sig_key] = sig
                if len(data) > 2_000_000:
                    st.error("El archivo supera 2 MB — no se guardó.")
                else:
                    html = data.decode("utf-8", errors="replace")
                    _add_prototipo(idea_id, up.name, html, autor)
                    st.success(f"✅ Prototipo guardado: {up.name}")
                    st.rerun()

        if protos:
            labels = {
                f"{p.get('nombre','?')} · v{p.get('version','?')} · {p.get('autor','—')}": p["id"]
                for p in protos
            }
            sel_label = st.selectbox(
                "Ver prototipo", list(labels.keys()), key=f"ib_proto_sel_{idea_id}"
            )
            if st.button("👁️ Ver seleccionado", key=f"ib_proto_view_{idea_id}"):
                st.session_state["ib_active_proto"] = labels[sel_label]
                st.rerun()
        else:
            st.caption("Sin prototipos todavía.")


def _ib_render_active_prototype():
    """Renderiza el prototipo activo (session_state) en el flujo principal.

    FUERA de cualquier popover — un iframe de 700px dentro de un popover es
    mala UX y su render no es validable headless.
    """
    active = st.session_state.get("ib_active_proto")
    if not active:
        return
    proto = _get_prototipo(active)
    if not proto:
        return

    st.divider()
    tc1, tc2 = st.columns([4, 1])
    tc1.markdown(
        f"#### 🧪 Prototipo: {proto.get('nombre','?')} · v{proto.get('version','?')}"
    )
    if tc2.button("✖ Cerrar", key="ib_proto_close"):
        st.session_state["ib_active_proto"] = None
        st.rerun()

    st.caption(
        "⚠️ HTML de terceros — ejecuta JS en el iframe. "
        "Solo prototipos de gente del equipo."
    )
    html = proto.get("html_content", "") or ""
    st.download_button(
        "⬇️ Descargar HTML",
        data=html.encode("utf-8"),
        file_name=proto.get("nombre", "prototipo.html"),
        mime="text/html",
        key="ib_proto_dl",
    )
    st_html(html, height=700, scrolling=True)


def _ib_coment_popover(idea_id, autor, idea):
    """Popover de comentarios: listado (destacados resaltados) + alta.

    El toggle de destacado solo lo ve el dueño de la idea (autor == idea.autor).
    """
    coms = _list_comentarios(idea_id)
    es_dueno = autor == idea.get("autor")
    with st.popover(f"💬 Comentarios ({len(coms)})", use_container_width=True):
        if not coms:
            st.caption("Sin comentarios todavía.")
        for c in coms:
            fecha = (c.get("created_at") or "")[:10] or "—"
            destacado = bool(c.get("destacado"))
            bg = "#FFF3E0" if destacado else "#FAFAFA"
            badge = (
                "<span style='background:#E84000;color:#fff;font-size:0.6rem;"
                "padding:1px 6px;border-radius:4px;font-weight:700;'>"
                "⭐ Aporte destacado</span>"
                if destacado else ""
            )
            st.markdown(
                f"<div style='background:{bg};border-radius:8px;"
                f"padding:0.5rem 0.7rem;margin:0.3rem 0;'>"
                f"<div style='font-size:0.72rem;color:#888;'>"
                f"{c.get('autor','—')} · {fecha} {badge}</div>"
                f"<div style='font-size:0.88rem;color:#333;margin-top:0.2rem;'>"
                f"{c.get('cuerpo','')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if es_dueno:
                lbl = "☆ Quitar destacado" if destacado else "⭐ Destacar"
                if st.button(lbl, key=f"ib_com_star_{c['id']}"):
                    _toggle_destacado(c["id"], not destacado)
                    st.rerun()

        st.divider()
        st.text_area("Nuevo comentario", key=f"ib_com_txt_{idea_id}", height=70)
        if st.button("💬 Comentar", key=f"ib_com_btn_{idea_id}"):
            cuerpo = str(st.session_state.get(f"ib_com_txt_{idea_id}", "")).strip()
            if not cuerpo:
                st.warning("El comentario no puede estar vacío.")
            else:
                _add_comentario(idea_id, autor, cuerpo)
                st.rerun()
