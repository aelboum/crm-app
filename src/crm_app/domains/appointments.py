"""Pure rules for appointments (decision P5-A, migration 0014).

Each function returns the value as the database stores it, or raises
`InvalidValue`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from crm_app.domains.records import InvalidValue, visible_text

TITLE_MAX = 200
LOCATION_MAX = 300
NOTE_MAX = 2000
KINDS = ("in_person", "video", "phone")
STATUSES = ("pending", "confirmed", "completed", "no_show", "cancelled")
DEFAULT_KIND = "in_person"
DEFAULT_STATUS = "confirmed"
SHORTEST = timedelta(minutes=5)
LONGEST = timedelta(hours=24)
# The calendar's widest range: a month view with its leading and trailing
# weeks (P5-A 5).
RANGE_MAX = timedelta(days=42)
RANGE_ITEMS_MAX = 500


def title(value: str) -> str:
    """Trimmed, 1..200 characters, no control, format or separator characters."""
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > TITLE_MAX:
        raise InvalidValue(f"must be at most {TITLE_MAX} characters")
    return trimmed


def location(value: str | None) -> str | None:
    """Trimmed, at most 300 characters, one line; blank is no location."""
    if value is None:
        return None
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if len(trimmed) > LOCATION_MAX:
        raise InvalidValue(f"must be at most {LOCATION_MAX} characters")
    return trimmed or None


def note(value: str | None) -> str | None:
    """Line breaks as LF, trimmed, at most 2,000 characters, no other
    control character; blank is no note."""
    if value is None:
        return None
    normalised = value.replace("\r\n", "\n").replace("\r", "\n")
    if not all(visible_text(line) for line in normalised.split("\n")):
        raise InvalidValue("must not contain control characters")
    trimmed = normalised.strip()
    if len(trimmed) > NOTE_MAX:
        raise InvalidValue(f"must be at most {NOTE_MAX} characters")
    return trimmed or None


def times(starts_at: datetime, ends_at: datetime) -> None:
    """The end comes 5 minutes to 24 hours after the start."""
    length = ends_at - starts_at
    if length < SHORTEST:
        raise InvalidValue("must end at least 5 minutes after it starts")
    if length > LONGEST:
        raise InvalidValue("must end at most 24 hours after it starts")


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open intervals `[start, end)` overlap (P5-A 4): back-to-back
    appointments do not."""
    return a_start < b_end and b_start < a_end
