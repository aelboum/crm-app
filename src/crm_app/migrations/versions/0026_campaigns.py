"""Campaigns: drafts, approval and recipients (Phase 7 slice 7C,
decision P7-C).

Revision ID: 0026_campaigns
Revises: 0025_inbound_email
Create Date: 2026-11-01

- `campaign`: tenant-owned, forced Row-Level Security. A campaign's name,
  subject, plain-text body and audience segment; its state
  (`crm_app.domains.campaigns.STATUSES`); the hash of its content
  (`content_hash`) and, once approved, the hash that was approved, by whom
  and when; the latest audience estimate; who submitted, rejected or
  cancelled it.
- `campaign_recipient`: tenant-owned, forced Row-Level Security. One row per
  contact a queued campaign reaches (unique per campaign and contact, so a
  repeated queuing step adds no one twice), with the address used, its
  state, the email it queued, and the SHA-256 of its unsubscribe token.
- `email_message.purpose` also allows `campaign`; `consent_record.method`
  also allows `unsubscribe_link` (a recipient's own withdrawal).

Both tables are in `crm_app.purge.PURGE_TABLES`. Downgrade drops them and
the campaign emails: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0026_campaigns"
down_revision: str | Sequence[str] | None = "0025_inbound_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
STATUSES = (
    "draft",
    "validated",
    "awaiting_approval",
    "approved",
    "queued",
    "processing",
    "completed",
    "partially_completed",
    "failed",
    "rejected",
    "cancelled",
)
RECIPIENT_STATUSES = ("queued", "skipped", "unsubscribed")
_PURPOSES_BEFORE = "purpose IN ('booking_confirmation', 'test', 'conversation_reply')"
_PURPOSES_AFTER = "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign')"
_METHODS_BEFORE = "method IN ('web_form', 'manual')"
_METHODS_AFTER = "method IN ('web_form', 'manual', 'unsubscribe_link')"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


CAMPAIGN = f"""
CREATE TABLE {SCHEMA}.campaign (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    segment jsonb NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    content_hash text NOT NULL,
    estimate jsonb,
    validated_at timestamptz,
    submitted_by_user_id uuid,
    submitted_at timestamptz,
    approved_hash text,
    approved_by_user_id uuid,
    approved_at timestamptz,
    decision_note text,
    rejected_by_user_id uuid,
    rejected_at timestamptz,
    cancelled_by_user_id uuid,
    cancelled_at timestamptz,
    queued_at timestamptz,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT campaign_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT campaign_name_check CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT campaign_subject_check CHECK (
        char_length(subject) BETWEEN 1 AND 200 AND subject !~ '[\\x00-\\x1f\\x7f]'
    ),
    CONSTRAINT campaign_body_check CHECK (
        char_length(body) BETWEEN 1 AND 18000 AND body !~ '[\\x00-\\x09\\x0b-\\x1f\\x7f]'
    ),
    CONSTRAINT campaign_status_check CHECK (status IN ({_in(STATUSES)})),
    CONSTRAINT campaign_hash_check CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT campaign_approved_check CHECK (
        (status IN ('approved', 'queued', 'processing', 'completed', 'partially_completed',
                    'failed'))
        = (approved_hash IS NOT NULL AND approved_at IS NOT NULL)
        OR status = 'cancelled'
    ),
    CONSTRAINT campaign_note_check CHECK (
        decision_note IS NULL OR char_length(decision_note) BETWEEN 1 AND 500
    )
)
"""

RECIPIENT = f"""
CREATE TABLE {SCHEMA}.campaign_recipient (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    campaign_id uuid NOT NULL,
    contact_id uuid,
    email text NOT NULL,
    status text NOT NULL,
    skip_reason text,
    email_message_id uuid,
    unsubscribe_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    unsubscribed_at timestamptz,
    CONSTRAINT campaign_recipient_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT campaign_recipient_once_key UNIQUE (tenant_id, campaign_id, contact_id),
    CONSTRAINT campaign_recipient_unsubscribe_key UNIQUE (tenant_id, unsubscribe_hash),
    CONSTRAINT campaign_recipient_campaign_fkey FOREIGN KEY (tenant_id, campaign_id)
        REFERENCES {SCHEMA}.campaign (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT campaign_recipient_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT campaign_recipient_status_check CHECK (status IN ({_in(RECIPIENT_STATUSES)})),
    CONSTRAINT campaign_recipient_reason_check CHECK (
        skip_reason IS NULL OR skip_reason ~ '^[a-z0-9_]{{1,64}}$'
    ),
    CONSTRAINT campaign_recipient_hash_check CHECK (unsubscribe_hash ~ '^[0-9a-f]{{64}}$')
)
"""

INDEXES = (
    f"CREATE INDEX campaign_recent_idx ON {SCHEMA}.campaign (tenant_id, updated_at DESC, id DESC)",
    f"CREATE INDEX campaign_recipient_campaign_idx ON {SCHEMA}.campaign_recipient"
    " (tenant_id, campaign_id, status)",
)


def _purpose_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.email_message DROP CONSTRAINT email_message_purpose_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message ADD CONSTRAINT email_message_purpose_check"
        f" CHECK ({expression})"
    )


def _method_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record DROP CONSTRAINT consent_record_method_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.consent_record ADD CONSTRAINT consent_record_method_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    app_role = _app_role()
    for statement in (CAMPAIGN, RECIPIENT, *INDEXES):
        op.execute(statement)
    for table in ("campaign", "campaign_recipient"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    _purpose_check(_PURPOSES_AFTER)
    _method_check(_METHODS_AFTER)


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.campaign_recipient")
    op.execute(f"DROP TABLE {SCHEMA}.campaign")
    with all_rows(f"{SCHEMA}.email_message"):
        op.execute(f"DELETE FROM {SCHEMA}.email_message WHERE purpose = 'campaign'")
    _purpose_check(_PURPOSES_BEFORE)
    with all_rows(f"{SCHEMA}.consent_record"):
        op.execute(f"DELETE FROM {SCHEMA}.consent_record WHERE method = 'unsubscribe_link'")
    _method_check(_METHODS_BEFORE)
