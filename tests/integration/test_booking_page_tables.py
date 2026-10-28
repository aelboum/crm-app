"""The booking_page and booking tables (migration 0016; decision P5-C, slice
5C).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges and purge coverage from the
catalogs. These tests prove the behaviour: what the runtime role can see and
write, the composite links with RLS bypassed, the value rules, what goes
with an appointment and what outlives a page or a contact, the widened
contact source, the real purge and the migration's rollback.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_appointment_tables import _appointment
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


def _page(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "name": "Intro call",
        "public_key": secrets.token_urlsafe(16),
        "host_user_id": uuid.uuid4(),
        **values,
    }
    return _insert(connection, "booking_page", row)


def _booking(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "outcome": "created",
        "token_hash": hashlib.sha256(secrets.token_bytes(16)).hexdigest(),
        **values,
    }
    if "appointment_id" not in row:
        row["appointment_id"] = _appointment(connection, tenant)
    return _insert(connection, "booking", row)


def test_pages_and_bookings_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        _booking(runtime, a, booking_page_id=_page(runtime, a))
    for table in ("booking_page", "booking"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _page(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        _page(runtime, b)  # no workspace set at all


@pytest.mark.parametrize("link", ["booking_page_id", "appointment_id", "contact_id"])
def test_a_booking_links_only_inside_its_own_workspace(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    link: str,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    other = {
        "booking_page_id": lambda: _page(owner_connection, b),
        "appointment_id": lambda: _appointment(owner_connection, b),
        "contact_id": lambda: _contact(owner_connection, b),
    }[link]()
    with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
        _booking(owner_connection, a, **{link: other})


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": " Padded"},
        {"name": "x" * 121},
        {"description": ""},
        {"description": "tab\there"},
        {"description": "x" * 1001},
        {"status": "live"},
        {"public_key": "short"},
        {"length_minutes": 20},
        {"step_minutes": 10},
        {"kind": "carrier_pigeon"},
        {"location": " Room 2"},
        {"notice_minutes": -1},
        {"notice_minutes": 7 * 24 * 60 + 1},
        {"horizon_days": 0},
        {"horizon_days": 91},
        {"booking_count": -1},
    ],
)
def test_pages_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _page(owner_connection, a, **values)


@pytest.mark.parametrize("values", [{"outcome": "guessed"}, {"token_hash": "not-a-hash"}])
def test_bookings_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _booking(owner_connection, a, **values)


def test_one_booking_per_appointment_and_unique_tokens(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    appointment = _appointment(owner_connection, a)
    _booking(owner_connection, a, appointment_id=appointment)
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _booking(owner_connection, a, appointment_id=appointment)
    digest = hashlib.sha256(secrets.token_bytes(16)).hexdigest()
    _booking(owner_connection, a, token_hash=digest)
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _booking(owner_connection, b, token_hash=digest)
    key = secrets.token_urlsafe(16)
    _page(owner_connection, a, public_key=key)
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _page(owner_connection, b, public_key=key)


def test_a_booking_goes_with_its_appointment_and_outlives_its_page_and_contact(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        page, contact = _page(runtime, a), _contact(runtime, a)
        appointment = _appointment(runtime, a, contact_id=contact)
        kept = _booking(
            runtime, a, booking_page_id=page, contact_id=contact, appointment_id=appointment
        )
        runtime.execute("DELETE FROM crm_app.booking_page WHERE id = %s", (page,))
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        row = runtime.execute(
            "SELECT tenant_id, booking_page_id, contact_id FROM crm_app.booking WHERE id = %s",
            (kept,),
        ).fetchone()
        assert row == (uuid.UUID(a), None, None)
        runtime.execute("DELETE FROM crm_app.appointment WHERE id = %s", (appointment,))
        assert _visible(runtime, "booking") == 0


def test_contacts_may_come_from_a_booking(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    _contact(owner_connection, a, source="booking")
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _contact(owner_connection, a, source="walk_in")


def test_the_operator_purge_removes_pages_and_bookings_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        page = _page(owner_connection, tenant)
        _booking(
            owner_connection,
            tenant,
            booking_page_id=page,
            contact_id=_contact(owner_connection, tenant),
        )

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("booking_page", "booking"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0015_business_hours')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0015 (dropping both tables, turning booking sources into
    `other` and giving visitor cancellations the host), then upgrades,
    leaving the schema as the other tests need it."""
    a = _workspace(env)["tenant"]
    contact = _contact(owner_connection, a, source="booking")
    host = uuid.uuid4()
    cancelled = _appointment(
        owner_connection,
        a,
        host_user_id=host,
        status="cancelled",
        cancelled_at="2026-10-28T10:00:00Z",
    )
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not {"booking_page", "booking"} & tables
        assert {"appointment", "contact"} <= tables
        source = owner_connection.execute(
            "SELECT source FROM crm_app.contact WHERE id = %s", (contact,)
        ).fetchone()
        assert source == ("other",)
        by = owner_connection.execute(
            "SELECT cancelled_by_user_id FROM crm_app.appointment WHERE id = %s", (cancelled,)
        ).fetchone()
        assert by == (host,)
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert {"booking_page", "booking"} <= tables
