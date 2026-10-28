"""Booking page rules (decision P5-C): the free times a page offers, the
visitor's details, the appointment title and the link token."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest

from crm_app.domains import appointments as appointment_rules
from crm_app.domains import booking_pages as rules
from crm_app.domains.records import InvalidValue


def _utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


MINUTES_30 = timedelta(minutes=30)
OPEN = [(_utc(2, 9), _utc(2, 12))]


def _free(
    *,
    intervals: list[tuple[datetime, datetime]] = OPEN,
    busy: list[tuple[datetime, datetime]] | None = None,
    length: timedelta = MINUTES_30,
    step: timedelta = MINUTES_30,
    earliest: datetime | None = None,
    latest: datetime | None = None,
) -> list[datetime]:
    return rules.free_times(
        intervals,
        busy or [],
        length=length,
        step=step,
        earliest=earliest or _utc(1, 0),
        latest=latest or _utc(30, 0),
    )


def test_times_follow_the_step_from_the_opening_and_fit_inside() -> None:
    assert _free() == [_utc(2, h, m) for h in (9, 10, 11) for m in (0, 30)]
    hour = timedelta(hours=1)
    # A 60-minute appointment every 30 minutes: the last one starts at 11:00.
    assert _free(length=hour)[-1] == _utc(2, 11)
    assert _free(length=hour, step=hour) == [_utc(2, 9), _utc(2, 10), _utc(2, 11)]


def test_busy_time_hides_overlapping_starts_only() -> None:
    times = _free(busy=[(_utc(2, 10), _utc(2, 10, 45))])
    assert _utc(2, 9, 30) in times  # Ends at 10:00: back to back is free.
    assert _utc(2, 10) not in times
    assert _utc(2, 10, 30) not in times
    assert _utc(2, 11) in times


def test_notice_and_horizon_bound_the_starts() -> None:
    assert _free(earliest=_utc(2, 10, 15))[0] == _utc(2, 10, 30)
    assert _free(latest=_utc(2, 10))[-1] == _utc(2, 10)
    assert _free(earliest=_utc(3, 0)) == []


def test_times_are_capped() -> None:
    fifteen = timedelta(minutes=15)
    wide = [(_utc(1, 0), _utc(1, 0) + timedelta(days=60))]
    times = _free(
        intervals=wide, step=fifteen, length=fifteen, latest=_utc(1, 0) + timedelta(days=60)
    )
    assert len(times) == rules.TIMES_MAX


def test_visitor_details_are_normalised() -> None:
    given = rules.visitor("  Ada ", None, " ADA@Example.org ", "+31 6 1234", " Hi\r\nthere ")
    assert given == {
        "first_name": "Ada",
        "last_name": None,
        "email": "ada@example.org",
        "phone": "+31 6 1234",
        "message": "Hi\nthere",
    }


@pytest.mark.parametrize(
    ("details", "errors"),
    [
        ((None, None, "a@b.co", None, None), {"first_name": "invalid"}),
        (("Ada", None, None, None, None), {"email": "required"}),
        (("Ada", None, "not an email", None, None), {"email": "invalid"}),
        (("Ada", None, "a@b.co", "call me", None), {"phone": "invalid"}),
        (("Ada\u200b", None, "a@b.co", None, None), {"first_name": "invalid"}),
        (("Ada", None, "a@b.co", None, "x" * 1001), {"message": "invalid"}),
        (("", "", "", None, None), {"first_name": "invalid", "email": "required"}),
    ],
)
def test_visitor_details_are_refused_by_field(
    details: tuple[str | None, str | None, str | None, str | None, str | None],
    errors: dict[str, str],
) -> None:
    with pytest.raises(rules.InvalidVisitor) as refused:
        rules.visitor(*details)
    assert refused.value.errors == errors


def test_page_values() -> None:
    assert rules.name("  Intro call ") == "Intro call"
    with pytest.raises(InvalidValue):
        rules.name(" ")
    with pytest.raises(InvalidValue):
        rules.name("x" * 121)
    assert rules.description(" One\r\ntwo ") == "One\ntwo"
    assert rules.description("   ") is None
    with pytest.raises(InvalidValue):
        rules.description("tab\there")
    assert rules.choice(45, rules.LENGTHS) == 45
    with pytest.raises(InvalidValue):
        rules.choice(20, rules.LENGTHS)
    assert rules.bounded(0, 0, rules.NOTICE_MAX) == 0
    with pytest.raises(InvalidValue):
        rules.bounded(91, 1, rules.HORIZON_MAX)


def test_the_title_fits_an_appointment() -> None:
    assert rules.title("Intro call", "Ada Lovelace") == "Intro call — Ada Lovelace"
    long = rules.title("x" * 120, "y" * 200)
    assert len(long) == appointment_rules.TITLE_MAX
    assert long.endswith("…")
    assert appointment_rules.title(long) == long


def test_only_issued_tokens_have_a_hash() -> None:
    token = secrets.token_urlsafe(32)
    digest = rules.token_hash(token)
    assert digest is not None
    assert len(digest) == 64
    assert rules.token_hash(token) == digest
    for wrong in ("", "short", token + "x", token[:-1] + "!"):
        assert rules.token_hash(wrong) is None
