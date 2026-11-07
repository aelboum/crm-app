"""Inbound email: received events, routing addresses and quarantine
(Phase 6 slice 6E.3, decision P6-I).

Revision ID: 0025_inbound_email
Revises: 0024_email_streams
Create Date: 2026-11-01

- `inbound_email`: global (tenant-context exclusion, like `email_index`),
  because a received email names no workspace until it is routed. One row
  per provider email, written when the signed webhook arrives and before
  anything else, unique by the webhook's event id and by the provider's
  email id, so a redelivered webhook is recorded once. It holds ids,
  states, a reason code, the routed workspace and, for mail that matches no
  workspace, only the sender's domain: no addresses, subject or body.
- `conversation_route`: tenant-owned, forced Row-Level Security. A
  conversation's routing token (`reply+<token>@inbound.<parent>`), random
  and unguessable, one per conversation.
- `conversation_route_index`: global. The SHA-256 of each token, with its
  workspace and conversation, so the processor finds the workspace without
  trusting anything in the email. The workspace's own row is checked
  again inside the workspace before anything is written.
- `inbound_quarantine`: tenant-owned, forced Row-Level Security. Routed
  mail that needs a member's review (sender is not the contact, DMARC
  failed, no text), with the text kept for that review.
- `conversation_message.inbound_email_id` (unique per workspace, so a
  retried job adds a message once) and `attachments` (names, types and
  sizes of attachments that were not fetched).

The tenant tables are in `crm_app.purge.PURGE_TABLES`; the global ones are
cleared per workspace by the purge participant. Downgrade drops it all:
for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0025_inbound_email"
down_revision: str | Sequence[str] | None = "0024_email_streams"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
STATUSES = ("received", "processing", "routed", "quarantined", "unmatched", "failed")
REVIEW = ("pending", "accepted", "discarded")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


INBOUND = f"""
CREATE TABLE {SCHEMA}.inbound_email (
    id uuid PRIMARY KEY,
    provider_event_id text NOT NULL UNIQUE,
    provider_email_id text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'received',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error text,
    reason text,
    workspace_id uuid,
    sender_domain text,
    received_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT inbound_email_event_check CHECK (provider_event_id ~ '^[A-Za-z0-9_.:-]{{1,128}}$'),
    CONSTRAINT inbound_email_provider_check CHECK (provider_email_id ~ '^[A-Za-z0-9_-]{{1,128}}$'),
    CONSTRAINT inbound_email_status_check CHECK (status IN ({_in(STATUSES)})),
    CONSTRAINT inbound_email_attempts_check CHECK (attempts BETWEEN 0 AND 100),
    CONSTRAINT inbound_email_error_check CHECK (
        last_error IS NULL OR last_error ~ '^[a-z0-9_]{{1,64}}$'
    ),
    CONSTRAINT inbound_email_reason_check CHECK (reason IS NULL OR reason ~ '^[a-z0-9_]{{1,64}}$'),
    CONSTRAINT inbound_email_domain_check CHECK (
        sender_domain IS NULL OR sender_domain ~ '^[a-z0-9.-]{{1,253}}$'
    ),
    CONSTRAINT inbound_email_workspace_check CHECK (
        (workspace_id IS NOT NULL) = (status IN ('routed', 'quarantined'))
    )
)
"""

ROUTE = f"""
CREATE TABLE {SCHEMA}.conversation_route (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    conversation_id uuid NOT NULL,
    token text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, conversation_id),
    CONSTRAINT conversation_route_conversation_fkey FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES {SCHEMA}.conversation (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT conversation_route_token_check CHECK (token ~ '^[0-9a-f]{{32}}$')
)
"""

ROUTE_INDEX = f"""
CREATE TABLE {SCHEMA}.conversation_route_index (
    token_hash text PRIMARY KEY,
    workspace_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    CONSTRAINT conversation_route_index_hash_check CHECK (token_hash ~ '^[0-9a-f]{{64}}$')
)
"""

QUARANTINE = f"""
CREATE TABLE {SCHEMA}.inbound_quarantine (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    inbound_email_id uuid NOT NULL,
    conversation_id uuid,
    reason text NOT NULL,
    sender text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    truncated boolean NOT NULL DEFAULT false,
    attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'pending',
    decided_by_user_id uuid,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT inbound_quarantine_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT inbound_quarantine_email_key UNIQUE (tenant_id, inbound_email_id),
    CONSTRAINT inbound_quarantine_conversation_fkey FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES {SCHEMA}.conversation (tenant_id, id) ON DELETE SET NULL (conversation_id),
    CONSTRAINT inbound_quarantine_reason_check CHECK (reason ~ '^[a-z0-9_]{{1,64}}$'),
    CONSTRAINT inbound_quarantine_sender_check CHECK (char_length(sender) BETWEEN 3 AND 320),
    CONSTRAINT inbound_quarantine_subject_check CHECK (char_length(subject) BETWEEN 1 AND 200),
    CONSTRAINT inbound_quarantine_body_check CHECK (char_length(body) <= 20000),
    CONSTRAINT inbound_quarantine_status_check CHECK (status IN ({_in(REVIEW)})),
    CONSTRAINT inbound_quarantine_decided_check CHECK (
        (status = 'pending') = (decided_at IS NULL)
    )
)
"""

INDEXES = (
    f"CREATE INDEX inbound_email_due_idx ON {SCHEMA}.inbound_email (status, next_attempt_at)"
    " WHERE status IN ('received', 'processing')",
    f"CREATE INDEX inbound_email_workspace_idx ON {SCHEMA}.inbound_email (workspace_id)"
    " WHERE workspace_id IS NOT NULL",
    f"CREATE INDEX conversation_route_index_workspace_idx"
    f" ON {SCHEMA}.conversation_route_index (workspace_id)",
    f"CREATE INDEX inbound_quarantine_pending_idx ON {SCHEMA}.inbound_quarantine"
    " (tenant_id, created_at DESC) WHERE status = 'pending'",
    f"CREATE UNIQUE INDEX conversation_message_inbound_key ON {SCHEMA}.conversation_message"
    " (tenant_id, inbound_email_id) WHERE inbound_email_id IS NOT NULL",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(INBOUND)
    op.execute(ROUTE)
    op.execute(ROUTE_INDEX)
    op.execute(QUARANTINE)
    op.execute(
        f"ALTER TABLE {SCHEMA}.conversation_message"
        " ADD COLUMN inbound_email_id uuid,"
        " ADD COLUMN attachments jsonb,"
        " ADD CONSTRAINT conversation_message_inbound_check"
        " CHECK (inbound_email_id IS NULL OR kind = 'inbound')"
    )
    for statement in INDEXES:
        op.execute(statement)
    for table in ("inbound_email", "conversation_route_index"):
        for statement in tenant_context_exclusion_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    for statement in tenant_rls_statements("conversation_route", schema=SCHEMA):
        op.execute(statement)
    # A route never changes: no UPDATE.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.conversation_route TO "{app_role}"')
    for statement in tenant_rls_statements("inbound_quarantine", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.inbound_quarantine TO "{app_role}"'
    )


def downgrade() -> None:
    with all_rows(f"{SCHEMA}.conversation_message"):
        op.execute(f"DELETE FROM {SCHEMA}.conversation_message WHERE inbound_email_id IS NOT NULL")
    op.execute(f"DROP INDEX {SCHEMA}.conversation_message_inbound_key")
    op.execute(
        f"ALTER TABLE {SCHEMA}.conversation_message"
        " DROP CONSTRAINT conversation_message_inbound_check,"
        " DROP COLUMN inbound_email_id,"
        " DROP COLUMN attachments"
    )
    for table in (
        "inbound_quarantine",
        "conversation_route_index",
        "conversation_route",
        "inbound_email",
    ):
        op.execute(f"DROP TABLE {SCHEMA}.{table}")
