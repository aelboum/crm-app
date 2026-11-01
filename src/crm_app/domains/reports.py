"""Report periods (decision P10-A): pure rules, no database or framework.

A period is a range of whole calendar days in the workspace's time zone,
both ends included, at most `MAX_DAYS` long. Its comparison period is the
same number of days immediately before it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_DAYS = 366


class InvalidPeriod(ValueError):
    """A period the rules refuse; the message names the rule."""


@dataclass(frozen=True)
class Period:
    """The instants a report counts: `[since, until)` and the comparison
    period `[previous_since, since)`, all in UTC."""

    start: date
    end: date
    since: datetime
    until: datetime
    previous_since: datetime

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tzinfo=zone).astimezone(UTC)


def period(start: date, end: date, time_zone: str) -> Period:
    """The period from `start` to `end`, both included, in `time_zone`."""
    if end < start:
        raise InvalidPeriod("the end must not be before the start")
    if start.year < 1900 or end.year > 2999:
        raise InvalidPeriod("a period lies between the years 1900 and 2999")
    days = (end - start).days + 1
    if days > MAX_DAYS:
        raise InvalidPeriod(f"a period is at most {MAX_DAYS} days")
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return Period(
        start=start,
        end=end,
        since=_midnight(start, zone),
        until=_midnight(end + timedelta(days=1), zone),
        previous_since=_midnight(start - timedelta(days=days), zone),
    )


def where(instant: datetime | None, chosen: Period) -> str | None:
    """`"current"`, `"previous"` or `None` for an instant outside both."""
    if instant is None or instant < chosen.previous_since or instant >= chosen.until:
        return None
    return "current" if instant >= chosen.since else "previous"
