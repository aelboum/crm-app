"""Appointment reminder rules (decision P5-D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crm_app.domains import reminders as rules
from crm_app.domains.records import InvalidValue

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def test_only_the_offered_lead_times_or_off_are_accepted() -> None:
    assert rules.lead_minutes(None) is None
    for lead in rules.LEADS:
        assert rules.lead_minutes(lead) == lead
    for bad in (0, 45, -60, 1440.0, "1440", True):
        with pytest.raises(InvalidValue):
            rules.lead_minutes(bad)


def _due(**overrides: object) -> bool:
    values: dict[str, object] = {
        "starts_at": NOW + timedelta(hours=20),
        "created_at": NOW - timedelta(days=3),
        "status": "confirmed",
        "cancelled": False,
        "lead": 1440,
        "now": NOW,
    }
    values.update(overrides)
    return rules.due(**values)  # type: ignore[arg-type]


def test_a_reminder_is_due_inside_the_window_for_an_open_appointment() -> None:
    assert _due()
    assert _due(status="pending")
    # exactly at the reminder time
    assert _due(starts_at=NOW + timedelta(hours=24))


def test_no_reminder_outside_the_window_or_for_a_closed_appointment() -> None:
    assert not _due(starts_at=NOW + timedelta(hours=25))
    assert not _due(starts_at=NOW)
    assert not _due(starts_at=NOW - timedelta(minutes=1))
    for status in ("completed", "no_show", "cancelled"):
        assert not _due(status=status)
    assert not _due(cancelled=True)


def test_an_appointment_made_inside_the_window_is_not_reminded() -> None:
    # booked an hour ago for 20 hours from now: the confirmation suffices
    assert not _due(created_at=NOW - timedelta(hours=1))


def test_the_text_names_the_time_and_holds_no_link() -> None:
    start = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)
    subject, body = rules.text(
        "Ada",
        "Intro call",
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        time_zone="Europe/Amsterdam",
        kind="video",
        location="https://meet.example.org/ada",
    )
    assert subject == "Reminder: Intro call, Tuesday 3 November 2026"
    assert "Hello Ada," in body
    assert "14:00 to 14:30 (Europe/Amsterdam)" in body
    assert "Video call: https://meet.example.org/ada" in body
    nameless = rules.text(
        None,
        "Call",
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        time_zone="UTC",
        kind="phone",
        location=None,
    )[1]
    assert nameless.startswith("Hello,\n")
