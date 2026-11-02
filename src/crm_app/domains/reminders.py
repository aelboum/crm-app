"""Appointment reminder rules (decision P5-D): pure functions, no database.

A workspace chooses how long before an appointment its contact is emailed
a reminder (`LEADS`, in minutes) or none. An appointment is reminded about
once per start time, only while it is still pending or confirmed, only if
it was made before the reminder time (one booked inside the window already
had its confirmation), and only before it starts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from crm_app.domains import booking_pages
from crm_app.domains.records import InvalidValue

LEADS = (60, 120, 1440, 2880)
REMINDED_STATUSES = ("pending", "confirmed")
# A member's "Send reminder" is refused within this time of the last one.
MANUAL_GAP = timedelta(hours=1)
SKIP_REASONS = ("no_contact", "contact_archived", "no_email", "invalid_email")


def lead_minutes(value: object) -> int | None:
    """A lead time from `LEADS`, or None (off)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in LEADS:
        raise InvalidValue(f"reminder: one of {', '.join(map(str, LEADS))} minutes, or off")
    return value


def due(  # noqa: PLR0913 - the appointment's state, the setting and the clock
    *,
    starts_at: datetime,
    created_at: datetime,
    status: str,
    cancelled: bool,
    lead: int,
    now: datetime,
) -> bool:
    """Whether an automatic reminder is due now for this appointment."""
    remind_at = starts_at - timedelta(minutes=lead)
    return (
        not cancelled and status in REMINDED_STATUSES and created_at < remind_at <= now < starts_at
    )


def text(  # noqa: PLR0913 - what the contact should remember
    first_name: str | None,
    title: str,
    *,
    starts_at: datetime,
    ends_at: datetime,
    time_zone: str,
    kind: str,
    location: str | None,
) -> tuple[str, str]:
    """The reminder's subject and plain text: the time in the workspace's
    time zone, named, and how it happens. No links and nothing else from
    the record: the appointment's note stays internal."""
    day, when = booking_pages.when_text(starts_at, ends_at, time_zone)
    subject = f"Reminder: {title}, {day}"
    lines = [
        f"Hello {first_name}," if first_name else "Hello,",
        "",
        f"This is a reminder of your appointment: {title}.",
        "",
        when,
        booking_pages.kind_text(kind, location),
    ]
    return subject[:200], "\n".join(lines)
