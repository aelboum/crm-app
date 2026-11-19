"""Archived campaigns (decision P7-AR).

Revision ID: 0047_campaign_archive
Revises: 0046_campaign_queue
Create Date: 2026-11-19

`campaign` gains `archived_at` and `archived_by_user_id`. Archiving hides
a finished campaign (completed, partially completed, failed or cancelled)
from the campaign list; its recipients, emails, results and audit stay.
Both columns are set together or cleared together (unarchiving), and only
a finished campaign may be archived, so an archived campaign can never be
queued or sent.

Downgrade drops the columns: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047_campaign_archive"
down_revision: str | Sequence[str] | None = "0046_campaign_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
TABLE = f"{SCHEMA}.campaign"
FINAL = ("completed", "partially_completed", "failed", "cancelled")


def upgrade() -> None:
    finished = ", ".join(f"'{status}'" for status in FINAL)
    op.execute(
        f"ALTER TABLE {TABLE} ADD COLUMN archived_at timestamptz,"
        " ADD COLUMN archived_by_user_id uuid,"
        " ADD CONSTRAINT campaign_archived_pair_check CHECK ("
        "(archived_at IS NULL) = (archived_by_user_id IS NULL)),"
        " ADD CONSTRAINT campaign_archived_final_check CHECK ("
        f"archived_at IS NULL OR status IN ({finished}))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN archived_by_user_id, DROP COLUMN archived_at")
