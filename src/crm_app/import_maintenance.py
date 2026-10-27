"""Delete CSV import staging rows when they fall due (decision P3-F 7).

    python -m crm_app.import_maintenance

Run it every hour or so from the deployment's scheduler, next to the
worker, as for `crm_app.signup_maintenance`: SaaS-OS v0.5.0 schedules system
jobs only through a queue that is not part of its public surface.

An import's rows (normalised values: personal data) are deleted 7 days
after the import finishes, or 7 days after its preview when it is never
committed; such an import becomes `expired`. Records the import created are
never touched. The job's summary, which holds no cell value, is kept.

Which imports are due comes from the global `import_expiry` table, read in
a transaction without a workspace (its exclusion policy allows nothing
else); each import's rows are then deleted inside its own workspace's
scope, so Row-Level Security confines every deletion. A queued or running
import is left alone and checked again a day later. It prints counts only.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from crm_app.settings import Process, validate_settings

BATCH = 200


@dataclass(frozen=True)
class Report:
    cleared: int
    expired: int
    postponed: int
    orphans: int


def maintain() -> Report:
    """Handle every due entry; safe to run again at any time."""
    from saas_os.infra.db import select, session_scope  # noqa: PLC0415

    from crm_app.models import ImportExpiry  # noqa: PLC0415

    now = datetime.now(UTC)
    cleared = expired = postponed = orphans = 0
    due: list[tuple[uuid.UUID, uuid.UUID]] = []

    def next_batch() -> list[tuple[uuid.UUID, uuid.UUID]]:
        # Handled entries are deleted or moved a day ahead, so each batch is new.
        with session_scope() as session:
            return [
                (import_id, workspace_id)
                for import_id, workspace_id in session.execute(
                    select(ImportExpiry.import_id, ImportExpiry.workspace_id)
                    .where(ImportExpiry.due_at <= now)
                    .order_by(ImportExpiry.due_at)
                    .limit(BATCH)
                )
            ]

    while due := next_batch():
        cleared, expired, postponed, orphans = _handle(
            due, now, (cleared, expired, postponed, orphans)
        )
    return Report(cleared=cleared, expired=expired, postponed=postponed, orphans=orphans)


def _handle(
    due: list[tuple[uuid.UUID, uuid.UUID]],
    now: datetime,
    counts: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    from saas_os.infra.db import (  # noqa: PLC0415
        delete,
        select,
        session_scope,
        tenant_session_scope,
        update,
    )

    from crm_app.models import ImportExpiry, ImportJob, ImportRow  # noqa: PLC0415

    cleared, expired, postponed, orphans = counts
    for import_id, workspace_id in due:
        with tenant_session_scope(workspace_id) as session:
            job = session.execute(
                select(ImportJob)
                .where(ImportJob.tenant_id == workspace_id, ImportJob.id == import_id)
                .with_for_update()
            ).scalar_one_or_none()
            keep = job is not None and job.status in ("queued", "running")
            if job is not None and not keep:
                session.execute(
                    delete(ImportRow).where(
                        ImportRow.tenant_id == workspace_id, ImportRow.import_id == import_id
                    )
                )
                if job.status == "previewed":
                    job.status = "expired"
                    job.finished_at = now
                    job.version += 1
                    job.updated_at = now
                    expired += 1
                cleared += 1
        with session_scope() as session:
            if keep:
                session.execute(
                    update(ImportExpiry)
                    .where(ImportExpiry.import_id == import_id)
                    .values(due_at=now + timedelta(days=1))
                )
                postponed += 1
            else:
                session.execute(delete(ImportExpiry).where(ImportExpiry.import_id == import_id))
                if job is None:
                    orphans += 1
    return cleared, expired, postponed, orphans


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("usage: python -m crm_app.import_maintenance", file=sys.stderr)
        return 2
    validate_settings(Process.WORKER)
    report = maintain()
    print(
        f"imports: cleared {report.cleared} (expired {report.expired}),"
        f" postponed {report.postponed}, orphan entries removed {report.orphans}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
