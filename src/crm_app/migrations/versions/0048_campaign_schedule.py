"""Scheduled campaigns (decision P7-SC).

Revision ID: 0048_campaign_schedule
Revises: 0047_campaign_archive
Create Date: 2026-11-19

- `campaign.scheduled_at` and `campaign.scheduled_by_user_id`: when an
  approved campaign is to be queued, and by whom. Both set or both empty,
  and only an `approved` campaign may carry them: editing, cancelling or
  queuing it clears them.
- `campaign_queue.due_at`: when the maintenance run may start the
  campaign; empty for a campaign queued at once.

Adds columns only; no data changes. Downgrade drops them: for test and
development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048_campaign_schedule"
down_revision: str | Sequence[str] | None = "0047_campaign_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.campaign ADD COLUMN scheduled_at timestamptz,"
        " ADD COLUMN scheduled_by_user_id uuid,"
        " ADD CONSTRAINT campaign_scheduled_pair_check"
        " CHECK ((scheduled_at IS NULL) = (scheduled_by_user_id IS NULL)),"
        " ADD CONSTRAINT campaign_scheduled_approved_check"
        " CHECK (scheduled_at IS NULL OR status = 'approved')"
    )
    op.execute(f"ALTER TABLE {SCHEMA}.campaign_queue ADD COLUMN due_at timestamptz")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.campaign_queue DROP COLUMN due_at")
    op.execute(
        f"ALTER TABLE {SCHEMA}.campaign DROP COLUMN scheduled_by_user_id, DROP COLUMN scheduled_at"
    )
