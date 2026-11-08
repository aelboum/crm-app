"""The workspace's business contact details (decision P2-BP).

Revision ID: 0044_business_profile
Revises: 0043_business_hours_wait
Create Date: 2026-11-08

- `workspace_settings` gains `business_phone`, `business_email`,
  `business_website` and `business_address` (each optional, `NULL` while
  not set) and `business_contact_public` (default false): whether booking
  pages show them to visitors. `crm_app.domains.settings` validates every
  value; the `CHECK`s bound their length and refuse empty strings.

Downgrade drops the columns: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0044_business_profile"
down_revision: str | Sequence[str] | None = "0043_business_hours_wait"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
TABLE = f"{SCHEMA}.workspace_settings"
# Column, maximum length (the same as the API's rules).
_TEXT = (
    ("business_phone", 32),
    ("business_email", 320),
    ("business_website", 2048),
    ("business_address", 300),
)


def upgrade() -> None:
    for column, maximum in _TEXT:
        op.execute(
            f"ALTER TABLE {TABLE} ADD COLUMN {column} text,"
            f" ADD CONSTRAINT workspace_settings_{column}_check CHECK ("
            f"{column} IS NULL OR char_length({column}) BETWEEN 1 AND {maximum})"
        )
    op.execute(
        f"ALTER TABLE {TABLE} ADD COLUMN business_contact_public boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN business_contact_public")
    for column, _ in reversed(_TEXT):
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {column}")
