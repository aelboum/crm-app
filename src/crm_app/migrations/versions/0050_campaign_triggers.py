"""Campaign triggers for automations (decision P8-C).

Revision ID: 0050_campaign_triggers
Revises: 0049_invitation_name
Create Date: 2026-11-20

`automation.trigger_type` also allows `campaign_sent` and
`campaign_unsubscribed`. `campaign_recipient_email_idx` finds the recipient
of a campaign email when it is sent, once per email. Downgrade deletes
automations with a campaign trigger (their runs and versions cascade): for
test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

from crm_app.migrations.all_rows import all_rows

revision: str = "0050_campaign_triggers"
down_revision: str | Sequence[str] | None = "0049_invitation_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_BEFORE = (
    "trigger_type IN ('contact_created', 'tag_added', 'form_submitted',"
    " 'appointment_booked', 'deal_stage_changed')"
)
_AFTER = (
    "trigger_type IN ('contact_created', 'tag_added', 'form_submitted',"
    " 'appointment_booked', 'deal_stage_changed', 'campaign_sent',"
    " 'campaign_unsubscribed')"
)


def _check(expression: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.automation DROP CONSTRAINT automation_trigger_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.automation ADD CONSTRAINT automation_trigger_check"
        f" CHECK ({expression})"
    )


def upgrade() -> None:
    _check(_AFTER)
    op.execute(
        f"CREATE INDEX campaign_recipient_email_idx ON {SCHEMA}.campaign_recipient"
        " (tenant_id, email_message_id) WHERE email_message_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX {SCHEMA}.campaign_recipient_email_idx")
    with all_rows(f"{SCHEMA}.automation"):
        op.execute(
            f"DELETE FROM {SCHEMA}.automation"
            " WHERE trigger_type IN ('campaign_sent', 'campaign_unsubscribed')"
        )
    _check(_BEFORE)
