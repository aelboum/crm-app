"""The automation step that sets a contact custom field (decision P8-F).

Revision ID: 0051_custom_field_step
Revises: 0050_campaign_triggers
Create Date: 2026-11-20

- `automation_step.action` also allows `set_custom_field`.

Downgrade deletes the steps of the new action: for test and development
databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0051_custom_field_step"
down_revision: str | Sequence[str] | None = "0050_campaign_triggers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
STEPS = f"{SCHEMA}.automation_step"
_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours')"
)
_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait',"
    " 'wait_for_business_hours', 'set_custom_field')"
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
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'set_custom_field'")
    _check(_BEFORE)
