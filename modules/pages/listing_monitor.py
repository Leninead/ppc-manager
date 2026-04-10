"""
modules/pages/listing_monitor.py
Listing Monitor — monitoreo de ASINs de Amazon con alertas de cambios.
Capybaras Agency · 2026
"""

import streamlit as st
import pandas as pd
import json
import os
import re
import time
from datetime import datetime

from core.helpers import kpi_card

# ── Deps opcionales ──────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    _SCRAPE_OK = True
except ImportError:
    _SCRAPE_OK = False

# ── Paleta Capybaras ─────────────────────────────────────────────────
_ORG   = "#E84000"
_ORG_P = "#FFF3E0"
_NEGRO = "#1F1F1F"
_GRN   = "#1B6B2F"
_GRN_L = "#E8F5E9"
_RED   = "#B71C1C"
_RED_L = "#FFEBEE"
_YEL   = "#9C5700"
_YEL_L = "#FFEB9C"
_GRAY  = "#F7FAFC"
_MGRAY = "#CBD5E0"

# ── Constantes ───────────────────────────────────────────────────────
_SNAPSHOT_DIR = "data/listing_snapshots"
_SNAPSHOT_FILE = os.path.join(_SNAPSHOT_DIR, "snapshots.json")

_MARKETPLACES = {
    "🇲🇽 Amazon México (MX)":     "https://www.amazon.com.mx/dp/",
    "🇺🇸 Amazon USA (COM)":        "https://www.amazon.com/dp/",
    "🇪🇸 Amazon España (ES)":      "https://www.amazon.es/dp/",
    "🇧🇷 Amazon Brasil (BR)":      "https://www.amazon.com.br/dp/",
    "🇨🇦 Amazon Canadá (CA)":      "https://www.amazon.ca/dp/",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Helpers de snapshot ──────────────────────────────────────────────

def _load_snapshots() -> dict:
    """Carga el JSON de snapshots. Retorna dict vacío si no existe."""
    if not os.path.exists(_SNAPSHOT_FILE):
        return {}
    try:
        with open(_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_snapshots(data: dict) -> None:
    """Guarda el JSON de snapshots al disco."""
    os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
    with open(_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _snapshot_key(asin: str, marketplace: str) -> str:
    """Genera la clave única por ASIN + marketplace."""
    mkt_code = re.sub(r"[^a-zA-Z]", "", marketplace.split("(")[-1].replace(")", ""))
    return f"{asin.strip().upper()}_{mkt_code.upper()}"


# ── Scraper ──────────────────────────────────────────────────────────

def _scrape_asin(asin: str, base_url: str) -> dict:
    """
    Scrapea un ASIN de Amazon y retorna un dict con los campos monitoreados.
    Retorna dict con error=True si falla.
    """
    url = f"{base_url}{asin.strip().upper()}"
    result = {
        "asin": asin.strip().upper(),
        "url": url,
        "scraped_at": datetime.now().isoformat(),
        "titulo": None,
        "precio": None,
        "reviews_count": None,
        "rating": None,
        "badge": None,
        "bullets": [],
        "stock_status": None,
        "error": False,
        "error_msg": "",
    }

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code == 503:
            result["error"] = True
            result["error_msg"] = "Amazon bloqueó la solicitud (503). Intentá de nuevo en unos minutos."
            return result
        if resp.status_code != 200:
            result["error"] = True
            result["error_msg"] = f"HTTP {resp.status_code}"
            return result

        soup = BeautifulSoup(resp.content, "html.parser")

        # ── Precio ──────────────────────────────────────────────────
        precio = None
        for selector in [
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price .a-offscreen",
            "#price_inside_buybox",
            "#apex_offeringDisplayGroup .a-price .a-offscreen",
        ]:
            el = soup.select_one(selector)
            if el:
                precio = el.get_text(strip=True)
                break
        result["precio"] = precio

        # ── Título ──────────────────────────────────────────────────
        titulo_el = soup.select_one("#productTitle, #title")
        if titulo_el:
            result["titulo"] = titulo_el.get_text(strip=True)[:80]

        # ── Reviews y rating ────────────────────────────────────────
        rating_el = soup.select_one("#acrPopover, [data-hook='rating-out-of-text']")
        if rating_el:
            txt = rating_el.get("title", "") or rating_el.get_text(strip=True)
            m = re.search(r"(\d[.,]\d)", txt)
            if m:
                result["rating"] = m.group(1).replace(",", ".")

        reviews_el = soup.select_one(
            "#acrCustomerReviewText, [data-hook='total-review-count']"
        )
        if reviews_el:
            txt = reviews_el.get_text(strip=True)
            m = re.search(r"[\d,\.]+", txt.replace(".", "").replace(",", ""))
            if m:
                result["reviews_count"] = int(re.sub(r"\D", "", m.group()))

        # ── Badge BSR / Amazon's Choice ─────────────────────────────
        badges = []
        if soup.select_one("#SalesRank, #detailBulletsWrapper_feature_div"):
            bsr_section = soup.select_one("#SalesRank") or soup.select_one(
                "#detailBulletsWrapper_feature_div"
            )
            if bsr_section and "Best Seller" in bsr_section.get_text():
                badges.append("🥇 Best Seller")
        if soup.select_one("[id*='acBadge'], .ac-badge-wrapper, #acBadge_feature_div"):
            badges.append("✅ Amazon's Choice")
        result["badge"] = ", ".join(badges) if badges else "—"

        # ── Bullets ─────────────────────────────────────────────────
        bullets_el = soup.select("#feature-bullets li span.a-list-item")
        bullets = [b.get_text(strip=True) for b in bullets_el if b.get_text(strip=True)]
        result["bullets"] = bullets[:6]  # máx 6

        # ── Stock ────────────────────────────────────────────────────
        stock_el = soup.select_one(
            "#availability span, #outOfStock, #add-to-cart-button"
        )
        if stock_el:
            txt = stock_el.get_text(strip=True).lower()
            if "disponible" in txt or "stock" in txt or "add to cart" in txt or "agregar" in txt:
                result["stock_status"] = "✅ En stock"
            elif "agotado" in txt or "out of stock" in txt or "unavailable" in txt:
                result["stock_status"] = "❌ Sin stock"
            else:
                result["stock_status"] = txt[:40]
        else:
            add_btn = soup.select_one("#add-to-cart-button")
            result["stock_status"] = "✅ En stock" if add_btn else "⚠️ No detectado"

    except requests.exceptions.Timeout:
        result["error"] = True
        result["error_msg"] = "Timeout — Amazon tardó más de 12s"
    except Exception as e:
        result["error"] = True
        result["error_msg"] = str(e)[:120]

    return result


# ── Comparador de cambios ─────────────────────────────────────────────

def _detect_changes(prev: dict, curr: dict) -> list[dict]:
    """
    Compara snapshot anterior vs actual.
    Retorna lista de dicts con {campo, anterior, actual, tipo}.
    tipo: 'alerta' | 'info' | 'ok'
    """
    cambios = []

    # Precio
    if prev.get("precio") != curr.get("precio"):
        tipo = "alerta" if curr.get("precio") is None else "info"
        cambios.append({
            "campo": "💲 Precio",
            "anterior": prev.get("precio") or "—",
            "actual": curr.get("precio") or "—",
            "tipo": tipo,
        })

    # Rating
    try:
        r_prev = float(prev.get("rating") or 0)
        r_curr = float(curr.get("rating") or 0)
        if abs(r_prev - r_curr) >= 0.1:
            tipo = "alerta" if r_curr < r_prev else "info"
            cambios.append({
                "campo": "⭐ Rating",
                "anterior": str(r_prev) if r_prev else "—",
                "actual": str(r_curr) if r_curr else "—",
                "tipo": tipo,
            })
    except Exception:
        pass

    # Reviews
    try:
        rv_prev = int(prev.get("reviews_count") or 0)
        rv_curr = int(curr.get("reviews_count") or 0)
        diff = rv_curr - rv_prev
        if abs(diff) > 0:
            cambios.append({
                "campo": "💬 Reseñas",
                "anterior": f"{rv_prev:,}",
                "actual": f"{rv_curr:,} ({'+' if diff > 0 else ''}{diff:,})",
                "tipo": "ok" if diff > 0 else "info",
            })
    except Exception:
        pass

    # Badge
    if prev.get("badge") != curr.get("badge"):
        tipo = "alerta" if "Best Seller" not in (curr.get("badge") or "") else "ok"
        cambios.append({
            "campo": "🏅 Badge",
            "anterior": prev.get("badge") or "—",
            "actual": curr.get("badge") or "—",
            "tipo": tipo,
        })

    # Stock
    if prev.get("stock_status") != curr.get("stock_status"):
        tipo = "alerta" if "Sin stock" in (curr.get("stock_status") or "") else "ok"
        cambios.append({
            "campo": "📦 Stock",
            "anterior": prev.get("stock_status") or "—",
            "actual": curr.get("stock_status") or "—",
            "tipo": tipo,
        })

    # Bullets — detectar si cambió cantidad o texto del primero
    prev_b = prev.get("bullets", [])
    curr_b = curr.get("bullets", [])
    if len(prev_b) != len(curr_b):
        cambios.append({
            "campo": "📝 Bullets",
            "anterior": f"{len(prev_b)} bullets",
            "actual": f"{len(curr_b)} bullets",
            "tipo": "info",
        })
    elif prev_b and curr_b and prev_b[0] != curr_b[0]:
        cambios.append({
            "campo": "📝 Bullets",
            "anterior": prev_b[0][:60] + "…",
            "actual": curr_b[0][:60] + "…",
            "tipo": "info",
        })

    return cambios


# ── Helpers de UI ────────────────────────────────────────────────────

def _badge_chip(text: str, bg: str, fg: str = "#fff") -> str:
    return (
        f"<span style='background:{bg};color:{fg};border-radius:4px;"
        f"padding:2px 8px;font-size:0.72rem;font-weight:700;"
        f"display:inline-block;margin:1px;'>{text}</span>"
    )


def _cambio_row_color(tipo: str) -> str:
    return {
        "alerta": _RED_L,
        "info":   _YEL_L,
        "ok":     _GRN_L,
    }.get(tipo, "#fff")


def _resumen_alertas(cambios: list) -> str:
    n_alerta = sum(1 for c in cambios if c["tipo"] == "alerta")
    n_info   = sum(1 for c in cambios if c["tipo"] == "info")
    n_ok     = sum(1 for c in cambios if c["tipo"] == "ok")
    parts = []
    if n_alerta: parts.append(_badge_chip(f"⚠️ {n_alerta} alerta{'s' if n_alerta>1 else ''}", _RED,   "#fff"))
    if n_info:   parts.append(_badge_chip(f"ℹ️ {n_info} cambio{'s' if n_info>1 else ''}",    _YEL,   "#fff"))
    if n_ok:     parts.append(_badge_chip(f"✅ {n_ok} positivo{'s' if n_ok>1 else ''}",       _GRN,   "#fff"))
    if not parts: parts.append(_badge_chip("Sin cambios", "#888", "#fff"))
    return " ".join(parts)


# ── Render principal ─────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        f"<h2 style='color:{_NEGRO};font-size:1.4rem;font-weight:800;"
        f"margin-bottom:0.2rem;'>👁️ Listing Monitor</h2>"
        f"<p style='color:#666;font-size:0.85rem;margin-top:0;'>"
        f"Monitoreá precio, reseñas, badge y bullets de tus ASINs — "
        f"con alertas de cambios semana a semana.</p>",
        unsafe_allow_html=True,
    )

    # ── Check dependencias ───────────────────────────────────────────
    if not _SCRAPE_OK:
        st.error(
            "**Faltan dependencias.** Corré en tu terminal:\n\n"
            "```bash\npip install requests beautifulsoup4\n```\n\n"
            "Después reiniciá Streamlit."
        )
        return

    snapshots = _load_snapshots()

    tab1, tab2, tab3 = st.tabs(["🔍 Escanear ASINs", "📊 Ver Alertas", "🗂️ Historial"])

    # ════════════════════════════════════════════════════════════════
    # TAB 1 — Escanear
    # ════════════════════════════════════════════════════════════════
    with tab1:
        c1, c2 = st.columns([2, 1])

        with c1:
            asins_raw = st.text_area(
                "ASINs a monitorear (uno por línea)",
                height=160,
                placeholder="B0CYLDSQ5L\nB09XYZ1234\nB08ABC5678",
                key="lm_asins_input",
                help="Pegá los ASINs de los productos que querés monitorear.",
            )

        with c2:
            marketplace_label = st.selectbox(
                "Marketplace",
                list(_MARKETPLACES.keys()),
                key="lm_marketplace",
            )
            delay_seg = st.slider(
                "Pausa entre requests (seg)",
                min_value=2, max_value=10, value=4,
                help="Más pausa = menos riesgo de bloqueo de Amazon.",
                key="lm_delay",
            )
            guardar_auto = st.checkbox(
                "Guardar snapshot automáticamente al escanear",
                value=True,
                key="lm_save_auto",
            )

        asins = [a.strip().upper() for a in asins_raw.strip().splitlines() if a.strip()]

        st.markdown(
            f"<div style='font-size:0.8rem;color:#666;margin-bottom:0.5rem;'>"
            f"{'<b>' + str(len(asins)) + ' ASINs</b> cargados.' if asins else 'Ingresá al menos un ASIN.'}"
            f"</div>",
            unsafe_allow_html=True,
        )

        if st.button(
            f"🚀 Escanear {len(asins)} ASIN{'s' if len(asins) != 1 else ''}",
            disabled=not asins,
            use_container_width=True,
            key="lm_btn_scan",
            type="primary",
        ):
            base_url = _MARKETPLACES[marketplace_label]
            resultados = []
            cambios_map = {}

            prog = st.progress(0, text="Iniciando escaneo…")
            status_box = st.empty()

            for i, asin in enumerate(asins):
                status_box.info(f"Escaneando **{asin}** ({i+1}/{len(asins)})…")
                data = _scrape_asin(asin, base_url)

                key = _snapshot_key(asin, marketplace_label)
                prev_snap = snapshots.get(key)
                cambios = _detect_changes(prev_snap, data) if prev_snap else []
                cambios_map[asin] = cambios

                resultados.append({
                    "asin": asin,
                    "data": data,
                    "prev": prev_snap,
                    "cambios": cambios,
                    "key": key,
                })

                if guardar_auto and not data["error"]:
                    snapshots[key] = data
                    _save_snapshots(snapshots)

                prog.progress((i + 1) / len(asins), text=f"Escaneado {i+1}/{len(asins)}")
                if i < len(asins) - 1:
                    time.sleep(delay_seg)

            prog.empty()
            status_box.empty()

            # ── Guardar en session_state para Tab 2 ─────────────────
            st.session_state["lm_resultados"] = resultados
            st.session_state["lm_marketplace_result"] = marketplace_label

            # ── Resumen del escaneo ──────────────────────────────────
            n_ok  = sum(1 for r in resultados if not r["data"]["error"])
            n_err = sum(1 for r in resultados if r["data"]["error"])
            n_con_cambios = sum(1 for r in resultados if r["cambios"])

            cols = st.columns(3)
            with cols[0]:
                st.markdown(kpi_card("Escaneados OK", str(n_ok)), unsafe_allow_html=True)
            with cols[1]:
                st.markdown(kpi_card("Con cambios", str(n_con_cambios)), unsafe_allow_html=True)
            with cols[2]:
                st.markdown(kpi_card("Errores", str(n_err)), unsafe_allow_html=True)

            if n_err:
                with st.expander("Ver errores"):
                    for r in resultados:
                        if r["data"]["error"]:
                            st.error(f"**{r['asin']}** — {r['data']['error_msg']}")

            st.success(
                f"Escaneo completado. "
                f"{'Snapshots guardados automáticamente.' if guardar_auto else 'Snapshots NO guardados (desactivado).'}"
            )
            st.info("👉 Andá a la tab **📊 Ver Alertas** para ver los cambios detectados.")

    # ════════════════════════════════════════════════════════════════
    # TAB 2 — Ver Alertas
    # ════════════════════════════════════════════════════════════════
    with tab2:
        resultados = st.session_state.get("lm_resultados", [])

        if not resultados:
            st.info("Todavía no escaneaste ningún ASIN. Andá a **🔍 Escanear ASINs** primero.")
        else:
            mkt = st.session_state.get("lm_marketplace_result", "")
            st.markdown(
                f"<div style='font-size:0.8rem;color:#666;margin-bottom:1rem;'>"
                f"Último escaneo: <b>{len(resultados)} ASINs</b> — {mkt}</div>",
                unsafe_allow_html=True,
            )

            # ── Filtro rápido ────────────────────────────────────────
            filtro = st.radio(
                "Mostrar",
                ["Todos", "Solo con cambios", "Solo alertas 🔴"],
                horizontal=True,
                key="lm_filtro_alertas",
            )

            for r in resultados:
                data    = r["data"]
                cambios = r["cambios"]
                prev    = r.get("prev")
                asin    = r["asin"]

                if filtro == "Solo con cambios" and not cambios:
                    continue
                if filtro == "Solo alertas 🔴" and not any(c["tipo"] == "alerta" for c in cambios):
                    continue

                # Build expander label with titulo if available
                _titulo = data.get("titulo") or ""
                _asin_label = f"{asin} — {_titulo[:50]}" if _titulo else asin

                with st.expander(
                    f"{'❌' if data['error'] else ('🔴' if any(c['tipo']=='alerta' for c in cambios) else ('🟡' if cambios else '🟢'))} "
                    f"**{_asin_label}** — {_resumen_alertas(cambios) if not data['error'] else '❌ Error de scraping'}",
                    expanded=any(c["tipo"] == "alerta" for c in cambios),
                ):
                    if data["error"]:
                        st.error(f"Error al scrapear: {data['error_msg']}")
                        continue

                    # ── Datos actuales ───────────────────────────────
                    d1, d2, d3, d4, d5 = st.columns(5)
                    with d1:
                        st.markdown(kpi_card("Precio", data.get("precio") or "—"), unsafe_allow_html=True)
                    with d2:
                        st.markdown(kpi_card("Rating", data.get("rating") or "—"), unsafe_allow_html=True)
                    with d3:
                        rv = f"{data.get('reviews_count', 0):,}" if data.get("reviews_count") else "—"
                        st.markdown(kpi_card("Reseñas", rv), unsafe_allow_html=True)
                    with d4:
                        st.markdown(kpi_card("Badge", data.get("badge") or "—"), unsafe_allow_html=True)
                    with d5:
                        st.markdown(kpi_card("Stock", data.get("stock_status") or "—"), unsafe_allow_html=True)

                    # ── Tabla de cambios ─────────────────────────────
                    if cambios:
                        st.markdown("**Cambios vs snapshot anterior:**")
                        rows_html = ""
                        for c in cambios:
                            bg = _cambio_row_color(c["tipo"])
                            rows_html += (
                                f"<tr style='background:{bg};'>"
                                f"<td style='padding:6px 10px;font-weight:600;'>{c['campo']}</td>"
                                f"<td style='padding:6px 10px;color:#666;'>{c['anterior']}</td>"
                                f"<td style='padding:6px 10px;'>→</td>"
                                f"<td style='padding:6px 10px;font-weight:700;'>{c['actual']}</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            f"<table style='width:100%;border-collapse:collapse;"
                            f"font-size:0.82rem;border-radius:6px;overflow:hidden;'>"
                            f"<thead><tr style='background:{_NEGRO};color:#fff;'>"
                            f"<th style='padding:6px 10px;text-align:left;'>Campo</th>"
                            f"<th style='padding:6px 10px;text-align:left;'>Anterior</th>"
                            f"<th></th>"
                            f"<th style='padding:6px 10px;text-align:left;'>Actual</th>"
                            f"</tr></thead><tbody>{rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )
                    elif prev:
                        st.success("Sin cambios vs el snapshot anterior. ✅")
                    else:
                        st.info("Primer snapshot guardado. La próxima semana verás los cambios aquí.")

                    # ── Bullets actuales ─────────────────────────────
                    if data.get("bullets"):
                        with st.expander("Ver bullets actuales"):
                            for b in data["bullets"]:
                                st.markdown(f"• {b}")

                    # ── Link directo ─────────────────────────────────
                    st.markdown(
                        f"<a href='{data['url']}' target='_blank' "
                        f"style='font-size:0.75rem;color:{_ORG};'>🔗 Ver en Amazon</a>",
                        unsafe_allow_html=True,
                    )

    # ════════════════════════════════════════════════════════════════
    # TAB 3 — Historial de snapshots guardados
    # ════════════════════════════════════════════════════════════════
    with tab3:
        snapshots_fresh = _load_snapshots()

        if not snapshots_fresh:
            st.info("No hay snapshots guardados todavía. Escaneá ASINs primero.")
        else:
            st.markdown(
                f"<div style='font-size:0.8rem;color:#666;margin-bottom:1rem;'>"
                f"<b>{len(snapshots_fresh)}</b> snapshots guardados en "
                f"<code>{_SNAPSHOT_FILE}</code></div>",
                unsafe_allow_html=True,
            )

            # ── Tabla resumen ────────────────────────────────────────
            rows = []
            for k, v in snapshots_fresh.items():
                rows.append({
                    "Clave": k,
                    "ASIN": v.get("asin", "—"),
                    "Producto": (v.get("titulo") or "—")[:40],
                    "Precio": v.get("precio") or "—",
                    "Rating": v.get("rating") or "—",
                    "Reseñas": v.get("reviews_count") or "—",
                    "Badge": v.get("badge") or "—",
                    "Stock": v.get("stock_status") or "—",
                    "Guardado": v.get("scraped_at", "—")[:16].replace("T", " "),
                })

            df_hist = pd.DataFrame(rows)
            st.dataframe(df_hist, use_container_width=True, hide_index=True)

            # ── Borrar snapshots ─────────────────────────────────────
            st.divider()
            with st.expander("⚠️ Borrar snapshots"):
                st.warning("Esto borra el historial. No podrás comparar cambios hasta el próximo escaneo.")
                if st.button("🗑️ Borrar todos los snapshots", key="lm_delete_all"):
                    _save_snapshots({})
                    st.success("Snapshots borrados.")
                    st.rerun()