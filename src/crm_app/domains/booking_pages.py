"""Pure rules for booking pages and the free times they offer (decision
P5-C, migration 0016).

Each validating function returns the value as the database stores it, or
raises `InvalidValue`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import datetime, timedelta

from crm_app.domains import appointments as appointment_rules
from crm_app.domains import records as record_rules
from crm_app.domains.records import InvalidValue, visible_text

NAME_MAX = 120
DESCRIPTION_MAX = 1000
LENGTHS = (15, 30, 45, 60, 90, 120)
STEPS = (15, 30, 60)
NOTICE_MAX = 7 * 24 * 60
HORIZON_MAX = 90
STATUSES = ("draft", "published")
DEFAULT_LENGTH = 30
DEFAULT_STEP = 30
DEFAULT_KIND = "video"
DEFAULT_NOTICE = 4 * 60
DEFAULT_HORIZON = 30
MAX_PAGES = 50
# The widest range of free times one request asks for (P5-C 4).
TIMES_RANGE_MAX = timedelta(days=14)
TIMES_MAX = 2000
# Upcoming bookings one contact may hold on one page (P5-C 6).
UPCOMING_PER_CONTACT = 3
VISITOR_MESSAGE_MAX = 1000
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
# All control characters but line feed.
_MULTILINE_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def name(value: str) -> str:
    """Trimmed, 1..120 characters, no control, format or separator characters."""
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > NAME_MAX:
        raise InvalidValue(f"must be at most {NAME_MAX} characters")
    return trimmed


def multiline(value: str | None, maximum: int) -> str | None:
    """Line breaks as LF, trimmed, at most `maximum` characters, no other
    control character; blank is none."""
    if value is None:
        return None
    normalised = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if _MULTILINE_CONTROL.search(normalised):
        raise InvalidValue("must not contain control characters")
    if len(normalised) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return normalised or None


def description(value: str | None) -> str | None:
    return multiline(value, DESCRIPTION_MAX)


def choice(value: int, allowed: Sequence[int]) -> int:
    if value not in allowed:
        raise InvalidValue(f"must be one of {', '.join(str(v) for v in allowed)}")
    return value


def bounded(value: int, low: int, high: int) -> int:
    if not low <= value <= high:
        raise InvalidValue(f"must be between {low} and {high}")
    return value


class InvalidVisitor(ValueError):
    """The visitor's details the page refuses: a rule per field name, never
    what the visitor typed."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("invalid visitor details")
        self.errors = errors


def _visitor_name(value: str | None, *, required: bool) -> str | None:
    if value is not None and not visible_text(value):
        raise InvalidValue("must not contain control characters")
    return record_rules.text(value, record_rules.NAME_MAX, required=required)


def visitor(
    first_name: str | None,
    last_name: str | None,
    email: str | None,
    phone: str | None,
    message: str | None,
) -> dict[str, str | None]:
    """The visitor's details as the contact and the appointment store them
    (P5-C 1): a first name and an email are required."""
    checks = {
        "first_name": lambda: _visitor_name(first_name, required=True),
        "last_name": lambda: _visitor_name(last_name, required=False),
        "email": lambda: record_rules.email(email),
        "phone": lambda: record_rules.phone(phone),
        "message": lambda: multiline(message, VISITOR_MESSAGE_MAX),
    }
    given: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    for key, check in checks.items():
        try:
            given[key] = check()
        except InvalidValue:
            errors[key] = "invalid"
    if "email" not in errors and given["email"] is None:
        errors["email"] = "required"
    if errors:
        raise InvalidVisitor(errors)
    return given


def title(page_name: str, visitor: str) -> str:
    """The appointment's title: "page name — visitor's name", shortened to
    the appointment's limit (P5-C 6)."""
    full = f"{page_name} — {visitor}"
    if len(full) <= appointment_rules.TITLE_MAX:
        return full
    return full[: appointment_rules.TITLE_MAX - 1].rstrip() + "…"


def free_times(  # noqa: PLR0913 - the open time, then what narrows it
    open_intervals: Sequence[tuple[datetime, datetime]],
    busy: Sequence[tuple[datetime, datetime]],
    *,
    length: timedelta,
    step: timedelta,
    earliest: datetime,
    latest: datetime,
) -> list[datetime]:
    """Start times on the step grid from each interval's opening, with the
    whole appointment inside the interval, not before `earliest`, not after
    `latest`, and overlapping nothing in `busy` (P5-C 4). Ordered, at most
    `TIMES_MAX`."""
    found: list[datetime] = []
    for opens, closes in open_intervals:
        start = opens
        while start + length <= closes and start <= latest:
            end = start + length
            if start >= earliest and not any(
                appointment_rules.overlaps(start, end, b_start, b_end) for b_start, b_end in busy
            ):
                found.append(start)
                if len(found) >= TIMES_MAX:
                    return found
            start += step
    return found


def token_hash(token: str) -> str | None:
    """The stored form of a visitor's link token, or `None` for one that
    could never have been issued (`secrets.token_urlsafe(32)`)."""
    if not _TOKEN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()
