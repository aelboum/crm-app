"""The automation trigger on a contact's date (decision P8-I).

Revision ID: 0053_date_reached_trigger
Revises: 0052_wait_until_date
Create Date: 2026-11-21

- `automation.trigger_type` also allows `date_reached`.
- `automation_date_workspace`: global (tenant-context exclusion). Which
  workspaces activated an automation with that trigger, and when the
  maintenance run next looks at their contacts; an id and a time only. A
  workspace's automations stay the authority: a row whose workspace has
  none active is removed by the run.

No back-fill: no automation has the trigger yet. The purge participant
removes a workspace's row. Downgrade drops the table and deletes the
automations with the trigger (their runs and versions cascade): for test
and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0053_date_reached_trigger"
down_revision: str | Sequence[str] | None = "0052_wait_until_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
_BEFORE = (
    "trigger_type IN ('contact_created', 'tag_added', 'form_submitted',"
    " 'appointment_booked', 'deal_stage_changed', 'campaign_sent',"
    " 'campaign_unsubscribed')"
)
_AFTER = (
    "trigger_type IN ('contact_created', 'tag_added', 'form_submitted',"
    " 'appointment_booked', 'deal_stage_changed', 'campaign_sent',"
    " 'campaign_unsubscribed', 'date_reached')"
)

WORKSPACES = f"""
CREATE TABLE {SCHEMA}.automation_date_workspace (
    workspace_id uuid PRIMARY KEY,
    due_at timestamptz NOT NULL
)
"""


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.automation DROP CONSTRAINT automation_trigger_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.automation ADD CONSTRAINT automation_trigger_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    _check(_AFTER)
    op.execute(WORKSPACES)
    for statement in tenant_context_exclusion_statements(
        "automation_date_workspace", schema=SCHEMA
    ):
        op.execute(statement)
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.automation_date_workspace"
        f' TO "{_app_role()}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.automation_date_workspace")
    with all_rows(f"{SCHEMA}.automation"):
        op.execute(f"DELETE FROM {SCHEMA}.automation WHERE trigger_type = 'date_reached'")
    _check(_BEFORE)
