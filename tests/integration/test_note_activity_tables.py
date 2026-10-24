"""The note and activity tables (migration 0003; `PHASE3-PLAN.md` §21).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges (no UPDATE on `activity`) and
purge coverage from the catalogs. These tests prove the behaviour: what the
runtime role can see and write, that it cannot change an activity entry,
the composite foreign keys with RLS bypassed, the payload rules behind
decision P3-B D5, the cascades behind D4, the real purge through the
installed operator command, and the migration's backfill and rollback.

Rows are written with plain SQL as the runtime role or the migration role,
as in `test_crm_tables.py`, in the disposable integration database.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
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


def _note(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    author = values.pop("author_user_id", uuid.uuid4())
    row = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "body": "Called about the renewal.",
        "author_user_id": author,
        "updated_by_user_id": author,
        **values,
    }
    return _insert(connection, "note", row)


def _activity(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, object] = {"id": uuid.uuid4(), "tenant_id": tenant, "kind": "archived"}
    row.update(values)
    return _insert(connection, "activity", row)


# --- Row-level security and append-only, as the runtime role ---------------------


def test_notes_and_activity_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        contact = _contact(runtime, a)
        _note(runtime, a, contact_id=contact)
        _activity(runtime, a, contact_id=contact)

    for table in ("note", "activity"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


@pytest.mark.parametrize("table", ["note", "activity"])
def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    contact_b = _contact(owner_connection, b)
    insert = _note if table == "note" else _activity
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        insert(runtime, b, contact_id=contact_b)
    with pytest.raises(errors.InsufficientPrivilege):
        insert(runtime, b, contact_id=contact_b)  # no workspace set at all


def test_the_runtime_role_cannot_change_an_activity_entry(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    """Decision P3-B D6: entries are append-only for the application."""
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        contact = _contact(runtime, a)
        entry = _activity(runtime, a, contact_id=contact)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("UPDATE crm_app.activity SET kind = 'restored' WHERE id = %s", (entry,))
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("TRUNCATE crm_app.activity")


def test_a_note_update_cannot_move_it_to_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        note = _note(runtime, a, contact_id=_contact(runtime, a))
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("UPDATE crm_app.note SET tenant_id = %s WHERE id = %s", (b, note))


# --- Composite foreign keys, with RLS bypassed -------------------------------------


@pytest.mark.parametrize("table", ["note", "activity"])
@pytest.mark.parametrize("parent", ["contact_id", "company_id"])
def test_an_entry_cannot_reference_another_workspaces_record(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
    parent: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    record = (
        _contact(owner_connection, a) if parent == "contact_id" else _company(owner_connection, a)
    )
    insert = _note if table == "note" else _activity
    with pytest.raises(errors.ForeignKeyViolation):
        insert(owner_connection, b, **{parent: record})


def test_an_activity_entry_cannot_reference_another_workspaces_note(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    note_a = _note(owner_connection, a, contact_id=_contact(owner_connection, a))
    contact_b = _contact(owner_connection, b)
    with pytest.raises(errors.ForeignKeyViolation):
        _activity(owner_connection, b, contact_id=contact_b, kind="note_added", note_id=note_a)


# --- Payload rules (D5) and note text -------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"contact_id": None},  # no parent
        {"body": ""},
        {"body": "   "},
        {"body": " leading space"},
        {"body": "trailing newline\n"},
        {"body": "x" * 10_001},
        {"body": "carriage\r\nreturn"},
        {"body": "bell\x07"},
        {"body": "escape\x1b[31m"},
    ],
)
def test_note_values_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    with pytest.raises(errors.CheckViolation):
        _note(owner_connection, a, **{"contact_id": contact, **values})


def test_a_note_keeps_inner_line_breaks_tabs_and_any_language(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    body = "Línea uno\n\tindented: <b>not html</b> & 'quotes'\n日本語 ✓\n" + "y" * 9_900
    note = _note(owner_connection, a, contact_id=_contact(owner_connection, a), body=body)
    row = owner_connection.execute(
        "SELECT body FROM crm_app.note WHERE id = %s", (note,)
    ).fetchone()
    assert row == (body,)


def test_a_note_and_an_entry_belong_to_exactly_one_record(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact, company = _contact(owner_connection, a), _company(owner_connection, a)
    with pytest.raises(errors.CheckViolation):
        _note(owner_connection, a, contact_id=contact, company_id=company)
    with pytest.raises(errors.CheckViolation):
        _activity(owner_connection, a, contact_id=contact, company_id=company)
    with pytest.raises(errors.CheckViolation):
        _activity(owner_connection, a)


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "commented"},  # unknown kind
        {"kind": "updated"},  # updated without field names
        {"kind": "updated", "fields": Jsonb([])},
        {"kind": "updated", "fields": Jsonb(["email", "password"])},  # not allow-listed
        {"kind": "updated", "fields": Jsonb({"email": "a@example.test"})},  # values, not names
        {"kind": "updated", "fields": Jsonb(["lifecycle_stage"])},  # has its own kind
        {"kind": "archived", "fields": Jsonb(["email"])},
        {"kind": "stage_changed"},
        {"kind": "stage_changed", "stage_to": "patient"},
        {"kind": "stage_changed", "stage_from": "lead", "stage_to": "lead"},
        {"kind": "archived", "stage_to": "lead"},
        {"kind": "owner_changed"},  # nothing changed
        {"kind": "archived", "owner_to": uuid.uuid4()},
        {"kind": "company_linked"},
        {"kind": "archived", "company_ref_id": uuid.uuid4()},
        {"kind": "note_added"},
    ],
)
def test_activity_payloads_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    with pytest.raises(errors.CheckViolation):
        _activity(owner_connection, a, contact_id=contact, **values)


def test_stage_and_company_entries_are_for_contacts_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    company = _company(owner_connection, a)
    with pytest.raises(errors.CheckViolation):
        _activity(owner_connection, a, company_id=company, kind="stage_changed", stage_to="lead")
    with pytest.raises(errors.CheckViolation):
        _activity(
            owner_connection, a, company_id=company, kind="company_linked", company_ref_id=company
        )


def test_the_allowed_payloads_are_accepted(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact, company = _contact(owner_connection, a), _company(owner_connection, a)
    note = _note(owner_connection, a, contact_id=contact)
    member = uuid.uuid4()
    for values in (
        {"kind": "created"},
        {"kind": "updated", "fields": Jsonb(["email", "phone"])},
        {"kind": "archived"},
        {"kind": "restored"},
        {"kind": "stage_changed", "stage_from": "lead", "stage_to": "customer"},
        {"kind": "owner_changed", "owner_to": member},
        {"kind": "owner_changed", "owner_from": member},
        {"kind": "company_linked", "company_ref_id": company},
        {"kind": "company_unlinked", "company_ref_id": uuid.uuid4()},  # may be deleted
        {"kind": "note_added", "note_id": note},
        {"kind": "note_deleted"},
    ):
        _activity(owner_connection, a, contact_id=contact, **values)
    _activity(owner_connection, a, company_id=company, kind="updated", fields=Jsonb(["domain"]))


# --- Cascades (D4) -----------------------------------------------------------------


def test_deleting_a_note_removes_its_note_added_entry_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    note = _note(owner_connection, a, contact_id=contact)
    added = _activity(owner_connection, a, contact_id=contact, kind="note_added", note_id=note)
    other = _activity(owner_connection, a, contact_id=contact, kind="archived")
    owner_connection.execute("DELETE FROM crm_app.note WHERE id = %s", (note,))
    remaining = {
        row[0]
        for row in owner_connection.execute(
            "SELECT id FROM crm_app.activity WHERE contact_id = %s", (contact,)
        )
    }
    assert added not in remaining
    assert other in remaining


@pytest.mark.parametrize("parent", ["contact", "company"])
def test_deleting_a_record_removes_its_notes_and_activity(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    parent: str,
) -> None:
    a = _workspace(env)["tenant"]
    record = _contact(owner_connection, a) if parent == "contact" else _company(owner_connection, a)
    key = f"{parent}_id"
    note = _note(owner_connection, a, **{key: record})
    _activity(owner_connection, a, **{key: record}, kind="note_added", note_id=note)
    _activity(owner_connection, a, **{key: record}, kind="created")
    owner_connection.execute(
        sql.SQL("DELETE FROM {} WHERE id = %s").format(_table(parent)), (record,)
    )
    for table in ("note", "activity"):
        row = owner_connection.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE {} = %s").format(
                _table(table), sql.Identifier(key)
            ),
            (record,),
        ).fetchone()
        assert row == (0,)


def test_the_runtime_role_can_delete_a_record_with_history(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    """The cascades run although the runtime role holds no UPDATE on
    `activity`: permanent record deletion keeps working (D6)."""
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        contact = _contact(runtime, a)
        note = _note(runtime, a, contact_id=contact)
        _activity(runtime, a, contact_id=contact, kind="note_added", note_id=note)
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        assert _visible(runtime, "note") == 0
        assert _visible(runtime, "activity") == 0


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_notes_and_activity_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        company = _company(owner_connection, tenant)
        contact = _contact(owner_connection, tenant, company_id=company)
        for key, record in (("contact_id", contact), ("company_id", company)):
            note = _note(owner_connection, tenant, **{key: record})
            _activity(owner_connection, tenant, **{key: record}, kind="note_added", note_id=note)
            _activity(owner_connection, tenant, **{key: record}, kind="created")

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("activity", "note", "contact", "company"):
        assert _count(owner_connection, table, target["tenant"]) == 0
    assert _count(owner_connection, "activity", other) == 4
    assert _count(owner_connection, "note", other) == 2


# --- Backfill and rollback (last in this module) ---------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0002_contacts_companies')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_backfills_created_entries_and_rolls_back(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0002 (dropping `note` and `activity` with their rows),
    writes records as they existed before 3B, then upgrades: each existing
    record gets exactly one `created` entry with its own time and creator
    (D7). Leaves the schema as the other tests need it."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        assert {name for (name,) in owner_connection.execute(_TABLES).fetchall()} == {
            "company",
            "contact",
        }
        a = _workspace(env)["tenant"]
        creator = uuid.uuid4()
        when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        company = _company(owner_connection, a, created_by_user_id=creator, created_at=when)
        contact = _contact(owner_connection, a, created_by_user_id=creator, created_at=when)
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    assert {name for (name,) in owner_connection.execute(_TABLES).fetchall()} == {
        "company",
        "contact",
        "note",
        "activity",
        "workspace_settings",
        "invitation_intent",
    }
    for key, record in (("company_id", company), ("contact_id", contact)):
        rows = owner_connection.execute(
            sql.SQL(
                "SELECT tenant_id, kind, actor_user_id, occurred_at FROM crm_app.activity"
                " WHERE {} = %s"
            ).format(sql.Identifier(key)),
            (record,),
        ).fetchall()
        assert rows == [(uuid.UUID(a), "created", creator, when)]
