"""Automations: definitions, versions, runs and steps (Phase 8 slice 8A,
decision P8-A).

Revision ID: 0021_automations
Revises: 0020_booking_confirmation
Create Date: 2026-11-01

- `automation`: tenant-owned. A workflow's name, status (`draft`,
  `active`, `paused`), its editable draft definition (JSON validated by
  `crm_app.domains.automations`) and the active version's number.
- `automation_version`: tenant-owned, immutable (no UPDATE for the runtime
  role). The definition as activated; runs follow the version they began
  with.
- `automation_run`: tenant-owned. One run of one automation for one
  contact, at most once per automation and contact (a unique key), with
  its branch, next step, status and wake-up time.
- `automation_step`: tenant-owned, append-only. One executed step, unique
  per run, branch and position, written in the same transaction as the
  step's effect: a retried job finds it and does not act again.
- `automation_due`: global (tenant-context exclusion policy, as
  `email_index`): which run of which workspace is due when. Ids and times
  only; the purge participant removes a workspace's rows.

All tenant tables have forced Row-Level Security and are in
`crm_app.purge.PURGE_TABLES`. Downgrade drops the five tables: for test and
development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0021_automations"
down_revision: str | Sequence[str] | None = "0020_booking_confirmation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"
NAME_MAX = 100


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


AUTOMATION = f"""
CREATE TABLE {SCHEMA}.automation (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    trigger_type text NOT NULL,
    definition jsonb NOT NULL,
    active_version integer,
    activated_by_user_id uuid,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT automation_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT automation_name_check CHECK (
        char_length(name) BETWEEN 1 AND {NAME_MAX} AND name = btrim(name)
        AND name !~ '[\\x00-\\x1f\\x7f]'
    ),
    CONSTRAINT automation_status_check CHECK (status IN ('draft', 'active', 'paused')),
    CONSTRAINT automation_trigger_check CHECK (trigger_type IN ('contact_created')),
    CONSTRAINT automation_definition_check CHECK (jsonb_typeof(definition) = 'object'),
    CONSTRAINT automation_active_check CHECK (
        (status = 'draft') = (active_version IS NULL)
        AND (active_version IS NULL) = (activated_by_user_id IS NULL)
    )
)
"""

VERSION = f"""
CREATE TABLE {SCHEMA}.automation_version (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    automation_id uuid NOT NULL,
    number integer NOT NULL CHECK (number >= 1),
    definition jsonb NOT NULL,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT automation_version_pkey PRIMARY KEY (tenant_id, automation_id, number),
    CONSTRAINT automation_version_automation_fkey FOREIGN KEY (tenant_id, automation_id)
        REFERENCES {SCHEMA}.automation (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT automation_version_definition_check CHECK (jsonb_typeof(definition) = 'object')
)
"""

RUN = f"""
CREATE TABLE {SCHEMA}.automation_run (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    automation_id uuid NOT NULL,
    version_number integer NOT NULL,
    contact_id uuid,
    branch text,
    next_step integer NOT NULL DEFAULT 0 CHECK (next_step BETWEEN 0 AND 100),
    status text NOT NULL DEFAULT 'running',
    resume_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 100),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CONSTRAINT automation_run_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT automation_run_once_key UNIQUE (tenant_id, automation_id, contact_id),
    CONSTRAINT automation_run_version_fkey FOREIGN KEY (tenant_id, automation_id, version_number)
        REFERENCES {SCHEMA}.automation_version (tenant_id, automation_id, number) ON DELETE CASCADE,
    CONSTRAINT automation_run_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT automation_run_branch_check CHECK (branch IS NULL OR branch IN ('yes', 'no')),
    CONSTRAINT automation_run_status_check CHECK (
        status IN ('running', 'waiting', 'completed', 'failed', 'cancelled')
    ),
    CONSTRAINT automation_run_wait_check CHECK ((status = 'waiting') = (resume_at IS NOT NULL)),
    CONSTRAINT automation_run_finished_check CHECK (
        (finished_at IS NOT NULL) = (status IN ('completed', 'failed', 'cancelled'))
    ),
    CONSTRAINT automation_run_error_check CHECK (
        last_error IS NULL OR last_error ~ '^[a-z0-9_]{{1,64}}$'
    )
)
"""

STEP = f"""
CREATE TABLE {SCHEMA}.automation_step (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    run_id uuid NOT NULL,
    branch text NOT NULL,
    position integer NOT NULL CHECK (position BETWEEN 0 AND 100),
    action text NOT NULL,
    outcome text NOT NULL,
    detail text,
    executed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT automation_step_pkey PRIMARY KEY (tenant_id, run_id, branch, position),
    CONSTRAINT automation_step_run_fkey FOREIGN KEY (tenant_id, run_id)
        REFERENCES {SCHEMA}.automation_run (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT automation_step_branch_check CHECK (branch IN ('yes', 'no')),
    CONSTRAINT automation_step_action_check CHECK (
        action IN ('add_tag', 'assign_owner', 'create_task', 'wait')
    ),
    CONSTRAINT automation_step_outcome_check CHECK (outcome IN ('done', 'skipped')),
    CONSTRAINT automation_step_detail_check CHECK (
        detail IS NULL OR detail ~ '^[a-z0-9_]{{1,64}}$'
    )
)
"""

DUE = f"""
CREATE TABLE {SCHEMA}.automation_due (
    run_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    due_at timestamptz NOT NULL
)
"""

INDEXES = (
    f"CREATE INDEX automation_list_idx ON {SCHEMA}.automation (tenant_id, created_at, id)",
    f"CREATE INDEX automation_active_idx ON {SCHEMA}.automation (tenant_id, trigger_type)"
    " WHERE status = 'active'",
    f"CREATE INDEX automation_run_recent_idx ON {SCHEMA}.automation_run"
    " (tenant_id, automation_id, created_at DESC, id DESC)",
    f"CREATE INDEX automation_run_contact_idx ON {SCHEMA}.automation_run (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
    f"CREATE INDEX automation_due_idx ON {SCHEMA}.automation_due (due_at)",
)


def upgrade() -> None:
    app_role = _app_role()
    for statement in (AUTOMATION, VERSION, RUN, STEP, DUE, *INDEXES):
        op.execute(statement)
    grants = {
        "automation": "SELECT, INSERT, UPDATE, DELETE",
        # Immutable and append-only: DELETE only for the purge and cascades.
        "automation_version": "SELECT, INSERT, DELETE",
        "automation_run": "SELECT, INSERT, UPDATE, DELETE",
        "automation_step": "SELECT, INSERT, DELETE",
    }
    for table, privileges in grants.items():
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT {privileges} ON {SCHEMA}.{table} TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("automation_due", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.automation_due TO "{app_role}"')


def downgrade() -> None:
    for table in (
        "automation_due",
        "automation_step",
        "automation_run",
        "automation_version",
        "automation",
    ):
        op.execute(f"DROP TABLE {SCHEMA}.{table}")
