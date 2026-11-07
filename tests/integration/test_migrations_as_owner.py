"""Migrations as a managed PostgreSQL runs them: by an owner that is no
superuser and cannot bypass Row-Level Security (decision M-RLS).

CI's and local development's migration role is a superuser, which RLS never
applies to, so the other integration tests cannot see a data change that
silently touches no rows. This module creates a fresh database owned by a
NOSUPERUSER NOBYPASSRLS role and, as that role:

1. applies both migration histories from scratch;
2. shows the problem and the fix on real rows: without `all_rows` an UPDATE
   on a tenant table changes nothing, with it every row, and the table
   forces RLS again afterwards;
3. downgrades the product's history to its base and applies it again, so
   every data change in every downgrade runs as that owner too.

The database and the role are dropped afterwards.
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from tests.integration.conftest import libpq_url
from tests.support import REPO_ROOT, run_module, run_python

MIGRATIONS_DIR = REPO_ROOT / "src" / "crm_app" / "migrations"


def _url(base: str, user: str, password: str, database: str) -> str:
    parts = urlsplit(base)
    netloc = f"{user}:{password}@{parts.hostname}:{parts.port}"
    return urlunsplit(parts._replace(netloc=netloc, path=f"/{database}"))


@pytest.fixture(scope="module")
def owner_database(
    integration_env: dict[str, str], owner_connection: psycopg.Connection
) -> Iterator[dict[str, str]]:
    """A fresh database owned by a role that is no superuser and cannot
    bypass RLS; the environment that migrates it as that role."""
    suffix = secrets.token_hex(4)
    role = database = f"crm_app_owner_check_{suffix}"
    password = secrets.token_urlsafe(16)
    admin = owner_connection
    admin.execute(
        sql.SQL(
            "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        ).format(sql.Identifier(role), sql.Literal(password))
    )
    # Created by an operator before the first migration (SaaS-OS RUNBOOKS),
    # so the owner needs no CREATEROLE; roles are shared by every database.
    admin.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles"
        " WHERE rolname = 'saas_os_platform_config') THEN"
        " CREATE ROLE saas_os_platform_config NOLOGIN; END IF; END $$"
    )
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(database), sql.Identifier(role)
        )
    )
    admin.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(integration_env["APP_DB_USER"])
        )
    )
    runtime = urlsplit(integration_env["DATABASE_URL"])
    env = {
        **integration_env,
        "MIGRATIONS_DATABASE_URL": _url(
            integration_env["MIGRATIONS_DATABASE_URL"], role, password, database
        ),
        "DATABASE_URL": urlunsplit(runtime._replace(path=f"/{database}")),
    }
    try:
        yield env
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@pytest.fixture(scope="module")
def migrated_as_owner(
    owner_database: dict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> dict[str, str]:
    cwd = tmp_path_factory.mktemp("owner-migrate")
    result = run_module("crm_app.migrate", [], owner_database, cwd)
    assert result.returncode == 0, f"migrating as the owner failed:\n{result.stderr[-3000:]}"
    return owner_database


def test_the_owner_is_no_superuser_and_cannot_bypass_rls(
    migrated_as_owner: dict[str, str],
) -> None:
    with psycopg.connect(libpq_url(migrated_as_owner["MIGRATIONS_DATABASE_URL"])) as owner:
        row = owner.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    assert row == (False, False)


# Run as the owner, inside an Alembic operations context, as a migration is.
_BACKFILL = """
import json
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from saas_os.infra.db import get_migrations_database_config
from sqlalchemy import create_engine, text
from crm_app.migrations.all_rows import all_rows

engine = create_engine(get_migrations_database_config().url)
with engine.begin() as connection:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        bare = connection.execute(text("UPDATE crm_app.tag SET name = name || ' bare'")).rowcount
        with all_rows("crm_app.tag"):
            wrapped = connection.execute(
                text("UPDATE crm_app.tag SET name = name || ' wrapped'")
            ).rowcount
        forced = connection.execute(text(
            "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'crm_app.tag'::regclass"
        )).scalar()
print("RESULT " + json.dumps({"bare": bare, "wrapped": wrapped, "forced": forced}))
"""


def _seed_tags(superuser_url: str, database: str) -> None:
    """One tag in each of two workspaces, written by the superuser, which RLS
    does not stop."""
    url = urlunsplit(urlsplit(libpq_url(superuser_url))._replace(path=f"/{database}"))
    with psycopg.connect(url, autocommit=True) as seeded:
        for name in ("one", "two"):
            tenant = uuid.uuid4()
            seeded.execute(
                "INSERT INTO core.tenants (id, name, status, inherits_billing)"
                " VALUES (%s, %s, 'active', false)",
                (tenant, f"owner-check-{name}-{tenant.hex[:6]}"),
            )
            seeded.execute(
                "INSERT INTO crm_app.tag (id, tenant_id, name) VALUES (%s, %s, %s)",
                (uuid.uuid4(), tenant, f"tag {name}"),
            )


def test_a_data_change_reaches_every_row_only_inside_all_rows(
    migrated_as_owner: dict[str, str], integration_env: dict[str, str], tmp_path: Path
) -> None:
    database = urlsplit(migrated_as_owner["MIGRATIONS_DATABASE_URL"]).path.lstrip("/")
    _seed_tags(integration_env["MIGRATIONS_DATABASE_URL"], database)
    result = run_python(_BACKFILL, migrated_as_owner, tmp_path)
    assert result.returncode == 0, result.stderr[-3000:]
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    found = json.loads(line.removeprefix("RESULT "))
    # Forced RLS, no tenant context: the owner sees nothing. The problem.
    assert found["bare"] == 0
    # The fix: both workspaces' rows, and forcing restored afterwards.
    assert found["wrapped"] == 2
    assert found["forced"] is True


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, 'base')\n"
)


def test_every_downgrade_and_upgrade_runs_as_the_owner(
    migrated_as_owner: dict[str, str], tmp_path: Path
) -> None:
    """Last in this module: every product data change in both directions,
    as the owner, against a database holding rows (the tags above)."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), migrated_as_owner, tmp_path)
    assert down.returncode == 0, down.stderr[-3000:]
    up = run_module("crm_app.migrate", [], migrated_as_owner, tmp_path)
    assert up.returncode == 0, up.stderr[-3000:]
