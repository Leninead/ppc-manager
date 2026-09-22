"""Amazon's limits on the text of a negative keyword, with no Excel dependency.

The negatives selection of the Search Term Report, validate_bulk and the MCP server all read these limits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class KeywordTextLimits:
    max_characters: int
    max_words_by_match_type: Mapping[str, int]
    forbidden_characters: re.Pattern


NEGATIVE_KEYWORD_TEXT_LIMITS = KeywordTextLimits(
    max_characters=80,
    max_words_by_match_type=MappingProxyType({"Negative Phrase": 4, "Negative Exact": 10}),
    forbidden_characters=re.compile(r"[%$#@*!^={}\[\]<>?/\\|`]"),
)


def negative_keyword_text_problem(keyword_text: str, match_type: str) -> str | None:
    """Why Amazon rejects this negative Keyword Text (Spanish, lower case), or None when it is accepted."""
    limits = NEGATIVE_KEYWORD_TEXT_LIMITS
    text = keyword_text.strip()
    if len(text) > limits.max_characters:
        return f"tiene {len(text)} caracteres y Amazon admite hasta {limits.max_characters}"
    max_words = limits.max_words_by_match_type.get(match_type)
    word_count = len(text.split())
    if max_words is not None and word_count > max_words:
        return f"tiene {word_count} palabras y un {match_type} admite hasta {max_words}"
    forbidden = limits.forbidden_characters.search(text)
    if forbidden:
        return f"lleva el signo «{forbidden.group()}», que Amazon no acepta en keywords"
    return None
