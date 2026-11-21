"""The automation step that waits until a contact's date (decision P8-D).

Revision ID: 0052_wait_until_date
Revises: 0051_custom_field_step
Create Date: 2026-11-21

- `automation_step.action` also allows `wait_until_date`.

Downgrade deletes the steps of the new action: for test and development
databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0052_wait_until_date"
down_revision: str | Sequence[str] | None = "0051_custom_field_step"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
STEPS = f"{SCHEMA}.automation_step"
_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field')"
)
_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field', 'wait_until_date')"
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
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'wait_until_date'")
    _check(_BEFORE)
