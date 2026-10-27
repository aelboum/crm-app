"""Tasks: the service layer (decision P4-C, slice 4C).

Every function takes a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it. Every
write takes `lock_open_tenant`, then the task's row lock, and records its
audit entry in the same transaction: the task ID and field names, never
the title (P4-C 6).

A task links only to a contact or company that is an active record of the
same workspace, or to a deal of the same workspace; its assignee must be an
active member (P4-C 2). "Overdue" is an open task due before now (P4-C 4).

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
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import paging
from crm_app.domains import tasks as rules
from crm_app.models import Company, Contact, Opportunity, Task
from crm_app.records import (
    TOTAL_CAP,
    ConstraintViolationError,
    InvalidReferenceError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    _after,
    _OrderKey,
    check_owner,
)

RESOURCE = "crm_app.task"
FIELDS = (
    "title",
    "priority",
    "due_at",
    "assignee_user_id",
    "contact_id",
    "company_id",
    "opportunity_id",
)
_CONSTRAINT_REFERENCES = {
    "task_contact_fkey": "contact_not_found",
    "task_company_fkey": "company_not_found",
    "task_opportunity_fkey": "opportunity_not_found",
}


class TaskNotFoundError(RecordError):
    status, code = 404, "task_not_found"


Item = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _refusal(exc: IntegrityError) -> Exception:
    """A link that vanished between the check and the write is the same
    refusal the check gives; anything else is `ConstraintViolationError`."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    code = _CONSTRAINT_REFERENCES.get(constraint or "")
    return InvalidReferenceError(code) if code else ConstraintViolationError()


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        raise _refusal(exc) from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _check_assignee(scope: Scope, user_id: uuid.UUID | None) -> None:
    try:
        check_owner(scope, user_id)
    except InvalidReferenceError:
        raise InvalidReferenceError("assignee_not_member") from None


def _check_links(session: Session, scope: Scope, values: Mapping[str, Any]) -> None:
    """Contacts and companies must be active records of the workspace; a
    deal must be the workspace's (any outcome)."""
    for name, model in (("contact_id", Contact), ("company_id", Company)):
        record_id = values.get(name)
        if record_id is None:
            continue
        found = session.execute(
            select(model.id).where(
                model.tenant_id == scope.workspace,
                model.id == record_id,
                model.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if found is None:
            raise InvalidReferenceError(f"{model.__tablename__}_not_found")
    deal_id = values.get("opportunity_id")
    if deal_id is not None:
        found = session.execute(
            select(Opportunity.id).where(
                Opportunity.tenant_id == scope.workspace, Opportunity.id == deal_id
            )
        ).scalar_one_or_none()
        if found is None:
            raise InvalidReferenceError("opportunity_not_found")


def _audit(session: Session, scope: Scope, verb: str, task_id: uuid.UUID, **metadata: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(task_id),
        metadata=metadata,
    )


def _load(session: Session, scope: Scope, task_id: uuid.UUID, *, lock: bool) -> Task:
    query = select(Task).where(Task.tenant_id == scope.workspace, Task.id == task_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise TaskNotFoundError
    return row


# --- Reads ---------------------------------------------------------------------------


def _names(
    session: Session, scope: Scope, rows: Sequence[Task]
) -> dict[str, dict[uuid.UUID, dict[str, Any]]]:
    """The linked records' names, read for a page at once."""
    found: dict[str, dict[uuid.UUID, dict[str, Any]]] = {
        "contact": {},
        "company": {},
        "opportunity": {},
    }
    contact_ids = {row.contact_id for row in rows if row.contact_id}
    if contact_ids:
        for record_id, first, last, archived in session.execute(
            select(Contact.id, Contact.first_name, Contact.last_name, Contact.archived_at).where(
                Contact.tenant_id == scope.workspace, Contact.id.in_(contact_ids)
            )
        ):
            name = " ".join(part for part in (first, last) if part)
            found["contact"][record_id] = {
                "id": record_id,
                "name": name,
                "archived": archived is not None,
            }
    company_ids = {row.company_id for row in rows if row.company_id}
    if company_ids:
        for record_id, name, archived in session.execute(
            select(Company.id, Company.name, Company.archived_at).where(
                Company.tenant_id == scope.workspace, Company.id.in_(company_ids)
            )
        ):
            found["company"][record_id] = {
                "id": record_id,
                "name": name,
                "archived": archived is not None,
            }
    deal_ids = {row.opportunity_id for row in rows if row.opportunity_id}
    if deal_ids:
        for record_id, title in session.execute(
            select(Opportunity.id, Opportunity.title).where(
                Opportunity.tenant_id == scope.workspace, Opportunity.id.in_(deal_ids)
            )
        ):
            found["opportunity"][record_id] = {"id": record_id, "name": title, "archived": False}
    return found


def _items(session: Session, scope: Scope, rows: Sequence[Task]) -> list[Item]:
    names = _names(session, scope, rows)
    return [
        {
            "id": row.id,
            "title": row.title,
            "priority": row.priority,
            "due_at": row.due_at,
            "assignee_user_id": row.assignee_user_id,
            "contact_id": row.contact_id,
            "contact": names["contact"].get(row.contact_id) if row.contact_id else None,
            "company_id": row.company_id,
            "company": names["company"].get(row.company_id) if row.company_id else None,
            "opportunity_id": row.opportunity_id,
            "opportunity": names["opportunity"].get(row.opportunity_id)
            if row.opportunity_id
            else None,
            "done": row.completed_at is not None,
            "completed_at": row.completed_at,
            "completed_by_user_id": row.completed_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "created_by_user_id": row.created_by_user_id,
            "updated_by_user_id": row.updated_by_user_id,
            "version": row.version,
        }
        for row in rows
    ]


def get(scope: Scope, task_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        return _items(session, scope, [_load(session, scope, task_id, lock=False)])[0]


@dataclass(frozen=True)
class ListQuery:
    """A validated list request; the API has checked every value."""

    order: str = "due_at"
    direction: str = "asc"
    limit: int = 50
    cursor: str | None = None
    status: str = "open"
    assignees: tuple[uuid.UUID, ...] = ()
    overdue: bool = False
    due_from: datetime | None = None
    due_to: datetime | None = None
    contacts: tuple[uuid.UUID, ...] = ()
    companies: tuple[uuid.UUID, ...] = ()
    opportunities: tuple[uuid.UUID, ...] = ()

    def filters(self) -> dict[str, object]:
        return {
            "status": self.status,
            "assignees": sorted(str(x) for x in self.assignees),
            "overdue": self.overdue,
            "due_from": self.due_from.isoformat() if self.due_from else None,
            "due_to": self.due_to.isoformat() if self.due_to else None,
            "contacts": sorted(str(x) for x in self.contacts),
            "companies": sorted(str(x) for x in self.companies),
            "opportunities": sorted(str(x) for x in self.opportunities),
        }


@dataclass(frozen=True)
class Page:
    items: list[Item]
    next_cursor: str | None
    total: int
    total_capped: bool


def _conditions(scope: Scope, query: ListQuery, now: datetime) -> list[Any]:
    conditions: list[Any] = [Task.tenant_id == scope.workspace]
    if query.status == "open":
        conditions.append(Task.completed_at.is_(None))
    elif query.status == "done":
        conditions.append(Task.completed_at.is_not(None))
    if query.assignees:
        conditions.append(Task.assignee_user_id.in_(query.assignees))
    if query.overdue:
        conditions.append(Task.completed_at.is_(None))
        conditions.append(Task.due_at < now)
    if query.due_from is not None:
        conditions.append(Task.due_at >= query.due_from)
    if query.due_to is not None:
        conditions.append(Task.due_at < query.due_to)
    if query.contacts:
        conditions.append(Task.contact_id.in_(query.contacts))
    if query.companies:
        conditions.append(Task.company_id.in_(query.companies))
    if query.opportunities:
        conditions.append(Task.opportunity_id.in_(query.opportunities))
    return conditions


def list_tasks(scope: Scope, query: ListQuery) -> Page:
    """One page in a total, deterministic order (the ID breaks ties); an
    unset due or completion time sorts last ascending. Raises
    `paging.InvalidCursor` for a cursor of another order or filter set."""
    filters = paging.filter_hash(query.filters())
    after = (
        paging.decode(query.cursor, "task", query.order, query.direction, filters)
        if query.cursor
        else None
    )
    column = getattr(Task, query.order)
    nullable = query.order in {"due_at", "completed_at"}
    keys = [_OrderKey(column, column, query.order, nullable), _OrderKey(Task.id, Task.id, "id")]
    ascending = query.direction == "asc"
    with tenant_session_scope(scope.workspace) as session:
        conditions = _conditions(scope, query, _now())
        counted = session.execute(select(Task.id).where(*conditions).limit(TOTAL_CAP + 1)).all()
        statement = select(Task).where(*conditions)
        if after is not None:
            statement = statement.where(_after(keys, after, ascending=ascending))
        statement = statement.order_by(
            *(key.expression.asc() if ascending else key.expression.desc() for key in keys)
        ).limit(query.limit + 1)
        rows = list(session.execute(statement).scalars())
        more = len(rows) > query.limit
        rows = rows[: query.limit]
        items = _items(session, scope, rows)
        last_key = tuple(getattr(rows[-1], key.attribute) for key in keys) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode("task", query.order, query.direction, filters, last_key)
    return Page(
        items=items,
        next_cursor=next_cursor,
        total=min(len(counted), TOTAL_CAP),
        total_capped=len(counted) > TOTAL_CAP,
    )


def counts(scope: Scope, assignees: tuple[uuid.UUID, ...]) -> dict[str, int]:
    """The four tabs' counts for the assignee filter (P4-C 5); each is at
    most `TOTAL_CAP`."""
    views = {
        "open": ListQuery(status="open", assignees=assignees),
        "mine": ListQuery(status="open", assignees=(scope.actor,)),
        "overdue": ListQuery(status="open", assignees=assignees, overdue=True),
        "done": ListQuery(status="done", assignees=assignees),
    }
    now = _now()
    with tenant_session_scope(scope.workspace) as session:
        return {
            name: len(
                session.execute(
                    select(Task.id).where(*_conditions(scope, query, now)).limit(TOTAL_CAP)
                ).all()
            )
            for name, query in views.items()
        }


# --- Writes ----------------------------------------------------------------------------


def create(
    scope: Scope, values: Mapping[str, Any], *, idempotency_key: str | None = None
) -> tuple[Item, bool]:
    """Create a task; returns it and whether this was an idempotent replay
    (the key is scoped to the workspace and the acting member)."""
    _check_assignee(scope, values.get("assignee_user_id"))
    task_id = uuid.uuid4()

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        _check_links(session, scope, values)
        now = _now()
        session.add(
            Task(
                id=task_id,
                tenant_id=scope.workspace,
                title=values["title"],
                priority=values.get("priority") or rules.DEFAULT_PRIORITY,
                due_at=values.get("due_at"),
                assignee_user_id=values.get("assignee_user_id"),
                contact_id=values.get("contact_id"),
                company_id=values.get("company_id"),
                opportunity_id=values.get("opportunity_id"),
                completed_at=None,
                completed_by_user_id=None,
                created_by_user_id=scope.actor,
                updated_by_user_id=scope.actor,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
        session.flush()
        given = sorted(name for name in FIELDS if values.get(name) is not None)
        _audit(session, scope, "created", task_id, fields=given)
        return {"id": str(task_id)}

    replay = False
    if idempotency_key is None:
        result = _transaction(scope, business)
    else:
        fingerprint = {
            name: None if values.get(name) is None else str(values[name]) for name in FIELDS
        }
        try:
            replay, result = run_idempotent(
                scope.workspace,
                f"{RESOURCE}.create:{scope.actor}",
                idempotency_key,
                fingerprint,
                business,
            )
        except (TenantClosedError, TenantNotFoundError):
            raise RecordNotFoundError from None
        except IntegrityError as exc:
            raise _refusal(exc) from None
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
    return get(scope, uuid.UUID(str(result["id"]))), replay


def update(
    scope: Scope, task_id: uuid.UUID, changes: Mapping[str, Any], *, expected_version: int
) -> Item:
    """Apply `changes` if the task is still at `expected_version`; `done`
    completes or reopens it. A change that alters nothing is a no-op."""
    if changes.get("assignee_user_id") is not None:
        _check_assignee(scope, changes["assignee_user_id"])

    def apply(session: Session) -> None:
        row = _load(session, scope, task_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        wanted = {name: value for name, value in changes.items() if name != "done"}
        changed = sorted(name for name, value in wanted.items() if getattr(row, name) != value)
        done = changes.get("done")
        toggled = done is not None and done != (row.completed_at is not None)
        if not changed and not toggled:
            return
        _check_links(session, scope, {name: wanted[name] for name in changed})
        now = _now()
        for name in changed:
            setattr(row, name, wanted[name])
        if toggled:
            row.completed_at = now if done else None
            row.completed_by_user_id = scope.actor if done else None
        row.version += 1
        row.updated_at = now
        row.updated_by_user_id = scope.actor
        session.flush()
        verb = ("completed" if done else "reopened") if toggled else "updated"
        _audit(session, scope, verb, row.id, fields=changed)

    _transaction(scope, apply)
    return get(scope, task_id)


def remove(scope: Scope, task_id: uuid.UUID) -> None:
    """Delete the task (Owner, Admin and Member, Q6)."""

    def apply(session: Session) -> None:
        row = _load(session, scope, task_id, lock=True)
        session.delete(row)
        session.flush()
        _audit(session, scope, "deleted", task_id)

    _transaction(scope, apply)
