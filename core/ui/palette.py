"""Single source of truth for the Agency OS visual language.

Every page that ships new UI reads its colors and CSS partials from here so a
palette change lands in one place and propagates everywhere it is used.

Scope today: the two new pages of the integrations feature (accounts.py,
integrations.py) plus the sidebar rules in app.py. Pre-existing pages keep
their own styles until they are migrated in their own iteration.
"""
from __future__ import annotations

# ── Brand ──────────────────────────────────────────────────────────────────
ACCENT = "#E84000"          # Capybaras orange, primary CTA and attention
ACCENT_HOVER = "#B23300"    # Darker for links + hover states
ACCENT_SOFT = "#FF6B00"     # Sidebar active accent

# ── Neutrals ───────────────────────────────────────────────────────────────
FG = "#1F1F1F"
FG_MUTED = "#6E6E73"
FG_SUBTLE = "#8E8E93"
BG = "#FAFAFA"
CARD = "#FFFFFF"
LINE = "#E5E5E5"
LINE_SOFT = "#F0F0F0"
ROW_HOVER = "#F5F5F5"

# ── Sidebar (dark) ─────────────────────────────────────────────────────────
SIDEBAR_BG = "#1A1A1A"
SIDEBAR_INK = "#CCCCCC"
SIDEBAR_INK_ACTIVE = "#FFFFFF"
SIDEBAR_ROW_HOVER = "#2A2A2A"
SIDEBAR_INPUT_BG = "#262626"
SIDEBAR_INPUT_BORDER = "#6E6E6E"

# ── Status ─────────────────────────────────────────────────────────────────
OK = "#22C55E"
OK_INK = "#15803D"
OK_GLOW = "#E7F8EE"
WARN = "#F59E0B"
WARN_INK = "#B45309"
WARN_GLOW = "#FEF3C7"
IDLE = "#A3A3A3"
ATTENTION_GLOW = "#FFF8F0"   # Neutral warm off-white for attention row backgrounds

# ── Chip / pill ────────────────────────────────────────────────────────────
CHIP_MARKETPLACE_BG = "#EEF2FF"
CHIP_MARKETPLACE_FG = "#3730A3"

# ── Typography ─────────────────────────────────────────────────────────────
CONTAINER_MAX = "1180px"
ROW_MIN_HEIGHT = "52px"
MONO_STACK = 'ui-monospace,"SF Mono",Menlo,Consolas,monospace'


# ── CSS partials ───────────────────────────────────────────────────────────
def list_shell(key: str) -> str:
    """Wrapper for a full-page tabular list (integrations, accounts, ...)."""
    return f"""
.st-key-{key} {{
    max-width: {CONTAINER_MAX};
    font-variant-numeric: tabular-nums;
}}
.st-key-{key} [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
.st-key-{key} [data-testid="stMarkdownContainer"] p {{ margin: 0; line-height: 1.35; }}
"""


def provider_band(prefix: str) -> str:
    """Spacing between provider bands.

    The header row itself is laid out inline by the markdown the page emits
    (`band_header_html`); styling Streamlit's own wrapper here would make
    that div a flex child and collapse it to its content width, pushing the
    right-hand count back against the tag instead of to the edge.
    """
    return f"""
[class*="st-key-{prefix}"] {{ margin-top: 34px; }}
[class*="st-key-{prefix}"]:first-of-type {{ margin-top: 0; }}
[class*="st-key-{prefix}"] [data-testid="stMarkdownContainer"] {{ width: 100%; }}
"""


def band_header_html(*, title: str, tag: str, right: str,
                     dimmed: bool = False) -> str:
    """Header row of a band: title + kind tag on the left, status on the right.

    Emitted as one inline-styled div so the flex context is owned here and
    not by Streamlit's wrapper markup.
    """
    title_color = FG_MUTED if dimmed else FG
    return (
        f"<div style='display:flex;width:100%;align-items:center;"
        f"justify-content:space-between;min-height:36px;padding-bottom:10px;"
        f"border-bottom:1px solid {LINE};margin-bottom:6px;gap:12px;'>"
        f"<span style='display:flex;align-items:center;gap:10px;min-width:0;'>"
        f"<span style='font-size:15px;font-weight:600;letter-spacing:-0.005em;"
        f"color:{title_color};'>{title}</span>"
        f"<span style='font-size:11px;font-weight:600;letter-spacing:0.08em;"
        f"color:{FG_SUBTLE};text-transform:uppercase;white-space:nowrap;'>{tag}</span>"
        f"</span>"
        f"<span style='white-space:nowrap;'>{right}</span>"
        f"</div>"
    )


def band_note_html(text: str) -> str:
    """Explanatory line under a band that has no rows of its own."""
    return (
        f"<p style='margin:12px 8px 4px 8px;font-size:13px;"
        f"color:{FG_SUBTLE};line-height:1.5;'>{text}</p>"
    )


def tabular_row(prefix: str, min_height: str = ROW_MIN_HEIGHT) -> str:
    """Fixed-height row with hover, used for account/credential rows."""
    return f"""
[class*="st-key-{prefix}"] [data-testid="stHorizontalBlock"] {{
    min-height: {min_height};
    border-bottom: 1px solid {LINE_SOFT};
    padding: 6px 8px;
}}
[class*="st-key-{prefix}"]:hover [data-testid="stHorizontalBlock"] {{ background: {ROW_HOVER}; }}
"""


def outline_button(prefix: str) -> str:
    """Discreet outline CTA that sits at the bottom of a provider band."""
    return f"""
[class*="st-key-{prefix}"] {{ margin-top: 14px; margin-bottom: 8px; }}
[class*="st-key-{prefix}"] button {{
    border: 1px solid #D4D4D8 !important;
    background: {CARD} !important;
    color: {FG} !important;
    padding: 6px 14px !important;
    font-weight: 500 !important;
}}
[class*="st-key-{prefix}"] button:hover {{
    border-color: {ACCENT} !important;
    color: {ACCENT_HOVER} !important;
}}
"""


def status_pill_html(kind: str, label: str) -> str:
    """Small colored dot + label used to render row status.

    `kind` is one of `ok`, `warn`, `idle`; anything else falls back to idle.
    """
    color, ink, glow = {
        "ok": (OK, OK_INK, OK_GLOW),
        "warn": (WARN, WARN_INK, WARN_GLOW),
    }.get(kind, (IDLE, FG_MUTED, "transparent"))
    return (
        "<span style='display:inline-flex;align-items:center;gap:6px;'>"
        f"<span style='width:7px;height:7px;border-radius:50%;background:{color};"
        f"box-shadow:0 0 0 2px {glow};'></span>"
        f"<span style='font-size:13px;color:{ink};font-weight:500;'>{label}</span>"
        "</span>"
    )


def marketplace_chip_html(text: str) -> str:
    """Monospaced pill used for MLA/MLM/... marketplace tags."""
    if not text:
        return ""
    return (
        f"<span style='display:inline-flex;align-items:center;height:20px;"
        f"padding:0 10px;border-radius:10px;background:{CHIP_MARKETPLACE_BG};"
        f"color:{CHIP_MARKETPLACE_FG};font-size:11px;font-weight:600;"
        f"letter-spacing:0.02em;font-family:{MONO_STACK};'>{text}</span>"
    )
