"""
Módulo: Gamboa Generator
Sección: Account
Input: SQP.xlsx (multi-mes), BR.csv by ASIN semanal, Inventory (opcional), Categorías (auto)
Output: HTML estilo Gamboa listo para publicar / compartir
"""
import io
from datetime import datetime

import pandas as pd
import streamlit as st

from modules.gamboa.parsers import (
    parse_sqp_multi,
    parse_br_multi,
    parse_inventory,
    load_categories,
    save_categories,
    generate_category_template,
)
from modules.gamboa.generator import (
    enrich_sqp,
    enrich_br,
    generate_html,
    get_filename,
    _slug_client,
)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UI
# ══════════════════════════════════════════════════════════════════════════════

def _header():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📊</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>Gamboa Generator</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Genera un reporte integral HTML con SQP mensual (15 meses) + BR semanal (68 sem) "
        "estilo dashboard interactivo.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _how_to_use():
    """Expander de ayuda — patrón Capybaras (🎯 Para qué sirve / 📁 Archivo necesario / ➡️ Siguiente paso + Pasos)."""
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("🎯 **Para qué sirve**")
            st.markdown(
                "<div style='font-size:0.88rem;color:#555;'>"
                "Generar un reporte integral HTML estilo dashboard interactivo con "
                "performance de SQP mensual + BR semanal, listo para compartir con el cliente."
                "</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown("📁 **Archivos necesarios**")
            st.markdown(
                "<div style='font-size:0.88rem;color:#555;'>"
                "SQP mensual (Brand Analytics) + BR semanal by ASIN + Inventory (opcional) "
                "+ mapeo ASIN→Categoría (persistente en <code>notes/brands/</code>)."
                "</div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown("➡️ **Siguiente paso**")
            st.markdown(
                "<div style='font-size:0.88rem;color:#555;'>"
                "Subir HTML a Hostinger (ver <code>SOPReportesHostinger.md</code>) "
                "o enviar al cliente por email / WhatsApp."
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("")
        st.markdown("▶️ **Pasos:**")
        st.markdown(
            """
1. Ingresá **Cliente/Marca**, **Mercado** y **Etiqueta fecha** (aparece en el hero del reporte)
2. Subí uno o varios **SQP mensuales** (Brand Analytics → Search Query Performance) — el mes se auto-detecta por nombre de archivo o columna `Reporting Range`
3. Subí uno o varios **BR semanales** (Business Reports → By ASIN → Child Item) — un archivo por semana, la semana ISO se auto-detecta por nombre o fecha interna
4. _Opcional:_ subí **Inventory Report** para que el reporte muestre SKUs reales en vez de ASINs
5. _Primera vez con un cliente:_ descargá la plantilla de categorías → completá la columna `category` en Excel → subila de vuelta (se guarda en `notes/brands/{cliente}/gamboa_categories.csv` y no hay que repetirlo)
6. Click **🎨 Generar HTML** → descargar → compartir
            """
        )


def _empty_state():
    st.markdown(
        "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
        "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
        "<div style='font-size:1.5rem;'>📂</div>"
        "<div style='font-weight:600;margin-top:0.5rem;'>Subí al menos 1 SQP y 1 BR semanal</div>"
        "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
        "SQP: Brand Analytics → Search Query Performance. "
        "BR: Business Reports → By ASIN → Child Item (un archivo por semana)."
        "</div></div>",
        unsafe_allow_html=True,
    )


def _info_box(title: str, body: str, color: str = "#E7F3FE"):
    st.markdown(
        f"<div style='background:{color};border-radius:8px;padding:0.75rem 1rem;"
        f"margin:0.5rem 0;font-size:0.9rem;'>"
        f"<strong>{title}</strong><br>{body}</div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# RENDER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def render():
    _header()
    _how_to_use()

    # ── Cliente y configuración básica ────────────────────────────────────────
    cfg_col1, cfg_col2, cfg_col3 = st.columns([2, 1, 1])
    with cfg_col1:
        client_name = st.text_input(
            "Cliente / Marca",
            value=st.session_state.get("gmb_client", ""),
            placeholder="Ej: Gamboa, Dermaglos, LTD...",
            key="gmb_client_input",
        )
    with cfg_col2:
        market = st.selectbox(
            "Mercado",
            options=["US", "MX", "CA", "BR", "UK", "DE", "ES"],
            index=0,
            key="gmb_market",
        )
    with cfg_col3:
        lang_period = st.text_input(
            "Etiqueta fecha",
            value=f"{['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][datetime.now().month-1]} {datetime.now().year}",
            help="Aparece en el hero del reporte",
            key="gmb_date_label",
        )

    if not client_name:
        st.info("👆 Primero ingresá el nombre del cliente — se usa como identificador para el mapeo de categorías persistente.")
        return

    st.session_state["gmb_client"] = client_name
    client_slug = _slug_client(client_name)

    st.markdown("---")

    # ── Uploaders ─────────────────────────────────────────────────────────────
    up_col1, up_col2 = st.columns(2)

    with up_col1:
        st.markdown("**📊 SQP — Search Query Performance** (obligatorio, multi-mes)")
        sqp_files = st.file_uploader(
            "Brand Analytics → SQP (un archivo por mes, o uno con rango)",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            key="gmb_sqp_files",
        )

    with up_col2:
        st.markdown("**📈 BR semanal by ASIN** (obligatorio, multi-semana)")
        br_files = st.file_uploader(
            "Business Reports → By ASIN Child Item (un archivo por semana)",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="gmb_br_files",
        )

    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        st.markdown("**📦 Inventory Report** _(opcional — para mapeo SKU↔ASIN)_")
        inv_file = st.file_uploader(
            "Si no lo subís, se usa el ASIN como identificador",
            type=["txt", "csv", "tsv", "xlsx"],
            accept_multiple_files=False,
            key="gmb_inv_file",
        )
    with opt_col2:
        st.markdown("**🏷️ Categorías ASIN→Categoría** _(persistente en `notes/brands/`)_")
        cat_override_file = st.file_uploader(
            "Subí un CSV (asin,category) para actualizar el mapeo guardado",
            type=["csv"],
            accept_multiple_files=False,
            key="gmb_cat_file",
        )

    if not (sqp_files and br_files):
        _empty_state()
        return

    # ── Parse ─────────────────────────────────────────────────────────────────
    with st.spinner("Parseando SQP..."):
        sqp_df, months_found, sqp_warnings = parse_sqp_multi(sqp_files)

    with st.spinner("Parseando BR semanales..."):
        br_df, weeks_found, br_warnings = parse_br_multi(br_files)

    # Mostrar resumen parseo
    st.markdown("### 📋 Resumen del parseo")
    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        st.metric("Queries SQP", f"{len(sqp_df):,}")
    with rc2:
        st.metric("Meses detectados", len(months_found))
    with rc3:
        st.metric("Filas BR", f"{len(br_df):,}")
    with rc4:
        st.metric("Semanas detectadas", len(weeks_found))

    with st.expander("🔍 Ver meses y semanas detectadas", expanded=False):
        st.write(f"**Meses SQP:** {', '.join(months_found) if months_found else '—'}")
        st.write(f"**Semanas BR:** {', '.join(weeks_found) if weeks_found else '—'}")

    # Warnings
    all_warnings = sqp_warnings + br_warnings
    if all_warnings:
        with st.expander(f"⚠️ {len(all_warnings)} warning(s) durante el parseo", expanded=False):
            for w in all_warnings:
                st.markdown(f"- {w}")

    if sqp_df.empty or br_df.empty:
        st.error("No se pudo extraer data suficiente. Revisá los archivos subidos.")
        return

    # ── Inventory (SKU mapping) ───────────────────────────────────────────────
    asin_sku_map = {}
    if inv_file is not None:
        with st.spinner("Parseando Inventory Report..."):
            asin_sku_map = parse_inventory(inv_file.read(), inv_file.name)
        if asin_sku_map:
            _info_box(
                "✅ Inventory cargado",
                f"{len(asin_sku_map)} ASINs con SKU mapeado. Los que no estén en Inventory usan ASIN como fallback.",
                color="#E8F5E9",
            )
        else:
            _info_box(
                "⚠️ Inventory sin mapeo útil",
                "No encontré columnas ASIN + SKU. Se usa ASIN como identificador.",
                color="#FFF3E0",
            )

    # ── Categorías ────────────────────────────────────────────────────────────
    br_asins = sorted(set(br_df["asin"].astype(str).str.strip()))

    # Si subió override: guardar primero
    if cat_override_file is not None:
        try:
            df_ovr = pd.read_csv(cat_override_file)
            asin_col = next((c for c in df_ovr.columns if c.lower() in ("asin", "asin1")), None)
            cat_col = next((c for c in df_ovr.columns if c.lower() in ("category", "categoria", "cat")), None)
            if asin_col and cat_col:
                new_map = dict(zip(df_ovr[asin_col].astype(str).str.strip(),
                                   df_ovr[cat_col].astype(str).str.strip()))
                new_map = {a: c for a, c in new_map.items() if a and c}
                existing = load_categories(client_slug)
                existing.update(new_map)
                saved_path = save_categories(client_slug, existing)
                _info_box(
                    "✅ Categorías guardadas",
                    f"Actualizado `{saved_path}` con {len(new_map)} mapeos.",
                    color="#E8F5E9",
                )
            else:
                _info_box("⚠️ CSV inválido",
                          "Falta columna 'asin' o 'category'. No se actualizó.",
                          color="#FFEBEE")
        except Exception as e:
            st.error(f"Error leyendo CSV de categorías: {e}")

    asin_category_map = load_categories(client_slug)

    # Diagnóstico de coverage
    missing = [a for a in br_asins if a not in asin_category_map]
    coverage_pct = (1 - len(missing) / len(br_asins)) * 100 if br_asins else 0

    st.markdown("### 🏷️ Mapeo de categorías")
    cat_c1, cat_c2 = st.columns([3, 1])
    with cat_c1:
        if asin_category_map:
            _info_box(
                f"Cobertura: {coverage_pct:.1f}% ({len(asin_category_map)}/{len(br_asins)} ASINs)",
                f"Archivo: `notes/brands/{client_slug}/gamboa_categories.csv` · "
                f"{len(missing)} ASINs sin categoría (quedarán como **'Sin Categorizar'**)",
                color="#E7F3FE" if coverage_pct >= 80 else "#FFF3E0",
            )
        else:
            _info_box(
                f"🆕 No hay mapeo de categorías para '{client_name}'",
                f"Descargá la plantilla → completá la columna 'category' → subila arriba. "
                f"Mientras tanto, todos los ASINs quedarán como **'Sin Categorizar'**.",
                color="#FFF3E0",
            )
    with cat_c2:
        template_csv = generate_category_template(client_slug, br_asins)
        st.download_button(
            "⬇️ Plantilla categorías",
            data=template_csv,
            file_name=f"{client_slug}_categories_template.csv",
            mime="text/csv",
            use_container_width=True,
            key="gmb_dl_cat_template",
        )

    # ── Enriquecer data ───────────────────────────────────────────────────────
    sqp_enriched = enrich_sqp(sqp_df, asin_category_map)
    br_enriched = enrich_br(br_df, asin_sku_map, asin_category_map)

    # ── Preview categorías detectadas ─────────────────────────────────────────
    cats_sqp = sqp_enriched["cat"].value_counts().head(10)
    cats_br = br_enriched["cat"].value_counts().head(10)
    with st.expander("👀 Preview — categorías asignadas", expanded=False):
        pc1, pc2 = st.columns(2)
        with pc1:
            st.markdown("**SQP (top 10):**")
            st.dataframe(cats_sqp.rename("queries"), use_container_width=True, height=280)
        with pc2:
            st.markdown("**BR (top 10):**")
            st.dataframe(cats_br.rename("filas"), use_container_width=True, height=280)

    # ── Generar HTML ──────────────────────────────────────────────────────────
    st.markdown("---")
    gen_col1, gen_col2 = st.columns([3, 1])
    with gen_col1:
        st.markdown("### 🚀 Generar reporte HTML")
        st.markdown(
            f"Va a producir: **{len(sqp_enriched):,} queries** × **{len(months_found)} meses** "
            f"+ **{len(br_enriched):,} filas** × **{len(weeks_found)} semanas** = "
            f"reporte integral para **{client_name}** ({market})."
        )
    with gen_col2:
        if st.button("🎨 Generar HTML", type="primary", use_container_width=True, key="gmb_generate"):
            st.session_state["gmb_do_generate"] = True

    if st.session_state.get("gmb_do_generate"):
        with st.spinner("Generando HTML... (puede tardar unos segundos con datasets grandes)"):
            try:
                html = generate_html(
                    sqp_df=sqp_enriched,
                    br_df=br_enriched,
                    client_name=client_name,
                    market=market,
                    generated_label=lang_period,
                )
                filename = get_filename(client_name)

                st.success(f"✅ HTML generado: **{len(html)/1024:.1f} KB** · `{filename}`")

                st.download_button(
                    "⬇️ Descargar HTML",
                    data=html.encode("utf-8"),
                    file_name=filename,
                    mime="text/html",
                    use_container_width=True,
                    key="gmb_dl_html",
                )

                # Preview inline (opcional — para datasets chicos funciona)
                if len(html) < 10 * 1024 * 1024:  # < 10MB
                    with st.expander("👁️ Preview inline (puede tardar)", expanded=False):
                        st.components.v1.html(html, height=900, scrolling=True)
                else:
                    st.info("ℹ️ Preview inline desactivado porque el HTML pesa más de 10MB. Descargalo y abrilo en el browser.")

                # Reset flag
                st.session_state["gmb_do_generate"] = False

            except Exception as e:
                st.error(f"❌ Error al generar: {e}")
                import traceback
                with st.expander("Traceback"):
                    st.code(traceback.format_exc())
                st.session_state["gmb_do_generate"] = False
