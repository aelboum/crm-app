"""A name suggested when inviting (decision M-P2).

Revision ID: 0049_invitation_name
Revises: 0048_campaign_schedule
Create Date: 2026-11-19

- `invitation_intent.display_name`: the name the inviter gave for the
  person, under the same rules as a member's own display name (migration
  0035): 1 to 80 characters, trimmed, no control characters. Optional.
  The member list shows it for the member who joined with the invitation
  until they set their own name, which always wins.

Adds a column only; no data changes. Downgrade drops it: for test and
development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049_invitation_name"
down_revision: str | Sequence[str] | None = "0048_campaign_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.invitation_intent ADD COLUMN display_name text,"
        " ADD CONSTRAINT invitation_intent_display_name_check CHECK ("
        " display_name IS NULL OR ("
        " char_length(display_name) BETWEEN 1 AND 80"
        " AND display_name = btrim(display_name)"
        " AND display_name !~ '[[:cntrl:]]'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.invitation_intent DROP COLUMN display_name")
