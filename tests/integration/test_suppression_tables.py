"""The suppression table and the widened consent records (migration 0017;
decision P7-B, slice 7B).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges (no UPDATE on either table)
and purge coverage from the catalogs. These tests prove the behaviour:
isolation, one address per workspace, the value rules, consent records
that may now be withdrawn or recorded by hand, the real purge and the
migration's rollback.
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
from tests.integration.test_form_tables import _consent
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _status
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")


def _suppression(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "email": f"sam.{uuid.uuid4().hex[:8]}@example.test",
        "reason": "manual",
        **values,
    }
    return _insert(connection, "suppression", row)


def test_suppressions_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _suppression(runtime, a)
    assert _visible(runtime, "suppression") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "suppression") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "suppression") == 1
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _suppression(runtime, b)


def test_one_address_per_workspace(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    _suppression(owner_connection, a, email="sam@example.test")
    _suppression(owner_connection, b, email="sam@example.test")
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _suppression(owner_connection, a, email="sam@example.test")


@pytest.mark.parametrize(
    "values",
    [
        {"email": "Sam@Example.test"},
        {"email": " sam@example.test"},
        {"email": "not-an-address"},
        {"reason": "annoyed"},
        {"origin": "import"},
        {"note": ""},
        {"note": "tab\there"},
        {"note": "x" * 501},
    ],
)
def test_suppressions_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _suppression(owner_connection, a, **values)


def test_suppressions_cannot_be_changed(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        row = _suppression(runtime, a)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("UPDATE crm_app.suppression SET reason = 'bounced' WHERE id = %s", (row,))


def test_consent_may_be_withdrawn_or_recorded_by_a_member(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    member = uuid.uuid4()
    _consent(owner_connection, a, contact, method="manual", recorded_by_user_id=member)
    _consent(owner_connection, a, contact, status="withdrawn", method="manual", wording=None)
    _consent(owner_connection, a, contact, status="withdrawn", method="manual", wording="By phone")
    assert _count(owner_connection, "consent_record", a) == 3
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _consent(owner_connection, a, contact, method="manual", wording=None)


def test_the_operator_purge_removes_suppressions_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        _suppression(owner_connection, tenant)

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    assert _count(owner_connection, "suppression", target["tenant"]) == 0
    assert _count(owner_connection, "suppression", other) == 1


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0016_booking_pages')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0016 (dropping the suppression table and the withdrawn
    and manual consent records), then upgrades, leaving the schema as the
    other tests need it."""
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a)
    kept = _consent(owner_connection, a, contact)
    dropped = _consent(owner_connection, a, contact, status="withdrawn", method="manual")
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert "suppression" not in tables
        ids = {
            row
            for (row,) in owner_connection.execute(
                "SELECT id FROM crm_app.consent_record WHERE contact_id = %s", (contact,)
            ).fetchall()
        }
        assert ids == {kept}
        assert dropped not in ids
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert "suppression" in tables
