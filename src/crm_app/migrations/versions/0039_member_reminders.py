"""In-app reminders of upcoming appointments for their hosts (decision N-2).

Revision ID: 0039_member_reminders
Revises: 0038_email_outcome_unknown
Create Date: 2026-11-07

- `appointment_member_reminder`: tenant-owned, forced Row-Level Security.
  One row per appointment and start time its host was reminded of; the
  primary key makes a retried or concurrent run remind nobody twice, and a
  rescheduled appointment is reminded of again for its new time.
- `member_reminder_workspace`: global (tenant-context exclusion). Which
  workspaces have an appointment starting up to `until`, so the
  maintenance run finds them without reading every workspace; an id and a
  time only. A workspace's appointments stay the authority.
- `member_notification.kind` also allows `appointment_upcoming`, about an
  appointment.

No back-fill: an appointment made before this migration is reminded of
once it is created or moved again. The tenant table is in
`crm_app.purge.PURGE_TABLES`; the purge participant removes a workspace's
global row. Downgrade drops both tables and the notifications of the new
kind: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0039_member_reminders"
down_revision: str | Sequence[str] | None = "0038_email_outcome_unknown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

_APPOINTMENT_KINDS_BEFORE = "'appointment_assigned', 'booking_received', 'booking_cancelled'"
_APPOINTMENT_KINDS_AFTER = f"{_APPOINTMENT_KINDS_BEFORE}, 'appointment_upcoming'"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


REMINDER = f"""
CREATE TABLE {SCHEMA}.appointment_member_reminder (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    appointment_id uuid NOT NULL,
    starts_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT appointment_member_reminder_pkey PRIMARY KEY (tenant_id, appointment_id, starts_at),
    CONSTRAINT appointment_member_reminder_appointment_fkey FOREIGN KEY (tenant_id, appointment_id)
        REFERENCES {SCHEMA}.appointment (tenant_id, id) ON DELETE CASCADE
)
"""

WORKSPACES = f"""
CREATE TABLE {SCHEMA}.member_reminder_workspace (
    workspace_id uuid PRIMARY KEY,
    until timestamptz NOT NULL
)
"""


def _kind_check(appointment_kinds: str) -> None:
    table = f"{SCHEMA}.member_notification"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT member_notification_kind_check")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT member_notification_kind_check CHECK ("
        "(kind = 'task_assigned' AND subject_type = 'task')"
        " OR (kind = 'conversation_assigned' AND subject_type = 'conversation')"
        f" OR (kind IN ({appointment_kinds}) AND subject_type = 'appointment'))"
    )


def upgrade() -> None:
    app_role = _app_role()
    op.execute(REMINDER)
    for statement in tenant_rls_statements("appointment_member_reminder", schema=SCHEMA):
        op.execute(statement)
    # Append-only: DELETE only for the purge and the appointment's cascade.
    op.execute(
        f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.appointment_member_reminder TO "{app_role}"'
    )
    op.execute(WORKSPACES)
    for statement in tenant_context_exclusion_statements(
        "member_reminder_workspace", schema=SCHEMA
    ):
        op.execute(statement)
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.member_reminder_workspace"
        f' TO "{app_role}"'
    )
    _kind_check(_APPOINTMENT_KINDS_AFTER)


def downgrade() -> None:
    with all_rows(f"{SCHEMA}.member_notification"):
        op.execute(f"DELETE FROM {SCHEMA}.member_notification WHERE kind = 'appointment_upcoming'")
    _kind_check(_APPOINTMENT_KINDS_BEFORE)
    op.execute(f"DROP TABLE {SCHEMA}.member_reminder_workspace")
    op.execute(f"DROP TABLE {SCHEMA}.appointment_member_reminder")
