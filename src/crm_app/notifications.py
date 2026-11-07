"""In-app notifications for members (decision N-1).

A notification tells one member that something happened to them: someone
else assigned them a task, a conversation or an appointment, a visitor
booked or cancelled on one of their booking pages, or an appointment they
host starts soon (`crm_app.member_reminders`, decision N-2), or an
automation step tells them about a contact (`notify_member`, decision P8-N).
Rows live in
`crm_app.member_notification` (forced RLS) and are written by `notify()`
inside the same transaction as the change they describe, so a rolled-back
change notifies nobody and an idempotent replay (which skips the business
function) notifies nobody twice.

- Nobody is notified about their own action.
- A member reads and marks only their own notifications; the recipient is
  always the signed-in member from the validated request context.
- A row names its record by type and ID only. The list reads the record's
  current name, and only when the reader may read that kind of record; a
  deleted record shows as unavailable. No record content is copied, so
  nothing personal outlives the record here. The one text a row may carry
  is an automation's `note`: the fixed message its author wrote in the
  definition, never filled in from the record.
- Rows older than `RETENTION` are deleted for a recipient whenever a new one
  is written for them, so the table stays bounded without a scheduled job.

SaaS-OS's `in_app` channel (`saas_os.core.notifications`) is not used: in
v0.8.0 it stores only text, has no read state and lists every row unpaged
(decision N-1). It remains the path for notification email once sending is
authorised.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.rbac import can
from saas_os.infra.db import Session, delete, now, select, tenant_session_scope, update

from crm_app.domains import paging
from crm_app.models import Appointment, Contact, Conversation, MemberNotification, Task
from crm_app.records import Scope, _after, _OrderKey

KINDS: Mapping[str, str] = {
    "task_assigned": "task",
    "conversation_assigned": "conversation",
    "appointment_assigned": "appointment",
    "booking_received": "appointment",
    "booking_cancelled": "appointment",
    # The host's appointment starts soon (N-2); no member acted.
    "appointment_upcoming": "appointment",
    # An automation step about the run's contact, with its note (P8-N).
    "automation_notice": "contact",
}
# Kinds that carry the automation author's note; no other kind has one.
NOTE_KINDS = frozenset({"automation_notice"})
RETENTION = timedelta(days=90)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
# The unread badge stops counting here ("99+").
UNREAD_CAP = 99

# The record each subject type names, the columns of its label (joined with
# spaces, empty parts left out) and the permission that lets the reader see
# that label.
_SUBJECTS: Mapping[str, tuple[Any, tuple[Any, ...], str]] = {
    "task": (Task, (Task.title,), "crm_app.task"),
    "conversation": (Conversation, (Conversation.subject,), "crm_app.conversation"),
    "appointment": (Appointment, (Appointment.title,), "crm_app.appointment"),
    "contact": (Contact, (Contact.first_name, Contact.last_name), "crm_app.contact"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def acting(scope: Scope) -> uuid.UUID | None:
    """The member who acted in `scope`: none when a system component (an
    automation run, a public page) acted in that member's scope."""
    return None if scope.component else scope.actor


def notify(  # noqa: PLR0913 - who, what, which record and who acted
    session: Session,
    workspace: uuid.UUID,
    recipient: uuid.UUID | None,
    kind: str,
    subject_id: uuid.UUID,
    *,
    actor: uuid.UUID | None,
    note: str | None = None,
) -> bool:
    """Record one notification in the caller's transaction (`session` is
    the caller's tenant session for `workspace`). `actor` is the member who
    acted, or None for a visitor or an automation. `note` is required for
    the kinds in `NOTE_KINDS` and refused for every other. Returns whether a
    row was written: never for no recipient or for the actor themselves."""
    if (kind in NOTE_KINDS) != (note is not None):
        raise ValueError(f"{kind}: a note exactly when the kind carries one")
    if recipient is None or recipient == actor:
        return False
    subject_type = KINDS[kind]
    session.execute(
        delete(MemberNotification).where(
            MemberNotification.tenant_id == workspace,
            MemberNotification.user_id == recipient,
            MemberNotification.created_at < _now() - RETENTION,
        )
    )
    session.add(
        MemberNotification(
            tenant_id=workspace,
            id=uuid.uuid4(),
            user_id=recipient,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            actor_user_id=actor,
            # The database's clock for both times, so `read_at >= created_at`
            # holds whatever the application servers' clocks say.
            created_at=now(),
            read_at=None,
            note=note,
        )
    )
    return True


@dataclass(frozen=True)
class Page:
    items: list[dict[str, Any]]
    next_cursor: str | None
    unread: int
    unread_capped: bool


_ORDER = "created_at"
_KEYS = [
    _OrderKey(MemberNotification.created_at, MemberNotification.created_at, "created_at"),
    _OrderKey(MemberNotification.id, MemberNotification.id, "id"),
]


def _labels(
    session: Session, workspace: uuid.UUID, reader: uuid.UUID, rows: list[MemberNotification]
) -> dict[tuple[str, uuid.UUID], str]:
    """The current names of the records `rows` name, for the kinds of record
    `reader` may read."""
    wanted: dict[str, set[uuid.UUID]] = {}
    for row in rows:
        wanted.setdefault(row.subject_type, set()).add(row.subject_id)
    labels: dict[tuple[str, uuid.UUID], str] = {}
    for subject_type, ids in wanted.items():
        model, columns, resource = _SUBJECTS[subject_type]
        if not can(actor_id=reader, tenant_id=workspace, action="read", resource=resource):
            continue
        found = session.execute(
            select(model.id, *columns).where(model.tenant_id == workspace, model.id.in_(ids))
        )
        for record_id, *parts in found.tuples():
            labels[(subject_type, record_id)] = " ".join(str(p) for p in parts if p)
    return labels


def list_own(
    workspace: uuid.UUID,
    reader: uuid.UUID,
    *,
    unread_only: bool = False,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page:
    """The reader's notifications, newest first, and their unread count.
    Raises `paging.InvalidCursor` for a cursor issued for other filters."""
    filters = paging.filter_hash({"unread": unread_only})
    after = paging.decode(cursor, "notification", _ORDER, "desc", filters) if cursor else None
    conditions: list[Any] = [
        MemberNotification.tenant_id == workspace,
        MemberNotification.user_id == reader,
    ]
    with tenant_session_scope(workspace) as session:
        unread = len(
            session.execute(
                select(MemberNotification.id)
                .where(*conditions, MemberNotification.read_at.is_(None))
                .limit(UNREAD_CAP + 1)
            ).all()
        )
        if unread_only:
            conditions.append(MemberNotification.read_at.is_(None))
        statement = select(MemberNotification).where(*conditions)
        if after is not None:
            statement = statement.where(_after(_KEYS, after, ascending=False))
        rows = list(
            session.execute(
                statement.order_by(
                    MemberNotification.created_at.desc(), MemberNotification.id.desc()
                ).limit(limit + 1)
            ).scalars()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        labels = _labels(session, workspace, reader, rows)
        items = [
            {
                "id": row.id,
                "kind": row.kind,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "subject_label": labels.get((row.subject_type, row.subject_id)),
                "actor_user_id": row.actor_user_id,
                "note": row.note,
                "created_at": row.created_at,
                "read_at": row.read_at,
            }
            for row in rows
        ]
        last = (rows[-1].created_at, rows[-1].id) if rows else None
    next_cursor = None
    if more and last is not None:
        next_cursor = paging.encode("notification", _ORDER, "desc", filters, last)
    return Page(
        items=items,
        next_cursor=next_cursor,
        unread=min(unread, UNREAD_CAP),
        unread_capped=unread > UNREAD_CAP,
    )


def mark_read(workspace: uuid.UUID, reader: uuid.UUID, notification_id: uuid.UUID) -> bool:
    """Mark one of the reader's notifications read. Returns False when the
    reader has no such notification (another member's is the same as an
    unknown one). Marking a read one again changes nothing."""
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            select(MemberNotification)
            .where(
                MemberNotification.tenant_id == workspace,
                MemberNotification.user_id == reader,
                MemberNotification.id == notification_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return False
        if row.read_at is None:
            row.read_at = now()
    return True


def mark_all_read(workspace: uuid.UUID, reader: uuid.UUID) -> int:
    """Mark every unread notification of the reader read; returns how many."""
    with tenant_session_scope(workspace) as session:
        result = session.execute(
            update(MemberNotification)
            .where(
                MemberNotification.tenant_id == workspace,
                MemberNotification.user_id == reader,
                MemberNotification.read_at.is_(None),
            )
            .values(read_at=now())
        )
        return int(getattr(result, "rowcount", 0) or 0)
