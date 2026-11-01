"""Conversation search rules (decision P6-C1, `crm_app.domains.conversations`)."""

from __future__ import annotations

import re

import pytest

from crm_app.domains import conversations as rules


def test_words_are_lowercased_deduplicated_and_kept_in_order() -> None:
    assert rules.search_terms("Parcel BROKEN parcel") == ["parcel", "broken"]
    assert rules.search_terms("Café crème") == ["café", "crème"]
    assert rules.search_terms("grace@example.test") == ["grace", "example", "test"]


@pytest.mark.parametrize(
    "text",
    ["", "   ", "%", "_", "\\", "'", "&|!():*", "-- ;", "<>"],
)
def test_input_without_letters_or_digits_has_no_terms(text: str) -> None:
    assert rules.search_terms(text) == []


def test_query_syntax_and_quotes_never_reach_the_query() -> None:
    terms = rules.search_terms("zebra & !parcel | (x:*) ' OR 1=1 -- 50% snake_case")
    query = rules.prefix_query(terms)
    assert terms == ["zebra", "parcel", "x", "or", "1", "50", "snake", "case"]
    assert re.fullmatch(r"\w+:\*( & \w+:\*)*", query)
    assert not set(query) & set("'|!()\\%_")


def test_terms_and_term_length_are_capped() -> None:
    terms = rules.search_terms(" ".join(f"w{i}" for i in range(20)))
    assert len(terms) == rules.SEARCH_TERMS
    assert rules.search_terms("a" * 500) == ["a" * rules.TERM_MAX]
