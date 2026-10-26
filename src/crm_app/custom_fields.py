"""Custom field definitions (decision P3-D, `PHASE3-PLAN.md` §3.2).

Every role reads the definitions; creating, changing, archiving and
restoring them is workspace configuration, which the routes gate with
`crm_app.workspace:update` (Owner, Admin; P3-D 4). Record values live in
`crm_app.records`, validated against `active_definitions`.

A key and a type never change, and a key is unique per workspace and
entity for good (the `custom_field_definition_key_key` index decides; a
clash is `DuplicateKeyError`). At most `MAX_ACTIVE` fields per entity are
active, checked under SaaS-OS's tenant advisory lock so concurrent
creations or restores cannot pass it. Archiving hides a field; its values
stay on the records and show again when it is restored.

Every change runs in one locked, workspace-scoped transaction with its
audit entry (`crm_app.custom_field.created`, `.updated`, `.archived`,
`.restored`), which holds the entity, key and type, never record values.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains.custom_fields import MAX_ACTIVE
from crm_app.models import CustomFieldDefinition
from crm_app.records import (
    ConstraintViolationError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.custom_field"
_KEY_INDEX = "custom_field_definition_key_key"

Definition = dict[str, Any]


class CustomFieldNotFoundError(RecordError):
    status, code = 404, "custom_field_not_found"


class DuplicateKeyError(RecordError):
    status, code = 409, "duplicate_custom_field_key"


class CustomFieldLimitError(RecordError):
    status, code = 409, "custom_field_limit_reached"


class OptionsNotAllowedError(RecordError):
    """Options for a field that is not a select, or none for a select."""

    status, code = 422, "invalid_options"


def _now() -> datetime:
    return datetime.now(UTC)


def _out(row: CustomFieldDefinition) -> Definition:
    return {
        "id": row.id,
        "entity": row.entity,
        "key": row.key,
        "label": row.label,
        "field_type": row.field_type,
        "options": row.options,
        "position": row.position,
        "version": row.version,
        "archived": row.archived_at is not None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _audit(session: Session, scope: Scope, verb: str, row: CustomFieldDefinition) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"entity": row.entity, "key": row.key, "field_type": row.field_type},
    )


def _write[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    """Run `fn` in one locked, workspace-scoped transaction; a key clash a
    concurrent creation caused becomes `DuplicateKeyError`."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == _KEY_INDEX:
            raise DuplicateKeyError from None
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _load(
    session: Session, scope: Scope, definition_id: uuid.UUID, *, lock: bool = False
) -> CustomFieldDefinition:
    query = select(CustomFieldDefinition).where(
        CustomFieldDefinition.tenant_id == scope.workspace,
        CustomFieldDefinition.id == definition_id,
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise CustomFieldNotFoundError
    return row


def _active_count(session: Session, scope: Scope, entity: str) -> int:
    rows = session.execute(
        select(CustomFieldDefinition.id).where(
            CustomFieldDefinition.tenant_id == scope.workspace,
            CustomFieldDefinition.entity == entity,
            CustomFieldDefinition.archived_at.is_(None),
        )
    ).all()
    return len(rows)


def _check_options(field_type: str, options: list[str] | None) -> None:
    if (field_type == "select") != (options is not None):
        raise OptionsNotAllowedError


# --- Reads ------------------------------------------------------------------------


def _ordered(entity: str | None, scope: Scope) -> Any:
    query = select(CustomFieldDefinition).where(CustomFieldDefinition.tenant_id == scope.workspace)
    if entity is not None:
        query = query.where(CustomFieldDefinition.entity == entity)
    return query.order_by(
        CustomFieldDefinition.entity,
        CustomFieldDefinition.position,
        CustomFieldDefinition.created_at,
        CustomFieldDefinition.id,
    )


def list_definitions(scope: Scope, entity: str | None = None) -> list[Definition]:
    """The workspace's fields, archived ones included, by entity and position."""
    with tenant_session_scope(scope.workspace) as session:
        return [_out(row) for row in session.execute(_ordered(entity, scope)).scalars()]


def active_definitions(
    session: Session, scope: Scope, entity: str
) -> dict[str, CustomFieldDefinition]:
    """The entity's active fields by key, read in the caller's transaction."""
    rows = session.execute(
        _ordered(entity, scope).where(CustomFieldDefinition.archived_at.is_(None))
    ).scalars()
    return {row.key: row for row in rows}


# --- Changes ----------------------------------------------------------------------


def create_definition(  # noqa: PLR0913 - each keyword is one property of the field
    scope: Scope,
    *,
    entity: str,
    key: str,
    label: str,
    field_type: str,
    options: list[str] | None,
    position: int,
) -> Definition:
    """A new active field. Values are already normalised by the API."""
    _check_options(field_type, options)

    def apply(session: Session) -> Definition:
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.active")
        taken = session.execute(
            select(CustomFieldDefinition.id).where(
                CustomFieldDefinition.tenant_id == scope.workspace,
                CustomFieldDefinition.entity == entity,
                CustomFieldDefinition.key == key,
            )
        ).first()
        if taken is not None:
            raise DuplicateKeyError
        if _active_count(session, scope, entity) >= MAX_ACTIVE:
            raise CustomFieldLimitError
        now = _now()
        row = CustomFieldDefinition(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            entity=entity,
            key=key,
            label=label,
            field_type=field_type,
            options=options,
            position=position,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
            archived_at=None,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", row)
        return _out(row)

    return _write(scope, apply)


def update_definition(
    scope: Scope,
    definition_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    expected_version: int,
) -> Definition:
    """Change the label, the options of a select or the position, if the
    field is still at `expected_version`. A change that alters nothing is a
    no-op."""

    def apply(session: Session) -> Definition:
        row = _load(session, scope, definition_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if "options" in changes:
            _check_options(row.field_type, changes["options"])
        changed = {name for name, value in changes.items() if getattr(row, name) != value}
        if not changed:
            return _out(row)
        for name in changed:
            setattr(row, name, changes[name])
        row.version += 1
        row.updated_at = _now()
        row.updated_by_user_id = scope.actor
        session.flush()
        _audit(session, scope, "updated", row)
        return _out(row)

    return _write(scope, apply)


def set_definition_archived(
    scope: Scope, definition_id: uuid.UUID, *, archived: bool
) -> Definition:
    """Archive or restore; repeating either is a no-op. Restoring counts
    towards the active limit."""

    def apply(session: Session) -> Definition:
        if not archived:
            acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.active")
        row = _load(session, scope, definition_id, lock=True)
        if (row.archived_at is not None) == archived:
            return _out(row)
        if not archived and _active_count(session, scope, row.entity) >= MAX_ACTIVE:
            raise CustomFieldLimitError
        row.archived_at = _now() if archived else None
        row.version += 1
        row.updated_at = _now()
        row.updated_by_user_id = scope.actor
        session.flush()
        _audit(session, scope, "archived" if archived else "restored", row)
        return _out(row)

    return _write(scope, apply)
