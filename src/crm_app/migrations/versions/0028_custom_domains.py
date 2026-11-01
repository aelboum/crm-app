"""Custom domains for LeadStack-hosted pages (Phase 12 slice 12D,
decision P12-D).

Revision ID: 0028_custom_domains
Revises: 0027_websites
Create Date: 2026-11-01

- `custom_domain`: tenant-owned, forced Row-Level Security. A hostname a
  workspace claims for its hosted pages, the random token its DNS TXT
  record must hold, and its state: `pending` (until verified, at most
  seven days), `verified`, or `lapsed` (the record disappeared on a later
  check). One claim per hostname per workspace.
- `custom_domain_index`: global (tenant-context exclusion), because a
  request names only its Host. Each claim's hostname and workspace, and
  whether it is verified; a partial unique index lets only one workspace
  hold a hostname verified at a time, while pending claims by others never
  block the owner.

`custom_domain` is in `crm_app.purge.PURGE_TABLES`; the purge participant
removes a workspace's index rows. Downgrade drops both tables: for test
and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0028_custom_domains"
down_revision: str | Sequence[str] | None = "0027_websites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
_HOST = "^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


DOMAIN = f"""
CREATE TABLE {SCHEMA}.custom_domain (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    hostname text NOT NULL,
    token text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    expires_at timestamptz,
    verified_at timestamptz,
    checked_at timestamptz,
    last_error text,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT custom_domain_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT custom_domain_host_key UNIQUE (tenant_id, hostname),
    CONSTRAINT custom_domain_host_check CHECK (hostname ~ '{_HOST}'),
    CONSTRAINT custom_domain_token_check CHECK (token ~ '^[0-9a-f]{{32}}$'),
    CONSTRAINT custom_domain_status_check CHECK (status IN ('pending', 'verified', 'lapsed')),
    CONSTRAINT custom_domain_verified_check CHECK (
        status <> 'verified' OR verified_at IS NOT NULL
    ),
    CONSTRAINT custom_domain_error_check CHECK (
        last_error IS NULL OR last_error ~ '^[a-z0-9_]{{1,64}}$'
    )
)
"""

INDEX = f"""
CREATE TABLE {SCHEMA}.custom_domain_index (
    domain_id uuid PRIMARY KEY,
    hostname text NOT NULL,
    workspace_id uuid NOT NULL,
    verified boolean NOT NULL DEFAULT false,
    CONSTRAINT custom_domain_index_host_check CHECK (hostname ~ '{_HOST}')
)
"""


def upgrade() -> None:
    app_role = _app_role()
    op.execute(DOMAIN)
    op.execute(INDEX)
    op.execute(
        f"CREATE UNIQUE INDEX custom_domain_index_verified_key ON {SCHEMA}.custom_domain_index"
        " (hostname) WHERE verified"
    )
    op.execute(
        f"CREATE INDEX custom_domain_index_workspace_idx ON {SCHEMA}.custom_domain_index"
        " (workspace_id)"
    )
    for statement in tenant_rls_statements("custom_domain", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.custom_domain TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("custom_domain_index", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.custom_domain_index TO "{app_role}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.custom_domain_index")
    op.execute(f"DROP TABLE {SCHEMA}.custom_domain")
