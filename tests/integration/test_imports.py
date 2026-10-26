"""CSV import preview (decision P3-F; `crm_app.api.imports`).

Drives `import_probe` in a fresh interpreter and checks the database
directly. Covers: Owner and Admin only; another workspace's import is
unreachable; the upload's type, size and mapping are checked; rows are
validated like the API, duplicates of records and of earlier rows are
found, formulas stay text; nothing is created by a preview; the error
report names rows, fields and codes only; the preview limit; the
retention entry; audit entries with counts only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("imports")
    result = run_module("tests.integration.import_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_only_owners_and_admins_may_import(probe: Probe) -> None:
    assert probe["roles"] == {"admin": 201, "member": 403, "reader": 403, "other_owner": 404}
    assert probe["anonymous"] == 401
    assert probe["member_get"] == 403


def test_the_upload_is_checked_before_anything_is_staged(probe: Probe) -> None:
    refused = probe["refused"]
    assert refused["json_body"] == 415
    assert refused["too_large"]["detail"] == {"code": "file_too_large", "max_bytes": 5242880}
    assert refused["unknown_param"] == 422
    assert refused["bad_entity"] == 422
    assert refused["bad_mapping"]["detail"] == {"code": "invalid_mapping"}
    assert refused["no_rows"]["detail"] == {"code": "no_rows"}
    assert refused["unmapped"]["detail"] == {"code": "required_field_unmapped"}


def test_rows_are_validated_and_duplicates_found(probe: Probe) -> None:
    status, preview = probe["contacts"]
    assert status == 201
    summary = preview["summary"]
    assert summary["status"] == "previewed"
    assert summary["mapping"] == {
        "first_name": 0,
        "last_name": 1,
        "email": 2,
        "phone": 3,
        "lifecycle_stage": 4,
    }
    counts = {key: summary[key] for key in ("total_rows", "valid_rows", "invalid_rows")}
    assert counts == {"total_rows": 7, "valid_rows": 3, "invalid_rows": 2}
    assert summary["duplicate_rows"] == 2
    assert summary["errors"] == [
        {"row": 2, "field": "email", "code": "invalid"},
        {"row": 3, "field": "email", "code": "email_or_phone_required"},
        {"row": 4, "field": None, "code": "duplicate"},
        {"row": 5, "field": None, "code": "duplicate"},
    ]
    assert preview["header"] == ["First name", "Last name", "E-mail", "Phone", "Stage", "Notes"]
    assert preview["sample"][0] == {
        "first_name": "Sam",
        "last_name": "Jansen",
        "email": "sam@example.test",
        "lifecycle_stage": "customer",
    }
    assert preview["sample"][1]["first_name"] == "=cmd"  # text, never evaluated
    assert preview["sample"][2]["first_name"] == "Zoë"


def test_windows_1252_and_explicit_mappings_are_read(probe: Probe) -> None:
    assert probe["cp1252"] == [
        {"first_name": "Zoë", "email": "z1252@example.test", "lifecycle_stage": "lead"}
    ]
    mapping, sample = probe["remapped"]
    assert mapping == {"first_name": 1, "email": 2}
    assert sample == [{"first_name": "Y", "email": "y@example.test", "lifecycle_stage": "lead"}]


def test_companies_get_their_domain_and_duplicates(probe: Probe) -> None:
    summary = probe["companies"]["summary"]
    assert (summary["valid_rows"], summary["invalid_rows"], summary["duplicate_rows"]) == (1, 1, 1)
    assert probe["companies"]["sample"] == [
        {
            "name": "Acme",
            "website": "https://www.acme.example",
            "country_code": "NL",
            "domain": "acme.example",
        }
    ]
    assert summary["errors"] == [
        {"row": 2, "field": None, "code": "duplicate"},
        {"row": 3, "field": "name", "code": "invalid"},
    ]


def test_a_preview_creates_nothing(probe: Probe) -> None:
    assert probe["contacts_after"] == probe["contacts_before"]


def test_imports_are_read_back_only_in_their_workspace(probe: Probe) -> None:
    assert probe["get"]["id"] == probe["import_id"]
    assert probe["get"]["errors"] == probe["contacts"][1]["summary"]["errors"]
    assert probe["import_id"] in probe["list"]
    assert probe["foreign_get"] == 404


def test_the_error_report_names_rows_fields_and_codes_only(probe: Probe) -> None:
    report = probe["errors_csv"]
    assert report["rows"] == [
        ["row", "field", "code"],
        ["2", "email", "invalid"],
        ["3", "email", "email_or_phone_required"],
        ["4", "", "duplicate"],
        ["5", "", "duplicate"],
    ]
    assert report["type"] == "text/csv; charset=utf-8"
    assert report["cache"] == "no-store"
    assert report["disposition"].startswith('attachment; filename="import-')


def test_ten_previews_per_user_per_window(probe: Probe) -> None:
    statuses, eleventh, retry_after = probe["limit"]
    assert statuses == [201] * 10
    assert eleventh == 429
    assert retry_after is not None


def test_every_import_is_due_for_deletion_within_seven_days(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    row = owner_connection.execute(
        "SELECT workspace_id::text, due_at FROM crm_app.import_expiry WHERE import_id = %s",
        (probe["import_id"],),
    ).fetchone()
    assert row is not None
    workspace, due = row
    assert workspace == probe["workspace"]
    assert timedelta(days=6, hours=23) < due - datetime.now(UTC) <= timedelta(days=7)


def test_staged_rows_hold_values_or_codes_and_audit_holds_counts(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT row_number, status, data IS NOT NULL, errors IS NOT NULL FROM crm_app.import_row"
        " WHERE import_id = %s ORDER BY row_number",
        (probe["import_id"],),
    ).fetchall()
    assert rows == [
        (1, "valid", True, False),
        (2, "invalid", False, True),
        (3, "invalid", False, True),
        (4, "duplicate", True, False),
        (5, "duplicate", True, False),
        (6, "valid", True, False),
        (7, "valid", True, False),
    ]
    audit = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE action = 'crm_app.import.previewed'"
        " AND resource_id = %s",
        (probe["import_id"],),
    ).fetchall()
    assert [entry for (entry,) in audit] == [
        {
            "entity": "contact",
            "total_rows": 7,
            "valid_rows": 3,
            "invalid_rows": 2,
            "duplicate_rows": 2,
        }
    ]
