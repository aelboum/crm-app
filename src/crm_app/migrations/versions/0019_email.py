"""Transactional email and delivery tracking (Phase 6 slice 6E, decision P6-E).

Revision ID: 0019_email
Revises: 0018_report_indexes
Create Date: 2026-11-01

- `email_message`: tenant-owned, forced Row-Level Security. One email the
  product sends to one address: its purpose, recipient, subject and text,
  its status from `queued` to the provider's last known delivery state,
  the provider and the provider's message id, attempts and the last error
  code (never a provider's error text). In `crm_app.purge.PURGE_TABLES`.
- `email_event`: tenant-owned, append-only (SELECT, INSERT and, for the
  purge, DELETE for the runtime role; no UPDATE). One delivery event a
  provider reported for a message, unique per provider event id, so a
  webhook delivered twice is stored once.
- `email_index`: a global table (tenant-context exclusion policy, as
  `import_expiry`), because a provider's webhook names only its message id
  and the sweeper must find unsent messages in every workspace. It holds
  ids and times only, no personal data; the purge participant removes a
  workspace's rows.
- `suppression.origin` also allows `provider`: an address suppressed
  because the provider reported a bounce or a complaint.

Downgrade drops the three tables and the provider-made suppressions: for
test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0019_email"
down_revision: str | Sequence[str] | None = "0018_report_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

EMAIL_MAX = 320
SUBJECT_MAX = 200
BODY_MAX = 20_000
PURPOSES = ("booking_confirmation", "test")
STATUSES = (
    "queued",
    "sending",
    "sent",
    "delivery_delayed",
    "delivered",
    "bounced",
    "complained",
    "failed",
    "suppressed",
)
EVENT_TYPES = ("sent", "delivery_delayed", "delivered", "bounced", "complained")
PROVIDERS = ("resend", "smtp", "mailpit", "fake")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


MESSAGE = f"""
CREATE TABLE {SCHEMA}.email_message (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    purpose text NOT NULL,
    to_email text NOT NULL,
    contact_id uuid,
    subject text NOT NULL,
    text_body text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    provider text,
    provider_message_id text,
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    CONSTRAINT email_message_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT email_message_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT email_message_purpose_check CHECK (purpose IN ({_in(PURPOSES)})),
    CONSTRAINT email_message_to_check CHECK (
        char_length(to_email) BETWEEN 3 AND {EMAIL_MAX}
        AND to_email = lower(btrim(to_email))
        AND to_email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'
    ),
    CONSTRAINT email_message_subject_check CHECK (
        char_length(subject) BETWEEN 1 AND {SUBJECT_MAX}
        AND subject !~ '[\\x00-\\x1f\\x7f]'
    ),
    CONSTRAINT email_message_body_check CHECK (
        char_length(text_body) BETWEEN 1 AND {BODY_MAX}
        AND text_body !~ '[\\x00-\\x09\\x0b-\\x1f\\x7f]'
    ),
    CONSTRAINT email_message_status_check CHECK (status IN ({_in(STATUSES)})),
    CONSTRAINT email_message_provider_check CHECK (
        provider IS NULL OR provider IN ({_in(PROVIDERS)})
    ),
    CONSTRAINT email_message_sent_check CHECK (
        (provider_message_id IS NULL OR provider IS NOT NULL)
        AND (sent_at IS NULL) = (status IN ('queued', 'sending', 'failed', 'suppressed'))
    ),
    CONSTRAINT email_message_attempts_check CHECK (attempts BETWEEN 0 AND 100),
    CONSTRAINT email_message_error_check CHECK (
        last_error IS NULL OR last_error ~ '^[a-z0-9_]{{1,64}}$'
    )
)
"""

EVENT = f"""
CREATE TABLE {SCHEMA}.email_event (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    email_message_id uuid NOT NULL,
    provider_event_id text NOT NULL,
    type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT email_event_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT email_event_provider_event_key UNIQUE (tenant_id, provider_event_id),
    CONSTRAINT email_event_message_fkey FOREIGN KEY (tenant_id, email_message_id)
        REFERENCES {SCHEMA}.email_message (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT email_event_type_check CHECK (type IN ({_in(EVENT_TYPES)})),
    CONSTRAINT email_event_provider_event_check CHECK (
        provider_event_id ~ '^[A-Za-z0-9_.:-]{{1,128}}$'
    )
)
"""

INDEX = f"""
CREATE TABLE {SCHEMA}.email_index (
    email_message_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    provider_message_id text UNIQUE,
    retry_at timestamptz,
    CONSTRAINT email_index_provider_message_check CHECK (
        provider_message_id IS NULL OR provider_message_id ~ '^[A-Za-z0-9_.:@<>-]{{1,200}}$'
    )
)
"""

INDEXES = (
    f"CREATE INDEX email_message_recent_idx ON {SCHEMA}.email_message"
    " (tenant_id, created_at DESC, id DESC)",
    f"CREATE INDEX email_message_contact_idx ON {SCHEMA}.email_message (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
    f"CREATE INDEX email_event_message_idx ON {SCHEMA}.email_event"
    " (tenant_id, email_message_id, occurred_at)",
    f"CREATE INDEX email_index_retry_idx ON {SCHEMA}.email_index (retry_at)"
    " WHERE retry_at IS NOT NULL",
)

_ORIGINS_BEFORE = "origin IN ('manual', 'consent_withdrawn')"
_ORIGINS_AFTER = "origin IN ('manual', 'consent_withdrawn', 'provider')"


def _origin_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.suppression DROP CONSTRAINT suppression_origin_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.suppression ADD CONSTRAINT suppression_origin_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    app_role = _app_role()
    op.execute(MESSAGE)
    op.execute(EVENT)
    op.execute(INDEX)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("email_message", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.email_message TO "{app_role}"')
    for statement in tenant_rls_statements("email_event", schema=SCHEMA):
        op.execute(statement)
    # Append-only: no UPDATE; DELETE only for the workspace purge.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.email_event TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("email_index", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.email_index TO "{app_role}"')
    _origin_check(_ORIGINS_AFTER)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.suppression WHERE origin = 'provider'")
    _origin_check(_ORIGINS_BEFORE)
    op.execute(f"DROP TABLE {SCHEMA}.email_index")
    op.execute(f"DROP TABLE {SCHEMA}.email_event")
    op.execute(f"DROP TABLE {SCHEMA}.email_message")
