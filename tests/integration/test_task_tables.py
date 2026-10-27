"""The task table (migration 0012; decision P4-C, slice 4C).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the composite links with RLS bypassed, the value rules, the links
cleared when a record is deleted, the real purge through the installed
operator command, and the migration's rollback.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
    _as_workspace,
    _company,
    _contact,
    _count,
    _insert,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.integration.test_opportunity_tables import _deal, _setup
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _status
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")


def _task(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "title": "Call back",
        **values,
    }
    return _insert(connection, "task", row)


def test_tasks_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _task(runtime, a)
    assert _visible(runtime, "task") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "task") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "task") == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _task(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        _task(runtime, b)  # no workspace set at all


def test_a_task_links_only_to_its_own_workspaces_records(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    pipeline_b, stages_b = _setup(owner_connection, b)
    refused: list[dict[str, Any]] = [
        {"contact_id": _contact(owner_connection, b)},
        {"company_id": _company(owner_connection, b)},
        {"opportunity_id": _deal(owner_connection, b, pipeline_b, stages_b[0])},
    ]
    for values in refused:
        with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
            _task(owner_connection, a, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"title": ""},
        {"title": " Padded"},
        {"title": "x" * 201},
        {"title": "line\nbreak"},
        {"priority": "urgent"},
        {"completed_at": "2026-10-27T10:00:00Z"},
        {"completed_by_user_id": str(uuid.uuid4())},
    ],
    ids=[
        "empty-title",
        "padded-title",
        "long-title",
        "control-title",
        "unknown-priority",
        "completed-without-who",
        "who-without-completed",
    ],
)
def test_tasks_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _task(owner_connection, a, **values)


def test_deleting_a_linked_record_keeps_the_task_without_the_link(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        pipeline, stages = _setup(runtime, a)
        contact, company = _contact(runtime, a), _company(runtime, a)
        deal = _deal(runtime, a, pipeline, stages[0])
        task = _task(runtime, a, contact_id=contact, company_id=company, opportunity_id=deal)
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        runtime.execute("DELETE FROM crm_app.company WHERE id = %s", (company,))
        runtime.execute("DELETE FROM crm_app.opportunity WHERE id = %s", (deal,))
        row = runtime.execute(
            "SELECT tenant_id, contact_id, company_id, opportunity_id FROM crm_app.task"
            " WHERE id = %s",
            (task,),
        ).fetchone()
    assert row == (uuid.UUID(a), None, None, None)


def test_the_operator_purge_removes_tasks_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        _task(owner_connection, tenant, contact_id=_contact(owner_connection, tenant))

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    assert _count(owner_connection, "task", target["tenant"]) == 0
    assert _count(owner_connection, "task", other) == 1


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0011_opportunities')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0011 (dropping the task table and its rows), then
    upgrades, leaving the schema as the other tests need it."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert "task" not in tables
        assert {"opportunity", "contact"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert "task" in tables
