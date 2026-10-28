"""Appointment value rules (`crm_app.domains.appointments`; decision P5-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crm_app.domains import appointments as rules
from crm_app.domains.records import InvalidValue

START = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def test_titles_are_trimmed_and_bounded() -> None:
    assert rules.title("  Intro call ") == "Intro call"
    assert rules.title("x" * 200) == "x" * 200
    for bad in ("", "  ", "x" * 201, "a\nb", "a\tb"):
        with pytest.raises(InvalidValue):
            rules.title(bad)


def test_locations_are_one_trimmed_line_and_blank_is_none() -> None:
    assert rules.location(" Room 2 ") == "Room 2"
    assert rules.location("   ") is None
    assert rules.location(None) is None
    for bad in ("x" * 301, "a\nb"):
        with pytest.raises(InvalidValue):
            rules.location(bad)


def test_notes_keep_line_breaks_as_lf() -> None:
    assert rules.note(" Bring the contract\r\nand the quote ") == (
        "Bring the contract\nand the quote"
    )
    assert rules.note("\n \n") is None
    assert rules.note("x" * 2000) == "x" * 2000
    for bad in ("x" * 2001, "a\tb", "a\x00b"):
        with pytest.raises(InvalidValue):
            rules.note(bad)


@pytest.mark.parametrize(
    "length", [timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=24)]
)
def test_lengths_from_five_minutes_to_a_day_are_allowed(length: timedelta) -> None:
    rules.times(START, START + length)


@pytest.mark.parametrize(
    "length",
    [timedelta(0), timedelta(minutes=4, seconds=59), timedelta(hours=-1), timedelta(hours=25)],
)
def test_other_lengths_are_refused(length: timedelta) -> None:
    with pytest.raises(InvalidValue):
        rules.times(START, START + length)


def test_back_to_back_appointments_do_not_overlap() -> None:
    hour = timedelta(hours=1)
    assert not rules.overlaps(START, START + hour, START + hour, START + 2 * hour)
    assert rules.overlaps(START, START + hour, START + hour / 2, START + 2 * hour)
    assert rules.overlaps(START, START + 2 * hour, START + hour / 2, START + hour)


def test_the_defaults_are_among_the_values() -> None:
    assert rules.DEFAULT_KIND in rules.KINDS
    assert rules.DEFAULT_STATUS in rules.STATUSES
    assert "cancelled" in rules.STATUSES
