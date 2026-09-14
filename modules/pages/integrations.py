"""M38 Integraciones — system credentials and connected accounts catalog.

Two levels with different blast radii: a broken system credential takes down
the integration for every client; an expired client authorization only breaks
one. The UI keeps them visually separate and confirms with asymmetric friction.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from html import escape

import streamlit as st

from core.integrations import catalog, crypto, lookup, oauth, roles
from core.integrations.store import (REVOKED_STATUS, SEALING_KEY_SETTING, StoreError,
                                     open_stores)
from core.ui import i18n, palette

# Status colors. Palette approximations for module-level constants used in
# inline HTML fragments; the word carries the meaning, color only accompanies.
GREEN = palette.OK_INK
ATTENTION_COLOR = palette.ACCENT_HOVER
GREY_TEXT = palette.FG_MUTED
TEXT_COLOR = palette.FG
ORANGE_RAIL = palette.ACCENT
GROUP_RULE_COLOR = palette.IDLE

_FLASH = "int_flash"
_NONCE = "int_nonce"
# Signal-based modal pattern: `_detail` sets this and reruns; the next
# render() opens `_remove_dialog` from top level, sidestepping the
# `Dialogs may not be nested inside other dialogs` restriction of 1.43.2.
_PENDING_REMOVE = "int_pending_remove"

# Seven-cell row weights. `StyledColumn` computes `width: calc(pct% - gap)` and
# splits the remainder evenly.
_ROW_WEIGHTS = [0.45, 3.2, 1.8, 3.2, 1.9, 1.75, 1.0]

# Everything hangs off the class Streamlit derives from a container's key
# (`convertKeyToClassName` → `st-key-<key>` in the 1.43.2 bundle). Without
# that anchor a testid rule would leak into other pages' widgets.
_CSS_LIST = (
    "<style>"
    + palette.list_shell("ig_lista")
    + '.st-key-ig_lista, [class*="st-key-ig_banda_"] { gap: 0; }'
    + f"""
[class*="st-key-ig_fila_"], [class*="st-key-ig_att_"] {{
    min-height: 44px;
    border-bottom: 1px solid {palette.LINE};
    /* Permanent indent + conditional color: nothing jumps when a row
       flips to attention. */
    border-left: 3px solid transparent;
    padding-left: 9px;
}}
[class*="st-key-ig_att_"] {{
    border-left-color: {palette.ACCENT};
    background: {palette.ATTENTION_GLOW};
}}
[class*="st-key-ig_fila_"]:hover,
[class*="st-key-ig_fila_"]:focus-within {{ background: {palette.ROW_HOVER}; }}

.st-key-ig_lista [data-testid="stHorizontalBlock"] {{ min-height: 44px; }}

/* Two margins to cancel: stMarkdownContainer ships margin-bottom: -1rem on
   non-label markdown, and the <p> ships its own. Cancelling one is not enough
   to close the row at 44px. */
.st-key-ig_lista [data-testid="stMarkdownContainer"] p {{ line-height: 1.25; }}

/* 40px is StyledBaseButton's minElementHeight; picking 44 fits the tertiary
   button without fighting any min-height. */
.st-key-ig_lista [data-testid^="stBaseButton-"] {{ min-height: 44px; }}
/* Label is a nested <p> with word-break: break-word; without nowrap, longer
   labels wrap and the row height explodes. */
.st-key-ig_lista [data-testid^="stBaseButton-"] p {{
    font-size: 14px; font-weight: 600; white-space: nowrap; color: {palette.ACCENT_HOVER};
}}
.st-key-ig_lista [data-testid^="stBaseButton-"]:focus-visible {{
    box-shadow: 0 0 0 3px {palette.ACCENT} !important;
}}

/* Below 900px the Class and Done cells drop out. Below 640 StyledColumn stacks
   the seven cells and this degrades — desktop-first by design for two admins. */
@media (max-width: 900px) {{
    .st-key-ig_lista [data-testid="stColumn"]:nth-child(3),
    .st-key-ig_lista [data-testid="stColumn"]:nth-child(5) {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{
    .st-key-ig_lista * {{ transition-duration: 0.01ms !important; }}
}}
</style>
"""
)

NO_DB = "sin_base"
NO_SEALING = "sin_sellado"
NO_CREDENTIAL = "sin_credencial"
# Running with a credential loaded before the portal existed, not yet imported.
PENDING_MIGRATION = "pending_migration"
CONNECTED = "conectada"
COMING_SOON = "proximamente"
# Works, but its credential lives outside the portal's reach.
OUT_OF_SCOPE = "fuera_de_alcance"

# Worst first inside a band. The band already sorts by urgency; this sorts
# inside — the row that reclaims attention is always the top of its band.
_PRIORITY = {
    NO_SEALING: 1,
    NO_CREDENTIAL: 2,
    PENDING_MIGRATION: 3,
    CONNECTED: 4,
    OUT_OF_SCOPE: 5,
    NO_DB: 6,
    COMING_SOON: 7,
}


# Band identifiers, internal only: they key `_GROUP_BY_STATE` and fix the order
# of the bands. What a band is CALLED on screen is looked up per render, so it
# follows the language toggle instead of freezing at import time.
GROUP_UNCERTAIN = "uncertain"
GROUP_ATTENTION = "attention"
GROUP_LOADABLE = "loadable"
GROUP_LIVE = "live"

_GROUP_LABEL_KEYS = {
    GROUP_UNCERTAIN: "integrations.band.uncertain",
    GROUP_ATTENTION: "integrations.band.attention",
    GROUP_LOADABLE: "integrations.band.loadable",
    GROUP_LIVE: "integrations.band.live",
}

# Order is fixed; only which bands exist on any given day varies.
_GROUP_ORDER = (GROUP_UNCERTAIN, GROUP_ATTENTION, GROUP_LOADABLE, GROUP_LIVE)

# Client-account states (REAUTORIZAR) live in the Marketplaces module now:
# accounts are the empleado's turf, credentials are the admin's.
_GROUP_BY_STATE = {
    NO_DB: GROUP_UNCERTAIN,
    NO_SEALING: GROUP_ATTENTION,
    # Works, but two copies of the key drift apart — the exact problem the
    # portal was built to end.
    PENDING_MIGRATION: GROUP_ATTENTION,
    NO_CREDENTIAL: GROUP_LOADABLE,
    CONNECTED: GROUP_LIVE,
    OUT_OF_SCOPE: GROUP_LIVE,
}


@dataclass
class Context:
    username: str
    is_admin: bool
    has_db: bool
    public_key: str | None = None
    credentials: dict = field(default_factory=dict)
    connections: dict = field(default_factory=dict)
    origins: dict = field(default_factory=dict)
    # An empty {} means two opposite things: "nothing loaded" and "the read
    # failed". Without splitting them, an intermittent PostgREST paints
    # "Sin configurar" over credentials that actually exist.
    read_ok: bool = True

    @property
    def sealing_ready(self) -> bool:
        return bool(self.public_key)


def render(username: str = "", role: str = roles.USER) -> None:
    """Sistema → Integraciones: system credentials only. Admin-only.

    Client accounts (OAuth grants) live in the Marketplaces module: admin
    owns the app registration, any empleado onboards a client account.
    """
    _purge_orphan_secrets()

    st.header(i18n.t("integrations.page.header"))
    st.caption(i18n.t("integrations.page.caption"))

    if not roles.is_admin(role):
        st.info(i18n.t("integrations.page.admin_only_info"))
        return

    context = _load_context(username, is_admin=True)

    with st.expander(i18n.t("integrations.sop.expander_title"), expanded=False):
        st.markdown(i18n.t("integrations.sop_md"))
    st.divider()
    st.markdown(_CSS_LIST, unsafe_allow_html=True)

    flash = st.session_state.pop(_FLASH, None)
    if flash:
        st.success(flash)

    # Signal-based remove: opened from _detail inside a dialog, resolved here
    # at top level. Popping BEFORE opening the dialog avoids a re-open loop
    # after the user confirms.
    pending_remove = st.session_state.pop(_PENDING_REMOVE, None)
    if pending_remove:
        integration = catalog.by_slug(pending_remove)
        if integration is not None:
            _remove_dialog(integration, _live_connection_count(context, integration.slug), context)

    _blocking_notice(context)

    with st.container(key="ig_lista"):
        _verdict(context)
        bands = _classify(context)
        dibujadas = 0
        for rotulo in _GROUP_ORDER:
            rows = bands.get(rotulo)
            if not rows:
                continue
            _row_group(dibujadas, rotulo, rows, context)
            dibujadas += 1
        _coming_soon_footer(context)


def _classify(context: Context) -> dict:
    """Assign each integration to its band. COMING_SOON is not a row."""
    bands: dict[str, list[tuple]] = {}
    for integration in catalog.all_integrations():
        status = _state_of(integration, context)
        if status == COMING_SOON:
            continue
        bands.setdefault(_GROUP_BY_STATE[status], []).append((integration, status))
    for rows in bands.values():
        rows.sort(key=lambda par: (_PRIORITY[par[1]], par[0].order))
    return bands


def _verdict(context: Context) -> None:
    """Answer the AM's real question before the inventory. Rail is permanent,
    color is conditional, so nothing jumps when state changes."""
    titular, hay_atencion = _headline(context)
    color = ATTENTION_COLOR if hay_atencion else TEXT_COLOR
    riel = ORANGE_RAIL if hay_atencion else "transparent"
    st.markdown(
        f"<div style='margin:20px 0 4px;border-left:3px solid {riel};padding-left:20px;'>"
        f"<div style='font-size:18px;font-weight:700;line-height:1.3;color:{color};'>"
        f"{titular}</div>"
        f"<div style='margin-top:5px;font-size:14px;color:{GREY_TEXT};'>"
        f"{_summary_count(context)}</div></div>",
        unsafe_allow_html=True,
    )


def _headline(context: Context) -> tuple[str, bool]:
    """Verdict is about the APPs of the agency, not client accounts."""
    if not context.has_db:
        return i18n.t("integrations.verdict.no_db"), True
    if not context.read_ok:
        return i18n.t("integrations.verdict.read_failed"), True
    pendientes = sum(
        1 for i in catalog.all_integrations()
        if _state_of(i, context) in (NO_SEALING, PENDING_MIGRATION)
    )
    if pendientes:
        return i18n.tn("integrations.verdict.needs_attention", pendientes), True
    return i18n.t("integrations.verdict.all_ok"), False


def _summary_count(context: Context) -> str:
    """Portal counts only what admin manages: the APPs, not the accounts."""
    activas = [i for i in catalog.all_integrations() if _state_of(i, context) != COMING_SOON]
    return i18n.tn("integrations.verdict.summary_count", len(activas))


def _row_group(indice: int, rotulo: str, rows: list, context: Context) -> None:
    """An empty band is not drawn: a label with a 0 next to it is chrome, and
    the absence of the attention band is the message."""
    with st.container(key=f"ig_banda_{indice}"):
        st.markdown(_row_group_header(rotulo, len(rows), indice == 0), unsafe_allow_html=True)
        for integration, status in rows:
            _row(integration, status, context)


def _row_group_header(rotulo: str, cuantas: int, primera: bool) -> str:
    color = ATTENTION_COLOR if rotulo in (GROUP_UNCERTAIN, GROUP_ATTENTION) else GREY_TEXT
    typography = "font-size:12px;font-weight:700;letter-spacing:.08em;"
    label = i18n.t(_GROUP_LABEL_KEYS[rotulo])
    return (
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"height:32px;margin-top:{0 if primera else 24}px;padding-bottom:8px;"
        f"border-bottom:1px solid {GROUP_RULE_COLOR};'>"
        f"<span style='{typography}text-transform:uppercase;color:{color};'>{label}</span>"
        f"<span style='{typography}color:{GREY_TEXT};'>{cuantas}</span></div>"
    )


def _row(integration, status: str, context: Context) -> None:
    credential = context.credentials.get(integration.slug)
    kind, phrase = _status_cell(integration, status)
    _ = credential  # silence unused-var warning; kept for future use
    prefijo = "ig_att" if _GROUP_BY_STATE[status] == GROUP_ATTENTION else "ig_fila"
    with st.container(key=f"{prefijo}_{integration.slug}"):
        cells = st.columns(_ROW_WEIGHTS, gap="small", vertical_alignment="center")
        cells[0].markdown(_glyph(kind), unsafe_allow_html=True)
        cells[1].markdown(_name_cell(integration.name), unsafe_allow_html=True)
        cells[2].markdown(_secondary_text(_class_of(integration), truncar=True), unsafe_allow_html=True)
        cells[3].markdown(_status_phrase(phrase, kind), unsafe_allow_html=True)
        cells[4].markdown(
            _secondary_text(_fact(integration, status, credential, context), truncar=True),
            unsafe_allow_html=True,
        )
        with cells[5]:
            _action(integration, status, credential, context)
        with cells[6]:
            _detail_button(integration, status, credential, context)


def _detail_button(integration, status: str, credential, context: Context) -> None:
    if status in (NO_DB, OUT_OF_SCOPE) or credential is None:
        return
    if st.button(
        i18n.t("integrations.row.btn_detail"),
        key=f"int_det_{integration.slug}",
        type="tertiary",
    ):
        _detail_dialog(integration, context)


def _coming_soon_footer(context: Context) -> None:
    """What doesn't exist yet is a sentence, not a row. That structural class
    change is what separates it from 'Andando, fuera del portal' without color."""
    faltan = [i for i in catalog.all_integrations() if _state_of(i, context) == COMING_SOON]
    if not faltan:
        return
    if len(faltan) == 1:
        unica = faltan[0]
        motivo = (unica.pending_reason or "").rstrip(".")
        body = f"{unica.name} — {motivo}." if motivo else f"{unica.name}."
    else:
        body = " · ".join(i.name for i in faltan) + "."
    st.markdown(
        f"<div style='margin-top:24px;font-size:13px;line-height:1.5;color:{GREY_TEXT};'>"
        f"<span style='font-weight:600;'>"
        f"{i18n.t('integrations.footer.coming_soon_label')}</span> {body}</div>",
        unsafe_allow_html=True,
    )


def _action(integration, status: str, credential, context: Context) -> None:
    """Only paint what can work; permission is signalled by absence, not disabled
    buttons. If DB or sealing is missing, the status cell already said so."""
    if status in (NO_DB, NO_SEALING, OUT_OF_SCOPE):
        return
    if credential is None:
        if st.button(
            i18n.t("integrations.row.btn_add_credential"),
            key=f"int_add_{integration.slug}",
            type="tertiary",
        ):
            _credential_dialog(integration, context)
        return
    # Admin section: the only action on a loaded credential is to replace it.
    # Connecting client accounts moved to the Marketplaces module (empleado's turf).
    if st.button(
        i18n.t("integrations.row.btn_replace"),
        key=f"int_repl_{integration.slug}",
        type="tertiary",
    ):
        _credential_dialog(integration, context, replacing=True)


def _load_context(username: str, is_admin: bool) -> Context:
    stores = open_stores()
    if stores is None:
        return Context(username=username, is_admin=is_admin, has_db=False)
    credential_store, connection_store, settings_store = stores
    # Origins go FIRST: resolving them migrates credentials still in .env or
    # secrets.toml, so reading states before that would show the pre-migration
    # snapshot.
    origenes = {i.slug: lookup.origin_of(i.slug) for i in catalog.all_integrations()}
    credentials = credential_store.list_states()
    connections = connection_store.by_integration_slug()
    return Context(
        username=username,
        is_admin=is_admin,
        has_db=True,
        read_ok=not (credential_store.read_failed or connection_store.read_failed),
        public_key=settings_store.get(SEALING_KEY_SETTING) or crypto.public_key_from_env(),
        credentials=credentials,
        connections=connections,
        origins=origenes,
    )


def _blocking_notice(context: Context) -> None:
    """One notice at the top, only for who can resolve it."""
    if not context.has_db:
        st.warning(i18n.t("integrations.notice.no_db_warning"))
        return
    if not context.is_admin:
        if not context.credentials:
            st.caption(i18n.t("integrations.notice.none_enabled"))
        return
    if not context.sealing_ready and any(i.is_sealed and i.available for i in catalog.all_integrations()):
        st.info(i18n.t("integrations.notice.worker_not_run"))


def _detail_dialog(integration, context: Context) -> None:
    """Read-only detail. Actions (Quitar, Reemplazar) live on the row now —
    Streamlit 1.43.2 forbids nested @st.dialog.

    The decorator is applied here, per call, instead of at import: `@st.dialog`
    binds its title once, which would freeze every dialog heading in whichever
    language was current the first time this module was imported.
    """
    st.dialog(i18n.t("integrations.dialog.detail_title"))(_detail_dialog_body)(
        integration, context
    )


def _detail_dialog_body(integration, context: Context) -> None:
    st.markdown(f"**{integration.name}**")
    _detail(integration, context.credentials.get(integration.slug), context)


def _detail(integration, credential, context: Context) -> None:
    """Read-only detail. Quitar cannot live inside this dialog: nested
    @st.dialog is forbidden in Streamlit 1.43.2."""
    st.markdown(i18n.t("integrations.detail.section_system_credential"))
    st.markdown(
        _facts_list(
            [
                (i18n.t("integrations.detail.label_fingerprint"),
                 credential.fingerprint or "—"),
                (i18n.t("integrations.detail.label_created_by"),
                 credential.created_by or "—"),
                (i18n.t("integrations.detail.label_updated_at"),
                 _short_date(credential.updated_at)),
                (i18n.t("integrations.detail.label_storage"),
                 i18n.t("integrations.detail.storage_encrypted")
                 if integration.is_sealed
                 else i18n.t("integrations.detail.storage_plain")),
            ]
            + [
                (field.label, str(credential.public_fields.get(field.key, "—")))
                for field in integration.public_field_defs
            ]
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        i18n.t("integrations.detail.caption_sealed")
        if integration.is_sealed
        else i18n.t("integrations.detail.caption_plain")
    )
    heredado = context.origins.get(integration.slug)
    if heredado is not None and heredado.detail.startswith("importada de"):
        # `heredado.detail` is a Spanish phrase assembled in
        # core/integrations/lookup.py ("importada de .env"); the sentence around
        # it translates, the phrase inside it needs that module's own pass.
        st.warning(
            i18n.t("integrations.detail.warning_imported_copy", detail=heredado.detail)
        )
    # Signal + rerun instead of a nested @st.dialog: the next render() sees
    # the signal and opens _remove_dialog from top level.
    if st.button(i18n.t("integrations.detail.btn_remove_credential"),
                 key=f"int_del_{integration.slug}",
                 type="secondary", use_container_width=True):
        st.session_state[_PENDING_REMOVE] = integration.slug
        st.rerun()


def _credential_dialog(integration, context: Context, replacing: bool = False) -> None:
    """Decorator applied per call so the title follows the language toggle."""
    st.dialog(i18n.t("integrations.dialog.credential_title"))(_credential_dialog_body)(
        integration, context, replacing
    )


def _credential_dialog_body(
    integration, context: Context, replacing: bool = False
) -> None:
    st.markdown(f"**{integration.name}**")
    st.caption(i18n.t("integrations.credential.caption_blast_radius"))

    nonce = _current_nonce()
    values: dict[str, str] = {}
    with st.form(f"int_form_{integration.slug}", clear_on_submit=True, border=False):
        for field in integration.fields:
            values[field.key] = st.text_input(
                field.label,
                # A secret is never pre-filled, whatever the catalog says: the
                # form is also the edit path, and a default sitting in a
                # password box reads like the stored value came back.
                value="" if field.secret else field.default,
                type="password" if field.secret else "default",
                key=f"int_secret_{nonce}_{field.key}" if field.secret else f"int_pub_{nonce}_{field.key}",
                help=field.help_text or None,
            )
        submitted = st.form_submit_button(
            i18n.t("integrations.credential.btn_replace")
            if replacing
            else i18n.t("integrations.credential.btn_save"),
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    secret_field = integration.secret_field
    secreto = (values.get(secret_field.key, "") if secret_field else "").strip()
    if not secreto:
        st.error(
            i18n.t(
                "integrations.credential.error_missing_secret",
                field=secret_field.label,
            )
        )
        return

    publicos = {field.key: values.get(field.key, "").strip() for field in integration.public_field_defs}
    faltantes = [field.label for field in integration.public_field_defs if not publicos[field.key]]
    if faltantes:
        st.error(
            i18n.tn(
                "integrations.credential.error_missing_public",
                len(faltantes),
                fields=", ".join(faltantes),
            )
        )
        return

    if integration.is_sealed:
        try:
            secreto = crypto.seal(secreto, context.public_key)
        except crypto.SealError as exc:
            st.error(
                i18n.t("integrations.credential.error_seal_failed", error=exc)
            )
            return

    stores = open_stores()
    if stores is None:
        st.error(i18n.t("integrations.credential.error_no_db_save"))
        return
    try:
        stores[0].save(
            slug=integration.slug,
            secret=secreto,
            sealed=integration.is_sealed,
            public_fields=publicos,
            user=context.username,
        )
    except StoreError as exc:
        st.error(str(exc))
        return

    _rotate_nonce()
    lookup.invalidate_cache()
    st.session_state[_FLASH] = i18n.t(
        "integrations.credential.flash_saved", integration=integration.name
    )
    st.rerun()


def _live_connection_count(context: Context, slug: str) -> int:
    """Accounts that stop refreshing the moment this credential goes: a refresh
    token is bound to the client application that minted it."""
    return sum(
        1 for connection in context.connections.get(slug, [])
        if (connection.status or "").strip().lower() != REVOKED_STATUS
    )


def _remove_dialog(integration, accounts: int, context: Context) -> None:
    """Decorator applied per call so the title follows the language toggle."""
    st.dialog(i18n.t("integrations.dialog.remove_title"))(_remove_dialog_body)(
        integration, accounts, context
    )


def _remove_dialog_body(integration, accounts: int, context: Context) -> None:
    st.markdown(f"**{integration.name}**")
    if accounts:
        st.warning(i18n.tn("integrations.remove.warning_accounts", accounts))
    confirmacion = st.text_input(
        i18n.t("integrations.remove.confirm_input_label", name=integration.name)
    )
    if st.button(
        i18n.t("integrations.remove.btn_confirm"),
        type="primary",
        disabled=confirmacion.strip() != integration.name,
        use_container_width=True,
    ):
        stores = open_stores()
        if stores is None:
            st.error(i18n.t("integrations.remove.error_no_db"))
            return
        try:
            stores[0].remove(integration.slug, context.username)
        except StoreError as exc:
            st.error(str(exc))
            return
        lookup.invalidate_cache()
        st.session_state[_FLASH] = i18n.t(
            "integrations.remove.flash_removed", integration=integration.name
        )
        st.rerun()


def _state_of(integration, context: Context) -> str:
    """Portal states only. Client-account trouble (REAUTORIZAR) is Marketplaces's turf."""
    if integration.works_outside:
        return OUT_OF_SCOPE
    if not integration.available:
        return COMING_SOON
    if not context.has_db:
        return NO_DB
    if integration.is_sealed and not context.sealing_ready:
        return NO_SEALING
    if context.credentials.get(integration.slug) is None:
        fuente = context.origins.get(integration.slug)
        if fuente is not None and fuente.pending_migration:
            return PENDING_MIGRATION
        return NO_CREDENTIAL
    return CONNECTED


def _status_cell(integration, status: str) -> tuple[str, str]:
    """(glyph class, phrase). The glyph encodes CLASS; the word names it."""
    if status == OUT_OF_SCOPE:
        return "anda", i18n.t("integrations.status.out_of_scope")
    if status == NO_DB:
        return "ninguno", "—"
    if status == NO_SEALING:
        return "atencion", i18n.t("integrations.status.no_sealing")
    if status == NO_CREDENTIAL:
        return "cargable", i18n.t("integrations.status.no_credential")
    if status == PENDING_MIGRATION:
        return "atencion", i18n.t("integrations.status.pending_migration")
    if not integration.connects_accounts:
        return "anda", i18n.t("integrations.status.credential_loaded")
    # OAuth apps live in a "lista para conectar cuentas" state — the actual
    # accounts hang off this credential in the Marketplaces module.
    return "anda", i18n.t("integrations.status.ready_for_accounts")


# Closed set of three. Redundant on purpose so the screen survives
# color-blindness and print.
_GLYPHS = {
    "anda": ("●", GREEN),
    "atencion": ("▲", ATTENTION_COLOR),
    "cargable": ("○", GREY_TEXT),
}


def _glyph(kind: str) -> str:
    par = _GLYPHS.get(kind)
    if par is None:
        return "<div></div>"
    caracter, color = par
    return (
        f"<div aria-hidden='true' style='font-size:11px;line-height:1.25;"
        f"color:{color};'>{caracter}</div>"
    )


def _name_cell(text: str, sangria: int = 0) -> str:
    return (
        f"<div style='font-size:15px;font-weight:600;line-height:1.25;color:{TEXT_COLOR};"
        f"padding-left:{sangria}px;'>{escape(text)}</div>"
    )


# One-line truncate + tooltip: a long created_by ("migración desde
# datadive.api_key") would wrap to three lines and unbalance row heights.
_SINGLE_LINE = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"


def _secondary_text(text: str, sangria: int = 0, truncar: bool = False) -> str:
    corte = _SINGLE_LINE if truncar else ""
    title = f" title='{escape(text, quote=True)}'" if truncar and text else ""
    return (
        f"<div{title} style='font-size:13px;line-height:1.25;color:{GREY_TEXT};"
        f"padding-left:{sangria}px;{corte}'>{escape(text)}</div>"
    )


def _status_phrase(text: str, kind: str) -> str:
    """The reason the row exists: matches the name in size, separates by column
    and by color."""
    color = ATTENTION_COLOR if kind == "atencion" else TEXT_COLOR
    return (
        f"<div style='font-size:15px;font-weight:600;line-height:1.25;"
        f"color:{color};'>{escape(text)}</div>"
    )


def _class_of(integration) -> str:
    return f"{_kind_of(integration)} · {catalog.CATEGORY_TITLE[integration.category]}"


def _fact(integration, status: str, credential, context: Context) -> str:
    """Identify without revealing. Empty when there's nothing to say."""
    if status == OUT_OF_SCOPE:
        return integration.pending_reason or ""
    if status == NO_SEALING:
        return i18n.t("integrations.fact.sealing_tonight")
    if status == PENDING_MIGRATION:
        origen = context.origins.get(integration.slug)
        if origen is None:
            return ""
        return i18n.t(
            "integrations.fact.pending_migration_origin", origin=origen.detail
        )
    if credential is None:
        return ""
    partes = [
        p for p in (credential.fingerprint, credential.created_by,
                    _plain_date(credential.updated_at))
        if p
    ]
    return " · ".join(partes)


def _facts_list(rows: list) -> str:
    cells = "".join(
        f"<tr><td style='color:{GREY_TEXT};padding:2px 14px 2px 0;white-space:nowrap;'>"
        f"{label}</td><td style='color:{TEXT_COLOR};font-weight:600;'>{value}</td></tr>"
        for label, value in rows
    )
    return f"<table style='font-size:0.82rem;border-collapse:collapse;'>{cells}</table>"


def _kind_of(integration) -> str:
    return (
        i18n.t("integrations.kind.oauth")
        if integration.auth_kind == catalog.OAUTH2
        else i18n.t("integrations.kind.api_key")
    )


def _short_date(iso: str) -> str:
    return iso[:10] if iso else "—"


def _plain_date(iso: str) -> str:
    """`2026-08-14` → `14 ago`. Row cell isn't wide enough for a full ISO."""
    if not iso or len(iso) < 10:
        return ""
    try:
        mes, dia = int(iso[5:7]), int(iso[8:10])
    except ValueError:
        return ""
    if not 1 <= mes <= 12:
        return ""
    return f"{dia} {i18n.months_short()[mes - 1]}"


def _current_nonce() -> str:
    if _NONCE not in st.session_state:
        _rotate_nonce()
    return st.session_state[_NONCE]


def _rotate_nonce() -> None:
    st.session_state[_NONCE] = secrets.token_hex(4)


def _purge_orphan_secrets() -> None:
    """ESC-closing a dialog does not trigger a rerun, so a typed secret would
    stick in session_state until something evicts it."""
    active_nonce = st.session_state.get(_NONCE, "")
    for key in [k for k in st.session_state if k.startswith("int_secret_")]:
        if not active_nonce or not key.startswith(f"int_secret_{active_nonce}"):
            del st.session_state[key]
