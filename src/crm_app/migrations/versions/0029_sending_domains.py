"""Customer-owned sending domains and sender identities (Phase 6 slice 6D,
decision P6-D).

Revision ID: 0029_sending_domains
Revises: 0028_custom_domains
Create Date: 2026-11-01

- `sending_domain`: tenant-owned, forced Row-Level Security. A domain a
  workspace registers to send from, the provider's id for it, its state as
  the provider reports it, and the exact DNS records the provider returned.
- `sending_domain_index`: global (tenant-context exclusion). One row per
  registered domain: a domain belongs to at most one workspace on this
  platform (one provider account), and the provider's id leads a signed
  domain event back to its workspace.
- `sender_identity`: tenant-owned, forced Row-Level Security. An address on
  one of the workspace's domains, whether it may send conversation or
  campaign mail, and whether it is the stream's default (at most one per
  stream).
- `email_message.sender_identity_id` and `sender_address`: the identity an
  email was queued with and its address then; it is sent from that address
  only while the identity is active and its domain verified.

The tenant tables are in `crm_app.purge.PURGE_TABLES`; the purge
participant removes a workspace's index rows. Downgrade drops it all: for
test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0029_sending_domains"
down_revision: str | Sequence[str] | None = "0028_custom_domains"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
_HOST = "^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$"
STATUSES = (
    "not_registered",
    "not_started",
    "pending",
    "verified",
    "failed",
    "temporary_failure",
    "unknown",
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


DOMAIN = f"""
CREATE TABLE {SCHEMA}.sending_domain (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    domain text NOT NULL,
    provider_id text,
    status text NOT NULL DEFAULT 'not_registered',
    records jsonb NOT NULL DEFAULT '[]'::jsonb,
    last_error text,
    checked_at timestamptz,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT sending_domain_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT sending_domain_domain_key UNIQUE (tenant_id, domain),
    CONSTRAINT sending_domain_domain_check CHECK (domain ~ '{_HOST}'),
    CONSTRAINT sending_domain_provider_check CHECK (
        provider_id IS NULL OR provider_id ~ '^[A-Za-z0-9_-]{{1,128}}$'
    ),
    CONSTRAINT sending_domain_status_check CHECK (status IN ({_in(STATUSES)})),
    CONSTRAINT sending_domain_records_check CHECK (jsonb_typeof(records) = 'array'),
    CONSTRAINT sending_domain_error_check CHECK (
        last_error IS NULL OR last_error ~ '^[a-z0-9_]{{1,64}}$'
    )
)
"""

INDEX = f"""
CREATE TABLE {SCHEMA}.sending_domain_index (
    domain text PRIMARY KEY,
    workspace_id uuid NOT NULL,
    sending_domain_id uuid NOT NULL UNIQUE,
    provider_id text UNIQUE,
    CONSTRAINT sending_domain_index_domain_check CHECK (domain ~ '{_HOST}')
)
"""

IDENTITY = f"""
CREATE TABLE {SCHEMA}.sender_identity (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    sending_domain_id uuid NOT NULL,
    address text NOT NULL,
    for_conversation boolean NOT NULL DEFAULT false,
    for_campaign boolean NOT NULL DEFAULT false,
    default_conversation boolean NOT NULL DEFAULT false,
    default_campaign boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active',
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT sender_identity_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT sender_identity_address_key UNIQUE (tenant_id, address),
    CONSTRAINT sender_identity_domain_fkey FOREIGN KEY (tenant_id, sending_domain_id)
        REFERENCES {SCHEMA}.sending_domain (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT sender_identity_address_check CHECK (
        char_length(address) BETWEEN 3 AND 320 AND address = lower(address)
        AND address ~ '^[a-z0-9._-]+@[a-z0-9.-]+$'
    ),
    CONSTRAINT sender_identity_status_check CHECK (status IN ('active', 'disabled')),
    CONSTRAINT sender_identity_default_check CHECK (
        (NOT default_conversation OR for_conversation)
        AND (NOT default_campaign OR for_campaign)
    )
)
"""

INDEXES = (
    f"CREATE UNIQUE INDEX sender_identity_default_conversation_key ON {SCHEMA}.sender_identity"
    " (tenant_id) WHERE default_conversation",
    f"CREATE UNIQUE INDEX sender_identity_default_campaign_key ON {SCHEMA}.sender_identity"
    " (tenant_id) WHERE default_campaign",
    f"CREATE INDEX sending_domain_index_workspace_idx ON {SCHEMA}.sending_domain_index"
    " (workspace_id)",
)


def upgrade() -> None:
    app_role = _app_role()
    for statement in (DOMAIN, INDEX, IDENTITY, *INDEXES):
        op.execute(statement)
    for table in ("sending_domain", "sender_identity"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("sending_domain_index", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.sending_domain_index TO "{app_role}"'
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message"
        " ADD COLUMN sender_identity_id uuid,"
        " ADD COLUMN sender_address text,"
        " ADD CONSTRAINT email_message_sender_check"
        " CHECK ((sender_identity_id IS NULL) = (sender_address IS NULL))"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message"
        " DROP CONSTRAINT email_message_sender_check,"
        " DROP COLUMN sender_address,"
        " DROP COLUMN sender_identity_id"
    )
    for table in ("sender_identity", "sending_domain_index", "sending_domain"):
        op.execute(f"DROP TABLE {SCHEMA}.{table}")
