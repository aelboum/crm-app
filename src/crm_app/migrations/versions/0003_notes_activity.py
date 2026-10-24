"""Create the note and activity tables (Phase 3 slice 3B, decision P3-B).

Revision ID: 0003_notes_activity
Revises: 0002_contacts_companies
Create Date: 2026-10-24

Both tables are tenant-owned (`PHASE3-PLAN.md` §21): forced Row-Level
Security from `saas_os.infra.db.tenant_rls_statements` in this same
migration, and both are in `crm_app.purge.PURGE_TABLES`.

- `note`: plain-text notes on one contact or one company, editable with a
  version for optimistic locking. The runtime role holds SELECT, INSERT,
  UPDATE, DELETE.
- `activity`: the record's user-visible history. Append-only for the
  application (decision P3-B D6): the runtime role holds SELECT, INSERT and
  DELETE but not UPDATE, so no application code can change an entry. DELETE
  stays because purge and the cascades from a deleted record or note must
  remove entries. Entries carry field names, the fixed stage values and
  member user IDs only; never field values or note text (D5).

Every reference is composite, `(tenant_id, x_id) → (tenant_id, id)`, so a
link to another workspace's record is impossible even with RLS bypassed.
Deleting a contact or company removes its notes and activity; deleting a
note removes its `note_added` entry (`ON DELETE CASCADE`). A contact's
`company_linked`/`company_unlinked` entry names the company in
`company_ref_id` without a key, because that company may later be deleted.

The upgrade backfills one `created` entry for every existing contact and
company from its own `created_at` and `created_by_user_id` (D7). It runs
once per workspace with `app.tenant_id` set, so it works under forced RLS
whether or not the migration role bypasses it.

Downgrade drops both tables and their rows: for test and development
databases only, never a way to recover production data.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0003_notes_activity"
down_revision: str | Sequence[str] | None = "0002_contacts_companies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

STAGES = ("lead", "prospect", "customer", "inactive")
KINDS = (
    "created",
    "updated",
    "archived",
    "restored",
    "stage_changed",
    "owner_changed",
    "company_linked",
    "company_unlinked",
    "note_added",
    "note_deleted",
)
# Fields an `updated` entry may name. Stage, owner and company changes have
# their own kinds and never appear here.
UPDATED_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "job_title",
    "city",
    "source",
    "name",
    "domain",
    "website",
    "industry",
    "country_code",
)
NOTE_MAX = 10_000


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _parents(table: str) -> str:
    """Exactly one parent record, each by a composite key that is deleted
    with the parent."""
    return f"""
    contact_id uuid,
    company_id uuid,
    CONSTRAINT {table}_one_parent_check CHECK (num_nonnulls(contact_id, company_id) = 1),
    CONSTRAINT {table}_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT {table}_company_fkey FOREIGN KEY (tenant_id, company_id)
        REFERENCES {SCHEMA}.company (tenant_id, id) ON DELETE CASCADE"""


NOTE = f"""
CREATE TABLE {SCHEMA}.note (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    body text NOT NULL,
    author_user_id uuid NOT NULL,
    updated_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT note_tenant_id_id_key UNIQUE (tenant_id, id),{_parents("note")},
    -- Plain text: trimmed, not blank, at most {NOTE_MAX} characters, line
    -- breaks as LF only and no control character other than tab and LF.
    CONSTRAINT note_body_check CHECK (
        char_length(body) BETWEEN 1 AND {NOTE_MAX}
        AND body = btrim(body, E' \\t\\n')
        AND body !~ '[\\x01-\\x08\\x0b-\\x1f\\x7f]'
    )
)
"""

ACTIVITY = f"""
CREATE TABLE {SCHEMA}.activity (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    kind text NOT NULL,
    actor_user_id uuid,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    fields jsonb,
    stage_from text,
    stage_to text,
    owner_from uuid,
    owner_to uuid,
    company_ref_id uuid,
    note_id uuid,
    CONSTRAINT activity_tenant_id_id_key UNIQUE (tenant_id, id),{_parents("activity")},
    CONSTRAINT activity_note_fkey FOREIGN KEY (tenant_id, note_id)
        REFERENCES {SCHEMA}.note (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT activity_kind_check CHECK (kind IN ({_in(KINDS)})),
    -- `updated` names the changed fields, and only from the allow-list.
    CONSTRAINT activity_fields_check CHECK (
        (kind = 'updated') = (fields IS NOT NULL)
        AND (
            fields IS NULL OR (
                jsonb_typeof(fields) = 'array'
                AND jsonb_array_length(fields) BETWEEN 1 AND {len(UPDATED_FIELDS)}
                AND fields <@ '[{", ".join(f'"{name}"' for name in UPDATED_FIELDS)}]'::jsonb
            )
        )
    ),
    -- Stages are the fixed P3-A values, on contacts only.
    CONSTRAINT activity_stage_check CHECK (
        (kind = 'stage_changed') = (stage_to IS NOT NULL)
        AND (kind = 'stage_changed' OR stage_from IS NULL)
        AND (stage_to IS NULL OR (contact_id IS NOT NULL AND stage_to IN ({_in(STAGES)})))
        AND (stage_from IS NULL OR stage_from IN ({_in(STAGES)}))
        AND (stage_to IS NULL OR stage_from IS DISTINCT FROM stage_to)
    ),
    CONSTRAINT activity_owner_check CHECK (
        (kind = 'owner_changed' AND owner_from IS DISTINCT FROM owner_to)
        OR (kind <> 'owner_changed' AND owner_from IS NULL AND owner_to IS NULL)
    ),
    CONSTRAINT activity_company_ref_check CHECK (
        (kind IN ('company_linked', 'company_unlinked'))
            = (company_ref_id IS NOT NULL AND contact_id IS NOT NULL)
    ),
    CONSTRAINT activity_note_check CHECK ((kind = 'note_added') = (note_id IS NOT NULL))
)
"""

INDEXES = (
    # Newest first per record (PHASE3-PLAN.md §21): the list order, with `id`
    # breaking ties.
    f"CREATE INDEX note_contact_order_idx ON {SCHEMA}.note"
    " (tenant_id, contact_id, created_at DESC, id DESC) WHERE contact_id IS NOT NULL",
    f"CREATE INDEX note_company_order_idx ON {SCHEMA}.note"
    " (tenant_id, company_id, created_at DESC, id DESC) WHERE company_id IS NOT NULL",
    f"CREATE INDEX activity_contact_order_idx ON {SCHEMA}.activity"
    " (tenant_id, contact_id, occurred_at DESC, id DESC) WHERE contact_id IS NOT NULL",
    f"CREATE INDEX activity_company_order_idx ON {SCHEMA}.activity"
    " (tenant_id, company_id, occurred_at DESC, id DESC) WHERE company_id IS NOT NULL",
    # The cascade from a deleted note.
    f"CREATE INDEX activity_note_idx ON {SCHEMA}.activity (tenant_id, note_id)"
    " WHERE note_id IS NOT NULL",
)

# One `created` entry per existing record, workspace by workspace, so forced
# RLS admits each insert. `core.tenants` has no RLS. The setting is
# transaction-local and cleared afterwards.
BACKFILL = f"""
DO $$
DECLARE
    workspace uuid;
BEGIN
    FOR workspace IN SELECT id FROM core.tenants LOOP
        PERFORM set_config('app.tenant_id', workspace::text, true);
        INSERT INTO {SCHEMA}.activity (id, tenant_id, company_id, kind, actor_user_id, occurred_at)
            SELECT gen_random_uuid(), tenant_id, id, 'created', created_by_user_id, created_at
            FROM {SCHEMA}.company WHERE tenant_id = workspace;
        INSERT INTO {SCHEMA}.activity (id, tenant_id, contact_id, kind, actor_user_id, occurred_at)
            SELECT gen_random_uuid(), tenant_id, id, 'created', created_by_user_id, created_at
            FROM {SCHEMA}.contact WHERE tenant_id = workspace;
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$
"""


def upgrade() -> None:
    app_role = _app_role()
    op.execute(NOTE)
    op.execute(ACTIVITY)
    for statement in INDEXES:
        op.execute(statement)
    for table in ("note", "activity"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.note TO "{app_role}"')
    # Append-only for the application (D6): no UPDATE.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.activity TO "{app_role}"')
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.activity")
    op.execute(f"DROP TABLE {SCHEMA}.note")
