"""Custom field rules (decision P3-D, migration 0008).

Pure functions: each takes what a client sent and returns the one form that
is stored, or raises `InvalidValue`. Definitions (key, label, options) and
record values (by type) are both checked here, so the API and the service
agree. Messages name the rule, never the value: they reach responses.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import date

from crm_app.domains.records import InvalidValue, visible_text

ENTITIES = ("contact", "company")
FIELD_TYPES = ("text", "number", "date", "boolean", "select")
LABEL_MAX = 60
OPTION_MAX = 60
OPTIONS_MAX = 50
TEXT_MAX = 500
NUMBER_DIGITS = 15
NUMBER_LIMIT = 10**15
MAX_ACTIVE = 50  # per entity per workspace (P3-D 3)
VALUES_MAX_BYTES = 32_768  # a record's values as JSON (migration 0008)

_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def key(value: str) -> str:
    """A machine name: a lower-case letter, then letters, digits or `_`."""
    if not _KEY.fullmatch(value):
        raise InvalidValue("must be a lower-case letter followed by letters, digits or _")
    return value


def _short_text(value: str, maximum: int) -> str:
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return trimmed


def label(value: str) -> str:
    return _short_text(value, LABEL_MAX)


def options(values: Sequence[str]) -> list[str]:
    """A select's options: 1-50, each 1-60 characters, distinct regardless
    of case, in the given order."""
    cleaned = [_short_text(value, OPTION_MAX) for value in values]
    if not 1 <= len(cleaned) <= OPTIONS_MAX:
        raise InvalidValue(f"must have 1 to {OPTIONS_MAX} options")
    if len({option.casefold() for option in cleaned}) != len(cleaned):
        raise InvalidValue("must not repeat an option")
    return cleaned


def _number(raw: object) -> int | float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise InvalidValue("must be a number")
    if isinstance(raw, float) and not math.isfinite(raw):
        raise InvalidValue("must be a finite number")
    if abs(raw) >= NUMBER_LIMIT:
        raise InvalidValue("must be smaller than 10^15")
    if isinstance(raw, float):
        # More digits than a decimal of 15 significant digits can carry.
        if float(f"{raw:.{NUMBER_DIGITS}g}") != raw:
            raise InvalidValue(f"must have at most {NUMBER_DIGITS} significant digits")
        if raw.is_integer():
            return int(raw)
    return raw


def _date(raw: object) -> str:
    if not isinstance(raw, str) or not _DATE.fullmatch(raw):
        raise InvalidValue("must be a date as YYYY-MM-DD")
    try:
        date.fromisoformat(raw)
    except ValueError:
        raise InvalidValue("must be a real date") from None
    return raw


def value(field_type: str, choices: Sequence[str] | None, raw: object) -> object:
    """A record's value for a field of `field_type`, as stored. `None`
    clears the field; so does empty text."""
    if raw is None:
        return None
    match field_type:
        case "text":
            if not isinstance(raw, str):
                raise InvalidValue("must be text")
            if not visible_text(raw):
                raise InvalidValue("must be one line without control characters")
            trimmed = raw.strip()
            if len(trimmed) > TEXT_MAX:
                raise InvalidValue(f"must be at most {TEXT_MAX} characters")
            return trimmed or None
        case "number":
            return _number(raw)
        case "date":
            return _date(raw)
        case "boolean":
            if not isinstance(raw, bool):
                raise InvalidValue("must be true or false")
            return raw
        case "select":
            if not isinstance(raw, str) or raw not in (choices or ()):
                raise InvalidValue("must be one of the field's options")
            return raw
        case _:
            raise InvalidValue("has an unknown type")
