"""Create the pipeline tables (Phase 4 slice 4A, decision P4).

Revision ID: 0010_pipelines
Revises: 0009_imports
Create Date: 2026-10-27

Two tenant-owned tables, each with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements` and SELECT, INSERT, UPDATE,
DELETE for the runtime role, in this same migration, and each in
`crm_app.purge.PURGE_TABLES`:

- `pipeline`: a sales pipeline. The schema allows several per workspace;
  the product offers one for now (P4 4A.1). Its `version` covers the whole
  configuration, stages included (P4 4A.5). A name is unique per workspace
  regardless of case.
- `pipeline_stage`: an open stage of a pipeline (won and lost are a deal's
  outcome, not stages; P2-E). A name is unique per pipeline regardless of
  case; the probability is a whole percentage; positions are unique per
  pipeline, checked at commit so a reorder can swap them. The reference to
  the pipeline is composite, `(tenant_id, pipeline_id)`, so a stage can
  never belong to another workspace's pipeline, and deleting a pipeline
  deletes its stages. `(tenant_id, pipeline_id, id)` is unique so a deal
  (slice 4B) can reference a stage of its own pipeline.

Names are trimmed, without control characters: a pipeline's 1-60
characters, a stage's 1-40.

Downgrade drops both tables with their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0010_pipelines"
down_revision: str | Sequence[str] | None = "0009_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

PIPELINE_NAME_MAX = 60
STAGE_NAME_MAX = 40


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _name_rule(constraint: str, maximum: int) -> str:
    return f"""CONSTRAINT {constraint} CHECK (
        char_length(name) BETWEEN 1 AND {maximum}
        AND name = btrim(name)
        AND name !~ '[\\x01-\\x1f\\x7f]'
    )"""


PIPELINE = f"""
CREATE TABLE {SCHEMA}.pipeline (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT pipeline_tenant_id_id_key UNIQUE (tenant_id, id),
    {_name_rule("pipeline_name_check", PIPELINE_NAME_MAX)}
)
"""

STAGE = f"""
CREATE TABLE {SCHEMA}.pipeline_stage (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    pipeline_id uuid NOT NULL,
    name text NOT NULL,
    probability smallint NOT NULL,
    position integer NOT NULL,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pipeline_stage_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT pipeline_stage_tenant_pipeline_id_key UNIQUE (tenant_id, pipeline_id, id),
    CONSTRAINT pipeline_stage_position_key UNIQUE (tenant_id, pipeline_id, position)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT pipeline_stage_pipeline_fkey FOREIGN KEY (tenant_id, pipeline_id)
        REFERENCES {SCHEMA}.pipeline (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT pipeline_stage_probability_check CHECK (probability BETWEEN 0 AND 100),
    CONSTRAINT pipeline_stage_position_check CHECK (position >= 0),
    {_name_rule("pipeline_stage_name_check", STAGE_NAME_MAX)}
)
"""

INDEXES = (
    # One name per workspace, and per pipeline, whatever its case.
    f"CREATE UNIQUE INDEX pipeline_name_key ON {SCHEMA}.pipeline (tenant_id, lower(name))",
    f"CREATE UNIQUE INDEX pipeline_stage_name_key"
    f" ON {SCHEMA}.pipeline_stage (tenant_id, pipeline_id, lower(name))",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(PIPELINE)
    op.execute(STAGE)
    for statement in INDEXES:
        op.execute(statement)
    for table in ("pipeline", "pipeline_stage"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.pipeline_stage")
    op.execute(f"DROP TABLE {SCHEMA}.pipeline")
