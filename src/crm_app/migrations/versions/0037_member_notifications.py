"""In-app notifications for members (decision N-1).

Revision ID: 0037_member_notifications
Revises: 0036_activity_source
Create Date: 2026-11-06

- `member_notification`: tenant-owned, forced Row-Level Security. One row
  per thing a member should know about: a task, conversation or
  appointment someone else assigned to them, or a booking a visitor made
  or cancelled on one of their booking pages. It names the record by type
  and ID only; the list reads the record's current name, so a renamed
  record shows its new name and a deleted one shows as unavailable.
  `read_at` is set when the member opens or dismisses it.

SaaS-OS v0.8.0's `in_app` notification channel stores only text, has no
read state and lists every row unpaged, so the product keeps its own inbox
(decision N-1). No foreign key to the record: the notification outlives a
deleted record. No foreign key to `core.tenant_memberships`: the product's
purge runs before the platform's, and recipients are checked members.

In `crm_app.purge.PURGE_TABLES`. Downgrade drops the table: for test and
development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0037_member_notifications"
down_revision: str | Sequence[str] | None = "0036_activity_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


TABLE = f"""
CREATE TABLE {SCHEMA}.member_notification (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    kind text NOT NULL,
    subject_type text NOT NULL,
    subject_id uuid NOT NULL,
    actor_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz,
    CONSTRAINT member_notification_pkey PRIMARY KEY (tenant_id, id),
    CONSTRAINT member_notification_kind_check CHECK (
        (kind = 'task_assigned' AND subject_type = 'task')
        OR (kind = 'conversation_assigned' AND subject_type = 'conversation')
        OR (kind IN ('appointment_assigned', 'booking_received', 'booking_cancelled')
            AND subject_type = 'appointment')
    ),
    CONSTRAINT member_notification_actor_check CHECK (
        actor_user_id IS NULL OR actor_user_id <> user_id
    ),
    CONSTRAINT member_notification_read_check CHECK (
        read_at IS NULL OR read_at >= created_at
    )
)
"""

INDEXES = (
    f"CREATE INDEX member_notification_recipient_idx ON {SCHEMA}.member_notification"
    " (tenant_id, user_id, created_at DESC, id DESC)",
    f"CREATE INDEX member_notification_unread_idx ON {SCHEMA}.member_notification"
    " (tenant_id, user_id) WHERE read_at IS NULL",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TABLE)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("member_notification", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.member_notification TO "{app_role}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.member_notification")
