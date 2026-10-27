"""Committing a previewed CSV import (decision P3-F 5, `PHASE3-PLAN.md` §9.1-9.2).

`queue` marks a previewed import `queued` (one queued or running import per
workspace, enforced by `import_job_one_active_key`) and the API enqueues the
worker job `crm_app_import_commit`, which calls `run`.

`run` creates records in batches of `BATCH` rows. Each batch is one
workspace-scoped transaction that creates the records (through
`crm_app.records.insert_record`: the same rules, history and audit as a
typed record) and marks each row `created` with the new record's ID,
`skipped` when an active record now holds its email or domain, or `failed`
when the database refuses it; then it moves the checkpoint. Delivery is at
least once: a repeated batch finds its rows already done and creates
nothing twice. Every row runs in a savepoint, so one refusal never undoes
the rest of its batch. Cancelling stops before the next batch; what was
created stays. A job that fails is marked `failed` and can be resumed from
its checkpoint.

When the import finishes, its staged rows fall due for deletion 7 days
later (P3-F 7): the `import_expiry` entry is moved, in a transaction
without a workspace.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    Session,
    select,
    session_scope,
    tenant_session_scope,
    update,
)

from crm_app.imports import RETENTION, Summary, audit, load, summary_of
from crm_app.models import ImportExpiry, ImportJob, ImportRow
from crm_app.records import (
    COMPANY,
    CONTACT,
    DuplicateRecordError,
    RecordError,
    RecordNotFoundError,
    Scope,
    insert_record,
)

logger = logging.getLogger(__name__)

JOB_NAME = "crm_app_import_commit"
BATCH = 500
_ACTIVE = ("queued", "running")


class ImportStateError(RecordError):
    """The import is not in a state that allows this action."""

    status = 409

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _touch(job: ImportJob) -> None:
    job.version += 1
    job.updated_at = _now()


def _write(scope: Scope, fn: Callable[[Session], Summary]) -> Summary:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None


def queue(scope: Scope, import_id: uuid.UUID, *, resume: bool = False) -> Summary:
    """Mark a previewed (or, with `resume`, a failed) import `queued`."""

    def apply(session: Session) -> Summary:
        job = load(session, scope, import_id, lock=True)
        if resume:
            if job.status != "failed":
                raise ImportStateError("import_not_failed")
        elif job.status != "previewed":
            raise ImportStateError("import_not_previewed")
        if job.valid_rows == 0:
            raise ImportStateError("nothing_to_import")
        active = session.execute(
            select(ImportJob.id).where(
                ImportJob.tenant_id == scope.workspace,
                ImportJob.status.in_(_ACTIVE),
                ImportJob.id != job.id,
            )
        ).first()
        if active is not None:
            raise ImportStateError("import_in_progress")
        job.status = "queued"
        job.finished_at = None
        job.cancel_requested = False
        _touch(job)
        session.flush()
        audit(session, scope, "committed", job, valid_rows=job.valid_rows)
        return summary_of(session, scope, job)

    try:
        return _write(scope, apply)
    except IntegrityError:
        # Another import was queued at the same moment.
        raise ImportStateError("import_in_progress") from None


def unqueue(scope: Scope, import_id: uuid.UUID) -> None:
    """Return a queued import to where it was when its job could not be
    enqueued: never started, so nothing was created."""

    def apply(session: Session) -> Summary:
        job = load(session, scope, import_id, lock=True)
        if job.status == "queued":
            job.status = "previewed" if job.checkpoint == 0 else "failed"
            job.finished_at = None if job.status == "previewed" else _now()
            _touch(job)
        return {}

    _write(scope, apply)


def cancel(scope: Scope, import_id: uuid.UUID) -> Summary:
    """Ask a queued or running import to stop before its next batch."""

    def apply(session: Session) -> Summary:
        job = load(session, scope, import_id, lock=True)
        if job.status not in _ACTIVE:
            raise ImportStateError("import_not_running")
        if not job.cancel_requested:
            job.cancel_requested = True
            _touch(job)
        return summary_of(session, scope, job)

    return _write(scope, apply)


def _move_expiry(import_id: uuid.UUID, finished: datetime) -> None:
    with session_scope() as session:
        session.execute(
            update(ImportExpiry)
            .where(ImportExpiry.import_id == import_id)
            .values(due_at=finished + RETENTION)
        )


def _finish(session: Session, scope: Scope, job: ImportJob, status: str) -> datetime:
    now = _now()
    job.status = status
    job.finished_at = now
    _touch(job)
    session.flush()
    verb = {"cancelled": "cancelled", "failed": "failed"}.get(status, "completed")
    audit(
        session,
        scope,
        verb,
        job,
        created_rows=job.created_rows,
        skipped_rows=job.skipped_rows,
        failed_rows=job.failed_rows,
    )
    return now


def _commit_row(session: Session, scope: Scope, job: ImportJob, row: ImportRow) -> str:
    kind = CONTACT if job.entity == "contact" else COMPANY
    values = dict(row.data or {})
    if kind is CONTACT:
        values["source"] = "import"
    record_id = uuid.uuid4()
    savepoint = session.begin_nested()
    try:
        insert_record(session, kind, scope, values, record_id=record_id, import_id=job.id)
    except DuplicateRecordError:
        savepoint.rollback()
        return "skipped"
    except IntegrityError as exc:
        savepoint.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        return "skipped" if constraint == kind.unique_index else "failed"
    except RecordError:
        savepoint.rollback()
        return "failed"
    savepoint.commit()
    row.record_id = record_id
    return "created"


def _batch(scope: Scope, import_id: uuid.UUID) -> tuple[bool, datetime | None]:
    """One batch; returns whether more remain, and the finish time when the
    import finished in this batch."""
    with tenant_session_scope(scope.workspace) as session:
        lock_open_tenant(session, scope.workspace)
        job = load(session, scope, import_id, lock=True)
        if job.status not in _ACTIVE:
            return False, None
        if job.cancel_requested:
            return False, _finish(session, scope, job, "cancelled")
        job.status = "running"
        rows = list(
            session.execute(
                select(ImportRow)
                .where(
                    ImportRow.tenant_id == scope.workspace,
                    ImportRow.import_id == import_id,
                    ImportRow.status == "valid",
                    ImportRow.row_number > job.checkpoint,
                )
                .order_by(ImportRow.row_number)
                .limit(BATCH)
                .with_for_update()
            ).scalars()
        )
        if not rows:
            job.checkpoint = job.total_rows
            refused = job.invalid_rows + job.duplicate_rows + job.skipped_rows + job.failed_rows
            status = "completed" if refused == 0 else "completed_with_errors"
            return False, _finish(session, scope, job, status)
        for row in rows:
            outcome = _commit_row(session, scope, job, row)
            row.status = outcome
            if outcome == "created":
                job.created_rows += 1
            elif outcome == "skipped":
                job.skipped_rows += 1
            else:
                job.failed_rows += 1
        job.checkpoint = rows[-1].row_number
        _touch(job)
        return True, None


def _fail(scope: Scope, import_id: uuid.UUID) -> datetime | None:
    with tenant_session_scope(scope.workspace) as session:
        job = load(session, scope, import_id, lock=True)
        if job.status not in _ACTIVE:
            return None
        return _finish(session, scope, job, "failed")


def run(scope: Scope, import_id: uuid.UUID) -> None:
    """Commit the import batch by batch until it finishes, is cancelled or
    fails. Safe to run again: done rows are never redone."""
    finished: datetime | None = None
    try:
        more = True
        while more:
            more, finished = _batch(scope, import_id)
    except Exception as exc:  # noqa: BLE001 - the job boundary: any failure marks the import failed
        # The type only: a driver message can quote a row's values.
        logger.error("import %s failed: %s", import_id, type(exc).__name__)
        finished = _fail(scope, import_id)
    if finished is not None:
        _move_expiry(import_id, finished)
