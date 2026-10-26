"""Create the tag tables (Phase 3 slice 3C, decision P3-C).

Revision ID: 0007_tags
Revises: 0006_signup
Create Date: 2026-10-26

Three tenant-owned tables (`PHASE3-PLAN.md` §3.2), each with forced
Row-Level Security from `saas_os.infra.db.tenant_rls_statements` and
SELECT, INSERT, UPDATE, DELETE for the runtime role, in this same
migration, and each in `crm_app.purge.PURGE_TABLES`:

- `tag`: the workspace's tag vocabulary. A name is unique per workspace
  regardless of case; it is trimmed text of 1-50 characters without control
  characters. Tags have no colour: the design shows every tag as the same
  neutral pill (P3-C 2).
- `contact_tag`, `company_tag`: which tags a record carries. Every
  reference is composite, `(tenant_id, x_id) → (tenant_id, id)`, so a tag
  of one workspace can never be put on another's record, even with RLS
  bypassed. Deleting a record or a tag removes its assignments
  (`ON DELETE CASCADE`).

The history's `updated` entries may now also name `tags` (P3-C 5); the
new rule accepts every row the old one did. Alembic runs this migration in
one transaction, so dropping the old rule holds an ACCESS EXCLUSIVE lock on
`activity` until commit, through the validating scan (`NOT VALID` then
`VALIDATE` does not shorten it within one transaction). That is acceptable
while no production data exists; a later change to a large table must split
its steps across transactions.

Downgrade restores the old rule and drops the three tables with their rows:
for test and development databases only. It fails if a history entry names
`tags`, rather than deleting it.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0007_tags"
down_revision: str | Sequence[str] | None = "0006_signup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

TAG_NAME_MAX = 50

# Migration 0003's allow-list, and the same plus `tags`.
_UPDATED_FIELDS_0003 = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "job_title",
    "city",
    "source",
    "name",
    "domain",
    "website",
    "industry",
    "country_code",
)
UPDATED_FIELDS = (*_UPDATED_FIELDS_0003, "tags")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


TAG = f"""
CREATE TABLE {SCHEMA}.tag (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT tag_tenant_id_id_key UNIQUE (tenant_id, id),
    -- Trimmed, 1-{TAG_NAME_MAX} characters, no control characters.
    CONSTRAINT tag_name_check CHECK (
        char_length(name) BETWEEN 1 AND {TAG_NAME_MAX}
        AND name = btrim(name)
        AND name !~ '[\\x01-\\x1f\\x7f]'
    )
)
"""


def _assignment(table: str, parent: str) -> str:
    return f"""
CREATE TABLE {SCHEMA}.{table} (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    {parent}_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT {table}_pkey PRIMARY KEY (tenant_id, {parent}_id, tag_id),
    CONSTRAINT {table}_{parent}_fkey FOREIGN KEY (tenant_id, {parent}_id)
        REFERENCES {SCHEMA}.{parent} (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT {table}_tag_fkey FOREIGN KEY (tenant_id, tag_id)
        REFERENCES {SCHEMA}.tag (tenant_id, id) ON DELETE CASCADE
)
"""


INDEXES = (
    # One name per workspace, whatever its case.
    f"CREATE UNIQUE INDEX tag_name_key ON {SCHEMA}.tag (tenant_id, lower(name))",
    # The tag filter on the lists, and the cascade from a deleted tag.
    f"CREATE INDEX contact_tag_tag_idx ON {SCHEMA}.contact_tag (tenant_id, tag_id, contact_id)",
    f"CREATE INDEX company_tag_tag_idx ON {SCHEMA}.company_tag (tenant_id, tag_id, company_id)",
)


def _fields_rule(fields: Sequence[str]) -> str:
    """Migration 0003's `activity_fields_check` over `fields`."""
    allowed = ", ".join(f'"{name}"' for name in fields)
    return f"""(kind = 'updated') = (fields IS NOT NULL)
        AND (
            fields IS NULL OR (
                jsonb_typeof(fields) = 'array'
                AND jsonb_array_length(fields) BETWEEN 1 AND {len(fields)}
                AND fields <@ '[{allowed}]'::jsonb
            )
        )"""


def _replace_fields_rule(fields: Sequence[str]) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.activity DROP CONSTRAINT activity_fields_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.activity ADD CONSTRAINT activity_fields_check"
        f" CHECK ({_fields_rule(fields)}) NOT VALID"
    )
    op.execute(f"ALTER TABLE {SCHEMA}.activity VALIDATE CONSTRAINT activity_fields_check")


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TAG)
    op.execute(_assignment("contact_tag", "contact"))
    op.execute(_assignment("company_tag", "company"))
    for statement in INDEXES:
        op.execute(statement)
    for table in ("tag", "contact_tag", "company_tag"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    _replace_fields_rule(UPDATED_FIELDS)


def downgrade() -> None:
    _replace_fields_rule(_UPDATED_FIELDS_0003)
    op.execute(f"DROP TABLE {SCHEMA}.company_tag")
    op.execute(f"DROP TABLE {SCHEMA}.contact_tag")
    op.execute(f"DROP TABLE {SCHEMA}.tag")
