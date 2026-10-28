"""Create the booking_page and booking tables (Phase 5 slice 5C, decision
P5-C).

Revision ID: 0016_booking_pages
Revises: 0015_business_hours
Create Date: 2026-10-28

Two tenant-owned tables with forced Row-Level Security from
`saas_os.infra.db.tenant_rls_statements` and a place in
`crm_app.purge.PURGE_TABLES`:

- `booking_page`: a public page where visitors book one host's free time
  (P5-C 2). The public key is random and unique across all workspaces; the
  hosted page's address names both the workspace and the key.
- `booking`: how a visitor booked an appointment. It goes with its
  appointment (`ON DELETE CASCADE`, one booking each); its page and contact
  links are cleared, not cascaded, so deleting a page keeps the
  appointments it booked. The visitor's link token is stored only as its
  SHA-256, unique across all workspaces.

Two existing rules widen:

- `contact.source` also allows `booking` (P5-C 6).
- `appointment`: a visitor's cancellation sets `cancelled_at` without
  `cancelled_by_user_id` (P5-C 2); `cancelled_at` still exists exactly
  while the status is `cancelled`.

Every link is composite, `(tenant_id, x_id) → (tenant_id, id)`, so no row
can point into another workspace even with RLS bypassed.

Downgrade drops the tables with their rows, turns `booking` sources into
`other` and gives visitor cancellations the host as canceller, so the
narrower checks hold again: for test and development databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0016_booking_pages"
down_revision: str | Sequence[str] | None = "0015_business_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

NAME_MAX = 120
DESCRIPTION_MAX = 1000
LOCATION_MAX = 300
KEY_LENGTH = 22
LENGTHS = (15, 30, 45, 60, 90, 120)
STEPS = (15, 30, 60)
NOTICE_MAX = 7 * 24 * 60
HORIZON_MAX = 90

SOURCES_BEFORE = ("manual", "import", "form", "referral", "other")
SOURCES_AFTER = (*SOURCES_BEFORE, "booking")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[object]) -> str:
    return ", ".join(f"'{value}'" if isinstance(value, str) else str(value) for value in values)


def _text(column: str, maximum: int) -> str:
    """Trimmed, 1-`maximum` characters, no control characters."""
    return f"""char_length({column}) BETWEEN 1 AND {maximum}
        AND {column} = btrim({column})
        AND {column} !~ '[\\x01-\\x1f\\x7f]'"""


BOOKING_PAGE = f"""
CREATE TABLE {SCHEMA}.booking_page (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    name text NOT NULL,
    description text,
    status text NOT NULL DEFAULT 'draft',
    public_key text NOT NULL,
    host_user_id uuid NOT NULL,
    length_minutes integer NOT NULL DEFAULT 30,
    step_minutes integer NOT NULL DEFAULT 30,
    kind text NOT NULL DEFAULT 'video',
    location text,
    notice_minutes integer NOT NULL DEFAULT 240,
    horizon_days integer NOT NULL DEFAULT 30,
    booking_count integer NOT NULL DEFAULT 0 CHECK (booking_count >= 0),
    last_booked_at timestamptz,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT booking_page_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT booking_page_public_key_key UNIQUE (public_key),
    CONSTRAINT booking_page_name_check CHECK ({_text("name", NAME_MAX)}),
    -- Trimmed, 1-{DESCRIPTION_MAX} characters; line breaks allowed.
    CONSTRAINT booking_page_description_check CHECK (
        description IS NULL OR (
            char_length(description) BETWEEN 1 AND {DESCRIPTION_MAX}
            AND description = btrim(description)
            AND description !~ '[\\x01-\\x09\\x0b-\\x1f\\x7f]'
        )
    ),
    CONSTRAINT booking_page_status_check CHECK (status IN ('draft', 'published')),
    CONSTRAINT booking_page_public_key_check CHECK (
        public_key ~ '^[A-Za-z0-9_-]{{{KEY_LENGTH}}}$'
    ),
    CONSTRAINT booking_page_length_check CHECK (length_minutes IN ({_in(LENGTHS)})),
    CONSTRAINT booking_page_step_check CHECK (step_minutes IN ({_in(STEPS)})),
    CONSTRAINT booking_page_kind_check CHECK (kind IN ('in_person', 'video', 'phone')),
    CONSTRAINT booking_page_location_check CHECK (
        location IS NULL OR ({_text("location", LOCATION_MAX)})
    ),
    CONSTRAINT booking_page_notice_check CHECK (notice_minutes BETWEEN 0 AND {NOTICE_MAX}),
    CONSTRAINT booking_page_horizon_check CHECK (horizon_days BETWEEN 1 AND {HORIZON_MAX})
)
"""

BOOKING = f"""
CREATE TABLE {SCHEMA}.booking (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    booking_page_id uuid,
    appointment_id uuid NOT NULL,
    contact_id uuid,
    outcome text NOT NULL,
    token_hash text NOT NULL,
    cancelled_by_visitor_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_tenant_id_id_key UNIQUE (tenant_id, id),
    CONSTRAINT booking_appointment_key UNIQUE (tenant_id, appointment_id),
    CONSTRAINT booking_token_hash_key UNIQUE (token_hash),
    CONSTRAINT booking_page_fkey FOREIGN KEY (tenant_id, booking_page_id)
        REFERENCES {SCHEMA}.booking_page (tenant_id, id) ON DELETE SET NULL (booking_page_id),
    CONSTRAINT booking_appointment_fkey FOREIGN KEY (tenant_id, appointment_id)
        REFERENCES {SCHEMA}.appointment (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT booking_contact_fkey FOREIGN KEY (tenant_id, contact_id)
        REFERENCES {SCHEMA}.contact (tenant_id, id) ON DELETE SET NULL (contact_id),
    CONSTRAINT booking_outcome_check CHECK (outcome IN ('created', 'matched')),
    CONSTRAINT booking_token_hash_check CHECK (token_hash ~ '^[0-9a-f]{{64}}$')
)
"""

INDEXES = (
    f"CREATE INDEX booking_page_list_idx ON {SCHEMA}.booking_page"
    " (tenant_id, updated_at DESC, id DESC)",
    # A page's upcoming bookings per contact (P5-C 6) and the SET NULL from
    # a deleted page or contact.
    f"CREATE INDEX booking_page_contact_idx ON {SCHEMA}.booking"
    " (tenant_id, booking_page_id, contact_id) WHERE booking_page_id IS NOT NULL",
    f"CREATE INDEX booking_contact_idx ON {SCHEMA}.booking (tenant_id, contact_id)"
    " WHERE contact_id IS NOT NULL",
)

CANCELLED_BEFORE = """(status = 'cancelled') = (cancelled_at IS NOT NULL)
        AND (cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)"""
CANCELLED_AFTER = """(status = 'cancelled') = (cancelled_at IS NOT NULL)
        AND (cancelled_by_user_id IS NULL OR cancelled_at IS NOT NULL)"""


def _replace_check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {SCHEMA}.{table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    app_role = _app_role()
    for statement in (BOOKING_PAGE, BOOKING, *INDEXES):
        op.execute(statement)
    for table in ("booking_page", "booking"):
        for statement in tenant_rls_statements(table, schema=SCHEMA):
            op.execute(statement)
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO "{app_role}"')
    _replace_check("contact", "contact_source_check", f"source IN ({_in(SOURCES_AFTER)})")
    _replace_check("appointment", "appointment_cancelled_check", CANCELLED_AFTER)


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.booking")
    op.execute(f"DROP TABLE {SCHEMA}.booking_page")
    op.execute(f"UPDATE {SCHEMA}.contact SET source = 'other' WHERE source = 'booking'")
    op.execute(
        f"UPDATE {SCHEMA}.appointment SET cancelled_by_user_id = host_user_id"
        " WHERE cancelled_at IS NOT NULL AND cancelled_by_user_id IS NULL"
    )
    _replace_check("contact", "contact_source_check", f"source IN ({_in(SOURCES_BEFORE)})")
    _replace_check("appointment", "appointment_cancelled_check", CANCELLED_BEFORE)
