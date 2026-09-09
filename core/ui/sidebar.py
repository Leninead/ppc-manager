"""Dark sidebar CSS block for the Agency OS shell.

Held in its own module (instead of a huge string in ``app.py``) so brand
colors come from ``core.ui.palette`` and a palette bump lands in one place.
The comments inside the CSS are the same the original author left for
future maintainers; only the color literals were swapped for template
placeholders that resolve from the palette.
"""
from __future__ import annotations

from string import Template

from core.ui import palette

_TEMPLATE = Template(r"""<style>
/* ── Tipografía ───────────────────────────────────────────────────
   `font = "sans serif"` en config.toml no llega al DOM: en 1.43.2 nada declara
   font-family sobre html/body, así que el navegador cae a su default serif y
   TODA la app se dibuja en Times New Roman. Verificado en runtime: ni una regla
   de las hojas cargadas toca font-family del body.
   Source Sans Pro ya viene servida por Streamlit (@font-face propio), así que
   esto no agrega ni una request ni depende de una CDN.                       */
html, body,
[data-testid="stAppViewContainer"], [data-testid="stSidebar"],
button, input, textarea, select, optgroup {
    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI",
                 Roboto, "Helvetica Neue", Arial, sans-serif !important;
}
/* El monoespaciado se declara aparte o la regla de arriba se lo come. */
code, pre, kbd, samp {
    font-family: "Source Code Pro", ui-monospace, SFMono-Regular, Menlo,
                 Consolas, monospace !important;
}

/* ── Sidebar ──────────────────────────────────────────────────────
   El riel medía 180px, lo que dejaba 78px de caja de texto y partía los
   nombres a mitad de palabra ("Performanc" / "e"), con filas de hasta 112px.
   Streamlit no pinta el texto en el <button> ni en el <summary> sino en un <p>
   interno, así que las reglas hay que ponerlas ahí o no se aplican.          */
[data-testid="stSidebar"] {
    background-color: $SIDEBAR_BG !important;
    min-width: 248px !important;
    max-width: 248px !important;
    /* El manejador de redimensión asoma 6px y genera scroll horizontal dentro
       del riel; con el ancho fijo no redimensiona nada. */
    overflow-x: hidden !important;
}

[data-testid="stSidebar"] * { color: $SIDEBAR_INK !important; }

[data-testid="stSidebar"] button {
    background-color: transparent !important;
    border: none !important;
    border-left: 3px solid transparent !important;
    border-radius: 0 6px 6px 0 !important;
    padding: 0.35rem 0.75rem !important;
    text-align: left !important;
    width: 100% !important;
    min-height: 44px !important;
    transition: background-color 0.15s ease !important;
    /* El botón por dentro es flex con `justify-content: center` de fábrica, así
       que el bloque ícono+texto se corría con el largo del texto: `Listing
       Monitor` empujaba el ícono a X=28 y `Weekly Client Report` a X=12.
       `text-align: left` no lo pisa porque no aplica a flex children.        */
    justify-content: flex-start !important;
    gap: 10px !important;
}

/* El <p> es el que pinta: acá van tamaño y corte de palabra. */
[data-testid="stSidebar"] button p {
    font-size: 0.82rem !important;
    line-height: 1.35 !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
    hyphens: none !important;
}

[data-testid="stSidebar"] button:hover { background-color: $SIDEBAR_ROW_HOVER !important; }
[data-testid="stSidebar"] button:hover p { color: $SIDEBAR_INK_ACTIVE !important; }
[data-testid="stSidebar"] button:hover [data-testid="stIconMaterial"] { color: $SIDEBAR_INK_ACTIVE !important; }

/* Dónde estás: 33 destinos y ninguno lo indicaba. */
[data-testid="stSidebar"] button[kind="primary"] {
    background-color: $SIDEBAR_ROW_HOVER !important;
    border-left-color: $ACCENT_SOFT !important;
}
[data-testid="stSidebar"] button[kind="primary"] p {
    color: $SIDEBAR_INK_ACTIVE !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] button[kind="primary"] [data-testid="stIconMaterial"] {
    color: $ACCENT_SOFT !important;
}

/* Íconos Material que van en cada fila. Uno por destino, en vez del emoji de la
   clave de ruteo: `📊` aparecía en cuatro destinos, `📈` en tres, `🛡️` en tres.
   El ícono es el único que hace diferencia visual entre esas filas.
   El comodín `*` del riel pinta todo $SIDEBAR_INK, así que estas reglas lo ganan. */
[data-testid="stSidebar"] button [data-testid="stIconMaterial"] {
    color: #B0B0B0 !important;
    font-size: 20px !important;
    /* Todos los íconos ocupan el mismo cajón: el glyph natural de Material va
       de 12px a 26px según cuál sea, así que sin este ancho fijo cada texto
       arrancaba a una X distinta aunque el font-size fuese igual. */
    width: 22px !important;
    text-align: center !important;
    flex-shrink: 0 !important;
}
[data-testid="stSidebar"] details summary [data-testid="stIconMaterial"] {
    color: $ACCENT_SOFT !important;
    font-size: 18px !important;
    margin-right: 6px !important;
}

/* $ACCENT sobre $SIDEBAR_BG da 4.28:1 y no llega a AA; $ACCENT_SOFT da 6.10:1. */
[data-testid="stSidebar"] details summary p {
    color: $ACCENT_SOFT !important;
    font-size: 0.72rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.07em !important;
    text-transform: uppercase !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
}

/* El conteo de la sección va en la etiqueta como :gray[...], que Streamlit
   emite como <span>. La regla de arriba pinta el <p>, no el <span>, y el
   comodín del riel lo dejaba igual que el resto del texto. */
[data-testid="stSidebar"] details summary p span {
    color: #9A9A9A !important;
    font-weight: 600 !important;
    letter-spacing: 0 !important;
}

/* Mismo mecanismo para el punto de aviso de Integraciones: :orange[●]. */
[data-testid="stSidebar"] button p span { color: #FFB74D !important; }

[data-testid="stSidebar"] details {
    background-color: transparent !important;
    border: none !important;
    margin-bottom: 0 !important;
}
[data-testid="stSidebar"] details summary {
    padding: 0.5rem !important;
    min-height: 44px !important;
    display: flex !important;
    align-items: center !important;
}

/* El anillo por defecto resuelve a 1.92:1 sobre el riel; el mínimo es 3:1. */
[data-testid="stSidebar"] button:focus-visible,
[data-testid="stSidebar"] summary:focus-visible {
    outline: 2px solid $ACCENT_SOFT !important;
    outline-offset: -2px !important;
    box-shadow: none !important;
}

/* El buscador. BaseWeb pone el borde y el fondo en el envoltorio, no en el
   <input>, que es transparente: pintar sólo el input deja una caja blanca. */
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] {
    background-color: $SIDEBAR_INPUT_BG !important;
    /* #383838 daba 1,29:1 contra el riel: el borde de un control tiene que
       llegar a 3:1 o la caja no se distingue del fondo. Este da 3,42:1. */
    border-color: $SIDEBAR_INPUT_BORDER !important;
    border-radius: 7px !important;
}
[data-testid="stSidebar"] [data-baseweb="input"]:focus-within {
    border-color: $ACCENT_SOFT !important;
}
[data-testid="stSidebar"] .stTextInput input {
    background-color: transparent !important;
    color: $SIDEBAR_INK_ACTIVE !important;
    font-size: 0.82rem !important;
    min-height: 44px !important;
}
/* #6B7280 sobre $SIDEBAR_INPUT_BG da 3,3:1 y el placeholder es texto que hay que leer. */
[data-testid="stSidebar"] .stTextInput input::placeholder {
    color: #9A9A9A !important;
    opacity: 1 !important;
}
/* "Press Enter to apply" es de Streamlit y no se puede traducir en 1.43.2: un
   cartel en inglés dentro de un riel en español. El dato va en el placeholder. */
[data-testid="stSidebar"] [data-testid="InputInstructions"] { display: none !important; }

[data-testid="stSidebar"] .sb-no-results {
    color: #AAAAAA !important;
    font-size: 0.78rem !important;
    padding: 0.5rem !important;
}

[data-testid="stSidebar"] .stMarkdown p {
    color: #999999 !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    margin: 0.75rem 0 0.25rem 0.5rem !important;
}

/* The footer declares its colors inline. The rule above overrode them with
   the accent, which pinned the health chip to its alarm state even when the
   mapping was fine.                                                        */
[data-testid="stSidebar"] .sb-marca { color: $ACCENT_SOFT !important; font-weight: 800 !important; }
[data-testid="stSidebar"] .sb-pie { color: #AAAAAA !important; font-size: 0.75rem !important; }
[data-testid="stSidebar"] .sb-pie-tenue { color: #999999 !important; }
[data-testid="stSidebar"] .sb-salud-ok { color: #5FD37A !important; }
[data-testid="stSidebar"] .sb-salud-alerta { color: #FFB74D !important; }

[data-testid="stSidebar"] hr {
    border-color: #333333 !important;
    margin: 0.5rem 0 !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: $ACCENT_SOFT !important;
    font-size: 0.85rem !important;
}

/* Se puede volver a abrir: a 420px el riel se auto-colapsa y ocultar el
   control dejaba al usuario sin forma de recuperarlo.                        */
[data-testid="stSidebarCollapseButton"] { display: block !important; }

[data-testid="stAppViewContainer"] > .main { padding-left: 1rem !important; }

/* 41 elementos con transición y ninguna regla de movimiento reducido. */
@media (prefers-reduced-motion: reduce) {
    [data-testid="stSidebar"], [data-testid="stSidebar"] * {
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }
}
""")

SIDEBAR_CSS = _TEMPLATE.substitute(
    SIDEBAR_BG=palette.SIDEBAR_BG,
    SIDEBAR_ROW_HOVER=palette.SIDEBAR_ROW_HOVER,
    SIDEBAR_INPUT_BG=palette.SIDEBAR_INPUT_BG,
    SIDEBAR_INPUT_BORDER=palette.SIDEBAR_INPUT_BORDER,
    SIDEBAR_INK=palette.SIDEBAR_INK,
    SIDEBAR_INK_ACTIVE=palette.SIDEBAR_INK_ACTIVE,
    ACCENT_SOFT=palette.ACCENT_SOFT,
    ACCENT=palette.ACCENT,
)
