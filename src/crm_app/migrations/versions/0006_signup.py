"""Create the self-service signup tables (decisions S-1, S-1.1, Stage C).

Revision ID: 0006_signup
Revises: 0005_invitation_intent
Create Date: 2026-10-25

`signup` records one person's request to create a workspace while it is
provisioned (`docs/project/SIGNUP-PLAN.md` §4, §4b). It exists before the
workspace does, so it is a *pre-tenant global* table: no `tenant_id` and
no tenant policy. It names the workspace it created as `workspace_id`,
without a foreign key, so it never blocks SaaS-OS's purge of that
workspace; the purge participant removes the rows (`crm_app.purge`).

Access model, option A (owner decision of 2026-10-25), forced RLS:

- SaaS-OS's tenant-context exclusion policy: no row is visible or writable
  in any transaction that carries a tenant (`app.tenant_id`);
- restrictive policies limiting every row to the person in
  `crm_app.signup_user_id`, a transaction-local setting written only by
  `crm_app.signups` from the server-side session. Reading may instead use
  `crm_app.signup_maintenance = 'on'`, set only by the maintenance
  command, which then acts on each row as that row's own person: the flag
  never allows a write.

The settings are compared as text, so a missing, empty or malformed value
matches nothing and never raises.

`signup_attempt` is the platform-wide attempt counter for the rolling
24-hour cap: one timestamp per counted attempt, nothing else. Global with
the exclusion policy only; the runtime role may insert, read and delete,
never update (append-only, like `activity`).

Exactly the privileges the guard requires are granted in this migration.
Downgrade drops both tables and their rows: for test and development
databases only.
"""

import os
import re
from collections.abc import Sequence

from alembic import op
from saas_os.infra.db import tenant_context_exclusion_statements

revision: str = "0006_signup"
down_revision: str | Sequence[str] | None = "0005_invitation_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"
_DEFAULT_APP_ROLE = "saas_os_app"

STATES = ("started", "provisioning", "complete", "failed", "expired")
OPEN_STATES = ("started", "provisioning")
STEPS = ("none", "creating", "workspace", "roles", "membership", "owner", "verified", "active")

# The same expressions are checked by the catalog guard (tests/catalog_rules.py).
OWNER_MATCH = "user_id::text = NULLIF(current_setting('crm_app.signup_user_id', true), '')"
MAINTENANCE = "NULLIF(current_setting('crm_app.signup_maintenance', true), '') = 'on'"


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("APP_DB_USER must be a plain SQL identifier.")
    return value


def _app_role() -> str:
    return _identifier(os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE))


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


SIGNUP = f"""
CREATE TABLE {SCHEMA}.signup (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    request_fingerprint text NOT NULL,
    state text NOT NULL DEFAULT 'started',
    step text NOT NULL DEFAULT 'none',
    workspace_name text,
    workspace_id uuid,
    step_started_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CONSTRAINT signup_state_check CHECK (state IN ({_in(STATES)})),
    CONSTRAINT signup_step_check CHECK (step IN ({_in(STEPS)})),
    CONSTRAINT signup_key_length CHECK (char_length(idempotency_key) BETWEEN 1 AND 255),
    CONSTRAINT signup_name_length
        CHECK (workspace_name IS NULL OR char_length(workspace_name) <= 100),
    CONSTRAINT signup_error_code_length
        CHECK (last_error_code IS NULL OR char_length(last_error_code) <= 64),
    CONSTRAINT signup_attempts_range CHECK (attempts >= 0),
    CONSTRAINT signup_complete_has_workspace
        CHECK (state <> 'complete' OR workspace_id IS NOT NULL),
    CONSTRAINT signup_user_key_unique UNIQUE (user_id, idempotency_key),
    CONSTRAINT signup_workspace_unique UNIQUE (workspace_id)
)
"""

# At most one unfinished signup per person.
OPEN_INDEX = (
    f"CREATE UNIQUE INDEX signup_one_open_per_user ON {SCHEMA}.signup (user_id)"
    f" WHERE state IN ({_in(OPEN_STATES)})"
)
DUE_INDEX = f"CREATE INDEX signup_state_updated ON {SCHEMA}.signup (state, updated_at)"

OWNER_POLICIES = (
    f"CREATE POLICY signup_owner_read ON {SCHEMA}.signup AS RESTRICTIVE FOR SELECT"
    f" USING ({OWNER_MATCH} OR {MAINTENANCE})",
    f"CREATE POLICY signup_owner_insert ON {SCHEMA}.signup AS RESTRICTIVE FOR INSERT"
    f" WITH CHECK ({OWNER_MATCH})",
    f"CREATE POLICY signup_owner_update ON {SCHEMA}.signup AS RESTRICTIVE FOR UPDATE"
    f" USING ({OWNER_MATCH}) WITH CHECK ({OWNER_MATCH})",
    f"CREATE POLICY signup_owner_delete ON {SCHEMA}.signup AS RESTRICTIVE FOR DELETE"
    f" USING ({OWNER_MATCH})",
)

SIGNUP_ATTEMPT = f"""
CREATE TABLE {SCHEMA}.signup_attempt (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attempted_at timestamptz NOT NULL DEFAULT now()
)
"""
ATTEMPT_INDEX = f"CREATE INDEX signup_attempt_at ON {SCHEMA}.signup_attempt (attempted_at)"


def upgrade() -> None:
    role = _app_role()
    op.execute(SIGNUP)
    op.execute(OPEN_INDEX)
    op.execute(DUE_INDEX)
    for statement in tenant_context_exclusion_statements("signup", schema=SCHEMA):
        op.execute(statement)
    for statement in OWNER_POLICIES:
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.signup TO "{role}"')

    op.execute(SIGNUP_ATTEMPT)
    op.execute(ATTEMPT_INDEX)
    for statement in tenant_context_exclusion_statements("signup_attempt", schema=SCHEMA):
        op.execute(statement)
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {SCHEMA}.signup_attempt TO "{role}"')


def downgrade() -> None:
    op.execute(f"DROP TABLE {SCHEMA}.signup_attempt")
    op.execute(f"DROP TABLE {SCHEMA}.signup")
