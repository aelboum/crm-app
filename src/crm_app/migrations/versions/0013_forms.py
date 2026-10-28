"""Create the form, form_submission and consent_record tables (Phase 7 slice
7A, decision P7-A).

Revision ID: 0013_forms
Revises: 0012_tasks
Create Date: 2026-10-28

Three tenant-owned tables with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements` and a place in
`crm_app.purge.PURGE_TABLES`:

- `form`: a lead-capture form. Its fields are a JSON array the service
  validates (P7-A 3); the database checks only its shape and size. The
  public key is random and unique across all workspaces; the hosted page's
  address names both the workspace and the key. The optional tag is a
  composite key `ON DELETE SET NULL (tag_id)`.
- `form_submission`: one accepted submission. It goes with its form
  (`ON DELETE CASCADE`); its contact link is cleared when the contact is
  deleted (`ON DELETE SET NULL (contact_id)`).
- `consent_record`: append-only evidence that a contact gave consent
  (P7-A 7): the runtime role holds SELECT, INSERT and DELETE, never UPDATE.
  It goes with its contact; its form and submission links are cleared, not
  cascaded, so the evidence outlives the form (P7-A 9).

Every link is composite, `(tenant_id, x_id) → (tenant_id, id)`, so no row
can point into another workspace even with RLS bypassed.

Downgrade drops the tables with their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0013_forms"
down_revision: str | Sequence[str] | None = "0012_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

NAME_MAX = 120
FIELDS_MAX = 20
MESSAGE_MAX = 500
KEY_LENGTH = 22


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _text(column: str, maximum: int) -> str:
    """Trimmed, 1-`maximum` characters, no control characters."""
    return f"""char_length({column}) BETWEEN 1 AND {maximum}
        AND {column} = btrim({column})
        AND {column} !~ '[\\x01-\\x1f\\x7f]'"""


def _message(column: str) -> str:
    """Trimmed, 1-500 characters; line breaks allowed."""
    return f"""char_length({column}) BETWEEN 1 AND {MESSAGE_MAX}
        AND {column} = btrim({column})
        AND {column} !~ '[\\x01-\\x09\\x0b-\\x1f\\x7f]'"""


FORM = f"""
CREATE TABLE {SCHEMA}.form (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    public_key text NOT NULL,
    fields jsonb NOT NULL,
    tag_id uuid,
    thank_you text NOT NULL,
    consent_text text,
    contact_owner_user_id uuid NOT NULL,
    submission_count integer NOT NULL DEFAULT 0 CHECK (submission_count >= 0),
    last_submission_at timestamptz,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT form_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT form_public_key_key UNIQUE (public_key),
    CONSTRAINT form_tag_fkey FOREIGN KEY (tenant_id, tag_id)
        REFERENCES {SCHEMA}.tag (tenant_id, id) ON DELETE SET NULL (tag_id),
    CONSTRAINT form_name_check CHECK ({_text("name", NAME_MAX)}),
    CONSTRAINT form_status_check CHECK (status IN ('draft', 'published')),
    CONSTRAINT form_public_key_check CHECK (public_key ~ '^[A-Za-z0-9_-]{{{KEY_LENGTH}}}$'),
    CONSTRAINT form_fields_check CHECK (
        jsonb_typeof(fields) = 'array'
        AND jsonb_array_length(fields) BETWEEN 1 AND {FIELDS_MAX}
    ),
    CONSTRAINT form_thank_you_check CHECK ({_message("thank_you")}),
    CONSTRAINT form_consent_text_check CHECK (
        consent_text IS NULL OR ({_message("consent_text")})
    )
)
"""

SUBMISSION = f"""
CREATE TABLE {SCHEMA}.form_submission (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    form_id uuid NOT NULL,
    contact_id uuid,
    answers jsonb NOT NULL,
    outcome text NOT NULL,
    consent boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT form_submission_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT form_submission_form_fkey FOREIGN KEY (tenant_id, form_id)
        REFERENCES {SCHEMA}.form (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT form_submission_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT form_submission_answers_check CHECK (jsonb_typeof(answers) = 'object'),
    CONSTRAINT form_submission_outcome_check CHECK (outcome IN ('created', 'matched'))
)
"""

CONSENT = f"""
CREATE TABLE {SCHEMA}.consent_record (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    contact_id uuid NOT NULL,
    channel text NOT NULL,
    status text NOT NULL,
    method text NOT NULL,
    wording text NOT NULL,
    form_id uuid,
    submission_id uuid,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT consent_record_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT consent_record_form_fkey FOREIGN KEY (tenant_id, form_id)
        REFERENCES {SCHEMA}.form (tenant_id, id) ON DELETE SET NULL (form_id),
    CONSTRAINT consent_record_submission_fkey FOREIGN KEY (tenant_id, submission_id)
        REFERENCES {SCHEMA}.form_submission (tenant_id, id) ON DELETE SET NULL (submission_id),
    CONSTRAINT consent_record_channel_check CHECK (channel IN ('email')),
    CONSTRAINT consent_record_status_check CHECK (status IN ('granted')),
    CONSTRAINT consent_record_method_check CHECK (method IN ('web_form')),
    CONSTRAINT consent_record_wording_check CHECK ({_message("wording")})
)
"""

INDEXES = (
    f"CREATE INDEX form_list_idx ON {SCHEMA}.form (tenant_id, updated_at DESC, id DESC)",
    f"CREATE INDEX form_tag_idx ON {SCHEMA}.form (tenant_id, tag_id) WHERE tag_id IS NOT NULL",
    # A form's submissions, newest first, and the cascade from a form.
    f"CREATE INDEX form_submission_form_idx ON {SCHEMA}.form_submission"
    " (tenant_id, form_id, created_at DESC, id DESC)",
    f"CREATE INDEX form_submission_contact_idx ON {SCHEMA}.form_submission"
    " (tenant_id, contact_id) WHERE contact_id IS NOT NULL",
    f"CREATE INDEX consent_record_contact_idx ON {SCHEMA}.consent_record"
    " (tenant_id, contact_id, recorded_at DESC)",
    f"CREATE INDEX consent_record_form_idx ON {SCHEMA}.consent_record"
    " (tenant_id, form_id) WHERE form_id IS NOT NULL",
    f"CREATE INDEX consent_record_submission_idx ON {SCHEMA}.consent_record"
    " (tenant_id, submission_id) WHERE submission_id IS NOT NULL",
)


def upgrade() -> None:
    app_role = _app_role()
    for statement in (FORM, SUBMISSION, CONSENT, *INDEXES):
        op.execute(statement)
    for table in ("form", "form_submission", "consent_record"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
    for table in ("form", "form_submission"):
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.consent_record TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.consent_record")
    op.execute(f"DROP TABLE {SCHEMA}.form_submission")
    op.execute(f"DROP TABLE {SCHEMA}.form")
