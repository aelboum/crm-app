"""Structural guards for the product schema, read from the PostgreSQL catalogs.

The product schema holds exactly the approved tables (`tests/support.py`
`PRODUCT_TABLES`; P3-A: `company`, `contact`; P3-B: `note`, `activity`), and
every tenant-owned one meets the rules in `tests/catalog_rules.py`
(`activity` is append-only: its runtime role must lack UPDATE). These tests
read structure only; runtime isolation is proven in `test_crm_tables.py` and
`test_note_activity_tables.py`.

Facts come from `pg_namespace`, `pg_class`, `pg_attribute` and `pg_policy`,
and privileges from `has_table_privilege` for the configured runtime role.
Unlike `information_schema`, these do not hide rows from the querying role
or omit grants made by another grantor. The self-tests at the end run the
same queries and rules against a table SaaS-OS protects the same way
(`core.role_permissions`), so the guard is shown to work independently of
the product's own tables.
"""

from __future__ import annotations

import psycopg
import pytest

from crm_app.permissions import PERMISSIONS
from tests.catalog_rules import (
    CHECKED_PRIVILEGES,
    Policy,
    classification_violations,
    global_policy_violations,
    global_reference_violations,
    policy_violations,
    privilege_violations,
    purge_violations,
    rls_violations,
)
from tests.support import (
    APPEND_ONLY_TABLES,
    GLOBAL_TABLES,
    PERSON_SCOPED_TABLES,
    PRODUCT_TABLES,
    PURGE_COVERED_TABLES,
    PURGE_GLOBAL_COVERED_TABLES,
)

SCHEMA = "crm_app"
# A platform table created with `tenant_rls_statements` (SaaS-OS migration
# 81ac56902107), used only to self-test the queries and rules below.
REFERENCE_SCHEMA, REFERENCE_TABLE = "core", "role_permissions"

pytestmark = pytest.mark.usefixtures("migrated")


def _relations(connection: psycopg.Connection, schema: str, kinds: str) -> set[str]:
    rows = connection.execute(
        "SELECT c.relname FROM pg_catalog.pg_class c"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND c.relkind = ANY(%s)",
        (schema, list(kinds)),
    ).fetchall()
    return {name for (name,) in rows}


def _tables(connection: psycopg.Connection, schema: str) -> set[str]:
    """Ordinary and partitioned tables (partitions are ordinary tables)."""
    return _relations(connection, schema, "rp")


def _tenant_tables(connection: psycopg.Connection, schema: str) -> set[str]:
    rows = connection.execute(
        "SELECT c.relname FROM pg_catalog.pg_class c"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid"
        " WHERE n.nspname = %s AND c.relkind IN ('r', 'p')"
        " AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped",
        (schema,),
    ).fetchall()
    return {name for (name,) in rows}


def _rls_flags(connection: psycopg.Connection, schema: str, table: str) -> tuple[bool, bool]:
    row = connection.execute(
        "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_catalog.pg_class c"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND c.relname = %s",
        (schema, table),
    ).fetchone()
    assert row is not None, f"{schema}.{table} not found in pg_class"
    return bool(row[0]), bool(row[1])


def _policies(connection: psycopg.Connection, schema: str, table: str) -> list[Policy]:
    rows = connection.execute(
        "SELECT p.polname, p.polcmd, p.polpermissive,"
        " ARRAY(SELECT CASE WHEN r = 0 THEN 'public' ELSE r::regrole::text END"
        "       FROM unnest(p.polroles) AS r ORDER BY 1),"
        " pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)"
        " FROM pg_catalog.pg_policy p"
        " JOIN pg_catalog.pg_class c ON c.oid = p.polrelid"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND c.relname = %s ORDER BY p.polname",
        (schema, table),
    ).fetchall()
    return [
        Policy(name, str(command), bool(permissive), tuple(roles), using, with_check)
        for name, command, permissive, roles, using, with_check in rows
    ]


def _privileges(
    connection: psycopg.Connection, role: str, schema: str, table: str
) -> dict[str, bool]:
    qualified = f'"{schema}"."{table}"'
    held: dict[str, bool] = {}
    for privilege in CHECKED_PRIVILEGES:
        row = connection.execute(
            "SELECT has_table_privilege(%s, %s::regclass, %s)", (role, qualified, privilege)
        ).fetchone()
        assert row is not None, f"no privilege answer for {qualified}"
        held[privilege] = bool(row[0])
    return held


@pytest.fixture(scope="module")
def runtime_role(integration_env: dict[str, str], owner_connection: psycopg.Connection) -> str:
    role = integration_env.get("APP_DB_USER", "")
    assert role, "APP_DB_USER is not set: the runtime role cannot be identified"
    exists = owner_connection.execute(
        "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (role,)
    ).fetchone()
    assert exists == (1,), f"runtime role {role!r} does not exist in this database"
    return role


# --- The product schema --------------------------------------------------


def test_the_product_schema_exists(owner_connection: psycopg.Connection) -> None:
    """Without it every other check here would pass vacuously."""
    row = owner_connection.execute(
        "SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s", (SCHEMA,)
    ).fetchone()
    assert row == (1,), f"schema {SCHEMA} is missing: were the migrations applied?"


def test_the_product_schema_holds_only_approved_tables(
    owner_connection: psycopg.Connection,
) -> None:
    assert _tables(owner_connection, SCHEMA) == set(PRODUCT_TABLES)


def test_the_product_schema_holds_no_views_or_foreign_tables(
    owner_connection: psycopg.Connection,
) -> None:
    """A view runs with its owner's rights and could read past RLS."""
    assert _relations(owner_connection, SCHEMA, "vmf") == set()


def test_every_product_table_is_tenant_owned_or_declared_global(
    owner_connection: psycopg.Connection,
) -> None:
    """Tenant tables are recognised by their `tenant_id`; this stops a table
    that keeps tenant data under another name from escaping the RLS and
    purge checks below."""
    tables = _tables(owner_connection, SCHEMA)
    tenant_tables = _tenant_tables(owner_connection, SCHEMA)
    assert classification_violations(tables, tenant_tables, GLOBAL_TABLES) == []


def test_every_tenant_table_has_forced_rls_and_the_platform_policy(
    owner_connection: psycopg.Connection,
) -> None:
    problems: list[str] = []
    for table in sorted(_tenant_tables(owner_connection, SCHEMA)):
        enabled, forced = _rls_flags(owner_connection, SCHEMA, table)
        problems += rls_violations(table, enabled=enabled, forced=forced)
        problems += policy_violations(table, _policies(owner_connection, SCHEMA, table))
    assert problems == []


def _has_column(connection: psycopg.Connection, schema: str, table: str, column: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM pg_catalog.pg_attribute a"
        " JOIN pg_catalog.pg_class c ON c.oid = a.attrelid"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s"
        " AND a.attnum > 0 AND NOT a.attisdropped",
        (schema, table, column),
    ).fetchone()
    return row is not None


def _references_tenants(connection: psycopg.Connection, schema: str, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM pg_catalog.pg_constraint k"
        " JOIN pg_catalog.pg_class c ON c.oid = k.conrelid"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND c.relname = %s AND k.contype = 'f'"
        " AND k.confrelid = 'core.tenants'::regclass",
        (schema, table),
    ).fetchone()
    return row is not None


def test_every_global_table_has_forced_rls_and_exactly_its_policies(
    owner_connection: psycopg.Connection,
) -> None:
    """A table is global only with SaaS-OS's tenant-context exclusion policy
    (no tenant transaction can reach it) and, if person-scoped, the
    restrictive owner policies (decision S-1, option A)."""
    problems: list[str] = []
    for table in sorted(GLOBAL_TABLES):
        enabled, forced = _rls_flags(owner_connection, SCHEMA, table)
        problems += rls_violations(table, enabled=enabled, forced=forced)
        problems += global_policy_violations(
            table,
            _policies(owner_connection, SCHEMA, table),
            person_scoped=table in PERSON_SCOPED_TABLES,
        )
    assert problems == []


def test_a_global_table_naming_a_workspace_is_purged_and_never_blocks_purge(
    owner_connection: psycopg.Connection,
) -> None:
    problems: list[str] = []
    for table in sorted(GLOBAL_TABLES):
        problems += global_reference_violations(
            table,
            names_workspace=_has_column(owner_connection, SCHEMA, table, "workspace_id"),
            references_tenants=_references_tenants(owner_connection, SCHEMA, table),
            purge_covered=table in PURGE_GLOBAL_COVERED_TABLES,
        )
    assert problems == []
    assert _has_column(owner_connection, SCHEMA, "signup", "workspace_id")


def test_the_runtime_role_holds_exactly_its_privileges_on_every_product_table(
    runtime_role: str, owner_connection: psycopg.Connection
) -> None:
    problems: list[str] = []
    for table in sorted(_tables(owner_connection, SCHEMA)):
        held = _privileges(owner_connection, runtime_role, SCHEMA, table)
        problems += privilege_violations(table, held, append_only=table in APPEND_ONLY_TABLES)
    assert problems == []


def test_every_tenant_table_is_covered_by_tenant_purge(
    owner_connection: psycopg.Connection,
) -> None:
    """`PURGE_COVERED_TABLES` is the purge participant's manifest
    (`crm_app.purge.PURGE_TABLES`), so a tenant-owned table the participant
    does not delete fails here."""
    tenant_tables = _tenant_tables(owner_connection, SCHEMA)
    assert purge_violations(tenant_tables, PURGE_COVERED_TABLES) == []


# --- Permission registration (S1b) ----------------------------------------


def test_the_migration_step_registered_every_granted_permission(
    owner_connection: psycopg.Connection,
) -> None:
    """`crm-app-migrate` (run by the `migrated` fixture) registers exactly
    the pairs the role templates grant (`crm_app.permissions.PERMISSIONS`)."""
    rows = owner_connection.execute(
        "SELECT resource, action FROM core.permissions WHERE starts_with(resource, 'crm_app.')"
    ).fetchall()
    registered_product = {(resource, action) for resource, action in rows}
    expected_product = {pair for pair in PERMISSIONS if pair[0].startswith("crm_app.")}
    assert registered_product == expected_product
    platform = [pair for pair in PERMISSIONS if not pair[0].startswith("crm_app.")]
    missing = [
        pair
        for pair in platform
        if owner_connection.execute(
            "SELECT 1 FROM core.permissions WHERE resource = %s AND action = %s", pair
        ).fetchone()
        is None
    ]
    assert missing == []


# --- Self-tests of the queries and rules on a SaaS-OS table ---------------


def test_the_tenant_table_query_finds_platform_tenant_tables(
    owner_connection: psycopg.Connection,
) -> None:
    found = _tenant_tables(owner_connection, REFERENCE_SCHEMA)
    assert {REFERENCE_TABLE, "tenant_memberships"} <= found
    assert found.isdisjoint(_tables(owner_connection, SCHEMA))


def test_the_rls_rules_accept_a_correctly_protected_table(
    owner_connection: psycopg.Connection,
) -> None:
    enabled, forced = _rls_flags(owner_connection, REFERENCE_SCHEMA, REFERENCE_TABLE)
    policies = _policies(owner_connection, REFERENCE_SCHEMA, REFERENCE_TABLE)
    assert rls_violations(REFERENCE_TABLE, enabled=enabled, forced=forced) == []
    assert policy_violations(REFERENCE_TABLE, policies) == []


def test_the_privilege_query_reports_every_checked_privilege(
    runtime_role: str, owner_connection: psycopg.Connection
) -> None:
    held = _privileges(owner_connection, runtime_role, REFERENCE_SCHEMA, REFERENCE_TABLE)
    assert set(held) == set(CHECKED_PRIVILEGES)
    assert held["SELECT"] is True  # the runtime role reads Core's RBAC tables
