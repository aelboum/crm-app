"""Create the deal tables (Phase 4 slice 4B, decision P4-B).

Revision ID: 0011_opportunities
Revises: 0010_pipelines
Create Date: 2026-10-27

Two tenant-owned tables, each with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements`, and each in
`crm_app.purge.PURGE_TABLES`:

- `opportunity`: a deal. The runtime role holds SELECT, INSERT, UPDATE,
  DELETE. Every reference is composite, so nothing can point into another
  workspace even with RLS bypassed:
  - the stage through `(tenant_id, pipeline_id, stage_id)`, a stage of that
    very pipeline, `ON DELETE RESTRICT`: a stage holding deals is removed
    only after they are moved (P4-B 8);
  - the contact and the company with `ON DELETE SET NULL` of the link
    column only, so the deal outlives a deleted record (P4-B 4).
  `amount` is `numeric(15,3)`, never negative; `currency` is an ISO 4217
  code set by the server (P4-B 2). The outcome is `open`, `won` or `lost`;
  a lost deal has a reason, an open or won one none; `closed_at` is set
  exactly while the deal is won or lost (P4-B 5).
- `opportunity_event`: a deal's history. Append-only for the application
  (P4-B 7): the runtime role holds SELECT, INSERT and DELETE (purge and the
  cascade from a deleted deal) but not UPDATE. `seq` orders entries, also
  within one transaction. Entries carry field names, stage IDs with their
  names at the time, member user IDs and outcomes, never amounts, titles or
  the lost reason.

Downgrade drops both tables with their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0011_opportunities"
down_revision: str | Sequence[str] | None = "0010_pipelines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

TITLE_MAX = 200
LOST_REASON_MAX = 500
STAGE_NAME_MAX = 40
OUTCOMES = ("open", "won", "lost")
KINDS = ("created", "updated", "stage_changed", "owner_changed", "outcome_changed")
# Fields an `updated` entry may name. Stage, owner and outcome changes have
# their own kinds.
UPDATED_FIELDS = (
    "title",
    "amount",
    "expected_close_date",
    "contact_id",
    "company_id",
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _visible(column: str) -> str:
    """Trimmed, no control characters (the stage name rule of migration 0010)."""
    return f"{column} = btrim({column}) AND {column} !~ '[\\x01-\\x1f\\x7f]'"


OPPORTUNITY = f"""
CREATE TABLE {SCHEMA}.opportunity (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    title text NOT NULL,
    amount numeric(15, 3),
    currency text NOT NULL,
    pipeline_id uuid NOT NULL,
    stage_id uuid NOT NULL,
    stage_entered_at timestamptz NOT NULL DEFAULT now(),
    owner_user_id uuid,
    expected_close_date date,
    contact_id uuid,
    company_id uuid,
    outcome text NOT NULL DEFAULT 'open',
    lost_reason text,
    closed_at timestamptz,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT opportunity_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT opportunity_stage_fkey FOREIGN KEY (tenant_id, pipeline_id, stage_id)
        REFERENCES {SCHEMA}.pipeline_stage (tenant_id, pipeline_id, id) ON DELETE RESTRICT,
    CONSTRAINT opportunity_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT opportunity_company_fkey FOREIGN KEY (tenant_id, company_id)
        REFERENCES {SCHEMA}.company (tenant_id, id) ON DELETE SET NULL (company_id),
    CONSTRAINT opportunity_title_check CHECK (
        char_length(title) BETWEEN 1 AND {TITLE_MAX} AND {_visible("title")}
    ),
    CONSTRAINT opportunity_amount_check CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT opportunity_currency_check CHECK (currency ~ '^[A-Z]{{3}}$'),
    CONSTRAINT opportunity_outcome_check CHECK (outcome IN ({_in(OUTCOMES)})),
    CONSTRAINT opportunity_lost_reason_check CHECK (
        (outcome = 'lost') = (lost_reason IS NOT NULL)
        AND (
            lost_reason IS NULL OR (
                char_length(lost_reason) BETWEEN 1 AND {LOST_REASON_MAX}
                AND {_visible("lost_reason")}
            )
        )
    ),
    CONSTRAINT opportunity_closed_at_check CHECK ((outcome = 'open') = (closed_at IS NULL))
)
"""

EVENT = f"""
CREATE TABLE {SCHEMA}.opportunity_event (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    opportunity_id uuid NOT NULL,
    seq bigint GENERATED ALWAYS AS IDENTITY,
    kind text NOT NULL,
    actor_user_id uuid,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    fields jsonb,
    stage_from uuid,
    stage_to uuid,
    stage_from_name text,
    stage_to_name text,
    stage_cause text,
    owner_from uuid,
    owner_to uuid,
    outcome_from text,
    outcome_to text,
    CONSTRAINT opportunity_event_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT opportunity_event_seq_key UNIQUE (seq),
    CONSTRAINT opportunity_event_opportunity_fkey FOREIGN KEY (tenant_id, opportunity_id)
        REFERENCES {SCHEMA}.opportunity (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT opportunity_event_kind_check CHECK (kind IN ({_in(KINDS)})),
    CONSTRAINT opportunity_event_fields_check CHECK (
        (kind = 'updated') = (fields IS NOT NULL)
        AND (
            fields IS NULL OR (
                jsonb_typeof(fields) = 'array'
                AND jsonb_array_length(fields) BETWEEN 1 AND {len(UPDATED_FIELDS)}
                AND fields <@ '[{", ".join(f'"{name}"' for name in UPDATED_FIELDS)}]'::jsonb
            )
        )
    ),
    -- A stage change names the new stage, its name then and its cause; a
    -- deal's first stage is in its `created` entry's stage_to.
    CONSTRAINT opportunity_event_stage_check CHECK (
        (kind IN ('stage_changed', 'created')) = (stage_to IS NOT NULL)
        AND (stage_to IS NULL) = (stage_to_name IS NULL)
        AND (kind = 'stage_changed') = (stage_cause IS NOT NULL)
        AND (kind = 'stage_changed') = (stage_from IS NOT NULL)
        AND (stage_from IS NULL) = (stage_from_name IS NULL)
        AND (stage_cause IS NULL OR stage_cause IN ('moved', 'stage_removed'))
        AND (stage_from IS NULL OR stage_from IS DISTINCT FROM stage_to)
        AND (stage_to_name IS NULL OR char_length(stage_to_name) BETWEEN 1 AND {STAGE_NAME_MAX})
        AND (
            stage_from_name IS NULL
            OR char_length(stage_from_name) BETWEEN 1 AND {STAGE_NAME_MAX}
        )
    ),
    CONSTRAINT opportunity_event_owner_check CHECK (
        (kind = 'owner_changed' AND owner_from IS DISTINCT FROM owner_to)
        OR (kind <> 'owner_changed' AND owner_from IS NULL AND owner_to IS NULL)
    ),
    -- Outcomes move only between open and won, or open and lost (P4-B 5).
    CONSTRAINT opportunity_event_outcome_check CHECK (
        (kind = 'outcome_changed') = (outcome_to IS NOT NULL)
        AND (kind = 'outcome_changed') = (outcome_from IS NOT NULL)
        AND (
            outcome_to IS NULL
            OR (outcome_from = 'open' AND outcome_to IN ('won', 'lost'))
            OR (outcome_from IN ('won', 'lost') AND outcome_to = 'open')
        )
    )
)
"""

INDEXES = (
    # The default list order (latest change first).
    f"CREATE INDEX opportunity_updated_idx ON {SCHEMA}.opportunity"
    " (tenant_id, updated_at DESC, id DESC)",
    # The board's columns, and finding a removed stage's deals.
    f"CREATE INDEX opportunity_stage_idx ON {SCHEMA}.opportunity"
    " (tenant_id, pipeline_id, stage_id, outcome)",
    # The links' filters and the SET NULL from a deleted record.
    f"CREATE INDEX opportunity_contact_idx ON {SCHEMA}.opportunity (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
    f"CREATE INDEX opportunity_company_idx ON {SCHEMA}.opportunity (tenant_id, company_id)"
    " WHERE company_id IS NOT NULL",
    f"CREATE INDEX opportunity_owner_idx ON {SCHEMA}.opportunity (tenant_id, owner_user_id)"
    " WHERE owner_user_id IS NOT NULL",
    # A deal's history, newest first.
    f"CREATE INDEX opportunity_event_order_idx ON {SCHEMA}.opportunity_event"
    " (tenant_id, opportunity_id, seq DESC)",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(OPPORTUNITY)
    op.execute(EVENT)
    for statement in INDEXES:
        op.execute(statement)
    for table in ("opportunity", "opportunity_event"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.opportunity TO "{app_role}"')
    # Append-only for the application (P4-B 7): no UPDATE.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.opportunity_event TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.opportunity_event")
    op.execute(f"DROP TABLE {SCHEMA}.opportunity")
