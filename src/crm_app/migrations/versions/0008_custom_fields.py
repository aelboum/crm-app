"""Custom fields on contacts and companies (Phase 3 slice 3D, decision P3-D).

Revision ID: 0008_custom_fields
Revises: 0007_tags
Create Date: 2026-10-26

- `custom_field_definition`: tenant-owned, forced Row-Level Security from
  `saas_os.infra.db.tenant_rls_statements` and SELECT, INSERT, UPDATE,
  DELETE for the runtime role, in this same migration, and in
  `crm_app.purge.PURGE_TABLES`. A definition belongs to one entity
  (`contact` or `company`), has a machine `key` that is unique per workspace
  and entity for good (archived definitions keep theirs, so a key is never
  reused for another meaning), a label, a type, and the options of a
  `select`.
- `contact.custom_fields`, `company.custom_fields`: the values as one JSON
  object `{key: value}`, validated by the application against the active
  definitions (`PHASE3-PLAN.md` §3.2). The column has a constant default,
  which PostgreSQL 11+ records in the catalog without rewriting the table.

Locking: Alembic runs this in one transaction, so every `ALTER TABLE` here
holds an ACCESS EXCLUSIVE lock on `contact`, `company` and `activity` until
commit, including the scans that validate the new checks. That is
acceptable while no production data exists (decision P3-C note); a later
change to a large table must split its steps across transactions.

The history's `updated` entries may now also name `custom_fields`.

Downgrade drops the columns (and their values), the table and the history
rule's new name: for test and development databases only. It fails if a
history entry names `custom_fields`, rather than deleting it.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0008_custom_fields"
down_revision: str | Sequence[str] | None = "0007_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

ENTITIES = ("contact", "company")
FIELD_TYPES = ("text", "number", "date", "boolean", "select")
KEY_PATTERN = "^[a-z][a-z0-9_]{0,39}$"
LABEL_MAX = 60
OPTIONS_MAX = 50
# The stored JSON of one record's values, in bytes (P3-D 4).
VALUES_MAX_BYTES = 32_768

# Migration 0007's allow-list, and the same plus `custom_fields`.
_UPDATED_FIELDS_0007 = (
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
    "tags",
)
UPDATED_FIELDS = (*_UPDATED_FIELDS_0007, "custom_fields")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


DEFINITION = f"""
CREATE TABLE {SCHEMA}.custom_field_definition (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    entity text NOT NULL,
    key text NOT NULL,
    label text NOT NULL,
    field_type text NOT NULL,
    options jsonb,
    position integer NOT NULL DEFAULT 0,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    archived_at timestamptz,
    CONSTRAINT custom_field_definition_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT custom_field_definition_entity_check CHECK (entity IN ({_in(ENTITIES)})),
    CONSTRAINT custom_field_definition_key_check CHECK (key ~ '{KEY_PATTERN}'),
    CONSTRAINT custom_field_definition_label_check CHECK (
        char_length(label) BETWEEN 1 AND {LABEL_MAX}
        AND label = btrim(label)
        AND label !~ '[\\x01-\\x1f\\x7f]'
    ),
    CONSTRAINT custom_field_definition_type_check CHECK (field_type IN ({_in(FIELD_TYPES)})),
    -- A select has 1-{OPTIONS_MAX} options; no other type has any.
    CONSTRAINT custom_field_definition_options_check CHECK (
        (field_type = 'select') = (options IS NOT NULL)
        AND (
            options IS NULL OR (
                jsonb_typeof(options) = 'array'
                AND jsonb_array_length(options) BETWEEN 1 AND {OPTIONS_MAX}
            )
        )
    ),
    CONSTRAINT custom_field_definition_position_check CHECK (position BETWEEN 0 AND 10000)
)
"""

INDEXES = (
    # A key keeps one meaning per workspace and entity, archived or not.
    f"CREATE UNIQUE INDEX custom_field_definition_key_key ON {SCHEMA}.custom_field_definition"
    " (tenant_id, entity, key)",
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
        f" CHECK ({_fields_rule(fields)})"
    )


def upgrade() -> None:
    app_role = _app_role()
    op.execute(DEFINITION)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("custom_field_definition", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.custom_field_definition TO "{app_role}"'
    )
    for table in ("contact", "company"):
        op.execute(
            f"ALTER TABLE {SCHEMA}.{table}"
            " ADD COLUMN custom_fields jsonb NOT NULL DEFAULT '{}'::jsonb,"
            f" ADD CONSTRAINT {table}_custom_fields_check CHECK ("
            "jsonb_typeof(custom_fields) = 'object'"
            f" AND octet_length(custom_fields::text) <= {VALUES_MAX_BYTES})"
        )
    _replace_fields_rule(UPDATED_FIELDS)


def downgrade() -> None:
    _replace_fields_rule(_UPDATED_FIELDS_0007)
    for table in ("company", "contact"):
        op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP COLUMN custom_fields")
    op.execute(f"DROP TABLE {SCHEMA}.custom_field_definition")
