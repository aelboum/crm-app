"""Create the task table (Phase 4 slice 4C, decision P4-C).

Revision ID: 0012_tasks
Revises: 0011_opportunities
Create Date: 2026-10-27

One tenant-owned table with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements`, SELECT, INSERT, UPDATE, DELETE for
the runtime role, and a place in `crm_app.purge.PURGE_TABLES`:

- `task`: a to-do with a title, a priority, an optional due time, an
  optional assignee and a completion. Its optional links to a contact, a
  company and a deal are composite, `(tenant_id, x_id) → (tenant_id, id)`,
  so a task can never point into another workspace even with RLS bypassed,
  and `ON DELETE SET NULL` of the link column only, so a task outlives the
  record it was about (P4-C 2). `completed_at` and `completed_by_user_id`
  are set together, exactly while the task is done.

Downgrade drops the table with its rows: for test and development databases
only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0012_tasks"
down_revision: str | Sequence[str] | None = "0011_opportunities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

TITLE_MAX = 200


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _link(column: str, table: str) -> str:
    return f"""CONSTRAINT task_{table}_fkey FOREIGN KEY (tenant_id, {column})
        REFERENCES {SCHEMA}.{table} (tenant_id, id) ON DELETE SET NULL ({column})"""


TASK = f"""
CREATE TABLE {SCHEMA}.task (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    title text NOT NULL,
    priority text NOT NULL DEFAULT 'medium',
    due_at timestamptz,
    assignee_user_id uuid,
    contact_id uuid,
    company_id uuid,
    opportunity_id uuid,
    completed_at timestamptz,
    completed_by_user_id uuid,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT task_tenant_id_id_key UNIQUE (tenant_id, id),
    {_link("contact_id", "contact")},
    {_link("company_id", "company")},
    {_link("opportunity_id", "opportunity")},
    -- Trimmed, 1-{TITLE_MAX} characters, no control characters.
    CONSTRAINT task_title_check CHECK (
        char_length(title) BETWEEN 1 AND {TITLE_MAX}
        AND title = btrim(title)
        AND title !~ '[\\x01-\\x1f\\x7f]'
    ),
    CONSTRAINT task_priority_check CHECK (priority IN ('high', 'medium', 'low')),
    CONSTRAINT task_completed_check CHECK (
        (completed_at IS NULL) = (completed_by_user_id IS NULL)
    )
)
"""

INDEXES = (
    # Open tasks by due time (the default list and the overdue count), and
    # the assignee's own.
    f"CREATE INDEX task_open_due_idx ON {SCHEMA}.task (tenant_id, due_at, id)"
    " WHERE completed_at IS NULL",
    f"CREATE INDEX task_assignee_idx ON {SCHEMA}.task (tenant_id, assignee_user_id)"
    " WHERE assignee_user_id IS NOT NULL",
    f"CREATE INDEX task_completed_idx ON {SCHEMA}.task (tenant_id, completed_at DESC, id DESC)"
    " WHERE completed_at IS NOT NULL",
    # The record drawers' task lists and the SET NULL from a deleted record.
    f"CREATE INDEX task_contact_idx ON {SCHEMA}.task (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
    f"CREATE INDEX task_company_idx ON {SCHEMA}.task (tenant_id, company_id)"
    " WHERE company_id IS NOT NULL",
    f"CREATE INDEX task_opportunity_idx ON {SCHEMA}.task (tenant_id, opportunity_id)"
    " WHERE opportunity_id IS NOT NULL",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TASK)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("task", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.task TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.task")
