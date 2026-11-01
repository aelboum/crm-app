"""Websites: allowed origins for external sites and lead attribution
(Phase 12 slice 12W, decision P12-W).

Revision ID: 0027_websites
Revises: 0026_campaigns
Create Date: 2026-11-01

- `website`: tenant-owned, forced Row-Level Security. A site outside
  LeadStack (WordPress, Shopify, Webflow, Wix or any other) whose pages may
  submit the workspace's published forms: a name, its allowed origins and
  whether it is active.
- `form_submission.website_id` (the site a cross-site submission came
  from; kept as null when the site is removed) and `attribution` (UTM
  parameters, the page and the referrer, when sent).

`website` is in `crm_app.purge.PURGE_TABLES`. Downgrade drops the table
and the two columns: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0027_websites"
down_revision: str | Sequence[str] | None = "0026_campaigns"
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


WEBSITE = f"""
CREATE TABLE {SCHEMA}.website (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    origins jsonb NOT NULL,
    status text NOT NULL DEFAULT 'active',
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT website_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT website_name_check CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT website_origins_check CHECK (
        jsonb_typeof(origins) = 'array' AND jsonb_array_length(origins) BETWEEN 1 AND 20
    ),
    CONSTRAINT website_status_check CHECK (status IN ('active', 'disabled'))
)
"""


def upgrade() -> None:
    app_role = _app_role()
    op.execute(WEBSITE)
    op.execute(f"CREATE INDEX website_tenant_idx ON {SCHEMA}.website (tenant_id, created_at)")
    for statement in tenant_rls_statements("website", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.website TO "{app_role}"')
    op.execute(
        f"ALTER TABLE {SCHEMA}.form_submission"
        " ADD COLUMN website_id uuid,"
        " ADD COLUMN attribution jsonb,"
        " ADD CONSTRAINT form_submission_website_fkey FOREIGN KEY (tenant_id, website_id)"
        f" REFERENCES {SCHEMA}.website (tenant_id, id) ON DELETE SET NULL (website_id),"
        " ADD CONSTRAINT form_submission_attribution_check"
        " CHECK (attribution IS NULL OR jsonb_typeof(attribution) = 'object')"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.form_submission"
        " DROP CONSTRAINT form_submission_attribution_check,"
        " DROP CONSTRAINT form_submission_website_fkey,"
        " DROP COLUMN attribution,"
        " DROP COLUMN website_id"
    )
    op.execute(f"DROP TABLE {SCHEMA}.website")
