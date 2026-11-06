"""Inbound email (decision P6-I): record, process, route, quarantine.

1. `record` stores a verified `email.received` webhook event once (unique by
   the webhook's event id and by the provider's email id) before anything
   else; the route then enqueues `crm_app_inbound_process`.
2. `process_due` (the job, and the sweeper `crm_app.email_maintenance`)
   claims due rows with `FOR UPDATE SKIP LOCKED`, so concurrent workers
   never take the same email, and a row left `processing` by a dead worker
   is taken again after `STALE`. Each email's content comes from a
   `ReceivingClient`; a transient failure waits with backoff and jitter;
   permanent failures and exhausted tries end as `failed`, never silently.
3. Routing trusts only server-side data: the recipient must be one of this
   deployment's routing addresses, whose token's hash
   (`conversation_route_index`) names a workspace and conversation; inside
   that workspace the conversation's own route row must hold the same
   token. Mail that matches no workspace stays `unmatched` for an operator,
   keeping only the sender's domain; routed mail that needs a look
   (`crm_app.domains.inbound.review_reason`) is quarantined for the
   workspace's members; the rest becomes an inbound message, at most once
   per email (a unique key on `inbound_email_id`).
4. Attachments are listed, never fetched.

No real `ReceivingClient` exists yet: SaaS-OS v0.6.0's egress client sends
only POST, and Resend's receiving API is GET (`EMAIL-ARCHITECTURE.md`, section 1).
Until one is approved, received emails wait as `received`, nothing is lost,
and only tests drive processing with a test double. Logs and errors carry
ids and codes, never addresses, subjects or bodies.
"""

from __future__ import annotations

import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from saas_os.infra.db import (
    IntegrityError,
    Session,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app import system_audit
from crm_app.domains import emails as email_rules
from crm_app.domains import inbound as rules
from crm_app.models import (
    Contact,
    Conversation,
    ConversationMessage,
    ConversationRoute,
    ConversationRouteIndex,
    InboundEmail,
    InboundQuarantine,
)
from crm_app.records import RecordError, RecordNotFoundError, Scope, StaleVersionError
from crm_app.settings import email_parent_domain, inbound_enabled

JOB_NAME = "crm_app_inbound_process"
BATCH = 50
MAX_ATTEMPTS = 8
STALE = timedelta(minutes=10)


class FetchError(Exception):
    """The receiving API did not answer usefully. `code` is a short fixed
    reason; `transient` says whether a later try may succeed."""

    def __init__(
        self, code: str, *, transient: bool = True, retry_after: float | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.transient = transient
        self.retry_after = retry_after


class ReceivingClient(Protocol):
    def fetch(self, provider_email_id: str) -> object:
        """The provider's JSON answer for one received email; raises
        `FetchError`."""
        ...


def configured_client() -> ReceivingClient | None:
    """The deployment's receiving client: none yet (see the module note)."""
    return None


def _now() -> datetime:
    return datetime.now(UTC)


# --- Recording --------------------------------------------------------------------------------


def record(event_id: str, event: rules.ReceivedEvent) -> str:
    """Store a verified received event; returns `recorded` or `duplicate`."""
    now = _now()
    try:
        with session_scope() as session:
            seen = session.execute(
                select(InboundEmail.id).where(
                    (InboundEmail.provider_event_id == event_id)
                    | (InboundEmail.provider_email_id == event.email_id)
                )
            ).first()
            if seen is not None:
                return "duplicate"
            session.add(
                InboundEmail(
                    id=uuid.uuid4(),
                    provider_event_id=event_id,
                    provider_email_id=event.email_id,
                    status="received",
                    attempts=0,
                    received_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError:
        return "duplicate"  # the same event, recorded by a concurrent delivery
    return "recorded"


# --- Processing ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Due:
    id: uuid.UUID
    provider_email_id: str
    attempts: int


def _claim_due(limit: int) -> list[_Due]:
    now = _now()
    with session_scope() as session:
        rows = (
            session.execute(
                select(InboundEmail)
                .where(
                    (
                        (InboundEmail.status == "received")
                        & (
                            InboundEmail.next_attempt_at.is_(None)
                            | (InboundEmail.next_attempt_at <= now)
                        )
                    )
                    | (
                        (InboundEmail.status == "processing")
                        & (InboundEmail.updated_at < now - STALE)
                    )
                )
                .order_by(InboundEmail.received_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        claimed = []
        for row in rows:
            row.status, row.attempts, row.updated_at = "processing", row.attempts + 1, now
            claimed.append(_Due(row.id, row.provider_email_id, row.attempts))
        return claimed


def _update(inbound_id: uuid.UUID, **values: Any) -> None:
    with session_scope() as session:
        row = session.get(InboundEmail, inbound_id, with_for_update=True)
        if row is None:
            return
        for name, value in values.items():
            setattr(row, name, value)
        row.updated_at = _now()


def _retry(due: _Due, code: str, retry_after: float | None = None) -> str:
    if due.attempts >= MAX_ATTEMPTS:
        _update(due.id, status="failed", last_error="attempts_exhausted", next_attempt_at=None)
        return "failed"
    delay = email_rules.retry_delay(due.attempts, retry_after, secrets.randbelow(10_000) / 10_000)
    _update(
        due.id,
        status="received",
        last_error=code,
        next_attempt_at=_now() + timedelta(seconds=delay),
    )
    return "waiting"


def production() -> bool:
    """Inbound email is not authorized in production (owner, 2026-11-01)."""
    return os.environ.get("ENVIRONMENT", "").strip().lower() == "production"


async def enqueue() -> bool:
    """Ask a worker to process due received emails; best effort, because the
    sweeper finds them anyway."""
    from saas_os.infra.jobs import enqueue_job  # noqa: PLC0415

    try:
        await enqueue_job(JOB_NAME)
    except Exception:  # noqa: BLE001 - the queue may be down; the sweeper covers it
        return False
    return True


def process_due(client: ReceivingClient | None = None, *, limit: int = BATCH) -> dict[str, int]:
    """Process the due received emails; returns how many ended in each
    state. Does nothing while inbound email is off, in production (not
    authorized), without a parent domain or without a receiving client."""
    parent = email_parent_domain()
    client = client or configured_client()
    if not inbound_enabled() or production() or parent is None or client is None:
        return {}
    counts: dict[str, int] = {}
    for due in _claim_due(limit):
        try:
            outcome = _process(due, client, parent)
        except Exception as exc:  # noqa: BLE001 - recorded by type; the row is retried
            outcome = _retry(due, f"error_{type(exc).__name__.lower()}"[:64])
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def _process(due: _Due, client: ReceivingClient, parent: str) -> str:  # noqa: PLR0911 - one answer per outcome
    try:
        answer = client.fetch(due.provider_email_id)
    except FetchError as exc:
        if not exc.transient:
            _update(due.id, status="failed", last_error=exc.code, next_attempt_at=None)
            return "failed"
        return _retry(due, exc.code, exc.retry_after)
    try:
        content = rules.received_content(answer)
    except rules.InboundRejected as exc:
        return _unmatched(due, exc.code, None)
    decision = rules.decide(content, parent)
    if decision.outcome != "route" or decision.token is None:
        return _unmatched(due, decision.reason or "unmatched", content.sender)
    with session_scope() as session:
        target = session.get(ConversationRouteIndex, rules.token_hash(decision.token))
        found = (target.workspace_id, target.conversation_id) if target else None
    if found is None:
        return _unmatched(due, "unknown_routing_address", content.sender)
    workspace, conversation_id = found
    outcome = _deliver(workspace, conversation_id, decision.token, due.id, content)
    if outcome == "gone":
        return _unmatched(due, "conversation_gone", content.sender)
    _update(
        due.id,
        status=outcome,
        workspace_id=workspace,
        reason=None,
        last_error=None,
        next_attempt_at=None,
    )
    return outcome


def _unmatched(due: _Due, reason: str, sender: str | None) -> str:
    domain = sender.rsplit("@", 1)[-1] if sender else None
    _update(
        due.id,
        status="unmatched",
        reason=reason,
        sender_domain=domain,
        last_error=None,
        next_attempt_at=None,
    )
    return "unmatched"


def _attachments(content: rules.ReceivedContent) -> list[dict[str, Any]]:
    return [
        {"filename": a.filename, "content_type": a.content_type, "size": a.size, "stored": False}
        for a in content.attachments
    ]


def _deliver(
    workspace: uuid.UUID,
    conversation_id: uuid.UUID,
    token: str,
    inbound_id: uuid.UUID,
    content: rules.ReceivedContent,
) -> str:
    """Inside the workspace: `routed`, `quarantined` or `gone`."""
    from saas_os.core.tenancy import lock_open_tenant  # noqa: PLC0415

    try:
        with tenant_session_scope(workspace) as session:
            lock_open_tenant(session, workspace)
            route = session.get(ConversationRoute, (workspace, conversation_id))
            if route is None or not hmac.compare_digest(route.token, token):
                return "gone"
            conversation = session.execute(
                select(Conversation)
                .where(Conversation.tenant_id == workspace, Conversation.id == conversation_id)
                .with_for_update()
            ).scalar_one_or_none()
            if conversation is None:
                return "gone"
            contact = (
                session.execute(
                    select(Contact).where(
                        Contact.tenant_id == workspace, Contact.id == conversation.contact_id
                    )
                ).scalar_one_or_none()
                if conversation.contact_id
                else None
            )
            reason = rules.review_reason(content, contact.email if contact else None)
            if reason is not None:
                if _quarantine(
                    session,
                    workspace,
                    conversation_id=conversation_id,
                    inbound_id=inbound_id,
                    content=content,
                    reason=reason,
                ):
                    _inbound_audit(
                        session, workspace, conversation_id, "inbound_quarantined", reason
                    )
                return "quarantined"
            if append(
                session,
                workspace,
                conversation=conversation,
                inbound_id=inbound_id,
                text=content.text,
                attachments=_attachments(content),
            ):
                _inbound_audit(session, workspace, conversation_id, "inbound_received", None)
            return "routed"
    except IntegrityError:
        # A concurrent try already delivered this email: same outcome once.
        return _already(workspace, inbound_id)


def _inbound_audit(
    session: Session,
    workspace: uuid.UUID,
    conversation_id: uuid.UUID,
    verb: str,
    reason: str | None,
) -> None:
    """The inbound processor changed the thread, not a member (K3.5). Codes
    only: never the sender, subject or text."""
    system_audit.record(
        session,
        workspace=workspace,
        component="crm_app.inbound_process",
        action=f"crm_app.conversation.{verb}",
        resource_type="crm_app.conversation",
        resource_id=str(conversation_id),
        metadata={"reason": reason} if reason is not None else None,
    )


def _already(workspace: uuid.UUID, inbound_id: uuid.UUID) -> str:
    with tenant_session_scope(workspace) as session:
        held = session.execute(
            select(InboundQuarantine.id).where(
                InboundQuarantine.tenant_id == workspace,
                InboundQuarantine.inbound_email_id == inbound_id,
            )
        ).first()
    return "quarantined" if held else "routed"


def _quarantine(  # noqa: PLR0913 - one quarantined email's parts
    session: Session,
    workspace: uuid.UUID,
    *,
    conversation_id: uuid.UUID,
    inbound_id: uuid.UUID,
    content: rules.ReceivedContent,
    reason: str,
) -> bool:
    """Hold an email for review, at most once per email; returns whether
    it was held now."""
    exists = session.execute(
        select(InboundQuarantine.id).where(
            InboundQuarantine.tenant_id == workspace,
            InboundQuarantine.inbound_email_id == inbound_id,
        )
    ).first()
    if exists:
        return False
    session.add(
        InboundQuarantine(
            id=uuid.uuid4(),
            tenant_id=workspace,
            inbound_email_id=inbound_id,
            conversation_id=conversation_id,
            reason=reason,
            sender=content.sender[:320],
            subject=content.subject,
            body=content.text,
            truncated=content.truncated,
            attachments=_attachments(content),
            status="pending",
            created_at=_now(),
            version=1,
        )
    )
    session.flush()
    return True


def append(  # noqa: PLR0913 - one inbound message's parts
    session: Session,
    workspace: uuid.UUID,
    *,
    conversation: Conversation,
    inbound_id: uuid.UUID,
    text: str,
    attachments: list[dict[str, Any]],
) -> bool:
    """Add an inbound message from the contact, at most once per email;
    returns whether one was added. Reopens the thread."""
    exists = session.execute(
        select(ConversationMessage.id).where(
            ConversationMessage.tenant_id == workspace,
            ConversationMessage.inbound_email_id == inbound_id,
        )
    ).first()
    if exists:
        return False
    now = _now()
    session.add(
        ConversationMessage(
            id=uuid.uuid4(),
            tenant_id=workspace,
            conversation_id=conversation.id,
            kind="inbound",
            body=text or "(no text)",
            author_user_id=None,
            email_message_id=None,
            inbound_email_id=inbound_id,
            attachments=attachments or None,
            created_at=now,
        )
    )
    conversation.status = "open"
    conversation.last_message_at, conversation.updated_at = now, now
    conversation.version += 1
    session.flush()
    return True


# --- Review (quarantine) -------------------------------------------------------------------


class AlreadyDecidedError(RecordError):
    """A quarantined email was already accepted or discarded."""

    status, code = 409, "already_decided"


class ConversationGoneError(RecordError):
    """The quarantined email's conversation was deleted."""

    status, code = 409, "conversation_gone"


def _review_item(row: InboundQuarantine) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "reason": row.reason,
        "sender": row.sender,
        "subject": row.subject,
        "body": row.body,
        "truncated": row.truncated,
        "attachments": row.attachments,
        "status": row.status,
        "created_at": row.created_at,
        "version": row.version,
    }


def list_reviews(
    scope: Scope, *, status: str = "pending", limit: int = 100
) -> list[dict[str, Any]]:
    """The workspace's quarantined emails, newest first."""
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(InboundQuarantine)
            .where(
                InboundQuarantine.tenant_id == scope.workspace, InboundQuarantine.status == status
            )
            .order_by(InboundQuarantine.created_at.desc(), InboundQuarantine.id.desc())
            .limit(limit)
        ).scalars()
        return [_review_item(row) for row in rows]


def decide_review(
    scope: Scope, review_id: uuid.UUID, *, accept: bool, expected_version: int
) -> dict[str, Any]:
    """Accept a quarantined email into its conversation, or discard it.
    Audited with ids and the reason code only."""
    from saas_os.core.audit_log import record_in_transaction  # noqa: PLC0415
    from saas_os.core.authority import UserCaller  # noqa: PLC0415
    from saas_os.core.tenancy import lock_open_tenant  # noqa: PLC0415

    with tenant_session_scope(scope.workspace) as session:
        lock_open_tenant(session, scope.workspace)
        row = session.execute(
            select(InboundQuarantine)
            .where(
                InboundQuarantine.tenant_id == scope.workspace, InboundQuarantine.id == review_id
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise RecordNotFoundError
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if row.status != "pending":
            raise AlreadyDecidedError
        if accept:
            conversation = (
                session.execute(
                    select(Conversation)
                    .where(
                        Conversation.tenant_id == scope.workspace,
                        Conversation.id == row.conversation_id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if row.conversation_id
                else None
            )
            if conversation is None:
                raise ConversationGoneError
            append(
                session,
                scope.workspace,
                conversation=conversation,
                inbound_id=row.inbound_email_id,
                text=row.body,
                attachments=row.attachments,
            )
        row.status = "accepted" if accept else "discarded"
        row.decided_by_user_id, row.decided_at = scope.actor, _now()
        row.version += 1
        record_in_transaction(
            session,
            caller=UserCaller(scope.actor),
            tenant_id=scope.workspace,
            action=f"crm_app.conversation.review_{row.status}",
            resource_type="crm_app.conversation",
            resource_id=str(row.conversation_id or row.id),
            metadata={"review_id": str(row.id), "reason": row.reason},
        )
        session.flush()
        return _review_item(row)


# --- Routes ------------------------------------------------------------------------------------


def ensure_route(session: Session, workspace: uuid.UUID, conversation_id: uuid.UUID) -> str:
    """The conversation's routing token, created once. The global index row
    is written first in its own transaction; if the caller's transaction
    rolls back, the orphan leads nowhere, because delivery checks the
    workspace's own row."""
    route = session.get(ConversationRoute, (workspace, conversation_id))
    if route is not None:
        return route.token
    token = rules.new_token()
    with session_scope() as global_session:
        global_session.add(
            ConversationRouteIndex(
                token_hash=rules.token_hash(token),
                workspace_id=workspace,
                conversation_id=conversation_id,
            )
        )
    session.add(
        ConversationRoute(
            tenant_id=workspace, conversation_id=conversation_id, token=token, created_at=_now()
        )
    )
    session.flush()
    return token


def route_token_for_email(
    session: Session, workspace: uuid.UUID, email_id: uuid.UUID
) -> str | None:
    """The routing token of the conversation an email reply belongs to."""
    row = session.execute(
        select(ConversationRoute.token)
        .join(
            ConversationMessage,
            (ConversationMessage.tenant_id == ConversationRoute.tenant_id)
            & (ConversationMessage.conversation_id == ConversationRoute.conversation_id),
        )
        .where(
            ConversationRoute.tenant_id == workspace,
            ConversationMessage.email_message_id == email_id,
        )
    ).first()
    return None if row is None else str(row[0])


# --- Purge -------------------------------------------------------------------------------------


def forget_workspace(tenant_id: uuid.UUID) -> None:
    """Remove a purged workspace's rows from the global inbound tables."""
    from saas_os.infra.db import delete  # noqa: PLC0415

    with session_scope() as session:
        session.execute(
            delete(ConversationRouteIndex).where(ConversationRouteIndex.workspace_id == tenant_id)
        )
        session.execute(delete(InboundEmail).where(InboundEmail.workspace_id == tenant_id))


def remaining_for_workspace(tenant_id: uuid.UUID) -> bool:
    with session_scope() as session:
        index = session.execute(
            select(ConversationRouteIndex.token_hash)
            .where(ConversationRouteIndex.workspace_id == tenant_id)
            .limit(1)
        ).first()
        inbound = session.execute(
            select(InboundEmail.id).where(InboundEmail.workspace_id == tenant_id).limit(1)
        ).first()
    return index is not None or inbound is not None
