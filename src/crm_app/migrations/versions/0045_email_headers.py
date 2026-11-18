"""Unsubscribe and threading headers for outgoing email (decision E-H1).

Revision ID: 0045_email_headers
Revises: 0044_business_profile
Create Date: 2026-11-18

`email_message` gains four optional columns, set when an email is queued
or sent and identical on every try (SaaS-OS v0.10.0 `EmailMessage`,
issue 224):

- `list_unsubscribe_url`: a campaign email's one-click unsubscribe address
  (`https:`), sent as `List-Unsubscribe` with `List-Unsubscribe-Post`
  (RFC 8058). It identifies the recipient, like the link in the body.
- `message_id`: the `Message-ID` an email was sent with, so a later reply
  in the same conversation can refer to it.
- `in_reply_to` and `thread_references`: a conversation reply's
  `In-Reply-To` and `References`, message ids separated by one space.

Every value is checked again by SaaS-OS before sending; the `CHECK`s bound
lengths. Downgrade drops the columns: for test and development databases
only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045_email_headers"
down_revision: str | Sequence[str] | None = "0044_business_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
TABLE = f"{SCHEMA}.email_message"
# Column, maximum length.
_COLUMNS = (
    ("list_unsubscribe_url", 2048),
    ("message_id", 998),
    ("in_reply_to", 998),
    ("thread_references", 8000),
)


def upgrade() -> None:
    for column, maximum in _COLUMNS:
        op.execute(
            f"ALTER TABLE {TABLE} ADD COLUMN {column} text,"
            f" ADD CONSTRAINT email_message_{column}_check CHECK ("
            f"{column} IS NULL OR char_length({column}) BETWEEN 1 AND {maximum})"
        )


def downgrade() -> None:
    for column, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {column}")
