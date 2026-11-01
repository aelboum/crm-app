"""Conversation rules that need no database (decisions P6-C, P6-C1).

Pure functions; no database or framework.
"""

from __future__ import annotations

import re

SEARCH_MAX = 100
SEARCH_TERMS = 8
TERM_MAX = 64
# Letters and digits; everything else separates words.
_WORD = re.compile(r"[^\W_]+")


def search_terms(text: str) -> list[str]:
    """The words of a search, lowercased, deduplicated, at most
    `SEARCH_TERMS` of at most `TERM_MAX` characters."""
    words: list[str] = []
    for found in _WORD.findall(text.lower()):
        word = found[:TERM_MAX]
        if word not in words:
            words.append(word)
    return words[:SEARCH_TERMS]


def prefix_query(terms: list[str]) -> str:
    """A `to_tsquery` text in which every term must start a word. Terms come
    from `search_terms`, so the text holds only word characters, `:*` and
    `&`: no operator, quote or wildcard from the search box reaches it."""
    return " & ".join(f"{term}:*" for term in terms)
