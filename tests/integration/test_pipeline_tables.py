"""The pipeline tables (migration 0010; decision P4, slice 4A).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the composite foreign key with RLS bypassed, the name, probability
and position rules, the cascade, the real purge through the installed
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

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
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


def _pipeline(connection: psycopg.Connection, tenant: object, name: str | None = None) -> uuid.UUID:
    return _insert(
        connection,
        "pipeline",
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant,
            "name": f"Pipeline {uuid.uuid4().hex[:8]}" if name is None else name,
        },
    )


def _stage(
    connection: psycopg.Connection,
    tenant: object,
    pipeline: object,
    position: int,
    *,
    name: str | None = None,
    probability: int = 50,
) -> uuid.UUID:
    return _insert(
        connection,
        "pipeline_stage",
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant,
            "pipeline_id": pipeline,
            "name": f"Stage {uuid.uuid4().hex[:8]}" if name is None else name,
            "probability": probability,
            "position": position,
        },
    )


# --- Row-level security, as the runtime role ---------------------------------------


def test_pipelines_and_stages_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _stage(runtime, a, _pipeline(runtime, a), 0)

    for table in ("pipeline", "pipeline_stage"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


@pytest.mark.parametrize("table", ["pipeline", "pipeline_stage"])
def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    pipeline_b = _pipeline(owner_connection, b)

    def write() -> None:
        if table == "pipeline":
            _pipeline(runtime, b)
        else:
            _stage(runtime, b, pipeline_b, 5)

    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        write()
    with pytest.raises(errors.InsufficientPrivilege):
        write()  # no workspace set at all


# --- Composite foreign key, with RLS bypassed --------------------------------------


def test_a_stage_cannot_belong_to_another_workspaces_pipeline(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    pipeline_b = _pipeline(owner_connection, b)
    with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
        _stage(owner_connection, a, pipeline_b, 0)


# --- Values -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["", " Sales", "Sales ", "x" * 61, "line\nbreak", "bell\x07"],
    ids=["empty", "leading", "trailing", "long", "newline", "control"],
)
def test_pipeline_names_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    name: str,
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _pipeline(owner_connection, a, name)


@pytest.mark.parametrize(
    ("name", "probability", "position"),
    [
        ("", 10, 0),
        ("x" * 41, 10, 0),
        ("tab\there", 10, 0),
        ("Fine", 101, 0),
        ("Fine", -1, 0),
        ("Fine", 10, -1),
    ],
    ids=["empty", "long", "control", "over", "under", "position"],
)
def test_stages_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    name: str,
    probability: int,
    position: int,
) -> None:
    a = _workspace(env)["tenant"]
    pipeline = _pipeline(owner_connection, a)
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _stage(owner_connection, a, pipeline, position, name=name, probability=probability)


def test_names_are_unique_regardless_of_case(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    first = _pipeline(owner_connection, a, "Sales")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _pipeline(owner_connection, a, "SALES")
    _pipeline(owner_connection, b, "Sales")  # another workspace may use it
    _stage(owner_connection, a, first, 0, name="Proposal")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _stage(owner_connection, a, first, 1, name="proposal")
    second = _pipeline(owner_connection, a, "Renewals")
    _stage(owner_connection, a, second, 0, name="Proposal")  # another pipeline may use it


def test_positions_are_unique_per_pipeline_when_the_transaction_commits(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    pipeline = _pipeline(owner_connection, a)
    one, two = _stage(owner_connection, a, pipeline, 0), _stage(owner_connection, a, pipeline, 1)
    # A swap passes: the check waits for the commit.
    with owner_connection.transaction():
        owner_connection.execute(
            "UPDATE crm_app.pipeline_stage SET position = 1 WHERE id = %s", (one,)
        )
        owner_connection.execute(
            "UPDATE crm_app.pipeline_stage SET position = 0 WHERE id = %s", (two,)
        )
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        owner_connection.execute(
            "UPDATE crm_app.pipeline_stage SET position = 0 WHERE id = %s", (one,)
        )


# --- Cascade -----------------------------------------------------------------------


def test_deleting_a_pipeline_deletes_its_stages(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        gone, kept = _pipeline(runtime, a), _pipeline(runtime, a)
        _stage(runtime, a, gone, 0)
        _stage(runtime, a, kept, 0)
        runtime.execute("DELETE FROM crm_app.pipeline WHERE id = %s", (gone,))
        assert _visible(runtime, "pipeline") == 1
        assert _visible(runtime, "pipeline_stage") == 1


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_pipelines_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        _stage(owner_connection, tenant, _pipeline(owner_connection, tenant), 0)

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("pipeline", "pipeline_stage"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1


# --- Rollback (last in this module) --------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0009_imports')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)
_PIPELINE_TABLES = {"pipeline", "pipeline_stage"}


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0009 (dropping the pipeline tables and their rows), then
    upgrades, leaving the schema as the other tests need it."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not tables & _PIPELINE_TABLES
        assert {"contact", "company", "import_job"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert tables >= _PIPELINE_TABLES
