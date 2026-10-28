"""Booking pages: the service layer (decision P5-C, slice 5C).

Members' functions take a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it. Every
write takes `lock_open_tenant` and records its audit entry in the same
transaction: the page ID and field names, never the page's text.

The public side has no member: the workspace comes from the address and is
only a lookup key. An unknown workspace or key, a draft page, a page whose
host has left and a closed or suspended workspace are all
`BookingPageNotFoundError`. A booking checks the time again under the
host's lock (P5-A 4), creates or matches a contact and creates the
appointment in one transaction, acting as the host (P5-C 6, 9); a matched
contact is never changed. The visitor's link token is returned once and
stored only as its SHA-256.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.idempotency import run_idempotent
from saas_os.core.identity import get_membership
from saas_os.core.tenancy import (
    PRINCIPAL_INACCESSIBLE_STATUSES,
    TenantClosedError,
    TenantNotFoundError,
    TenantStatus,
    lock_open_tenant,
    require_open_tenant,
)
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app import appointments
from crm_app.domains import appointments as appointment_rules
from crm_app.domains import booking_pages as rules
from crm_app.domains.records import InvalidValue
from crm_app.models import Appointment, Booking, BookingPage, Contact
from crm_app.records import (
    CONTACT,
    ConstraintViolationError,
    DuplicateRecordError,
    InvalidReferenceError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    check_owner,
    insert_record,
)

RESOURCE = "crm_app.booking_page"
FIELDS = (
    "name",
    "description",
    "host_user_id",
    "length_minutes",
    "step_minutes",
    "kind",
    "location",
    "notice_minutes",
    "horizon_days",
    "status",
)
_ACTIVE = "active"


class BookingPageNotFoundError(RecordError):
    status, code = 404, "booking_page_not_found"


class BookingNotFoundError(RecordError):
    status, code = 404, "booking_not_found"


class BookingPageLimitError(RecordError):
    status, code = 409, "booking_page_limit"


class BookingPageRuleError(RecordError):
    """A page the rules refuse, by the code of the rule."""

    status = 422

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TimeUnavailableError(RecordError):
    """The chosen time is not (or no longer) a free time (P5-C 6)."""

    status, code = 409, "time_unavailable"


class BookingLimitError(RecordError):
    status, code = 409, "booking_limit"


class NotCancellableError(RecordError):
    """The appointment has started: the visitor can no longer cancel."""

    status, code = 409, "booking_not_cancellable"


class VisitorError(RecordError):
    """The visitor's details the page refuses, a rule per field name."""

    status, code = 422, "invalid_visitor"

    def __init__(self, errors: Mapping[str, str]) -> None:
        super().__init__(self.code)
        self.errors = dict(errors)


Item = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](workspace: uuid.UUID, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(workspace) as session:
            lock_open_tenant(session, workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError:
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _page_audit(session: Session, scope: Scope, verb: str, page_id: uuid.UUID, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(page_id),
        metadata=meta,
    )


def _load(session: Session, scope: Scope, page_id: uuid.UUID, *, lock: bool) -> BookingPage:
    query = select(BookingPage).where(
        BookingPage.tenant_id == scope.workspace, BookingPage.id == page_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise BookingPageNotFoundError
    return row


def _item(row: BookingPage) -> Item:
    return {name: getattr(row, name) for name in _ITEM_FIELDS}


_ITEM_FIELDS = (
    "id",
    "name",
    "description",
    "status",
    "public_key",
    "host_user_id",
    "length_minutes",
    "step_minutes",
    "kind",
    "location",
    "notice_minutes",
    "horizon_days",
    "booking_count",
    "last_booked_at",
    "created_at",
    "updated_at",
    "created_by_user_id",
    "updated_by_user_id",
    "version",
)


# --- Validation ----------------------------------------------------------------------


def _normalised(values: Mapping[str, Any]) -> dict[str, Any]:  # noqa: PLR0912 - one branch per field
    """The given values as stored; text is checked here so a refusal never
    echoes it."""
    result: dict[str, Any] = {}
    for name, value in values.items():
        try:
            if name == "name":
                result[name] = rules.name(value)
            elif name == "description":
                result[name] = rules.description(value)
            elif name == "location":
                result[name] = appointment_rules.location(value)
            elif name == "length_minutes":
                result[name] = rules.choice(value, rules.LENGTHS)
            elif name == "step_minutes":
                result[name] = rules.choice(value, rules.STEPS)
            elif name == "notice_minutes":
                result[name] = rules.bounded(value, 0, rules.NOTICE_MAX)
            elif name == "horizon_days":
                result[name] = rules.bounded(value, 1, rules.HORIZON_MAX)
            elif name == "kind":
                if value not in appointment_rules.KINDS:
                    raise InvalidValue("unknown kind")
                result[name] = value
            elif name == "status":
                if value not in rules.STATUSES:
                    raise InvalidValue("unknown status")
                result[name] = value
            else:
                result[name] = value
        except InvalidValue:
            raise BookingPageRuleError(f"invalid_{name}") from None
    return result


def _check_host(scope: Scope, user_id: uuid.UUID) -> None:
    try:
        check_owner(scope, user_id)
    except InvalidReferenceError:
        raise InvalidReferenceError("host_not_member") from None


def _check_publishable(session: Session, scope: Scope) -> None:
    """A published page needs the business hours (P5-C 3)."""
    hours, _zone = appointments.workspace_hours(session, scope.workspace)
    if hours is None:
        raise BookingPageRuleError("business_hours_required")


# --- Members ---------------------------------------------------------------------------


def list_pages(scope: Scope) -> list[Item]:
    """Every booking page of the workspace (at most `MAX_PAGES`), last
    changed first."""
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(BookingPage)
            .where(BookingPage.tenant_id == scope.workspace)
            .order_by(BookingPage.updated_at.desc(), BookingPage.id.desc())
            .limit(rules.MAX_PAGES)
        ).scalars()
        return [_item(row) for row in rows]


def get(scope: Scope, page_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        return _item(_load(session, scope, page_id, lock=False))


def create(
    scope: Scope, values: Mapping[str, Any], *, idempotency_key: str | None = None
) -> tuple[Item, bool]:
    """A new draft page; returns it and whether this was an idempotent replay
    (the key is scoped to the workspace and the acting member). The host
    defaults to the creator."""
    given = _normalised(values)
    host = given.get("host_user_id") or scope.actor
    _check_host(scope, host)
    page_id = uuid.uuid4()
    public_key = secrets.token_urlsafe(16)

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        count = len(
            session.execute(
                select(BookingPage.id)
                .where(BookingPage.tenant_id == scope.workspace)
                .limit(rules.MAX_PAGES)
            ).all()
        )
        if count >= rules.MAX_PAGES:
            raise BookingPageLimitError
        now = _now()
        session.add(
            BookingPage(
                id=page_id,
                tenant_id=scope.workspace,
                name=given["name"],
                description=given.get("description"),
                status="draft",
                public_key=public_key,
                host_user_id=host,
                length_minutes=given.get("length_minutes", rules.DEFAULT_LENGTH),
                step_minutes=given.get("step_minutes", rules.DEFAULT_STEP),
                kind=given.get("kind", rules.DEFAULT_KIND),
                location=given.get("location"),
                notice_minutes=given.get("notice_minutes", rules.DEFAULT_NOTICE),
                horizon_days=given.get("horizon_days", rules.DEFAULT_HORIZON),
                booking_count=0,
                last_booked_at=None,
                created_by_user_id=scope.actor,
                updated_by_user_id=scope.actor,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
        session.flush()
        _page_audit(session, scope, "created", page_id)
        return {"id": str(page_id)}

    replay = False
    if idempotency_key is None:
        result = _transaction(scope.workspace, business)
    else:
        fingerprint = {
            name: None if given.get(name) is None else str(given[name])
            for name in FIELDS
            if name != "status"
        }
        fingerprint["host_user_id"] = str(host)
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
        except IntegrityError:
            raise ConstraintViolationError from None
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
    return get(scope, uuid.UUID(str(result["id"]))), replay


def update(
    scope: Scope, page_id: uuid.UUID, changes: Mapping[str, Any], *, expected_version: int
) -> Item:
    """Apply `changes` if the page is still at `expected_version`.
    Publishing and unpublishing are a change of `status`; the audit entry
    says which. A change that alters nothing is a no-op."""
    given = _normalised(changes)
    if given.get("host_user_id") is not None:
        _check_host(scope, given["host_user_id"])

    def apply(session: Session) -> None:
        row = _load(session, scope, page_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        changed = sorted(name for name, value in given.items() if getattr(row, name) != value)
        if not changed:
            return
        before = row.status
        for name in changed:
            setattr(row, name, given[name])
        if row.status == "published":
            if "host_user_id" not in changed:
                _check_host(scope, row.host_user_id)
            _check_publishable(session, scope)
        row.version += 1
        row.updated_at = _now()
        row.updated_by_user_id = scope.actor
        session.flush()
        other = [name for name in changed if name != "status"]
        if other:
            _page_audit(session, scope, "updated", page_id, fields=other)
        if row.status != before:
            verb = "published" if row.status == "published" else "unpublished"
            _page_audit(session, scope, verb, page_id)

    _transaction(scope.workspace, apply)
    return get(scope, page_id)


def remove(scope: Scope, page_id: uuid.UUID) -> None:
    """Delete a page; the appointments it booked stay (P5-C 2)."""

    def apply(session: Session) -> None:
        row = _load(session, scope, page_id, lock=True)
        session.delete(row)
        session.flush()
        _page_audit(session, scope, "deleted", page_id)

    _transaction(scope.workspace, apply)


# --- Public ----------------------------------------------------------------------------


def _accessible(status: str) -> bool:
    return TenantStatus(status) not in PRINCIPAL_INACCESSIBLE_STATUSES


def _open_workspace(workspace: uuid.UUID) -> None:
    try:
        tenant = require_open_tenant(workspace)
    except (TenantClosedError, TenantNotFoundError):
        raise BookingPageNotFoundError from None
    if not _accessible(tenant.status):
        raise BookingPageNotFoundError


def _gate(session: Session, workspace: uuid.UUID) -> None:
    """The workspace exists, is open and is not suspended."""
    try:
        tenant = lock_open_tenant(session, workspace)
    except (TenantClosedError, TenantNotFoundError):
        raise BookingPageNotFoundError from None
    if not _accessible(tenant.status):
        raise BookingPageNotFoundError


def _active_member(workspace: uuid.UUID, user_id: uuid.UUID) -> bool:
    membership = get_membership(workspace, user_id)
    return membership is not None and membership.status == _ACTIVE


def _published(session: Session, workspace: uuid.UUID, key: str, *, lock: bool) -> BookingPage:
    query = select(BookingPage).where(
        BookingPage.tenant_id == workspace,
        BookingPage.public_key == key,
        BookingPage.status == "published",
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise BookingPageNotFoundError
    return row


@dataclass(frozen=True)
class _Offer:
    """What a published page offers, read before any time is computed."""

    page_id: uuid.UUID
    name: str
    host: uuid.UUID
    length: timedelta
    step: timedelta
    notice: timedelta
    horizon: timedelta


def _offer(row: BookingPage) -> _Offer:
    return _Offer(
        page_id=row.id,
        name=row.name,
        host=row.host_user_id,
        length=timedelta(minutes=row.length_minutes),
        step=timedelta(minutes=row.step_minutes),
        notice=timedelta(minutes=row.notice_minutes),
        horizon=timedelta(days=row.horizon_days),
    )


def public_page(workspace: uuid.UUID, key: str) -> Item:
    """What the hosted page shows before booking: the name, description,
    length and kind, and the workspace's time zone. The host, the location
    and the workspace's name are not shown."""
    _open_workspace(workspace)
    with tenant_session_scope(workspace) as session:
        row = _published(session, workspace, key, lock=False)
        _hours, zone = appointments.workspace_hours(session, workspace)
        item = {
            "name": row.name,
            "description": row.description,
            "length_minutes": row.length_minutes,
            "kind": row.kind,
            "time_zone": zone,
            "horizon_days": row.horizon_days,
        }
        host = row.host_user_id
    if not _active_member(workspace, host):
        raise BookingPageNotFoundError
    return item


def _free(
    session: Session, workspace: uuid.UUID, offer: _Offer, start: datetime, end: datetime
) -> list[datetime]:
    """The page's free times starting in `[start, end)` (P5-C 4)."""
    hours, zone = appointments.workspace_hours(session, workspace)
    if hours is None:
        return []
    now = _now()
    earliest = max(start, now + offer.notice)
    latest = min(end - timedelta(microseconds=1), now + offer.horizon)
    if earliest > latest:
        return []
    intervals = appointment_rules.open_intervals(hours, zone, start, end + offer.length)
    busy = session.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            Appointment.tenant_id == workspace,
            Appointment.host_user_id == offer.host,
            Appointment.status != "cancelled",
            Appointment.starts_at < end + offer.length,
            Appointment.ends_at > start,
            Appointment.starts_at > start - appointment_rules.LONGEST,
        )
    ).all()
    return rules.free_times(
        intervals,
        [(row.starts_at, row.ends_at) for row in busy],
        length=offer.length,
        step=offer.step,
        earliest=earliest,
        latest=latest,
    )


def free_times(workspace: uuid.UUID, key: str, start: datetime, end: datetime) -> list[datetime]:
    """The free start times in `[start, end)` (at most 14 days, checked by
    the API)."""
    _open_workspace(workspace)
    with tenant_session_scope(workspace) as session:
        offer = _offer(_published(session, workspace, key, lock=False))
    if not _active_member(workspace, offer.host):
        raise BookingPageNotFoundError
    with tenant_session_scope(workspace) as session:
        return _free(session, workspace, offer, start, end)


@dataclass(frozen=True)
class BookingRequest:
    """A visitor's booking as the API received it."""

    starts_at: datetime
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    message: str | None


def _view(appointment: Appointment, page: BookingPage | None, booking: Booking) -> Item:
    """What the visitor sees of their booking (P5-C 7)."""
    return {
        "page_name": page.name if page is not None else None,
        "starts_at": appointment.starts_at,
        "ends_at": appointment.ends_at,
        "kind": appointment.kind,
        "location": appointment.location,
        "cancelled": appointment.status == "cancelled",
        "cancelled_by_visitor": booking.cancelled_by_visitor_at is not None,
        "can_cancel": appointment.status != "cancelled" and appointment.starts_at > _now(),
    }


def _match(session: Session, workspace: uuid.UUID, email: str) -> Contact | None:
    return session.execute(
        select(Contact)
        .where(
            Contact.tenant_id == workspace,
            Contact.archived_at.is_(None),
            Contact.email == email,
        )
        .with_for_update()
    ).scalar_one_or_none()


def _upcoming(
    session: Session, workspace: uuid.UUID, page_id: uuid.UUID, contact_id: uuid.UUID
) -> int:
    """The contact's bookings on this page that are not cancelled and have
    not ended."""
    rows = session.execute(
        select(Booking.id)
        .join(
            Appointment,
            (Appointment.tenant_id == Booking.tenant_id)
            & (Appointment.id == Booking.appointment_id),
        )
        .where(
            Booking.tenant_id == workspace,
            Booking.booking_page_id == page_id,
            Booking.contact_id == contact_id,
            Appointment.status != "cancelled",
            Appointment.ends_at > _now(),
        )
        .limit(rules.UPCOMING_PER_CONTACT)
    ).all()
    return len(rows)


@dataclass(frozen=True)
class _Accepted:
    """A booking whose details passed the page's checks."""

    workspace: uuid.UUID
    key: str
    offer: _Offer
    starts_at: datetime
    visitor: dict[str, str | None]
    token_hash: str


def _record(session: Session, accepted: _Accepted) -> dict[str, object]:
    """The booking's whole effect, in the idempotency transaction."""
    workspace, offer = accepted.workspace, accepted.offer
    _gate(session, workspace)
    page = _published(session, workspace, accepted.key, lock=True)
    if _offer(page) != offer:
        # Changed since the details were checked: the visitor retries.
        raise TransactionConflictError
    scope = Scope(workspace=workspace, actor=offer.host)
    starts_at = accepted.starts_at
    ends_at = starts_at + offer.length
    acquire_tenant_advisory_lock(session, workspace, f"{appointments.RESOURCE}.host:{offer.host}")
    if starts_at not in _free(session, workspace, offer, starts_at, ends_at):
        raise TimeUnavailableError
    visitor = accepted.visitor
    email = visitor["email"]
    if email is None:  # `rules.visitor` requires it.
        raise ConstraintViolationError
    contact = _match(session, workspace, email)
    if contact is None:
        contact_id, outcome = uuid.uuid4(), "created"
        insert_record(
            session,
            CONTACT,
            scope,
            {
                "first_name": visitor["first_name"],
                "last_name": visitor["last_name"],
                "email": email,
                "phone": visitor["phone"],
                "lifecycle_stage": "lead",
                "source": "booking",
                "owner_user_id": offer.host,
            },
            record_id=contact_id,
            booking_page_id=page.id,
        )
    else:
        contact_id, outcome = contact.id, "matched"
        if _upcoming(session, workspace, page.id, contact_id) >= rules.UPCOMING_PER_CONTACT:
            raise BookingLimitError
    visitor_name = " ".join(part for part in (visitor["first_name"], visitor["last_name"]) if part)
    now = _now()
    appointment_id = uuid.uuid4()
    session.add(
        Appointment(
            id=appointment_id,
            tenant_id=workspace,
            title=rules.title(page.name, visitor_name),
            starts_at=starts_at,
            ends_at=ends_at,
            kind=page.kind,
            location=page.location,
            note=visitor["message"],
            status=appointment_rules.DEFAULT_STATUS,
            host_user_id=offer.host,
            contact_id=contact_id,
            cancelled_at=None,
            cancelled_by_user_id=None,
            created_by_user_id=offer.host,
            updated_by_user_id=offer.host,
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
    session.flush()
    given = ["contact_id", "ends_at", "host_user_id", "kind", "starts_at", "title"]
    if page.location is not None:
        given.append("location")
    if visitor["message"] is not None:
        given.append("note")
    record_in_transaction(
        session,
        caller=UserCaller(offer.host),
        tenant_id=workspace,
        action=f"{appointments.RESOURCE}.created",
        resource_type=appointments.RESOURCE,
        resource_id=str(appointment_id),
        metadata={
            "fields": sorted(given),
            "status": appointment_rules.DEFAULT_STATUS,
            "booking_page_id": str(page.id),
        },
    )
    session.add(
        Booking(
            id=uuid.uuid4(),
            tenant_id=workspace,
            booking_page_id=page.id,
            appointment_id=appointment_id,
            contact_id=contact_id,
            outcome=outcome,
            token_hash=accepted.token_hash,
            cancelled_by_visitor_at=None,
            created_at=now,
        )
    )
    page.booking_count += 1
    page.last_booked_at = now
    return {"appointment_id": str(appointment_id)}


def book(
    workspace: uuid.UUID, key: str, request: BookingRequest, *, idempotency_key: str
) -> tuple[Item, str | None]:
    """Book a free time on a published page; returns what the visitor sees
    and their link token, which only the first answer carries: a replay
    returns `None` for it, since only its hash is kept (P5-C 6)."""
    with tenant_session_scope(workspace) as session:
        _gate(session, workspace)
        offer = _offer(_published(session, workspace, key, lock=False))
    if not _active_member(workspace, offer.host):
        raise BookingPageNotFoundError
    try:
        visitor = rules.visitor(
            request.first_name, request.last_name, request.email, request.phone, request.message
        )
    except rules.InvalidVisitor as exc:
        raise VisitorError(exc.errors) from None
    token = secrets.token_urlsafe(32)
    token_hash = rules.token_hash(token)
    if token_hash is None:  # `token_urlsafe(32)` is always 43 characters.
        raise ConstraintViolationError
    accepted = _Accepted(
        workspace=workspace,
        key=key,
        offer=offer,
        starts_at=request.starts_at.astimezone(UTC),
        visitor=visitor,
        token_hash=token_hash,
    )
    fingerprint = {
        "starts_at": accepted.starts_at.isoformat(),
        **{name: str(value) for name, value in visitor.items()},
    }
    # Two first bookings with one new email can race; the loser's unique
    # violation rolls everything back and the retry matches the winner.
    for attempt in (1, 2):
        try:
            replay, result = run_idempotent(
                workspace,
                f"crm_app.booking.create:{offer.page_id}",
                idempotency_key,
                fingerprint,
                lambda session: _record(session, accepted),
            )
        except (TenantClosedError, TenantNotFoundError):
            raise BookingPageNotFoundError from None
        except (DuplicateRecordError, IntegrityError):
            if attempt == 2:
                raise TransactionConflictError from None
            continue
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
        view = _view_of(workspace, uuid.UUID(str(result["appointment_id"])))
        return view, None if replay else token
    raise TransactionConflictError


def _view_of(workspace: uuid.UUID, appointment_id: uuid.UUID) -> Item:
    with tenant_session_scope(workspace) as session:
        row = (
            session.execute(
                select(Booking, Appointment, BookingPage)
                .join(
                    Appointment,
                    (Appointment.tenant_id == Booking.tenant_id)
                    & (Appointment.id == Booking.appointment_id),
                )
                .outerjoin(
                    BookingPage,
                    (BookingPage.tenant_id == Booking.tenant_id)
                    & (BookingPage.id == Booking.booking_page_id),
                )
                .where(Booking.tenant_id == workspace, Booking.appointment_id == appointment_id)
            )
            .tuples()
            .one()
        )
        booking, appointment, page = row
        return _view(appointment, page, booking)


def _by_token(
    session: Session, workspace: uuid.UUID, token: str, *, lock: bool
) -> tuple[Booking, Appointment, BookingPage | None]:
    digest = rules.token_hash(token)
    if digest is None:
        raise BookingNotFoundError
    query = (
        select(Booking, Appointment, BookingPage)
        .join(
            Appointment,
            (Appointment.tenant_id == Booking.tenant_id)
            & (Appointment.id == Booking.appointment_id),
        )
        .outerjoin(
            BookingPage,
            (BookingPage.tenant_id == Booking.tenant_id)
            & (BookingPage.id == Booking.booking_page_id),
        )
        .where(Booking.tenant_id == workspace, Booking.token_hash == digest)
    )
    if lock:
        query = query.with_for_update(of=[Booking, Appointment])
    row = session.execute(query).tuples().one_or_none()
    if row is None:
        raise BookingNotFoundError
    return row


def view(workspace: uuid.UUID, token: str) -> Item:
    """The visitor's booking by their link token (P5-C 7)."""
    try:
        _open_workspace(workspace)
    except BookingPageNotFoundError:
        raise BookingNotFoundError from None
    with tenant_session_scope(workspace) as session:
        booking, appointment, page = _by_token(session, workspace, token, lock=False)
        return _view(appointment, page, booking)


def cancel(workspace: uuid.UUID, token: str) -> Item:
    """The visitor cancels until the appointment starts; cancelling again
    answers the same view (P5-C 7)."""

    def apply(session: Session) -> Item:
        try:
            _gate(session, workspace)
        except BookingPageNotFoundError:
            raise BookingNotFoundError from None
        booking, appointment, page = _by_token(session, workspace, token, lock=True)
        if appointment.status == "cancelled":
            return _view(appointment, page, booking)
        if appointment.starts_at <= _now():
            raise NotCancellableError
        now = _now()
        previous = appointment.status
        appointment.status = "cancelled"
        appointment.cancelled_at = now
        appointment.cancelled_by_user_id = None
        appointment.updated_at = now
        appointment.updated_by_user_id = None
        appointment.version += 1
        booking.cancelled_by_visitor_at = now
        session.flush()
        metadata: dict[str, object] = {"previous_status": previous, "by": "visitor"}
        if booking.booking_page_id is not None:
            metadata["booking_page_id"] = str(booking.booking_page_id)
        record_in_transaction(
            session,
            caller=UserCaller(appointment.host_user_id),
            tenant_id=workspace,
            action=f"{appointments.RESOURCE}.cancelled",
            resource_type=appointments.RESOURCE,
            resource_id=str(appointment.id),
            metadata=metadata,
        )
        return _view(appointment, page, booking)

    try:
        with tenant_session_scope(workspace) as session:
            return apply(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise
