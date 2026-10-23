"""Contact and company records: the service layer (`PHASE3-PLAN.md` §19.3-§19.6).

Every function takes a `Scope`: the workspace and the acting user, which
callers take from SaaS-OS's validated `RequestContext`, never from a path or
a body. Every query runs in `tenant_session_scope(workspace)` and also names
the workspace explicitly, so Row-Level Security and the predicate both
confine it. Every write takes `lock_open_tenant` first, so no row is written
while the workspace is being deleted or purged, and records its audit entry
with `record_in_transaction` in the same transaction: the record ID and the
names of the changed fields, never their values.

Values arrive already normalised (`crm_app.domains.records`). Duplicates
(decision P3-A 3) are refused twice: by a check before the write, and by
the partial unique index under concurrency, whose violation is mapped by
constraint name to the same `DuplicateRecord`.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.idempotency import run_idempotent
from saas_os.core.identity import get_membership
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    delete,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)
from saas_os.infra.db import update as update_rows

from crm_app.domains import paging
from crm_app.domains.membership import ACTIVE
from crm_app.models import Company, Contact


@dataclass(frozen=True)
class Kind:
    name: str
    model: type[Contact] | type[Company]
    fields: tuple[str, ...]
    unique_field: str
    unique_index: str
    duplicate_code: str

    @property
    def resource(self) -> str:
        return f"crm_app.{self.name}"


CONTACT = Kind(
    "contact",
    Contact,
    (
        "first_name",
        "last_name",
        "email",
        "phone",
        "job_title",
        "city",
        "lifecycle_stage",
        "source",
        "company_id",
        "owner_user_id",
    ),
    "email",
    "contact_active_email_key",
    "duplicate_email",
)
COMPANY = Kind(
    "company",
    Company,
    ("name", "domain", "website", "phone", "industry", "city", "country_code", "owner_user_id"),
    "domain",
    "company_active_domain_key",
    "duplicate_domain",
)
_SYSTEM_FIELDS = (
    "id",
    "created_at",
    "updated_at",
    "created_by_user_id",
    "updated_by_user_id",
    "version",
    "archived_at",
)


@dataclass(frozen=True)
class Scope:
    """Who acts, in which workspace: both from the validated request context."""

    workspace: uuid.UUID
    actor: uuid.UUID


class RecordError(Exception):
    status = 400
    code = "invalid"


class RecordNotFoundError(RecordError):
    status, code = 404, "not_found"


class DuplicateRecordError(RecordError):
    status = 409

    def __init__(self, code: str, existing_id: uuid.UUID | None) -> None:
        super().__init__(code)
        self.code = code
        self.existing_id = existing_id


class StaleVersionError(RecordError):
    status, code = 409, "stale_version"

    def __init__(self, current: int) -> None:
        super().__init__(self.code)
        self.current = current


class InvalidReferenceError(RecordError):
    status = 422

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EmailOrPhoneRequiredError(RecordError):
    status, code = 422, "email_or_phone_required"


class TransactionConflictError(RecordError):
    """PostgreSQL aborted the transaction to resolve a conflict with a
    concurrent one (deadlock or serialization failure); nothing was
    committed and repeating the request is safe."""

    status, code = 409, "conflict"


Record = dict[str, Any]
Row = Contact | Company


def _now() -> datetime:
    return datetime.now(UTC)


def _load(session: Session, kind: Kind, scope: Scope, record_id: uuid.UUID, *, lock: bool) -> Row:
    model = kind.model
    query = select(model).where(model.tenant_id == scope.workspace, model.id == record_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _active_with(
    session: Session, kind: Kind, scope: Scope, value: str, *, other_than: uuid.UUID | None
) -> uuid.UUID | None:
    model = kind.model
    query = select(model.id).where(
        model.tenant_id == scope.workspace,
        model.archived_at.is_(None),
        getattr(model, kind.unique_field) == value,
    )
    if other_than is not None:
        query = query.where(model.id != other_than)
    return session.execute(query.limit(1)).scalar_one_or_none()


def _refuse_duplicate(session: Session, kind: Kind, scope: Scope, row: Row) -> None:
    value = getattr(row, kind.unique_field)
    if value is None or row.archived_at is not None:
        return
    existing = _active_with(session, kind, scope, value, other_than=row.id)
    if existing is not None:
        raise DuplicateRecordError(kind.duplicate_code, existing)


_COMPANY_LINK = "contact_company_fkey"


def _duplicate_or(exc: IntegrityError, kind: Kind, scope: Scope, value: str | None) -> Exception:
    """A violation of the kind's unique index becomes the same
    `DuplicateRecordError` the pre-check raises. A contact whose company was
    deleted between the pre-check and the write breaks the company foreign
    key; that is the same `company_not_found` the pre-check gives. Anything
    else is unchanged."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if kind is CONTACT and constraint == _COMPANY_LINK:
        return InvalidReferenceError("company_not_found")
    if constraint != kind.unique_index or value is None:
        return exc
    with tenant_session_scope(scope.workspace) as session:
        existing = _active_with(session, kind, scope, value, other_than=None)
    return DuplicateRecordError(kind.duplicate_code, existing)


def _write[T](
    kind: Kind, scope: Scope, unique_value: Callable[[], str | None], fn: Callable[[Session], T]
) -> T:
    """Run `fn` in one locked, workspace-scoped transaction."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        raise _duplicate_or(exc, kind, scope, unique_value()) from None
    except OperationalError as exc:
        raise _conflict_or(exc) from None


def _conflict_or(exc: OperationalError) -> Exception:
    """Only a deadlock or serialization failure becomes the retryable 409;
    every other operational error is unchanged."""
    return TransactionConflictError() if is_transaction_conflict(exc) else exc


@dataclass(frozen=True)
class _Event:
    verb: str
    record_id: uuid.UUID
    metadata: Mapping[str, object] | None = None


def _audit(session: Session, kind: Kind, scope: Scope, event: _Event) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{kind.resource}.{event.verb}",
        resource_type=kind.resource,
        resource_id=str(event.record_id),
        metadata=dict(event.metadata or {}),
    )


def check_owner(scope: Scope, owner_user_id: uuid.UUID | None) -> None:
    """An owner must be an active member of the workspace (§19.6)."""
    if owner_user_id is None:
        return
    membership = get_membership(scope.workspace, owner_user_id)
    if membership is None or membership.status != ACTIVE:
        raise InvalidReferenceError("owner_not_member")


def _check_company(session: Session, scope: Scope, company_id: uuid.UUID | None) -> None:
    """A contact links only to an active company of its own workspace."""
    if company_id is None:
        return
    query = select(Company.id).where(
        Company.tenant_id == scope.workspace,
        Company.id == company_id,
        Company.archived_at.is_(None),
    )
    if session.execute(query).scalar_one_or_none() is None:
        raise InvalidReferenceError("company_not_found")


def _check_row(session: Session, scope: Scope, row: Row, changed: set[str]) -> None:
    if isinstance(row, Contact):
        if row.email is None and row.phone is None:
            raise EmailOrPhoneRequiredError
        if "company_id" in changed:
            _check_company(session, scope, row.company_id)


def _touch(row: Row, scope: Scope) -> None:
    row.version += 1
    row.updated_at = _now()
    row.updated_by_user_id = scope.actor


# --- Reads -----------------------------------------------------------------------


def _records(session: Session, scope: Scope, kind: Kind, rows: Sequence[Row]) -> list[Record]:
    """Rows as API records; a contact also carries a summary of its company,
    read for the whole page in one query."""
    records = [
        {name: getattr(row, name) for name in (*_SYSTEM_FIELDS, *kind.fields)} for row in rows
    ]
    if kind is CONTACT:
        linked = {row.company_id for row in rows if isinstance(row, Contact) and row.company_id}
        companies = {}
        if linked:
            companies = {
                company.id: {
                    "id": company.id,
                    "name": company.name,
                    "archived": company.archived_at is not None,
                }
                for company in session.execute(
                    select(Company.id, Company.name, Company.archived_at).where(
                        Company.tenant_id == scope.workspace, Company.id.in_(linked)
                    )
                )
            }
        for record in records:
            record["company"] = companies.get(record["company_id"])
    return records


def get(kind: Kind, scope: Scope, record_id: uuid.UUID) -> Record:
    with tenant_session_scope(scope.workspace) as session:
        row = _load(session, kind, scope, record_id, lock=False)
        return _records(session, scope, kind, [row])[0]


# --- Lists (PHASE3-PLAN.md §19.5) -----------------------------------------------------

ORDER_COLLATION = "und-x-icu"  # as in migration 0002's order indexes
TOTAL_CAP = 10_000


@dataclass(frozen=True)
class ListQuery:
    """A validated list request. Every value is already checked by the API."""

    order: str = "name"
    direction: str = "asc"
    limit: int = 50
    cursor: str | None = None
    q: str | None = None
    archived: str = "false"
    stages: tuple[str, ...] = ()
    owners: tuple[uuid.UUID, ...] = ()
    companies: tuple[uuid.UUID, ...] = ()

    def filters(self) -> dict[str, object]:
        return {
            "q": self.q,
            "archived": self.archived,
            "stages": sorted(self.stages),
            "owners": sorted(str(owner) for owner in self.owners),
            "companies": sorted(str(company) for company in self.companies),
        }


@dataclass(frozen=True)
class Page:
    items: list[Record]
    next_cursor: str | None
    total: int
    total_capped: bool


@dataclass(frozen=True)
class _OrderKey:
    expression: Any  # the column, collated where names are compared
    column: Any  # the plain column, for NULL tests
    attribute: str
    nullable: bool = False


def _order(kind: Kind, order: str) -> list[_OrderKey]:
    model = kind.model
    identity = _OrderKey(model.id, model.id, "id")
    if order != "name":
        column = getattr(model, order)
        return [_OrderKey(column, column, order), identity]
    if kind is CONTACT:
        return [
            _OrderKey(
                Contact.last_name.collate(ORDER_COLLATION), Contact.last_name, "last_name", True
            ),
            _OrderKey(
                Contact.first_name.collate(ORDER_COLLATION), Contact.first_name, "first_name"
            ),
            identity,
        ]
    return [_OrderKey(Company.name.collate(ORDER_COLLATION), Company.name, "name"), identity]


def _after(keys: Sequence[_OrderKey], values: Sequence[Any], *, ascending: bool) -> Any:
    """Rows strictly after `values` in the order `keys` define. PostgreSQL
    puts NULLs last ascending and first descending; a nullable key follows
    that rule, so the predicate matches `ORDER BY` exactly."""
    key, value = keys[0], values[0]
    if len(keys) == 1:
        return key.expression > value if ascending else key.expression < value
    rest = _after(keys[1:], values[1:], ascending=ascending)
    if value is None:
        tied = key.column.is_(None) & rest
        return tied if ascending else tied | key.column.is_not(None)
    beyond = key.expression > value if ascending else key.expression < value
    condition = beyond | ((key.expression == value) & rest)
    if key.nullable and ascending:
        condition = condition | key.column.is_(None)
    return condition


def _conditions(kind: Kind, scope: Scope, query: ListQuery) -> list[Any]:
    model = kind.model
    conditions: list[Any] = [model.tenant_id == scope.workspace]
    if query.archived == "false":
        conditions.append(model.archived_at.is_(None))
    elif query.archived == "true":
        conditions.append(model.archived_at.is_not(None))
    if query.owners:
        conditions.append(model.owner_user_id.in_(query.owners))
    if query.q:
        lowered = query.q.lower()
        if kind is CONTACT:
            conditions.append(
                Contact.first_name.istartswith(query.q, autoescape=True)
                | Contact.last_name.istartswith(query.q, autoescape=True)
                | Contact.email.startswith(lowered, autoescape=True)
            )
        else:
            conditions.append(
                Company.name.istartswith(query.q, autoescape=True)
                | Company.domain.startswith(lowered, autoescape=True)
            )
    if kind is CONTACT and query.stages:
        conditions.append(Contact.lifecycle_stage.in_(query.stages))
    if kind is CONTACT and query.companies:
        conditions.append(Contact.company_id.in_(query.companies))
    return conditions


def list_records(kind: Kind, scope: Scope, query: ListQuery) -> Page:
    """One page in a total, deterministic order (the row ID breaks ties).
    Raises `paging.InvalidCursor` for a cursor issued for another order,
    direction or filter set."""
    filters = paging.filter_hash(query.filters())
    after = (
        paging.decode(query.cursor, kind.name, query.order, query.direction, filters)
        if query.cursor
        else None
    )
    keys = _order(kind, query.order)
    ascending = query.direction == "asc"
    model = kind.model
    with tenant_session_scope(scope.workspace) as session:
        conditions = _conditions(kind, scope, query)
        counted = session.execute(select(model.id).where(*conditions).limit(TOTAL_CAP + 1)).all()
        statement = select(model).where(*conditions)
        if after is not None:
            statement = statement.where(_after(keys, after, ascending=ascending))
        statement = statement.order_by(
            *(key.expression.asc() if ascending else key.expression.desc() for key in keys)
        ).limit(query.limit + 1)
        rows = list(session.execute(statement).scalars())
        more = len(rows) > query.limit
        rows = rows[: query.limit]
        items = _records(session, scope, kind, rows)
        # Read the last key while the row is still attached to the session.
        last_key = tuple(getattr(rows[-1], key.attribute) for key in keys) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode(kind.name, query.order, query.direction, filters, last_key)
    return Page(
        items=items,
        next_cursor=next_cursor,
        total=min(len(counted), TOTAL_CAP),
        total_capped=len(counted) > TOTAL_CAP,
    )


# --- Writes ----------------------------------------------------------------------


def create(
    kind: Kind,
    scope: Scope,
    values: Mapping[str, Any],
    *,
    idempotency_key: str | None = None,
) -> tuple[Record, bool]:
    """Create a record; returns it and whether this was an idempotent replay.
    An idempotency key is scoped to the workspace, the kind and the acting
    member. The idempotency record stores the new ID only, never the
    content; a replay returns the record's current state."""
    check_owner(scope, values.get("owner_user_id"))
    record_id = uuid.uuid4()

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        now = _now()
        row = kind.model(
            id=record_id,
            tenant_id=scope.workspace,
            created_at=now,
            updated_at=now,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            version=1,
            archived_at=None,
            **values,
        )
        _check_row(session, scope, row, set(values))
        _refuse_duplicate(session, kind, scope, row)
        session.add(row)
        session.flush()
        given = sorted(name for name, value in values.items() if value is not None)
        _audit(session, kind, scope, _Event("created", record_id, {"fields": given}))
        return {"id": str(record_id)}

    def unique_value() -> str | None:
        return values.get(kind.unique_field)

    replay = False
    if idempotency_key is None:
        result = _write(kind, scope, unique_value, business)
    else:
        fingerprint = {k: None if v is None else str(v) for k, v in values.items()}
        try:
            # Keys are scoped to the acting member: another member's request
            # with the same key never replays this one.
            replay, result = run_idempotent(
                scope.workspace,
                f"{kind.resource}.create:{scope.actor}",
                idempotency_key,
                fingerprint,
                business,
            )
        except (TenantClosedError, TenantNotFoundError):
            raise RecordNotFoundError from None
        except IntegrityError as exc:
            raise _duplicate_or(exc, kind, scope, unique_value()) from None
        except OperationalError as exc:
            raise _conflict_or(exc) from None
    return get(kind, scope, uuid.UUID(str(result["id"]))), replay


def update(
    kind: Kind,
    scope: Scope,
    record_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    expected_version: int,
) -> Record:
    """Apply `changes` if the record is still at `expected_version`. A change
    that alters nothing is a no-op: no new version, no audit entry."""
    if "owner_user_id" in changes:
        check_owner(scope, changes["owner_user_id"])
    unique: dict[str, str | None] = {}

    def apply(session: Session) -> None:
        row = _load(session, kind, scope, record_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        changed = {name for name, value in changes.items() if getattr(row, name) != value}
        for name in changed:
            setattr(row, name, changes[name])
        unique["value"] = getattr(row, kind.unique_field)
        if not changed:
            return
        _check_row(session, scope, row, changed)
        if kind.unique_field in changed:
            _refuse_duplicate(session, kind, scope, row)
        _touch(row, scope)
        session.flush()
        _audit(session, kind, scope, _Event("updated", record_id, {"fields": sorted(changed)}))

    _write(kind, scope, lambda: unique.get("value"), apply)
    return get(kind, scope, record_id)


def set_archived(kind: Kind, scope: Scope, record_id: uuid.UUID, *, archived: bool) -> Record:
    """Archive or restore. Repeating either is a no-op. Restoring a record
    whose email or domain an active record now holds is a duplicate."""
    unique: dict[str, str | None] = {}

    def apply(session: Session) -> None:
        row = _load(session, kind, scope, record_id, lock=True)
        unique["value"] = getattr(row, kind.unique_field)
        if (row.archived_at is not None) == archived:
            return
        row.archived_at = _now() if archived else None
        if not archived:
            _refuse_duplicate(session, kind, scope, row)
        _touch(row, scope)
        session.flush()
        _audit(session, kind, scope, _Event("archived" if archived else "restored", record_id))

    _write(kind, scope, lambda: unique.get("value"), apply)
    return get(kind, scope, record_id)


def remove(kind: Kind, scope: Scope, record_id: uuid.UUID) -> None:
    """Permanent delete. Deleting a company first unlinks its contacts as an
    ordinary contact change: `company_id` cleared, a new version, the time
    and the actor, and an audit entry each. The contacts are kept.

    Lock order: the company row (`FOR UPDATE`), then the linked contact
    rows, by the same `UPDATE`. A concurrent contact update that links to
    this company either commits first (its foreign-key check holds the
    company row, so this waits, then sees and unlinks that contact) or
    finds the company gone (`company_not_found`). The foreign key's own
    `ON DELETE SET NULL (company_id)` stays as a backstop and finds nothing
    left to clear."""

    def apply(session: Session) -> None:
        _load(session, kind, scope, record_id, lock=True)
        metadata: dict[str, object] = {}
        if kind is COMPANY:
            unlinked = list(
                session.execute(
                    update_rows(Contact)
                    .where(Contact.tenant_id == scope.workspace, Contact.company_id == record_id)
                    .values(
                        company_id=None,
                        version=Contact.version + 1,
                        updated_at=_now(),
                        updated_by_user_id=scope.actor,
                    )
                    .returning(Contact.id)
                    .execution_options(synchronize_session=False)
                ).scalars()
            )
            for contact_id in unlinked:
                _audit(
                    session,
                    CONTACT,
                    scope,
                    _Event(
                        "updated",
                        contact_id,
                        {"fields": ["company_id"], "reason": "company_deleted"},
                    ),
                )
            metadata["unlinked_contacts"] = len(unlinked)
        model = kind.model
        session.execute(
            delete(model).where(model.tenant_id == scope.workspace, model.id == record_id)
        )
        _audit(session, kind, scope, _Event("deleted", record_id, metadata))

    _write(kind, scope, lambda: None, apply)
