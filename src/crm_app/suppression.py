"""Consent and suppression: the service layer (decision P7-B, slice 7B).

Every function takes a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it. Every
write takes `lock_open_tenant` and records its audit entry in the same
transaction: counts, reasons and IDs, never an address, wording or note.

The suppression list holds email addresses the workspace must not send to;
it has no link to a contact, so nothing a contact does lifts it. Additions
are serialised per workspace by an advisory lock, which also guards the
size limit. Consent records are append-only: recording and withdrawing add
a record, and the latest one is the contact's current consent. Withdrawing
also suppresses the contact's address in the same transaction (P7-B 5).

`may_send` is the check every future send must pass (P7-B 6); nothing
sends yet.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
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

from crm_app.domains import paging
from crm_app.domains import suppression as rules
from crm_app.models import ConsentRecord, Contact, Suppression
from crm_app.records import (
    CONTACT,
    TOTAL_CAP,
    ConstraintViolationError,
    RecordError,
    RecordNotFoundError,
    Scope,
    TransactionConflictError,
    _after,
    _audit,
    _Event,
    _OrderKey,
)

RESOURCE = "crm_app.suppression"
_CHANNEL = "email"


class SuppressionNotFoundError(RecordError):
    status, code = 404, "suppression_not_found"


class SuppressionLimitError(RecordError):
    status, code = 409, "suppression_limit"


class NoEmailError(RecordError):
    """Consent is for an email address; the contact has none (P7-B 4)."""

    status, code = 409, "contact_has_no_email"


Item = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError:
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _list_audit(session: Session, scope: Scope, verb: str, resource_id: str, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=resource_id,
        metadata=meta,
    )


def _item(row: Suppression) -> Item:
    return {
        "id": row.id,
        "email": row.email,
        "reason": row.reason,
        "origin": row.origin,
        "note": row.note,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


# --- The list -------------------------------------------------------------------------


@dataclass(frozen=True)
class ListQuery:
    """A validated list request; the API has checked every value."""

    limit: int = 50
    cursor: str | None = None
    search: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[Item]
    next_cursor: str | None
    total: int
    total_capped: bool


def _escaped(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_suppressions(scope: Scope, query: ListQuery) -> Page:
    """The workspace's suppressions, newest first; `search` matches part of
    the address. Raises `paging.InvalidCursor` for another search's cursor."""
    filters = paging.filter_hash({"search": query.search})
    after = (
        paging.decode(query.cursor, "suppression", "created_at", "desc", filters)
        if query.cursor
        else None
    )
    keys = [
        _OrderKey(Suppression.created_at, Suppression.created_at, "created_at"),
        _OrderKey(Suppression.id, Suppression.id, "id"),
    ]
    conditions: list[Any] = [Suppression.tenant_id == scope.workspace]
    if query.search:
        conditions.append(Suppression.email.like(f"%{_escaped(query.search)}%", escape="\\"))
    with tenant_session_scope(scope.workspace) as session:
        counted = session.execute(
            select(Suppression.id).where(*conditions).limit(TOTAL_CAP + 1)
        ).all()
        statement = select(Suppression).where(*conditions)
        if after is not None:
            statement = statement.where(_after(keys, after, ascending=False))
        rows = list(
            session.execute(
                statement.order_by(Suppression.created_at.desc(), Suppression.id.desc()).limit(
                    query.limit + 1
                )
            ).scalars()
        )
        more = len(rows) > query.limit
        items = [_item(row) for row in rows[: query.limit]]
    next_cursor = None
    if more and items:
        last = items[-1]
        next_cursor = paging.encode(
            "suppression", "created_at", "desc", filters, (last["created_at"], last["id"])
        )
    return Page(
        items=items,
        next_cursor=next_cursor,
        total=min(len(counted), TOTAL_CAP),
        total_capped=len(counted) > TOTAL_CAP,
    )


def _room(session: Session, workspace: uuid.UUID, wanted: int) -> bool:
    """Whether `wanted` more rows stay within `MAX_ROWS`. Counts at most one
    row past the limit's remainder, never the whole list."""
    allowed = rules.MAX_ROWS - wanted
    if allowed < 0:
        return False
    beyond = session.execute(
        select(Suppression.id).where(Suppression.tenant_id == workspace).offset(allowed).limit(1)
    ).first()
    return beyond is None


def _suppress(  # noqa: PLR0913 - the addresses, then why and how
    session: Session,
    scope: Scope,
    emails: list[str],
    *,
    reason: str,
    origin: str,
    note: str | None,
) -> int:
    """Insert the addresses not yet suppressed; returns how many were new.
    An address already on the list keeps its first reason (P7-B 5)."""
    if not emails:
        return 0
    acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.add")
    already = set(
        session.execute(
            select(Suppression.email).where(
                Suppression.tenant_id == scope.workspace, Suppression.email.in_(emails)
            )
        ).scalars()
    )
    new = [email for email in emails if email not in already]
    if not new:
        return 0
    if not _room(session, scope.workspace, len(new)):
        raise SuppressionLimitError
    now = _now()
    session.add_all(
        Suppression(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            email=email,
            reason=reason,
            origin=origin,
            note=note,
            created_by_user_id=scope.actor,
            created_at=now,
        )
        for email in new
    )
    session.flush()
    return len(new)


def add(scope: Scope, emails: list[str], *, reason: str, note: str | None) -> dict[str, int]:
    """Suppress the given addresses (already normalised by `rules.addresses`);
    returns how many were added and how many were already on the list."""

    def apply(session: Session) -> dict[str, int]:
        added = _suppress(session, scope, emails, reason=reason, origin="manual", note=note)
        if added:
            _list_audit(session, scope, "added", str(scope.workspace), count=added, reason=reason)
        return {"added": added, "already_suppressed": len(emails) - added}

    return _transaction(scope, apply)


def remove(scope: Scope, suppression_id: uuid.UUID) -> None:
    """Lift one suppression: the address may be sent to again."""

    def apply(session: Session) -> None:
        # No row lock: the runtime role holds no UPDATE here (migration 0017),
        # and a concurrent removal only deletes the same row twice.
        row = session.execute(
            select(Suppression).where(
                Suppression.tenant_id == scope.workspace, Suppression.id == suppression_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise SuppressionNotFoundError
        reason = row.reason
        session.delete(row)
        session.flush()
        _list_audit(session, scope, "removed", str(suppression_id), reason=reason)

    _transaction(scope, apply)


# --- The send check -------------------------------------------------------------------


def _suppressed(session: Session, workspace: uuid.UUID, email: str) -> Suppression | None:
    return session.execute(
        select(Suppression).where(Suppression.tenant_id == workspace, Suppression.email == email)
    ).scalar_one_or_none()


def _consent_state(session: Session, workspace: uuid.UUID, contact_id: uuid.UUID) -> str:
    latest = session.execute(
        select(ConsentRecord.status)
        .where(
            ConsentRecord.tenant_id == workspace,
            ConsentRecord.contact_id == contact_id,
            ConsentRecord.channel == _CHANNEL,
        )
        .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return latest or "none"


def may_send(
    session: Session,
    workspace: uuid.UUID,
    email: str,
    contact_id: uuid.UUID | None,
    *,
    marketing: bool,
) -> bool:
    """Whether `email` (as stored: lower-cased) may be sent to now (P7-B 6),
    inside the caller's session: never when suppressed; a marketing send
    also needs the contact's consent `granted`."""
    suppressed = _suppressed(session, workspace, email) is not None
    consent = _consent_state(session, workspace, contact_id) if contact_id else "none"
    return rules.may_send(suppressed=suppressed, consent=consent, marketing=marketing)


# --- A contact's consent --------------------------------------------------------------


def _contact(session: Session, scope: Scope, contact_id: uuid.UUID, *, lock: bool) -> Contact:
    query = select(Contact).where(Contact.tenant_id == scope.workspace, Contact.id == contact_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def contact_email_status(scope: Scope, contact_id: uuid.UUID) -> Item:
    """What the contact drawer shows (P7-B 10): whether and why the address
    is suppressed, the current consent, and whether marketing may be sent."""
    with tenant_session_scope(scope.workspace) as session:
        contact = _contact(session, scope, contact_id, lock=False)
        email = contact.email
        consent = _consent_state(session, scope.workspace, contact.id)
        row = _suppressed(session, scope.workspace, email) if email else None
        suppression = (
            None
            if row is None
            else {"id": row.id, "reason": row.reason, "created_at": row.created_at}
        )
    return {
        "has_email": email is not None,
        "consent": consent,
        "suppression": suppression,
        "marketing_allowed": email is not None
        and rules.may_send(suppressed=suppression is not None, consent=consent, marketing=True),
    }


def _record(
    session: Session, scope: Scope, contact_id: uuid.UUID, status: str, wording: str | None
) -> None:
    session.add(
        ConsentRecord(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            contact_id=contact_id,
            channel=_CHANNEL,
            status=status,
            method="manual",
            wording=wording,
            form_id=None,
            submission_id=None,
            recorded_by_user_id=scope.actor,
            recorded_at=_now(),
        )
    )
    session.flush()


def record_consent(scope: Scope, contact_id: uuid.UUID, wording: str) -> Item:
    """A member records the consent a person gave, with its exact wording
    (P7-B 4). It never lifts a suppression (P7-B 5)."""

    def apply(session: Session) -> None:
        contact = _contact(session, scope, contact_id, lock=True)
        if contact.email is None:
            raise NoEmailError
        _record(session, scope, contact.id, "granted", wording)
        event = _Event("consent_recorded", contact.id, {"channel": _CHANNEL})
        _audit(session, CONTACT, scope, event)

    _transaction(scope, apply)
    return contact_email_status(scope, contact_id)


def withdraw_consent(scope: Scope, contact_id: uuid.UUID, note: str | None) -> Item:
    """The person no longer wants email: a `withdrawn` record and, when the
    contact has an address, its suppression, in one transaction (P7-B 5)."""

    def apply(session: Session) -> None:
        contact = _contact(session, scope, contact_id, lock=True)
        _record(session, scope, contact.id, "withdrawn", note)
        event = _Event("consent_withdrawn", contact.id, {"channel": _CHANNEL})
        _audit(session, CONTACT, scope, event)
        if contact.email is None:
            return
        added = _suppress(
            session,
            scope,
            [contact.email],
            reason="unsubscribed",
            origin="consent_withdrawn",
            note=None,
        )
        if added:
            _list_audit(
                session, scope, "added", str(scope.workspace), count=1, reason="unsubscribed"
            )

    _transaction(scope, apply)
    return contact_email_status(scope, contact_id)
