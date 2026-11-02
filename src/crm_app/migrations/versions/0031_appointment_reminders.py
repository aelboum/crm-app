"""Appointment reminder emails (Phase 5 slice 5D, decision P5-D).

Revision ID: 0031_appointment_reminders
Revises: 0030_domain_claims
Create Date: 2026-11-02

- `workspace_settings.reminder_lead_minutes`: how long before an
  appointment its contact is emailed a reminder: 60, 120, 1440 or 2880
  minutes, or NULL (off, the default).
- `appointment_reminder`: tenant-owned, forced Row-Level Security. One row
  per reminder made, automatic or sent by a member: the start time it was
  for, whether an email was queued or why not, and the email. At most one
  automatic reminder per appointment and start time, so a retried run or
  two runs at once never remind twice; a rescheduled appointment gets its
  own.
- `reminder_workspace`: global (tenant-context exclusion). Which workspaces
  have reminders on, so the maintenance run finds them; ids, a number and
  times only. The workspace's settings stay the authority.
- `email_message.purpose` also allows `appointment_reminder`.

The tenant table is in `crm_app.purge.PURGE_TABLES`; the purge participant
removes a workspace's global row. Downgrade drops it all: for test and
development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0031_appointment_reminders"
down_revision: str | Sequence[str] | None = "0030_domain_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
LEADS = (60, 120, 1440, 2880)
_PURPOSES_BEFORE = "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign')"
_PURPOSES_AFTER = (
    "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign',"
    " 'appointment_reminder')"
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


_LEADS = ", ".join(str(value) for value in LEADS)

REMINDER = f"""
CREATE TABLE {SCHEMA}.appointment_reminder (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    appointment_id uuid NOT NULL,
    starts_at timestamptz NOT NULL,
    kind text NOT NULL,
    outcome text NOT NULL,
    skip_reason text,
    email_message_id uuid,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT appointment_reminder_appointment_fkey FOREIGN KEY (tenant_id, appointment_id)
        REFERENCES {SCHEMA}.appointment (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT appointment_reminder_kind_check CHECK (kind IN ('automatic', 'manual')),
    CONSTRAINT appointment_reminder_outcome_check CHECK (
        (outcome = 'queued' AND email_message_id IS NOT NULL AND skip_reason IS NULL)
        OR (outcome = 'skipped' AND email_message_id IS NULL
            AND skip_reason ~ '^[a-z0-9_]{{1,64}}$')
    ),
    CONSTRAINT appointment_reminder_actor_check CHECK (
        (kind = 'manual') = (created_by_user_id IS NOT NULL)
    )
)
"""

WORKSPACES = f"""
CREATE TABLE {SCHEMA}.reminder_workspace (
    workspace_id uuid PRIMARY KEY,
    lead_minutes integer NOT NULL CHECK (lead_minutes IN ({_LEADS})),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

INDEXES = (
    f"CREATE UNIQUE INDEX appointment_reminder_automatic_key ON {SCHEMA}.appointment_reminder"
    " (tenant_id, appointment_id, starts_at) WHERE kind = 'automatic'",
    f"CREATE INDEX appointment_reminder_recent_idx ON {SCHEMA}.appointment_reminder"
    " (tenant_id, appointment_id, created_at DESC)",
)


def _purpose_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.email_message DROP CONSTRAINT email_message_purpose_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message ADD CONSTRAINT email_message_purpose_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    app_role = _app_role()
    op.execute(
        f"ALTER TABLE {SCHEMA}.workspace_settings ADD COLUMN reminder_lead_minutes integer,"
        " ADD CONSTRAINT workspace_settings_reminder_check CHECK ("
        f"reminder_lead_minutes IS NULL OR reminder_lead_minutes IN ({_LEADS}))"
    )
    for statement in (REMINDER, WORKSPACES, *INDEXES):
        op.execute(statement)
    for statement in tenant_rls_statements("appointment_reminder", schema=SCHEMA):
        op.execute(statement)
    # Append-only: DELETE only for the purge and the appointment's cascade.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.appointment_reminder TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("reminder_workspace", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.reminder_workspace TO "{app_role}"'
    )
    _purpose_check(_PURPOSES_AFTER)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.email_message WHERE purpose = 'appointment_reminder'")
    _purpose_check(_PURPOSES_BEFORE)
    op.execute(f"DROP TABLE {SCHEMA}.reminder_workspace")
    op.execute(f"DROP TABLE {SCHEMA}.appointment_reminder")
    op.execute(
        f"ALTER TABLE {SCHEMA}.workspace_settings"
        " DROP CONSTRAINT workspace_settings_reminder_check,"
        " DROP COLUMN reminder_lead_minutes"
    )
