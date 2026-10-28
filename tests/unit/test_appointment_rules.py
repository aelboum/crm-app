"""Appointment value rules and business hours (`crm_app.domains.appointments`;
decisions P5-A and P5-B)."""

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


# --- Business hours (decision P5-B) ------------------------------------------------

NINE_TO_FIVE: list[dict[str, str] | None] = [
    *({"opens": "09:00", "closes": "17:00"} for _ in range(5)),
    None,
    None,
]


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_open_intervals_follow_the_weekdays_in_the_workspace_zone() -> None:
    # Monday 2026-10-19 to Monday 2026-10-26 in Amsterdam (UTC+2 until the 25th).
    found = rules.open_intervals(
        NINE_TO_FIVE, "Europe/Amsterdam", _utc(2026, 10, 18, 22), _utc(2026, 10, 25, 23)
    )
    assert [(o.isoformat(), c.isoformat()) for o, c in found] == [
        (f"2026-10-{day}T07:00:00+00:00", f"2026-10-{day}T15:00:00+00:00")
        for day in (19, 20, 21, 22, 23)
    ]


def test_a_daylight_saving_change_keeps_the_local_hours() -> None:
    # Amsterdam moves from UTC+2 to UTC+1 on Sunday 2026-10-25.
    found = rules.open_intervals(
        NINE_TO_FIVE, "Europe/Amsterdam", _utc(2026, 10, 23, 0), _utc(2026, 10, 27, 0)
    )
    assert [o.isoformat() for o, _ in found] == [
        "2026-10-23T07:00:00+00:00",  # Friday, summer time
        "2026-10-26T08:00:00+00:00",  # Monday, winter time
    ]


def test_intervals_only_overlapping_the_range_are_returned() -> None:
    found = rules.open_intervals(
        NINE_TO_FIVE, "UTC", _utc(2026, 10, 19, 16, 30), _utc(2026, 10, 19, 18)
    )
    assert found == [(_utc(2026, 10, 19, 9), _utc(2026, 10, 19, 17))]
    assert rules.open_intervals(NINE_TO_FIVE, "UTC", _utc(2026, 10, 24), _utc(2026, 10, 26)) == []


def test_a_time_is_within_hours_only_inside_one_open_interval() -> None:
    days = rules.open_intervals(NINE_TO_FIVE, "UTC", _utc(2026, 10, 19), _utc(2026, 10, 21))
    assert rules.within(days, _utc(2026, 10, 19, 9), _utc(2026, 10, 19, 17))
    assert not rules.within(days, _utc(2026, 10, 19, 16, 30), _utc(2026, 10, 19, 17, 30))
    assert not rules.within(days, _utc(2026, 10, 19, 8, 30), _utc(2026, 10, 19, 9, 30))
    # Spanning the night between two open days is outside.
    assert not rules.within(days, _utc(2026, 10, 19, 16), _utc(2026, 10, 20, 10))
