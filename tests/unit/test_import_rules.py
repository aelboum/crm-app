"""CSV import rules (decision P3-F; `crm_app.domains.imports`): decoding,
reading, mapping and row validation, without a database."""

from __future__ import annotations

import pytest

from crm_app.domains import imports as rules
from tests.support import REPO_ROOT

MIGRATION = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0009_imports.py"


# --- Decoding and reading ------------------------------------------------------------


def test_utf8_with_or_without_a_bom_and_windows_1252_are_read() -> None:
    assert rules.decode("first_name\nZoë\n".encode()) == "first_name\nZoë\n"
    assert rules.decode(b"\xef\xbb\xbffirst_name\n") == "first_name\n"
    assert rules.decode("first_name\nZoë\n".encode("cp1252")) == "first_name\nZoë\n"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"x" * (rules.MAX_BYTES + 1), "file_too_large"),
        (b"\x81\x8d\x8f\x90\x9d", "unreadable_file"),  # not UTF-8, undefined in cp1252
        (b"first_name\x00\nSam\n", "unreadable_file"),
    ],
    ids=["too-large", "undecodable", "nul"],
)
def test_unreadable_or_oversized_files_are_refused(body: bytes, code: str) -> None:
    with pytest.raises(rules.ImportFileError) as refused:
        rules.decode(body)
    assert refused.value.code == code


def test_the_header_and_rows_are_read_skipping_blank_lines() -> None:
    table = rules.read('first_name,email\n\nSam,sam@example.test\n"Ann, Jr.",ann@example.test\n')
    assert table.header == ["first_name", "email"]
    assert table.rows == [["Sam", "sam@example.test"], ["Ann, Jr.", "ann@example.test"]]


def test_semicolons_and_tabs_are_recognised() -> None:
    assert rules.read("first_name;email\nSam;s@x.test\n").rows == [["Sam", "s@x.test"]]
    assert rules.read("first_name\temail\nSam\ts@x.test\n").rows == [["Sam", "s@x.test"]]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "empty_file"),
        ("first_name\n", "no_rows"),
        (",".join(f"c{n}" for n in range(101)) + "\nx\n", "too_many_columns"),
        ("first_name\n" + "Sam\n" * (rules.MAX_ROWS + 1), "too_many_rows"),
        ("first_name\n" + "x" * (rules.MAX_CELL + 1) + "\n", "cell_too_long"),
    ],
    ids=["empty", "header-only", "columns", "rows", "cell"],
)
def test_files_outside_the_limits_are_refused(text: str, code: str) -> None:
    with pytest.raises(rules.ImportFileError) as refused:
        rules.read(text)
    assert refused.value.code == code


def test_exactly_ten_thousand_rows_are_accepted() -> None:
    assert len(rules.read("first_name\n" + "Sam\n" * rules.MAX_ROWS).rows) == rules.MAX_ROWS


# --- Mapping ---------------------------------------------------------------------------


def test_a_mapping_is_proposed_from_header_names() -> None:
    header = ["First Name", "Surname", "E-mail", "Mobile", "Notes", "Stage"]
    assert rules.propose("contact", header) == {
        "first_name": 0,
        "last_name": 1,
        "email": 2,
        "phone": 3,
        "lifecycle_stage": 5,
    }
    assert rules.propose("company", ["Company", "Web", "Country"]) == {
        "name": 0,
        "website": 1,
        "country_code": 2,
    }


@pytest.mark.parametrize(
    ("mapping", "code"),
    [
        ({"first_name": 0, "notes": 1}, "unknown_field"),
        ({"first_name": 5}, "unknown_column"),
        ({"first_name": 0, "email": 0}, "column_mapped_twice"),
        ({"email": 1}, "required_field_unmapped"),
    ],
)
def test_unusable_mappings_are_refused(mapping: dict[str, int], code: str) -> None:
    with pytest.raises(rules.ImportFileError) as refused:
        rules.check_mapping("contact", mapping, 3)
    assert refused.value.code == code


# --- Rows ------------------------------------------------------------------------------

CONTACT = {"first_name": 0, "last_name": 1, "email": 2, "phone": 3, "lifecycle_stage": 4}


def test_a_contact_row_is_normalised_like_the_api_does() -> None:
    row = [" Sam ", "", " SAM@Example.TEST ", "", "Customer"]
    result = rules.validate("contact", CONTACT, 1, row)
    assert result.valid
    assert result.data == {
        "first_name": "Sam",
        "email": "sam@example.test",
        "lifecycle_stage": "customer",
    }


def test_the_stage_defaults_to_lead() -> None:
    result = rules.validate("contact", CONTACT, 1, ["Sam", "", "", "+31 6 1234 5678", ""])
    assert result.data == {
        "first_name": "Sam",
        "phone": "+31 6 1234 5678",
        "lifecycle_stage": "lead",
    }


@pytest.mark.parametrize(
    ("row", "errors"),
    [
        (["", "J", "s@x.test", "", ""], [{"field": "first_name", "code": "invalid"}]),
        (["Sam", "", "not-an-email", "", ""], [{"field": "email", "code": "invalid"}]),
        (
            ["Sam", "", "s@x.test", "", "patient"],
            [{"field": "lifecycle_stage", "code": "invalid"}],
        ),
        (["Sam", "", "", "", ""], [{"field": "email", "code": "email_or_phone_required"}]),
    ],
)
def test_refused_rows_name_the_field_and_code_never_the_value(
    row: list[str], errors: list[dict[str, str]]
) -> None:
    result = rules.validate("contact", CONTACT, 7, row)
    assert result.number == 7
    assert result.data is None
    assert result.errors == errors


def test_a_formula_is_kept_as_text_and_never_evaluated() -> None:
    result = rules.validate("contact", CONTACT, 1, ["=HYPERLINK(1)", "", "s@x.test", "", ""])
    assert result.data is not None
    assert result.data["first_name"] == "=HYPERLINK(1)"


def test_a_short_row_reads_missing_cells_as_empty() -> None:
    result = rules.validate("contact", CONTACT, 1, ["Sam", "Jansen", "s@x.test"])
    assert result.data == {
        "first_name": "Sam",
        "last_name": "Jansen",
        "email": "s@x.test",
        "lifecycle_stage": "lead",
    }


def test_a_companys_domain_is_derived_from_its_website() -> None:
    mapping = {"name": 0, "website": 1, "country_code": 2}
    result = rules.validate("company", mapping, 1, ["Acme", "https://www.Acme.example/x", "nl"])
    assert result.data == {
        "name": "Acme",
        "website": "https://www.Acme.example/x",
        "country_code": "NL",
        "domain": "acme.example",
    }
    refused = rules.validate("company", mapping, 2, ["Acme", "javascript:alert(1)", ""])
    assert refused.errors == [{"field": "website", "code": "invalid"}]


def test_duplicates_are_matched_on_email_or_domain() -> None:
    assert rules.unique_key("contact", {"email": "s@x.test"}) == "s@x.test"
    assert rules.unique_key("contact", {"phone": "+31"}) is None
    assert rules.unique_key("company", {"domain": "acme.example"}) == "acme.example"


def test_the_migration_checks_the_same_row_limit() -> None:
    assert f"MAX_ROWS = {rules.MAX_ROWS:_}" in MIGRATION.read_text(encoding="utf-8")
