"""Conversations (decision P6-C): threads with a contact and their messages.

Provider-neutral. A thread is on the `email` channel or `other` (messages
logged by hand). A message is `inbound` (logged by a member: no provider
delivers inbound mail yet), `outbound` or a `note` seen only by members.
An outbound message on an email thread queues one email through
`crm_app.emails` (purpose `conversation_reply`) and points at it; that
email's status is the message's delivery state, and it stays `queued`,
shown as not sent, while `EMAIL_SENDING_ENABLED` is off. Nothing here
knows the provider.

Every member reads (`crm_app.conversation:read`); Owners, Admins and
Members reply, log messages, add notes, assign and close
(`crm_app.conversation:reply`). Unread means a message by someone else
after the member last opened the thread. Audit entries name ids, kinds and
field names, never message text.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.idempotency import run_idempotent
from saas_os.core.identity import get_membership
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    OperationalError,
    Session,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app import emails, inbound
from crm_app.domains import conversations as rules
from crm_app.domains import paging
from crm_app.domains.records import InvalidValue, visible_text
from crm_app.models import (
    Contact,
    Conversation,
    ConversationMessage,
    ConversationRead,
    EmailMessage,
)
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.conversation"
CHANNELS = ("email", "other")
KINDS = ("inbound", "outbound", "note")
SUBJECT_MAX = 200
BODY_MAX = 20_000
LIST_LIMIT = 100
PAGE_DEFAULT = 50
SEARCH_MAX = rules.SEARCH_MAX
ORDER = "last_message_at"
# `tsvector @@ varchar`, inlined to `@@ to_tsquery('simple', ...)` (migration 0023).
_MATCHES = "OPERATOR(crm_app.@@)"
THREAD_LIMIT = 500

Item = dict[str, Any]


class ConversationRuleError(RecordError):
    """A value or step the rules refuse; `detail` names the rule."""

    status, code = 422, "invalid_conversation"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class NoEmailAddressError(RecordError):
    """An email reply needs the contact's email address."""

    status, code = 409, "contact_has_no_email"


def _now() -> datetime:
    return datetime.now(UTC)


def _subject(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= SUBJECT_MAX or not visible_text(text):
        raise ConversationRuleError(f"subject: 1 to {SUBJECT_MAX} visible characters")
    return text


def _body(value: str) -> str:
    text = value.replace("\r\n", "\n").strip()
    if not 1 <= len(text) <= BODY_MAX:
        raise ConversationRuleError(f"body: 1 to {BODY_MAX} characters")
    if any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in text):
        raise ConversationRuleError("body: no control characters")
    return text


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


Outcome = dict[str, str | None]


def _once(
    scope: Scope,
    operation: str,
    key: str | None,
    fingerprint: dict[str, object],
    business: Callable[[Session], Outcome],
) -> tuple[Outcome, bool]:
    """Run `business` in one transaction; with a key, at most once per key
    for the acting member, so a retried reply never queues a second email.
    Returns the outcome and whether it was a replay."""
    if key is None:
        return _transaction(scope, business), False

    def locked(session: Session) -> Outcome:
        lock_open_tenant(session, scope.workspace)
        return business(session)

    try:
        replay, result = run_idempotent(
            scope.workspace, f"{RESOURCE}.{operation}:{scope.actor}", key, fingerprint, locked
        )
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise
    return {k: None if v is None else str(v) for k, v in result.items()}, replay


def _uuid(value: str | None) -> uuid.UUID | None:
    return None if value is None else uuid.UUID(value)


def _audit(
    session: Session, scope: Scope, verb: str, conversation_id: uuid.UUID, **meta: Any
) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(conversation_id),
        metadata=meta,
    )


def _load(
    session: Session, scope: Scope, conversation_id: uuid.UUID, *, lock: bool
) -> Conversation:
    query = select(Conversation).where(
        Conversation.tenant_id == scope.workspace, Conversation.id == conversation_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _contact_of(session: Session, scope: Scope, contact_id: uuid.UUID | None) -> Contact | None:
    if contact_id is None:
        return None
    return session.execute(
        select(Contact).where(Contact.tenant_id == scope.workspace, Contact.id == contact_id)
    ).scalar_one_or_none()


def _name(contact: Contact | None) -> str | None:
    if contact is None:
        return None
    return " ".join(part for part in (contact.first_name, contact.last_name) if part)


def _mark_read(session: Session, scope: Scope, conversation_id: uuid.UUID, at: datetime) -> None:
    row = session.get(ConversationRead, (scope.workspace, conversation_id, scope.actor))
    if row is None:
        session.add(
            ConversationRead(
                tenant_id=scope.workspace,
                conversation_id=conversation_id,
                user_id=scope.actor,
                read_at=at,
            )
        )
    elif row.read_at < at:
        row.read_at = at


def _queue_reply(
    session: Session, scope: Scope, conversation: Conversation, text: str
) -> uuid.UUID:
    contact = _contact_of(session, scope, conversation.contact_id)
    if contact is None or not contact.email:
        raise NoEmailAddressError
    # The address replies come back to (decision P6-I); used once inbound is on.
    inbound.ensure_route(session, scope.workspace, conversation.id)
    try:
        return emails.queue(
            session,
            scope,
            purpose="conversation_reply",
            to_email=contact.email,
            subject=conversation.subject,
            text_body=text,
            contact_id=contact.id,
        )
    except InvalidValue as exc:
        raise ConversationRuleError(str(exc)) from None


def _add(
    session: Session, scope: Scope, conversation: Conversation, kind: str, body: str
) -> uuid.UUID | None:
    """One message in the caller's transaction; returns the email an email
    reply queued, if any."""
    if kind not in KINDS:
        raise ConversationRuleError(f"kind: one of {', '.join(KINDS)}")
    if kind == "outbound" and conversation.channel != "email":
        raise ConversationRuleError("outbound: only on an email thread")
    text = _body(body)
    email_id = _queue_reply(session, scope, conversation, text) if kind == "outbound" else None
    now = _now()
    message_id = uuid.uuid4()
    session.add(
        ConversationMessage(
            id=message_id,
            tenant_id=scope.workspace,
            conversation_id=conversation.id,
            kind=kind,
            body=text,
            author_user_id=scope.actor,
            email_message_id=email_id,
            created_at=now,
        )
    )
    if kind != "note":
        conversation.status = "open"
    conversation.last_message_at, conversation.updated_at = now, now
    conversation.version += 1
    session.flush()
    _mark_read(session, scope, conversation.id, now)
    _audit(session, scope, "message_added", conversation.id, kind=kind, message_id=str(message_id))
    return email_id


# --- Reads ---------------------------------------------------------------------------------


def _summary(row: Conversation, contact_name: str | None, unread: bool) -> Item:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "contact_name": contact_name,
        "channel": row.channel,
        "subject": row.subject,
        "status": row.status,
        "assignee_user_id": row.assignee_user_id,
        "last_message_at": row.last_message_at,
        "unread": unread,
        "created_at": row.created_at,
        "version": row.version,
    }


def _unread(
    session: Session, scope: Scope, read: dict[uuid.UUID, datetime | None]
) -> set[uuid.UUID]:
    """The threads with a message by someone else since the caller read them."""
    if not read:
        return set()
    rows = session.execute(
        select(ConversationMessage.conversation_id, ConversationMessage.created_at).where(
            ConversationMessage.tenant_id == scope.workspace,
            ConversationMessage.conversation_id.in_(list(read)),
            ConversationMessage.kind != "note",
            (ConversationMessage.author_user_id.is_(None))
            | (ConversationMessage.author_user_id != scope.actor),
        )
    ).all()
    found: set[uuid.UUID] = set()
    for conversation_id, created_at in rows:
        seen = read.get(conversation_id)
        if seen is None or created_at > seen:
            found.add(conversation_id)
    return found


def _matching(scope: Scope, q: str) -> Any:
    r"""Threads whose subject or any message has every word as a prefix, or
    whose contact's first name, last name or email starts with the whole
    search (taken literally: `%`, `_` and `\` match themselves)."""
    lowered = q.lower()
    contact = Conversation.contact_id.in_(
        select(Contact.id).where(
            Contact.tenant_id == scope.workspace,
            Contact.first_name.istartswith(q, autoescape=True)
            | Contact.last_name.istartswith(q, autoescape=True)
            | Contact.email.startswith(lowered, autoescape=True),
        )
    )
    terms = rules.search_terms(q)
    if not terms:
        return contact
    query = rules.prefix_query(terms)
    words = Conversation.search_vector.op(_MATCHES, is_comparison=True)(query)
    messages = Conversation.id.in_(
        select(ConversationMessage.conversation_id).where(
            ConversationMessage.tenant_id == scope.workspace,
            ConversationMessage.search_vector.op(_MATCHES, is_comparison=True)(query),
        )
    )
    return words | messages | contact


@dataclass(frozen=True)
class InboxQuery:
    """What the Inbox list asks for. `status`: `open`, `closed` or `all`;
    `assigned`: `all`, `mine` or `unassigned`. With `contact_id`, that
    contact's threads of every status. `q` searches subjects, message text
    (notes included: every reader of a thread sees them) and contact names."""

    status: str = "open"
    assigned: str = "all"
    contact_id: uuid.UUID | None = None
    q: str = ""
    limit: int = PAGE_DEFAULT
    cursor: str | None = None


def list_conversations(scope: Scope, inbox: InboxQuery | None = None) -> Item:
    """One page of threads, latest message first, with unread state for the
    caller and the cursor of the next page (or None). Raises
    `paging.InvalidCursor` for a cursor issued for other filters."""
    inbox = inbox or InboxQuery()
    status, assigned, contact_id = inbox.status, inbox.assigned, inbox.contact_id
    limit, cursor = inbox.limit, inbox.cursor
    q = inbox.q.strip()
    filters = paging.filter_hash(
        {
            "status": status,
            "assigned": assigned,
            "contact": str(contact_id or ""),
            "q": q,
        }
    )
    after = paging.decode(cursor, "conversation", ORDER, "desc", filters) if cursor else None
    with tenant_session_scope(scope.workspace) as session:
        query = (
            select(Conversation, ConversationRead.read_at)
            .outerjoin(
                ConversationRead,
                (ConversationRead.tenant_id == Conversation.tenant_id)
                & (ConversationRead.conversation_id == Conversation.id)
                & (ConversationRead.user_id == scope.actor),
            )
            .where(Conversation.tenant_id == scope.workspace)
        )
        if contact_id is not None:
            query = query.where(Conversation.contact_id == contact_id)
        elif status != "all":
            query = query.where(Conversation.status == status)
        if assigned == "mine":
            query = query.where(Conversation.assignee_user_id == scope.actor)
        elif assigned == "unassigned":
            query = query.where(Conversation.assignee_user_id.is_(None))
        if q:
            query = query.where(_matching(scope, q))
        if after is not None:
            at, last_id = after
            query = query.where(
                (Conversation.last_message_at < at)
                | ((Conversation.last_message_at == at) & (Conversation.id < last_id))
            )
        rows = session.execute(
            query.order_by(Conversation.last_message_at.desc(), Conversation.id.desc()).limit(
                limit + 1
            )
        ).all()
        more = len(rows) > limit
        rows = rows[:limit]
        contact_ids = {row.contact_id for row, _ in rows if row.contact_id}
        names: dict[uuid.UUID, str | None] = {}
        if contact_ids:
            for contact in session.execute(
                select(Contact).where(
                    Contact.tenant_id == scope.workspace, Contact.id.in_(contact_ids)
                )
            ).scalars():
                names[contact.id] = _name(contact)
        unread = _unread(session, scope, {row.id: read_at for row, read_at in rows})
        items = [
            _summary(row, names.get(row.contact_id) if row.contact_id else None, row.id in unread)
            for row, _ in rows
        ]
        last = (rows[-1][0].last_message_at, rows[-1][0].id) if rows else None
    next_cursor = (
        paging.encode("conversation", ORDER, "desc", filters, last) if more and last else None
    )
    return {"items": items, "next_cursor": next_cursor}


def get(scope: Scope, conversation_id: uuid.UUID) -> Item:
    """A thread with its messages, oldest first, and each email's state."""
    with tenant_session_scope(scope.workspace) as session:
        row = _load(session, scope, conversation_id, lock=False)
        contact = _contact_of(session, scope, row.contact_id)
        messages = session.execute(
            select(ConversationMessage, EmailMessage.status)
            .outerjoin(
                EmailMessage,
                (EmailMessage.tenant_id == ConversationMessage.tenant_id)
                & (EmailMessage.id == ConversationMessage.email_message_id),
            )
            .where(
                ConversationMessage.tenant_id == scope.workspace,
                ConversationMessage.conversation_id == conversation_id,
            )
            .order_by(ConversationMessage.created_at, ConversationMessage.id)
            .limit(THREAD_LIMIT)
        ).all()
        return {
            **_summary(row, _name(contact), False),
            "contact_email": contact.email if contact else None,
            "messages": [
                {
                    "id": message.id,
                    "kind": message.kind,
                    "body": message.body,
                    "author_user_id": message.author_user_id,
                    "created_at": message.created_at,
                    "delivery": status,
                    "attachments": message.attachments,
                }
                for message, status in messages
            ],
        }


# --- Changes --------------------------------------------------------------------------------


def create(  # noqa: PLR0913 - the thread, then its first message
    scope: Scope,
    *,
    contact_id: uuid.UUID,
    channel: str,
    subject: str,
    kind: str,
    body: str,
    idempotency_key: str | None = None,
) -> tuple[Item, uuid.UUID | None, bool]:
    """A new thread with its first message; returns it, the email it queued,
    if any (to enqueue after the commit), and whether this was a replay."""
    if channel not in CHANNELS:
        raise ConversationRuleError(f"channel: one of {', '.join(CHANNELS)}")
    clean_subject = _subject(subject)
    conversation_id = uuid.uuid4()

    def apply(session: Session) -> Outcome:
        if _contact_of(session, scope, contact_id) is None:
            raise ConversationRuleError("contact: not found")
        now = _now()
        row = Conversation(
            id=conversation_id,
            tenant_id=scope.workspace,
            contact_id=contact_id,
            channel=channel,
            subject=clean_subject,
            status="open",
            assignee_user_id=None,
            last_message_at=now,
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", conversation_id, channel=channel)
        email_id = _add(session, scope, row, kind, body)
        return {"id": str(conversation_id), "email": None if email_id is None else str(email_id)}

    fingerprint: dict[str, object] = {
        "contact_id": str(contact_id),
        "channel": channel,
        "subject": clean_subject,
        "kind": kind,
        "body": body,
    }
    result, replay = _once(scope, "create", idempotency_key, fingerprint, apply)
    return get(scope, uuid.UUID(str(result["id"]))), _uuid(result["email"]), replay


def add_message(
    scope: Scope,
    conversation_id: uuid.UUID,
    *,
    kind: str,
    body: str,
    idempotency_key: str | None = None,
) -> tuple[Item, uuid.UUID | None, bool]:
    """Reply, log an inbound message or add a note; returns the thread, the
    email queued, if any, and whether this was a replay."""

    def apply(session: Session) -> Outcome:
        row = _load(session, scope, conversation_id, lock=True)
        email_id = _add(session, scope, row, kind, body)
        return {"email": None if email_id is None else str(email_id)}

    fingerprint: dict[str, object] = {
        "conversation_id": str(conversation_id),
        "kind": kind,
        "body": body,
    }
    result, replay = _once(scope, "message", idempotency_key, fingerprint, apply)
    return get(scope, conversation_id), _uuid(result["email"]), replay


def _active_member(workspace: uuid.UUID, user_id: uuid.UUID) -> bool:
    membership = get_membership(workspace, user_id)
    return membership is not None and membership.status == "active"


def update(
    scope: Scope,
    conversation_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    expected_version: int,
) -> Item:
    """Assign (or unassign) and close or reopen."""
    if "status" in changes and changes["status"] not in ("open", "closed"):
        raise ConversationRuleError("status: open or closed")
    assignee = changes.get("assignee_user_id")
    if assignee is not None and not _active_member(scope.workspace, assignee):
        raise ConversationRuleError("assignee: an active member")

    def apply(session: Session) -> None:
        row = _load(session, scope, conversation_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        changed = sorted(k for k, v in changes.items() if getattr(row, k) != v)
        if not changed:
            return
        for name in changed:
            setattr(row, name, changes[name])
        row.updated_at = _now()
        row.version += 1
        session.flush()
        verb = "updated"
        if changed == ["status"]:
            verb = "closed" if changes["status"] == "closed" else "reopened"
        _audit(session, scope, verb, conversation_id, fields=changed)

    _transaction(scope, apply)
    return get(scope, conversation_id)


def mark_read(scope: Scope, conversation_id: uuid.UUID) -> None:
    def apply(session: Session) -> None:
        _load(session, scope, conversation_id, lock=False)
        _mark_read(session, scope, conversation_id, _now())

    _transaction(scope, apply)
