"""Email confirmation of consent from public forms (decision P7-V).

Revision ID: 0034_consent_confirmations
Revises: 0033_email_templates
Create Date: 2026-11-02

- `consent_confirmation`: tenant-owned, forced Row-Level Security. A public
  form's consent for an existing contact, matched only by the email typed,
  waiting for that person to confirm by email link. Only the token's
  SHA-256 hash is kept; it expires after 7 days and is used once
  (`confirmed_at`).
- `consent_record.method` also allows `email_confirmation`.
- `email_message.purpose` also allows `consent_confirmation`.

In `crm_app.purge.PURGE_TABLES`. Downgrade drops the table and the new
values: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0034_consent_confirmations"
down_revision: str | Sequence[str] | None = "0033_email_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
_METHODS_BEFORE = "method IN ('web_form', 'manual', 'unsubscribe_link')"
_METHODS_AFTER = "method IN ('web_form', 'manual', 'unsubscribe_link', 'email_confirmation')"
_PURPOSES_BEFORE = (
    "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign',"
    " 'appointment_reminder')"
)
_PURPOSES_AFTER = (
    "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign',"
    " 'appointment_reminder', 'consent_confirmation')"
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


TABLE = f"""
CREATE TABLE {SCHEMA}.consent_confirmation (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    contact_id uuid NOT NULL,
    form_id uuid,
    submission_id uuid,
    wording text NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    confirmed_at timestamptz,
    email_message_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT consent_confirmation_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT consent_confirmation_token_key UNIQUE (tenant_id, token_hash),
    CONSTRAINT consent_confirmation_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT consent_confirmation_hash_check CHECK (token_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT consent_confirmation_wording_check CHECK (char_length(wording) BETWEEN 1 AND 2000),
    CONSTRAINT consent_confirmation_window_check CHECK (expires_at > created_at)
)
"""

INDEX = (
    f"CREATE INDEX consent_confirmation_contact_idx ON {SCHEMA}.consent_confirmation"
    " (tenant_id, contact_id, created_at DESC)"
)


def _check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {SCHEMA}.{table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TABLE)
    op.execute(INDEX)
    for statement in tenant_rls_statements("consent_confirmation", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.consent_confirmation TO "{app_role}"'
    )
    _check("consent_record", "consent_record_method_check", _METHODS_AFTER)
    _check("email_message", "email_message_purpose_check", _PURPOSES_AFTER)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.consent_record WHERE method = 'email_confirmation'")
    _check("consent_record", "consent_record_method_check", _METHODS_BEFORE)
    op.execute(f"DELETE FROM {SCHEMA}.email_message WHERE purpose = 'consent_confirmation'")
    _check("email_message", "email_message_purpose_check", _PURPOSES_BEFORE)
    op.execute(f"DROP TABLE {SCHEMA}.consent_confirmation")
