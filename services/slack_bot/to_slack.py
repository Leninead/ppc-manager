"""An answer's components as Slack messages: Block Kit for what Slack can draw, PNG for the charts."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.chat import components
from services.slack_bot import charts, slack_text

log = logging.getLogger(__name__)

TONE_MARK = {"good": "🟢", "bad": "🔴"}
ALERT_MARK = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
ACTION_MARK = "➡️"
IDEA_ACTION_PREFIX = "idea_"

_MESSAGE_BLOCKS = 45  # Slack refuses more than 50 blocks in one message
_KPI_FIELDS = 10
_TABLE_ROWS = 100
_TABLE_COLUMNS = 20
_TABLE_CHARS = 10_000
_FALLBACK_CHARS = 2_900
_BUTTON_CHARS = 75


@dataclass
class MessagePart:
    blocks: list[dict]
    text: str


@dataclass(frozen=True)
class ChartPart:
    png: bytes
    title: str
    alt: str


Part = MessagePart | ChartPart


def section(mrkdwn: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": mrkdwn}}


def context(mrkdwn: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": mrkdwn}]}


def prose(text: str) -> list[dict]:
    return [section(piece) for piece in slack_text.sections(slack_text.to_mrkdwn(text))]


def answer_parts(blocks: list[dict], *, header: str = "", sources: str = "", mention: str = "") -> list[Part]:
    """The answer in the order the model wrote it: a chart or a table ends a message, so nothing moves."""
    builder = _Parts(mention)
    leading = [context(text) for text in (header, sources) if text]
    if leading:
        builder.add(leading, "")
    for block in blocks:
        if block["kind"] in charts.KINDS:
            try:
                builder.chart(ChartPart(charts.draw(block), _chart_title(block), components.plain_text([block])))
            except Exception:  # a chart that cannot be drawn is still readable as text
                log.exception("chart %s not drawn; sent as text", block["kind"])
                builder.add(prose(components.plain_text([block])), components.plain_text([block]))
            continue
        converted, closes = _blocks(block)
        builder.add(converted, components.plain_text([block]), closes=closes)
    return builder.done()


def ideas_blocks(intro: str, questions: list[str]) -> list[dict]:
    buttons = [{"type": "button", "action_id": f"{IDEA_ACTION_PREFIX}{index}",
                "text": {"type": "plain_text", "text": slack_text.shortened(question, _BUTTON_CHARS)},
                "value": question[:2000]}
               for index, question in enumerate(questions)]
    return [section(slack_text.escape(intro)), {"type": "actions", "elements": buttons}] if buttons else \
        [section(slack_text.escape(intro))]


class _Parts:
    def __init__(self, mention: str):
        self._mention = mention
        self._parts: list[Part] = []
        self._blocks: list[dict] = []
        self._plain: list[str] = []

    def add(self, blocks: list[dict], plain: str, closes: bool = False) -> None:
        if self._blocks and len(self._blocks) + len(blocks) > _MESSAGE_BLOCKS:
            self._flush()
        for start in range(0, len(blocks), _MESSAGE_BLOCKS):
            self._blocks.extend(blocks[start:start + _MESSAGE_BLOCKS])
            if start + _MESSAGE_BLOCKS < len(blocks):
                self._flush()
        if plain:
            self._plain.append(plain)
        if closes:
            self._flush()

    def chart(self, part: ChartPart) -> None:
        self._flush()
        self._parts.append(part)

    def done(self) -> list[Part]:
        self._flush()
        return self._parts

    def _flush(self) -> None:
        if not self._blocks:
            return
        first = not any(isinstance(part, MessagePart) for part in self._parts)
        text = "\n\n".join(self._plain)
        if first and self._mention:
            text = f"{self._mention} {text}".strip()
        self._parts.append(MessagePart(self._blocks, slack_text.shortened(text, _FALLBACK_CHARS) or "…"))
        self._blocks, self._plain = [], []


def _blocks(block: dict) -> tuple[list[dict], bool]:
    """(Slack blocks, whether they end the message): Slack shows one table per message, at its bottom."""
    kind = block["kind"]
    if kind == "text":
        return prose(block["text"]), False
    if kind == "kpis":
        return _kpis(block), False
    if kind == "table":
        table = _table(block)
        return ([table], True) if table else (_table_as_text(block), False)
    if kind == "alert":
        mark = ALERT_MARK.get(block["level"], ALERT_MARK["info"])
        return [section(piece) for piece in slack_text.sections(
            slack_text.quoted(f"{mark} {slack_text.to_mrkdwn(block['text'])}"))], False
    if kind == "action":
        return [section(piece) for piece in slack_text.sections(
            slack_text.quoted(f"{ACTION_MARK} {slack_text.to_mrkdwn(block['text'])}"))], False
    return prose(components.plain_text([block])), False


def _marked(value: str, tone: str) -> str:
    mark = TONE_MARK.get(tone)
    return f"{value} {mark}" if mark and value else value


def _kpis(block: dict) -> list[dict]:
    fields = []
    for item in block["items"]:
        lines = [f"*{slack_text.escape(item['label'])}*" if item["label"] else "",
                 slack_text.escape(_marked(item["value"], item["tone"]))]
        if item["detail"]:
            lines.append(f"_{slack_text.escape(item['detail'])}_")
        fields.append({"type": "mrkdwn", "text": "\n".join(line for line in lines if line)})
    return [{"type": "section", "fields": fields[start:start + _KPI_FIELDS]}
            for start in range(0, len(fields), _KPI_FIELDS)]


def _table(block: dict) -> dict | None:
    columns = block["columns"]
    rows = block["rows"]
    with_header = any(columns)
    if len(rows) + int(with_header) > _TABLE_ROWS or len(columns) > _TABLE_COLUMNS:
        return None
    body = [[{"type": "raw_text", "text": _marked(cell["value"], cell["tone"]) or "—"} for cell in row]
            for row in rows]
    header = [[{"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [
        {"type": "text", "text": column or " ", "style": {"bold": True}}]}]} for column in columns]]
    table_rows = (header if with_header else []) + body
    if sum(len(column) for column in columns) + sum(len(cell["text"]) for row in body for cell in row) > _TABLE_CHARS:
        return None
    settings = [{"is_wrapped": True}] + [{"align": "right"} for _ in columns[1:]]
    return {"type": "table", "column_settings": settings, "rows": table_rows}


def _table_as_text(block: dict) -> list[dict]:
    """Too big for Slack's table: the same rows, aligned in a code block."""
    rows = [block["columns"]] + [[_marked(cell["value"], cell["tone"]) for cell in row] for row in block["rows"]]
    widths = [max(len(row[i]) for row in rows) for i in range(len(block["columns"]))]
    lines = ["  ".join(cell.ljust(width) if i == 0 else cell.rjust(width) for i, (cell, width)
                       in enumerate(zip(row, widths, strict=True))).rstrip() for row in rows]
    pieces = slack_text.sections(slack_text.escape("\n".join(lines)), slack_text.SECTION_LIMIT - 8)
    return [section(f"```\n{piece}\n```") for piece in pieces]


def _chart_title(block: dict) -> str:
    return block.get("metric") or block.get("label") or "Gráfico"


@dataclass(frozen=True)
class Notice:
    """A short message of the bot's own: a status, a refusal or a failure, never an answer."""

    text: str
    blocks: list[dict] = field(default_factory=list)

    @classmethod
    def of(cls, text: str) -> Notice:
        return cls(text=text, blocks=[section(slack_text.escape(text))])
