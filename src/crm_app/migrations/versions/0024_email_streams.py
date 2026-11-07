"""Email streams: retry timing and provider rejections (decision P6-S).

Revision ID: 0024_email_streams
Revises: 0023_conversation_search
Create Date: 2026-11-01

- `email_message.next_attempt_at`: the earliest time another try may be
  made, set after a transient failure (exponential backoff with jitter, at
  least the provider's `Retry-After`) or a rate limit. Null means "now".
- `email_message.status` also allows `rejected`: the provider accepted the
  email and later reported that it did not send it (Resend's
  `email.failed` or `email.suppressed`). `failed` keeps its meaning: never
  accepted.
- `email_event.type` also allows `failed` and `suppressed`.

Additive; existing rows are unchanged. Downgrade turns `rejected` emails
back into `failed` ones and drops the column and the new event rows: for
test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0024_email_streams"
down_revision: str | Sequence[str] | None = "0023_conversation_search"
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
)
_AFTER = (*_BEFORE, "rejected")
_EVENTS_BEFORE = ("sent", "delivery_delayed", "delivered", "bounced", "complained")
_EVENTS_AFTER = (*_EVENTS_BEFORE, "failed", "suppressed")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _checks(statuses: Sequence[str], events: Sequence[str]) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.email_message DROP CONSTRAINT email_message_status_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_message ADD CONSTRAINT email_message_status_check"
        f" CHECK (status IN ({_in(statuses)}))"
    )
    op.execute(f"ALTER TABLE {SCHEMA}.email_event DROP CONSTRAINT email_event_type_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.email_event ADD CONSTRAINT email_event_type_check"
        f" CHECK (type IN ({_in(events)}))"
    )


def upgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.email_message ADD COLUMN next_attempt_at timestamptz")
    _checks(_AFTER, _EVENTS_AFTER)


def downgrade() -> None:
    with all_rows(f"{SCHEMA}.email_event", f"{SCHEMA}.email_message"):
        op.execute(f"DELETE FROM {SCHEMA}.email_event WHERE type IN ('failed', 'suppressed')")
        # A rejected email was accepted (it has sent_at); as `failed` it must not.
        op.execute(
            f"UPDATE {SCHEMA}.email_message SET status = 'failed', sent_at = NULL"
            " WHERE status = 'rejected'"
        )
    _checks(_BEFORE, _EVENTS_BEFORE)
    op.execute(f"ALTER TABLE {SCHEMA}.email_message DROP COLUMN next_attempt_at")
