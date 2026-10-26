"""Contacts CSV export (slice 3E; `PHASE3-PLAN.md` §10, owner approval of
2026-10-26).

Drives `contact_export_probe` in fresh interpreters and checks the audit log
directly. Covers: Owner and Admin only; workspace isolation through the
path, the filters and the company names; selection and order identical to
the contact list for every filter and order; the CSV contract; the
50,000-row bound with no partial file; the per-user limit; the limiter
failing closed; and audit entries that hold counts and filter names only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
HEADER = [
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
]


def _run(integration_env: dict[str, str], tmp: Path, mode: str, **overrides: str) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        # The probe makes many list requests; this is the platform's general
        # per-path limit, not the export limit, which stays at 10.
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
        **overrides,
    }
    result = run_module("tests.integration.contact_export_probe", [mode], env, tmp, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    return _run(integration_env, tmp_path_factory.mktemp("export"), "main")


def _by_id(probe: Probe) -> dict[str, dict[str, str]]:
    header, *rows = probe["rows"]
    return {row[0]: dict(zip(header, row, strict=True)) for row in rows}


# --- Who may export --------------------------------------------------------------------


def test_only_owners_and_admins_may_export(probe: Probe) -> None:
    assert probe["roles"] == {
        "owner": 200,
        "admin": 200,
        "member": 403,
        "reader": 403,
        # Not a member of the workspace: the same 404 as an unknown one.
        "other_owner": 404,
    }
    assert probe["anonymous"] == 401


# --- Isolation ---------------------------------------------------------------------------


def test_another_workspaces_ids_and_records_never_appear(probe: Probe) -> None:
    status, rows = probe["foreign_filter"]
    assert status == 200
    assert rows == [HEADER]
    assert probe["foreign_text"] is False


def test_company_names_come_from_the_workspace_itself(probe: Probe) -> None:
    rows, ids = _by_id(probe), probe["ids"]
    assert rows[ids["sam"]]["company_id"] == ids["acme"]
    assert rows[ids["sam"]]["company_name"] == "Acme, Ltd"
    assert rows[ids["ria"]]["company_name"] == "Zeta"
    assert all(row["company_name"] != "Foreign Secret BV" for row in rows.values())


# --- Selection and order ---------------------------------------------------------------


def test_every_filter_and_order_selects_exactly_what_the_list_shows(probe: Probe) -> None:
    for label, case in probe["compared"].items():
        assert case["status"] == 200, label
        assert case["export"] == case["list"], label
        assert case["list"], label  # every case selects something


def test_the_default_is_active_records_and_the_archived_views_follow_the_list(
    probe: Probe,
) -> None:
    archived = probe["ids"]["archived"]
    compared = probe["compared"]
    assert archived not in compared["default"]["export"]
    assert compared["archived"]["export"] == [archived]
    assert archived in compared["all"]["export"]
    assert len(compared["all"]["export"]) == len(compared["default"]["export"]) + 1


def test_paging_and_unknown_parameters_are_refused(probe: Probe) -> None:
    assert probe["refused_params"] == {"cursor": 422, "limit": 422, "colour": 422}


# --- The file -------------------------------------------------------------------------


def test_the_file_follows_the_approved_contract(probe: Probe) -> None:
    headers = probe["headers"]
    assert headers["type"] == "text/csv; charset=utf-8"
    assert headers["cache"] == "no-store"
    disposition = headers["disposition"]
    assert disposition.startswith('attachment; filename="contacts-')
    assert disposition.endswith('.csv"')
    assert disposition.isascii()
    assert probe["bom_crlf"] == [True, True]
    assert probe["rows"][0] == HEADER


def test_values_are_quoted_protected_and_kept_intact(probe: Probe) -> None:
    rows, ids = _by_id(probe), probe["ids"]
    sam = rows[ids["sam"]]
    assert sam["first_name"] == "'=cmd"
    assert sam["last_name"] == 'Jansen, "Sam"'
    assert sam["phone"] == "'+31 6 1234 5678"
    assert sam["city"] == "Zoë North"
    assert rows[ids["ria"]]["job_title"] == "'-Head of sales"
    names = {row["first_name"] for row in rows.values()}
    assert {"'@home", "Émile"} <= names
    assert any(row["last_name"] == "张伟" for row in rows.values())
    anna = next(row for row in rows.values() if row["first_name"] == "Anna")
    assert anna["last_name"] == ""
    assert anna["company_id"] == anna["company_name"] == anna["archived_at"] == ""
    assert sam["created_at"].endswith("Z")
    assert len(sam["created_at"]) == len("2026-10-26T10:00:00Z")
    assert rows[ids["archived"]]["archived_at"].endswith("Z")


def test_the_stored_values_are_unchanged(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    stored = owner_connection.execute(
        "SELECT first_name, phone FROM crm_app.contact WHERE id = %s", (probe["ids"]["sam"],)
    ).fetchone()
    assert stored == ("=cmd", "+31 6 1234 5678")


# --- Bounds and limits -----------------------------------------------------------------


def test_fifty_thousand_rows_export_and_one_more_is_refused_whole(probe: Probe) -> None:
    big = probe["big"]
    assert big["exactly"] == [200, 50_000]
    status, content_type, body = big["over"]
    assert status == 413
    assert content_type.startswith("application/json")
    assert body["detail"] == {"code": "export_too_large", "max_rows": 50_000}


def test_the_eleventh_export_in_a_window_is_refused_with_retry_after(probe: Probe) -> None:
    limit = probe["limit"]
    assert limit["statuses"] == [200] * 10
    status, retry_after = limit["eleventh"]
    assert status == 429
    assert retry_after is not None
    assert int(retry_after) > 0


def test_an_unreachable_limiter_refuses_and_exports_nothing(
    integration_env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    down = _run(integration_env, tmp_path, "limiter_down", REDIS_URL="redis://127.0.0.1:1/0")
    status, retry_after = down["down"]
    assert status == 503
    assert retry_after is not None
    exported = owner_connection.execute(
        "SELECT count(*) FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contacts.exported'",
        (down["workspace"],),
    ).fetchone()
    assert exported == (0,)


# --- Audit -------------------------------------------------------------------------------


def test_exports_are_audited_with_counts_and_filter_names_only(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contacts.exported'",
        (probe["workspace"],),
    ).fetchall()
    metadata = [row[0] for row in rows]
    assert metadata
    assert all(set(entry) == {"row_count", "filter_keys"} for entry in metadata)
    assert {"filter_keys": ["q"], "row_count": 1} in metadata
    assert {"filter_keys": ["lifecycle_stage"], "row_count": 2} in metadata
    text = json.dumps(metadata)
    for value in ("Jan", "@example.test", "Acme", "=cmd", "prospect", "customer"):
        assert value not in text


def test_a_refused_export_leaves_no_audit_entry(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contacts.exported'",
        (probe["big"]["workspace"],),
    ).fetchall()
    assert [row[0] for row in rows] == [{"row_count": 50_000, "filter_keys": []}]
