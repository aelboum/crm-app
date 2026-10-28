"""Suppression and consent rules (decision P7-B): pasted address lists, the
reason, notes and wording, the search term and the send rule."""

from __future__ import annotations

import pytest

from crm_app.domains import suppression as rules
from crm_app.domains.records import InvalidValue


def test_addresses_are_stored_lower_cased_once_in_order() -> None:
    given = [" Sam@Example.TEST ", "ada@example.test", "sam@example.test"]
    assert rules.addresses(given) == ["sam@example.test", "ada@example.test"]


def test_refused_addresses_are_named_by_position_only() -> None:
    with pytest.raises(rules.InvalidAddresses) as refused:
        rules.addresses(["ok@example.test", "not an address", "", "x\x00@example.test"])
    assert refused.value.positions == [1, 2, 3]
    assert "not an address" not in str(refused.value)


@pytest.mark.parametrize("raw", [[], ["a@example.test"] * (rules.ADD_MAX + 1)])
def test_a_list_is_neither_empty_nor_too_long(raw: list[str]) -> None:
    with pytest.raises(InvalidValue):
        rules.addresses(raw)


def test_reasons_notes_and_wording() -> None:
    assert rules.reason("bounced") == "bounced"
    with pytest.raises(InvalidValue):
        rules.reason("annoyed")
    assert rules.note("  Asked by phone\r\n ") == "Asked by phone"
    assert rules.note("   ") is None
    assert rules.note(None) is None
    with pytest.raises(InvalidValue):
        rules.note("x" * (rules.NOTE_MAX + 1))
    assert rules.wording(" Yes, email me. ") == "Yes, email me."
    for refused in ("", "   ", "tab\there", "x" * 501):
        with pytest.raises(InvalidValue):
            rules.wording(refused)


def test_search_terms() -> None:
    assert rules.search("  SAM@ ") == "sam@"
    assert rules.search(" ") is None
    assert rules.search(None) is None
    with pytest.raises(InvalidValue):
        rules.search("x" * (rules.SEARCH_MAX + 1))


@pytest.mark.parametrize(
    ("suppressed", "consent", "marketing", "allowed"),
    [
        (True, "granted", False, False),
        (True, "granted", True, False),
        (False, "none", False, True),
        (False, "none", True, False),
        (False, "withdrawn", True, False),
        (False, "granted", True, True),
    ],
)
def test_the_send_rule(*, suppressed: bool, consent: str, marketing: bool, allowed: bool) -> None:
    assert rules.may_send(suppressed=suppressed, consent=consent, marketing=marketing) is allowed
