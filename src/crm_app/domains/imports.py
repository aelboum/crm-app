"""CSV import rules (decision P3-F, `PHASE3-PLAN.md` §9).

Pure functions, no database or framework: decode an uploaded file, read its
header and rows with Python's `csv` module, propose or check a mapping of
fields to column positions, and turn each row into the normalised values a
record would store, or into error codes. Values are checked with the same
rules as the API (`crm_app.domains.records`), so an imported record is
exactly what a typed one would be. No formula is evaluated and no URL in the
file is fetched. Errors name a field and a code, never a cell's value.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from crm_app.domains import records as values

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 100
MAX_CELL = 4096
BOM = "﻿"

ENTITIES = ("contact", "company")

# The fields an import can fill, in the order a mapping lists them (P3-F 2).
FIELDS: dict[str, tuple[str, ...]] = {
    "contact": (
        "first_name",
        "last_name",
        "email",
        "phone",
        "job_title",
        "city",
        "lifecycle_stage",
    ),
    "company": ("name", "domain", "website", "phone", "industry", "city", "country_code"),
}

# Header names that propose a field, after normalising (lower case, any run
# of other characters as `_`).
_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "contact": {
        "first_name": ("first_name", "firstname", "first", "given_name"),
        "last_name": ("last_name", "lastname", "last", "surname", "family_name"),
        "email": ("email", "e_mail", "email_address", "mail"),
        "phone": ("phone", "telephone", "phone_number", "mobile", "tel"),
        "job_title": ("job_title", "title", "position", "role"),
        "city": ("city", "town"),
        "lifecycle_stage": ("lifecycle_stage", "stage", "lifecycle"),
    },
    "company": {
        "name": ("name", "company", "company_name", "organisation", "organization"),
        "domain": ("domain", "company_domain"),
        "website": ("website", "url", "web", "homepage"),
        "phone": ("phone", "telephone", "phone_number", "tel"),
        "industry": ("industry", "sector"),
        "city": ("city", "town"),
        "country_code": ("country_code", "country"),
    },
}
_REQUIRED: dict[str, str] = {"contact": "first_name", "company": "name"}
_HEADER = re.compile(r"[^a-z0-9]+")


def _stage(value: str | None) -> str | None:
    return None if value is None else values.stage(value.strip().lower())


_RULES: dict[str, Callable[[str | None], object]] = {
    "first_name": lambda v: values.text(v, values.NAME_MAX, required=True),
    "last_name": lambda v: values.text(v, values.NAME_MAX),
    "email": values.email,
    "phone": values.phone,
    "job_title": lambda v: values.text(v, values.JOB_TITLE_MAX),
    "city": lambda v: values.text(v, values.CITY_MAX),
    "lifecycle_stage": _stage,
    "name": lambda v: values.text(v, values.NAME_MAX, required=True),
    "domain": values.domain,
    "website": values.website,
    "industry": lambda v: values.text(v, values.INDUSTRY_MAX),
    "country_code": values.country_code,
}


class ImportFileError(ValueError):
    """The file as a whole cannot be imported; `code` says why."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class RowResult:
    number: int
    data: dict[str, object] | None
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def decode(body: bytes) -> str:
    """UTF-8 (a byte-order mark is allowed), else Windows-1252 (P3-F 3)."""
    if len(body) > MAX_BYTES:
        raise ImportFileError("file_too_large")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = body.decode("cp1252")
        except UnicodeDecodeError:
            raise ImportFileError("unreadable_file") from None
    text = text.removeprefix(BOM)
    if "\x00" in text:
        raise ImportFileError("unreadable_file")
    return text


def _delimiter(first_line: str) -> str:
    """Comma, or the semicolon spreadsheets use where the comma is a decimal
    separator, or a tab: whichever the header uses most."""
    counts = {delimiter: first_line.count(delimiter) for delimiter in (",", ";", "\t")}
    best = max(counts, key=lambda delimiter: counts[delimiter])
    return best if counts[best] else ","


def read(text: str) -> Table:
    """The header and the data rows, skipping blank lines. Refuses a file
    without a header or rows, or with too many columns or rows, or too long
    a cell."""
    first_line = text.split("\n", 1)[0]
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(first_line))
    rows: Iterator[list[str]] = (row for row in reader if any(cell.strip() for cell in row))
    try:
        header = next(rows, None)
        if header is None:
            raise ImportFileError("empty_file")
        if len(header) > MAX_COLUMNS:
            raise ImportFileError("too_many_columns")
        data: list[list[str]] = []
        for row in rows:
            if len(data) == MAX_ROWS:
                raise ImportFileError("too_many_rows")
            if len(row) > MAX_COLUMNS or any(len(cell) > MAX_CELL for cell in row):
                raise ImportFileError("cell_too_long")
            data.append(row)
    except csv.Error:
        raise ImportFileError("unreadable_file") from None
    if not data:
        raise ImportFileError("no_rows")
    return Table(header=[cell.strip() for cell in header], rows=data)


def propose(entity: str, header: Sequence[str]) -> dict[str, int]:
    """A field-to-column mapping from the header names; each column and each
    field at most once."""
    mapping: dict[str, int] = {}
    for position, name in enumerate(header):
        key = _HEADER.sub("_", name.lower()).strip("_")
        for field_name, names in _ALIASES[entity].items():
            if key in names and field_name not in mapping:
                mapping[field_name] = position
                break
    return mapping


def check_mapping(entity: str, mapping: Mapping[str, int], columns: int) -> dict[str, int]:
    """A mapping is usable when it names only importable fields, each to a
    column of the file, no column twice, and the required field."""
    if any(name not in FIELDS[entity] for name in mapping):
        raise ImportFileError("unknown_field")
    if any(not 0 <= position < columns for position in mapping.values()):
        raise ImportFileError("unknown_column")
    if len(set(mapping.values())) != len(mapping):
        raise ImportFileError("column_mapped_twice")
    if _REQUIRED[entity] not in mapping:
        raise ImportFileError("required_field_unmapped")
    return dict(mapping)


def validate(entity: str, mapping: Mapping[str, int], number: int, row: Sequence[str]) -> RowResult:
    """One data row as the values a record would store, or its errors."""
    data: dict[str, object] = {}
    errors: list[dict[str, str]] = []
    for name in FIELDS[entity]:
        position = mapping.get(name)
        raw = row[position] if position is not None and position < len(row) else ""
        try:
            value = _RULES[name](raw if raw.strip() else None)
        except values.InvalidValue:
            errors.append({"field": name, "code": "invalid"})
            continue
        if value is not None:
            data[name] = value
    if errors:
        return RowResult(number=number, data=None, errors=errors)
    if entity == "contact":
        if "email" not in data and "phone" not in data:
            return RowResult(
                number=number,
                data=None,
                errors=[{"field": "email", "code": "email_or_phone_required"}],
            )
        data.setdefault("lifecycle_stage", "lead")
    if entity == "company" and "domain" not in data:
        website = data.get("website")
        derived = values.domain_from_website(website if isinstance(website, str) else None)
        if derived is not None:
            data["domain"] = derived
    return RowResult(number=number, data=data)


def unique_key(entity: str, data: Mapping[str, object]) -> str | None:
    """The value duplicates are matched on: a contact's email, a company's
    domain (both already normalised), as the partial unique indexes do."""
    key = data.get("email" if entity == "contact" else "domain")
    return key if isinstance(key, str) else None
