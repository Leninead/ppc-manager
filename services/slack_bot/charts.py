"""The chat's bars, pie and trend drawn as PNG in memory, with the panel's colors and layout."""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.chat.components.bars import _NEUTRAL_BAR
from core.chat.components.base import INK, LINE, MUTED, TONE_COLOR
from core.chat.components.pie import SLICE_COLORS
from core.chat.components.trend import _NEUTRAL_LINE

KINDS = frozenset({"bars", "pie", "trend"})

# Drawn at twice the panel's 420 px so the image stays sharp on retina screens.
_SCALE = 2
_WIDTH = 420
_PAD = 16
_BACKGROUND = "#FFFFFF"


def draw(block: dict) -> bytes:
    painter = {"bars": _bars, "pie": _pie, "trend": _trend}[block["kind"]]
    image = painter(block)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def font_path(bold: bool = False) -> Path | None:
    """Bitstream Vera from reportlab (xhtml2pdf's dependency): Pillow's own font has no accents or ñ."""
    try:
        import reportlab
    except ImportError:
        return None
    path = Path(reportlab.__file__).parent / "fonts" / ("VeraBd.ttf" if bold else "Vera.ttf")
    return path if path.exists() else None


@lru_cache(maxsize=16)
def _font(size: float, bold: bool = False) -> ImageFont.ImageFont:
    path = font_path(bold)
    pixels = round(size * _SCALE)
    return ImageFont.truetype(str(path), pixels) if path else ImageFont.load_default(size=pixels)


def _canvas(height: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (_WIDTH * _SCALE, round(height * _SCALE)), _BACKGROUND)
    return image, ImageDraw.Draw(image)


def _xy(*values: float) -> list[float]:
    return [value * _SCALE for value in values]


def _fit(text: str, size: float, width: float, bold: bool = False) -> str:
    font = _font(size, bold)
    if font.getlength(text) <= width * _SCALE:
        return text
    while text and font.getlength(text + "…") > width * _SCALE:
        text = text[:-1]
    return text.rstrip() + "…"


def _text(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, size: float, color: str,
          anchor: str = "la", bold: bool = False) -> None:
    draw.text(_xy(x, y), text, font=_font(size, bold), fill=color, anchor=anchor)


def _width(text: str, size: float, bold: bool = False) -> float:
    return _font(size, bold).getlength(text) / _SCALE


def _bars(block: dict) -> Image.Image:
    items = block["items"]
    top = max(item["value"] for item in items)
    title = 22 if block["metric"] else 0
    row = 38
    image, draw = _canvas(_PAD * 2 + title + row * len(items))
    if block["metric"]:
        _text(draw, _PAD, _PAD, _fit(block["metric"], 12.5, _WIDTH - 2 * _PAD, bold=True), 12.5, MUTED, bold=True)
    inner = _WIDTH - 2 * _PAD
    for index, item in enumerate(items):
        y = _PAD + title + index * row
        color = TONE_COLOR.get(item["tone"])
        display_width = _width(item["display"], 14)
        _text(draw, _WIDTH - _PAD, y, item["display"], 14, color or INK, anchor="ra")
        _text(draw, _PAD, y, _fit(item["label"], 14, inner - display_width - 12), 14, INK)
        bar_y = y + 22
        draw.rounded_rectangle(_xy(_PAD, bar_y, _WIDTH - _PAD, bar_y + 6), radius=3 * _SCALE, fill=LINE)
        if top > 0 and item["value"] > 0:
            filled = max(item["value"] / top, 0.015) * inner
            draw.rounded_rectangle(_xy(_PAD, bar_y, _PAD + filled, bar_y + 6), radius=3 * _SCALE,
                                   fill=color or _NEUTRAL_BAR)
    return image


def _pie(block: dict) -> Image.Image:
    items = block["items"]
    total = sum(item["value"] for item in items)
    shares = [item["value"] / total * 100 for item in items]
    title = 24 if block["metric"] else 0
    ring = 104
    row = 24
    legend_height = row * len(items)
    image, draw = _canvas(_PAD * 2 + title + max(ring, legend_height))
    if block["metric"]:
        _text(draw, _PAD, _PAD, _fit(block["metric"], 12.5, _WIDTH - 2 * _PAD, bold=True), 12.5, MUTED, bold=True)
    top = _PAD + title
    box = _xy(_PAD, top, _PAD + ring, top + ring)
    start = -90.0
    for index, share in enumerate(shares):
        end = start + share * 3.6
        draw.pieslice(box, start, end, fill=SLICE_COLORS[index % len(SLICE_COLORS)])
        start = end
    hole = ring * 0.62
    offset = (ring - hole) / 2
    draw.ellipse(_xy(_PAD + offset, top + offset, _PAD + offset + hole, top + offset + hole), fill=_BACKGROUND)

    left = _PAD + ring + 18
    legend_top = top + max((ring - legend_height) / 2, 0)
    for index, (item, share) in enumerate(zip(items, shares, strict=True)):
        y = legend_top + index * row
        draw.rounded_rectangle(_xy(left, y + 3, left + 10, y + 13), radius=2 * _SCALE,
                               fill=SLICE_COLORS[index % len(SLICE_COLORS)])
        percent = f"{share:.1f}%"
        _text(draw, _WIDTH - _PAD, y, percent, 13, MUTED, anchor="ra")
        right = _WIDTH - _PAD - max(_width(percent, 13), 46) - 10
        _text(draw, right, y, item["display"], 14, INK, anchor="ra")
        label_width = right - _width(item["display"], 14) - 10 - (left + 16)
        _text(draw, left + 16, y, _fit(item["label"], 14, label_width), 14, INK)
    return image


def _trend(block: dict) -> Image.Image:
    points = block["points"]
    footer = 20 if block["start"] or block["end"] else 0
    chart_top, chart_height = _PAD + 26, 64
    image, draw = _canvas(chart_top + chart_height + footer + _PAD)
    color = TONE_COLOR.get(block["tone"])
    _text(draw, _WIDTH - _PAD, _PAD, block["display"], 14, color or INK, anchor="ra", bold=True)
    label_width = _WIDTH - 2 * _PAD - _width(block["display"], 14, bold=True) - 12
    _text(draw, _PAD, _PAD, _fit(block["label"], 14, label_width), 14, INK)

    inner = _WIDTH - 2 * _PAD
    low, high = min(points), max(points)
    span = high - low
    step = inner / (len(points) - 1)
    margin = 7

    def y_of(value: float) -> float:
        if span == 0:
            return chart_top + chart_height / 2
        return chart_top + chart_height - margin - (value - low) / span * (chart_height - 2 * margin)

    coordinates = [(_PAD + index * step, y_of(value)) for index, value in enumerate(points)]
    baseline = chart_top + chart_height - 1
    draw.line(_xy(_PAD, baseline, _WIDTH - _PAD, baseline), fill=LINE, width=_SCALE)
    draw.line([coordinate * _SCALE for point in coordinates for coordinate in point],
              fill=color or _NEUTRAL_LINE, width=2 * _SCALE, joint="curve")
    last_x, last_y = coordinates[-1]
    draw.ellipse(_xy(last_x - 3.5, last_y - 3.5, last_x + 3.5, last_y + 3.5), fill=color or _NEUTRAL_LINE)
    if footer:
        y = chart_top + chart_height + 6
        _text(draw, _PAD, y, block["start"], 12, MUTED)
        _text(draw, _WIDTH - _PAD, y, block["end"], 12, MUTED, anchor="ra")
    return image
