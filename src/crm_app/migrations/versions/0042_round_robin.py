"""Round-robin assignment in automations (decision P8-R).

Revision ID: 0042_round_robin
Revises: 0041_saved_views
Create Date: 2026-11-08

- `automation_step.action` also allows `assign_round_robin`.
- `automation_rotation`: tenant-owned, forced Row-Level Security. How many
  contacts one round-robin step of one automation has handed out, so the
  next goes to the next member in its list. Advanced under a row lock in
  the step's own transaction, so parallel runs never take the same turn
  and a retried step never advances it twice. Removed with its automation;
  in `crm_app.purge.PURGE_TABLES`.

Downgrade deletes the steps of the new action and drops the table: for
test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

from crm_app.migrations.all_rows import all_rows

revision: str = "0042_round_robin"
down_revision: str | Sequence[str] | None = "0041_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
STEPS = f"{SCHEMA}.automation_step"
_DEFAULT_APP_ROLE = "saas_os_app"
_BEFORE = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'wait')"
)
_AFTER = (
    "action IN ('add_tag', 'remove_tag', 'assign_owner', 'set_lifecycle_stage',"
    " 'create_task', 'notify_member', 'assign_round_robin', 'wait')"
)


def _app_role() -> str:
    value = os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


TABLE = f"""
CREATE TABLE {SCHEMA}.automation_rotation (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    automation_id uuid NOT NULL,
    branch text NOT NULL,
    position integer NOT NULL,
    handed_out bigint NOT NULL DEFAULT 0,
    CONSTRAINT automation_rotation_pkey PRIMARY KEY (tenant_id, automation_id, branch, position),
    CONSTRAINT automation_rotation_automation_fkey FOREIGN KEY (tenant_id, automation_id)
        REFERENCES {SCHEMA}.automation (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT automation_rotation_branch_check CHECK (branch IN ('yes', 'no')),
    CONSTRAINT automation_rotation_counts_check CHECK (position >= 0 AND handed_out >= 0)
)
"""


def _check(expression: str) -> None:
    op.execute(f"ALTER TABLE {STEPS} DROP CONSTRAINT automation_step_action_check")
    op.execute(
        f"ALTER TABLE {STEPS} ADD CONSTRAINT automation_step_action_check CHECK ({expression})"
    )


def upgrade() -> None:
    _check(_AFTER)
    op.execute(TABLE)
    for statement in tenant_rls_statements("automation_rotation", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.automation_rotation TO "{_app_role()}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.automation_rotation")
    with all_rows(STEPS):
        op.execute(f"DELETE FROM {STEPS} WHERE action = 'assign_round_robin'")
    _check(_BEFORE)
