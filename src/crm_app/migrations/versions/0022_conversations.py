"""Conversations: threads, messages and read state (Phase 6 slice 6C,
decision P6-C).

Revision ID: 0022_conversations
Revises: 0021_automations
Create Date: 2026-11-01

Provider-neutral: no table names a provider. An outbound email is a
message that points at the `email_message` it queued (P6-E), whose status
is the delivery state; nothing here assumes SMTP or Resend.

- `conversation`: tenant-owned. One thread with one contact on one channel
  (`email`, or `other` for messages logged by hand), a subject, a status
  (`open`, `closed`), an assignee and the time of its last message.
- `conversation_message`: tenant-owned, append-only. Inbound (logged by a
  member), outbound (an email queued through `crm_app.emails`) or an
  internal note, with its author, plain text, and for outbound email the
  `email_message` id.
- `conversation_read`: tenant-owned. When each member last read a thread,
  for unread counts.

All three have forced Row-Level Security and are in
`crm_app.purge.PURGE_TABLES`. `email_message.purpose` also allows
`conversation_reply`. Downgrade drops the three tables and the reply
emails: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0022_conversations"
down_revision: str | Sequence[str] | None = "0021_automations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
SUBJECT_MAX = 200
BODY_MAX = 20_000


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


CONVERSATION = f"""
CREATE TABLE {SCHEMA}.conversation (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    contact_id uuid,
    channel text NOT NULL,
    subject text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    assignee_user_id uuid,
    last_message_at timestamptz NOT NULL DEFAULT now(),
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT conversation_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT conversation_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT conversation_channel_check CHECK (channel IN ('email', 'other')),
    CONSTRAINT conversation_status_check CHECK (status IN ('open', 'closed')),
    CONSTRAINT conversation_subject_check CHECK (
        char_length(subject) BETWEEN 1 AND {SUBJECT_MAX}
        AND subject = btrim(subject) AND subject !~ '[\\x00-\\x1f\\x7f]'
    )
)
"""

MESSAGE = f"""
CREATE TABLE {SCHEMA}.conversation_message (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    conversation_id uuid NOT NULL,
    kind text NOT NULL,
    body text NOT NULL,
    author_user_id uuid,
    email_message_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT conversation_message_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT conversation_message_conversation_fkey FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES {SCHEMA}.conversation (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT conversation_message_email_fkey FOREIGN KEY (tenant_id, email_message_id)
        REFERENCES {SCHEMA}.email_message (tenant_id, id) ON DELETE SET NULL (email_message_id),
    CONSTRAINT conversation_message_kind_check CHECK (kind IN ('inbound', 'outbound', 'note')),
    CONSTRAINT conversation_message_email_kind_check CHECK (
        email_message_id IS NULL OR kind = 'outbound'
    ),
    CONSTRAINT conversation_message_body_check CHECK (
        char_length(body) BETWEEN 1 AND {BODY_MAX}
        AND body !~ '[\\x00-\\x09\\x0b-\\x1f\\x7f]'
    )
)
"""

READ = f"""
CREATE TABLE {SCHEMA}.conversation_read (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    read_at timestamptz NOT NULL,
    CONSTRAINT conversation_read_pkey PRIMARY KEY (tenant_id, conversation_id, user_id),
    CONSTRAINT conversation_read_conversation_fkey FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES {SCHEMA}.conversation (tenant_id, id) ON DELETE CASCADE
)
"""

INDEXES = (
    f"CREATE INDEX conversation_inbox_idx ON {SCHEMA}.conversation"
    " (tenant_id, status, last_message_at DESC, id DESC)",
    f"CREATE INDEX conversation_contact_idx ON {SCHEMA}.conversation (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
    f"CREATE INDEX conversation_assignee_idx ON {SCHEMA}.conversation"
    " (tenant_id, assignee_user_id) WHERE assignee_user_id IS NOT NULL",
    f"CREATE INDEX conversation_message_thread_idx ON {SCHEMA}.conversation_message"
    " (tenant_id, conversation_id, created_at, id)",
)

_PURPOSES_BEFORE = "purpose IN ('booking_confirmation', 'test')"
_PURPOSES_AFTER = "purpose IN ('booking_confirmation', 'test', 'conversation_reply')"


def _purpose_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.email_message DROP CONSTRAINT email_message_purpose_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message ADD CONSTRAINT email_message_purpose_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    app_role = _app_role()
    for statement in (CONVERSATION, MESSAGE, READ, *INDEXES):
        op.execute(statement)
    grants = {
        "conversation": "SELECT, INSERT, UPDATE, DELETE",
        # Append-only: DELETE only for the purge and cascades.
        "conversation_message": "SELECT, INSERT, DELETE",
        "conversation_read": "SELECT, INSERT, UPDATE, DELETE",
    }
    for table, privileges in grants.items():
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT {privileges} ON {SCHEMA}.{table} TO "{app_role}"')
    _purpose_check(_PURPOSES_AFTER)


def downgrade() -> None:
    for table in ("conversation_read", "conversation_message", "conversation"):
        op.execute(f"DROP TABLE {SCHEMA}.{table}")
    op.execute(f"DELETE FROM {SCHEMA}.email_message WHERE purpose = 'conversation_reply'")
    _purpose_check(_PURPOSES_BEFORE)
