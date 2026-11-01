"""Try again the emails whose job was lost or deferred (decision P6-E).

    python -m crm_app.email_maintenance

Run it every few minutes from the deployment's scheduler, next to the
worker, as `crm_app.import_maintenance`: SaaS-OS v0.6.0 still schedules
system jobs only through a queue outside its public surface.

Emails due for another try come from the global `email_index`, read in a
transaction without a workspace; each is checked in its own workspace.
An index row whose email never committed is removed. Every other one is
postponed by `RETRY_DELAY` and its send job enqueued; the job itself
decides whether to send (only while `EMAIL_SENDING_ENABLED` is on, never
twice, at most `MAX_ATTEMPTS` tries). It prints counts only.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Sequence

from crm_app.settings import Process, validate_settings


async def _enqueue_all(pairs: list[tuple[uuid.UUID, uuid.UUID]]) -> tuple[int, int]:
    from crm_app import emails  # noqa: PLC0415

    queued = unreachable = 0
    for workspace, email_id in pairs:
        if await emails.enqueue(workspace, email_id):
            queued += 1
        else:
            unreachable += 1
    return queued, unreachable


def maintain() -> dict[str, int]:
    from crm_app import emails  # noqa: PLC0415

    orphans = 0
    pending: list[tuple[uuid.UUID, uuid.UUID]] = []
    for workspace, email_id in emails.due():
        if emails.orphan(workspace, email_id):
            orphans += 1
            continue
        emails.postpone(email_id)
        pending.append((workspace, email_id))
    queued, unreachable = asyncio.run(_enqueue_all(pending))
    return {"queued": queued, "unreachable": unreachable, "orphans": orphans}


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("usage: python -m crm_app.email_maintenance", file=sys.stderr)
        return 2
    validate_settings(Process.WORKER)
    report = maintain()
    print(
        f"emails: queued {report['queued']}, queue unreachable {report['unreachable']},"
        f" orphan entries removed {report['orphans']}"
    )
    return 1 if report["unreachable"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
