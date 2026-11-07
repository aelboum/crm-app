"""Saved views of the contacts and deals lists (decision P3-SV).

Revision ID: 0041_saved_views
Revises: 0040_automation_notice
Create Date: 2026-11-07

`saved_view`: tenant-owned, forced Row-Level Security. One member's named
set of list filters for `contacts` or `opportunities`; only that member
reads or changes it (`crm_app.saved_views`). `filters` holds the list's
own filter values, checked against an allow-list before they are stored;
a name is unique per member and list, ignoring case. In
`crm_app.purge.PURGE_TABLES`. Downgrade drops the table: for test and
development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0041_saved_views"
down_revision: str | Sequence[str] | None = "0040_automation_notice"
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


TABLE = f"""
CREATE TABLE {SCHEMA}.saved_view (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    filters jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT saved_view_pkey PRIMARY KEY (tenant_id, id),
    CONSTRAINT saved_view_kind_check CHECK (kind IN ('contacts', 'opportunities')),
    CONSTRAINT saved_view_name_check CHECK (
        char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)
    ),
    CONSTRAINT saved_view_filters_check CHECK (jsonb_typeof(filters) = 'object')
)
"""

INDEX = (
    f"CREATE UNIQUE INDEX saved_view_name_key ON {SCHEMA}.saved_view"
    " (tenant_id, user_id, kind, lower(name))"
)


def upgrade() -> None:
    op.execute(TABLE)
    op.execute(INDEX)
    for statement in tenant_rls_statements("saved_view", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.saved_view TO "{_app_role()}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.saved_view")
