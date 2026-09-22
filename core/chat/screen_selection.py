"""What the AM has selected on each page, written for the chat's turn note.

A page shares its selection on every run and the chat remembers the last one of each page for the rest of the
browser session. It carries coordinates, never tables: the figures are brought by the MCP call it names.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

FROM_AMAZON_ADS = "Amazon Ads"
FROM_HAND_UPLOAD = "un archivo subido a mano"
HAND_UPLOAD_NOTE = "Las herramientas no ven archivos subidos a mano: sus cifras sólo están en esta pantalla."
OLDER_DATA_NOTE = ("La pantalla muestra datos anteriores a la última sincronización: las herramientas leen los más "
                   "nuevos, así que sus cifras pueden diferir.")


@dataclass(frozen=True)
class ToolCall:
    """The call of the app's MCP tools (or DataDive's) that brings the figures behind a selection."""

    name: str
    arguments: tuple[tuple[str, object], ...] = ()

    def text(self) -> str:
        arguments = ", ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in self.arguments)
        return f"{self.name}({arguments})"


@dataclass(frozen=True)
class ScreenSelection:
    module: str
    account: str
    source: str
    # The Amazon Ads profile on screen; "" for a hand upload or another source.
    profile_id: str = ""
    window_start: date | None = None
    window_end: date | None = None
    # The inputs on screen as the AM reads them: ("mínimo de órdenes para harvest", "3").
    values: tuple[tuple[str, str], ...] = ()
    calls: tuple[ToolCall, ...] = ()
    notes: tuple[str, ...] = ()


def account_window(profile_id: str, start: date, end: date) -> tuple[tuple[str, object], ...]:
    """The arguments every account tool takes to read exactly the days a page shows."""
    return (("profile_id", profile_id), ("date_from", start.isoformat()), ("date_to", end.isoformat()))


def selection_text(selection: ScreenSelection) -> str:
    """One sentence per selection: module, account, days, source, values, the calls behind it and its caveats."""
    parts = [f"«{selection.module}» con {selection.account}"]
    if selection.window_start and selection.window_end:
        parts.append(f"del {selection.window_start.isoformat()} al {selection.window_end.isoformat()}")
    parts.append(f"datos de {selection.source}")
    text = ", ".join(parts)
    if selection.values:
        text += "; valores en pantalla: " + ", ".join(f"{label} = {value}" for label, value in selection.values)
    if selection.calls:
        text += "; sus cifras salen de " + " y ".join(call.text() for call in selection.calls)
    text += "."
    if selection.notes:
        text += " " + " ".join(selection.notes)
    return text


def selections_note(page: str, selections: dict[str, ScreenSelection], remembered: int) -> list[str]:
    """The open page's selection first, then the ones the AM looked at before, the most recent first."""
    lines = []
    if page in selections:
        lines.append(f"Lo que tiene seleccionado en esta pantalla: {selection_text(selections[page])}")
    earlier = [selections[visited] for visited in reversed(list(selections)) if visited != page][:remembered]
    if earlier:
        lines.append("Antes miró, de lo más reciente a lo más viejo: "
                     + " ".join(selection_text(selection) for selection in earlier))
    return lines
