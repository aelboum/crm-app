"""Member display names (PHASE2-PLAN.md §6.5, decision M-P1).

Revision ID: 0035_member_profiles
Revises: 0034_consent_confirmations
Create Date: 2026-11-03

- `member_profile`: tenant-owned, forced Row-Level Security. One row per
  member who chose a display name: SaaS-OS's `core.users` stores no name,
  so without it members appear by ID. The member sets it themselves; it is
  personal data, kept with the workspace and removed by the workspace purge.

No foreign key to `core.tenant_memberships`: the product's purge runs before
the platform's, and the row is written only for the signed-in member, whose
membership the route has already checked.

In `crm_app.purge.PURGE_TABLES`. Downgrade drops the table: for test and
development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0035_member_profiles"
down_revision: str | Sequence[str] | None = "0034_consent_confirmations"
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
CREATE TABLE {SCHEMA}.member_profile (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    user_id uuid NOT NULL,
    display_name text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT member_profile_pkey PRIMARY KEY (tenant_id, user_id),
    CONSTRAINT member_profile_name_check CHECK (
        char_length(display_name) BETWEEN 1 AND 80
        AND display_name = btrim(display_name)
        AND display_name !~ '[[:cntrl:]]'
    )
)
"""


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TABLE)
    for statement in tenant_rls_statements("member_profile", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.member_profile TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.member_profile")
