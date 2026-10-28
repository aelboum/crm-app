"""Add business hours to the workspace settings (Phase 5 slice 5B, decision P5-B).

Revision ID: 0015_business_hours
Revises: 0014_appointments
Create Date: 2026-10-28

One nullable `jsonb` column on `workspace_settings`: SQL NULL while the
workspace has not set its hours (P5-B 3), otherwise seven items, Monday
first, each JSON `null` (closed) or `{"opens": "HH:MM", "closes": "HH:MM"}`
in the workspace's time zone (P5-B 2, 4). The `CHECK` keeps the outer
shape; `crm_app.domains.settings.business_hours` checks every day. The
table already has forced Row-Level Security, its grants and a place in
`crm_app.purge.PURGE_TABLES` (migration 0004), so nothing else changes.

Downgrade drops the column and the hours in it: for test and development
databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_business_hours"
down_revision: str | Sequence[str] | None = "0014_appointments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"

ADD_COLUMN = f"""
ALTER TABLE {SCHEMA}.workspace_settings
    ADD COLUMN business_hours jsonb,
    ADD CONSTRAINT workspace_settings_business_hours_check CHECK (
        business_hours IS NULL OR (
            jsonb_typeof(business_hours) = 'array'
            AND jsonb_array_length(business_hours) = 7
        )
    )
"""


def upgrade() -> None:
    op.execute(ADD_COLUMN)


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.workspace_settings DROP COLUMN business_hours")
