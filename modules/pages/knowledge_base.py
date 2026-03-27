import io
import re
from datetime import datetime

import streamlit as st
import pandas as pd


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


def render():
    st.header("📚 Knowledge Base")
    st.caption("Repositorio de notas, aprendizajes y documentación del equipo.")
    st.divider()

    tab1, tab2 = st.tabs(["📖 Explorar notas", "✏️ Agregar nota"])

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
            st.info("Subí uno o más archivos .md para explorar tu knowledge base.")
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
                cats_html = " · ".join(note["categories"])
                date_label = note["date"] or "sin fecha"

                label = f"📄 {note['title']}  —  {date_label}  ({note['word_count']} palabras)"

                with st.expander(label):
                    if tags_html:
                        st.markdown(f"**Tags:** {tags_html}")
                    st.markdown(f"**Categorías:** {cats_html}")
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
