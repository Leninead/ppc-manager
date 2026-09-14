"""Static catalog of the integrations the Agency OS can talk to.

Adding an integration is an entry here, not new code: the credential dialog
renders from `fields` and the grid orders by `order`.

Storage class is chosen per integration by *who consumes the credential*:

  APP_READABLE  the Streamlit process itself reads it (core/datadive.py:441).
                Sealing it would make it unusable, so the app can read it back.
  SEALED        only the worker can open it. Correct for an OAuth client secret,
                which governs every client account at once.
"""
from __future__ import annotations

from dataclasses import dataclass

APP_READABLE = "app_readable"
SEALED = "sealed"

API_KEY = "api_key"
OAUTH2 = "oauth2"

AVAILABLE = "disponible"
COMING_SOON = "proximamente"

CATEGORIES = ("marketplaces", "ads", "research", "ia")

CATEGORY_TITLE = {
    "marketplaces": "Marketplaces",
    "ads": "Publicidad",
    "research": "Research",
    "ia": "IA",
}


@dataclass(frozen=True)
class CredentialField:
    key: str
    label: str
    secret: bool
    help_text: str = ""
    # Pre-filled in the form. For a field whose right value depends on which
    # flavour of an account the agency runs — Mercado Libre's authorize host is
    # the case — a default plus help text lets the admin decide once, instead of
    # the catalog deciding for every agency at once.
    default: str = ""


@dataclass(frozen=True)
class Integration:
    slug: str
    name: str
    provider: str
    category: str
    auth_kind: str
    storage: str
    state: str
    order: int
    fields: tuple[CredentialField, ...]
    consumer: str = ""
    pending_reason: str = ""
    # Works, but its credential lives outside the portal's reach. Not the same
    # as "does not exist yet", and painting them alike makes the screen lie.
    works_outside: bool = False
    # Where the credential lived BEFORE the portal. Declared so we can tell
    # the truth on screen: an integration configured on the server is not the
    # same as one that is unconfigured, and offering to import it is the
    # point of the portal.
    env_var: str = ""
    secrets_section: str = ""
    secrets_key: str = ""
    scopes: tuple[str, ...] = ()
    authorize_url: str = ""
    token_url: str = ""
    # Whether a refresh returns a replacement token that must be persisted
    # (Mercado Libre) or echoes the same one (Login with Amazon).
    refresh_rotates: bool = True
    # Days a consent stays valid from the date it was given; 0 = until revoked.
    # Login with Amazon: 365, fixed at consent, not extended by refreshing.
    refresh_token_lifetime_days: int = 0
    # One authorization reaches many client accounts (an agency user invited
    # into each client's Amazon Ads), listed in `integration_accounts`. For
    # Mercado Libre the connection IS the client account.
    discovers_accounts: bool = False

    @property
    def available(self) -> bool:
        return self.state == AVAILABLE

    @property
    def is_sealed(self) -> bool:
        return self.storage == SEALED

    @property
    def connects_accounts(self) -> bool:
        return self.auth_kind == OAUTH2

    @property
    def secret_field(self) -> CredentialField | None:
        for field in self.fields:
            if field.secret:
                return field
        return None

    @property
    def public_field_defs(self) -> tuple[CredentialField, ...]:
        return tuple(field for field in self.fields if not field.secret)


_CATALOG: tuple[Integration, ...] = (
    Integration(
        slug="mercado_libre",
        name="Mercado Libre",
        provider="Mercado Libre",
        category="marketplaces",
        auth_kind=OAUTH2,
        storage=SEALED,
        state=AVAILABLE,
        order=10,
        consumer="worker de ingesta",
        scopes=("offline_access", "read", "write"),
        authorize_url="https://auth.mercadolibre.com.ar/authorization",
        token_url="https://api.mercadolibre.com/oauth/token",
        fields=(
            CredentialField(
                key="client_id",
                label="App ID",
                secret=False,
                help_text="No es secreto: queda visible en el detalle.",
            ),
            CredentialField(
                key="client_secret",
                label="Client Secret",
                secret=True,
                help_text="Se guarda sellado. No se vuelve a mostrar.",
            ),
            # Mercado Libre has no single authorize host: it is per site, and
            # Global Selling (CBT) is not a site at all — it authorizes on its
            # own domain. The country cannot be discovered before consent
            # either (`/users/me` needs the token the consent produces, and
            # `/applications/$APP_ID` needs a token too), so it cannot be
            # resolved at connect time. It belongs to the app the agency
            # registered, which is exactly what the system credential is.
            CredentialField(
                key="authorize_url",
                label="URL de autorización",
                secret=False,
                help_text=(
                    "Depende de dónde registraste la app. CBT / Global Selling: "
                    "https://global-selling.mercadolibre.com/authorization · "
                    "Vendedor local: https://auth.mercadolibre.com.XX/authorization "
                    "con el dominio del país (.com.ar, .com.mx, .com.br…). "
                    "El token se canjea siempre contra api.mercadolibre.com."
                ),
                default="https://auth.mercadolibre.com.ar/authorization",
            ),
        ),
    ),
    Integration(
        slug="datadive",
        name="DataDive",
        provider="DataDive",
        category="research",
        auth_kind=API_KEY,
        storage=APP_READABLE,
        state=AVAILABLE,
        order=20,
        consumer="core/datadive.py",
        env_var="DATADIVE_API_KEY",
        secrets_section="datadive",
        secrets_key="api_key",
        fields=(
            CredentialField(
                key="api_key",
                label="API key",
                secret=True,
                help_text="Se genera en DataDive, en la sección de API.",
            ),
        ),
    ),
    Integration(
        slug="amazon_ads",
        name="Amazon Ads",
        provider="Amazon",
        category="ads",
        auth_kind=OAUTH2,
        storage=SEALED,
        state=AVAILABLE,
        order=30,
        consumer="worker de integraciones",
        # `profile:user_id` is the narrowest Login with Amazon identity scope:
        # only the user id, which is what keys the authorization row.
        scopes=("advertising::campaign_management", "profile:user_id"),
        authorize_url="https://www.amazon.com/ap/oa",
        # Global: a code from any regional consent host is exchanged here.
        token_url="https://api.amazon.com/auth/o2/token",
        refresh_rotates=False,
        refresh_token_lifetime_days=365,
        discovers_accounts=True,
        fields=(
            CredentialField(
                key="client_id",
                label="LwA Client ID",
                secret=False,
                help_text=(
                    "Del Security Profile en developer.amazon.com (Login with Amazon). "
                    "En Web Settings, Allowed Return URLs tiene que contener exactamente "
                    "la INTEGRATIONS_REDIRECT_URI del servidor. No es secreto."
                ),
            ),
            CredentialField(
                key="client_secret",
                label="LwA Client Secret",
                secret=True,
                help_text="Se guarda sellado. No se vuelve a mostrar.",
            ),
            # The consent host only picks which Amazon login page the employee
            # sees: a code from any of the three works for every region, and
            # the client accounts are discovered on all regions regardless.
            CredentialField(
                key="authorize_url",
                label="URL de autorización",
                secret=False,
                help_text=(
                    "No hace falta cambiarla por tener clientes en otros continentes. "
                    "NA: https://www.amazon.com/ap/oa · EU: https://eu.account.amazon.com/ap/oa · "
                    "FE: https://apac.account.amazon.com/ap/oa. El token se canjea siempre "
                    "contra api.amazon.com."
                ),
                default="https://www.amazon.com/ap/oa",
            ),
        ),
    ),
    Integration(
        slug="walmart",
        name="Walmart Marketplace",
        provider="Walmart",
        category="marketplaces",
        auth_kind=OAUTH2,
        storage=SEALED,
        state=COMING_SOON,
        order=70,
        pending_reason="Sin cuenta de vendedor todavía.",
        fields=(
            CredentialField(key="client_id", label="Client ID", secret=False),
            CredentialField(key="client_secret", label="Client Secret", secret=True),
        ),
    ),
)

_BY_SLUG = {integration.slug: integration for integration in _CATALOG}


def all_integrations() -> tuple[Integration, ...]:
    return tuple(sorted(_CATALOG, key=lambda i: i.order))


def by_slug(slug: str) -> Integration | None:
    return _BY_SLUG.get(slug)


def by_category() -> list[tuple[str, list[Integration]]]:
    """Groups for the grid, skipping categories with nothing in them."""
    grouped: list[tuple[str, list[Integration]]] = []
    for category in CATEGORIES:
        integrations = [i for i in all_integrations() if i.category == category]
        if integrations:
            grouped.append((category, integrations))
    return grouped
