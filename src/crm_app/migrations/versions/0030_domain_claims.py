"""Unverified sending-domain claims expire; domain events apply in order
(security review 13-H3 of the email and domain surface).

Revision ID: 0030_domain_claims
Revises: 0029_sending_domains
Create Date: 2026-11-01

- `sending_domain.verified_at`: when the provider first reported the domain
  verified; a domain that never was cannot hold its name for ever.
- `sending_domain.event_at`: the time of the newest provider event applied,
  so an older event delivered late never overwrites a newer state.
- `sending_domain.status` also allows `expired`: a claim that was not
  verified within its time, whose name is free again.
- `sending_domain_index.claimed_at`: when the name was claimed; existing
  rows count from this migration.

Downgrade removes the columns and turns `expired` rows back into
`not_registered`: for test and development databases only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_domain_claims"
down_revision: str | Sequence[str] | None = "0029_sending_domains"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_BEFORE = (
    "'not_registered', 'not_started', 'pending', 'verified', 'failed',"
    " 'temporary_failure', 'unknown'"
)
_AFTER = _BEFORE + ", 'expired'"


def _status_check(values: str) -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.sending_domain DROP CONSTRAINT sending_domain_status_check")
    op.execute(
        f"ALTER TABLE {SCHEMA}.sending_domain ADD CONSTRAINT sending_domain_status_check"
        f" CHECK (status IN ({values}))"
    )


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.sending_domain"
        " ADD COLUMN verified_at timestamptz,"
        " ADD COLUMN event_at timestamptz"
    )
    op.execute(
        f"UPDATE {SCHEMA}.sending_domain SET verified_at = updated_at WHERE status = 'verified'"
    )
    _status_check(_AFTER)
    op.execute(
        f"ALTER TABLE {SCHEMA}.sending_domain_index"
        " ADD COLUMN claimed_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        f"CREATE INDEX sending_domain_index_claimed_idx ON {SCHEMA}.sending_domain_index"
        " (claimed_at)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX {SCHEMA}.sending_domain_index_claimed_idx")
    op.execute(f"ALTER TABLE {SCHEMA}.sending_domain_index DROP COLUMN claimed_at")
    op.execute(
        f"UPDATE {SCHEMA}.sending_domain SET status = 'not_registered' WHERE status = 'expired'"
    )
    _status_check(_BEFORE)
    op.execute(f"ALTER TABLE {SCHEMA}.sending_domain DROP COLUMN event_at, DROP COLUMN verified_at")
