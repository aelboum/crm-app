"""Create the workspace settings table (Phase 2, decision P2-F 1).

Revision ID: 0004_workspace_settings
Revises: 0003_notes_activity
Create Date: 2026-10-24

One row per workspace (`PHASE2-PLAN.md` S10, §12): its locale (a BCP 47
tag), time zone (an IANA name) and default currency (ISO 4217). Times are
stored in UTC everywhere; the time zone only says how to show them. A
workspace without a row uses the product defaults
(`crm_app.workspace_settings`), so no backfill is needed.

Tenant-owned: `tenant_id` is the primary key and references
`core.tenants`; forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements` and exactly SELECT, INSERT,
UPDATE, DELETE for the runtime role, in this same migration. In
`crm_app.purge.PURGE_TABLES`. The `CHECK`s enforce the shape of each value;
the API validates against the full lists (IANA zones, ISO 4217 codes).

Downgrade drops the table and its rows: for test and development databases
only, never a way to recover production data.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0004_workspace_settings"
down_revision: str | Sequence[str] | None = "0003_notes_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

# BCP 47 language[-Script][-REGION], as `crm_app.domains.settings` accepts.
LOCALE_PATTERN = r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$"
TIME_ZONE_PATTERN = r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*$"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


WORKSPACE_SETTINGS = f"""
CREATE TABLE {SCHEMA}.workspace_settings (
    tenant_id uuid PRIMARY KEY REFERENCES core.tenants (id),
    locale text NOT NULL,
    time_zone text NOT NULL,
    currency text NOT NULL,
    updated_by_user_id uuid,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT workspace_settings_locale_check CHECK (
        char_length(locale) <= 35 AND locale ~ '{LOCALE_PATTERN}'
    ),
    CONSTRAINT workspace_settings_time_zone_check CHECK (
        char_length(time_zone) <= 64 AND time_zone ~ '{TIME_ZONE_PATTERN}'
    ),
    CONSTRAINT workspace_settings_currency_check CHECK (currency ~ '^[A-Z]{{3}}$')
)
"""


def upgrade() -> None:
    op.execute(WORKSPACE_SETTINGS)
    for statement in tenant_rls_statements("workspace_settings", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.workspace_settings TO "{_app_role()}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.workspace_settings")
