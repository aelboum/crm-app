"""The source of a history entry no member made (decision K3.8).

Revision ID: 0036_activity_source
Revises: 0035_member_profiles
Create Date: 2026-11-06

Adds two nullable columns to `crm_app.activity`:

- `source`: what made the entry when no member did, one of `booking_page`,
  `public_form`, `consent_link` or `automation`;
- `source_id`: that page's, form's or automation's id. It is a reference,
  not a foreign key: the history outlives a deleted page, form or
  automation, which then shows without a name.

Checks: an entry with a source names no member (`actor_user_id` is NULL),
and `source_id` needs a `source`. Existing rows are unchanged (both columns
NULL), so they keep the member they named.

Additive: no row is rewritten. The table grants (SELECT, INSERT, DELETE) are
table-wide, so they cover the new columns. Downgrade drops the columns: for
test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036_activity_source"
down_revision: str | Sequence[str] | None = "0035_member_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
SOURCES = ("booking_page", "public_form", "consent_link", "automation")


def upgrade() -> None:
    allowed = ", ".join(f"'{source}'" for source in SOURCES)
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.activity
            ADD COLUMN source text,
            ADD COLUMN source_id uuid,
            ADD CONSTRAINT activity_source_check CHECK (source IS NULL OR source IN ({allowed})),
            ADD CONSTRAINT activity_source_actor_check CHECK (
                source IS NULL OR actor_user_id IS NULL
            ),
            ADD CONSTRAINT activity_source_id_check CHECK (source_id IS NULL OR source IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.activity
            DROP CONSTRAINT activity_source_id_check,
            DROP CONSTRAINT activity_source_actor_check,
            DROP CONSTRAINT activity_source_check,
            DROP COLUMN source_id,
            DROP COLUMN source
        """
    )
