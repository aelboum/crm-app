"""CSV import staging (Phase 3 slice 3F, decision P3-F).

Revision ID: 0009_imports
Revises: 0008_custom_fields
Create Date: 2026-10-26

- `import_job`: one import of contacts or companies: its status, counts,
  the field-to-column mapping by position, and the commit checkpoint. It
  holds no cell value. A partial unique index allows one queued or running
  import per workspace.
- `import_row`: one data row of the file, as normalised values (personal
  data) or as error codes with field names, and the record it created.
  Deleted with its job (`ON DELETE CASCADE`) and by the 7-day retention
  (P3-F 7).

Both are tenant-owned: forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements`, SELECT, INSERT, UPDATE, DELETE
for the runtime role, composite keys, and both in
`crm_app.purge.PURGE_TABLES`.

- `import_expiry`: a global table (no `tenant_id`), because no SaaS-OS
  authority lets product code list every workspace: which import's rows are
  due for deletion, in which workspace, and when. No personal data. It
  carries SaaS-OS's tenant-context exclusion policy (as `signup` does), so
  only a transaction without a workspace sees it; it names the workspace
  without a key into `core.tenants`, and the purge participant removes its
  rows (`crm_app.purge.PURGE_GLOBAL_REFERENCES`).

Downgrade drops the three tables and their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements, tenant_rls_statements

revision: str = "0009_imports"
down_revision: str | Sequence[str] | None = "0008_custom_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

ENTITIES = ("contact", "company")
JOB_STATUSES = (
    "previewed",
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
    "expired",
)
FINISHED = ("completed", "completed_with_errors", "failed", "cancelled", "expired")
ROW_STATUSES = ("valid", "invalid", "duplicate", "created", "skipped", "failed")
MAX_ROWS = 10_000


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_COUNTS = ("total_rows", "valid_rows", "invalid_rows", "duplicate_rows")
_RESULTS = ("created_rows", "skipped_rows", "failed_rows")

JOB = f"""
CREATE TABLE {SCHEMA}.import_job (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    entity text NOT NULL,
    status text NOT NULL,
    mapping jsonb NOT NULL,
    {", ".join(f"{name} integer NOT NULL DEFAULT 0" for name in (*_COUNTS, *_RESULTS))},
    checkpoint integer NOT NULL DEFAULT 0,
    cancel_requested boolean NOT NULL DEFAULT false,
    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT import_job_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT import_job_entity_check CHECK (entity IN ({_in(ENTITIES)})),
    CONSTRAINT import_job_status_check CHECK (status IN ({_in(JOB_STATUSES)})),
    CONSTRAINT import_job_mapping_check CHECK (jsonb_typeof(mapping) = 'object'),
    CONSTRAINT import_job_counts_check CHECK (
        {" AND ".join(f"{name} >= 0" for name in (*_COUNTS, *_RESULTS, "checkpoint"))}
        AND total_rows <= {MAX_ROWS}
        AND valid_rows + invalid_rows + duplicate_rows = total_rows
        AND checkpoint <= total_rows
    ),
    -- Finished exactly when the status says so.
    CONSTRAINT import_job_finished_check CHECK (
        (finished_at IS NOT NULL) = (status IN ({_in(FINISHED)}))
    )
)
"""

ROW = f"""
CREATE TABLE {SCHEMA}.import_row (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    import_id uuid NOT NULL,
    row_number integer NOT NULL,
    status text NOT NULL,
    data jsonb,
    errors jsonb,
    record_id uuid,
    CONSTRAINT import_row_pkey PRIMARY KEY (tenant_id, import_id, row_number),
    CONSTRAINT import_row_job_fkey FOREIGN KEY (tenant_id, import_id)
        REFERENCES {SCHEMA}.import_job (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT import_row_number_check CHECK (row_number BETWEEN 1 AND {MAX_ROWS}),
    CONSTRAINT import_row_status_check CHECK (status IN ({_in(ROW_STATUSES)})),
    -- Invalid rows keep error codes only; every other row keeps its values.
    CONSTRAINT import_row_payload_check CHECK (
        (status = 'invalid') = (errors IS NOT NULL)
        AND (status = 'invalid' OR (data IS NOT NULL AND jsonb_typeof(data) = 'object'))
        AND (status <> 'invalid' OR data IS NULL)
        AND (errors IS NULL OR jsonb_typeof(errors) = 'array')
    ),
    CONSTRAINT import_row_record_check CHECK ((status = 'created') = (record_id IS NOT NULL))
)
"""

EXPIRY = f"""
CREATE TABLE {SCHEMA}.import_expiry (
    import_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    due_at timestamptz NOT NULL
)
"""

INDEXES = (
    # One queued or running import per workspace (P3-F 5).
    f"CREATE UNIQUE INDEX import_job_one_active_key ON {SCHEMA}.import_job (tenant_id)"
    " WHERE status IN ('queued', 'running')",
    f"CREATE INDEX import_job_recent_idx ON {SCHEMA}.import_job (tenant_id, created_at DESC, id)",
    # The commit walks valid rows in order.
    f"CREATE INDEX import_row_status_idx ON {SCHEMA}.import_row"
    " (tenant_id, import_id, status, row_number)",
    f"CREATE INDEX import_expiry_due_idx ON {SCHEMA}.import_expiry (due_at)",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(JOB)
    op.execute(ROW)
    op.execute(EXPIRY)
    for statement in INDEXES:
        op.execute(statement)
    for table in ("import_job", "import_row"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    for statement in tenant_context_exclusion_statements("import_expiry", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.import_expiry TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.import_expiry")
    op.execute(f"DROP TABLE {SCHEMA}.import_row")
    op.execute(f"DROP TABLE {SCHEMA}.import_job")
