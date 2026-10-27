"""Task value rules and cursors (`crm_app.domains.tasks`, `paging`; decision P4-C)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from crm_app.domains import paging
from crm_app.domains import tasks as rules
from crm_app.domains.records import InvalidValue


def test_titles_are_trimmed_and_bounded() -> None:
    assert rules.title("  Call back ") == "Call back"
    assert rules.title("x" * 200) == "x" * 200
    for bad in ("", "  ", "x" * 201, "a\nb", "a\tb"):
        with pytest.raises(InvalidValue):
            rules.title(bad)


def test_the_default_priority_is_one_of_the_priorities() -> None:
    assert rules.DEFAULT_PRIORITY in rules.PRIORITIES


@pytest.mark.parametrize(
    "key",
    [
        (datetime(2026, 10, 27, 9, 30, tzinfo=UTC), uuid.UUID(int=1)),
        (None, uuid.UUID(int=2)),
    ],
)
def test_due_cursors_round_trip_with_and_without_a_due_time(key: paging.Key) -> None:
    cursor = paging.encode("task", "due_at", "asc", "f", key)
    assert paging.decode(cursor, "task", "due_at", "asc", "f") == key


def test_a_created_cursor_needs_a_time() -> None:
    cursor = paging.encode("task", "due_at", "asc", "f", (None, uuid.UUID(int=1)))
    with pytest.raises(paging.InvalidCursor):
        paging.decode(cursor, "task", "created_at", "asc", "f")
