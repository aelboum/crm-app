"""List cursors (`PHASE3-PLAN.md` §19.5).

A cursor is URL-safe base64 of a small JSON object: a format version, the
order, the direction, a hash of the filters, and the last row's order key.
Parsing is strict: anything that is not exactly what `encode` produces for
the same order, direction and filters is `InvalidCursor`, which the API
answers with 400.

Cursors are not signed. Row-Level Security and the workspace predicate
confine every query to the caller's workspace, so a forged cursor can only
skip within rows the caller may already read.

Pure functions; no database or framework.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURSOR_MAX = 1024
_FORMAT = 1
_KEYS = {"v", "s", "d", "f", "k"}

# What each order's key holds, in order; the last is always the row ID.
# "text?" is nullable text (a contact's last name, which sorts last ascending).
ORDER_KEYS: Mapping[str, Mapping[str, Sequence[str]]] = {
    "contact": {
        "name": ("text?", "text", "uuid"),
        "created_at": ("datetime", "uuid"),
        "updated_at": ("datetime", "uuid"),
    },
    "company": {
        "name": ("text", "uuid"),
        "created_at": ("datetime", "uuid"),
        "updated_at": ("datetime", "uuid"),
    },
    # A record's history and notes, newest first (`PHASE3-PLAN.md` §21).
    "activity": {"occurred_at": ("datetime", "uuid")},
    "note": {"created_at": ("datetime", "uuid")},
    # Deals (decision P4-B 10). "decimal?" and "date?" are nullable and sort
    # last ascending; a deal's history is ordered by its sequence number.
    "opportunity": {
        "updated_at": ("datetime", "uuid"),
        "created_at": ("datetime", "uuid"),
        "title": ("text", "uuid"),
        "amount": ("decimal?", "uuid"),
        "expected_close_date": ("date?", "uuid"),
    },
    "opportunity_event": {"seq": ("int",)},
}

Value = str | datetime | date | Decimal | int | uuid.UUID | None
Key = tuple[Value, ...]


class InvalidCursor(ValueError):
    """The cursor is malformed or belongs to another order or filter set."""


def filter_hash(filters: Mapping[str, object]) -> str:
    """A short, stable digest of the filters a cursor was issued for."""
    canonical = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _dump(value: Value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise InvalidCursor
    return parsed


def _finite(value: str) -> Decimal:
    number = Decimal(value)
    if not number.is_finite():
        raise InvalidCursor
    return number


def _count(value: str) -> int:
    if not value.isascii() or not value.isdigit() or len(value) > 19:
        raise InvalidCursor
    return int(value)


# How each non-text key type is read back; text is checked in `_load`.
_PARSERS: Mapping[str, Callable[[str], Value]] = {
    "uuid": uuid.UUID,
    "datetime": _aware,
    "date?": date.fromisoformat,
    "decimal?": _finite,
    "int": _count,
}


def _load(kind: str, value: object) -> Value:
    if value is None:
        if kind.endswith("?"):
            return None
        raise InvalidCursor
    if not isinstance(value, str):
        raise InvalidCursor
    parser = _PARSERS.get(kind)
    if parser is not None:
        try:
            return parser(value)
        except (ValueError, InvalidOperation):
            raise InvalidCursor from None
    if "\x00" in value:
        raise InvalidCursor
    return value


def encode(record_kind: str, order: str, direction: str, filters: str, key: Key) -> str:
    kinds = ORDER_KEYS[record_kind][order]
    payload = {
        "v": _FORMAT,
        "s": order,
        "d": direction,
        "f": filters,
        "k": [_dump(v) for _, v in zip(kinds, key, strict=True)],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(cursor: str, record_kind: str, order: str, direction: str, filters: str) -> Key:
    """The order key of the row after which the next page starts."""
    if not cursor or len(cursor) > CURSOR_MAX:
        raise InvalidCursor
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
    except (binascii.Error, ValueError):
        raise InvalidCursor from None
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        raise InvalidCursor
    if (payload["v"], payload["s"], payload["d"], payload["f"]) != (
        _FORMAT,
        order,
        direction,
        filters,
    ):
        raise InvalidCursor
    kinds = ORDER_KEYS[record_kind][order]
    values = payload["k"]
    if not isinstance(values, list) or len(values) != len(kinds):
        raise InvalidCursor
    return tuple(_load(k, v) for k, v in zip(kinds, values, strict=True))
