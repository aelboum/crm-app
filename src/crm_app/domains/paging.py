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
from collections.abc import Mapping, Sequence
from datetime import datetime

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
}

Key = tuple[str | datetime | uuid.UUID | None, ...]


class InvalidCursor(ValueError):
    """The cursor is malformed or belongs to another order or filter set."""


def filter_hash(filters: Mapping[str, object]) -> str:
    """A short, stable digest of the filters a cursor was issued for."""
    canonical = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _dump(value: str | datetime | uuid.UUID | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _load(kind: str, value: object) -> str | datetime | uuid.UUID | None:
    if value is None:
        if kind == "text?":
            return None
        raise InvalidCursor
    if not isinstance(value, str):
        raise InvalidCursor
    try:
        if kind == "uuid":
            return uuid.UUID(value)
        if kind == "datetime":
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise InvalidCursor
            return parsed
    except ValueError:
        raise InvalidCursor from None
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
