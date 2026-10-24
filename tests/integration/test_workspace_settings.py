"""Workspace settings (decision P2-F 1; `PHASE2-PLAN.md` §13 "Settings").

Drives `settings_probe` in a fresh interpreter, then checks the audit trail
and the table's runtime isolation directly. Covers: product defaults before
the first save; read for every role and change for Owner and Admin only;
validation and normalisation of locale, time zone and currency; optimistic
versions, including two first saves at once; other workspaces; audit
entries naming fields only; and, as the runtime role, rows visible and
writable only inside their own workspace. The structural guards prove
forced RLS, grants and purge coverage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from tests.integration.test_crm_tables import (
    _as_workspace,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    probe_env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    cwd: Path = tmp_path_factory.mktemp("settings")
    result = run_module("tests.integration.settings_probe", [], probe_env, cwd, timeout=600)
    assert result.returncode == 0, result.stderr
    assert "leak-3c1d" not in result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_new_workspace_has_the_defaults_at_version_0(probe: Probe) -> None:
    status, body, etag = probe["defaults"]
    assert status == 200
    assert (body["locale"], body["time_zone"], body["currency"]) == (
        "en",
        "Europe/Amsterdam",
        "EUR",
    )
    assert (body["version"], body["updated_at"], etag) == (0, None, '"0"')


def test_every_role_reads_and_nobody_else_does(probe: Probe) -> None:
    assert probe["read"] == {
        "Owner": 200,
        "Admin": 200,
        "Member": 200,
        "Read-only": 200,
        "outsider": 404,
        "other_owner": 404,
        "anonymous": 401,
    }


def test_only_owners_and_admins_change_them(probe: Probe) -> None:
    assert probe["change"] == {"Member": 403, "Read-only": 403, "Admin": 200}
    after = probe["after_admin"]
    assert (after["currency"], after["version"]) == ("USD", 1)
    assert after["updated_by_user_id"] == probe["admin"]


def test_values_are_normalised_and_versions_checked(probe: Probe) -> None:
    status, body, etag = probe["normalised"]
    assert status == 200
    assert (body["locale"], body["time_zone"], body["currency"]) == (
        "nl-NL",
        "Europe/Berlin",
        "EUR",
    )
    assert (body["version"], etag) == (2, '"2"')
    assert probe["unchanged"] == 2  # nothing changed: no new version
    assert probe["stale"] == [409, {"code": "stale_version", "current_version": 2}]
    assert probe["missing_version"] == 428


def test_invalid_values_and_extra_fields_are_refused_without_echo(probe: Probe) -> None:
    validation = probe["validation"]
    assert {k: v for k, v in validation.items() if k != "time_zone_body"} == {
        "time_zone": 422,
        "currency": 422,
        "locale": 422,
        "unknown_field": 422,
        "tenant_id": 422,
        "version_field": 422,
    }
    assert "leak-3c1d" not in validation["time_zone_body"]


def test_other_workspaces_cannot_read_or_change_them(probe: Probe) -> None:
    assert probe["cross"] == {
        "other_owner_patch": 404,
        "outsider_patch": 404,
        "b_defaults": "EUR",
        "a_after": "EUR",
    }


def test_two_first_saves_at_once_leave_one_winner(probe: Probe) -> None:
    assert probe["race"] == [200, 409]
    assert probe["race_after"] == 1


def test_each_save_is_audited_with_field_names_only(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT metadata::text FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.workspace_settings.updated' ORDER BY created_at",
        (probe["workspace"],),
    ).fetchall()
    assert [json.loads(metadata) for (metadata,) in rows] == [
        {"fields": ["currency"]},
        {"fields": ["currency", "locale", "time_zone"]},
    ]


# --- Row-level security, as the runtime role -----------------------------------


def test_settings_rows_are_visible_and_writable_only_in_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    insert = (
        "INSERT INTO crm_app.workspace_settings (tenant_id, locale, time_zone, currency)"
        " VALUES (%s, 'en', 'UTC', 'EUR')"
    )
    with _as_workspace(runtime, a):
        runtime.execute(insert, (a,))
    assert _visible(runtime, "workspace_settings") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "workspace_settings") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "workspace_settings") == 1
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(insert, (b,))
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(
            "UPDATE crm_app.workspace_settings SET tenant_id = %s WHERE tenant_id = %s", (b, a)
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [("locale", "english"), ("time_zone", "Not a zone!"), ("currency", "eur")],
)
def test_the_table_refuses_values_outside_the_rules(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    column: str,
    value: str,
) -> None:
    a = _workspace(env)["tenant"]
    row = {"tenant_id": a, "locale": "en", "time_zone": "UTC", "currency": "EUR", column: value}
    with pytest.raises(errors.CheckViolation):
        owner_connection.execute(
            "INSERT INTO crm_app.workspace_settings (tenant_id, locale, time_zone, currency)"
            " VALUES (%(tenant_id)s, %(locale)s, %(time_zone)s, %(currency)s)",
            row,
        )
