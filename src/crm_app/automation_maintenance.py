"""Advance the automation runs that are due (decision P8-A).

    python -m crm_app.automation_maintenance

Run it every minute from the deployment's scheduler, next to the worker, as
`crm_app.email_maintenance`: SaaS-OS v0.6.0 schedules system jobs only
through a queue outside its public surface. New runs and runs whose wait
has passed are found in the global `automation_due`, read without a
workspace; each is pushed back by `RETRY_DELAY` and its job enqueued, so a
lost job is tried again. The job decides what to do; a step it already did
is never done again. It prints counts only.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Sequence

from crm_app.settings import Process, validate_settings


async def _enqueue_all(pairs: list[tuple[uuid.UUID, uuid.UUID]]) -> tuple[int, int]:
    from crm_app import automations  # noqa: PLC0415

    queued = unreachable = 0
    for workspace, run_id in pairs:
        if await automations.enqueue(workspace, run_id):
            queued += 1
        else:
            unreachable += 1
    return queued, unreachable


def maintain() -> dict[str, int]:
    from crm_app import automations  # noqa: PLC0415

    queued, unreachable = asyncio.run(_enqueue_all(automations.due()))
    return {"queued": queued, "unreachable": unreachable}


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("usage: python -m crm_app.automation_maintenance", file=sys.stderr)
        return 2
    validate_settings(Process.WORKER)
    report = maintain()
    print(f"automations: queued {report['queued']}, queue unreachable {report['unreachable']}")
    return 1 if report["unreachable"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
