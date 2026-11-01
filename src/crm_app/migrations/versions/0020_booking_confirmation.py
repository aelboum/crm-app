"""Booking confirmation emails (Phase 6 slice 6E.2, decision P6-E2).

Revision ID: 0020_booking_confirmation
Revises: 0019_email
Create Date: 2026-11-01

`booking_page.confirmation_email`: whether a booking on the page emails a
confirmation to the visitor. On by default; nothing is sent while the
installation's `EMAIL_SENDING_ENABLED` is off. Additive; existing pages get
the default. Downgrade drops the column.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_booking_confirmation"
down_revision: str | Sequence[str] | None = "0019_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.booking_page"
        " ADD COLUMN confirmation_email boolean NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.booking_page DROP COLUMN confirmation_email")
