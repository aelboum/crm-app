"""Reusable email templates (Phase 7 slice 7T, decision P7-T).

Revision ID: 0033_email_templates
Revises: 0032_automation_triggers
Create Date: 2026-11-02

`email_template`: tenant-owned, forced Row-Level Security. A named subject
and plain-text body with the campaign placeholders (`{{first_name}}`,
`{{last_name}}`), copied into a campaign or rendered for a conversation's
contact; a template never sends anything itself. Names are unique per
workspace. In `crm_app.purge.PURGE_TABLES`. Downgrade drops the table: for
test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0033_email_templates"
down_revision: str | Sequence[str] | None = "0032_automation_triggers"
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


TEMPLATE = f"""
CREATE TABLE {SCHEMA}.email_template (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT email_template_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT email_template_name_key UNIQUE (tenant_id, name),
    CONSTRAINT email_template_name_check CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT email_template_subject_check CHECK (
        char_length(subject) BETWEEN 1 AND 200 AND subject !~ '[\\x00-\\x1f\\x7f]'
    ),
    CONSTRAINT email_template_body_check CHECK (char_length(body) BETWEEN 1 AND 18000)
)
"""

INDEX = (
    f"CREATE INDEX email_template_recent_idx ON {SCHEMA}.email_template"
    " (tenant_id, updated_at DESC, id DESC)"
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(TEMPLATE)
    op.execute(INDEX)
    for statement in tenant_rls_statements("email_template", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.email_template TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.email_template")
