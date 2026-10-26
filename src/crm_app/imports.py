"""CSV imports of contacts and companies (decision P3-F, `PHASE3-PLAN.md` §9).

Preview reads the uploaded file (never stored), validates every row with the
API's own rules and keeps only normalised values or error codes in
`import_row`, with the job's counts in `import_job`. A row whose email
(contact) or domain (company) belongs to an existing active record, or to an
earlier row of the file, is a duplicate and is never imported: nothing is
updated or overwritten. Committing creates the records later, on the worker.

Retention (P3-F 7): every import gets an `import_expiry` entry, written in a
transaction without a workspace (the table's exclusion policy allows
nothing else) before its rows exist, so no staging row is ever left without
a due date; `crm_app.import_maintenance` deletes the rows when due.

Every change runs in a workspace-scoped transaction with its audit entry,
which holds counts only. No cell value reaches a log, an audit entry or an
error.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import Session, select, session_scope, tenant_session_scope

from crm_app.domains import imports as rules
from crm_app.models import Company, Contact, ImportExpiry, ImportJob, ImportRow
from crm_app.records import RecordError, RecordNotFoundError, Scope

RESOURCE = "crm_app.import"
RETENTION = timedelta(days=7)
ERRORS_SHOWN = 50
SAMPLE_ROWS = 5
RECENT_JOBS = 20
_LOOKUP_CHUNK = 1000
_REFUSED = ("invalid", "duplicate", "failed")


class ImportNotFoundError(RecordError):
    status, code = 404, "import_not_found"


class ImportRefusedError(RecordError):
    """The file or mapping cannot be imported (P3-F 3); `code` says why."""

    status = 422

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


Summary = dict[str, Any]


@dataclass(frozen=True)
class Preview:
    summary: Summary
    header: list[str]
    sample: list[dict[str, object]]


def _now() -> datetime:
    return datetime.now(UTC)


def _summary(job: ImportJob, errors: Sequence[dict[str, object]]) -> Summary:
    return {
        "id": job.id,
        "entity": job.entity,
        "status": job.status,
        "mapping": job.mapping,
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "duplicate_rows": job.duplicate_rows,
        "created_rows": job.created_rows,
        "skipped_rows": job.skipped_rows,
        "failed_rows": job.failed_rows,
        "cancel_requested": job.cancel_requested,
        "created_by_user_id": job.created_by_user_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "finished_at": job.finished_at,
        "errors": list(errors),
    }


def audit(session: Session, scope: Scope, verb: str, job: ImportJob, **counts: int) -> None:
    """An import audit entry: the kind of records and counts, never values."""
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(job.id),
        metadata={"entity": job.entity, **counts},
    )


def existing_keys(session: Session, scope: Scope, entity: str, keys: set[str]) -> set[str]:
    """The keys (emails or domains) an active record of the workspace holds."""
    model = Contact if entity == "contact" else Company
    column = Contact.email if entity == "contact" else Company.domain
    found: set[str] = set()
    ordered = sorted(keys)
    for start in range(0, len(ordered), _LOOKUP_CHUNK):
        chunk = ordered[start : start + _LOOKUP_CHUNK]
        found.update(
            key
            for key in session.execute(
                select(column).where(
                    model.tenant_id == scope.workspace,
                    model.archived_at.is_(None),
                    column.in_(chunk),
                )
            ).scalars()
            if key is not None
        )
    return found


def _row_errors(rows: Sequence[ImportRow]) -> list[dict[str, object]]:
    """Row number, field and code of the first refused rows; never a value."""
    shown: list[dict[str, object]] = []
    for row in rows:
        if row.status != "invalid":
            shown.append({"row": row.row_number, "field": None, "code": row.status})
        for error in row.errors or []:
            shown.append({"row": row.row_number, "field": error["field"], "code": error["code"]})
    return shown[:ERRORS_SHOWN]


def _stage(
    scope: Scope, entity: str, results: Sequence[rules.RowResult], session: Session
) -> tuple[list[ImportRow], dict[str, int]]:
    keys = {
        key
        for result in results
        if result.data is not None and (key := rules.unique_key(entity, result.data)) is not None
    }
    taken = existing_keys(session, scope, entity, keys)
    rows: list[ImportRow] = []
    seen: set[str] = set()
    counts = {"valid": 0, "invalid": 0, "duplicate": 0}
    import_id = uuid.uuid4()
    for result in results:
        status = "invalid" if result.data is None else "valid"
        if result.data is not None:
            key = rules.unique_key(entity, result.data)
            if key is not None:
                if key in taken or key in seen:
                    status = "duplicate"
                seen.add(key)
        counts[status] += 1
        rows.append(
            ImportRow(
                tenant_id=scope.workspace,
                import_id=import_id,
                row_number=result.number,
                status=status,
                data=result.data,
                errors=result.errors or None,
                record_id=None,
            )
        )
    return rows, counts


def preview(scope: Scope, entity: str, body: bytes, mapping: Mapping[str, int] | None) -> Preview:
    """Read, validate and stage one file; nothing is imported yet."""
    try:
        table = rules.read(rules.decode(body))
        chosen = rules.check_mapping(
            entity,
            mapping if mapping is not None else rules.propose(entity, table.header),
            len(table.header),
        )
    except rules.ImportFileError as exc:
        raise ImportRefusedError(exc.code) from None
    results = [
        rules.validate(entity, chosen, number, row)
        for number, row in enumerate(table.rows, start=1)
    ]
    import_id = uuid.uuid4()
    now = _now()
    # The due date first, in a transaction without a workspace: rows never
    # exist without one. If staging fails below, the entry has nothing to
    # delete, and the maintenance command removes it.
    with session_scope() as session:
        session.add(
            ImportExpiry(import_id=import_id, workspace_id=scope.workspace, due_at=now + RETENTION)
        )
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            rows, counts = _stage(scope, entity, results, session)
            for row in rows:
                row.import_id = import_id
            job = ImportJob(
                id=import_id,
                tenant_id=scope.workspace,
                entity=entity,
                status="previewed",
                mapping=chosen,
                total_rows=len(results),
                valid_rows=counts["valid"],
                invalid_rows=counts["invalid"],
                duplicate_rows=counts["duplicate"],
                created_rows=0,
                skipped_rows=0,
                failed_rows=0,
                checkpoint=0,
                cancel_requested=False,
                created_by_user_id=scope.actor,
                created_at=now,
                updated_at=now,
                finished_at=None,
                version=1,
            )
            session.add(job)
            session.flush()
            session.add_all(rows)
            audit(
                session,
                scope,
                "previewed",
                job,
                total_rows=job.total_rows,
                valid_rows=job.valid_rows,
                invalid_rows=job.invalid_rows,
                duplicate_rows=job.duplicate_rows,
            )
            summary = _summary(job, _row_errors([r for r in rows if r.status != "valid"]))
            # The first rows that would be imported, as they would be stored.
            sample = [r.data for r in rows if r.status == "valid" and r.data][:SAMPLE_ROWS]
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    return Preview(summary=summary, header=table.header, sample=sample)


def load(session: Session, scope: Scope, import_id: uuid.UUID, *, lock: bool = False) -> ImportJob:
    query = select(ImportJob).where(
        ImportJob.tenant_id == scope.workspace, ImportJob.id == import_id
    )
    job = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if job is None:
        raise ImportNotFoundError
    return job


def summary_of(session: Session, scope: Scope, job: ImportJob) -> Summary:
    refused = session.execute(
        select(ImportRow)
        .where(
            ImportRow.tenant_id == scope.workspace,
            ImportRow.import_id == job.id,
            ImportRow.status.in_(_REFUSED),
        )
        .order_by(ImportRow.row_number)
        .limit(ERRORS_SHOWN)
    ).scalars()
    return _summary(job, _row_errors(list(refused)))


def get(scope: Scope, import_id: uuid.UUID) -> Summary:
    with tenant_session_scope(scope.workspace) as session:
        return summary_of(session, scope, load(session, scope, import_id))


def recent(scope: Scope) -> list[Summary]:
    """The workspace's latest imports, newest first."""
    with tenant_session_scope(scope.workspace) as session:
        jobs = session.execute(
            select(ImportJob)
            .where(ImportJob.tenant_id == scope.workspace)
            .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
            .limit(RECENT_JOBS)
        ).scalars()
        return [_summary(job, []) for job in jobs]


def error_rows(scope: Scope, import_id: uuid.UUID) -> list[tuple[int, str, str]]:
    """Every refused row as (row number, field, code), for the error report."""
    with tenant_session_scope(scope.workspace) as session:
        load(session, scope, import_id)
        rows = session.execute(
            select(ImportRow.row_number, ImportRow.status, ImportRow.errors)
            .where(
                ImportRow.tenant_id == scope.workspace,
                ImportRow.import_id == import_id,
                ImportRow.status.in_(_REFUSED),
            )
            .order_by(ImportRow.row_number)
        ).all()
    report: list[tuple[int, str, str]] = []
    for number, status, errors in rows:
        if status != "invalid":
            report.append((number, "", status))
        for error in errors or []:
            report.append((number, error["field"], error["code"]))
    return report
