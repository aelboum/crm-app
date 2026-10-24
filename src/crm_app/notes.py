"""Notes on contacts and companies (`PHASE3-PLAN.md` §21.2, decision P3-B).

Plain text only (`crm_app.domains.records.note_body`); the API renders it
as JSON text and the frontend as text, never HTML.

Who may do what (D3, the Q6 amendment): every role reads; Owner, Admin and
Member add notes (`crm_app.activity:create`); a note's author may edit and
delete it while they hold `activity:create`; holders of `activity:update`
or `activity:delete` (Owner, Admin) may edit or delete any note. The routes
declare `activity:create` and pass the caller's broader rights in
`NoteRights`; this module applies the author rule, so both always agree.

On an archived record notes stay readable; adding or editing one is
refused with `record_archived` until the record is restored; deleting
follows the rule above (D8).

Every change runs in one locked, workspace-scoped transaction with its
history entry (`note_added`, `note_deleted`) and its audit entry
(`crm_app.note.created`/`.updated`/`.deleted`). Neither ever holds the note
text: the audit metadata names the record only, and a deleted note's text
is gone with its row and its `note_added` entry (D4). Adding a note never
changes its record's version.

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
from saas_os.core.idempotency import run_idempotent
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

from crm_app.domains import paging
from crm_app.models import Note
from crm_app.records import (
    COMPANY,
    CONTACT,
    ConstraintViolationError,
    Kind,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    history_entry,
    load_record,
)

RESOURCE = "crm_app.note"
ORDER, DIRECTION = "created_at", "desc"


class NoteNotFoundError(RecordError):
    status, code = 404, "note_not_found"


class RecordArchivedError(RecordError):
    """Adding or editing a note on an archived record (D8)."""

    status, code = 409, "record_archived"


class NotNoteAuthorError(RecordError):
    """Editing or deleting another member's note without the right (D3)."""

    status, code = 403, "not_note_author"


@dataclass(frozen=True)
class NoteRights:
    """The caller's rights beyond the route's `activity:create`, read with
    SaaS-OS `can()` by the API for this request."""

    edit_any: bool = False
    delete_any: bool = False


@dataclass(frozen=True)
class PageRequest:
    limit: int
    cursor: str | None = None


@dataclass(frozen=True)
class NotePage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    archived: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _kind_of(note: Note) -> tuple[Kind, uuid.UUID]:
    if note.contact_id is not None:
        return CONTACT, note.contact_id
    if note.company_id is not None:
        return COMPANY, note.company_id
    raise ConstraintViolationError  # unreachable: the table's one-parent CHECK


def _may_edit(note: Note, scope: Scope, rights: NoteRights) -> bool:
    return note.author_user_id == scope.actor or rights.edit_any


def _may_delete(note: Note, scope: Scope, rights: NoteRights) -> bool:
    return note.author_user_id == scope.actor or rights.delete_any


def _out(note: Note, scope: Scope, rights: NoteRights | None, *, archived: bool) -> dict[str, Any]:
    """A note as the API returns it. `rights` is `None` for a caller who may
    not add notes at all (Read-only): such a caller may change none."""
    return {
        "id": note.id,
        "contact_id": note.contact_id,
        "company_id": note.company_id,
        "body": note.body,
        "author_user_id": note.author_user_id,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "updated_by_user_id": note.updated_by_user_id,
        "edited": note.version > 1,
        "version": note.version,
        "can_edit": rights is not None and not archived and _may_edit(note, scope, rights),
        "can_delete": rights is not None and _may_delete(note, scope, rights),
    }


def _audit(session: Session, scope: Scope, verb: str, note: Note) -> None:
    kind, record_id = _kind_of(note)
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(note.id),
        metadata={"record_type": kind.name, "record_id": str(record_id)},
    )


def _write[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    """Run `fn` in one locked, workspace-scoped transaction. A database
    refusal never surfaces as the driver error, whose detail would quote the
    note (personal data) in the server log."""
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


def _load_note(session: Session, scope: Scope, note_id: uuid.UUID, *, lock: bool = False) -> Note:
    query = select(Note).where(Note.tenant_id == scope.workspace, Note.id == note_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise NoteNotFoundError
    return row


def _lock_note(session: Session, scope: Scope, note_id: uuid.UUID) -> tuple[Note, bool]:
    """The note, locked, and whether its record is archived. Locks the record
    first and then the note, the order every record change and its cascade
    take, so a note change never deadlocks with a record change; the record
    stays locked until commit, so it cannot be archived meanwhile (D8)."""
    kind, record_id = _kind_of(_load_note(session, scope, note_id))
    archived = load_record(session, kind, scope, record_id, lock=True).archived_at is not None
    return _load_note(session, scope, note_id, lock=True), archived


def _parent_archived(session: Session, scope: Scope, note: Note) -> bool:
    kind, record_id = _kind_of(note)
    return load_record(session, kind, scope, record_id).archived_at is not None


# --- Reads -----------------------------------------------------------------------


def list_notes(
    kind: Kind,
    scope: Scope,
    record_id: uuid.UUID,
    page: PageRequest,
    rights: NoteRights | None,
) -> NotePage:
    """Newest first, in a total order (`id` breaks ties). Raises
    `paging.InvalidCursor` for a cursor issued for another record."""
    filters = paging.filter_hash({"record": f"{kind.name}:{record_id}"})
    limit = page.limit
    after = paging.decode(page.cursor, "note", ORDER, DIRECTION, filters) if page.cursor else None
    parent = Note.contact_id if kind is CONTACT else Note.company_id
    with tenant_session_scope(scope.workspace) as session:
        archived = load_record(session, kind, scope, record_id).archived_at is not None
        statement = select(Note).where(Note.tenant_id == scope.workspace, parent == record_id)
        if after is not None:
            created, last_id = after
            statement = statement.where(
                (Note.created_at < created) | ((Note.created_at == created) & (Note.id < last_id))
            )
        statement = statement.order_by(Note.created_at.desc(), Note.id.desc()).limit(limit + 1)
        rows = list(session.execute(statement).scalars())
        more = len(rows) > limit
        rows = rows[:limit]
        items = [_out(row, scope, rights, archived=archived) for row in rows]
        last_key = (rows[-1].created_at, rows[-1].id) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode("note", ORDER, DIRECTION, filters, last_key)
    return NotePage(items=items, next_cursor=next_cursor, archived=archived)


def get_note(scope: Scope, note_id: uuid.UUID, rights: NoteRights | None) -> dict[str, Any]:
    with tenant_session_scope(scope.workspace) as session:
        row = session.execute(
            select(Note).where(Note.tenant_id == scope.workspace, Note.id == note_id)
        ).scalar_one_or_none()
        if row is None:
            raise NoteNotFoundError
        return _out(row, scope, rights, archived=_parent_archived(session, scope, row))


# --- Writes ----------------------------------------------------------------------


def create_note(
    kind: Kind,
    scope: Scope,
    record_id: uuid.UUID,
    body: str,
    *,
    idempotency_key: str | None = None,
) -> tuple[uuid.UUID, bool]:
    """Add a note; returns its ID and whether this was an idempotent replay.
    The key is scoped to the workspace and the acting member; the
    idempotency record stores the new ID only, never the text."""
    note_id = uuid.uuid4()

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        # Locking the record serialises with its archive and delete: a note
        # is never added to a record archived or deleted meanwhile.
        record = load_record(session, kind, scope, record_id, lock=True)
        if record.archived_at is not None:
            raise RecordArchivedError
        now = _now()
        note = Note(
            id=note_id,
            tenant_id=scope.workspace,
            body=body,
            author_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
            **({"contact_id": record_id} if kind is CONTACT else {"company_id": record_id}),
        )
        session.add(note)
        session.flush()
        session.add(history_entry(kind, scope, record_id, "note_added", note_id=note_id))
        _audit(session, scope, "created", note)
        return {"id": str(note_id)}

    replay = False
    if idempotency_key is None:
        result = _write(scope, business)
    else:
        fingerprint = {"record": f"{kind.name}:{record_id}", "body": body}
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
    return uuid.UUID(str(result["id"])), replay


def update_note(
    scope: Scope,
    note_id: uuid.UUID,
    body: str,
    *,
    expected_version: int,
    rights: NoteRights,
) -> dict[str, Any]:
    """Replace a note's text if it is still at `expected_version`. The
    same text is a no-op: no new version, no audit entry."""

    def apply(session: Session) -> dict[str, Any]:
        note, archived = _lock_note(session, scope, note_id)
        if not _may_edit(note, scope, rights):
            raise NotNoteAuthorError
        if archived:
            raise RecordArchivedError
        if note.version != expected_version:
            raise StaleVersionError(note.version)
        if note.body != body:
            note.body = body
            note.version += 1
            note.updated_at = _now()
            note.updated_by_user_id = scope.actor
            session.flush()
            _audit(session, scope, "updated", note)
        # Built in the writing transaction: a delete committed just after
        # cannot turn a successful edit into a 404.
        return _out(note, scope, rights, archived=False)

    return _write(scope, apply)


def delete_note(scope: Scope, note_id: uuid.UUID, *, rights: NoteRights) -> None:
    """Permanent (D4): the row and its `note_added` entry go (`ON DELETE
    CASCADE`); a `note_deleted` entry without text records that it did."""

    def apply(session: Session) -> None:
        note, _ = _lock_note(session, scope, note_id)
        if not _may_delete(note, scope, rights):
            raise NotNoteAuthorError
        kind, record_id = _kind_of(note)
        _audit(session, scope, "deleted", note)
        session.execute(delete(Note).where(Note.tenant_id == scope.workspace, Note.id == note_id))
        session.add(history_entry(kind, scope, record_id, "note_deleted"))

    _write(scope, apply)
