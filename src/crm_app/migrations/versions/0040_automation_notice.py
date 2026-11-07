"""The automation notify action (Phase 8, decision P8-N).

Revision ID: 0040_automation_notice
Revises: 0039_member_reminders
Create Date: 2026-11-07

- `automation_step.action` also allows `notify_member`.
- `member_notification.kind` also allows `automation_notice`, about a
  contact.
- `member_notification.note`: the fixed message an automation's author
  wrote in the definition, 1 to 200 characters; present exactly for
  `automation_notice` and absent for every other kind. It is never filled
  in from the contact.

No back-fill: the column is new and no row of the new kind exists yet.
Downgrade deletes the steps and notifications of the new kinds and drops
the column: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0040_automation_notice"
down_revision: str | Sequence[str] | None = "0039_member_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
NOTIFICATIONS = f"{SCHEMA}.member_notification"
STEPS = f"{SCHEMA}.automation_step"

_ACTIONS_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'wait')"
)
_ACTIONS_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'wait')"
)
_KINDS_BEFORE = (
    "(kind = 'task_assigned' AND subject_type = 'task')"
    " OR (kind = 'conversation_assigned' AND subject_type = 'conversation')"
    " OR (kind IN ('appointment_assigned', 'booking_received', 'booking_cancelled',"
    " 'appointment_upcoming') AND subject_type = 'appointment')"
)
_KINDS_AFTER = f"{_KINDS_BEFORE} OR (kind = 'automation_notice' AND subject_type = 'contact')"
_NOTE = (
    "(kind = 'automation_notice') = (note IS NOT NULL)"
    " AND (note IS NULL OR char_length(note) BETWEEN 1 AND 200)"
)


def _check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    _check(STEPS, "automation_step_action_check", _ACTIONS_AFTER)
    op.execute(f"ALTER TABLE {NOTIFICATIONS} ADD COLUMN note text")
    _check(NOTIFICATIONS, "member_notification_kind_check", _KINDS_AFTER)
    op.execute(
        f"ALTER TABLE {NOTIFICATIONS} ADD CONSTRAINT member_notification_note_check CHECK ({_NOTE})"
    )


def downgrade() -> None:
    with all_rows(NOTIFICATIONS, STEPS):
        op.execute(f"DELETE FROM {NOTIFICATIONS} WHERE kind = 'automation_notice'")
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'notify_member'")
    op.execute(f"ALTER TABLE {NOTIFICATIONS} DROP CONSTRAINT member_notification_note_check")
    _check(NOTIFICATIONS, "member_notification_kind_check", _KINDS_BEFORE)
    op.execute(f"ALTER TABLE {NOTIFICATIONS} DROP COLUMN note")
    _check(STEPS, "automation_step_action_check", _ACTIONS_BEFORE)
