"""The custom field schema (migration 0008; decision P3-D).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the definition rules, keys that keep one meaning, the records' new
`custom_fields` column, the history's new field name, the real purge through
the installed operator command, and the migration's rollback.

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
    NEWER_HISTORY,
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


def _definition(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "entity": "contact",
        "key": f"field_{uuid.uuid4().hex[:8]}",
        "label": "Insurance carrier",
        "field_type": "text",
    }
    row.update(values)
    return _insert(connection, "custom_field_definition", row)


# --- Row-level security, as the runtime role ---------------------------------------


def test_definitions_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _definition(runtime, a)
    assert _visible(runtime, "custom_field_definition") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "custom_field_definition") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "custom_field_definition") == 1


def test_the_runtime_role_cannot_write_another_workspaces_definitions(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _definition(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        _definition(runtime, b)  # no workspace set at all
    with _as_workspace(runtime, a):
        mine = _definition(runtime, a)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(
            "UPDATE crm_app.custom_field_definition SET tenant_id = %s WHERE id = %s", (b, mine)
        )


# --- Definition rules ----------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"entity": "deal"},
        {"key": "Insurance"},
        {"key": "1st_field"},
        {"key": "has-dash"},
        {"key": "x" * 41},
        {"label": ""},
        {"label": " Padded"},
        {"label": "x" * 61},
        {"label": "line\nbreak"},
        {"field_type": "currency"},
        {"field_type": "select"},  # a select needs options
        {"field_type": "text", "options": Jsonb(["a"])},  # only a select has them
        {"field_type": "select", "options": Jsonb([])},
        {"field_type": "select", "options": Jsonb({"a": 1})},
        {"field_type": "select", "options": Jsonb([str(n) for n in range(51)])},
        {"position": -1},
    ],
)
def test_definitions_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _definition(owner_connection, a, **values)


def test_every_type_and_a_select_with_options_are_accepted(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    for field_type in ("text", "number", "date", "boolean"):
        _definition(owner_connection, a, field_type=field_type, entity="company")
    _definition(owner_connection, a, field_type="select", options=Jsonb(["Gold", "Silver"]))


def test_a_key_keeps_one_meaning_per_workspace_and_entity(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    _definition(owner_connection, a, key="carrier", archived_at="2026-10-26T00:00:00Z")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _definition(owner_connection, a, key="carrier")  # archived keys are not reused
    _definition(owner_connection, a, key="carrier", entity="company")
    _definition(owner_connection, b, key="carrier")


# --- The records' values column --------------------------------------------------------


def test_records_start_with_no_values_and_hold_only_an_object(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    for table, insert in (("contact", _contact), ("company", _company)):
        record = insert(owner_connection, a)
        row = owner_connection.execute(
            sql.SQL("SELECT custom_fields FROM {} WHERE id = %s").format(_table(table)),
            (record,),
        ).fetchone()
        assert row == ({},)
        for refused in (Jsonb([]), Jsonb("text"), Jsonb({"big": "x" * 33_000})):
            with pytest.raises(errors.CheckViolation), owner_connection.transaction():
                insert(owner_connection, a, custom_fields=refused)
        with pytest.raises(errors.NotNullViolation), owner_connection.transaction():
            insert(owner_connection, a, custom_fields=None)
        insert(owner_connection, a, custom_fields=Jsonb({"carrier": "Delta", "seats": 4}))


def test_an_updated_entry_may_name_custom_fields(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    for fields in (["custom_fields"], ["tags", "custom_fields", "city"]):
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
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _insert(
            owner_connection,
            "activity",
            {
                "id": uuid.uuid4(),
                "tenant_id": a,
                "contact_id": contact,
                "kind": "updated",
                "fields": Jsonb(["carrier"]),
            },
        )


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_definitions_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        _definition(owner_connection, tenant)
        _contact(owner_connection, tenant, custom_fields=Jsonb({"carrier": "Delta"}))

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("custom_field_definition", "contact"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1


# --- Rollback (last in this module) --------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0007_tags')\n"
)
_COLUMNS = (
    "SELECT table_name FROM information_schema.columns"
    " WHERE table_schema = 'crm_app' AND column_name = 'custom_fields' ORDER BY 1"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0007 (dropping the definitions and every record's values),
    then upgrades, leaving the schema as the other tests need it. Entries that
    name `custom_fields` are removed first: the old rule refuses them."""
    owner_connection.execute(NEWER_HISTORY)
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        assert owner_connection.execute(_COLUMNS).fetchall() == []
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert "custom_field_definition" not in tables
        assert {"contact", "company", "tag"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    assert owner_connection.execute(_COLUMNS).fetchall() == [("company",), ("contact",)]
