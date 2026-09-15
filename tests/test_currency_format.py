"""Tests for core/currency_format.py: money follows the account currency."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.currency_format import CURRENCY_SYMBOLS, ZERO_DECIMAL, currency_symbol, money


def test_empty_code_keeps_todays_dollar_format():
    assert money(1234.56) == "$1,234.56"
    assert money(1234.56, "") == "$1,234.56"


def test_usd_matches_todays_dollar_format():
    assert money(1234.56, "USD") == f"${1234.56:,.2f}"


def test_known_currency_uses_its_symbol():
    assert money(1234.56, "MXN") == "MX$1,234.56"
    assert money(1234.56, "CAD") == "CA$1,234.56"
    assert money(99.5, "EUR") == "€99.50"


def test_currency_code_is_case_and_space_insensitive():
    assert money(10, " mxn ") == "MX$10.00"


def test_zero_decimal_currency_rounds_to_whole_units():
    assert "JPY" in ZERO_DECIMAL
    assert money(1234.56, "JPY") == "¥1,235"


def test_unknown_currency_prefixes_the_code():
    assert money(1234.56, "SEK") == "SEK 1,234.56"


@pytest.mark.parametrize("missing", [None, float("nan"), np.nan, pd.NA, math.inf, -math.inf])
def test_missing_or_infinite_amount_renders_dash(missing):
    assert money(missing, "MXN") == "—"


def test_explicit_decimals_override_the_currency_default():
    assert money(1234.5678, "USD", decimals=3) == "$1,234.568"
    assert money(1234.4, "USD", decimals=0) == "$1,234"


def test_negative_amount_puts_the_sign_before_the_symbol():
    assert money(-12.5, "MXN") == "-MX$12.50"
    assert money(-12.5, "SEK") == "-SEK 12.50"


def test_negative_amount_that_rounds_to_zero_has_no_sign():
    assert money(-0.001, "USD") == "$0.00"


def test_integer_and_numpy_amounts_are_accepted():
    assert money(7, "BRL") == "R$7.00"
    assert money(np.float64(3.456), "GBP") == "£3.46"
    assert money(np.int64(2000), "INR") == "₹2,000.00"


def test_currency_symbol_defaults_to_dollar_without_code():
    assert currency_symbol("") == "$"
    assert currency_symbol(None) == "$"


def test_currency_symbol_for_every_known_code():
    for code, symbol in CURRENCY_SYMBOLS.items():
        assert currency_symbol(code) == symbol
        assert currency_symbol(code.lower()) == symbol


def test_currency_symbol_for_unknown_code_is_the_code():
    assert currency_symbol("sek") == "SEK"
