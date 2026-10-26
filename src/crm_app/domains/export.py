"""CSV export of contacts (`PHASE3-PLAN.md` §10, slice 3E; owner approval of
2026-10-26).

Two separate steps, so each is tested on its own:

1. `protect`: a cell that a spreadsheet would read as a formula (it starts
   with `=`, `+`, `-`, `@`, a tab or a carriage return) gets a leading `'`.
   Phone numbers such as `+31…` are protected too, by decision.
2. `to_csv`: the standard `csv` module with minimal quoting and CRLF record
   endings, encoded as UTF-8 with a byte-order mark for spreadsheets.

Pure functions; no database or framework. Stored values are never changed.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime

CONTACT_COLUMNS: tuple[str, ...] = (
    "id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "job_title",
    "city",
    "lifecycle_stage",
    "source",
    "company_id",
    "company_name",
    "created_at",
    "updated_at",
    "archived_at",
)

MAX_ROWS = 50_000
BOM = "﻿"
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def protect(value: str) -> str:
    """`value`, made inert for spreadsheets when it could start a formula."""
    return "'" + value if value.startswith(_FORMULA_START) else value


def cell(value: object) -> str:
    """One value as exported text: empty for none, ISO 8601 UTC for times."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def to_csv(columns: Sequence[str], rows: Iterable[Mapping[str, object]]) -> bytes:
    """The header and rows as CSV bytes; every cell is protected first."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([protect(cell(row.get(column))) for column in columns])
    return (BOM + buffer.getvalue()).encode("utf-8")


def filename(kind: str, today: date) -> str:
    """A fixed ASCII name, never built from user input: `contacts-2026-10-26.csv`."""
    return f"{kind}-{today.isoformat()}.csv"
