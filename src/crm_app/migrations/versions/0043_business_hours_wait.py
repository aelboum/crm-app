"""The automation step that waits for business hours (decision P8-W).

Revision ID: 0043_business_hours_wait
Revises: 0042_round_robin
Create Date: 2026-11-08

- `automation_step.action` also allows `wait_for_business_hours`.

Downgrade deletes the steps of the new action: for test and development
databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0043_business_hours_wait"
down_revision: str | Sequence[str] | None = "0042_round_robin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
STEPS = f"{SCHEMA}.automation_step"
_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait')"
)
_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours')"
)


def _check(expression: str) -> None:
    op.execute(f"ALTER TABLE {STEPS} DROP CONSTRAINT automation_step_action_check")
    op.execute(
        f"ALTER TABLE {STEPS} ADD CONSTRAINT automation_step_action_check CHECK ({expression})"
    )


def upgrade() -> None:
    _check(_AFTER)


def downgrade() -> None:
    with all_rows(STEPS):
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'wait_for_business_hours'")
    _check(_BEFORE)
