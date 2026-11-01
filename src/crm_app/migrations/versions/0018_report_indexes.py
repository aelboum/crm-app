"""Indexes for reports (Phase 10 slice 10A, decision P10-A).

Revision ID: 0018_report_indexes
Revises: 0017_suppression
Create Date: 2026-11-01

Reports count deals created or closed, and tasks created, in a period of
one workspace (`crm_app.reports`). Contacts, completed tasks and
appointments already have matching indexes. Additive only; no table, row
or grant changes. Downgrade drops the three indexes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_report_indexes"
down_revision: str | Sequence[str] | None = "0017_suppression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"

INDEXES = (
    ("opportunity_created_idx", f"{SCHEMA}.opportunity (tenant_id, created_at)", ""),
    (
        "opportunity_closed_idx",
        f"{SCHEMA}.opportunity (tenant_id, closed_at)",
        " WHERE closed_at IS NOT NULL",
    ),
    ("task_created_idx", f"{SCHEMA}.task (tenant_id, created_at)", ""),
)


def upgrade() -> None:
    for name, target, condition in INDEXES:
        op.execute(f"CREATE INDEX {name} ON {target}{condition}")


def downgrade() -> None:
    for name, _, _ in INDEXES:
        op.execute(f"DROP INDEX {SCHEMA}.{name}")
