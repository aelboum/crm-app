"""The queue of campaigns waiting to be sent (decision P7-S).

Revision ID: 0046_campaign_queue
Revises: 0045_email_headers
Create Date: 2026-11-18

- `campaign_queue`: global (tenant-context exclusion). One row per queued
  campaign, so the email maintenance run finds them without reading every
  workspace: the campaign's and workspace's ids, the member who queued it,
  and a time. The campaign itself stays the authority: a row whose
  campaign is not queued or processing is removed.

The purge participant removes a workspace's rows. Downgrade drops the
table: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements

revision: str = "0046_campaign_queue"
down_revision: str | Sequence[str] | None = "0045_email_headers"
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


QUEUE = f"""
CREATE TABLE {SCHEMA}.campaign_queue (
    campaign_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    queued_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""


def upgrade() -> None:
    op.execute(QUEUE)
    op.execute(
        f"CREATE INDEX campaign_queue_workspace_idx ON {SCHEMA}.campaign_queue (workspace_id)"
    )
    for statement in tenant_context_exclusion_statements("campaign_queue", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.campaign_queue TO "{_app_role()}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.campaign_queue")
