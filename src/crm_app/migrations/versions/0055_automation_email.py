"""The automation step that sends one marketing email (decision P8-E).

Revision ID: 0055_automation_email
Revises: 0054_wait_for_field
Create Date: 2026-11-22

- `automation_email`: tenant-owned, forced Row-Level Security. One row per
  email a `send_email` step queued (at most one per run and step), with the
  address used, the email it queued, and the SHA-256 of its unsubscribe
  token. The automation and the run are kept as references only (set to
  null when they are deleted), so an email's unsubscribe link keeps working
  after its automation is gone. The daily limit counts these rows.
- `automation_step.action` also allows `send_email`.
- `email_message.purpose` also allows `automation`.

In `crm_app.purge.PURGE_TABLES`. Downgrade drops the table, the steps and
the emails of the new values: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0055_automation_email"
down_revision: str | Sequence[str] | None = "0054_wait_for_field"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
STEPS = f"{SCHEMA}.automation_step"
EMAILS = f"{SCHEMA}.email_message"
_ACTIONS_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field', 'wait_until_date',"
    " 'wait_for_field')"
)
_ACTIONS_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field', 'wait_until_date',"
    " 'wait_for_field', 'send_email')"
)
_PURPOSES_BEFORE = (
    "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign',"
    " 'appointment_reminder', 'consent_confirmation')"
)
_PURPOSES_AFTER = (
    "purpose IN ('booking_confirmation', 'test', 'conversation_reply', 'campaign',"
    " 'appointment_reminder', 'consent_confirmation', 'automation')"
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


TABLE = f"""
CREATE TABLE {SCHEMA}.automation_email (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    automation_id uuid,
    run_id uuid,
    branch text NOT NULL,
    position integer NOT NULL,
    contact_id uuid,
    email text NOT NULL,
    status text NOT NULL,
    email_message_id uuid,
    unsubscribe_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    unsubscribed_at timestamptz,
    CONSTRAINT automation_email_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT automation_email_once_key UNIQUE (tenant_id, run_id, branch, position),
    CONSTRAINT automation_email_unsubscribe_key UNIQUE (tenant_id, unsubscribe_hash),
    CONSTRAINT automation_email_automation_fkey FOREIGN KEY (tenant_id, automation_id)
        REFERENCES {SCHEMA}.automation (tenant_id, id) ON DELETE SET NULL (automation_id),
    CONSTRAINT automation_email_run_fkey FOREIGN KEY (tenant_id, run_id)
        REFERENCES {SCHEMA}.automation_run (tenant_id, id) ON DELETE SET NULL (run_id),
    CONSTRAINT automation_email_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT automation_email_branch_check CHECK (branch IN ('yes', 'no')),
    CONSTRAINT automation_email_status_check CHECK (status IN ('queued', 'unsubscribed')),
    CONSTRAINT automation_email_hash_check CHECK (unsubscribe_hash ~ '^[0-9a-f]{{64}}$')
)
"""

INDEX = (
    f"CREATE INDEX automation_email_recent_idx ON {SCHEMA}.automation_email"
    " (tenant_id, automation_id, created_at DESC)"
)


def _check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TABLE)
    op.execute(INDEX)
    for statement in tenant_rls_statements("automation_email", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.automation_email TO "{app_role}"')
    _check(STEPS, "automation_step_action_check", _ACTIONS_AFTER)
    _check(EMAILS, "email_message_purpose_check", _PURPOSES_AFTER)


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.automation_email")
    with all_rows(STEPS):
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'send_email'")
    _check(STEPS, "automation_step_action_check", _ACTIONS_BEFORE)
    with all_rows(EMAILS):
        op.execute(f"DELETE FROM {EMAILS} WHERE purpose = 'automation'")
    _check(EMAILS, "email_message_purpose_check", _PURPOSES_BEFORE)
