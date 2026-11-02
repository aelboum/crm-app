"""Is periodic work keeping up? (decision 13-O1)

    python -m crm_app.health_check

For the deployment's monitoring: counts the global due rows that should
have been handled long ago, which means the worker or a scheduled command
(`docs/project/OPERATIONS.md`) is not running. Reads ids and times only,
in a transaction without a workspace, and prints counts only. Exits 1 when
anything is overdue, 0 otherwise; it changes nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from crm_app.settings import Process, validate_settings

# Beyond its command's cadence plus a margin (OPERATIONS.md).
EMAIL_LATE = timedelta(minutes=15)
AUTOMATION_LATE = timedelta(minutes=15)
IMPORT_LATE = timedelta(hours=3)
CAP = 1000


def overdue(now: datetime | None = None) -> dict[str, int]:
    """How many due rows are overdue, each counted up to `CAP`."""
    from saas_os.infra.db import select, session_scope  # noqa: PLC0415

    from crm_app.models import AutomationDue, EmailIndex, ImportExpiry  # noqa: PLC0415

    now = now or datetime.now(UTC)
    with session_scope() as session:
        emails = session.execute(
            select(EmailIndex.email_message_id)
            .where(EmailIndex.retry_at.is_not(None), EmailIndex.retry_at <= now - EMAIL_LATE)
            .limit(CAP)
        ).all()
        runs = session.execute(
            select(AutomationDue.run_id)
            .where(AutomationDue.due_at <= now - AUTOMATION_LATE)
            .limit(CAP)
        ).all()
        imports = session.execute(
            select(ImportExpiry.import_id)
            .where(ImportExpiry.due_at <= now - IMPORT_LATE)
            .limit(CAP)
        ).all()
    return {"emails": len(emails), "automation_runs": len(runs), "imports": len(imports)}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("usage: python -m crm_app.health_check", file=sys.stderr)
        return 2
    validate_settings(Process.WORKER)
    counts = overdue()
    print(" ".join(f"{name}_overdue={count}" for name, count in counts.items()))
    return 1 if any(counts.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
