"""Keeps exported spreadsheet text inert: text that openpyxl typed as a formula is stored as plain text.

Search terms are typed by shoppers, so a term like `=HYPERLINK(...)` must never run when the file is opened.
"""
from __future__ import annotations

from openpyxl.workbook.workbook import Workbook

_FORMULA_TYPE = "f"
_TEXT_TYPE = "s"


def force_text_cells(workbook: Workbook) -> int:
    """Stores every formula-typed text cell as plain text with the exact same value; returns how many changed."""
    changed = 0
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.data_type == _FORMULA_TYPE and isinstance(cell.value, str):
                    cell.data_type = _TEXT_TYPE
                    changed += 1
    return changed
