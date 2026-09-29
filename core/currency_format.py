"""Money formatting that follows the account currency instead of a hardcoded dollar sign."""
from __future__ import annotations

import math

import pandas as pd

CURRENCY_SYMBOLS = {"USD": "$", "MXN": "MX$", "CAD": "CA$", "BRL": "R$", "GBP": "£", "EUR": "€", "JPY": "¥",
                    "AUD": "A$", "SGD": "S$", "INR": "₹"}
ZERO_DECIMAL = {"JPY"}
MISSING_AMOUNT = "—"


def currency_symbol(currency_code: str) -> str:
    code = (currency_code or "").strip().upper()
    if not code:
        return CURRENCY_SYMBOLS["USD"]
    return CURRENCY_SYMBOLS.get(code, code)


def money(value: float | int | None, currency_code: str = "", decimals: int | None = None) -> str:
    """Formats an amount with the currency symbol ("MX$1,234.56"); unknown codes read "SEK 1,234.56"."""
    if value is None or pd.isna(value):
        return MISSING_AMOUNT
    amount = float(value)
    if math.isinf(amount):
        return MISSING_AMOUNT

    code = (currency_code or "").strip().upper()
    if decimals is None:
        decimals = 0 if code in ZERO_DECIMAL else 2
    digits = f"{abs(amount):,.{decimals}f}"
    sign = "-" if amount < 0 and float(digits.replace(",", "")) != 0 else ""

    if not code or code in CURRENCY_SYMBOLS:
        return f"{sign}{currency_symbol(code)}{digits}"
    return f"{sign}{code} {digits}"


def excel_money_format(currency_code: str = "") -> str:
    """The Excel number format of an amount in the currency: '"MX$"#,##0.00', without decimals for JPY."""
    code = (currency_code or "").strip().upper()
    decimals = "" if code in ZERO_DECIMAL else ".00"
    return f'"{currency_symbol(code)}"#,##0{decimals}'
