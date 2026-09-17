"""What a chat component is made of, and the HTML helpers every component shares.

Everything a component draws lands inside the chat thread, which is ONE st.markdown
call: no script runs there, no Streamlit element can be nested there, and a blank
line ends the HTML block. So a component is static HTML or inline SVG, styled inline
(Streamlit's markdown CSS outranks a class), escaped, and always on one line.
"""
from __future__ import annotations

import html
import math
from collections.abc import Callable
from dataclasses import dataclass

ACCENT = "#E84000"
INK = "#1F1F1F"
MUTED = "#8A867C"
LINE = "#EFECE6"
SURFACE = "#FAF8F4"
TONES = ("neutral", "good", "bad")
TONE_COLOR = {"good": "#1B6B2F", "bad": "#B71C1C"}
TONE_SCHEMA = {"enum": list(TONES)}


@dataclass(frozen=True)
class Component:
    """One thing the panel can draw.

    `purpose`, `looks` and `limits` are what the model reads to choose it. `fields`
    is the JSON schema of the block's properties, every one of them required: an
    optional value is an empty string, so a block never arrives half-described.
    `clean` returns the block ready to draw, a text block when its data cannot be
    drawn but can still be read, or None when nothing of it is left. `strings`
    returns the block with a function run over every string the AM reads."""

    kind: str
    fields: dict
    purpose: str
    looks: str
    limits: str
    prose: bool
    clean: Callable[[dict], dict | None]
    render: Callable[[dict], str]
    plain: Callable[[dict], str]
    strings: Callable[[dict, Callable[[str], str]], dict]
    example: dict

    def schema(self) -> dict:
        return {"type": "object", "additionalProperties": False,
                "required": ["kind", *self.fields],
                "properties": {"kind": {"const": self.kind}, **self.fields}}


def unix_newlines(text: object) -> str:
    # Markdown also ends a line at a bare CR, so a CR pair would close the thread's HTML block.
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def esc(text: object) -> str:
    """Escaped for HTML, with `$` spelled out: st.markdown reads a bare pair as LaTeX."""
    return html.escape(unix_newlines(text)).replace("$", "&#36;")


def one_line(text: object) -> str:
    return esc(text).replace("\n", " ")


def md_bold(safe: str) -> str:
    """Re-apply ONLY the model's **bold** after escaping; leaves the rest inert."""
    parts = safe.split("**")
    if len(parts) < 3:
        return safe
    if len(parts) % 2 == 0:  # unmatched trailing marker stays literal
        parts[-2] = parts[-2] + "**" + parts[-1]
        parts = parts[:-1]
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def prose_html(text: str) -> str:
    """Paragraphs, **bold** and "- " bullets: the only formatting the chat rules allow."""
    paras = [p.strip() for p in unix_newlines(text).split("\n\n") if p.strip()]
    blocks = []
    for p in paras:
        rich = md_bold(esc(p))  # bold before line split so it never breaks
        lines = []
        for ln in rich.split("\n"):
            if ln.strip().startswith("- "):
                lines.append('<div style="display:flex;gap:7px;margin:3px 0">'
                             f'<span>•</span><span>{ln.strip()[2:]}</span></div>')
            elif ln.strip():
                lines.append(f'<div style="margin:2px 0">{ln}</div>')
        blocks.append(f'<div style="margin:0 0 8px 0">{"".join(lines)}</div>')
    return "".join(blocks)


def text_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def tone_of(value: object) -> str:
    return value if value in TONES else "neutral"


def number(value: object) -> float | None:
    """A finite number, or None. A bool is not a number here, whatever Python says."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        as_float = float(value)
    except OverflowError:
        return None
    return as_float if math.isfinite(as_float) else None


def list_of(value: object) -> list:
    return value if isinstance(value, list) else []


def items_of(block: dict) -> list[dict]:
    return [item for item in list_of(block.get("items")) if isinstance(item, dict)]
