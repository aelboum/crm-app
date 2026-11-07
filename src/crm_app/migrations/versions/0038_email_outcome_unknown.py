"""Emails whose send outcome is unknown are not retried blindly (decision E-R1).

Revision ID: 0038_email_outcome_unknown
Revises: 0037_member_notifications
Create Date: 2026-11-07

- `email_message.status` also allows `outcome_unknown`: the provider's
  transport failed after the message may have been handed over, and a
  retry could deliver it twice. Final, like `failed`, and like it with no
  `sent_at` (nothing says the provider accepted it).
- `email_message.first_attempt_at`: when the first try started. A provider
  that de-duplicates a repeated request does so for a window counted from
  the first request (Resend: 24 hours under one idempotency key), so a
  retry is only safe inside that window. Existing rows that were tried get
  their `created_at`, which is never later than the first try: the window
  can only come out shorter, never longer.
- `email_message.retry_safe_until`: set once a try ended with an unknown
  outcome that the provider de-duplicates. No later try starts at or after
  it, whatever failed in between; such an email becomes `outcome_unknown`.

Downgrade turns `outcome_unknown` into `failed` (code `outcome_unknown`) and
drops the columns: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0038_email_outcome_unknown"
down_revision: str | Sequence[str] | None = "0037_member_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"

_BEFORE = (
    "queued",
    "sending",
    "sent",
    "delivery_delayed",
    "delivered",
    "bounced",
    "complained",
    "failed",
    "suppressed",
    "rejected",
)
_AFTER = (*_BEFORE, "outcome_unknown")
_UNSENT_BEFORE = ("queued", "sending", "failed", "suppressed")
_UNSENT_AFTER = (*_UNSENT_BEFORE, "outcome_unknown")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _checks(statuses: Sequence[str], unsent: Sequence[str]) -> None:
    table = f"{SCHEMA}.email_message"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT email_message_status_check")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT email_message_status_check"
        f" CHECK (status IN ({_in(statuses)}))"
    )
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT email_message_sent_check")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT email_message_sent_check CHECK ("
        "(provider_message_id IS NULL OR provider IS NOT NULL)"
        f" AND (sent_at IS NULL) = (status IN ({_in(unsent)})))"
    )


def upgrade() -> None:
    table = f"{SCHEMA}.email_message"
    op.execute(f"ALTER TABLE {table} ADD COLUMN first_attempt_at timestamptz")
    with all_rows(table):
        op.execute(f"UPDATE {table} SET first_attempt_at = created_at WHERE attempts > 0")
    op.execute(f"ALTER TABLE {table} ADD COLUMN retry_safe_until timestamptz")
    _checks(_AFTER, _UNSENT_AFTER)


def downgrade() -> None:
    table = f"{SCHEMA}.email_message"
    with all_rows(table):
        op.execute(
            f"UPDATE {table} SET status = 'failed', last_error = 'outcome_unknown'"
            " WHERE status = 'outcome_unknown'"
        )
    _checks(_BEFORE, _UNSENT_BEFORE)
    op.execute(f"ALTER TABLE {table} DROP COLUMN retry_safe_until")
    op.execute(f"ALTER TABLE {table} DROP COLUMN first_attempt_at")
