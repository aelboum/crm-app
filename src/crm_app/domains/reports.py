"""Report periods (decision P10-A): pure rules, no database or framework.

A period is a range of whole calendar days in the workspace's time zone,
both ends included, at most `MAX_DAYS` long. Its comparison period is the
same number of days immediately before it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_DAYS = 366
# A report as CSV (decision P10-B): one row per figure.
CSV_COLUMNS: tuple[str, ...] = ("section", "item", "value", "previous")
# What names an entry of a breakdown list, and what it counts, in order.
_ITEM_KEYS = ("source", "status", "user_id", "currency")
_VALUE_KEYS = ("count", "amount", "won")


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


def _first(entry: Mapping[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in entry:
            return entry[key]
    return None


def csv_rows(report: Mapping[str, Any]) -> list[dict[str, object]]:
    """A report's figures as rows (decision P10-B): the period first, then
    each figure with its comparison value (`<name>_before`), then each
    breakdown entry (`section` the list, `item` what it is about). Only
    counts, rates, amounts and member ids: never a record's contents."""
    period = report["period"]
    rows: list[dict[str, object]] = [
        {"section": "period", "item": "start", "value": period["start"], "previous": ""},
        {"section": "period", "item": "end", "value": period["end"], "previous": ""},
        {"section": "period", "item": "days", "value": period["days"], "previous": ""},
        {"section": "period", "item": "capped", "value": report["capped"], "previous": ""},
    ]
    for name, value in report.items():
        if name in ("period", "capped") or name.endswith("_before"):
            continue
        if isinstance(value, list):
            for entry in value:
                rows.append(
                    {
                        "section": name,
                        "item": _first(entry, _ITEM_KEYS),
                        "value": _first(entry, _VALUE_KEYS),
                        "previous": "",
                    }
                )
            continue
        previous = report.get(f"{name}_before", "")
        rows.append({"section": "total", "item": name, "value": value, "previous": previous})
    return rows


def where(instant: datetime | None, chosen: Period) -> str | None:
    """`"current"`, `"previous"` or `None` for an instant outside both."""
    if instant is None or instant < chosen.previous_since or instant >= chosen.until:
        return None
    return "current" if instant >= chosen.since else "previous"
