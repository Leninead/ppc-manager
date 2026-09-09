"""Sistema → Cuentas conectadas: per-provider client account management.

Separate from the integrations portal — which holds the agency's own app
credentials (`client_id`, `client_secret`, API keys) and is admin-only —
this screen manages the CLIENT accounts the agency wires against each
provider. Any employee may connect or remove one: the system credential
is already loaded, here we only open the OAuth consent for the seller
and persist the returned refresh token.

Multi-provider by design: when Amazon or Walmart light up, the list
grows straight from the catalog — no parallel flow in each marketplace
module.

Visual language mirrors ``modules/pages/integrations.py``: a 1180px
column, band headers with a provider name + tag + count, tabular rows
of fixed height, monospaced marketplace chip, hover on the row, and a
tertiary "Quitar" action that reads as a link rather than a button.
Both pages should feel like siblings so an operator that learns one
knows the other.
"""
from __future__ import annotations

import html
import os

import streamlit as st

from core.integrations import catalog, crypto, oauth, roles
from core.integrations.store import (SEALING_KEY_SETTING, StoreError, open_stores)
from core.ui import i18n, palette

_REDIRECT_URI_ENV = "INTEGRATIONS_REDIRECT_URI"

# Signal keys — Streamlit 1.43.2 forbids nested @st.dialog, so Remove is
# triggered from the row and the dialog opens from `render()` on the next run.
_PENDING_REMOVE = "accounts_pending_remove"
_CONNECT_URL_KEY = "accounts_connect_consent_url"
_CONNECT_SLUG_KEY = "accounts_connect_slug"

# Column weights: dot, account+chip, meta, status, reauth slot, remove.
# The reauth slot stays empty for healthy rows so every row keeps the same
# column grid and the Quitar action lines up down the list.
_ROW_WEIGHTS = [0.45, 4.2, 2.6, 2.4, 1.8, 1.3]

# All CSS lives in `core.ui.palette` so a palette change lands in one place.
_STYLE = (
    "<style>"
    + palette.list_shell("ac_lista")
    + '.st-key-ac_lista, [class*="st-key-ac_prov_"] { gap: 0; }'
    + palette.provider_band("ac_prov_")
    + palette.tabular_row("ac_row_")
    + palette.outline_button("ac_cta_")
    + "</style>"
)


def _status_html() -> dict[str, str]:
    """Status pill markup, keyed by the value the database stores.

    The keys are `integration_connections.status` values and are never
    translated; only the label inside the pill is. Built per call rather than
    once at import time, so a language switch repaints the pills instead of
    freezing them in whatever language was active when the module first loaded.
    """
    return {
        "activo": palette.status_pill_html("ok", i18n.t("accounts.status_active")),
        "needs_reauth": palette.status_pill_html(
            "warn", i18n.t("accounts.status_needs_reauth")
        ),
    }


def _header() -> None:
    st.markdown(f"## {i18n.t('accounts.header_title')}")
    st.caption(i18n.t("accounts.header_caption"))
    st.divider()


def _verdict(connections_by_slug: dict, providers: list) -> None:
    """One-line summary that answers "does anything need me right now?"."""
    live_slugs = [i.slug for i in providers if i.available and i.connects_accounts]
    needs = 0
    total_live = 0
    for slug in live_slugs:
        for c in connections_by_slug.get(slug, []):
            status = (c.status or "").strip().lower()
            if status == "revocado":
                continue
            total_live += 1
            if status == "needs_reauth":
                needs += 1
    if needs:
        title = i18n.tn("accounts.verdict_needs_reauth", needs)
    else:
        title = i18n.t("accounts.verdict_all_clear")
    coming = sum(1 for i in providers if not i.available)
    detail_parts = [
        i18n.t(
            "accounts.verdict_detail",
            accounts=total_live,
            account_word=i18n.tn("accounts.word_account", total_live),
            providers=len(live_slugs),
            provider_word=i18n.tn("accounts.word_provider", len(live_slugs)),
        )
    ]
    if coming:
        detail_parts.append(i18n.t("accounts.verdict_detail_coming", n=coming))
    st.markdown(
        f"<h2 style='margin:0 0 4px 0;font-size:16px;font-weight:600;color:{palette.FG};'>{html.escape(title)}</h2>"
        f"<p style='margin:0 0 20px 0;font-size:12.5px;color:{palette.FG_SUBTLE};'>{' '.join(detail_parts)}</p>",
        unsafe_allow_html=True,
    )


def render(username: str = "", role: str = roles.USER) -> None:
    """Sistema → Cuentas conectadas. All-employees access."""
    _ = role  # every employee sees the same screen; kept for symmetry with M36
    _header()

    with st.expander(i18n.t("accounts.sop_expander"), expanded=False):
        st.markdown(i18n.t("accounts.sop_md"))

    stores = open_stores()
    if stores is None:
        st.warning(i18n.t("accounts.error_db_unavailable"))
        return

    credential_store, connection_store, _ = stores
    connections_by_slug = connection_store.by_integration_slug()
    credentials_by_slug = credential_store.list_states()

    providers = [i for i in catalog.all_integrations() if i.connects_accounts]
    if not providers:
        st.info(i18n.t("accounts.empty_no_providers"))
        return

    st.markdown(_STYLE, unsafe_allow_html=True)
    with st.container(key="ac_lista"):
        _verdict(connections_by_slug, providers)
        for integration in providers:
            _render_provider(
                integration,
                connections_by_slug.get(integration.slug, []),
                credentials_by_slug.get(integration.slug),
            )

    # Signal fallback: `_dialog_remove_account` opens here to avoid nested dialogs.
    pending = st.session_state.pop(_PENDING_REMOVE, None)
    if pending:
        provider_slug, connection_id = pending
        _dialog_remove_account(connection_store, provider_slug, connection_id, username)


def _render_provider(integration, connections, credential) -> None:
    """One provider block: header + account rows + CTA."""
    with st.container(key=f"ac_prov_{integration.slug}"):
        _render_provider_header(integration, connections)

        if not integration.available:
            # A provider still being rolled out — no accounts, no CTA.
            reason = (integration.pending_reason or "").strip() or i18n.t(
                "accounts.provider_pending_default"
            )
            st.markdown(
                palette.band_note_html(html.escape(reason)),
                unsafe_allow_html=True,
            )
            st.write("")
            return

        if credential is None:
            # The sentence carries its own <strong>, so it is composed inside
            # the catalog and only dropped into the paragraph here.
            st.markdown(
                f"<p style='margin:12px 8px 0 8px;font-size:13px;color:{palette.FG_SUBTLE};"
                f"line-height:1.5;'>"
                + i18n.t("accounts.provider_missing_credential",
                         provider=html.escape(integration.name))
                + "</p>",
                unsafe_allow_html=True,
            )
            st.write("")
            return

        visible = [c for c in connections
                   if (c.status or "").strip().lower() != "revocado"]
        if visible:
            for connection in visible:
                _render_account_row(integration.slug, connection)
        else:
            st.markdown(
                palette.band_note_html(i18n.t("accounts.provider_no_accounts")),
                unsafe_allow_html=True,
            )

    # CTA outside the provider container so the CSS grid rules don't apply.
    _render_connect_cta(integration.slug)
    st.write("")


def _render_provider_header(integration, connections) -> None:
    """Header of a provider band: name + tag + right-side count/state."""
    live_count = sum(
        1 for c in connections
        if (c.status or "").strip().lower() != "revocado"
    )
    if not integration.available:
        right = (
            f"<span style='font-size:12px;font-weight:600;letter-spacing:0.06em;"
            f"text-transform:uppercase;color:{palette.ACCENT_HOVER};'>"
            f"{i18n.t('accounts.provider_coming_soon')}</span>"
        )
    else:
        right = (
            f"<span style='font-size:12px;color:{palette.FG_SUBTLE};font-weight:500;'>"
            f"{i18n.tn('accounts.provider_count', live_count)}</span>"
        )

    st.markdown(
        palette.band_header_html(
            title=html.escape(integration.name),
            tag=html.escape(
                f"{integration.auth_kind.upper()} · {integration.category.upper()}"
            ),
            right=right,
            dimmed=not integration.available,
        ),
        unsafe_allow_html=True,
    )


def _render_account_row(provider_slug: str, connection) -> None:
    """One row: dot · account+chip · meta · status · Remove.

    Every cell uses inline HTML so the row height and vertical alignment
    stay consistent — a Streamlit ``st.markdown`` paragraph adds its own
    line-height that would break the 48px strip.
    """
    with st.container(key=f"ac_row_{provider_slug}_{connection.id}"):
        cells = st.columns(_ROW_WEIGHTS, gap="small", vertical_alignment="center")
        status = (connection.status or "").strip().lower()

        # Dot glyph — carries the same green as the status label so it reads
        # at a glance without needing to look right.
        dot_color = {"activo": palette.OK, "needs_reauth": palette.WARN}.get(status, palette.IDLE)
        cells[0].markdown(
            f"<div style='width:6px;height:6px;border-radius:50%;"
            f"background:{dot_color};margin-left:16px;'></div>",
            unsafe_allow_html=True,
        )

        client = html.escape(connection.client or "—")
        marketplace = html.escape((connection.marketplace or "").strip())
        cells[1].markdown(
            f"<div style='display:flex;align-items:center;gap:10px;'>"
            f"<span style='font-size:14.5px;font-weight:600;color:{palette.FG};"
            f"letter-spacing:-0.005em;'>{client}</span>"
            f"{palette.marketplace_chip_html(marketplace)}</div>",
            unsafe_allow_html=True,
        )

        connected_by = html.escape((connection.connected_by or "").strip())
        meta_html = (
            i18n.t(
                "accounts.row_connected_by",
                user=f"<span style='color:{palette.FG};'>{connected_by}</span>",
            )
            if connected_by else "—"
        )
        cells[2].markdown(
            f"<span style='font-size:12.5px;color:{palette.FG_MUTED};'>{meta_html}</span>",
            unsafe_allow_html=True,
        )

        cells[3].markdown(
            _status_html().get(status,
                               palette.status_pill_html("idle",
                                                        html.escape(status or "—"))),
            unsafe_allow_html=True,
        )

        # A row that says "needs reauth" has to offer the fix, or the reader
        # is told there is a problem and left without the button that solves
        # it. Same OAuth dialog: the exchange upserts on the external account
        # id, so reauthorizing updates this row instead of creating a second.
        if status == "needs_reauth":
            with cells[4]:
                if st.button(
                    i18n.t("accounts.btn_reauth"),
                    key=f"accounts_reauth_{provider_slug}_{connection.id}",
                    icon=":material/refresh:",
                    type="tertiary",
                    use_container_width=False,
                ):
                    st.session_state[_CONNECT_SLUG_KEY] = provider_slug
                    _dialog_connect_account(provider_slug)

        # Action — tertiary so it reads as a link, not a button.
        with cells[5]:
            if st.button(
                i18n.t("accounts.btn_remove"),
                key=f"accounts_del_{provider_slug}_{connection.id}",
                icon=":material/link_off:",
                type="tertiary",
                use_container_width=False,
            ):
                st.session_state[_PENDING_REMOVE] = (provider_slug, connection.id)
                st.rerun()


def _render_connect_cta(provider_slug: str) -> None:
    """Outline CTA sitting below the account rows of a provider."""
    with st.container(key=f"ac_cta_{provider_slug}"):
        if st.button(
            i18n.t("accounts.btn_connect_new"),
            icon=":material/add:",
            key=f"accounts_btn_connect_{provider_slug}",
            use_container_width=False,
        ):
            st.session_state[_CONNECT_SLUG_KEY] = provider_slug
            _dialog_connect_account(provider_slug)


def _dialog_connect_account(provider_slug: str) -> None:
    """Open the connect dialog with its title in the current language.

    `st.dialog` captures its title when the decorator runs, so decorating at
    import time would pin the title to whichever language was active on the
    first import. Applying the decorator here re-reads it on every open.
    Streamlit derives the dialog's fragment id from the wrapped function's
    name, which does not change, so the dialog keeps its identity across runs.
    """
    open_dialog = st.dialog(i18n.t("accounts.dialog_connect_title"))(
        _connect_account_body
    )
    open_dialog(provider_slug)


def _connect_account_body(provider_slug: str) -> None:
    """Field-less OAuth flow, single-step. The consent URL is prepared as the
    dialog opens — no intermediate "Preparar autorización" click that would
    force a rerun and close the dialog. The account name and country come
    from the worker via /users/me after the token exchange, not from the
    operator.
    """
    integration = catalog.by_slug(provider_slug)
    if integration is None:
        st.error(i18n.t("accounts.error_unknown_provider"))
        return

    stores = open_stores()
    if stores is None:
        st.error(i18n.t("accounts.error_db_unavailable_short"))
        return
    credential_store, connection_store, settings_store = stores

    public = credential_store.public_fields(provider_slug)
    client_id = str(public.get("client_id") or "").strip()
    if not client_id:
        st.error(i18n.t("accounts.error_missing_credential",
                        provider=integration.name))
        return
    redirect_uri = os.environ.get(_REDIRECT_URI_ENV, "").strip()
    if not redirect_uri:
        st.error(i18n.t("accounts.error_missing_redirect_uri"))
        return
    public_key = settings_store.get(SEALING_KEY_SETTING) or crypto.public_key_from_env()
    if not public_key:
        st.error(i18n.t("accounts.error_missing_public_key"))
        return

    # Prepare the grant on the FIRST render of this dialog instance. Keyed by
    # provider slug so opening for a different provider doesn't reuse a stale
    # URL. If the user closes and reopens for the same provider, the previous
    # pending grant expires on its own via `_expire_pending_grants` (30 min TTL).
    slug_key = f"{_CONNECT_URL_KEY}_slug"
    if (st.session_state.get(slug_key) != provider_slug
            or not st.session_state.get(_CONNECT_URL_KEY)):
        try:
            grant = oauth.start_grant()
            connection_store.open_grant(
                slug=provider_slug,
                # Placeholders: the worker replaces both with real values from
                # /users/me during the token exchange.
                client=f"_pending_{grant.state[:12]}",
                marketplace="",
                state=grant.state,
                verifier_sealed=crypto.seal(grant.verifier, public_key),
                user=st.session_state.get("username", "") or "",
            )
            url = oauth.consent_url(
                authorize_url=integration.authorize_url,
                client_id=client_id,
                redirect_uri=redirect_uri,
                grant=grant,
                scopes=integration.scopes,
            )
        except StoreError as exc:
            st.error(str(exc))
            return
        st.session_state[_CONNECT_URL_KEY] = url
        st.session_state[slug_key] = provider_slug

    consent = st.session_state[_CONNECT_URL_KEY]
    st.markdown(i18n.t("accounts.connect_dialog_body", provider=integration.name))
    st.link_button(
        i18n.t("accounts.btn_open_consent", provider=integration.name),
        consent, type="primary", use_container_width=True,
    )
    if st.button(i18n.t("accounts.btn_close"), key="accounts_connect_close",
                 use_container_width=True):
        st.session_state.pop(_CONNECT_URL_KEY, None)
        st.session_state.pop(slug_key, None)
        st.session_state.pop(_CONNECT_SLUG_KEY, None)
        st.rerun()


def _dialog_remove_account(connection_store, provider_slug: str, connection_id,
                           username: str) -> None:
    """Open the remove dialog with its title in the current language.

    Same reason as `_dialog_connect_account`: the decorator would otherwise
    freeze the title at import time.
    """
    open_dialog = st.dialog(i18n.t("accounts.dialog_remove_title"))(
        _remove_account_body
    )
    open_dialog(connection_store, provider_slug, connection_id, username)


def _remove_account_body(connection_store, provider_slug: str, connection_id,
                         username: str) -> None:
    """Soft-revoke the account. The row itself stays for auditing."""
    integration = catalog.by_slug(provider_slug)
    provider_name = integration.name if integration else provider_slug
    st.markdown(i18n.t("accounts.remove_dialog_body", provider=provider_name))
    col_cancel, col_remove = st.columns(2)
    if col_cancel.button(i18n.t("accounts.btn_cancel"), key="accounts_remove_cancel",
                         use_container_width=True):
        st.rerun()
    if col_remove.button(i18n.t("accounts.btn_disconnect"), key="accounts_remove_ok",
                         type="primary", use_container_width=True):
        try:
            connection_store.set_status(
                connection_id=connection_id,
                status="revocado",
                user=username or "",
                slug=provider_slug,
            )
        except StoreError as exc:
            st.error(str(exc))
            return
        st.success(i18n.t("accounts.toast_disconnected"))
        st.rerun()
