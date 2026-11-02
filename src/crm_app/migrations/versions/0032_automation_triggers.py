"""More automation triggers (Phase 8 slice 8B, decision P8-B).

Revision ID: 0032_automation_triggers
Revises: 0031_appointment_reminders
Create Date: 2026-11-02

`automation.trigger_type` also allows `tag_added`, `form_submitted`,
`appointment_booked` and `deal_stage_changed`; `automation_step.action`
also allows `remove_tag` and `set_lifecycle_stage`. Downgrade deletes
automations with a new trigger (their runs and versions cascade) and steps
of a new action: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_automation_triggers"
down_revision: str | Sequence[str] | None = "0031_appointment_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_BEFORE = "trigger_type IN ('contact_created')"
_AFTER = (
    "trigger_type IN ('contact_created', 'tag_added', 'form_submitted',"
    " 'appointment_booked', 'deal_stage_changed')"
)


_ACTIONS_BEFORE = "action IN ('add_tag', 'assign_owner', 'create_task', 'wait')"
_ACTIONS_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'wait')"
)


def _check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {SCHEMA}.{table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    _check("automation", "automation_trigger_check", _AFTER)
    _check("automation_step", "automation_step_action_check", _ACTIONS_AFTER)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.automation WHERE trigger_type <> 'contact_created'")
    op.execute(
        f"DELETE FROM {SCHEMA}.automation_step"
        " WHERE action IN ('remove_tag', 'set_lifecycle_stage')"
    )
    _check("automation", "automation_trigger_check", _BEFORE)
    _check("automation_step", "automation_step_action_check", _ACTIONS_BEFORE)
