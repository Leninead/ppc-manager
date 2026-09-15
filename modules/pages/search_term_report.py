import html
import io
import logging
import re
import unicodedata
from functools import partial
from types import SimpleNamespace

import numpy as np
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

from ai.agent_call import build_agent_call
from core.ai_analysis.chat_context import (
    PREVIOUS_ANALYSES,
    analysis_chat_documents,
    current_analysis_text,
    in_memory_analysis,
)
from core.ai_analysis.store import TRIGGER_SCHEDULED, AiAnalysisStore
from core.bulk_export import build_adgroup_negative, write_bulk_excel
from core.integrations.store import StoreError
from core.integrations.sync_jobs import SyncJobStore
from core.currency_format import currency_symbol, money
from core.excel_text import force_text_cells
from core.helpers import kpi_card
from core.search_term_analysis import (
    ANALYSIS_MODULE,
    CANONICAL_LANG,
    CANONICAL_WINDOW_DAYS,
    DEFAULT_HARVEST_MIN_CLICKS,
    DEFAULT_PRODUCT_PRICE,
    DEFAULT_TARGET_ACOS,
    StrAnalysisParams,
    build_analysis_input,
    normalized_brand_terms,
    rule_two_cvr,
    sorted_harvest,
)
from core.search_term_analysis import detect_columns as _detect_cols
from core.search_term_analysis import harvest_candidate_rows as _harvest_candidate_rows
from core.search_term_analysis import negative_candidate_rows as _negative_candidate_rows
from core.search_term_analysis import numeric_column as _to_num
from core.search_term_analysis import uses_dollar_price as _uses_dollar_price
from core.search_term_frame import SOURCE_FILE
from core.search_term_negatives import (
    ACTION_NEGATIVE,
    AD_GROUP_STATE_UNVERIFIED_NOTE,
    EXACT_GUARD_PARTIAL_NOTE,
    ad_group_guards,
    evaluate_candidates,
    negative_key,
    select_for_bulk,
)
from modules.pages import search_term_source
from modules.pages.search_term_source import DISPLAY_TIMEZONE, date_range_label, render_source_picker

log = logging.getLogger(__name__)

DEFAULT_PRIORITY_FILTER = ["Alta", "Media"]
RELEASED_RANKING_KEY = "neg_released_ranking"
LIBERAR_COLUMN = "Liberar"
# Big accounts reach hundreds of thousands of terms: draw and chart a slice, build their files only on request.
TABLE_ROW_LIMIT = 1_000
SCATTER_POINT_LIMIT = 2_000
EAGER_EXPORT_ROW_LIMIT = 5_000
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_VIEW_ORDER_LABELS = {"Winners": "las de menor ACoS", "Top Sales": "las de mayor venta"}

_INPUT_KEYS = (
    "str_portfolio_filter", "str_target_acos_tab1", "str_brand_terms", "str_f_camp", "str_f_match",
    "str_f_acos_max", "str_f_spend_min", "str_vista", "neg_target_acos", "neg_prio_filter",
    "harv_target_acos", "harv_min_clicks", "harv_include_dupes",
)
_PRICE_KEY_PREFIXES = ("neg_precio", "harv_precio")
_PARKED_INPUTS_KEY = "str_parked_inputs"
_PORTFOLIO_OPTIONS_KEY = "str_portfolio_filter_options"


def _price_key(base_key, currency_code):
    """One price input per currency: a price typed for dollars must never carry over to pesos or yen."""
    code = (currency_code or "").strip().upper()
    return base_key if _uses_dollar_price(code) else f"{base_key}_{code}"


def _seed_input(key, default):
    """First value for a widget without a default of its own: Streamlit warns on a default plus a session value."""
    if key not in st.session_state:
        st.session_state[key] = default


def _park_inputs(keys):
    """Re-stores inputs whose widgets are not drawn this run, so Streamlit does not drop what the AM typed."""
    parked = set(st.session_state.get(_PARKED_INPUTS_KEY, ()))
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
            parked.add(key)
    if parked:
        st.session_state[_PARKED_INPUTS_KEY] = tuple(sorted(parked))


def _restore_parked_inputs():
    """Writes parked values again in the run that draws their widgets; unwritten, the page would show defaults."""
    for key in st.session_state.pop(_PARKED_INPUTS_KEY, ()):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _all_input_keys():
    price_keys = [key for key in st.session_state.keys()
                  if isinstance(key, str) and key.startswith(_PRICE_KEY_PREFIXES)]
    return (*_INPUT_KEYS, *price_keys)


def _xlsx_bytes(frame, **to_excel_options):
    """One-sheet .xlsx whose text cells stay text: search terms and campaign names are typed by people."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, **to_excel_options)
        force_text_cells(writer.book)
    return buffer.getvalue()


def released_ranking_keys(previously_released, releasable_exclusions, liberar_flags):
    """Release keys after the AM ticks «Liberar»: rows shown now follow their box, rows not shown keep theirs."""
    shown = {negative_key(exclusion.candidate) for exclusion in releasable_exclusions}
    ticked = {negative_key(exclusion.candidate)
              for exclusion, ticked_box in zip(releasable_exclusions, liberar_flags) if ticked_box}
    return frozenset((set(previously_released) - shown) | ticked)


def _classify_term_type(term, brand_terms):
    """Classify a search term as Brand, Long-tail, or Generic."""
    t = str(term).lower().strip()
    if brand_terms and any(bt in t for bt in brand_terms):
        return "Brand"
    if len(t.split()) >= 4:
        return "Long-tail"
    return "Generic"


def _classify_statuses(frame, target_acos):
    """Action status per row (Escalar / OK / Reducir / Revisar / Negativa? / —), first matching rule wins."""
    spend, sales, orders, clicks = frame["_spend"], frame["_sales"], frame["_orders"], frame["_clicks"]
    acos = (spend / sales.where(sales > 0) * 100).fillna(0)
    conditions = [
        (orders >= 3) & (acos > 0) & (acos < target_acos * 0.5),
        (sales > 0) & (acos <= target_acos),
        (sales > 0) & (acos > target_acos * 1.5),
        (clicks > 10) & (orders == 0),
        (clicks >= 3) & (sales == 0) & (spend > 0),
    ]
    labels = ["Escalar", "OK", "Reducir", "Revisar", "Negativa?"]
    return pd.Series(np.select(conditions, labels, default="—"), index=frame.index)


def _drawn_rows(frame, order_column=None):
    """(the rows to draw, whether some were left out); `order_column` picks the biggest rows of an unordered frame."""
    if len(frame) <= TABLE_ROW_LIMIT:
        return frame, False
    if order_column is not None:
        frame = frame.sort_values(order_column, ascending=False, kind="stable")
    return frame.head(TABLE_ROW_LIMIT), True


def _brand_match_caption(frame, brand_terms, currency_code):
    terms = ", ".join(brand_terms)
    brand_rows = frame["_term_type"] == "Brand"
    matched = int(brand_rows.sum())
    if not matched:
        return f"Marca aplicada ({terms}): ningún término de búsqueda la contiene."
    brand_spend = frame.loc[brand_rows, "_spend"].sum()
    total_spend = frame["_spend"].sum()
    share = f" ({brand_spend / total_spend * 100:.1f}%)" if total_spend > 0 else ""
    return (f"Marca aplicada ({terms}): {_dot_thousands(matched)} de {_dot_thousands(len(frame))} términos la "
            f"contienen · {money(brand_spend, currency_code)} de gasto{share}.")


def _dot_thousands(number):
    return f"{number:,}".replace(",", ".")


def _drawn_rows_caption(total_rows, what, exported_rows=None):
    exported = "todas" if exported_rows is None or exported_rows == total_rows else _dot_thousands(exported_rows)
    return (f"Mostrando {_dot_thousands(TABLE_ROW_LIMIT)} de {_dot_thousands(total_rows)} filas ({what}). "
            f"La descarga en Excel trae {exported}.")


def _harvest_export_rows(harvest, *, include_existing_exact):
    """The harvest rows the Excel carries: without the terms already running as active Exact unless asked for."""
    if include_existing_exact or "Ya en Exact" not in harvest.columns:
        return harvest
    return harvest[harvest["Ya en Exact"] == ""]


def _xlsx_download(label, build, *, file_name, key, row_count, fingerprint):
    """Download button for an .xlsx; past EAGER_EXPORT_ROW_LIMIT rows the file is built only when asked for."""
    if row_count <= EAGER_EXPORT_ROW_LIMIT:
        st.download_button(label, data=build(), file_name=file_name, mime=XLSX_MIME,
                           use_container_width=True, key=key)
        return
    prepared_key = f"{key}_prepared"
    prepared = st.session_state.get(prepared_key)
    if prepared is None or prepared[0] != fingerprint:
        if not st.button(f"Preparar el archivo ({_dot_thousands(row_count)} filas)", key=f"{key}_prepare",
                         use_container_width=True,
                         icon=":material/download:"):
            st.caption("Es un archivo grande: se arma cuando lo pedís y puede tardar un poco.")
            return
        with st.spinner("Armando el archivo…"):
            prepared = (fingerprint, build())
            # Saved before the spinner closes: a widget event during the build stops the run at that st call.
            st.session_state[prepared_key] = prepared
    st.download_button(label, data=prepared[1], file_name=file_name, mime=XLSX_MIME,
                       use_container_width=True, key=key)


def _is_brand_campaign(name):
    """Detect if a campaign name suggests brand/defensive."""
    n = str(name).lower()
    return any(kw in n for kw in ["branded", "brand", "defense", "defensive"])


def _build_str_excel(df_f, df_original, kpi_dict, brand_terms):
    """Genera Excel multi-sheet con STR analizado. Retorna bytes."""
    buf = io.BytesIO()

    # Preparar hoja 1
    df_exp = df_f.copy() if len(df_f) > 0 else df_original.head(0).copy()
    rename_map = {}
    if "_term_type" in df_exp.columns:
        rename_map["_term_type"] = "Tipo Termino"
    if "_estado" in df_exp.columns:
        rename_map["_estado"] = "Estado"
    if rename_map:
        df_exp = df_exp.rename(columns=rename_map)
    drop_cols = [c for c in df_exp.columns if c.startswith("_")]
    df_exp = df_exp.drop(columns=drop_cols, errors="ignore")

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Hoja 1 — siempre
        df_exp.to_excel(writer, sheet_name="STR Analizado", index=False)

        # Hoja 2 — KPIs
        kpi_rows = [[k, v] for k, v in kpi_dict.items()]
        pd.DataFrame(kpi_rows, columns=["Metrica", "Valor"]).to_excel(
            writer, sheet_name="Resumen KPIs", index=False
        )

        # Hoja 3 — Por Estado
        if len(df_f) > 0 and "_estado" in df_f.columns:
            est = df_f.groupby("_estado").agg(
                Terminos=("_estado", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
            ).reset_index().rename(columns={"_estado": "Estado"})
            est["ACoS"] = (est["Spend"] / est["Sales"].replace(0, float("nan")) * 100).fillna(0).round(1)
            est.sort_values("Spend", ascending=False).to_excel(
                writer, sheet_name="Por Estado", index=False
            )

        # Hoja 4 — Por Tipo Término
        if len(df_f) > 0 and "_term_type" in df_f.columns and brand_terms:
            tt = df_f.groupby("_term_type").agg(
                Terminos=("_term_type", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index().rename(columns={"_term_type": "Tipo"})
            tt["ACoS"] = (tt["Spend"] / tt["Sales"].replace(0, float("nan")) * 100).fillna(0).round(1)
            tt["% Spend"] = (tt["Spend"] / tt["Spend"].sum() * 100).round(1)
            if not tt.empty:
                tt.to_excel(writer, sheet_name="Por Tipo Termino", index=False)

        force_text_cells(writer.book)

    return buf.getvalue()


def _amount_unit(currency_code):
    """Unit shown in amount labels: the dollar sign for USD or an unknown currency, else the code."""
    code = (currency_code or "").strip().upper()
    return currency_symbol(code) if code in ("", "USD") else code


def _missing_data_reasons(frame):
    """What each candidate lacks to be applied in Amazon: a campaign name, then an ad group; "" when nothing."""
    campaign_blank = frame["Campaign"].astype(str).str.strip() == ""
    ad_group_blank = frame["Ad Group"].astype(str).str.strip() == ""
    return pd.Series(np.select([campaign_blank, ad_group_blank], ["Sin Campaign Name", "Sin Ad Group"], default=""),
                     index=frame.index)


def _bulk_selected_candidates(candidates, exclusions):
    """The Negativo candidates that made it into the bulk, in the order of select_for_bulk's rows."""
    excluded = {id(exclusion.candidate) for exclusion in exclusions}
    return [candidate for candidate in candidates
            if candidate.action == ACTION_NEGATIVE and id(candidate) not in excluded]


def _bulk_metadata_frame(selected_candidates):
    return pd.DataFrame([{
        "Search Term": candidate.search_term,
        "Campaign": candidate.campaign,
        "Ad Group": candidate.ad_group,
        "Portfolio": candidate.portfolio,
        "Clicks": candidate.clicks,
        "Impressions": candidate.impressions,
        "Spend": candidate.spend,
        "Regla": candidate.rule,
        "Match Type": candidate.match_type,
        "Prioridad": candidate.priority,
    } for candidate in selected_candidates])


def _bulk_exclusion_frame(exclusions):
    return pd.DataFrame([{
        "Search Term": exclusion.candidate.search_term,
        "Campaign": exclusion.candidate.campaign,
        "Ad Group": exclusion.candidate.ad_group,
        "Regla": exclusion.candidate.rule,
        "Motivo": exclusion.reason,
    } for exclusion in exclusions])


def _unique_by_negative_key(exclusions):
    seen = set()
    unique = []
    for exclusion in exclusions:
        key = negative_key(exclusion.candidate)
        if key not in seen:
            seen.add(key)
            unique.append(exclusion)
    return unique


def _release_frame(releasable_exclusions, released):
    return pd.DataFrame([{
        LIBERAR_COLUMN: negative_key(exclusion.candidate) in released,
        "Search Term": exclusion.candidate.search_term,
        "Campaign": exclusion.candidate.campaign,
        "Ad Group": exclusion.candidate.ad_group,
        "Portfolio": exclusion.candidate.portfolio,
        "Regla": exclusion.candidate.rule,
        "Motivo": exclusion.reason,
    } for exclusion in releasable_exclusions])


def _render_release_editor(releasable_exclusions):
    """«Liberar» boxes for the protected-portfolio rows (INV-11.3); returns the keys the AM released."""
    released = frozenset(st.session_state.get(RELEASED_RANKING_KEY, frozenset()))
    if not releasable_exclusions:
        return released
    st.caption("Los términos de portfolios RANKING o sin nombre sincronizado quedan afuera. Marcá «Liberar» "
               "en los que sí querés negativizar.")
    release_frame = _release_frame(releasable_exclusions, released)
    edited = st.data_editor(
        release_frame, key="neg_release_editor", hide_index=True, use_container_width=True,
        disabled=[column for column in release_frame.columns if column != LIBERAR_COLUMN],
        column_config={LIBERAR_COLUMN: st.column_config.CheckboxColumn(
            LIBERAR_COLUMN, help="Incluye este término en el bulk aunque su portfolio esté protegido.")},
    )
    released = released_ranking_keys(released, releasable_exclusions, edited[LIBERAR_COLUMN].tolist())
    st.session_state[RELEASED_RANKING_KEY] = released
    return released


def _bulk_file_name(source_label, currency_code, day):
    ascii_label = unicodedata.normalize("NFKD", source_label).encode("ascii", "ignore").decode("ascii")
    label_slug = re.sub(r"[^a-z0-9]+", "-", ascii_label.casefold()).strip("-") or "cuenta"
    currency = re.sub(r"[^A-Z0-9]", "", (currency_code or "").upper()) or "SIN-MONEDA"
    return f"negativos_bulk_{label_slug}_{currency}_{day.isoformat()}.xlsx"


def _render_negatives_bulk(candidates, unfiltered_frame, source, day, *, price_missing):
    """Ad-group negatives bulk from Amazon Ads data: the download plus what stayed out and why."""
    try:
        guards = ad_group_guards(unfiltered_frame)
        _, unreleased_exclusions = select_for_bulk(candidates, unfiltered_frame, guards=guards)
    except ValueError as exc:
        log.error("negatives bulk could not be built for %s: %s", source.label, exc)
        st.error("No se pudo armar el bulk de negativos con estos datos. Quedó registrado en el log.")
        return
    st.caption(EXACT_GUARD_PARTIAL_NOTE)
    st.caption(AD_GROUP_STATE_UNVERIFIED_NOTE)
    # The download sits above the release boxes but is built from what they say, so it is filled in last.
    download_slot = st.container()
    exclusions_heading_slot = st.container()
    releasable = _unique_by_negative_key([exclusion for exclusion in unreleased_exclusions if exclusion.releasable])
    released = _render_release_editor(releasable)
    bulk_rows, exclusions = select_for_bulk(candidates, unfiltered_frame, released_ranking=released, guards=guards)

    with download_slot:
        if bulk_rows:
            bulk_df, invalid_df = build_adgroup_negative(bulk_rows)
            if not invalid_df.empty:
                log.warning("negatives bulk for %s: %d rows failed bulk validation", source.label, len(invalid_df))
                st.caption(f"{len(invalid_df)} negativos no pasaron la validación del bulk de Amazon y quedaron afuera.")
            if not bulk_df.empty:
                metadata_df = _bulk_metadata_frame(_bulk_selected_candidates(candidates, exclusions))
                st.download_button(
                    "Descargar bulk de negativos (.xlsx)",
                    data=b"" if price_missing else write_bulk_excel(bulk_df, metadata_df),
                    file_name=_bulk_file_name(source.label, source.currency_code, day),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="neg_bulk_dl", disabled=price_missing,
                )
        else:
            st.info("Ningún candidato a negativo pasa los controles para ir al bulk.")

    if exclusions:
        exclusions_heading_slot.markdown(f"**Quedaron afuera del bulk ({len(exclusions)})**")
        protected_keys = {negative_key(exclusion.candidate) for exclusion in releasable}
        other_exclusions = [exclusion for exclusion in exclusions
                            if not (exclusion.releasable and negative_key(exclusion.candidate) in protected_keys)]
        if other_exclusions:
            st.dataframe(_bulk_exclusion_frame(other_exclusions), use_container_width=True, hide_index=True,
                         height=min(38 + 35 * len(other_exclusions), 400))


# STR-only UI strings; everything shared comes from core/ai_tab's label base.
_STR_LABELS = {
    "es": {"caption": "Análisis ejecutivo generado por IA sobre los "
                      "candidatos detectados",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_neg": "Candidatos a negativizar (Alta/Media) — lectura IA",
           "table_harv": "Candidatos a harvest — lectura IA",
           "table_camp": "Diagnóstico por campaña",
           "col_item": "Candidato", "col_campaign": "Campaña",
           "title": "Análisis IA",
           "no_rows": "No hay candidatos a negativizar ni a harvest con los "
                      "criterios actuales; no hay nada que analizar.",
           "already_exact": "ya en exact",
           "cat_dudosa": "revisar categoría",
           "neg_word": "negativos", "harv_word": "harvest",
           "camp_word": "campañas"},
    "en": {"caption": "AI-generated executive analysis over the detected "
                      "candidates",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_neg": "Negative candidates (High/Med) — AI read",
           "table_harv": "Harvest candidates — AI read",
           "table_camp": "Campaign diagnosis",
           "col_item": "Candidate", "col_campaign": "Campaign",
           "title": "AI Analysis",
           "no_rows": "No negative or harvest candidates under the current "
                      "criteria; nothing to analyze.",
           "already_exact": "already in exact",
           "cat_dudosa": "check category",
           "neg_word": "negatives", "harv_word": "harvest",
           "camp_word": "campaigns"},
}

_STR_BADGE_COLORS = {
    "marca_propia": "background-color:#FFF3E0;color:#BF360C",
    "competidor": "background-color:#EEEDFE;color:#3C3489",
    "generico": "background-color:#F5F5F5;color:#616161",
    "atributo": "background-color:#E1F5EE;color:#0F6E56",
    "irrelevante": "background-color:#FFEBEE;color:#9C0006",
}


def _str_neg_metrics(rec, currency_code=""):
    return [f"{int(rec.get('Clicks', 0))} clicks",
            f"{int(rec.get('Orders', 0))} ord",
            money(float(rec.get('Spend', 0)), currency_code),
            f"{int(rec.get('Impressions', 0))} impr"]


def _str_harv_metrics(rec, already_exact_label="ya en exact", currency_code=""):
    metrics = [f"{int(rec.get('Clicks', 0))} clicks",
               f"{int(rec.get('Orders', 0))} ord",
               f"ACoS {float(rec.get('ACoS', 0)):.1f}%"]
    if rec.get("CVR%") is not None:
        metrics.append(f"CVR {float(rec['CVR%']):.1f}%")
    if rec.get("Bid Sugerido") is not None:
        metrics.append(f"bid {money(float(rec['Bid Sugerido']), currency_code)}")
    # Tab 3 fills the column with "Ya en Exact activo" or "", never a yes/no.
    if str(rec.get("Ya en Exact", "")).strip():
        metrics.append(already_exact_label)
    return metrics


def _str_ai_rows(records, opinions, prefix, brand_terms, labels, metrics_fn):
    """Display rows for core/ai_tab.opinion_table_html.

    Positional row_id join against the SAME records that were serialized into
    the analysis payload — never against a recomputed frame. The category
    hint is deterministic and never a gate: it only flags a disagreement
    between the AI's category and the declared brand terms.
    """
    from ai.agents.str.context import make_ids
    ops = {o.get("row_id"): o for o in opinions}
    rows = []
    for rid, rec in zip(make_ids(prefix, len(records)), records):
        o = ops.get(rid, {})
        cat = o.get("categoria", "")
        term_l = str(rec.get("Search Term", "")).lower()
        dudosa = bool(brand_terms) and bool(cat) and (
            (cat == "marca_propia"
             and not any(b in term_l for b in brand_terms))
            or (cat != "marca_propia"
                and any(b in term_l for b in brand_terms)))
        metrics = metrics_fn(rec)
        campaign = str(rec.get("Campaign", "")).strip()
        if campaign:
            metrics.append(f"@ {campaign[:40]}")
        rows.append({
            "row_id": rid,
            "item": rec.get("Search Term", ""),
            "type_tag": rec.get("Regla", ""),
            "metrics": metrics,
            "badges": [cat] + ([labels["cat_dudosa"]] if dudosa else []),
            "warning": o.get("advertencia") or "",
            "reasoning": o.get("razon", ""),
        })
    return rows


def _str_campaign_rows(campaigns, campaign_records, currency_code=""):
    """AI campaign diagnoses with the figures of the campaign the AI read, matched by exact name."""
    by_name = {str(record.get("Campaign", "")): record for record in campaign_records or []}
    return [{"item": c.get("campaign", ""), "reasoning": c.get("diagnostico", ""),
             "metrics": _str_campaign_metrics(by_name[c.get("campaign", "")], currency_code)
             if c.get("campaign", "") in by_name else []}
            for c in campaigns]


def _str_campaign_metrics(record, currency_code=""):
    return [money(float(record.get("Spend", 0)), currency_code),
            f"ACoS {float(record.get('ACoS', 0)):.1f}%",
            f"{int(record.get('Orders', 0))} ord",
            f"{int(record.get('Clicks', 0))} clicks"]


def _str_row_labels(neg_records, harv_records):
    """row_id -> search term for the rows sent to the AI, so the ids the
    synthesis and the chat cite (N07, H59) can be annotated with their term."""
    from ai.agents.str.context import HARV_PREFIX, NEG_PREFIX, make_ids
    labels = {}
    for prefix, records in ((NEG_PREFIX, neg_records or []),
                            (HARV_PREFIX, harv_records or [])):
        for rid, rec in zip(make_ids(prefix, len(records)), records):
            labels[rid] = str(rec.get("Search Term", "")).strip()
    return labels


def _render_str_ai_result(result, analysis, neg_records, harv_records,
                          brand_terms, labels, currency_code="", campaign_records=None):
    from core import ai_tab
    from ai.agents.str.context import NEG_PREFIX, HARV_PREFIX
    row_labels = _str_row_labels(neg_records, harv_records)
    synthesis = ai_tab.map_synthesis_text(
        result.get("synthesis") or {},
        lambda text: ai_tab.annotate_row_ids(text, row_labels))
    negs = result.get("negativos") or []
    harvs = result.get("harvest") or []
    campaigns = result.get("campanas") or []
    n_warnings = sum(1 for o in negs + harvs if o.get("advertencia"))
    with st.container(border=True):
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(ai_tab.ai_chips_html(
                n_warnings,
                f"{len(negs)} {labels['neg_word']} · "
                f"{len(harvs)} {labels['harv_word']} · "
                f"{len(campaigns)} {labels['camp_word']}",
                analysis.elapsed, labels), unsafe_allow_html=True)
        with head_r:
            with st.popover(labels["copy_btn"], use_container_width=True):
                situation = synthesis.get("situation", "")
                actions = "\n".join(f"- {a}" for a in synthesis.get("week_actions", []))
                st.code(f"{situation}\n{actions}".strip(), language=None)
        st.markdown(ai_tab.synthesis_html(synthesis, labels),
                    unsafe_allow_html=True)
    badge_colors = {**_STR_BADGE_COLORS,
                    labels["cat_dudosa"]: "background-color:#FFF8E1;color:#9C5700"}
    if neg_records:
        st.markdown(ai_tab.opinion_table_html(
            _str_ai_rows(neg_records, negs, NEG_PREFIX, brand_terms, labels,
                         lambda rec: _str_neg_metrics(rec, currency_code)),
            labels["table_neg"], labels, badge_colors), unsafe_allow_html=True)
    if harv_records:
        st.markdown(ai_tab.opinion_table_html(
            _str_ai_rows(harv_records, harvs, HARV_PREFIX, brand_terms, labels,
                         lambda rec: _str_harv_metrics(rec, labels["already_exact"],
                                                       currency_code)),
            labels["table_harv"], labels, badge_colors), unsafe_allow_html=True)
    if campaigns:
        st.markdown(ai_tab.opinion_table_html(
            _str_campaign_rows(campaigns, campaign_records, currency_code), labels["table_camp"],
            {**labels, "col_item": labels["col_campaign"]}, badge_colors, diagnosis_column=False),
            unsafe_allow_html=True)


_SEEDED_ACCOUNT_KEY = "str_ai_seeded_account"
_AI_REQUEST_FEEDBACK_KEY = "str_ai_request_feedback"
AI_STATUS_TTL_SECONDS = 15
AI_GENERATING_POLL = "10s"
_AI_REQUEST_FEEDBACK = {
    "created": "Análisis IA pedido: se genera en unos minutos.",
    "already_running": "Ya se está generando el análisis de estos datos.",
    "already_done": "Ya existe el análisis de estos datos.",
}


def _price_input(label, key, currency_code, amount_unit):
    """A price input; outside dollars it starts empty, because 30 pesos or yen would price every rule wrong.

    Each currency keeps one widget signature: changing its arguments would make Streamlit reset the value.
    """
    if _uses_dollar_price(currency_code):
        _seed_input(key, DEFAULT_PRODUCT_PRICE)
        return st.number_input(label, min_value=1.0, step=1.0, key=key)
    return st.number_input(label, min_value=1.0, value=None, step=1.0, key=key,
                           placeholder=f"Precio en {amount_unit}")


def _seed_account_parameters(source):
    """Loads the account's saved analysis parameters, or the defaults, into the inputs when the AM opens an account."""
    if st.session_state.get(_SEEDED_ACCOUNT_KEY) == source.profile_id:
        return
    try:
        settings = _load_account_settings(source.profile_id)
    except (requests.RequestException, StoreError) as exc:
        log.warning("analysis parameters for %s could not be read: %s", source.profile_id, exc)
        return
    st.session_state[_SEEDED_ACCOUNT_KEY] = source.profile_id
    params = (StrAnalysisParams.from_dict(settings.params, source.currency_code) if settings
              else StrAnalysisParams.defaults(source.currency_code))
    st.session_state["neg_target_acos"] = params.target_acos
    st.session_state["harv_target_acos"] = params.harvest_target_acos
    st.session_state["harv_min_clicks"] = params.harvest_min_clicks
    st.session_state["str_brand_terms"] = ", ".join(params.brand_terms)
    for base_key, price in (("neg_precio", params.price), ("harv_precio", params.harvest_price)):
        key = _price_key(base_key, source.currency_code)
        if price is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = price


def _analysis_store():
    rest = search_term_source._open_rest()
    return AiAnalysisStore(rest) if rest is not None else None


@st.cache_data(ttl=60, show_spinner=False)
def _load_account_settings(profile_id):
    store = _analysis_store()
    return store.settings(ANALYSIS_MODULE, profile_id) if store is not None else None


@st.cache_data(ttl=AI_STATUS_TTL_SECONDS, show_spinner=False)
def _load_stored_analysis(profile_id, input_digest):
    store = _analysis_store()
    return store.done_for_input(ANALYSIS_MODULE, profile_id, input_digest) if store is not None else None


@st.cache_data(ttl=AI_STATUS_TTL_SECONDS, show_spinner=False)
def _load_analysis_job(profile_id, input_digest):
    store = _analysis_store()
    return store.latest_job_for_input(ANALYSIS_MODULE, profile_id, input_digest) if store is not None else None


@st.cache_data(ttl=300, show_spinner=False)
def _load_analysis_history(profile_id, exclude_id):
    store = _analysis_store()
    if store is None:
        return []
    return store.history(ANALYSIS_MODULE, profile_id, limit=PREVIOUS_ANALYSES, exclude_id=exclude_id)


def _forget_analysis_reads():
    for loader in (_load_account_settings, _load_stored_analysis, _load_analysis_job, _load_analysis_history):
        loader.clear()


def _missing_price_notice(params):
    """What the analysis leaves out while a price is missing; None when both prices are loaded."""
    if params.price is None and params.harvest_price is None:
        return ("Sin precio del producto: este análisis no evalúa la Regla 3 (gasto sin conversión) ni sugiere bids. "
                "Cargá el precio en Negatives Mining y en Harvest Candidates y pedí el análisis de nuevo.")
    if params.price is None:
        return ("Sin precio en Negatives Mining: este análisis no evalúa la Regla 3 (gasto sin conversión). "
                "Cargalo y pedí el análisis de nuevo.")
    if params.harvest_price is None:
        return ("Sin precio en Harvest Candidates: este análisis no sugiere bids. Cargalo y pedí el análisis de nuevo.")
    return None


def _stored_analysis_caption(stored):
    moment = stored.finished_at.astimezone(DISPLAY_TIMEZONE).strftime("%d/%m %H:%M") if stored.finished_at else "?"
    origin = ("generado automáticamente al llegar los datos" if stored.trigger == TRIGGER_SCHEDULED
              else f"pedido por {stored.requested_by}")
    return (f"Análisis del {date_range_label(stored.window_start, stored.window_end)} · {origin} · "
            f"listo el {moment}.")


def _render_stored_analysis(source, ai_input, params, *, lang, labels):
    """Tab 4 for Amazon Ads data: the stored analysis of exactly these data and parameters, never an older one.

    Returns it with the state the app chat is told, or None with the state that explains why there is none."""
    from core.app_chat import AnalysisState
    feedback = st.session_state.pop(_AI_REQUEST_FEEDBACK_KEY, None)
    if feedback:
        st.toast(feedback)
    call = build_agent_call(ANALYSIS_MODULE, ai_input.data)
    try:
        stored = _load_stored_analysis(source.profile_id, call.input_digest)
        job = None if stored is not None else _load_analysis_job(source.profile_id, call.input_digest)
    except (requests.RequestException, StoreError) as exc:
        log.warning("stored analysis for %s could not be read: %s", source.profile_id, exc)
        st.error("No se pudo leer el análisis IA guardado. Probá de nuevo en unos segundos.")
        return None, AnalysisState.MISSING

    if stored is not None:
        st.caption(_stored_analysis_caption(stored))
        _render_str_ai_result(stored.result, SimpleNamespace(elapsed=int((stored.duration_ms or 0) / 1000)),
                              stored.negative_records, stored.harvest_records,
                              list(stored.params.get("brand_terms") or []), labels, source.currency_code,
                              # Same fingerprint, so these are the campaign figures the stored analysis read.
                              campaign_records=ai_input.data.campanas)
        return stored, AnalysisState.CURRENT
    if job is not None and job.is_open:
        _render_analysis_generating(source.profile_id, call.input_digest, job)
        return None, AnalysisState.RUNNING
    if job is not None and job.status == "failed":
        st.error(f"El análisis IA de estos datos falló: {job.error_message or job.error_class}")
        if st.button("Reintentar", key="str_ai_retry_job"):
            _retry_analysis_job(job)
        return None, AnalysisState.FAILED
    _render_analysis_request(source, ai_input, params, call.input_digest, lang=lang)
    return None, AnalysisState.MISSING


def _render_analysis_generating(profile_id, input_digest, job):
    @st.fragment(run_every=AI_GENERATING_POLL)
    def _poll():
        _load_stored_analysis.clear()
        _load_analysis_job.clear()
        current = _load_analysis_job(profile_id, input_digest) or job
        if _load_stored_analysis(profile_id, input_digest) is not None or not current.is_open:
            st.rerun()
        requested = current.created_at.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M") if current.created_at else "?"
        st.status(f"Generando el análisis IA de estos datos · pedido a las {requested}. "
                  "Puede tardar unos minutos.", state="running")

    _poll()


def _render_analysis_request(source, ai_input, params, input_digest, *, lang):
    try:
        settings = _load_account_settings(source.profile_id)
    except (requests.RequestException, StoreError):
        settings = None
    account_params = (StrAnalysisParams.from_dict(settings.params, source.currency_code) if settings
                      else StrAnalysisParams.defaults(source.currency_code))
    window_days = ((source.window_end - source.window_start).days + 1
                   if source.window_start and source.window_end else 0)
    from core import ai_tab
    if params == account_params and lang == CANONICAL_LANG and window_days == CANONICAL_WINDOW_DAYS:
        body = ("Todavía no hay un análisis de estos datos. Se genera solo cuando llegan datos nuevos de Amazon "
                "Ads; si no querés esperar, pedilo ahora.")
    else:
        body = ("No hay un análisis con estos parámetros, este período o este idioma. Generalo para esta "
                "configuración: los parámetros quedan guardados para la cuenta.")
    st.markdown(ai_tab.ai_notice_html("Análisis IA pendiente", body), unsafe_allow_html=True)
    if not st.button("Generar análisis IA", key="str_ai_request", type="primary"):
        return
    store = _analysis_store()
    if store is None or source.window_start is None or source.window_end is None:
        st.error("No hay base de datos configurada para pedir el análisis.")
        return
    username = search_term_source._current_username()
    try:
        if params != account_params:
            store.save_settings(ANALYSIS_MODULE, source.profile_id, params.as_dict(), username)
        outcome = store.request_analysis(
            ANALYSIS_MODULE, source.profile_id, window_start=source.window_start, window_end=source.window_end,
            lang=lang, params=params.as_dict(), input_digest=input_digest, requested_by=username)
    except StoreError as exc:
        st.error(str(exc))
        return
    _forget_analysis_reads()
    message = _AI_REQUEST_FEEDBACK.get(outcome.reason)
    if message is None:
        st.warning("No se pudo pedir el análisis para esta cuenta o este período.")
        return
    # A toast sent right before st.rerun() is dropped with the run; the next run shows it.
    st.session_state[_AI_REQUEST_FEEDBACK_KEY] = message
    st.rerun()


def _retry_analysis_job(job):
    rest = search_term_source._open_rest()
    if rest is None:
        st.error("No hay base de datos configurada para reintentar.")
        return
    try:
        SyncJobStore(rest).retry(job.id, search_term_source._current_username())
    except StoreError as exc:
        st.error(str(exc))
        return
    _forget_analysis_reads()
    st.rerun()


def _analysis_chat_context(source, stored):
    """The documents the chat opens with for Amazon Ads data, and the key that changes when they do."""
    try:
        previous = _load_analysis_history(source.profile_id, stored.id if stored is not None else None)
    except (requests.RequestException, StoreError) as exc:
        log.warning("analysis history for %s could not be read: %s", source.profile_id, exc)
        previous = []
    docs = analysis_chat_documents(stored, previous, currency_code=source.currency_code)
    key = f"{source.profile_id}:{stored.id if stored is not None else '-'}:{'-'.join(str(a.id) for a in previous)}"
    return docs, key


def _share_stored_analysis(source, stored, state) -> None:
    """The app chat reads the account's analysis on screen and its earlier ones, and whether there is one."""
    from ai.config import AI_ENABLED
    from core import ai_tab, app_chat
    from core.ai_analysis.account_summaries import account_labels
    if not AI_ENABLED:
        app_chat.withdraw_analysis("str")
        return
    docs, key = _analysis_chat_context(source, stored)
    if not docs:
        if state == app_chat.AnalysisState.RUNNING:
            app_chat.report_running("str")
        elif state == app_chat.AnalysisState.FAILED:
            app_chat.report_failed("str")
        else:
            app_chat.withdraw_analysis("str")
        return
    profiles = search_term_source._available_profiles()
    subject = account_labels(profiles).get(source.profile_id, source.label)
    country_code = next((profile.country_code for profile in profiles if profile.profile_id == source.profile_id), "")
    row_labels = _str_row_labels(stored.negative_records, stored.harvest_records) if stored is not None else {}
    app_chat.share_analysis(app_chat.ChatAnalysis(
        module="str", key=f"str:{key}", subject=subject,
        documents=tuple({"title": f"Search Term Report · {subject} · {doc['title']}", "content": doc["content"]}
                        for doc in docs),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=row_labels),
        country_code=country_code, profile_id=source.profile_id), state=state)


def _file_analysis_reading(analysis, *, params, lang, negative_records, harvest_records, currency_code) -> str:
    """Read from the analysis itself, so one finished after the AM left the page carries its own moment."""
    snapshot = in_memory_analysis(analysis.result, params=params, lang=lang, finished_at=analysis.finished_at,
                                  negative_records=negative_records, harvest_records=harvest_records)
    return current_analysis_text(snapshot, currency_code)


def render():
    _restore_parked_inputs()
    st.header("Search Term Report")
    st.caption("Analisis de terminos de busqueda con metricas de ACoS, gasto y ventas totales.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Analizar search terms de campañas SP para negativizar, harvestear y clasificar por estado.")
        with col2:
            st.markdown("**📥 De dónde salen los datos**")
            st.caption("Solos desde Amazon Ads si la cuenta está conectada (Sistema → Cuentas conectadas). Si no, "
                       "subís el reporte a mano.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Search Query Performance (M3) para validar contra datos del mercado.")

        st.markdown("**🔄 Datos automáticos (cuenta conectada)**")
        st.markdown(
            "- No hace falta bajar ni subir nada: el reporte se actualiza solo todos los días con los datos hasta "
            "ayer (hora de la cuenta). Una cuenta recién conectada trae sus últimos 65 días.\n"
            "- Elegís **Cuenta**, **País** y **Período** (7, 14, 30 o 60 días, o un rango de hasta 60).\n"
            "- **Actualizar ahora** pide datos nuevos a Amazon si no querés esperar a la actualización diaria "
            "(una vez cada 30 minutos). Cuando llegan, aparece **Cargar datos nuevos**.\n"
            "- El **análisis IA** ya está hecho y guardado: se genera solo cuando llegan datos nuevos y lo ve todo "
            "el equipo. Si cambiás parámetros, período o idioma, se pide con **Generar análisis IA**.\n"
            "- Con el precio cargado se puede descargar el **bulk de negativos** para subir a Amazon."
        )

        st.markdown("**📂 Archivo manual (Subir archivo manualmente)**")
        st.markdown(
            "- Para una cuenta que no está conectada, o para analizar un reporte puntual: el Search Term Report de "
            "Sponsored Products que bajás de la consola de Amazon Ads (.xlsx o .csv). Sirve el formato viejo y el "
            "nuevo de la consola.\n"
            "- Si el archivo trae varias cuentas, elegís cuál ver; si una cuenta tiene montos en dos monedas, se "
            "separan, nunca se suman.\n"
            "- El archivo queda solo en tu sesión: no se guarda ni se mezcla con los datos automáticos.\n"
            "- El **análisis IA** se genera en el momento y solo para vos. Si falta el precio, espera a que lo "
            "cargues o a que lo pidas con el botón.\n"
            "- El **bulk de negativos no está disponible**: el archivo no trae el match type de origen que exigen "
            "las reglas para subirlo."
        )

        st.markdown("**⚖️ En qué se diferencian**")
        st.markdown(
            "| | Automático | Archivo manual |\n"
            "|---|---|---|\n"
            "| Actualización | Sola, todos los días (y *Actualizar ahora*) | Cada vez que subís un archivo |\n"
            "| Se guarda | Sí, para todo el equipo | No, solo tu sesión |\n"
            "| Análisis IA | Guardado y listo al entrar | Se genera al subir, solo para vos |\n"
            "| Bulk de negativos | Sí | No |"
        )

        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí cuenta, país y período, o subí el archivo si la cuenta no está conectada\n"
            "2. Revisá precio promedio del producto (fuera de USD arranca vacío: sin precio no corre la Regla 3 "
            "ni hay bid sugerido), brand terms (Enter para aplicar) y Target ACoS\n"
            "3. Revisá Tab 1 (12 KPIs), Tab 2 (Negatives), Tab 3 (Harvest con anti-canibalización) y Tab 4 (Análisis IA)\n"
            "4. Opcional: subí Campaign CSV en Tab 3 para cruzar con Exact activos\n"
            "5. Descargá el bulk de negativos (datos automáticos) y los Excel de candidatos"
        )

    source = render_source_picker()
    if source is None:
        # A period without searches must not wipe brand terms, prices and filters typed before it.
        _park_inputs(_all_input_keys())
        from core import app_chat
        app_chat.withdraw_analysis("str")
        return

    df_raw = source.frame
    currency_code = source.currency_code
    amount_unit = _amount_unit(currency_code)
    money_format = partial(money, currency_code=currency_code)
    if source.source == SOURCE_FILE:
        st.success(f"{len(df_raw)} filas cargadas")
    elif source.profile_id:
        _seed_account_parameters(source)

    cols = _detect_cols(df_raw)

    # Numeric columns on raw df
    df_raw["_spend"]  = _to_num(df_raw, cols["spend"])
    df_raw["_sales"]  = _to_num(df_raw, cols["sales"])
    df_raw["_orders"] = _to_num(df_raw, cols["orders"])
    df_raw["_clicks"] = _to_num(df_raw, cols["clicks"])
    df_raw["_imps"]   = _to_num(df_raw, cols["impressions"])
    df_raw["_acos"]   = _to_num(df_raw, cols["acos"])
    df_raw["_ctr"]    = _to_num(df_raw, cols["ctr"])

    total_rows = len(df_raw)

    # ── CAMBIO 1: Filtro portfolio transversal ──────────────────────
    port_col = cols["portfolio"]
    if port_col and port_col in df_raw.columns:
        portfolios = sorted(df_raw[port_col].dropna().astype(str).str.strip().unique())
        portfolios = [p for p in portfolios if p and p != "" and p.lower() != "nan"]
    else:
        portfolios = []

    if portfolios:
        # A different portfolio list starts with every portfolio selected, as a brand new filter did.
        if st.session_state.get(_PORTFOLIO_OPTIONS_KEY) != tuple(portfolios):
            st.session_state["str_portfolio_filter"] = portfolios
        _seed_input("str_portfolio_filter", portfolios)
        st.session_state[_PORTFOLIO_OPTIONS_KEY] = tuple(portfolios)
        selected_ports = st.multiselect(
            "Filtrar por Portfolio",
            options=portfolios,
            key="str_portfolio_filter",
        )
        if selected_ports and len(selected_ports) < len(portfolios):
            df = df_raw[df_raw[port_col].astype(str).str.strip().isin(selected_ports)].copy()
            st.caption(f"{len(df)} de {total_rows} filas (filtrado por portfolio)")
        else:
            df = df_raw.copy()
    else:
        _park_inputs(("str_portfolio_filter",))
        df = df_raw.copy()

    # Pre-init for tab4 (IA) scope
    df_neg = pd.DataFrame()
    df_harv = pd.DataFrame()
    analysis = None  # AI run; without one the page withdraws its analysis from the app chat
    stored_analysis = None  # the stored analysis tab 4 shows for API data; the chat reads it too
    stored_state = None  # why tab 4 shows it or not, as the app chat is told
    candidates = None
    ai_labels_str = None

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Vista General",
        "Negatives Mining",
        "Harvest Candidates",
        "Analisis IA",
        "Por Campana",
    ])

    # ══════════════════════════════════════════════════════════════
    # TAB 1: Vista General ENRIQUECIDA
    # ══════════════════════════════════════════════════════════════
    with tab1:
        # ── Target ACoS slider ──────────────────────────────────
        _seed_input("str_target_acos_tab1", DEFAULT_TARGET_ACOS)
        target_acos = st.slider("Target ACoS (%)", 10, 80, key="str_target_acos_tab1")

        # ── Brand terms input ───────────────────────────────────
        brand_input = st.text_input(
            "Brand terms (separados por coma)",
            placeholder="ej: dermaglos, dg, love to dream",
            key="str_brand_terms",
        )
        brand_terms = [t.strip().lower() for t in brand_input.split(",") if t.strip()] if brand_input else []

        # ── Term type classification ────────────────────────────
        st_col = cols["search_term"]
        if st_col and st_col in df.columns:
            df["_term_type"] = df[st_col].apply(lambda t: _classify_term_type(t, brand_terms))
        else:
            df["_term_type"] = "Generic"
        if brand_terms:
            # The KPIs below ignore the brand, so without this line an applied term looks like it did nothing.
            st.caption(_brand_match_caption(df, brand_terms, currency_code))

        # ── 12 KPIs ────────────────────────────────────────────
        total_spend = df["_spend"].sum()
        total_sales = df["_sales"].sum()
        total_clicks = df["_clicks"].sum()
        total_imps = df["_imps"].sum()
        total_orders = df["_orders"].sum()
        acos_val = (total_spend / total_sales * 100) if total_sales > 0 else 0
        roas_val = (total_sales / total_spend) if total_spend > 0 else 0
        ctr_val = (total_clicks / total_imps * 100) if total_imps > 0 else 0
        cvr_val = (total_orders / total_clicks * 100) if total_clicks > 0 else 0
        cpc_val = (total_spend / total_clicks) if total_clicks > 0 else 0
        waste_spend = df[df["_sales"] == 0]["_spend"].sum()
        pct_waste = (waste_spend / total_spend * 100) if total_spend > 0 else 0
        rows_with_sales = (df["_sales"] > 0).sum()
        pct_conv = (rows_with_sales / len(df) * 100) if len(df) > 0 else 0

        # Row 1
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            st.markdown(kpi_card("Total Spend", html.escape(money(total_spend, currency_code))), unsafe_allow_html=True)
        with r1c2:
            st.markdown(kpi_card("Total Sales", html.escape(money(total_sales, currency_code))), unsafe_allow_html=True)
        with r1c3:
            acos_delta = acos_val - target_acos
            st.markdown(kpi_card("ACoS", f"{acos_val:.1f}%", delta=acos_delta, delta_good=False), unsafe_allow_html=True)
        with r1c4:
            st.markdown(kpi_card("ROAS", f"{roas_val:.2f}x"), unsafe_allow_html=True)

        # Row 2
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        with r2c1:
            st.markdown(kpi_card("Impressions", f"{total_imps:,.0f}"), unsafe_allow_html=True)
        with r2c2:
            st.markdown(kpi_card("Clicks", f"{total_clicks:,.0f}"), unsafe_allow_html=True)
        with r2c3:
            st.markdown(kpi_card("CTR Promedio", f"{ctr_val:.2f}%"), unsafe_allow_html=True)
        with r2c4:
            st.markdown(kpi_card("CVR Promedio", f"{cvr_val:.2f}%"), unsafe_allow_html=True)

        # Row 3
        r3c1, r3c2, r3c3, r3c4 = st.columns(4)
        with r3c1:
            st.markdown(kpi_card("CPC Promedio", html.escape(money(cpc_val, currency_code))), unsafe_allow_html=True)
        with r3c2:
            st.markdown(kpi_card("Orders", f"{total_orders:,.0f}"), unsafe_allow_html=True)
        with r3c3:
            st.markdown(kpi_card("% Waste", f"{pct_waste:.1f}%"), unsafe_allow_html=True)
        with r3c4:
            st.markdown(kpi_card("% Con Ventas", f"{pct_conv:.1f}%"), unsafe_allow_html=True)

        st.markdown("")

        # ── Filtros interactivos ────────────────────────────────
        st.markdown("#### Filtros")
        fc1, fc2, fc3, fc4 = st.columns(4)
        camp_col = cols["campaign"]
        match_col = cols["match_type"]

        with fc1:
            camp_options = ["Todas"]
            if camp_col and camp_col in df.columns:
                camp_options += sorted(df[camp_col].dropna().astype(str).unique())
            # A kept campaign that is not in this data would make Streamlit fail to draw the filter.
            if st.session_state.get("str_f_camp") not in camp_options:
                st.session_state["str_f_camp"] = "Todas"
            selected_camp = st.selectbox("Campana", camp_options, key="str_f_camp")
        with fc2:
            match_options = []
            if match_col and match_col in df.columns:
                match_options = sorted(df[match_col].dropna().astype(str).str.strip().unique())
            if not set(st.session_state.get("str_f_match") or []) <= set(match_options):
                st.session_state["str_f_match"] = []
            _seed_input("str_f_match", [])
            selected_match = st.multiselect("Match Type", match_options, key="str_f_match")
        with fc3:
            _seed_input("str_f_acos_max", 0)
            acos_max = st.number_input("ACoS max %", min_value=0, key="str_f_acos_max")
        with fc4:
            _seed_input("str_f_spend_min", 0.0)
            spend_min = st.number_input(f"Spend min {amount_unit}", min_value=0.0, step=0.5, key="str_f_spend_min")

        vista = st.radio(
            "Vista rapida",
            ["Todos", "Winners", "Sin ventas", "Top Sales", "Top Spend"],
            horizontal=True,
            key="str_vista",
        )

        # ── Apply filters ──────────────────────────────────────
        df_f = df.copy()
        if selected_camp != "Todas" and camp_col:
            df_f = df_f[df_f[camp_col].astype(str) == selected_camp]
        if selected_match and match_col:
            df_f = df_f[df_f[match_col].astype(str).str.strip().isin(selected_match)]
        if acos_max > 0:
            df_f = df_f[df_f["_acos"] <= acos_max]
        if spend_min > 0:
            df_f = df_f[df_f["_spend"] >= spend_min]

        # Vista rápida
        if vista == "Winners":
            df_f = df_f[(df_f["_orders"] >= 2) & (df_f["_acos"] > 0) & (df_f["_acos"] < target_acos)]
            df_f = df_f.sort_values("_acos", ascending=True)
        elif vista == "Sin ventas":
            df_f = df_f[(df_f["_spend"] > 0) & (df_f["_sales"] == 0)]
            df_f = df_f.sort_values("_spend", ascending=False)
        elif vista == "Top Sales":
            df_f = df_f.sort_values("_sales", ascending=False)
        elif vista == "Top Spend":
            df_f = df_f.sort_values("_spend", ascending=False)

        # ── Estado column ──────────────────────────────────────
        df_f["_estado"] = _classify_statuses(df_f, target_acos)

        # ── Show table ─────────────────────────────────────────
        # Views other than Todos are already sorted by what they are about.
        df_drawn, rows_left_out = _drawn_rows(df_f, order_column="_spend" if vista == "Todos" else None)
        if rows_left_out:
            st.caption(_drawn_rows_caption(len(df_f), _VIEW_ORDER_LABELS.get(vista, "las de mayor gasto")))
        else:
            st.caption(f"Mostrando {len(df_f)} de {len(df)} filas")

        # Pick display columns
        display_cols = []
        for c in [cols["search_term"], cols["campaign"], cols["match_type"]]:
            if c and c in df_f.columns:
                display_cols.append(c)
        display_cols += ["_imps", "_clicks", "_spend", "_sales", "_orders", "_acos", "_term_type", "_estado"]
        display_cols = [c for c in display_cols if c in df_f.columns]

        def _color_estado(val):
            colors = {
                "Escalar": "background-color:#C6EFCE;color:#276221",
                "OK": "background-color:#E8F5E9;color:#2E7D32",
                "Reducir": "background-color:#FFC7CE;color:#9C0006",
                "Revisar": "background-color:#FFEB9C;color:#9C5700",
                "Negativa?": "background-color:#FFC7CE;color:#9C0006",
            }
            return colors.get(val, "color:#999")

        styled = df_drawn[display_cols].style.map(_color_estado, subset=["_estado"])
        st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_drawn), 600))

        # ── Charts ─────────────────────────────────────────────
        st.markdown("---")
        ch1, ch2 = st.columns(2)

        with ch1:
            st.markdown("**Spend vs Sales**")
            if len(df_f) > 0 and df_f["_spend"].sum() > 0:
                hover_col = cols["search_term"] if cols["search_term"] and cols["search_term"] in df_f.columns else None
                scatter_rows = df_f[df_f["_spend"] > 0]
                if len(scatter_rows) > SCATTER_POINT_LIMIT:
                    scatter_rows = scatter_rows.nlargest(SCATTER_POINT_LIMIT, "_spend")
                    st.caption(f"Se grafican los {_dot_thousands(SCATTER_POINT_LIMIT)} términos de mayor gasto.")
                fig_scatter = px.scatter(
                    scatter_rows,
                    x="_spend", y="_sales",
                    color="_term_type",
                    hover_data=[hover_col] if hover_col else None,
                    labels={"_spend": f"Spend ({amount_unit})", "_sales": f"Sales ({amount_unit})", "_term_type": "Tipo"},
                    color_discrete_map={"Brand": "#06b6d4", "Generic": "#6366f1", "Long-tail": "#f59e0b"},
                )
                # Breakeven line
                max_spend = df_f["_spend"].max()
                breakeven_sales = max_spend / (target_acos / 100) if target_acos > 0 else max_spend
                fig_scatter.add_shape(
                    type="line", x0=0, y0=0, x1=max_spend, y1=breakeven_sales,
                    line=dict(color="rgba(255,255,255,0.3)", dash="dash", width=1),
                )
                fig_scatter.update_layout(
                    height=300, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#888",
                )
                st.plotly_chart(fig_scatter, use_container_width=True, key="str_scatter_chart")
            else:
                st.info("Sin datos para el scatter.")

        with ch2:
            st.markdown("**Funnel de Conversion**")
            f_imps = df_f["_imps"].sum()
            f_clicks = df_f["_clicks"].sum()
            f_orders = df_f["_orders"].sum()
            if f_imps > 0:
                pct_ctr = (f_clicks / f_imps * 100) if f_imps > 0 else 0
                pct_cvr = (f_orders / f_clicks * 100) if f_clicks > 0 else 0
                funnel_df = pd.DataFrame({
                    "Etapa": ["Impressions", "Clicks", "Orders"],
                    "Cantidad": [f_imps, f_clicks, f_orders],
                    "Paso": ["", f"{pct_ctr:.2f}% CTR", f"{pct_cvr:.2f}% CVR"],
                })
                fig_funnel = px.bar(
                    funnel_df, y="Etapa", x="Cantidad", orientation="h",
                    text="Paso",
                    color="Etapa",
                    color_discrete_sequence=["#6366f1", "#06b6d4", "#10b981"],
                )
                fig_funnel.update_layout(
                    height=300, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#888", showlegend=False,
                    yaxis=dict(autorange="reversed"),
                )
                fig_funnel.update_traces(textposition="inside", textfont_size=11)
                st.plotly_chart(fig_funnel, use_container_width=True, key="str_funnel_chart")
            else:
                st.info("Sin datos para el funnel.")

        # ── Term type distribution table ───────────────────────
        if brand_terms and st_col and st_col in df_f.columns:
            st.markdown("---")
            st.markdown("**Distribucion por tipo de termino**")
            tt_group = df_f.groupby("_term_type").agg(
                Terminos=("_term_type", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index()
            tt_group.rename(columns={"_term_type": "Tipo"}, inplace=True)
            tt_group["ACoS"] = tt_group.apply(
                lambda r: round(r["Spend"] / r["Sales"] * 100, 1) if r["Sales"] > 0 else 0, axis=1
            )
            tt_group["% Spend"] = tt_group.apply(
                lambda r: round(r["Spend"] / total_spend * 100, 1) if total_spend > 0 else 0, axis=1
            )
            tt_group["Spend"] = tt_group["Spend"].apply(money_format)
            tt_group["Sales"] = tt_group["Sales"].apply(money_format)
            st.dataframe(tt_group, use_container_width=True, hide_index=True)

        # ── Download Excel multi-sheet ─────────────────────────
        st.markdown("---")
        from datetime import date
        _today = date.today().isoformat()

        kpi_dict = {
            "Total Spend": money(total_spend, currency_code),
            "Total Sales": money(total_sales, currency_code),
            "ACoS": f"{acos_val:.1f}%",
            "ROAS": f"{roas_val:.2f}x",
            "Impressions": f"{total_imps:,.0f}",
            "Clicks": f"{total_clicks:,.0f}",
            "CTR": f"{ctr_val:.2f}%",
            "CVR": f"{cvr_val:.2f}%",
            "CPC": money(cpc_val, currency_code),
            "Orders": f"{total_orders:,.0f}",
            "% Waste": f"{pct_waste:.1f}%",
            "% Con Ventas": f"{pct_conv:.1f}%",
            "Target ACoS": f"{target_acos}%",
            "Fecha": _today,
        }

        def _str_analysis_excel():
            try:
                return _build_str_excel(df_f, df, kpi_dict, brand_terms)
            except Exception as e:
                log.exception("STR analysis workbook failed, falling back to the plain table")
                st.warning(f"Error generando Excel: {e}")
                return _xlsx_bytes(df_f)

        _xlsx_download(
            "\u2b07\ufe0f Descargar STR Analizado (Excel)", _str_analysis_excel,
            file_name=f"STR_analizado_{_today}.xlsx", key="str_dl", row_count=len(df_f),
            fingerprint=(source.signature, tuple(st.session_state.get("str_portfolio_filter") or ()), selected_camp,
                         tuple(selected_match), acos_max, spend_min, vista, target_acos, tuple(brand_terms), _today),
        )

    # ══════════════════════════════════════════════════════════════
    # TAB 2: Negatives Mining
    # ══════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("Negatives Mining")
        st.caption("Terminos candidatos a negativizar segun reglas Capybaras 2026")

        nc1, nc2 = st.columns(2)
        with nc1:
            _seed_input("neg_target_acos", DEFAULT_TARGET_ACOS)
            target_acos = st.slider("Target ACoS (%)", 10, 80, key="neg_target_acos")
        with nc2:
            neg_price_key = _price_key("neg_precio", currency_code)
            precio_producto = _price_input(f"Precio promedio del producto ({amount_unit})", neg_price_key,
                                           currency_code, amount_unit)
        price_missing = precio_producto is None
        if price_missing:
            st.warning(
                f"Ingresá el precio promedio del producto en {amount_unit}. Mientras no esté, no se aplica la "
                "Regla 3 (gasto sin conversión), el bulk de negativos queda deshabilitado y el análisis IA se "
                "genera sin esa regla."
            )

        # CVR promedio del STR cargado
        total_clicks = df["_clicks"].sum()
        total_orders = df["_orders"].sum()
        cvr_avg, cvr_is_reference = rule_two_cvr(total_clicks, total_orders)
        clicks_threshold = max(10, round((1 / (cvr_avg / 100)) * 2))
        if cvr_is_reference:
            st.info(f"Sin órdenes en estos datos: se usa un CVR de referencia de **{cvr_avg:.0f}%**, no un CVR "
                    f"medido — Threshold dinamico Regla 2: **{clicks_threshold} clicks**")
        else:
            st.info(f"CVR promedio del archivo: **{cvr_avg:.2f}%** — "
                    f"Threshold dinamico Regla 2: **{clicks_threshold} clicks**")

        # Rule 3 needs the product price; an infinite threshold switches it off while the price is missing.
        spend_threshold = float("inf") if price_missing else precio_producto * 0.50

        st_col = cols["search_term"]
        if not st_col:
            _park_inputs(("neg_prio_filter",))
            st.warning("No se encontro columna 'Customer Search Term' en el archivo.")
        else:
            candidates = evaluate_candidates(df, cols, clicks_threshold=clicks_threshold,
                                             spend_threshold=spend_threshold)

            if candidates:
                df_neg = pd.DataFrame(_negative_candidate_rows(candidates))
                prio_order = {"Alta": 0, "Media": 1, "Revisar": 2}
                df_neg["_sort"] = df_neg["Prioridad"].map(prio_order)
                df_neg = df_neg.sort_values(["_sort", "Spend"], ascending=[True, False]).drop(columns=["_sort"])

                n_alta   = (df_neg["Prioridad"] == "Alta").sum()
                n_media  = (df_neg["Prioridad"] == "Media").sum()
                n_review = (df_neg["Prioridad"] == "Revisar").sum()

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Total candidatos", len(df_neg))
                mc2.metric("Alta", n_alta)
                mc3.metric("Media", n_media)
                mc4.metric("Revisar", n_review)

                _seed_input("neg_prio_filter", DEFAULT_PRIORITY_FILTER)
                prio_filter = st.multiselect(
                    "Filtrar por prioridad", ["Alta", "Media", "Revisar"], key="neg_prio_filter",
                )
                df_show = df_neg[df_neg["Prioridad"].isin(prio_filter)] if prio_filter else df_neg

                def _color_prio(val):
                    if val == "Alta": return "background-color: #FFC7CE; color: #9C0006"
                    if val == "Media": return "background-color: #FFEB9C; color: #9C5700"
                    return "background-color: #F5F5F5; color: #666"

                # df_show is already sorted by priority, then spend.
                neg_drawn, neg_left_out = _drawn_rows(df_show)
                if neg_left_out:
                    st.caption(_drawn_rows_caption(len(df_show), "por prioridad y gasto"))
                st.dataframe(
                    neg_drawn.style.map(_color_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(neg_drawn), 800),
                )

                # Export de la tabla de candidatos
                st.markdown("---")
                st.markdown("**Export de candidatos**")
                df_export = df_show.copy()
                if not df_export.empty:
                    # Que le falta a cada candidato para poder ejecutarse. Sin
                    # Campaign Name o Ad Group el termino no se puede aplicar ni
                    # a mano: el AM tiene que completar el dato primero.
                    df_export["Falta dato"] = _missing_data_reasons(df_export)

                    metadata_df = df_export[
                        ["Search Term", "Campaign", "Ad Group", "Clicks", "Impressions",
                         "Spend", "Orders", "ACoS", "Acción", "Match Type", "Regla", "Prioridad",
                         "Falta dato"]
                    ].copy()

                    _n_incompletos = int((metadata_df["Falta dato"] != "").sum())
                    if _n_incompletos:
                        st.caption(
                            f"{_n_incompletos} de {len(metadata_df)} candidatos no traen "
                            "Campaign Name o Ad Group en el STR. Mira la columna "
                            "**Falta dato**: sin ese campo el termino no se puede "
                            "aplicar en Amazon, ni siquiera a mano."
                        )

                    from datetime import date as _date_neg
                    _neg_today = _date_neg.today()
                    if source.bulk_ready:
                        visible_candidates = [c for c in candidates if not prio_filter or c.priority in prio_filter]
                        _render_negatives_bulk(visible_candidates, df_raw, source, _neg_today,
                                               price_missing=price_missing)
                    else:
                        st.warning(
                            "El bulk se habilita con datos de Amazon Ads conectados: el archivo "
                            "manual no trae el match type de origen que exigen las reglas de "
                            "negativización."
                        )

                    _xlsx_download(
                        "Descargar candidatos a negativo (.xlsx)", lambda: _xlsx_bytes(metadata_df),
                        file_name=f"negativos_candidatos_{_neg_today.isoformat()}.xlsx", key="neg_dl",
                        row_count=len(metadata_df),
                        fingerprint=(source.signature, tuple(st.session_state.get("str_portfolio_filter") or ()),
                                     tuple(prio_filter), clicks_threshold, spend_threshold, _neg_today),
                    )
                else:
                    st.info("No hay candidatos visibles para exportar.")
            else:
                _park_inputs(("neg_prio_filter",))
                st.success("No se encontraron candidatos a negativizar con las reglas actuales.")

    # ══════════════════════════════════════════════════════════════
    # TAB 3: Harvest Candidates (SIN CAMBIOS)
    # ══════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("Harvest Candidates")
        st.caption("Terminos listos para harvestear a Exact Match segun reglas Capybaras 2026")

        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            _seed_input("harv_target_acos", DEFAULT_TARGET_ACOS)
            harv_target_acos = st.slider("Target ACoS (%)", 10, 80, key="harv_target_acos")
        with hc2:
            harv_price_key = _price_key("harv_precio", currency_code)
            harv_precio = _price_input(f"Precio promedio ({amount_unit})", harv_price_key, currency_code, amount_unit)
        with hc3:
            _seed_input("harv_min_clicks", DEFAULT_HARVEST_MIN_CLICKS)
            harv_min_clicks = st.number_input("Clicks minimos para CVR", min_value=5, step=1, key="harv_min_clicks")
        if harv_precio is None:
            st.warning(f"Ingresá el precio promedio en {amount_unit}. Mientras no esté, el bid sugerido queda vacío, "
                       "también en el análisis IA.")

        # ── Anti-canibalizacion: Campaign CSV opcional ────────────
        st.markdown("---")
        st.markdown("**Anti-canibalizacion** (opcional)")
        st.caption("Subi el Campaign CSV o Bulk para detectar keywords que ya estan en Exact activo.")
        file_camp_harv = st.file_uploader(
            "Campaign CSV / Bulk (.xlsx o .csv)",
            type=["xlsx", "csv"],
            key="harv_anti_canib",
        )

        existing_exact_kws = set()
        if file_camp_harv:
            try:
                df_camp_h = pd.read_excel(file_camp_harv) if file_camp_harv.name.endswith(".xlsx") else pd.read_csv(file_camp_harv)
                # Detectar columnas
                kw_col_h = next((c for c in df_camp_h.columns if "keyword" in c.lower() and "text" in c.lower()), None)
                if not kw_col_h:
                    kw_col_h = next((c for c in df_camp_h.columns if "keyword" in c.lower() or "targeting" in c.lower()), None)
                mt_col_h = next((c for c in df_camp_h.columns if "match type" in c.lower()), None)
                st_col_h = next((c for c in df_camp_h.columns if c.lower() == "state" or c.lower() == "status"), None)

                if kw_col_h:
                    df_kw = df_camp_h.copy()
                    # Filtrar solo Exact + Enabled
                    if mt_col_h:
                        df_kw = df_kw[df_kw[mt_col_h].astype(str).str.lower().str.strip().isin(["exact", "exact match"])]
                    if st_col_h:
                        df_kw = df_kw[df_kw[st_col_h].astype(str).str.lower().str.strip().isin(["enabled", "active"])]
                    existing_exact_kws = set(df_kw[kw_col_h].dropna().astype(str).str.lower().str.strip())
                    st.success(f"{len(existing_exact_kws)} keywords Exact activas detectadas")
                else:
                    st.warning("No se encontro columna de keywords en el archivo.")
            except Exception as e:
                st.warning(f"Error leyendo Campaign CSV: {e}")

        st.markdown("---")

        st_col = cols["search_term"]
        if not st_col:
            st.warning("No se encontro columna 'Customer Search Term' en el archivo.")
        else:
            harvests = _harvest_candidate_rows(df, cols, min_clicks=harv_min_clicks, price=harv_precio,
                                               target_acos=harv_target_acos)

            if not harvests.empty:
                df_harv = sorted_harvest(harvests)

                # ── Anti-canibalizacion: marcar duplicados ────────────
                if existing_exact_kws:
                    df_harv["Ya en Exact"] = df_harv["Search Term"].str.lower().str.strip().isin(existing_exact_kws).map(
                        {True: "Ya en Exact activo", False: ""}
                    )
                    n_dupes = (df_harv["Ya en Exact"] != "").sum()
                    n_nuevos = len(df_harv) - n_dupes
                else:
                    df_harv["Ya en Exact"] = ""
                    n_dupes = 0
                    n_nuevos = len(df_harv)

                n_alta  = (df_harv["Prioridad"] == "Alta").sum()
                n_media = (df_harv["Prioridad"] == "Media").sum()
                avg_bid = pd.to_numeric(df_harv["Bid Sugerido"], errors="coerce").mean()
                avg_bid_text = money(avg_bid, currency_code) if pd.notna(avg_bid) else "—"

                if existing_exact_kws:
                    hm1, hm2, hm3, hm4, hm5 = st.columns(5)
                    hm1.metric("Total candidatos", len(df_harv))
                    hm2.metric("Alta", n_alta)
                    hm3.metric("Media", n_media)
                    hm4.metric("Bid promedio", avg_bid_text)
                    hm5.metric("Ya en Exact", n_dupes)
                else:
                    hm1, hm2, hm3, hm4 = st.columns(4)
                    hm1.metric("Total candidatos", len(df_harv))
                    hm2.metric("Alta", n_alta)
                    hm3.metric("Media", n_media)
                    hm4.metric("Bid promedio", avg_bid_text)

                def _color_harv_prio(val):
                    if val == "Alta": return "background-color: #C6EFCE; color: #276221"
                    return "background-color: #DBEAFE; color: #1E3A8A"

                def _color_exact_dup(val):
                    if val and "Ya en Exact" in str(val): return "background-color: #FFF3E0; color: #BF360C"
                    return ""

                # The checkbox below renders after the table; its stored value already decides the export.
                incluir_dupes = bool(st.session_state.get("harv_include_dupes"))
                df_harv_export = _harvest_export_rows(df_harv, include_existing_exact=incluir_dupes)

                # df_harv is already sorted by priority, then orders.
                harv_drawn, harv_left_out = _drawn_rows(df_harv)
                if harv_left_out:
                    st.caption(_drawn_rows_caption(len(df_harv), "por prioridad y órdenes",
                                                   exported_rows=len(df_harv_export)))
                styled_harv = harv_drawn.style.map(_color_harv_prio, subset=["Prioridad"])
                if existing_exact_kws:
                    styled_harv = styled_harv.map(_color_exact_dup, subset=["Ya en Exact"])

                st.dataframe(
                    styled_harv,
                    use_container_width=True,
                    height=min(38 + 35 * len(harv_drawn), 800),
                )

                # Export bulk-ready formato Amazon
                st.markdown("---")
                st.markdown("**Export bulk-ready para Amazon — Exact Match**")

                # Checkbox para incluir/excluir duplicados
                if existing_exact_kws and n_dupes > 0:
                    incluir_dupes = st.checkbox(
                        f"Incluir {n_dupes} keywords que ya estan en Exact activo",
                        value=False,
                        key="harv_include_dupes",
                    )
                    if not incluir_dupes:
                        st.caption(f"Exportando {len(df_harv_export)} keywords nuevas (excluidas {n_dupes} que ya estan en Exact).")
                    else:
                        st.caption("Exportando TODAS las keywords incluyendo las que ya estan en Exact.")
                else:
                    st.caption("Campaign Name y Ad Group Name vacios — el AM los completa antes de subir.")

                # Export de la tabla de candidatos
                # Que le falta a cada candidato para poder ejecutarse. Sin
                # Campaign Name o Ad Group el termino no se puede aplicar ni
                # a mano: el AM tiene que completar el dato primero.
                df_harv_export = df_harv_export.copy()
                df_harv_export["Falta dato"] = _missing_data_reasons(df_harv_export)

                metadata_cols = ["Search Term", "Campaign", "Ad Group", "Clicks", "Orders",
                                 "ACoS", "CVR%", "Bid Sugerido", "Regla", "Prioridad"]
                if "Ya en Exact" in df_harv_export.columns:
                    metadata_cols.append("Ya en Exact")
                metadata_cols.append("Falta dato")
                metadata_df = df_harv_export[metadata_cols].copy()

                _n_incompletos = int((metadata_df["Falta dato"] != "").sum())
                if _n_incompletos:
                    st.caption(
                        f"{_n_incompletos} de {len(metadata_df)} candidatos no traen "
                        "Campaign Name o Ad Group en el STR. Mira la columna "
                        "**Falta dato**: sin ese campo el termino no se puede "
                        "aplicar en Amazon, ni siquiera a mano."
                    )

                # TODO(M2-bulkfile): restaurar la descarga cuando el modulo lea el Bulk
                # File. Los constructores ya existen en core.bulk_export; lo que falta
                # son los IDs, que salen de core.bulk_parser.parse_bulk_str().
                st.warning(
                    "**La descarga de bulk esta temporalmente deshabilitada.** "
                    "Para que Amazon acepte un bulk hacen falta los IDs numericos "
                    "de campana y ad group, y el Search Term Report standalone no "
                    "los trae: por eso los archivos de harvest que este modulo "
                    "generaba antes rebotaban al subirlos. "
                    "El modulo esta migrando al Bulk File de Amazon, que si los trae. "
                    "Mientras tanto, la tabla de arriba se puede seguir usando para "
                    "revisar los candidatos y armar el bulk a mano."
                )

                from datetime import date as _date_harv
                _harv_today = _date_harv.today().isoformat()
                _xlsx_download(
                    "Descargar candidatos de harvest (.xlsx)", lambda: _xlsx_bytes(metadata_df),
                    file_name=f"harvest_candidatos_{_harv_today}.xlsx", key="harv_dl", row_count=len(metadata_df),
                    fingerprint=(source.signature, tuple(st.session_state.get("str_portfolio_filter") or ()),
                                 harv_target_acos, harv_precio, harv_min_clicks, frozenset(existing_exact_kws),
                                 st.session_state.get("harv_include_dupes"), _harv_today),
                )
            else:
                st.info("No se encontraron candidatos de harvest con los criterios actuales.")

    # Tab 4 consumes core/ai_tab over the ai/agents/str agent.
    with tab4:
        from core import ai_tab
        ai_lang = ai_tab.app_language()
        str_labels = _STR_LABELS.get(ai_lang, _STR_LABELS["es"])
        st.subheader(str_labels["title"])
        st.caption(str_labels["caption"])
        ai_labels_str = ai_tab.ai_labels(ai_lang, str_labels)

        from ai.config import AI_ENABLED
        if not AI_ENABLED:
            st.caption(str_labels["disabled"])
        else:
            st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
            ai_params = StrAnalysisParams(
                target_acos=int(target_acos), price=precio_producto, harvest_target_acos=int(harv_target_acos),
                harvest_price=harv_precio, harvest_min_clicks=int(harv_min_clicks),
                brand_terms=normalized_brand_terms(brand_terms),
            )
            from_api = source.source != SOURCE_FILE
            # A stored analysis covers the whole account: the worker cannot reproduce a portfolio filter.
            portfolio_filtered = len(df) != len(df_raw)
            ai_frame = df_raw if from_api else df
            ai_input = build_analysis_input(
                ai_frame, cols, ai_params, currency_code=currency_code, lang=ai_lang,
                candidates=None if from_api and portfolio_filtered else candidates,
                # The anti-cannibalization CSV is a manual file: it never reaches a stored analysis.
                existing_exact_terms=None if from_api else existing_exact_kws,
            )
            price_notice = _missing_price_notice(ai_params)
            if ai_input.data is None:
                st.info(str_labels["no_rows"])
                if price_notice:
                    st.info(price_notice)
            elif from_api:
                if price_notice:
                    st.info(price_notice)
                if portfolio_filtered:
                    st.caption("El análisis IA cubre todos los portfolios de la cuenta, no sólo los filtrados.")
                if existing_exact_kws:
                    st.caption("El análisis IA guardado no usa el Campaign CSV de anti-canibalización.")
                stored_analysis, stored_state = _render_stored_analysis(source, ai_input, ai_params, lang=ai_lang,
                                                                        labels=ai_labels_str)
            else:
                if price_notice:
                    st.info(price_notice)
                ai_data = ai_input.data
                # The AM is here and the page asks for the price: a file waits for it or for the click.
                analysis = ai_tab.resolve_analysis(
                    slug="str", payload=ai_data,
                    file_signature=source.signature,
                    labels=ai_labels_str, show_previous=False, auto_fire=price_notice is None)
                if analysis is not None:
                    render_neg, render_harv = ai_tab.records_for_render(
                        "str", analysis, ai_data, (ai_input.negative_records, ai_input.harvest_records))

                    def _render_result(result, a, _n=render_neg, _h=render_harv,
                                       _bt=list(ai_params.brand_terms), _lab=ai_labels_str,
                                       _cc=currency_code, _camps=ai_data.campanas):
                        _render_str_ai_result(result, a, _n, _h, _bt, _lab, _cc, campaign_records=_camps)

                    ai_tab.render_analysis(analysis, slug="str",
                                           labels=ai_labels_str,
                                           render_result=_render_result)
                    ai_tab.publish_analysis_to_chat(
                        "str", analysis, ai_data, module_label="Search Term Report", subject=source.label,
                        reading=partial(_file_analysis_reading, params=ai_params.as_dict(), lang=ai_lang,
                                        negative_records=render_neg, harvest_records=render_harv,
                                        currency_code=currency_code),
                        annotate=partial(ai_tab.annotate_row_ids,
                                         labels_by_id=_str_row_labels(render_neg, render_harv)))

    # ══════════════════════════════════════════════════════════════
    # TAB 5: Por Campana (NUEVO)
    # ══════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("Performance por Campana")
        st.caption("Metricas agregadas desde el STR por campana. Clasificacion Brand/No Brand automatica.")

        camp_col = cols["campaign"]
        if not camp_col or camp_col not in df.columns:
            st.warning("No se encontro columna de campana en el archivo.")
        else:
            # ── Aggregate by campaign ──────────────────────────
            df_camp = df.groupby(camp_col).agg(
                Impressions=("_imps", "sum"),
                Clicks=("_clicks", "sum"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index()

            df_camp.rename(columns={camp_col: "Campaign"}, inplace=True)
            df_camp["ACoS"] = df_camp.apply(
                lambda r: round(r["Spend"] / r["Sales"] * 100, 1) if r["Sales"] > 0 else 0, axis=1
            )
            df_camp["ROAS"] = df_camp.apply(
                lambda r: round(r["Sales"] / r["Spend"], 2) if r["Spend"] > 0 else 0, axis=1
            )
            df_camp["CTR"] = df_camp.apply(
                lambda r: round(r["Clicks"] / r["Impressions"] * 100, 2) if r["Impressions"] > 0 else 0, axis=1
            )
            df_camp["CVR"] = df_camp.apply(
                lambda r: round(r["Orders"] / r["Clicks"] * 100, 2) if r["Clicks"] > 0 else 0, axis=1
            )
            df_camp["CPC"] = df_camp.apply(
                lambda r: round(r["Spend"] / r["Clicks"], 2) if r["Clicks"] > 0 else 0, axis=1
            )
            df_camp["Tipo"] = df_camp["Campaign"].apply(
                lambda n: "Brand" if _is_brand_campaign(n) else "No Brand"
            )
            df_camp = df_camp.sort_values("Sales", ascending=False)

            # ── KPIs ──────────────────────────────────────────
            total_camps = len(df_camp)
            brand_camps = (df_camp["Tipo"] == "Brand").sum()
            nobrand_camps = total_camps - brand_camps
            top_spend_camp = df_camp.loc[df_camp["Spend"].idxmax(), "Campaign"] if len(df_camp) > 0 else "—"
            # Truncate long name
            top_spend_display = top_spend_camp[:35] + "..." if len(top_spend_camp) > 35 else top_spend_camp

            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1:
                st.markdown(kpi_card("Total Campanas", str(total_camps)), unsafe_allow_html=True)
            with kc2:
                st.markdown(kpi_card("Brand", str(brand_camps)), unsafe_allow_html=True)
            with kc3:
                st.markdown(kpi_card("No Brand", str(nobrand_camps)), unsafe_allow_html=True)
            with kc4:
                st.markdown(kpi_card("Mayor Spend", html.escape(top_spend_display)), unsafe_allow_html=True)

            st.markdown("")

            # ── Table with color coding ───────────────────────
            def _color_acos_camp(val):
                try:
                    v = float(val)
                    if v == 0:
                        return "color:#999"
                    if v <= 30:
                        return "background-color:#C6EFCE;color:#276221"
                    if v <= 55:
                        return "background-color:#FFEB9C;color:#9C5700"
                    return "background-color:#FFC7CE;color:#9C0006"
                except (ValueError, TypeError):
                    return ""

            def _color_brand_tipo(val):
                if val == "Brand":
                    return "background-color:#E0F7FA;color:#006064"
                return "background-color:#F5F5F5;color:#616161"

            display_camp_cols = ["Campaign", "Tipo", "Impressions", "Clicks", "Spend", "Sales",
                                 "Orders", "ACoS", "ROAS", "CTR", "CVR", "CPC"]

            styled_camp = df_camp[display_camp_cols].style\
                .map(_color_acos_camp, subset=["ACoS"])\
                .map(_color_brand_tipo, subset=["Tipo"])\
                .format({"Spend": money_format, "Sales": money_format, "CPC": money_format,
                         "ACoS": "{:.1f}%", "CTR": "{:.2f}%", "CVR": "{:.2f}%", "ROAS": "{:.2f}x",
                         "Impressions": "{:,.0f}", "Clicks": "{:,.0f}", "Orders": "{:,.0f}"})

            st.dataframe(styled_camp, use_container_width=True, height=min(38 + 35 * len(df_camp), 600), hide_index=True)

            # ── Term type distribution by campaign ────────────
            st_col = cols["search_term"]
            if brand_terms and st_col and st_col in df.columns:
                st.markdown("---")
                st.markdown("**Distribucion Brand/Generic/Long-tail por campana**")

                df["_term_type_camp"] = df[st_col].apply(lambda t: _classify_term_type(t, brand_terms))
                tt_camp = df.groupby([camp_col, "_term_type_camp"]).agg(
                    Spend=("_spend", "sum"),
                ).reset_index()
                tt_pivot = tt_camp.pivot_table(
                    index=camp_col, columns="_term_type_camp", values="Spend", fill_value=0
                ).reset_index()
                tt_pivot.rename(columns={camp_col: "Campaign"}, inplace=True)

                # Add % columns
                for col_name in ["Brand", "Generic", "Long-tail"]:
                    if col_name not in tt_pivot.columns:
                        tt_pivot[col_name] = 0.0

                tt_pivot["Total"] = tt_pivot["Brand"] + tt_pivot["Generic"] + tt_pivot["Long-tail"]
                tt_pivot["% Brand"] = tt_pivot.apply(
                    lambda r: round(r["Brand"] / r["Total"] * 100, 1) if r["Total"] > 0 else 0, axis=1
                )
                tt_pivot = tt_pivot.sort_values("Total", ascending=False)

                show_cols = ["Campaign", "Brand", "Generic", "Long-tail", "Total", "% Brand"]
                st.dataframe(
                    tt_pivot[show_cols].style.format({
                        "Brand": money_format, "Generic": money_format,
                        "Long-tail": money_format, "Total": money_format, "% Brand": "{:.1f}%"
                    }),
                    use_container_width=True, hide_index=True,
                )

            # ── Download ──────────────────────────────────────
            st.markdown("---")
            from datetime import date as _date
            camp_today = _date.today().strftime("%Y-%m-%d")
            st.download_button(
                "Descargar Performance por Campana (Excel)",
                data=_xlsx_bytes(df_camp),
                file_name=f"STR_por_campana_{camp_today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key="str_camp_dl",
            )

    from core import app_chat
    if source.source != SOURCE_FILE:
        _share_stored_analysis(source, stored_analysis, stored_state or app_chat.AnalysisState.MISSING)
    elif analysis is None:
        app_chat.withdraw_analysis("str")
