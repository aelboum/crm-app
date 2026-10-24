"""Create the invitation intent table (Phase 2, decisions Q4, Q5, P2-F 1).

Revision ID: 0005_invitation_intent
Revises: 0004_workspace_settings
Create Date: 2026-10-24

SaaS-OS's invitation (`core.invitations`) carries no role and its token is
stored only as a hash. This table holds what the product adds
(`PHASE2-PLAN.md` §8.2): the role an Owner or Admin intends the invitee
to get, who invited, and how the link was delivered (`manual`: shown once
to the inviter, labelled not sent, decision Q4; `email`: accepted by the
email provider). The role is applied only when an Owner or Admin confirms
it after acceptance (Q5). No token, link or email address is stored here.

Tenant-owned: composite key `(tenant_id, invitation_id)`, `tenant_id`
references `core.tenants`; `invitation_id` names the SaaS-OS invitation
without a key into Core (product tables never reference Core's own tables
except `core.tenants`). Forced Row-Level Security and exactly SELECT,
INSERT, UPDATE, DELETE for the runtime role in this same migration; in
`crm_app.purge.PURGE_TABLES`.

Downgrade drops the table and its rows: for test and development databases
only, never a way to recover production data.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_rls_statements

revision: str = "0005_invitation_intent"
down_revision: str | Sequence[str] | None = "0004_workspace_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

ROLES = ("Owner", "Admin", "Member", "Read-only")
DELIVERIES = ("manual", "email")


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


INVITATION_INTENT = f"""
CREATE TABLE {SCHEMA}.invitation_intent (
    tenant_id uuid NOT NULL REFERENCES core.tenants (id),
    invitation_id uuid NOT NULL,
    role text NOT NULL,
    invited_by_user_id uuid NOT NULL,
    delivery text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, invitation_id),
    CONSTRAINT invitation_intent_role_check CHECK (role IN ({_in(ROLES)})),
    CONSTRAINT invitation_intent_delivery_check CHECK (delivery IN ({_in(DELIVERIES)}))
)
"""


def upgrade() -> None:
    op.execute(INVITATION_INTENT)
    for statement in tenant_rls_statements("invitation_intent", schema=SCHEMA):
        op.execute(statement)
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.invitation_intent TO "{_app_role()}"'
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.invitation_intent")
