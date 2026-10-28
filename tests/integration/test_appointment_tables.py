"""The appointment table (migration 0014; decision P5-A, slice 5A).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the composite contact link with RLS bypassed, the value rules, the
link cleared when the contact is deleted, the real purge through the
installed operator command, and the migration's rollback.
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
    _contact,
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


def _appointment(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "title": "Intro call",
        "starts_at": "2026-10-28T09:00:00Z",
        "ends_at": "2026-10-28T09:30:00Z",
        "host_user_id": uuid.uuid4(),
        **values,
    }
    return _insert(connection, "appointment", row)


def test_appointments_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _appointment(runtime, a)
    assert _visible(runtime, "appointment") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "appointment") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "appointment") == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _appointment(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        _appointment(runtime, b)  # no workspace set at all


def test_an_appointment_links_only_to_its_own_workspaces_contacts(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
        _appointment(owner_connection, a, contact_id=_contact(owner_connection, b))


@pytest.mark.parametrize(
    "values",
    [
        {"title": ""},
        {"title": " Padded"},
        {"title": "x" * 201},
        {"title": "line\nbreak"},
        {"ends_at": "2026-10-28T09:04:00Z"},
        {"ends_at": "2026-10-28T08:00:00Z"},
        {"ends_at": "2026-10-29T09:01:00Z"},
        {"kind": "carrier_pigeon"},
        {"location": ""},
        {"location": " Room 2"},
        {"location": "x" * 301},
        {"note": ""},
        {"note": "x" * 2001},
        {"status": "maybe"},
        {"status": "cancelled"},
        {"cancelled_at": "2026-10-28T10:00:00Z"},
        {"cancelled_by_user_id": uuid.UUID(int=7)},
    ],
    ids=[
        "empty-title",
        "padded-title",
        "long-title",
        "control-title",
        "too-short",
        "ends-before-start",
        "longer-than-a-day",
        "unknown-kind",
        "empty-location",
        "padded-location",
        "long-location",
        "empty-note",
        "long-note",
        "unknown-status",
        "cancelled-without-when",
        "when-without-cancelled",
        "who-without-cancelled",
    ],
)
def test_appointments_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _appointment(owner_connection, a, **values)


def test_a_cancelled_appointment_records_when_and_by_whom(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    _appointment(
        owner_connection,
        a,
        status="cancelled",
        cancelled_at="2026-10-28T10:00:00Z",
        cancelled_by_user_id=uuid.uuid4(),
    )
    assert _count(owner_connection, "appointment", a) == 1


def test_a_visitor_cancels_without_a_member(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    """Migration 0016 (P5-C 2): a visitor's cancellation has no member."""
    a = _workspace(env)["tenant"]
    _appointment(owner_connection, a, status="cancelled", cancelled_at="2026-10-28T10:00:00Z")
    assert _count(owner_connection, "appointment", a) == 1


def test_deleting_the_contact_keeps_the_appointment_without_the_link(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        contact = _contact(runtime, a)
        appointment = _appointment(runtime, a, contact_id=contact)
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        row = runtime.execute(
            "SELECT tenant_id, contact_id FROM crm_app.appointment WHERE id = %s",
            (appointment,),
        ).fetchone()
    assert row == (uuid.UUID(a), None)


def test_the_operator_purge_removes_appointments_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        _appointment(owner_connection, tenant, contact_id=_contact(owner_connection, tenant))

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    assert _count(owner_connection, "appointment", target["tenant"]) == 0
    assert _count(owner_connection, "appointment", other) == 1


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0013_forms')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0013 (dropping the appointment table and its rows),
    then upgrades, leaving the schema as the other tests need it."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert "appointment" not in tables
        assert {"form", "contact"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert "appointment" in tables
