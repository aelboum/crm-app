"""Companies CSV export (slice 3E2; `PHASE3-PLAN.md` §10, decision P3-E2).

Drives `company_export_probe` in fresh interpreters and checks the audit log
directly. Covers: Owner and Admin only; workspace isolation through the
path and the owner filter; selection and order identical to the company list
for every filter and order; the CSV contract; the 50,000-row bound with no
partial file; the per-user limit, separate from the contacts export's; the
limiter failing closed; and audit entries that hold counts and filter names
only.
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
]
EXPORTED = "crm_app.companies.exported"


def _run(integration_env: dict[str, str], tmp: Path, mode: str, **overrides: str) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        # The probe makes many list requests; this is the platform's general
        # per-path limit, not the export limit, which stays at 10.
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
        **overrides,
    }
    result = run_module("tests.integration.company_export_probe", [mode], env, tmp, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    return _run(integration_env, tmp_path_factory.mktemp("company-export"), "main")


def _by_id(probe: Probe) -> dict[str, dict[str, str]]:
    header, *rows = probe["rows"]
    return {row[0]: dict(zip(header, row, strict=True)) for row in rows}


def _audit(connection: psycopg.Connection, workspace: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s AND action = %s",
        (workspace, EXPORTED),
    ).fetchall()
    return [row[0] for row in rows]


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


def test_another_workspaces_owner_ids_and_records_never_appear(probe: Probe) -> None:
    status, rows = probe["foreign_owner"]
    assert status == 200
    assert rows == [HEADER]
    assert probe["foreign_text"] is False


# --- Selection and order ---------------------------------------------------------------


def test_every_filter_and_order_selects_exactly_what_the_list_shows(probe: Probe) -> None:
    for label, case in probe["compared"].items():
        assert case["status"] == 200, label
        assert case["export"] == case["list"], label
        assert case["list"], label  # every case selects something


def test_search_matches_names_and_domains_as_the_list_does(probe: Probe) -> None:
    ids, compared = probe["ids"], probe["compared"]
    assert compared["search_name"]["export"] == [ids["zeta"]]
    assert compared["search_domain"]["export"] == [ids["acme"]]
    assert set(compared["owner_me"]["export"]) == {ids["acme"], ids["zeta"]}
    assert compared["owner_id"]["export"] == compared["owner_me"]["export"]
    assert compared["combined"]["export"] == [ids["zeta"]]


def test_the_default_is_active_records_and_the_archived_views_follow_the_list(
    probe: Probe,
) -> None:
    archived = probe["ids"]["archived"]
    compared = probe["compared"]
    assert archived not in compared["default"]["export"]
    assert compared["archived"]["export"] == [archived]
    assert archived in compared["all"]["export"]
    assert len(compared["all"]["export"]) == len(compared["default"]["export"]) + 1


def test_the_orders_differ_and_reverse(probe: Probe) -> None:
    compared = probe["compared"]
    for order in ("name", "created", "updated"):
        ascending = compared[f"{order}_asc"]["export"]
        assert compared[f"{order}_desc"]["export"] == ascending[::-1], order
    assert compared["created_asc"]["export"] != compared["updated_asc"]["export"]


def test_an_empty_result_is_the_header_alone(probe: Probe) -> None:
    assert probe["empty"] == [200, [HEADER]]


def test_paging_contact_filters_and_unknown_parameters_are_refused(probe: Probe) -> None:
    assert probe["refused_params"] == {
        "cursor": 422,
        "limit": 422,
        "colour": 422,
        "company_id": 422,
        "lifecycle_stage": 422,
        "archived": 422,
        "sort": 422,
    }
    status, body = probe["bad_owner"]
    assert status == 422
    assert body["detail"] == {"code": "invalid_owner_filter"}


# --- The file -------------------------------------------------------------------------


def test_the_file_follows_the_approved_contract(probe: Probe) -> None:
    headers = probe["headers"]
    assert headers["type"] == "text/csv; charset=utf-8"
    assert headers["cache"] == "no-store"
    disposition = headers["disposition"]
    assert disposition.startswith('attachment; filename="companies-')
    assert disposition.endswith('.csv"')
    assert disposition.isascii()
    assert probe["bom_crlf"] == [True, True]
    assert probe["rows"][0] == HEADER


def test_values_are_quoted_protected_and_kept_intact(probe: Probe) -> None:
    rows, ids = _by_id(probe), probe["ids"]
    acme = rows[ids["acme"]]
    assert acme["name"] == '\'=Acme, "Holdings"'
    assert acme["domain"] == "acme.example"
    assert acme["website"] == "https://acme.example/?a=1,b=2"
    assert acme["phone"] == "'+31 20 123 4567"
    assert acme["industry"] == "'@Logistics"
    assert acme["city"] == "Zoë North"
    assert acme["country_code"] == "NL"
    emile = rows[ids["emile"]]
    assert emile["name"] == "Émile Bakkerij"
    assert emile["industry"] == "'-Food"
    assert emile["city"] == "Utrecht"
    assert emile["domain"] == emile["website"] == emile["phone"] == emile["archived_at"] == ""
    assert acme["created_at"].endswith("Z")
    assert len(acme["created_at"]) == len("2026-10-26T10:00:00Z")
    assert rows[ids["archived"]]["archived_at"].endswith("Z")
    for excluded in ("owner_user_id", "tenant_id", "version", "created_by_user_id"):
        assert excluded not in probe["rows"][0]


def test_the_stored_values_are_unchanged(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    stored = owner_connection.execute(
        "SELECT name, phone, industry FROM crm_app.company WHERE id = %s", (probe["ids"]["acme"],)
    ).fetchone()
    assert stored == ('=Acme, "Holdings"', "+31 20 123 4567", "@Logistics")


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


def test_contacts_and_companies_have_separate_budgets(probe: Probe) -> None:
    limit = probe["limit"]
    # Companies spent: contacts still open, and the other way round.
    assert limit["contacts_after_companies"] == 200
    assert limit["contacts_spent"] == [200] * 10
    assert limit["contacts_eleventh"] == 429
    assert limit["companies_after_contacts"] == 200


def test_an_unreachable_limiter_refuses_and_exports_nothing(
    integration_env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    down = _run(integration_env, tmp_path, "limiter_down", REDIS_URL="redis://127.0.0.1:1/0")
    status, retry_after = down["down"]
    assert status == 503
    assert retry_after is not None
    assert _audit(owner_connection, down["workspace"]) == []


# --- Audit -------------------------------------------------------------------------------


def test_exports_are_audited_with_counts_and_filter_names_only(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    metadata = _audit(owner_connection, probe["workspace"])
    assert metadata
    assert all(set(entry) == {"row_count", "filter_keys"} for entry in metadata)
    assert {"filter_keys": ["q"], "row_count": 1} in metadata
    assert {"filter_keys": ["owner"], "row_count": 2} in metadata
    assert {"filter_keys": ["archived", "owner", "q", "sort"], "row_count": 1} in metadata
    text = json.dumps(metadata)
    for value in ("ZE", "acme", "Acme", "=Acme", "Logistics", probe["ids"]["me"], "nothing"):
        assert value not in text
    resources = owner_connection.execute(
        "SELECT DISTINCT resource_type FROM core.audit_log WHERE tenant_id = %s AND action = %s",
        (probe["workspace"], EXPORTED),
    ).fetchall()
    assert resources == [("crm_app.company",)]


def test_a_refused_export_leaves_no_audit_entry(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    assert _audit(owner_connection, probe["big"]["workspace"]) == [
        {"row_count": 50_000, "filter_keys": []}
    ]
