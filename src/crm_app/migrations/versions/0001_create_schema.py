"""Create the product's own schema.

Revision ID: 0001_crm_app_schema
Revises:
Create Date: 2026-10-20

The product's tables live in the `crm_app` schema, never in `core`
(SaaS-OS ADR-0016). The restricted application role receives USAGE on the
schema and nothing wider: no CREATE, and no default privileges. Each table
added later grants SELECT, INSERT, UPDATE, DELETE on itself explicitly and
enables forced Row-Level Security with
`saas_os.infra.db.tenant_rls_statements` in the same migration, so no table
is ever readable before its policy exists.
"""

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0001_crm_app_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def upgrade() -> None:
    app_role = _app_role()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC")
    op.execute(f'GRANT USAGE ON SCHEMA {SCHEMA} TO "{app_role}"')


def downgrade() -> None:
    app_role = _app_role()
    op.execute(f'REVOKE USAGE ON SCHEMA {SCHEMA} FROM "{app_role}"')
    # RESTRICT: refuses to drop a schema that still holds product tables.
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} RESTRICT")
