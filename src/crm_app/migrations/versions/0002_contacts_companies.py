"""Create the contact and company tables (Phase 3 slice 3A, decision P3-A).

Revision ID: 0002_contacts_companies
Revises: 0001_crm_app_schema
Create Date: 2026-10-23

Both tables are tenant-owned (`PHASE3-PLAN.md` §19.2): forced Row-Level
Security from `saas_os.infra.db.tenant_rls_statements` and exactly
SELECT, INSERT, UPDATE, DELETE for the runtime role, in this same
migration, so neither table is ever readable before its policy exists. Both
are in `crm_app.purge.PURGE_TABLES`.

`contact` references `company` through `(tenant_id, company_id)`, so a link
across workspaces is impossible even with RLS bypassed. `tenant_id`
references `core.tenants`, whose rows Core keeps as tombstones after a
purge, so the key never blocks one.

Downgrade drops both tables and their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0002_contacts_companies"
down_revision: str | Sequence[str] | None = "0001_crm_app_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

STAGES = ("lead", "prospect", "customer", "inactive")
SOURCES = ("manual", "import", "form", "referral", "other")
ORDER_COLLATION = "und-x-icu"
DOMAIN_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _text(table: str, column: str, maximum: int, *, required: bool = False) -> str:
    """Trimmed text of 1..maximum characters; optional text is NULL, never ''."""
    rule = f"{column} = btrim({column}) AND char_length({column}) BETWEEN 1 AND {maximum}"
    if not required:
        rule = f"{column} IS NULL OR ({rule})"
    return f"CONSTRAINT {table}_{column}_check CHECK ({rule})"


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_STANDARD_COLUMNS = """
    owner_user_id uuid,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    archived_at timestamptz"""

COMPANY = f"""
CREATE TABLE {SCHEMA}.company (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    domain text,
    website text,
    phone text,
    industry text,
    city text,
    country_code text,{_STANDARD_COLUMNS},
    CONSTRAINT company_tenant_id_id_key UNIQUE (tenant_id, id),
    {_text("company", "name", 200, required=True)},
    CONSTRAINT company_domain_check CHECK (
        domain IS NULL OR (char_length(domain) <= 253 AND domain ~ '{DOMAIN_PATTERN}')
    ),
    CONSTRAINT company_website_check CHECK (
        website IS NULL OR (
            website = btrim(website)
            AND char_length(website) BETWEEN 1 AND 2048
            AND website ~* '^https?://[^[:space:]]+$'
        )
    ),
    {_text("company", "phone", 32)},
    {_text("company", "industry", 100)},
    {_text("company", "city", 100)},
    CONSTRAINT company_country_code_check CHECK (
        country_code IS NULL OR country_code ~ '^[A-Z]{{2}}$'
    )
)
"""

CONTACT = f"""
CREATE TABLE {SCHEMA}.contact (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    first_name text NOT NULL,
    last_name text,
    email text,
    phone text,
    job_title text,
    city text,
    lifecycle_stage text NOT NULL DEFAULT 'lead',
    source text NOT NULL DEFAULT 'manual',
    company_id uuid,{_STANDARD_COLUMNS},
    CONSTRAINT contact_tenant_id_id_key UNIQUE (tenant_id, id),
    {_text("contact", "first_name", 200, required=True)},
    {_text("contact", "last_name", 200)},
    CONSTRAINT contact_email_check CHECK (
        email IS NULL OR (
            email = lower(btrim(email))
            AND char_length(email) BETWEEN 3 AND 320
            AND email ~ '^[^@[:space:]]+@[^@[:space:]]+$'
        )
    ),
    {_text("contact", "phone", 32)},
    {_text("contact", "job_title", 200)},
    {_text("contact", "city", 100)},
    CONSTRAINT contact_lifecycle_stage_check CHECK (lifecycle_stage IN ({_in(STAGES)})),
    CONSTRAINT contact_source_check CHECK (source IN ({_in(SOURCES)})),
    CONSTRAINT contact_email_or_phone_check CHECK (email IS NOT NULL OR phone IS NOT NULL),
    CONSTRAINT contact_company_fkey FOREIGN KEY (tenant_id, company_id)
        REFERENCES {SCHEMA}.company (tenant_id, id) ON DELETE SET NULL (company_id)
)
"""

INDEXES = (
    # Duplicates (P3-A decision 3): active rows only; archived rows never block.
    f"CREATE UNIQUE INDEX company_active_domain_key ON {SCHEMA}.company (tenant_id, domain)"
    " WHERE archived_at IS NULL AND domain IS NOT NULL",
    f"CREATE UNIQUE INDEX contact_active_email_key ON {SCHEMA}.contact (tenant_id, email)"
    " WHERE archived_at IS NULL AND email IS NOT NULL",
    # List orders (PHASE3-PLAN.md §19.5); `id` breaks every tie. Names sort in
    # the ICU root collation, which orders case-insensitively at the primary level.
    f"CREATE INDEX company_name_order_idx ON {SCHEMA}.company"
    f' (tenant_id, name COLLATE "{ORDER_COLLATION}", id)',
    f"CREATE INDEX company_created_order_idx ON {SCHEMA}.company (tenant_id, created_at, id)",
    f"CREATE INDEX company_updated_order_idx ON {SCHEMA}.company (tenant_id, updated_at, id)",
    f"CREATE INDEX contact_name_order_idx ON {SCHEMA}.contact"
    f' (tenant_id, last_name COLLATE "{ORDER_COLLATION}",'
    f' first_name COLLATE "{ORDER_COLLATION}", id)',
    f"CREATE INDEX contact_created_order_idx ON {SCHEMA}.contact (tenant_id, created_at, id)",
    f"CREATE INDEX contact_updated_order_idx ON {SCHEMA}.contact (tenant_id, updated_at, id)",
    # Filters and the foreign key.
    f"CREATE INDEX company_owner_idx ON {SCHEMA}.company (tenant_id, owner_user_id)",
    f"CREATE INDEX contact_owner_idx ON {SCHEMA}.contact (tenant_id, owner_user_id)",
    f"CREATE INDEX contact_company_idx ON {SCHEMA}.contact (tenant_id, company_id)",
    # Prefix search.
    f"CREATE INDEX company_name_prefix_idx ON {SCHEMA}.company"
    " (tenant_id, lower(name) text_pattern_ops)",
    f"CREATE INDEX company_domain_prefix_idx ON {SCHEMA}.company"
    " (tenant_id, domain text_pattern_ops)",
    f"CREATE INDEX contact_first_name_prefix_idx ON {SCHEMA}.contact"
    " (tenant_id, lower(first_name) text_pattern_ops)",
    f"CREATE INDEX contact_last_name_prefix_idx ON {SCHEMA}.contact"
    " (tenant_id, lower(last_name) text_pattern_ops)",
    f"CREATE INDEX contact_email_prefix_idx ON {SCHEMA}.contact"
    " (tenant_id, email text_pattern_ops)",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(COMPANY)
    op.execute(CONTACT)
    for statement in INDEXES:
        op.execute(statement)
    for table in ("company", "contact"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.contact")
    op.execute(f"DROP TABLE {SCHEMA}.company")
