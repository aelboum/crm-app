"""Workspace settings: locale, time zone and default currency
(`PHASE2-PLAN.md` S10, decision P2-F 1).

A workspace without a row has the product defaults
(`crm_app.domains.settings`) at version 0; the first save inserts the row
at version 1. Every save needs the version it was made from, so two
administrators never silently overwrite each other; two first saves at
once meet the primary key, and the loser gets the same `stale_version`.

Reads run in `tenant_session_scope(workspace)` with an explicit workspace
predicate; a save takes `lock_open_tenant` first and records
`crm_app.workspace_settings.updated` with the names of the changed fields
in the same transaction. The values are configuration, not personal data.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import settings as values
from crm_app.models import WorkspaceSettings
from crm_app.records import (
    ConstraintViolationError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

FIELDS = ("locale", "time_zone", "currency")
RESOURCE = "crm_app.workspace_settings"
_PRIMARY_KEY = "workspace_settings_pkey"


def _defaults() -> dict[str, Any]:
    return {
        "locale": values.DEFAULT_LOCALE,
        "time_zone": values.DEFAULT_TIME_ZONE,
        "currency": values.DEFAULT_CURRENCY,
        "version": 0,
        "updated_at": None,
        "updated_by_user_id": None,
    }


def _out(row: WorkspaceSettings) -> dict[str, Any]:
    return {
        "locale": row.locale,
        "time_zone": row.time_zone,
        "currency": row.currency,
        "version": row.version,
        "updated_at": row.updated_at,
        "updated_by_user_id": row.updated_by_user_id,
    }


def get(scope: Scope) -> dict[str, Any]:
    with tenant_session_scope(scope.workspace) as session:
        row = session.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == scope.workspace)
        ).scalar_one_or_none()
        return _defaults() if row is None else _out(row)


def update(scope: Scope, changes: Mapping[str, str], *, expected_version: int) -> dict[str, Any]:
    """Apply `changes` (already normalised) if the settings are still at
    `expected_version`. Changing nothing is a no-op: no new version, no
    audit entry."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            row = session.execute(
                select(WorkspaceSettings)
                .where(WorkspaceSettings.tenant_id == scope.workspace)
                .with_for_update()
            ).scalar_one_or_none()
            current = _defaults() if row is None else _out(row)
            if current["version"] != expected_version:
                raise StaleVersionError(current["version"])
            changed = sorted(
                name for name in FIELDS if name in changes and changes[name] != current[name]
            )
            if not changed:
                return current
            now = datetime.now(UTC)
            if row is None:
                row = WorkspaceSettings(
                    tenant_id=scope.workspace,
                    **{name: changes.get(name, current[name]) for name in FIELDS},
                    version=1,
                    updated_at=now,
                    updated_by_user_id=scope.actor,
                )
                session.add(row)
            else:
                for name in changed:
                    setattr(row, name, changes[name])
                row.version += 1
                row.updated_at = now
                row.updated_by_user_id = scope.actor
            session.flush()
            record_in_transaction(
                session,
                caller=UserCaller(scope.actor),
                tenant_id=scope.workspace,
                action=f"{RESOURCE}.updated",
                resource_type=RESOURCE,
                resource_id=str(scope.workspace),
                metadata={"fields": changed},
            )
            return _out(row)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == _PRIMARY_KEY:
            # Two first saves at once: the other one created the row.
            raise StaleVersionError(1) from None
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise
