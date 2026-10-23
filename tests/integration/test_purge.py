"""Workspace purge removes this product's data (gate G1; `crm_app.purge`).

Each step runs in a fresh interpreter (`purge_probe`, or the installed
`saas-os-operator` command), because the purge-participant registry is per
process; results are read back as the owner connection.

The failure paths (a failing participant, rows left behind, an unmapped
manifest table) are proven on a probe table, `<schema>.items`, created like a
product table (forced Row-Level Security, DML for the runtime role) in its
own schema, which is dropped afterwards. The participant under test is the
product's own class (`CrmDataPurgeParticipant`), given the probe table as
its manifest. The real contact and company purge is in
`test_crm_tables.py`.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.purge_probe import PROBE_PARTICIPANT, PROBE_TABLE
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

OPERATOR = Path(sys.executable).parent / (
    "saas-os-operator.exe" if os.name == "nt" else "saas-os-operator"
)
OPERATOR_SETUP = ("--setup", "crm_app.purge:register_purge_participants")


def _probe(env: dict[str, str], *args: str) -> dict[str, object]:
    result = run_module("tests.integration.purge_probe", list(args), env, REPO_ROOT)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _status(connection: psycopg.Connection, tenant: object) -> str:
    row = connection.execute("SELECT status FROM core.tenants WHERE id = %s", (tenant,)).fetchone()
    assert row is not None
    return str(row[0])


def _rows(connection: psycopg.Connection, schema: str, tenant: object) -> int:
    query = sql.SQL("SELECT count(*) FROM {} WHERE tenant_id = %s").format(
        sql.Identifier(schema, PROBE_TABLE)
    )
    row = connection.execute(query, (tenant,)).fetchone()
    assert row is not None
    return int(row[0])


def _events(connection: psycopg.Connection, tenant: object, action: str) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s AND action = %s"
        " ORDER BY created_at",
        (tenant, action),
    ).fetchall()
    return [dict(row[0]) for row in rows]


@pytest.fixture
def env(integration_env: dict[str, str]) -> dict[str, str]:
    return dict(integration_env)


@pytest.fixture
def probe_schema(env: dict[str, str], owner_connection: psycopg.Connection) -> Iterator[str]:
    schema = f"crm_app_purge_probe_{secrets.token_hex(4)}"
    _probe(env, "probe-table", schema)
    try:
        yield schema
    finally:
        owner_connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _operator(
    env: dict[str, str], tenant: str, actor: str, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(OPERATOR),
            "purge-tenant",
            "--tenant",
            tenant,
            "--actor",
            actor,
            "--confirm",
            tenant,
            *extra,
        ],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_the_operator_command_purges_with_the_products_participant(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    target = _probe(env, "deleted")
    tenant, actor = str(target["tenant"]), str(target["actor"])

    refused = _operator(env, tenant, actor)
    assert refused.returncode == 2, refused.stderr
    assert _status(owner_connection, tenant) == "deleted"

    purged = _operator(env, tenant, actor, *OPERATOR_SETUP)
    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, tenant) == "purged"
    (completed,) = _events(owner_connection, tenant, "tenant.purge_completed")
    assert "product_participants_skipped" not in completed


def test_purge_deletes_the_purged_workspaces_rows_and_no_others(
    env: dict[str, str], owner_connection: psycopg.Connection, probe_schema: str
) -> None:
    target = str(_probe(env, "deleted")["tenant"])
    other = str(_probe(env, "active")["tenant"])
    _probe(env, "seed", probe_schema, target, "3")
    _probe(env, "seed", probe_schema, other, "2")

    result = _probe(env, "purge", target, probe_schema, "probe")

    assert result == {"already_purged": False, "participant_names": [PROBE_PARTICIPANT]}
    assert _rows(owner_connection, probe_schema, target) == 0
    assert _rows(owner_connection, probe_schema, other) == 2
    assert _status(owner_connection, target) == "purged"
    assert _status(owner_connection, other) == "active"
    again = _probe(env, "purge", target, probe_schema, "probe")
    assert again["already_purged"] is True


def test_a_failing_participant_leaves_the_workspace_purging_and_a_retry_completes(
    env: dict[str, str], owner_connection: psycopg.Connection, probe_schema: str
) -> None:
    target = str(_probe(env, "deleted")["tenant"])
    _probe(env, "seed", probe_schema, target, "2")

    failed = _probe(env, "purge", target, probe_schema, "failing")

    assert failed == {"error": "ProbeFailureError"}
    assert _status(owner_connection, target) == "purging"
    assert _rows(owner_connection, probe_schema, target) == 2
    (event,) = _events(owner_connection, target, "tenant.purge_failed")
    assert event["failure_class"] == "participant_error"
    assert event["failed_step"] == f"participant:{PROBE_PARTICIPANT}"
    assert event["error_type"] == "ProbeFailureError"

    retried = _probe(env, "purge", target, probe_schema, "probe")

    assert retried == {"already_purged": False, "participant_names": [PROBE_PARTICIPANT]}
    assert _status(owner_connection, target) == "purged"
    assert _rows(owner_connection, probe_schema, target) == 0


def test_rows_left_behind_fail_the_purge(
    env: dict[str, str], owner_connection: psycopg.Connection, probe_schema: str
) -> None:
    """A trigger that silently cancels deletes stands in for any cause of
    leftover rows: the participant's re-read must catch it."""
    target = str(_probe(env, "deleted")["tenant"])
    _probe(env, "seed", probe_schema, target, "2")
    owner_connection.execute(
        sql.SQL(
            "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"
        ).format(sql.Identifier(probe_schema, "keep_rows"))
    )
    owner_connection.execute(
        sql.SQL(
            "CREATE TRIGGER keep_rows BEFORE DELETE ON {} FOR EACH ROW EXECUTE FUNCTION {}()"
        ).format(
            sql.Identifier(probe_schema, PROBE_TABLE), sql.Identifier(probe_schema, "keep_rows")
        )
    )

    failed = _probe(env, "purge", target, probe_schema, "probe")

    assert failed == {"error": "PurgeIncompleteError"}
    assert _status(owner_connection, target) == "purging"
    assert _rows(owner_connection, probe_schema, target) == 2
    (event,) = _events(owner_connection, target, "tenant.purge_failed")
    assert event["error_type"] == "PurgeIncompleteError"


def test_a_manifest_table_that_is_not_mapped_fails_the_purge(
    env: dict[str, str], owner_connection: psycopg.Connection, probe_schema: str
) -> None:
    target = str(_probe(env, "deleted")["tenant"])

    failed = _probe(env, "purge", target, probe_schema, "unmapped")

    assert failed == {"error": "PurgeIncompleteError"}
    assert _status(owner_connection, target) == "purging"
