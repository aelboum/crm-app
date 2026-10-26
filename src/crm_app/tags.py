"""The workspace's tag vocabulary (decision P3-C, `PHASE3-PLAN.md` §3.2).

Every role reads the tags; creating, renaming and deleting them is
workspace configuration, which the routes gate with
`crm_app.workspace:update` (Owner, Admin; P3-C 4). Putting tags on records
is a record update and lives in `crm_app.records`.

A name is unique per workspace regardless of case; the database's
`tag_name_key` index (`lower(name)`) decides, and a clash becomes
`DuplicateTagError` with the existing tag's ID. A workspace holds at most
`MAX_TAGS` tags, checked under SaaS-OS's tenant advisory lock so concurrent
creations cannot pass it.

Every change runs in one locked, workspace-scoped transaction with its
audit entry (`crm_app.tag.created`, `.renamed`, `.deleted`), which names
the tag by ID only. Deleting a tag removes it from every record (P3-C 6):
those records keep their version and get no history entry, and the audit
entry counts the assignments removed.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
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
    delete,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.models import CompanyTag, ContactTag, Tag
from crm_app.records import (
    ORDER_COLLATION,
    ConstraintViolationError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.tag"
MAX_TAGS = 500
_NAME_KEY = "tag_name_key"


class TagNotFoundError(RecordError):
    status, code = 404, "tag_not_found"


class DuplicateTagError(RecordError):
    status, code = 409, "duplicate_tag"

    def __init__(self, existing_id: uuid.UUID | None) -> None:
        super().__init__(self.code)
        self.existing_id = existing_id


class TagLimitError(RecordError):
    status, code = 409, "tag_limit_reached"


Tagged = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _out(tag: Tag) -> Tagged:
    return {
        "id": tag.id,
        "name": tag.name,
        "version": tag.version,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
    }


def _names(session: Session, scope: Scope) -> list[tuple[uuid.UUID, str]]:
    rows = session.execute(select(Tag.id, Tag.name).where(Tag.tenant_id == scope.workspace))
    return [(tag_id, name) for tag_id, name in rows]


def _holder(names: list[tuple[uuid.UUID, str]], name: str) -> uuid.UUID | None:
    """The tag holding `name` in any case, if one does (the index compares
    `lower(name)`)."""
    lowered = name.lower()
    return next((tag_id for tag_id, other in names if other.lower() == lowered), None)


def _audit(session: Session, scope: Scope, verb: str, tag_id: uuid.UUID, **metadata: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(tag_id),
        metadata=metadata,
    )


def _write[T](scope: Scope, name: str | None, fn: Callable[[Session], T]) -> T:
    """Run `fn` in one locked, workspace-scoped transaction. A name clash
    the pre-check missed (a concurrent change) becomes the same
    `DuplicateTagError`; no other database refusal surfaces as the driver
    error."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint != _NAME_KEY or name is None:
            raise ConstraintViolationError from None
        with tenant_session_scope(scope.workspace) as session:
            existing = _holder(_names(session, scope), name)
        raise DuplicateTagError(existing) from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _load(session: Session, scope: Scope, tag_id: uuid.UUID, *, lock: bool = False) -> Tag:
    query = select(Tag).where(Tag.tenant_id == scope.workspace, Tag.id == tag_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise TagNotFoundError
    return row


# --- Reads ------------------------------------------------------------------------


def list_tags(scope: Scope) -> list[Tagged]:
    """Every tag of the workspace, by name (at most `MAX_TAGS`)."""
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(Tag)
            .where(Tag.tenant_id == scope.workspace)
            .order_by(Tag.name.collate(ORDER_COLLATION), Tag.id)
        ).scalars()
        return [_out(tag) for tag in rows]


# --- Changes ----------------------------------------------------------------------


def create_tag(scope: Scope, name: str) -> Tagged:
    """A new tag named `name` (already normalised)."""

    def apply(session: Session) -> Tagged:
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        names = _names(session, scope)
        clash = _holder(names, name)
        if clash is not None:
            raise DuplicateTagError(clash)
        if len(names) >= MAX_TAGS:
            raise TagLimitError
        now = _now()
        tag = Tag(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            name=name,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(tag)
        session.flush()
        _audit(session, scope, "created", tag.id)
        return _out(tag)

    return _write(scope, name, apply)


def rename_tag(scope: Scope, tag_id: uuid.UUID, name: str, *, expected_version: int) -> Tagged:
    """Rename if the tag is still at `expected_version`. The same name is a
    no-op: no new version, no audit entry. A change of case alone is a
    rename."""

    def apply(session: Session) -> Tagged:
        tag = _load(session, scope, tag_id, lock=True)
        if tag.version != expected_version:
            raise StaleVersionError(tag.version)
        if tag.name == name:
            return _out(tag)
        clash = _holder([(i, n) for i, n in _names(session, scope) if i != tag.id], name)
        if clash is not None:
            raise DuplicateTagError(clash)
        tag.name = name
        tag.version += 1
        tag.updated_at = _now()
        tag.updated_by_user_id = scope.actor
        session.flush()
        _audit(session, scope, "renamed", tag.id)
        return _out(tag)

    return _write(scope, name, apply)


def delete_tag(scope: Scope, tag_id: uuid.UUID) -> None:
    """Delete the tag and remove it from every record (P3-C 6)."""

    def apply(session: Session) -> None:
        _load(session, scope, tag_id, lock=True)
        removed: dict[str, int] = {}
        for label, model in (("contacts", ContactTag), ("companies", CompanyTag)):
            removed[label] = len(
                session.execute(
                    delete(model)
                    .where(model.tenant_id == scope.workspace, model.tag_id == tag_id)
                    .returning(model.tag_id)
                    .execution_options(synchronize_session=False)
                ).all()
            )
        session.execute(delete(Tag).where(Tag.tenant_id == scope.workspace, Tag.id == tag_id))
        _audit(
            session,
            scope,
            "deleted",
            tag_id,
            removed_from_contacts=removed["contacts"],
            removed_from_companies=removed["companies"],
        )

    _write(scope, None, apply)
