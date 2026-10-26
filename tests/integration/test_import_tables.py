"""The import staging schema (migration 0009; decision P3-F).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policies, the runtime role's privileges, the global table's
exclusion policy and purge coverage from the catalogs. These tests prove
the behaviour: what the runtime role can see and write, the composite key,
the row and job rules, one active import per workspace, the cascade, the
global expiry table's visibility, the real purge through the installed
operator command, and the migration's rollback.

Rows are written with plain SQL as the runtime role or the migration role,
as in `test_crm_tables.py`, in the disposable integration database.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
    NEWER_HISTORY,
    _as_workspace,
    _count,
    _insert,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _status
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")


def _job(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "entity": "contact",
        "status": "previewed",
        "mapping": Jsonb({"first_name": 0, "email": 1}),
        "created_by_user_id": uuid.uuid4(),
    }
    row.update(values)
    return _insert(connection, "import_job", row)


def _row(connection: psycopg.Connection, tenant: object, job: object, **values: object) -> None:
    row: dict[str, object] = {
        "tenant_id": tenant,
        "import_id": job,
        "row_number": 1,
        "status": "valid",
        "data": Jsonb({"first_name": "Sam", "email": "sam@example.test"}),
        "errors": None,
        "record_id": None,
    }
    row.update(values)
    connection.execute(
        "INSERT INTO crm_app.import_row (tenant_id, import_id, row_number, status, data,"
        " errors, record_id) VALUES (%(tenant_id)s, %(import_id)s, %(row_number)s,"
        " %(status)s, %(data)s, %(errors)s, %(record_id)s)",
        row,
    )


def _expiry(connection: psycopg.Connection, import_id: object, workspace: object) -> None:
    connection.execute(
        "INSERT INTO crm_app.import_expiry (import_id, workspace_id, due_at)"
        " VALUES (%s, %s, now())",
        (import_id, workspace),
    )


# --- Row-level security, as the runtime role ---------------------------------------


def test_jobs_and_rows_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _row(runtime, a, _job(runtime, a))
    for table in ("import_job", "import_row"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    job_b = _job(owner_connection, b)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _job(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _row(runtime, b, job_b)
    with pytest.raises(errors.InsufficientPrivilege):
        _job(runtime, b)  # no workspace set at all


def test_a_row_cannot_belong_to_another_workspaces_import(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    job_b = _job(owner_connection, b)
    with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
        _row(owner_connection, a, job_b)


# --- Rules ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"entity": "deal"},
        {"status": "paused"},
        {"mapping": Jsonb([0, 1])},
        {"total_rows": 10_001, "valid_rows": 10_001},
        {"total_rows": 3, "valid_rows": 1},  # the counts do not add up
        {"created_rows": -1},
        {"checkpoint": 2, "total_rows": 1, "valid_rows": 1},
        {"status": "completed"},  # finished without a time
        {"finished_at": "2026-10-26T10:00:00Z"},  # a time without finishing
    ],
)
def test_jobs_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _job(owner_connection, a, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"row_number": 0},
        {"row_number": 10_001},
        {"status": "pending"},
        {"status": "invalid"},  # invalid rows need their errors and no values
        {"status": "invalid", "errors": Jsonb([{"field": "email", "code": "invalid"}])},
        {"status": "valid", "data": None},
        {"status": "valid", "errors": Jsonb([])},
        {"status": "created"},  # created without its record
        {"status": "valid", "record_id": uuid.uuid4()},
    ],
)
def test_rows_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    job = _job(owner_connection, a)
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _row(owner_connection, a, job, **values)


def test_the_allowed_rows_are_accepted(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    job = _job(owner_connection, a)
    _row(owner_connection, a, job, row_number=1)
    _row(
        owner_connection,
        a,
        job,
        row_number=2,
        status="invalid",
        data=None,
        errors=Jsonb([{"field": "email", "code": "invalid"}]),
    )
    _row(owner_connection, a, job, row_number=3, status="duplicate")
    _row(owner_connection, a, job, row_number=4, status="created", record_id=uuid.uuid4())


def test_one_import_is_queued_or_running_per_workspace(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    _job(owner_connection, a, status="queued")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _job(owner_connection, a, status="running")
    _job(owner_connection, a, status="previewed")
    _job(owner_connection, a, status="completed", finished_at="2026-10-26T10:00:00Z")
    _job(owner_connection, b, status="running")


def test_deleting_a_job_removes_its_rows(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        job = _job(runtime, a)
        _row(runtime, a, job)
        runtime.execute("DELETE FROM crm_app.import_job WHERE id = %s", (job,))
        assert _visible(runtime, "import_row") == 0


# --- The global expiry table --------------------------------------------------------


def test_the_expiry_table_is_seen_and_written_only_without_a_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    entry = uuid.uuid4()
    _expiry(runtime, entry, a)
    query = "SELECT count(*) FROM crm_app.import_expiry WHERE import_id = %s"
    assert runtime.execute(query, (entry,)).fetchone() == (1,)
    with _as_workspace(runtime, a):
        assert runtime.execute(query, (entry,)).fetchone() == (0,)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _expiry(runtime, uuid.uuid4(), a)


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_imports_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        job = _job(owner_connection, tenant)
        _row(owner_connection, tenant, job)
        _expiry(owner_connection, job, tenant)

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("import_job", "import_row"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1
    left = owner_connection.execute(
        "SELECT workspace_id::text FROM crm_app.import_expiry WHERE workspace_id::text = ANY(%s)",
        ([target["tenant"], other],),
    ).fetchall()
    assert left == [(other,)]


# --- Rollback (last in this module) --------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0008_custom_fields')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)
_IMPORT_TABLES = {"import_job", "import_row", "import_expiry"}


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0008 (dropping the import tables and their rows), then
    upgrades, leaving the schema as the other tests need it."""
    owner_connection.execute(NEWER_HISTORY)
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not tables & _IMPORT_TABLES
        assert {"contact", "company", "custom_field_definition"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert tables >= _IMPORT_TABLES
