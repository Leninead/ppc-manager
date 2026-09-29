"""SBH Recommendation (M23): Sponsored Brand Headline targets from DataDive's MKL and the brand's SQP.

Whether a keyword already runs in Sponsored Products comes from the SP structure listing of the Amazon Ads account
the AM picks, or from a Bulk File or keyword export uploaded by hand when there is no account or the AM prefers a file;
without either, that column is unknown and the page says so. The rules live in core/sbh/.
"""
import hashlib
import html
import io
import logging
import re
import zipfile
from datetime import datetime, timezone
from functools import partial

import pandas as pd
import streamlit as st

from ai.agents.sbh.chat_document import row_item
from ai.agents.sbh.context import MAX_HEADLINE_CHARS
from core.amazon_ads.active_keywords import active_keyword_texts
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.chat import app_chat
from core.date_labels import data_of_day_phrase, day_phrase
from core.helpers import extract_sqp_brand, kpi_card, read_sqp
from core.sbh.analysis import ANALYSIS_MODULE, build_analysis_input, sbh_row_labels, sp_file_source
from core.sbh.sp_keyword_file import (
    CHECKED_NONE,
    NOT_READABLE_MESSAGE,
    SpKeywordFile,
    SpKeywordFileError,
    read_sp_keyword_file,
)
from core.sbh.targets import (
    COL_CLUSTER,
    COL_IMPRESSION_SHARE,
    COL_KEYWORD,
    COL_PRIORITY,
    COL_SV,
    PRIORITIES,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    SbhTargets,
    SpKeywordCoverage,
    SqpFormatError,
    query_shares,
    recommend_targets,
)
from core.ui import palette
from modules.pages import search_term_source
from modules.pages.datadive_analyzer import _parse_mkl
from modules.pages.keyword_listing_source import listing_moment, load_keyword_listing
from modules.pages.search_term_source import (
    count_label,
    country_labels,
    group_by_label,
    picker_key,
    profile_today,
)

log = logging.getLogger(__name__)

MODULE_LABEL = "SBH Recommendation"
KEY_PREFIX = "sbh"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SP_BLOCK_TITLE = "Keywords activas en Sponsored Products"
SP_BLOCK_TAG = "Listado diario de Amazon Ads"
ACCOUNT_PLACEHOLDER = "Elegí la cuenta de la marca"
SP_UPLOAD_LABEL = "Sube tu Bulk File o un export de keywords SP (.xlsx o .csv)"
NO_ACCOUNTS_NOTE = ("No hay cuentas de Amazon Ads conectadas: sin archivo, «En SP» queda sin dato. Si conectás la "
                    "cuenta en Sistema → Cuentas conectadas, las keywords que corren en Sponsored Products se leen "
                    "solas todos los días.")
CHOOSE_ACCOUNT_NOTE = ("Elegí la cuenta de la marca del MKL y el SQP para marcar las keywords que ya corren en "
                       "Sponsored Products, o subí su Bulk File a mano. Sin cuenta ni archivo, «En SP» queda sin dato.")
SP_FILE_MODE_NOTE = ("Estás marcando «En SP» con un archivo subido a mano. No se guarda ni se mezcla con los datos de "
                     "Amazon Ads.")
UNREADABLE_FILE_MESSAGE = ("No se pudo leer «{file}»: {reason} Subí el Bulk File tal como lo exporta Campaign Manager "
                           "→ Bulk Operations, o un export de las keywords de Sponsored Products. «En SP» queda sin "
                           "dato.")
NOT_LISTED_NOTE = ("Todavía no hay un listado de las campañas y keywords de Sponsored Products de esta cuenta: se "
                   "listan una vez por día. Mientras tanto, «En SP» queda sin dato.")
REFUSED_NOTE = ("Amazon rechazó el listado de Sponsored Products de esta cuenta: «{refusal}». «En SP» queda sin dato; "
                "si sigue así, avisale a un admin.")
UNREADABLE_NOTE = "«En SP» queda sin dato."
IN_SP_KNOWN_CAPTION = ("«En SP»: la keyword corre hoy en Sponsored Products de {account} con ese mismo texto, en "
                       "cualquier match type (keyword, campaña y ad group habilitados), según el listado {listed}.")
IN_SP_FILE_CAPTION = ("«En SP»: la keyword está en Sponsored Products con ese mismo texto, en cualquier match type, "
                      "según el archivo subido a mano {source}.")
IN_SP_UNKNOWN_CAPTION = ("«En SP» sin dato (—): no hay un listado de Sponsored Products de la cuenta de la marca ni "
                         "un archivo subido a mano que se pueda leer. La prioridad trata esas keywords como si no "
                         "corrieran en SP.")

_MARKDOWN_SPECIALS = re.compile(r"([\\`*_\[\]~$])")
_VERDICT_COLORS = {
    "LANZAR": "background-color:#EAF3DE;color:#173404",
    "PROBAR": "background-color:#FAEEDA;color:#412402",
    "DESCARTAR": "background-color:#F1EFE8;color:#2C2C2A",
}
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre los clusters que ya calculó el módulo: cuáles lanzar como campaña SBH "
                      "primero y con qué headline",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_title": "Clusters en orden de lanzamiento — lectura IA",
           "col_item": "Cluster",
           "counts": "{n} clusters priorizados",
           "stale_body": "Cambió lo que el análisis leyó, por ejemplo las keywords que corren en Sponsored Products. "
                         "Lo que se muestra abajo corresponde a los datos anteriores.",
           "headline": "Headline propuesto: «{headline}» ({chars} caracteres).",
           "headline_too_long": "El headline propuesto tiene {chars} caracteres y el Campaign Builder acepta hasta "
                                "{limit}."},
    "en": {"title": "AI analysis",
           "caption": "AI read on the clusters the module already computed: which to launch first as an SBH campaign "
                      "and with which headline",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_title": "Clusters in launch order — AI read",
           "col_item": "Cluster",
           "counts": "{n} clusters prioritized",
           "stale_body": "What the analysis read changed, for example the keywords that run in Sponsored Products. "
                         "What is shown below belongs to the previous data.",
           "headline": "Proposed headline: “{headline}” ({chars} characters).",
           "headline_too_long": "The proposed headline has {chars} characters and Campaign Builder takes up to "
                                "{limit}."},
}


def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📢</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>SBH Target Recommendation</div>"
        "<div style='font-size:0.82rem;color:#888;'>Recomendar keywords target para Sponsored Brand Headline cruzando "
        "MKL + SQP con las keywords que ya corren en Sponsored Products.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    _how_to_use()

    mkl_col, sqp_col = st.columns(2)
    with mkl_col:
        file_mkl = st.file_uploader("DataDive MKL (.xlsx)", type=["xlsx"], key="sbh_mkl")
    with sqp_col:
        file_sqp = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sbh_sqp")
    coverage = _render_sp_keywords()

    if not file_mkl or not file_sqp:
        _render_empty_state()
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    mkl_bytes = file_mkl.getvalue()
    df_mkl, _ = _parse_mkl(mkl_bytes, file_mkl.name)
    if df_mkl.empty:
        st.warning("No se pudieron parsear keywords del MKL.")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    df_sqp = read_sqp(file_sqp)
    file_sqp.seek(0)
    brand = extract_sqp_brand(file_sqp) or ""
    try:
        shares = query_shares(df_sqp)
    except SqpFormatError as exc:
        st.warning(str(exc))
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    st.success(f"✅ MKL: {len(df_mkl)} keywords · SQP: {len(shares)} queries"
               + (f" · Marca: **{brand}**" if brand else ""))
    targets = recommend_targets(df_mkl, shares, coverage.keyword_texts)
    if targets.keywords.empty:
        st.info("No hay keywords que cumplan los criterios mínimos (SV >= 300).")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    targets_tab, analysis_tab = st.tabs(["📢 Targets", "🤖 Análisis IA"])
    with targets_tab:
        _render_targets(targets, coverage)
    with analysis_tab:
        _render_ai_tab(targets, coverage, brand=brand, mkl_keywords=len(df_mkl), sqp_queries=len(shares),
                       subject=f"marca {brand}" if brand else coverage.account_label or file_mkl.name,
                       data_signature=_data_signature(mkl_bytes, file_sqp.getvalue(), coverage))


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Priorizar keywords target para campañas Sponsored Brand Headline. Clustering automático + "
                       "headline sugerido por cluster.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("DataDive MKL + SQP (requeridos). Las keywords que ya corren en Sponsored Products salen de la "
                       "cuenta de Amazon Ads conectada que elijas; si no está conectada, o preferís un archivo, subí "
                       "el Bulk File (Campaign Manager → Bulk Operations) o un export de keywords SP. Es opcional: "
                       "sin cuenta ni archivo, «En SP» queda sin dato.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Campaign Builder (M10) con el SBH Target Pack para generar bulk de campañas SB.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el MKL de DataDive + el SQP de la marca\n"
            "2. Elegí la cuenta de Amazon Ads de la marca para marcar las keywords que ya corren en SP, o subí su "
            "Bulk File a mano\n"
            "3. Revisá priorización: ALTA (SV≥1000, IS<10%) / MEDIA / BAJA\n"
            "4. Análisis IA: qué clusters lanzar primero y con qué headline\n"
            "5. Descargá el SBH Target Pack con clusters y headlines sugeridos"
        )


def _render_empty_state():
    st.markdown(
        "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
        "border-radius:12px;margin:1rem 0;'>"
        "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
        "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el MKL de DataDive y el SQP de Amazon para "
        "generar recomendaciones.</div>"
        "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
        "Arrastrá o hacé click en los uploaders de arriba</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_sp_keywords() -> SpKeywordCoverage:
    """Mounts the SP keywords block; returns those that run in the chosen account or the uploaded file, or unknown."""
    search_term_source._keep_choices(KEY_PREFIX)
    profiles = search_term_source._available_profiles()
    if not profiles:
        return _render_sp_file(hint=NO_ACCOUNTS_NOTE)
    if st.session_state.get(picker_key(KEY_PREFIX, "manual")):
        return _render_manual_mode()

    groups = group_by_label(profiles)
    card_key = picker_key(KEY_PREFIX, "card")
    st.markdown(search_term_source._card_css(card_key), unsafe_allow_html=True)
    with st.container(border=True, key=card_key):
        header = st.empty()
        account_col, country_col = st.columns([2.2, 1.3])
        account = _choose_account(account_col, list(groups))
        if account is None:
            header.markdown(_block_header("idle", "Sin cuenta elegida"), unsafe_allow_html=True)
            st.caption(CHOOSE_ACCOUNT_NOTE)
            _render_upload_action()
            return SpKeywordCoverage()

        countries = country_labels(groups[account])
        profile_id = search_term_source._resolve_choice(KEY_PREFIX, "profile", list(countries), fallback=None)
        country_col.segmented_control("País", options=list(countries), format_func=countries.get,
                                      key=picker_key(KEY_PREFIX, "profile"))
        option = next(profile for profile in groups[account] if profile.profile_id == profile_id)
        unknown = SpKeywordCoverage(account_label=_account_label(option), profile_id=option.profile_id,
                                    country_code=option.country_code)
        now = datetime.now(timezone.utc)
        try:
            listing = load_keyword_listing(option, profile_today(option, now))
        except ReportReadError as exc:
            log.warning("SBH: SP keywords unreadable for profile %s: %s", option.profile_id, exc)
            header.markdown(_block_header("err", "No se pudo leer"), unsafe_allow_html=True)
            st.error(f"{exc} {UNREADABLE_NOTE}")
            _render_upload_action()
            return unknown
        if not listing.known and listing.refusal:
            header.markdown(_block_header("err", "Sin permiso"), unsafe_allow_html=True)
            st.caption(REFUSED_NOTE.format(refusal=listing.refusal))
            _render_upload_action()
            return unknown
        if not listing.known:
            header.markdown(_block_header("warn", "Sin listar"), unsafe_allow_html=True)
            st.caption(NOT_LISTED_NOTE)
            _render_upload_action()
            return unknown

        keyword_texts = active_keyword_texts(listing.rows)
        header.markdown(_block_header("ok", f"Listadas {listing_moment(listing.listed_at, now, day_phrase)}"),
                        unsafe_allow_html=True)
        info_col, action_col = st.columns([4.2, 3.8], vertical_alignment="center")
        info_col.markdown(search_term_source._muted_line_html([_active_keywords_label(len(keyword_texts)),
                                                               html.escape(unknown.account_label)]),
                          unsafe_allow_html=True)
        with action_col:
            _render_upload_action()
        return SpKeywordCoverage(keyword_texts, unknown.account_label, option.profile_id,
                                 option.country_code, listing.listed_at)


def _render_upload_action() -> None:
    actions_key = picker_key(KEY_PREFIX, "actions")
    st.markdown(search_term_source._actions_css(actions_key), unsafe_allow_html=True)
    with st.container(key=actions_key):
        st.button("Subir archivo manualmente", key=picker_key(KEY_PREFIX, "upload_manual"), type="secondary",
                  icon=":material/upload:", on_click=search_term_source._set_manual_mode, args=(KEY_PREFIX, True))


def _render_manual_mode() -> SpKeywordCoverage:
    with st.container(border=True):
        note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
        note_col.markdown(SP_FILE_MODE_NOTE)
        back_col.button("Volver a datos de Amazon Ads", key=picker_key(KEY_PREFIX, "back_to_api"), type="tertiary",
                        icon=":material/arrow_back:", on_click=search_term_source._set_manual_mode,
                        args=(KEY_PREFIX, False))
        return _render_sp_file(hint="")


def _render_sp_file(*, hint: str) -> SpKeywordCoverage:
    """The SP source stays optional: without a readable file «En SP» is unknown and the page still recommends."""
    uploaded = st.file_uploader(SP_UPLOAD_LABEL, type=["xlsx", "csv"], key=picker_key(KEY_PREFIX, "file"))
    if hint:
        st.caption(hint)
    if uploaded is None:
        return SpKeywordCoverage()
    file_bytes = uploaded.getvalue()
    try:
        sp_file = _read_sp_keyword_file(file_bytes, uploaded.name)
    except (ValueError, zipfile.BadZipFile, OSError) as exc:
        log.warning("SBH: SP keyword file %s could not be read: %s", uploaded.name, exc)
        reason = str(exc) if isinstance(exc, SpKeywordFileError) else NOT_READABLE_MESSAGE
        st.error(UNREADABLE_FILE_MESSAGE.format(file=_markdown_literal(uploaded.name), reason=reason))
        return SpKeywordCoverage()
    file_name_html = html.escape(uploaded.name).replace("$", "&#36;")
    st.markdown(search_term_source._muted_line_html([_file_keywords_label(sp_file), file_name_html]),
                unsafe_allow_html=True)
    return SpKeywordCoverage(sp_file.keyword_texts, file_name=uploaded.name,
                             file_digest=hashlib.sha256(file_bytes).hexdigest()[:16],
                             file_checked_states=sp_file.checked_states)


@st.cache_data(max_entries=3, ttl=3600, show_spinner="Leyendo el archivo de keywords…")
def _read_sp_keyword_file(file_bytes: bytes, file_name: str) -> SpKeywordFile:
    return read_sp_keyword_file(file_bytes, file_name)


def _choose_account(column, accounts: list[str]) -> str | None:
    """The chosen account, never a default one: the files do not say whose they are."""
    key = picker_key(KEY_PREFIX, "account")
    if st.session_state.get(key) not in accounts:
        st.session_state[key] = None
    return column.selectbox("Cuenta", accounts, index=None, placeholder=ACCOUNT_PLACEHOLDER, key=key)


def _block_header(kind: str, label: str) -> str:
    return palette.band_header_html(title=SP_BLOCK_TITLE, tag=SP_BLOCK_TAG,
                                    right=palette.status_pill_html(kind, html.escape(label)))


def _active_keywords_label(count: int) -> str:
    return "1 keyword activa" if count == 1 else f"{count_label(count)} keywords activas"


def _file_keywords_label(sp_file: SpKeywordFile) -> str:
    """A file without a state column lists keywords, not active ones."""
    count = len(sp_file.keyword_texts)
    if sp_file.checked_states != CHECKED_NONE:
        return _active_keywords_label(count)
    return "1 keyword" if count == 1 else f"{count_label(count)} keywords"


def _markdown_literal(text: str) -> str:
    """The text as typed in a markdown element: a file name's $ is never LaTeX, nor its * or _ emphasis."""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", text)


def _account_label(option: ProfileOption) -> str:
    return f"{option.label} · {option.country_code}" if option.country_code else option.label


def _render_targets(targets: SbhTargets, coverage: SpKeywordCoverage):
    df_sbh, cluster_df = targets.keywords, targets.clusters

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card("Targets totales", str(len(df_sbh))), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card("Alta prioridad", str((df_sbh[COL_PRIORITY] == PRIORITY_HIGH).sum())),
                    unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card("Media prioridad", str((df_sbh[COL_PRIORITY] == PRIORITY_MEDIUM).sum())),
                    unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card("Clusters", str(df_sbh[COL_CLUSTER].nunique())), unsafe_allow_html=True)

    prio_filter = st.multiselect(
        "Filtrar por prioridad",
        options=list(PRIORITIES),
        default=[PRIORITY_HIGH, PRIORITY_MEDIUM],
        key="sbh_prio_filter",
    )
    df_show = df_sbh[df_sbh[COL_PRIORITY].isin(prio_filter)] if prio_filter else df_sbh

    def _color_prio(val):
        if "ALTA" in str(val):
            return "background-color: #FFEBEE; color: #B71C1C"
        if "MEDIA" in str(val):
            return "background-color: #FFF8E1; color: #F57F17"
        if "BAJA" in str(val):
            return "background-color: #E8F5E9; color: #1B5E20"
        return ""

    styled = df_show.style.format(na_rep="", precision=2).map(_color_prio, subset=[COL_PRIORITY])
    st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_show), 600))
    st.caption(_in_sp_caption(coverage))

    st.markdown("---")
    st.markdown("#### Clusters + Headline sugerido")
    st.caption("Agrupá keywords por tema para headlines de SBH coherentes.")

    def _color_alta(val):
        try:
            v = int(val)
            if v >= 3:
                return "background-color: #FFEBEE; color: #B71C1C"
            if v >= 1:
                return "background-color: #FFF8E1; color: #F57F17"
            return ""
        except (ValueError, TypeError):
            return ""

    styled_cluster = cluster_df.style
    if "Alta" in cluster_df.columns:
        styled_cluster = styled_cluster.map(_color_alta, subset=["Alta"])
    st.dataframe(styled_cluster, use_container_width=True, hide_index=True)

    headlines = dict(zip(cluster_df["Cluster"], cluster_df["Headline"]))
    for cluster_name in cluster_df["Cluster"].tolist()[:10]:
        cluster_kws = df_sbh[df_sbh[COL_CLUSTER] == cluster_name].nlargest(5, COL_SV)
        with st.expander(f"📢 {cluster_name.title()} — \"{headlines.get(cluster_name, '')}\" ({len(cluster_kws)} KWs)"):
            st.dataframe(
                cluster_kws[[COL_KEYWORD, COL_SV, COL_IMPRESSION_SHARE, COL_PRIORITY]].reset_index(drop=True),
                use_container_width=True, hide_index=True,
            )

    st.markdown("---")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_sbh.to_excel(writer, sheet_name="SBH Targets", index=False)
        cluster_df.to_excel(writer, sheet_name="Clusters", index=False)
    st.download_button(
        f"⬇️ Exportar SBH Target Pack ({len(df_sbh)} keywords)",
        data=buf.getvalue(),
        file_name="sbh_target_pack.xlsx",
        mime=XLSX_MIME,
        key="sbh_dl",
    )


def _in_sp_caption(coverage: SpKeywordCoverage) -> str:
    if not coverage.known:
        return IN_SP_UNKNOWN_CAPTION
    if coverage.from_file:
        return IN_SP_FILE_CAPTION.format(source=_markdown_literal(sp_file_source(coverage)))
    listed = listing_moment(coverage.listed_at, datetime.now(timezone.utc), data_of_day_phrase)
    return IN_SP_KNOWN_CAPTION.format(account=coverage.account_label, listed=listed)


def _render_ai_tab(targets: SbhTargets, coverage: SpKeywordCoverage, *, brand: str, mkl_keywords: int,
                   sqp_queries: int, subject: str, data_signature: str):
    from ai.agents.sbh import chat_document
    from ai.config import AI_ENABLED
    from core import ai_tab

    lang = ai_tab.app_language()
    texts = _AI_TEXTS.get(lang, _AI_TEXTS["es"])
    st.subheader(texts["title"])
    st.caption(texts["caption"])
    if not AI_ENABLED:
        st.caption(texts["disabled"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    analysis_input = build_analysis_input(targets, coverage, brand=brand, mkl_keywords=mkl_keywords,
                                          sqp_queries=sqp_queries, lang=lang)
    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    payload = analysis_input.data
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload, file_signature=data_signature,
                                       labels=labels, auto_fire=False)
    records = analysis_input.records
    if analysis is not None:
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload, analysis_input.records)
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=subject,
        reading=lambda finished, _records=records: chat_document.reading_text(finished.result, _records),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=sbh_row_labels(records)),
        country_code=coverage.country_code, profile_id=coverage.profile_id)


def _render_ai_result(result, analysis, *, records, labels):
    from core import ai_tab

    opinions = result.get("clusters") or []
    rows = sbh_ai_rows(opinions, records, labels)
    warnings = sum(1 for row in rows if row["warning"])
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(opinions)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    row_labels = sbh_row_labels(records)
    synthesis = ai_tab.map_synthesis_text(result.get("synthesis") or {},
                                          lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _VERDICT_COLORS),
                    unsafe_allow_html=True)


def sbh_ai_rows(opinions: list, records: list, labels: dict) -> list[dict]:
    """Display rows for the opinion table: the cluster, its figures, the verdict and the proposed headline."""
    by_id = dict(zip(sbh_row_labels(records), records))
    rows = []
    for opinion in opinions:
        row_id = str(opinion.get("row_id", ""))
        record = by_id.get(row_id)
        if record is None:
            continue
        headline = str(opinion.get("headline") or "").strip()
        proposed = labels["headline"].format(headline=headline, chars=len(headline)) if headline else ""
        too_long = (labels["headline_too_long"].format(chars=len(headline), limit=MAX_HEADLINE_CHARS)
                    if len(headline) > MAX_HEADLINE_CHARS else "")
        rows.append({
            "row_id": row_id,
            "item": row_item(record),
            "type_tag": f"{record.get('keywords')} keywords",
            "metrics": _cluster_metrics(record),
            "badges": [opinion.get("veredicto", "")],
            "confidence": str(opinion.get("confianza", "")).upper(),
            "warning": " ".join(part for part in (opinion.get("advertencia") or "", too_long) if part),
            "reasoning": " ".join(part for part in (opinion.get("razon", ""), proposed) if part),
        })
    return rows


def _cluster_metrics(record: dict) -> list[str]:
    in_sp = record.get("en_sp")
    metrics = [f"SV {count_label(record.get('sv_total') or 0)}", f"{record.get('alta')} ALTA",
               f"{in_sp} en SP" if in_sp is not None else "En SP sin dato"]
    if record.get("is_ponderado") is not None:
        metrics.append(f"IS {record['is_ponderado']}%")
    return metrics


def _data_signature(mkl_bytes: bytes, sqp_bytes: bytes, coverage: SpKeywordCoverage) -> str:
    """What changes when the files, the account or the SP file under the analysis do, not when a value on screen does."""
    files = hashlib.sha256(hashlib.sha256(mkl_bytes).digest() + hashlib.sha256(sqp_bytes).digest()).hexdigest()
    return f"{files[:16]}|{coverage.profile_id or coverage.file_digest}"
