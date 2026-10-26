"""The contacts and companies CSV contract (slices 3E1 and 3E2;
`crm_app.domains.export`): formula protection and CSV serialization, each on
its own, then together."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from crm_app.domains.export import (
    BOM,
    COMPANY_COLUMNS,
    CONTACT_COLUMNS,
    MAX_ROWS,
    cell,
    filename,
    protect,
    to_csv,
)


def _parse(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8")
    assert text.startswith(BOM)
    return list(csv.reader(io.StringIO(text.removeprefix(BOM), newline="")))


# --- Formula protection, on its own ------------------------------------------------


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_every_formula_start_gets_a_leading_apostrophe(start: str) -> None:
    assert protect(f"{start}SUM(A1:A2)") == f"'{start}SUM(A1:A2)"


def test_phone_numbers_starting_with_plus_are_protected_too() -> None:
    assert protect("+31 6 1234 5678") == "'+31 6 1234 5678"


@pytest.mark.parametrize(
    "value", ["", "Anna", "anna@example.test", "06 1234", "a=b", "x-y", "' quoted", " =space"]
)
def test_other_values_are_unchanged(value: str) -> None:
    assert protect(value) == value


# --- Cells and CSV serialization ---------------------------------------------------


def test_cells_render_none_as_empty_and_times_as_iso_8601_utc() -> None:
    assert cell(None) == ""
    amsterdam = timezone(timedelta(hours=1))
    assert cell(datetime(2026, 10, 26, 11, 30, 5, 123, tzinfo=amsterdam)) == "2026-10-26T10:30:05Z"
    record_id = uuid.UUID("11111111-2222-4333-8444-555555555555")
    assert cell(record_id) == "11111111-2222-4333-8444-555555555555"


def test_the_file_is_utf8_with_a_bom_crlf_records_and_the_header_first() -> None:
    data = to_csv(("a", "b"), [{"a": "1", "b": "2"}])
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8") == BOM + "a,b\r\n1,2\r\n"


def test_commas_quotes_and_newlines_are_quoted_and_survive_a_round_trip() -> None:
    tricky = {
        "a": 'Jansen, "Sam"',
        "b": "line one\nline two\r\nline three",
    }
    data = to_csv(("a", "b"), [tricky])
    assert _parse(data) == [["a", "b"], ['Jansen, "Sam"', "line one\nline two\r\nline three"]]
    assert '"Jansen, ""Sam"""' in data.decode("utf-8")


def test_accented_and_non_latin_text_is_kept() -> None:
    row = {"a": "Émile Zoë", "b": "张伟 · Ελένη · Дмитрий"}
    assert _parse(to_csv(("a", "b"), [row]))[1] == ["Émile Zoë", "张伟 · Ελένη · Дмитрий"]


def test_empty_and_missing_values_become_empty_cells() -> None:
    assert _parse(to_csv(("a", "b", "c"), [{"a": None, "b": ""}]))[1] == ["", "", ""]


def test_serialization_protects_cells_and_quoting_still_applies() -> None:
    rows = [{"a": '=HYPERLINK("http://x")', "b": "+31 6 1234", "c": "-1,5"}]
    assert _parse(to_csv(("a", "b", "c"), rows))[1] == [
        '\'=HYPERLINK("http://x")',
        "'+31 6 1234",
        "'-1,5",
    ]


def test_an_empty_export_is_the_header_alone() -> None:
    data = to_csv(CONTACT_COLUMNS, [])
    assert _parse(data) == [list(CONTACT_COLUMNS)]


# --- The approved contract ----------------------------------------------------------


def test_the_contact_columns_are_exactly_the_approved_ones_in_order() -> None:
    assert CONTACT_COLUMNS == (
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
    for excluded in ("owner_user_id", "tenant_id", "version", "created_by_user_id", "notes"):
        assert excluded not in CONTACT_COLUMNS
    assert MAX_ROWS == 50_000


def test_the_filename_is_fixed_ascii_with_the_date() -> None:
    name = filename("contacts", date(2026, 10, 26))
    assert name == "contacts-2026-10-26.csv"
    assert name.isascii()
    assert filename("contacts", datetime.now(UTC).date()).startswith("contacts-")


def test_the_company_columns_are_exactly_the_approved_ones_in_order() -> None:
    assert COMPANY_COLUMNS == (
        "id",
        "name",
        "domain",
        "website",
        "phone",
        "industry",
        "city",
        "country_code",
        "created_at",
        "updated_at",
        "archived_at",
    )
    for excluded in (
        "owner_user_id",
        "tenant_id",
        "version",
        "created_by_user_id",
        "updated_by_user_id",
        "notes",
    ):
        assert excluded not in COMPANY_COLUMNS


def test_a_company_row_is_protected_and_quoted_cell_by_cell() -> None:
    company = uuid.UUID("c0000000-0000-4000-8000-000000000001")
    row = {
        "id": company,
        "name": '=Acme, "Holdings"',
        "domain": "acme.example",
        "website": "https://acme.example/?a=1,b=2",
        "phone": "+31 20 123 4567",
        "industry": "@Logistics",
        "city": "-Zürich",
        "country_code": "CH",
        "created_at": datetime(2026, 10, 26, 9, 30, tzinfo=UTC),
        "updated_at": datetime(2026, 10, 26, 11, 30, tzinfo=timezone(timedelta(hours=2))),
        "archived_at": None,
    }
    data = to_csv(COMPANY_COLUMNS, [row])
    record = data.decode("utf-8").removeprefix(BOM).split("\r\n")[1]
    assert record.startswith(
        f'{company},"\'=Acme, ""Holdings""",acme.example,"https://acme.example/?a=1,b=2",'
    )
    assert _parse(data)[1] == [
        str(company),
        '\'=Acme, "Holdings"',
        "acme.example",
        "https://acme.example/?a=1,b=2",
        "'+31 20 123 4567",
        "'@Logistics",
        "'-Zürich",
        "CH",
        "2026-10-26T09:30:00Z",
        "2026-10-26T09:30:00Z",
        "",
    ]


def test_an_empty_company_export_is_the_header_alone() -> None:
    assert _parse(to_csv(COMPANY_COLUMNS, [])) == [list(COMPANY_COLUMNS)]


def test_the_company_filename_is_fixed_ascii_with_the_date() -> None:
    assert filename("companies", date(2026, 10, 26)) == "companies-2026-10-26.csv"
