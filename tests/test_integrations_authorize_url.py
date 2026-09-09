"""Tests del host de autorización configurable (core/integrations/catalog.py).

Mercado Libre no tiene UN host de autorización: es por sitio, y Global Selling
(CBT) ni siquiera es un sitio — autoriza en su propio dominio. Y el país no se
puede descubrir antes del consentimiento: `/users/me` necesita el token que el
consentimiento produce, y `/applications/$APP_ID` también pide token. Así que el
host no es un dato del vendedor sino de la app que registró la agencia, que es
exactamente lo que guarda la credencial del sistema.

Lo que se fija acá es que el host viaje como dato configurable y que `consent_url`
lo respete sin reescribirlo, para que una cuenta CBT y una local puedan convivir.
"""

from __future__ import annotations

import pytest

from core.integrations import catalog, oauth

CBT = "https://global-selling.mercadolibre.com/authorization"
MLM = "https://auth.mercadolibre.com.mx/authorization"


@pytest.fixture
def meli():
    integration = catalog.by_slug("mercado_libre")
    assert integration is not None
    return integration


def test_la_credencial_pide_el_host_de_autorizacion(meli):
    """Sin este campo el host quedaba clavado y una cuenta CBT no podía conectarse."""
    campo = next((f for f in meli.fields if f.key == "authorize_url"), None)
    assert campo is not None, "falta el campo authorize_url en la credencial"
    assert not campo.secret, "el host no es un secreto: tiene que quedar visible"


def test_el_host_es_publico_y_obligatorio(meli):
    """Público para poder leerlo al armar el link; obligatorio para no armar uno vacío."""
    assert "authorize_url" in [f.key for f in meli.public_field_defs]


def test_trae_un_default_usable(meli):
    """El formulario se pre-llena: el admin corrige, no arranca de cero."""
    campo = next(f for f in meli.fields if f.key == "authorize_url")
    assert campo.default.startswith("https://")
    assert "/authorization" in campo.default


def test_el_token_se_canjea_siempre_contra_el_mismo_host(meli):
    """Solo la autorización es por sitio; el canje es global y NO se toca."""
    assert meli.token_url == "https://api.mercadolibre.com/oauth/token"


@pytest.mark.parametrize("host", [CBT, MLM])
def test_consent_url_respeta_el_host_que_le_pasan(meli, host):
    """El armador no reescribe ni asume dominio: usa el que sale de la credencial."""
    grant = oauth.start_grant()
    url = oauth.consent_url(
        authorize_url=host,
        client_id="APPID",
        redirect_uri="https://app.capybaras.agency/oauth/callback",
        grant=grant,
        scopes=meli.scopes,
    )
    assert url.startswith(host + "?")


def test_cambiar_de_host_no_pierde_pkce_ni_scopes(meli):
    """CBT y local comparten el resto del flujo; solo cambia dónde se consiente."""
    grant = oauth.start_grant()
    urls = [
        oauth.consent_url(authorize_url=h, client_id="APPID",
                          redirect_uri="https://app.capybaras.agency/oauth/callback",
                          grant=grant, scopes=meli.scopes)
        for h in (CBT, MLM)
    ]
    for url in urls:
        assert "code_challenge_method=S256" in url
        assert "offline_access" in url
    # Lo único que difiere es el host.
    assert urls[0].split("?", 1)[1] == urls[1].split("?", 1)[1]
