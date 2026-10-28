"""The contact and company tables (migration 0002; `PHASE3-PLAN.md` §19.2).

The structural guards (`test_tenant_table_guard.py`) already prove forced
RLS, the platform policy, the runtime role's privileges and purge coverage
from the catalogs. These tests prove the behaviour: what the runtime role
can see and write under each workspace setting, the composite foreign key
with RLS bypassed, the constraints behind decisions P3-A 3 and 4, the real
purge through the installed operator command, and the migration's rollback.

Rows are written with plain SQL as the runtime role (`DATABASE_URL`),
setting `app.tenant_id` the way `tenant_session_scope` does, or as the
migration role, which bypasses RLS, where a test needs that. Workspaces are
created by `purge_probe` through public SaaS-OS calls. Everything runs in the
disposable integration database.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from psycopg import errors, sql

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.conftest import libpq_url
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _probe, _status
from tests.support import REPO_ROOT, run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")

MIGRATIONS_DIR = REPO_ROOT / "src" / "crm_app" / "migrations"


# History entries naming fields that later migrations allowed (0007 `tags`,
# 0008 `custom_fields`): an older rule refuses them, and a downgrade fails
# rather than delete them, so a rollback test removes them first. Other
# test modules may have written them in the same database.
NEWER_HISTORY = "DELETE FROM crm_app.activity WHERE fields ?| array['tags', 'custom_fields']"


@pytest.fixture
def env(integration_env: dict[str, str]) -> dict[str, str]:
    return dict(integration_env)


@pytest.fixture
def runtime(env: dict[str, str]) -> Iterator[psycopg.Connection]:
    with psycopg.connect(libpq_url(env["DATABASE_URL"]), autocommit=True) as connection:
        yield connection


@contextmanager
def _as_workspace(connection: psycopg.Connection, tenant: object) -> Iterator[None]:
    """One transaction scoped like `tenant_session_scope`: `app.tenant_id`
    set transaction-locally."""
    with connection.transaction():
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant),))
        yield


def _workspace(env: dict[str, str], *, deleted: bool = False) -> dict[str, str]:
    return {k: str(v) for k, v in _probe(env, "deleted" if deleted else "active").items()}


def _table(table: str) -> sql.Identifier:
    return sql.Identifier("crm_app", table)


def _insert(connection: psycopg.Connection, table: str, row: dict[str, object]) -> uuid.UUID:
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        _table(table),
        sql.SQL(", ").join(map(sql.Identifier, row)),
        sql.SQL(", ").join(map(sql.Placeholder, row)),
    )
    connection.execute(statement, row)
    return row["id"]  # type: ignore[return-value]


def _visible(connection: psycopg.Connection, table: str) -> int:
    row = connection.execute(sql.SQL("SELECT count(*) FROM {}").format(_table(table))).fetchone()
    assert row is not None
    return int(row[0])


def _company(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    return _insert(
        connection,
        "company",
        {"id": uuid.uuid4(), "tenant_id": tenant, "name": "Example Ltd", **values},
    )


def _contact(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "first_name": "Sam",
        "email": f"sam.{uuid.uuid4().hex[:8]}@example.test",
        **values,
    }
    return _insert(connection, "contact", row)


def _count(connection: psycopg.Connection, table: str, tenant: object) -> int:
    row = connection.execute(
        sql.SQL("SELECT count(*) FROM {} WHERE tenant_id = %s").format(_table(table)), (tenant,)
    ).fetchone()
    assert row is not None
    return int(row[0])


# --- Row-level security, as the runtime role ----------------------------------


def test_rows_are_visible_only_inside_their_own_workspace(
    env: dict[str, str], runtime: psycopg.Connection
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        company = _company(runtime, a)
        _contact(runtime, a, company_id=company)

    for table in ("company", "contact"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


@pytest.mark.parametrize("table", ["company", "contact"])
def test_the_runtime_role_cannot_write_another_workspaces_rows(
    env: dict[str, str], runtime: psycopg.Connection, table: str
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    insert = _company if table == "company" else _contact
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        insert(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        insert(runtime, b)  # no workspace set at all


def test_updates_cannot_move_a_row_to_another_workspace(
    env: dict[str, str], runtime: psycopg.Connection
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        company = _company(runtime, a)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute("UPDATE crm_app.company SET tenant_id = %s WHERE id = %s", (b, company))


# --- Composite foreign key, with RLS bypassed ---------------------------------


def test_a_contact_cannot_link_to_another_workspaces_company(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    company_a = _company(owner_connection, a)
    with pytest.raises(errors.ForeignKeyViolation):
        _contact(owner_connection, b, company_id=company_a)


def test_deleting_a_company_unlinks_its_contacts_and_keeps_them(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    a = _workspace(env)["tenant"]
    company = _company(owner_connection, a)
    contact = _contact(owner_connection, a, company_id=company)
    owner_connection.execute("DELETE FROM crm_app.company WHERE id = %s", (company,))
    row = owner_connection.execute(
        "SELECT tenant_id, company_id FROM crm_app.contact WHERE id = %s", (contact,)
    ).fetchone()
    assert row == (uuid.UUID(a), None)


# --- Constraints behind P3-A --------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"email": None, "phone": None},  # P3-A 4: email or phone
        {"email": "Upper@Example.test"},  # stored normalised only
        {"email": " sam@example.test"},
        {"email": "no-at-sign"},
        {"first_name": " Sam"},
        {"first_name": ""},
        {"last_name": ""},  # optional text is NULL, never ''
        {"lifecycle_stage": "patient"},  # P3-A 1
        {"source": "web"},  # P3-A 2
        {"phone": "1" * 33},
    ],
)
def test_contact_values_outside_the_rules_are_refused(
    env: dict[str, str], owner_connection: psycopg.Connection, values: dict[str, object]
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation):
        _contact(owner_connection, a, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": "x" * 201},
        {"domain": "Example.test"},
        {"domain": "example"},
        {"domain": "-bad.test"},
        {"website": "ftp://example.test"},
        {"website": "javascript:alert(1)"},
        {"country_code": "nl"},
    ],
)
def test_company_values_outside_the_rules_are_refused(
    env: dict[str, str], owner_connection: psycopg.Connection, values: dict[str, object]
) -> None:
    a = _workspace(env)["tenant"]
    with pytest.raises(errors.CheckViolation):
        _company(owner_connection, a, **values)


def test_a_phone_alone_and_an_email_alone_are_both_enough(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    a = _workspace(env)["tenant"]
    _contact(owner_connection, a, email=None, phone="+31 20 123 4567")
    _contact(owner_connection, a, email="only.email@example.test", phone=None)


def test_an_active_email_is_unique_per_workspace_and_archived_ones_do_not_block(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    first = _contact(owner_connection, a, email="dup@example.test")
    with pytest.raises(errors.UniqueViolation) as raised:
        _contact(owner_connection, a, email="dup@example.test")
    assert raised.value.diag.constraint_name == "contact_active_email_key"
    _contact(owner_connection, b, email="dup@example.test")  # other workspace
    owner_connection.execute(
        "UPDATE crm_app.contact SET archived_at = now() WHERE id = %s", (first,)
    )
    _contact(owner_connection, a, email="dup@example.test")  # archived does not block
    with pytest.raises(errors.UniqueViolation):  # restoring the archived one would collide
        owner_connection.execute(
            "UPDATE crm_app.contact SET archived_at = NULL WHERE id = %s", (first,)
        )


def test_an_active_domain_is_unique_per_workspace_and_names_may_repeat(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    a = _workspace(env)["tenant"]
    first = _company(owner_connection, a, name="Same Name", domain="dup.example.test")
    _company(owner_connection, a, name="Same Name")
    with pytest.raises(errors.UniqueViolation) as raised:
        _company(owner_connection, a, domain="dup.example.test")
    assert raised.value.diag.constraint_name == "company_active_domain_key"
    owner_connection.execute(
        "UPDATE crm_app.company SET archived_at = now() WHERE id = %s", (first,)
    )
    _company(owner_connection, a, domain="dup.example.test")


# --- Purge through the installed operator command ----------------------------


def test_the_operator_purge_removes_contacts_and_companies_of_that_workspace_only(
    env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        company = _company(owner_connection, tenant)
        _contact(owner_connection, tenant, company_id=company)
        _contact(owner_connection, tenant, email=None, phone="+31 6 1234 5678")

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    assert _count(owner_connection, "contact", target["tenant"]) == 0
    assert _count(owner_connection, "company", target["tenant"]) == 0
    assert _count(owner_connection, "contact", other) == 2
    assert _count(owner_connection, "company", other) == 1

    again = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)
    assert again.returncode == 0, again.stderr
    assert json.loads(again.stdout)["result"]["already_purged"] is True


# --- Rollback -------------------------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0001_crm_app_schema')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str], owner_connection: psycopg.Connection, tmp_path: Path
) -> None:
    """Last in this module: drops every product table (and its rows), then
    applies the migrations again, leaving the schema as the other tests need
    it."""
    owner_connection.execute(NEWER_HISTORY)
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        assert owner_connection.execute(_TABLES).fetchall() == []
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
        "signup",
        "signup_attempt",
        "tag",
        "contact_tag",
        "company_tag",
        "custom_field_definition",
        "import_job",
        "import_row",
        "import_expiry",
        "pipeline",
        "pipeline_stage",
        "opportunity",
        "opportunity_event",
        "task",
        "appointment",
        "form",
        "form_submission",
        "consent_record",
    }
