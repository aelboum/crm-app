"""The contact and company routes (slice 3A, `PHASE3-PLAN.md` §19).

Drives `record_route_probe` in a fresh interpreter against the integration
database, then checks the audit trail as the owner connection. Covers the
role matrix (Q6, P3-A), workspace isolation (§19.3), mass assignment and
validation (§19.6), duplicates including a concurrent pair (§19.4),
versions, idempotency, archive and restore, links, owners, and a deleted
workspace.
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


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    cwd: Path = tmp_path_factory.mktemp("records")
    result = run_module("tests.integration.record_route_probe", [], env, cwd, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


EDIT = {"create": 201, "read": 200, "update": 200, "archive": 200, "restore": 200}


def test_owners_and_admins_may_do_everything(probe: Probe) -> None:
    for role in ("Owner", "Admin"):
        assert probe["matrix"][role] == {
            **EDIT,
            "delete": 204,
            "company_create": 201,
            "company_delete": 204,
        }, role


def test_members_edit_archive_and_restore_but_never_delete(probe: Probe) -> None:
    assert probe["matrix"]["Member"] == {
        **EDIT,
        "delete": 403,
        "company_create": 201,
        "company_delete": 403,
    }


def test_read_only_members_only_read(probe: Probe) -> None:
    assert probe["matrix"]["Read-only"] == {
        "create": 403,
        "read": 200,
        "update": 403,
        "archive": 403,
        "restore": 403,
        "delete": 403,
        "company_create": 403,
        "company_delete": 403,
    }


def test_other_workspaces_and_outsiders_see_the_same_404_and_change_nothing(
    probe: Probe,
) -> None:
    cross = probe["cross"]
    for key in (
        "outsider_read",
        "other_owner_read",
        "foreign_get",
        "foreign_patch",
        "foreign_archive",
        "foreign_delete",
        "unknown_record",
    ):
        assert cross[key] == 404, key
    assert cross["anonymous_read"] == 401
    assert cross["after"]["version"] == 1
    assert cross["after"]["city"] is None
    assert cross["after"]["archived_at"] is None


def test_system_fields_and_reserved_sources_cannot_be_set(probe: Probe) -> None:
    assert probe["refused_fields"] == dict.fromkeys(
        ("tenant_id", "id", "version", "archived_at", "created_by_user_id", "source"), 422
    )


def test_validation_follows_p3a_and_never_echoes_values(probe: Probe) -> None:
    validation = probe["validation"]
    assert validation["no_email_or_phone"] == 422
    assert validation["bad_email"] == 422
    assert "leak-check-7f3a" not in validation["bad_email_body"]
    assert '"input"' not in validation["bad_email_body"]
    assert validation["stage_patient"] == 422
    assert validation["blank_first_name"] == 422
    assert validation["phone_only"] == 201
    assert validation["normalised"] == "mixed.case@example.test"


def test_duplicates_are_refused_with_the_existing_record(probe: Probe) -> None:
    duplicates = probe["duplicates"]
    assert duplicates["contact"] == [
        409,
        {"code": "duplicate_email", "existing_id": duplicates["taken_id"]},
    ]
    assert duplicates["company_domain"] == "acme.example.test"
    assert duplicates["company"] == [
        409,
        {"code": "duplicate_domain", "existing_id": duplicates["company_id"]},
    ]
    assert duplicates["same_name"] == 201


def test_two_concurrent_creates_with_one_email_give_one_record(probe: Probe) -> None:
    assert probe["concurrent_duplicate"] == [201, 409]


def test_updates_need_the_current_version(probe: Probe) -> None:
    versions = probe["versions"]
    assert versions["missing"] == 428
    assert versions["changed"] == [200, 2, '"2"']
    assert versions["stale"] == [409, {"code": "stale_version", "current_version": 2}]
    assert versions["unchanged"] == [200, 2]
    assert versions["cleared_both"] == [422, {"code": "email_or_phone_required"}]
    assert versions["malformed"] == 400


def test_an_idempotency_key_creates_once(probe: Probe) -> None:
    idempotency = probe["idempotency"]
    first_status, first_id, first_replayed = idempotency["first"]
    assert (first_status, first_replayed) == (201, None)
    assert idempotency["second"] == [201, first_id, "true"]
    assert idempotency["reused"] == [422, {"code": "idempotency_key_reused"}]


def test_archive_is_repeatable_and_restore_respects_duplicates(probe: Probe) -> None:
    archive = probe["archive"]
    assert archive["archived"] == [True, 2]
    assert archive["again_version"] == 2
    assert archive["replacement"] == 201
    assert archive["restore_blocked"][0] == 409
    assert archive["restore_blocked"][1]["code"] == "duplicate_email"


def test_links_stay_inside_the_workspace_and_owners_must_be_members(probe: Probe) -> None:
    links = probe["links"]
    assert links["foreign_company"] == [422]
    assert links["archived_company"] == [422]
    assert links["linked_summary"]["name"] == "Acme"
    assert links["owner_outsider"] == 422
    assert links["owner_member"] == 201
    assert links["company_deleted"] == 204
    assert links["contact_after"] == [None, None]


def test_a_deleted_workspace_refuses_writes(probe: Probe) -> None:
    assert probe["deleted_workspace"] == 404


def test_every_change_is_audited_without_values(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata::text FROM core.audit_log"
        " WHERE tenant_id = %s AND starts_with(action, 'crm_app.')",
        (probe["workspace"],),
    ).fetchall()
    actions = {action for action, _ in rows}
    assert {
        "crm_app.contact.created",
        "crm_app.contact.updated",
        "crm_app.contact.archived",
        "crm_app.contact.restored",
        "crm_app.contact.deleted",
        "crm_app.company.created",
        "crm_app.company.deleted",
    } <= actions
    text = " ".join(metadata for _, metadata in rows)
    assert "@example.test" not in text
    assert "Acme" not in text
    creations = [m for a, m in rows if a == "crm_app.contact.created"]
    assert all('"fields"' in m for m in creations)
    idempotent = [m for a, m in rows if a == "crm_app.contact.created" and '"first_name"' in m]
    assert idempotent  # field names, never values
