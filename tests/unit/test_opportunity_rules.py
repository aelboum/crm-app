"""Deal value rules and cursors (`crm_app.domains.opportunities`,
`crm_app.domains.paging`; decision P4-B)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from crm_app.domains import opportunities as rules
from crm_app.domains import paging
from crm_app.domains.records import InvalidValue
from crm_app.domains.settings import CURRENCIES


@pytest.mark.parametrize(
    ("raw", "currency", "stored", "shown"),
    [
        ("12500.5", "EUR", Decimal("12500.5"), "12500.50"),
        ("0", "EUR", Decimal(0), "0.00"),
        ("999999999999.99", "USD", Decimal("999999999999.99"), "999999999999.99"),
        ("1500", "JPY", Decimal(1500), "1500"),
        ("1.250", "BHD", Decimal("1.25"), "1.250"),
        ("0.1", "EUR", Decimal("0.1"), "0.10"),
    ],
)
def test_amounts_are_exact_in_their_currency(
    raw: str, currency: str, stored: Decimal, shown: str
) -> None:
    value = rules.amount(raw, currency)
    assert value == stored
    assert rules.amount_text(value, currency) == shown


@pytest.mark.parametrize(
    ("raw", "currency"),
    [
        ("10.505", "EUR"),
        ("1500.5", "JPY"),
        ("1.2345", "KWD"),
        ("1000000000000", "EUR"),
        ("-1", "EUR"),
        ("+1", "EUR"),
        ("1e3", "EUR"),
        ("1,50", "EUR"),
        ("01", "EUR"),
        (".5", "EUR"),
        ("5.", "EUR"),
        ("NaN", "EUR"),
        ("Infinity", "EUR"),
        ("", "EUR"),
        (" 1", "EUR"),
    ],
)
def test_amounts_outside_the_rules_are_refused_never_rounded(raw: str, currency: str) -> None:
    with pytest.raises(InvalidValue):
        rules.amount(raw, currency)


def test_the_currencies_with_other_minor_digits() -> None:
    assert rules.minor_digits("JPY") == 0
    assert rules.minor_digits("BHD") == 3
    assert rules.minor_digits("EUR") == 2
    # Every special case is a currency a workspace can choose.
    assert {"JPY", "KRW", "BHD", "KWD", "TND", "XOF"} <= CURRENCIES


def test_titles_and_reasons_are_trimmed_and_bounded() -> None:
    assert rules.title("  Website redesign ") == "Website redesign"
    assert rules.lost_reason(" Budget cut ") == "Budget cut"
    for bad in ("", "  ", "x" * 201, "a\nb", "a\tb"):
        with pytest.raises(InvalidValue):
            rules.title(bad)
    with pytest.raises(InvalidValue):
        rules.lost_reason("x" * 501)


def test_outcomes_move_only_through_open() -> None:
    assert ("open", "won") in rules.TRANSITIONS
    assert ("lost", "open") in rules.TRANSITIONS
    assert ("won", "lost") not in rules.TRANSITIONS
    assert ("lost", "won") not in rules.TRANSITIONS
    assert ("open", "open") not in rules.TRANSITIONS


@pytest.mark.parametrize(
    ("order", "key"),
    [
        ("amount", (Decimal("12500.500"), uuid.UUID(int=1))),
        ("amount", (None, uuid.UUID(int=2))),
        ("expected_close_date", (date(2026, 12, 15), uuid.UUID(int=3))),
        ("expected_close_date", (None, uuid.UUID(int=4))),
        ("title", ("Website", uuid.UUID(int=5))),
    ],
)
def test_deal_cursors_round_trip(order: str, key: paging.Key) -> None:
    cursor = paging.encode("opportunity", order, "asc", "f", key)
    assert paging.decode(cursor, "opportunity", order, "asc", "f") == key


def test_history_cursors_hold_a_sequence_number() -> None:
    cursor = paging.encode("opportunity_event", "seq", "desc", "", (42,))
    assert paging.decode(cursor, "opportunity_event", "seq", "desc", "") == (42,)
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "opportunity_event", "seq", "asc", "")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "abc"])
def test_a_forged_amount_key_is_refused(bad: str) -> None:
    payload = {"v": 1, "s": "amount", "d": "asc", "f": "f", "k": [bad, str(uuid.UUID(int=1))]}
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "opportunity", "amount", "asc", "f")
