"""Create the appointment table (Phase 5 slice 5A, decision P5-A).

Revision ID: 0014_appointments
Revises: 0013_forms
Create Date: 2026-10-28

One tenant-owned table with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements`, SELECT, INSERT, UPDATE, DELETE for
the runtime role, and a place in `crm_app.purge.PURGE_TABLES`:

- `appointment`: a meeting of one host (a member) with an optional contact,
  from `starts_at` to `ends_at` (at least 5 minutes, at most 24 hours). Its
  link to a contact is composite, `(tenant_id, contact_id) → (tenant_id,
  id)`, and `ON DELETE SET NULL (contact_id)`, so an appointment outlives
  the contact. Cancelling is a status: `cancelled_at` and
  `cancelled_by_user_id` are set together, exactly while the status is
  `cancelled` (P5-A 3). Conflicts between appointments are a service rule
  (P5-A 4), not a constraint: a member may book over a conflict on purpose.

Downgrade drops the table with its rows: for test and development databases
only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0014_appointments"
down_revision: str | Sequence[str] | None = "0013_forms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

TITLE_MAX = 200
LOCATION_MAX = 300
NOTE_MAX = 2000


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


APPOINTMENT = f"""
CREATE TABLE {SCHEMA}.appointment (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    title text NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    kind text NOT NULL DEFAULT 'in_person',
    location text,
    note text,
    status text NOT NULL DEFAULT 'confirmed',
    host_user_id uuid NOT NULL,
    contact_id uuid,
    cancelled_at timestamptz,
    cancelled_by_user_id uuid,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT appointment_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT appointment_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    -- Trimmed, 1-{TITLE_MAX} characters, no control characters.
    CONSTRAINT appointment_title_check CHECK (
        char_length(title) BETWEEN 1 AND {TITLE_MAX}
        AND title = btrim(title)
        AND title !~ '[\\x01-\\x1f\\x7f]'
    ),
    CONSTRAINT appointment_time_check CHECK (
        ends_at >= starts_at + interval '5 minutes'
        AND ends_at <= starts_at + interval '24 hours'
    ),
    CONSTRAINT appointment_kind_check CHECK (kind IN ('in_person', 'video', 'phone')),
    CONSTRAINT appointment_location_check CHECK (
        location IS NULL OR (
            char_length(location) BETWEEN 1 AND {LOCATION_MAX}
            AND location = btrim(location)
            AND location !~ '[\\x01-\\x1f\\x7f]'
        )
    ),
    CONSTRAINT appointment_note_check CHECK (
        note IS NULL OR (char_length(note) BETWEEN 1 AND {NOTE_MAX} AND note = btrim(note))
    ),
    CONSTRAINT appointment_status_check CHECK (
        status IN ('pending', 'confirmed', 'completed', 'no_show', 'cancelled')
    ),
    CONSTRAINT appointment_cancelled_check CHECK (
        (status = 'cancelled') = (cancelled_at IS NOT NULL)
        AND (cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)
    )
)
"""

INDEXES = (
    # The calendar's range query and the host's conflict check.
    f"CREATE INDEX appointment_range_idx ON {SCHEMA}.appointment (tenant_id, starts_at, id)",
    f"CREATE INDEX appointment_host_idx ON {SCHEMA}.appointment"
    " (tenant_id, host_user_id, starts_at) WHERE status <> 'cancelled'",
    # The contact drawer's list and the SET NULL from a deleted contact.
    f"CREATE INDEX appointment_contact_idx ON {SCHEMA}.appointment (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
)


def upgrade() -> None:
    app_role = _app_role()
    op.execute(APPOINTMENT)
    for statement in INDEXES:
        op.execute(statement)
    for statement in tenant_rls_statements("appointment", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.appointment TO "{app_role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.appointment")
