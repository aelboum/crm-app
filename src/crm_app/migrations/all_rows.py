"""Data changes in migrations under forced Row-Level Security (decision M-RLS).

Every tenant table forces RLS, which applies to the table's owner too. A
migration runs as the migration owner (`MIGRATIONS_DATABASE_URL`), which on
a managed PostgreSQL is no superuser and cannot bypass RLS; with no tenant
context, its `UPDATE`, `INSERT ... SELECT` or `DELETE` on a tenant table
sees no rows and silently changes nothing. Local development and CI used to
migrate as a superuser, which RLS never applies to, and hid this.

`all_rows` lets the owner, and only the owner, see every row of the named
tables for the statements inside it:

    with all_rows(f"{SCHEMA}.email_message"):
        op.execute(f"UPDATE {SCHEMA}.email_message SET ...")

- It turns `FORCE ROW LEVEL SECURITY` off for each table, runs the block,
  and turns it on again. RLS stays enabled throughout, so it still applies
  to every role that does not own the table: the application never sees
  another tenant's rows, whichever role runs the migration.
- `ALTER TABLE` holds an ACCESS EXCLUSIVE lock to the end of the
  transaction, and `crm_app.migrations.env` runs every migration in one
  transaction: nothing else reads or writes these tables meanwhile, and a
  failure rolls the setting back with everything else.
- Each table must force RLS when the block starts, or the migration fails:
  the block never turns forcing on for a table that did not have it.
- A role that does not own the table cannot use it (`ALTER TABLE` fails),
  so it never widens anyone's access.

The alternative, a role with BYPASSRLS, was rejected: a managed service's
admin usually cannot create one ("Only roles with the BYPASSRLS attribute
may create roles with the BYPASSRLS attribute", PostgreSQL 16).
A per-workspace loop with `app.tenant_id` (migration 0003) stays valid.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from alembic import op

# A schema-qualified name built from this project's own constants.
_TABLE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def _must_force(table: str) -> str:
    return f"""
DO $$
BEGIN
    IF NOT (SELECT relforcerowsecurity FROM pg_class WHERE oid = '{table}'::regclass) THEN
        RAISE EXCEPTION 'all_rows: % does not force row-level security', '{table}';
    END IF;
END
$$
"""


@contextmanager
def all_rows(*tables: str) -> Iterator[None]:
    """The migration owner sees every row of `tables` inside the block."""
    if not tables:
        raise ValueError("all_rows needs at least one table")
    for table in tables:
        if not _TABLE.match(table):
            raise ValueError(f"all_rows: {table!r} is not a schema-qualified table name")
    for table in tables:
        op.execute(_must_force(table))
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    yield
    # Not in a `finally`: after a failure the transaction is aborted and
    # rolls back, restoring FORCE with it.
    for table in tables:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
