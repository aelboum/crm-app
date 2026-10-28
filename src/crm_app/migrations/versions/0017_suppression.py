"""Create the suppression table and widen consent records (Phase 7 slice 7B,
decision P7-B).

Revision ID: 0017_suppression
Revises: 0016_booking_pages
Create Date: 2026-10-28

- `suppression`: tenant-owned, forced Row-Level Security from
  `saas_os.infra.db.tenant_rls_statements`, in
  `crm_app.purge.PURGE_TABLES`. One row per email address the workspace
  must not send to (P7-B 2), lower-cased and unique per workspace. It has
  no link to a contact, so deleting or changing a contact never lifts it.
  Rows are added and removed, never changed: the runtime role holds
  SELECT, INSERT and DELETE.
- `consent_record` stays append-only (the runtime role still has no
  UPDATE) and gains status `withdrawn`, method `manual` and the member who
  recorded it (P7-B 3). Wording is required for `granted` and an optional
  note for `withdrawn`.

Downgrade drops the suppression table with its rows and deletes the
withdrawn and manual consent records, so the narrower checks hold again:
for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0017_suppression"
down_revision: str | Sequence[str] | None = "0016_booking_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

EMAIL_MAX = 320
NOTE_MAX = 500
MESSAGE_MAX = 500
REASONS = ("unsubscribed", "bounced", "complained", "manual")
ORIGINS = ("manual", "consent_withdrawn")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _message(column: str) -> str:
    """Trimmed, 1-500 characters; line breaks allowed."""
    return f"""char_length({column}) BETWEEN 1 AND {MESSAGE_MAX}
        AND {column} = btrim({column})
        AND {column} !~ '[\\x01-\\x09\\x0b-\\x1f\\x7f]'"""


SUPPRESSION = f"""
CREATE TABLE {SCHEMA}.suppression (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    email text NOT NULL,
    reason text NOT NULL,
    origin text NOT NULL DEFAULT 'manual',
    note text,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT suppression_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT suppression_tenant_id_email_key UNIQUE (tenant_id, email),
    -- Lower-cased and trimmed, as `crm_app.domains.records.email` stores it.
    CONSTRAINT suppression_email_check CHECK (
        char_length(email) BETWEEN 3 AND {EMAIL_MAX}
        AND email = lower(btrim(email))
        AND email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'
    ),
    CONSTRAINT suppression_reason_check CHECK (reason IN ({_in(REASONS)})),
    CONSTRAINT suppression_origin_check CHECK (origin IN ({_in(ORIGINS)})),
    CONSTRAINT suppression_note_check CHECK (note IS NULL OR ({_message("note")}))
)
"""

INDEXES = (
    # The list, newest first.
    f"CREATE INDEX suppression_list_idx ON {SCHEMA}.suppression"
    " (tenant_id, created_at DESC, id DESC)",
)


def _replace_check(name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    app_role = _app_role()
    op.execute(SUPPRESSION)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("suppression", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.suppression TO "{app_role}"')
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record ADD COLUMN recorded_by_user_id uuid")
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record ALTER COLUMN wording DROP NOT NULL")
    _replace_check("consent_record_status_check", "status IN ('granted', 'withdrawn')")
    _replace_check("consent_record_method_check", "method IN ('web_form', 'manual')")
    _replace_check(
        "consent_record_wording_check",
        f"(wording IS NULL OR ({_message('wording')}))"
        " AND (status <> 'granted' OR wording IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.suppression")
    op.execute(
        f"DELETE FROM {SCHEMA}.consent_record WHERE status <> 'granted' OR method <> 'web_form'"
    )
    _replace_check("consent_record_status_check", "status IN ('granted')")
    _replace_check("consent_record_method_check", "method IN ('web_form')")
    _replace_check("consent_record_wording_check", _message("wording"))
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record ALTER COLUMN wording SET NOT NULL")
    op.execute(f"ALTER TABLE {SCHEMA}.consent_record DROP COLUMN recorded_by_user_id")
