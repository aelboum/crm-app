"""The tag tables (migration 0007; decision P3-C).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the composite foreign keys with RLS bypassed, the name rules, the
cascades, the history's new `tags` field, the real purge through the
installed operator command, and the migration's rollback.

Rows are written with plain SQL as the runtime role or the migration role,
as in `test_crm_tables.py`, in the disposable integration database.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import errors, sql
from psycopg.types.json import Jsonb

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
    _as_workspace,
    _company,
    _contact,
    _count,
    _insert,
    _table,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _status
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")

ASSIGNMENTS = {"contact_tag": "contact_id", "company_tag": "company_id"}


def _tag(connection: psycopg.Connection, tenant: object, name: str | None = None) -> uuid.UUID:
    return _insert(
        connection,
        "tag",
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant,
            "name": f"Tag {uuid.uuid4().hex[:8]}" if name is None else name,
        },
    )


def _record(connection: psycopg.Connection, table: str, tenant: object) -> uuid.UUID:
    return _contact(connection, tenant) if table == "contact_tag" else _company(connection, tenant)


def _assign(
    connection: psycopg.Connection, table: str, tenant: object, record: object, tag: object
) -> None:
    statement = sql.SQL("INSERT INTO {} (tenant_id, {}, tag_id) VALUES (%s, %s, %s)").format(
        _table(table), sql.Identifier(ASSIGNMENTS[table])
    )
    connection.execute(statement, (tenant, record, tag))


# --- Row-level security, as the runtime role ---------------------------------------


def test_tags_and_assignments_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        tag = _tag(runtime, a)
        for table in ASSIGNMENTS:
            _assign(runtime, table, a, _record(runtime, table, a), tag)

    for table in ("tag", *ASSIGNMENTS):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


@pytest.mark.parametrize("table", ["tag", *ASSIGNMENTS])
def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    tag_b = _tag(owner_connection, b)

    def write() -> None:
        if table == "tag":
            _tag(runtime, b)
        else:
            _assign(runtime, table, b, _record(owner_connection, table, b), tag_b)

    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        write()
    with pytest.raises(errors.InsufficientPrivilege):
        write()  # no workspace set at all


def test_a_tag_update_cannot_move_it_to_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        tag = _tag(runtime, a)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("UPDATE crm_app.tag SET tenant_id = %s WHERE id = %s", (b, tag))


# --- Composite foreign keys, with RLS bypassed -------------------------------------


@pytest.mark.parametrize("table", list(ASSIGNMENTS))
def test_a_tag_cannot_be_put_on_another_workspaces_record(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    record_a, record_b = _record(owner_connection, table, a), _record(owner_connection, table, b)
    tag_a, tag_b = _tag(owner_connection, a), _tag(owner_connection, b)
    for tenant, record, tag in ((a, record_a, tag_b), (a, record_b, tag_a), (b, record_a, tag_b)):
        with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
            _assign(owner_connection, table, tenant, record, tag)


# --- Values -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["", " VIP", "VIP ", "x" * 51, "line\nbreak", "tab\there", "bell\x07"]
)
def test_tag_names_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    name: str,
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _tag(owner_connection, a, name)


def test_a_name_is_unique_per_workspace_whatever_its_case(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    _tag(owner_connection, a, "Hot lead")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _tag(owner_connection, a, "HOT LEAD")
    _tag(owner_connection, b, "Hot lead")  # another workspace may use it
    _tag(owner_connection, a, "Héllo 张伟 " + "x" * 41)  # any language, 50 characters


def test_a_record_carries_a_tag_once(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    tag = _tag(owner_connection, a)
    for table in ASSIGNMENTS:
        record = _record(owner_connection, table, a)
        _assign(owner_connection, table, a, record, tag)
        with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
            _assign(owner_connection, table, a, record, tag)


# --- Cascades -------------------------------------------------------------------------


def test_deleting_a_tag_removes_its_assignments_and_keeps_the_records(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        tag, kept = _tag(runtime, a), _tag(runtime, a)
        records = {table: _record(runtime, table, a) for table in ASSIGNMENTS}
        for table, record in records.items():
            _assign(runtime, table, a, record, tag)
            _assign(runtime, table, a, record, kept)
        runtime.execute("DELETE FROM crm_app.tag WHERE id = %s", (tag,))
        for table in ASSIGNMENTS:
            remaining = runtime.execute(
                sql.SQL("SELECT tag_id FROM {}").format(_table(table))
            ).fetchall()
            assert remaining == [(kept,)]
        assert _visible(runtime, "contact") == 1
        assert _visible(runtime, "company") == 1


def test_deleting_a_record_removes_its_assignments_and_keeps_the_tag(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        tag = _tag(runtime, a)
        for table, key in ASSIGNMENTS.items():
            record = _record(runtime, table, a)
            _assign(runtime, table, a, record, tag)
            parent = key.removesuffix("_id")
            runtime.execute(
                sql.SQL("DELETE FROM {} WHERE id = %s").format(_table(parent)), (record,)
            )
            assert _visible(runtime, table) == 0
        assert _visible(runtime, "tag") == 1


# --- History ----------------------------------------------------------------------


def test_an_updated_entry_may_name_tags_and_still_nothing_else_new(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)

    def entry(fields: list[str]) -> None:
        _insert(
            owner_connection,
            "activity",
            {
                "id": uuid.uuid4(),
                "tenant_id": a,
                "contact_id": contact,
                "kind": "updated",
                "fields": Jsonb(fields),
            },
        )

    entry(["tags"])
    entry(["tags", "first_name"])
    for refused in (["tag_ids"], ["tags", "owner_user_id"]):
        with pytest.raises(errors.CheckViolation), owner_connection.transaction():
            entry(refused)


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_tags_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        tag = _tag(owner_connection, tenant)
        for table in ASSIGNMENTS:
            _assign(owner_connection, table, tenant, _record(owner_connection, table, tenant), tag)

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("tag", *ASSIGNMENTS, "contact", "company"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1


# --- Rollback (last in this module) --------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0006_signup')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)
_TAG_TABLES = {"tag", "contact_tag", "company_tag"}


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0006 (dropping the tag tables and their rows), then
    upgrades, leaving the schema as the other tests need it. Entries that
    name `tags` are removed first: the old rule refuses them, and downgrade
    fails rather than delete them itself."""
    owner_connection.execute("DELETE FROM crm_app.activity WHERE fields ? 'tags'")
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not tables & _TAG_TABLES
        assert {"contact", "company", "activity"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert tables >= _TAG_TABLES
