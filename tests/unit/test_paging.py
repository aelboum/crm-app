"""List cursors (`crm_app.domains.paging`; `PHASE3-PLAN.md` §19.5).

A cursor must round-trip exactly and be refused for anything else: another
order, direction or filter set, a damaged encoding, extra or missing fields,
wrong types, or a size over the limit.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import pytest

from crm_app.domains import paging

ROW = uuid.UUID("00000000-0000-4000-8000-000000000001")
FILTERS = paging.filter_hash({"q": None, "archived": "false"})


def _cursor(payload: object) -> str:
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.mark.parametrize(
    ("kind", "order", "key"),
    [
        ("contact", "name", ("Jansen", "Anna", ROW)),
        ("contact", "name", (None, "Anna", ROW)),
        ("company", "name", ("Acme", ROW)),
        ("contact", "created_at", (datetime(2026, 10, 23, 9, 30, 1, 123456, tzinfo=UTC), ROW)),
        ("company", "updated_at", (datetime(2026, 10, 23, tzinfo=UTC), ROW)),
    ],
)
def test_a_cursor_round_trips_its_key(kind: str, order: str, key: tuple[object, ...]) -> None:
    cursor = paging.encode(kind, order, "asc", FILTERS, key)  # type: ignore[arg-type]
    assert len(cursor) <= paging.CURSOR_MAX
    assert paging.decode(cursor, kind, order, "asc", FILTERS) == key


def test_the_filter_hash_ignores_key_order_and_sees_every_value() -> None:
    assert paging.filter_hash({"a": 1, "b": [2]}) == paging.filter_hash({"b": [2], "a": 1})
    assert paging.filter_hash({"a": 1}) != paging.filter_hash({"a": 2})


@pytest.mark.parametrize(
    ("order", "direction", "filters"),
    [
        ("created_at", "asc", FILTERS),
        ("name", "desc", FILTERS),
        ("name", "asc", paging.filter_hash({"q": "a"})),
    ],
)
def test_a_cursor_is_refused_for_another_order_direction_or_filter_set(
    order: str, direction: str, filters: str
) -> None:
    cursor = paging.encode("company", "name", "asc", FILTERS, ("Acme", ROW))
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "company", order, direction, filters)


def _valid() -> dict[str, object]:
    return {"v": 1, "s": "name", "d": "asc", "f": FILTERS, "k": ["Acme", str(ROW)]}


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not base64 !",
        "x" * (paging.CURSOR_MAX + 1),
        base64.urlsafe_b64encode(b"not json").decode(),
        _cursor([1, 2]),
        _cursor({**_valid(), "extra": 1}),
        _cursor({k: v for k, v in _valid().items() if k != "k"}),
        _cursor({**_valid(), "v": 2}),
        _cursor({**_valid(), "k": ["Acme"]}),
        _cursor({**_valid(), "k": ["Acme", "not-a-uuid"]}),
        _cursor({**_valid(), "k": [None, str(ROW)]}),  # a company name is never NULL
        _cursor({**_valid(), "k": [7, str(ROW)]}),
    ],
)
def test_a_damaged_or_forged_cursor_is_refused(cursor: str) -> None:
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "company", "name", "asc", FILTERS)


def test_a_timestamp_without_a_time_zone_is_refused() -> None:
    cursor = _cursor(
        {
            "v": 1,
            "s": "created_at",
            "d": "asc",
            "f": FILTERS,
            "k": ["2026-10-23T09:30:00", str(ROW)],
        }
    )
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "contact", "created_at", "asc", FILTERS)


def test_a_cursor_holding_a_nul_character_is_refused() -> None:
    cursor = _cursor({**_valid(), "k": ["Ac\0me", str(ROW)]})
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "company", "name", "asc", FILTERS)
