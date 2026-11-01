"""Transactional email (decision P6-E): queue, send through SaaS-OS, track.

- `queue` records an email inside the caller's workspace transaction and
  indexes it globally with a retry time, so a lost job is found again by
  `sweep`. The caller enqueues `crm_app_email_send` after its commit.
- `send` (the job) hands a queued email to SaaS-OS's `send_email`, the
  deployment's provider (Resend in LeadStack's case), only while
  `EMAIL_SENDING_ENABLED` is on. It claims the email first, so concurrent
  jobs never send it twice; every try carries the same `Message-ID`, from
  which SaaS-OS derives Resend's idempotency key, so a retry after an
  ambiguous failure is not a second email within Resend's 24 hours. An
  address on the workspace's suppression list is never sent to. A
  permanent refusal fails the email; anything else is retried, at most
  `MAX_ATTEMPTS` times.
- `apply_event` records a provider's delivery event once per provider
  event id and moves the status forward only; a bounce or a complaint
  suppresses the address (origin `provider`).

Personal data (address, subject, text) stays in the workspace's own rows;
the global index holds ids and times; audit entries and errors carry codes,
never addresses or provider texts. SaaS-OS has no system caller for a
worker that sends on a member's behalf, so audit entries act as the member
whose action queued the email; an email queued by nobody has its status
and events as its record.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.email import (
    EmailMessage as OutgoingEmail,
)
from saas_os.core.email import (
    EmailProvider,
    EmailProviderError,
    InvalidEmailAddressError,
    get_email_default_sender,
    get_email_provider_name,
    send_email,
)
from saas_os.infra.db import (
    IntegrityError,
    Session,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app import suppression
from crm_app.domains import emails as rules
from crm_app.models import EmailEvent, EmailIndex, EmailMessage
from crm_app.records import Scope
from crm_app.settings import email_sending_enabled

RESOURCE = "crm_app.email"
JOB_NAME = "crm_app_email_send"
RETRY_DELAY = timedelta(minutes=10)
_ERROR_CODE = re.compile(r"[^a-z0-9_]+")


class EmailSendDeferredError(RuntimeError):
    """A try failed in a way that may pass; the job queue retries it. The
    message is a code only."""


def _now() -> datetime:
    return datetime.now(UTC)


def _code(reason: str) -> str:
    return (_ERROR_CODE.sub("_", reason.lower()).strip("_") or "error")[:64]


def _audit(session: Session, row: EmailMessage, verb: str, **meta: Any) -> None:
    if row.created_by_user_id is None:
        return
    record_in_transaction(
        session,
        caller=UserCaller(row.created_by_user_id),
        tenant_id=row.tenant_id,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"purpose": row.purpose, **meta},
    )


def _index(email_id: uuid.UUID, **values: Any) -> None:
    """Update the global index row (outside any workspace)."""
    with session_scope() as session:
        row = session.get(EmailIndex, email_id)
        if row is not None:
            for name, value in values.items():
                setattr(row, name, value)


# --- Queue -----------------------------------------------------------------------------


def queue(  # noqa: PLR0913 - one email's fields
    session: Session,
    scope: Scope,
    *,
    purpose: str,
    to_email: str,
    subject: str,
    text_body: str,
    contact_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Record an email in the caller's workspace transaction; returns its id.
    `InvalidValue` for content outside the rules."""
    if purpose not in rules.PURPOSES:
        raise ValueError(f"unknown email purpose: {purpose}")
    content = rules.content(to_email, subject, text_body)
    email_id = uuid.uuid4()
    now = _now()
    # Indexed first, with a retry time, in its own transaction: if the
    # caller's transaction rolls back, the sweeper finds no email and drops
    # the index row.
    with session_scope() as global_session:
        global_session.add(
            EmailIndex(
                email_message_id=email_id, workspace_id=scope.workspace, retry_at=now + RETRY_DELAY
            )
        )
    row = EmailMessage(
        id=email_id,
        tenant_id=scope.workspace,
        purpose=purpose,
        to_email=content.to_email,
        contact_id=contact_id,
        subject=content.subject,
        text_body=content.text_body,
        status="queued",
        attempts=0,
        created_by_user_id=scope.actor,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    _audit(session, row, "queued")
    return email_id


# --- Send --------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Claim:
    to_email: str
    subject: str
    text_body: str


def _claim(workspace: uuid.UUID, email_id: uuid.UUID) -> _Claim | str:  # noqa: PLR0911 - one answer per state
    """Take an email for one try, or say why not (a final status, `disabled`,
    `suppressed`, `failed`)."""
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            select(EmailMessage)
            .where(EmailMessage.tenant_id == workspace, EmailMessage.id == email_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return "missing"
        if row.status in rules.FINAL:
            return row.status
        now = _now()
        if row.status == "sending" and row.updated_at > now - RETRY_DELAY:
            # Another try is under way; a stale one (its process died) is
            # taken over by the sweeper's job after `RETRY_DELAY`.
            return "sending"
        if not email_sending_enabled():
            return "disabled"
        if not suppression.may_send(
            session, workspace, row.to_email, row.contact_id, marketing=False
        ):
            row.status, row.updated_at = "suppressed", now
            _audit(session, row, "suppressed")
            return "suppressed"
        if row.attempts >= rules.MAX_ATTEMPTS:
            row.status, row.updated_at = "failed", now
            row.last_error = row.last_error or "attempts_exhausted"
            _audit(session, row, "failed", error=row.last_error)
            return "failed"
        row.status, row.attempts, row.updated_at = "sending", row.attempts + 1, now
        return _Claim(to_email=row.to_email, subject=row.subject, text_body=row.text_body)


def _finish(workspace: uuid.UUID, email_id: uuid.UUID, apply: Any) -> None:
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            select(EmailMessage)
            .where(EmailMessage.tenant_id == workspace, EmailMessage.id == email_id)
            .with_for_update()
        ).scalar_one()
        apply(session, row)


def send(
    workspace: uuid.UUID, email_id: uuid.UUID, *, provider: EmailProvider | None = None
) -> str:
    """One try at an email; returns its status afterwards. Raises
    `EmailSendDeferredError` when a later try may succeed."""
    claim = _claim(workspace, email_id)
    if isinstance(claim, str):
        if claim in rules.FINAL or claim == "missing":
            _index(email_id, retry_at=None)
        elif claim == "disabled":  # looked at again later, never sent meanwhile
            postpone(email_id)
        return claim
    # Claimed: if this process dies mid-send, the sweeper tries again later
    # with the same Message-ID.
    postpone(email_id)
    sender = get_email_default_sender()
    if not sender:
        # Start-up validation requires it while sending is on; refuse safely.
        _release(workspace, email_id, "no_sender")
        raise EmailSendDeferredError("no_sender")
    outgoing = OutgoingEmail(
        sender=sender,
        to=(claim.to_email,),
        subject=claim.subject,
        text_body=claim.text_body,
        message_id=rules.message_id(str(email_id), sender),
    )
    failure: EmailProviderError | None = None
    provider_id: str | None = None
    try:
        provider_id = send_email(outgoing, provider=provider).provider_message_id
    except EmailProviderError as exc:
        failure = exc
    except InvalidEmailAddressError:
        # Refused before any provider call: the same message cannot pass.
        failure = EmailProviderError("send", "invalid_address", permanent=True)
    if failure is not None:
        code = _code(failure.reason)
        if failure.permanent:
            _fail(workspace, email_id, code)
            _index(email_id, retry_at=None)
            return "failed"
        _release(workspace, email_id, code)
        raise EmailSendDeferredError(code)
    name = "fake" if provider is not None else (get_email_provider_name() or "smtp")

    def sent(session: Session, row: EmailMessage) -> None:
        now = _now()
        row.status, row.provider, row.sent_at, row.updated_at = "sent", name, now, now
        row.provider_message_id = provider_id
        row.last_error = None
        _audit(session, row, "sent", provider=name)

    _finish(workspace, email_id, sent)
    _index(email_id, provider_message_id=provider_id, retry_at=None)
    return "sent"


def _fail(workspace: uuid.UUID, email_id: uuid.UUID, code: str) -> None:
    def failed(session: Session, row: EmailMessage) -> None:
        row.status, row.last_error, row.updated_at = "failed", code, _now()
        _audit(session, row, "failed", error=code)

    _finish(workspace, email_id, failed)


def _release(workspace: uuid.UUID, email_id: uuid.UUID, code: str) -> None:
    """Back to `queued` for another try, due in `RETRY_DELAY`."""

    def back(session: Session, row: EmailMessage) -> None:
        row.status, row.last_error, row.updated_at = "queued", code, _now()

    _finish(workspace, email_id, back)
    _index(email_id, retry_at=_now() + RETRY_DELAY)


# --- Sweep --------------------------------------------------------------------------------


def due(limit: int = 500) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Emails due for another try, as (workspace, email) pairs, oldest first."""
    with session_scope() as session:
        rows = session.execute(
            select(EmailIndex.workspace_id, EmailIndex.email_message_id)
            .where(EmailIndex.retry_at.is_not(None), EmailIndex.retry_at <= _now())
            .order_by(EmailIndex.retry_at)
            .limit(limit)
        ).all()
    return [(workspace, email_id) for workspace, email_id in rows]


def postpone(email_id: uuid.UUID) -> None:
    """Push an email's retry time on while its job is queued."""
    _index(email_id, retry_at=_now() + RETRY_DELAY)


# --- Delivery events ------------------------------------------------------------------------


def apply_event(event: rules.ProviderEvent) -> str:
    """Record a provider's delivery event; returns `recorded`, `duplicate` or
    `unknown` (no email of ours has that provider id)."""
    with session_scope() as session:
        found = session.execute(
            select(EmailIndex.workspace_id, EmailIndex.email_message_id).where(
                EmailIndex.provider_message_id == event.provider_message_id
            )
        ).first()
    if found is None:
        return "unknown"
    workspace, email_id = found
    try:
        with tenant_session_scope(workspace) as session:
            return _record_event(session, workspace, email_id, event)
    except IntegrityError:
        # The same provider event, recorded by a concurrent delivery.
        return "duplicate"


def _record_event(
    session: Session, workspace: uuid.UUID, email_id: uuid.UUID, event: rules.ProviderEvent
) -> str:
    seen = session.execute(
        select(EmailEvent.id).where(
            EmailEvent.tenant_id == workspace,
            EmailEvent.provider_event_id == event.provider_event_id,
        )
    ).first()
    if seen is not None:
        return "duplicate"
    row = session.execute(
        select(EmailMessage)
        .where(EmailMessage.tenant_id == workspace, EmailMessage.id == email_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return "unknown"
    now = _now()
    session.add(
        EmailEvent(
            id=uuid.uuid4(),
            tenant_id=workspace,
            email_message_id=email_id,
            provider_event_id=event.provider_event_id,
            type=event.type,
            occurred_at=event.occurred_at,
            received_at=now,
        )
    )
    session.flush()
    status = rules.after_event(row.status, event.type)
    if status != row.status:
        row.status, row.updated_at = status, now
    if event.type in ("bounced", "complained"):
        added = suppression.suppress_from_provider(
            session, workspace, row.to_email, reason=event.type, actor=row.created_by_user_id
        )
        if added:
            _audit(session, row, event.type)
    return "recorded"


def history(scope: Scope, email_id: uuid.UUID) -> list[dict[str, object]]:
    """An email's delivery events, oldest first (for its owner's screens)."""
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(EmailEvent.type, EmailEvent.occurred_at)
            .where(EmailEvent.tenant_id == scope.workspace, EmailEvent.email_message_id == email_id)
            .order_by(EmailEvent.occurred_at, EmailEvent.id)
        ).all()
    return [{"type": kind, "occurred_at": at} for kind, at in rows]


# --- Jobs -----------------------------------------------------------------------------------


async def enqueue(workspace: uuid.UUID, email_id: uuid.UUID) -> bool:
    """Ask the worker to try an email; `False` when the queue is unreachable,
    in which case the sweeper finds it at its retry time."""
    from saas_os.infra.jobs import TenantJobPayload, enqueue_job  # noqa: PLC0415

    payload = TenantJobPayload(tenant_id=str(workspace), data={"email_id": str(email_id)})
    try:
        await enqueue_job(JOB_NAME, payload)
    except Exception:  # noqa: BLE001 - any queue failure leaves it to the sweeper
        return False
    return True


def orphan(workspace: uuid.UUID, email_id: uuid.UUID) -> bool:
    """Drop the index row of an email whose workspace transaction never
    committed; `True` when it was such an orphan."""
    with tenant_session_scope(workspace) as session:
        exists = session.execute(
            select(EmailMessage.id).where(
                EmailMessage.tenant_id == workspace, EmailMessage.id == email_id
            )
        ).first()
    if exists is not None:
        return False
    with session_scope() as session:
        row = session.get(EmailIndex, email_id)
        if row is not None:
            session.delete(row)
    return True
