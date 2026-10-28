"""Appointments: the service layer (decision P5-A, slice 5A).

Every function takes a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it. Every
write takes `lock_open_tenant`, then the appointment's row lock, and records
its audit entries in the same transaction: the appointment ID, field names
and statuses, never the title, location or note (P5-A 8).

An appointment's host must be an active member and its contact an active
contact of the same workspace. Booking it, or moving it to another time or
host, is refused while it conflicts with another appointment of the host
unless the caller allows the conflict (P5-A 4); a per-host advisory lock
serialises the check and the write. A cancelled appointment never changes
again (P5-A 3).

The workspace's business hours (decision P5-B) give the open intervals
the calendar shades around and the "outside business hours" warning of
the live check; booking outside them is allowed (P5-B 7).

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
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import appointments as rules
from crm_app.domains import settings as setting_values
from crm_app.domains.records import InvalidValue
from crm_app.models import Appointment, Contact, WorkspaceSettings
from crm_app.records import (
    ConstraintViolationError,
    InvalidReferenceError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    check_owner,
)

RESOURCE = "crm_app.appointment"
FIELDS = (
    "title",
    "starts_at",
    "ends_at",
    "kind",
    "location",
    "note",
    "host_user_id",
    "contact_id",
)
# Changes that move an appointment, and so need a new conflict check.
_MOVES = frozenset({"starts_at", "ends_at", "host_user_id"})
CONFLICTS_SHOWN = 10
UPCOMING_MAX = 50


class AppointmentNotFoundError(RecordError):
    status, code = 404, "appointment_not_found"


class AppointmentCancelledError(RecordError):
    """A cancelled appointment cannot be changed or reopened (P5-A 3)."""

    status, code = 409, "appointment_cancelled"


class InvalidTimesError(RecordError):
    status, code = 422, "invalid_times"


class AppointmentConflictError(RecordError):
    """The host has other appointments at that time (P5-A 4)."""

    status, code = 409, "appointment_conflict"

    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        super().__init__(self.code)
        self.conflicts = conflicts


Item = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _refusal(exc: IntegrityError) -> Exception:
    """A contact that vanished between the check and the write is the same
    refusal the check gives; anything else is `ConstraintViolationError`."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint == "appointment_contact_fkey":
        return InvalidReferenceError("contact_not_found")
    return ConstraintViolationError()


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


def _check_host(scope: Scope, user_id: uuid.UUID) -> None:
    try:
        check_owner(scope, user_id)
    except InvalidReferenceError:
        raise InvalidReferenceError("host_not_member") from None


def _check_times(starts_at: datetime, ends_at: datetime) -> None:
    try:
        rules.times(starts_at, ends_at)
    except InvalidValue:
        raise InvalidTimesError from None


def _check_contact(session: Session, scope: Scope, contact_id: uuid.UUID | None) -> None:
    if contact_id is None:
        return
    found = session.execute(
        select(Contact.id).where(
            Contact.tenant_id == scope.workspace,
            Contact.id == contact_id,
            Contact.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if found is None:
        raise InvalidReferenceError("contact_not_found")


def _audit(
    session: Session, scope: Scope, verb: str, appointment_id: uuid.UUID, **metadata: Any
) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(appointment_id),
        metadata=metadata,
    )


def _load(session: Session, scope: Scope, appointment_id: uuid.UUID, *, lock: bool) -> Appointment:
    query = select(Appointment).where(
        Appointment.tenant_id == scope.workspace, Appointment.id == appointment_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise AppointmentNotFoundError
    return row


def _conflicting(
    session: Session,
    scope: Scope,
    host: uuid.UUID,
    window: tuple[datetime, datetime],
    *,
    exclude: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """The host's other appointments, not cancelled, overlapping
    `window`, `[starts_at, ends_at)`, earliest first."""
    starts_at, ends_at = window
    conditions: list[Any] = [
        Appointment.tenant_id == scope.workspace,
        Appointment.host_user_id == host,
        Appointment.status != "cancelled",
        Appointment.starts_at < ends_at,
        Appointment.ends_at > starts_at,
        # Bounds the index scan: nothing lasts longer than a day.
        Appointment.starts_at > starts_at - rules.LONGEST,
    ]
    if exclude is not None:
        conditions.append(Appointment.id != exclude)
    rows = session.execute(
        select(Appointment.id, Appointment.title, Appointment.starts_at, Appointment.ends_at)
        .where(*conditions)
        .order_by(Appointment.starts_at, Appointment.id)
        .limit(CONFLICTS_SHOWN)
    ).all()
    return [
        {"id": row.id, "title": row.title, "starts_at": row.starts_at, "ends_at": row.ends_at}
        for row in rows
    ]


def _reserve(
    session: Session,
    scope: Scope,
    host: uuid.UUID,
    window: tuple[datetime, datetime],
    exclude: uuid.UUID | None,
) -> None:
    """Take the host's lock, then refuse a conflict (P5-A 4): the lock is
    held to the end of the transaction, so a concurrent booking for the
    same host waits and then sees this one."""
    acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.host:{host}")
    found = _conflicting(session, scope, host, window, exclude=exclude)
    if found:
        raise AppointmentConflictError(found)


# --- Reads ---------------------------------------------------------------------------


def _contacts(
    session: Session, scope: Scope, rows: Sequence[Appointment]
) -> dict[uuid.UUID, dict[str, Any]]:
    ids = {row.contact_id for row in rows if row.contact_id}
    if not ids:
        return {}
    found: dict[uuid.UUID, dict[str, Any]] = {}
    for record_id, first, last, archived in session.execute(
        select(Contact.id, Contact.first_name, Contact.last_name, Contact.archived_at).where(
            Contact.tenant_id == scope.workspace, Contact.id.in_(ids)
        )
    ):
        name = " ".join(part for part in (first, last) if part)
        found[record_id] = {"id": record_id, "name": name, "archived": archived is not None}
    return found


def _items(session: Session, scope: Scope, rows: Sequence[Appointment]) -> list[Item]:
    contacts = _contacts(session, scope, rows)
    return [
        {
            "id": row.id,
            "title": row.title,
            "starts_at": row.starts_at,
            "ends_at": row.ends_at,
            "kind": row.kind,
            "location": row.location,
            "note": row.note,
            "status": row.status,
            "host_user_id": row.host_user_id,
            "contact_id": row.contact_id,
            "contact": contacts.get(row.contact_id) if row.contact_id else None,
            "cancelled_at": row.cancelled_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "created_by_user_id": row.created_by_user_id,
            "updated_by_user_id": row.updated_by_user_id,
            "version": row.version,
        }
        for row in rows
    ]


def get(scope: Scope, appointment_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        return _items(session, scope, [_load(session, scope, appointment_id, lock=False)])[0]


@dataclass(frozen=True)
class RangeQuery:
    """A validated range request; the API has checked every value."""

    starts: datetime
    ends: datetime
    hosts: tuple[uuid.UUID, ...] = ()
    contacts: tuple[uuid.UUID, ...] = ()
    include_cancelled: bool = False


@dataclass(frozen=True)
class Range:
    items: list[Item]
    truncated: bool


def in_range(scope: Scope, query: RangeQuery) -> Range:
    """Every appointment overlapping `[starts, ends)`, earliest first, at
    most `RANGE_ITEMS_MAX` (P5-A 5)."""
    conditions: list[Any] = [
        Appointment.tenant_id == scope.workspace,
        Appointment.starts_at < query.ends,
        Appointment.ends_at > query.starts,
        Appointment.starts_at > query.starts - rules.LONGEST,
    ]
    if not query.include_cancelled:
        conditions.append(Appointment.status != "cancelled")
    if query.hosts:
        conditions.append(Appointment.host_user_id.in_(query.hosts))
    if query.contacts:
        conditions.append(Appointment.contact_id.in_(query.contacts))
    with tenant_session_scope(scope.workspace) as session:
        rows = list(
            session.execute(
                select(Appointment)
                .where(*conditions)
                .order_by(Appointment.starts_at, Appointment.id)
                .limit(rules.RANGE_ITEMS_MAX + 1)
            ).scalars()
        )
        truncated = len(rows) > rules.RANGE_ITEMS_MAX
        return Range(
            items=_items(session, scope, rows[: rules.RANGE_ITEMS_MAX]), truncated=truncated
        )


def upcoming(
    scope: Scope,
    *,
    hosts: tuple[uuid.UUID, ...] = (),
    contacts: tuple[uuid.UUID, ...] = (),
    limit: int = 10,
) -> list[Item]:
    """Appointments not cancelled that have not ended, earliest first: the
    calendar's "Up next" and the contact drawer's list."""
    conditions: list[Any] = [
        Appointment.tenant_id == scope.workspace,
        Appointment.status != "cancelled",
        Appointment.ends_at > _now(),
    ]
    if hosts:
        conditions.append(Appointment.host_user_id.in_(hosts))
    if contacts:
        conditions.append(Appointment.contact_id.in_(contacts))
    with tenant_session_scope(scope.workspace) as session:
        rows = list(
            session.execute(
                select(Appointment)
                .where(*conditions)
                .order_by(Appointment.starts_at, Appointment.id)
                .limit(min(limit, UPCOMING_MAX))
            ).scalars()
        )
        return _items(session, scope, rows)


def _hours(session: Session, scope: Scope) -> tuple[list[dict[str, str] | None] | None, str]:
    """The workspace's business hours (`None` while not set) and its zone."""
    row = session.execute(
        select(WorkspaceSettings.business_hours, WorkspaceSettings.time_zone).where(
            WorkspaceSettings.tenant_id == scope.workspace
        )
    ).one_or_none()
    if row is None:
        return None, setting_values.DEFAULT_TIME_ZONE
    return row.business_hours, row.time_zone


def availability(scope: Scope, start: datetime, end: datetime) -> dict[str, Any]:
    """The open intervals of `[start, end)` from the business hours (P5-B 6)."""
    with tenant_session_scope(scope.workspace) as session:
        hours, zone = _hours(session, scope)
    opened = [] if hours is None else rules.open_intervals(hours, zone, start, end)
    return {
        "hours_set": hours is not None,
        "time_zone": zone,
        "open": [{"starts_at": opens, "ends_at": closes} for opens, closes in opened],
    }


def conflicts(
    scope: Scope,
    host: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude: uuid.UUID | None = None,
) -> dict[str, Any]:
    """The live check behind the booking dialog (P5-A 4): the host's
    conflicting appointments, and whether the time falls outside business
    hours (P5-B 6; always false while they are not set)."""
    _check_times(starts_at, ends_at)
    with tenant_session_scope(scope.workspace) as session:
        found = _conflicting(session, scope, host, (starts_at, ends_at), exclude=exclude)
        hours, zone = _hours(session, scope)
    outside = hours is not None and not rules.within(
        rules.open_intervals(hours, zone, starts_at, ends_at), starts_at, ends_at
    )
    return {"conflicts": found, "outside_hours": outside}


# --- Writes ----------------------------------------------------------------------------


def create(
    scope: Scope,
    values: Mapping[str, Any],
    *,
    allow_conflict: bool = False,
    idempotency_key: str | None = None,
) -> tuple[Item, bool]:
    """Book an appointment; returns it and whether this was an idempotent
    replay (the key is scoped to the workspace and the acting member)."""
    _check_times(values["starts_at"], values["ends_at"])
    _check_host(scope, values["host_user_id"])
    appointment_id = uuid.uuid4()
    status = values.get("status") or rules.DEFAULT_STATUS

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        _check_contact(session, scope, values.get("contact_id"))
        host = values["host_user_id"]
        if not allow_conflict:
            _reserve(session, scope, host, (values["starts_at"], values["ends_at"]), None)
        now = _now()
        session.add(
            Appointment(
                id=appointment_id,
                tenant_id=scope.workspace,
                title=values["title"],
                starts_at=values["starts_at"],
                ends_at=values["ends_at"],
                kind=values.get("kind") or rules.DEFAULT_KIND,
                location=values.get("location"),
                note=values.get("note"),
                status=status,
                host_user_id=host,
                contact_id=values.get("contact_id"),
                cancelled_at=None,
                cancelled_by_user_id=None,
                created_by_user_id=scope.actor,
                updated_by_user_id=scope.actor,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
        session.flush()
        given = sorted(name for name in FIELDS if values.get(name) is not None)
        _audit(session, scope, "created", appointment_id, fields=given, status=status)
        return {"id": str(appointment_id)}

    replay = False
    if idempotency_key is None:
        result = _transaction(scope, business)
    else:
        fingerprint: dict[str, object] = {
            name: None if values.get(name) is None else str(values[name]) for name in FIELDS
        }
        fingerprint["status"] = status
        fingerprint["allow_conflict"] = allow_conflict
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
    scope: Scope,
    appointment_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    expected_version: int,
    allow_conflict: bool = False,
) -> Item:
    """Apply `changes` if the appointment is still at `expected_version`;
    `status` `cancelled` cancels it. A change that alters nothing is a
    no-op."""
    if changes.get("host_user_id") is not None:
        _check_host(scope, changes["host_user_id"])

    def apply(session: Session) -> None:
        row = _load(session, scope, appointment_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if row.status == "cancelled":
            raise AppointmentCancelledError
        wanted = {name: value for name, value in changes.items() if name != "status"}
        changed = sorted(name for name, value in wanted.items() if getattr(row, name) != value)
        status = changes.get("status")
        old_status = row.status
        if status == old_status:
            status = None
        if not changed and status is None:
            return
        starts_at = wanted.get("starts_at", row.starts_at)
        ends_at = wanted.get("ends_at", row.ends_at)
        _check_times(starts_at, ends_at)
        if "contact_id" in changed:
            _check_contact(session, scope, wanted["contact_id"])
        if _MOVES.intersection(changed) and status != "cancelled" and not allow_conflict:
            host = wanted.get("host_user_id", row.host_user_id)
            _reserve(session, scope, host, (starts_at, ends_at), row.id)
        now = _now()
        for name in changed:
            setattr(row, name, wanted[name])
        if status is not None:
            row.status = status
            if status == "cancelled":
                row.cancelled_at = now
                row.cancelled_by_user_id = scope.actor
        row.version += 1
        row.updated_at = now
        row.updated_by_user_id = scope.actor
        session.flush()
        _audit_update(session, scope, row.id, changed, (old_status, status))

    _transaction(scope, apply)
    return get(scope, appointment_id)


def _audit_update(
    session: Session,
    scope: Scope,
    appointment_id: uuid.UUID,
    changed: list[str],
    transition: tuple[str, str | None],
) -> None:
    """One entry for changed fields, one for a new status (P5-A 8)."""
    if changed:
        _audit(session, scope, "updated", appointment_id, fields=changed)
    previous, status = transition
    if status == "cancelled":
        _audit(session, scope, "cancelled", appointment_id, previous_status=previous)
    elif status is not None:
        _audit(session, scope, "status_changed", appointment_id, previous=previous, status=status)


def remove(scope: Scope, appointment_id: uuid.UUID) -> None:
    """Delete the appointment (Owner and Admin, P5-A 6)."""

    def apply(session: Session) -> None:
        row = _load(session, scope, appointment_id, lock=True)
        session.delete(row)
        session.flush()
        _audit(session, scope, "deleted", appointment_id)

    _transaction(scope, apply)
