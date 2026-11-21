"""The automation step that waits for a contact field's value (decision P8-J).

Revision ID: 0054_wait_for_field
Revises: 0053_date_reached_trigger
Create Date: 2026-11-21

- `automation_step.action` also allows `wait_for_field`.
- `automation_run.field_wait_until`: when a run waiting on that step stops
  waiting for a value; empty otherwise.

Downgrade deletes the steps of the new action: for test and development
databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0054_wait_for_field"
down_revision: str | Sequence[str] | None = "0053_date_reached_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
STEPS = f"{SCHEMA}.automation_step"
RUNS = f"{SCHEMA}.automation_run"
_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field', 'wait_until_date')"
)
_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field', 'wait_until_date',"
    " 'wait_for_field')"
)


def _check(expression: str) -> None:
    op.execute(f"ALTER TABLE {STEPS} DROP CONSTRAINT automation_step_action_check")
    op.execute(
        f"ALTER TABLE {STEPS} ADD CONSTRAINT automation_step_action_check CHECK ({expression})"
    )


def upgrade() -> None:
    _check(_AFTER)
    op.execute(f"ALTER TABLE {RUNS} ADD COLUMN field_wait_until timestamptz")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {RUNS} DROP COLUMN field_wait_until")
    with all_rows(STEPS):
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'wait_for_field'")
    _check(_BEFORE)
