"""Resume, expire and clean up self-service signups (`SIGNUP-PLAN.md` §4b).

    python -m crm_app.signup_maintenance

Run it every few minutes from the deployment's scheduler, next to the
worker. It is a command rather than a worker cron job because SaaS-OS
v0.5.0 schedules system jobs only through `saas_os.infra.jobs.queue`, which
is not part of its public surface (a gap recorded in `SIGNUP-PLAN.md`
§4b). Signups also resume when their person retries the same request.

It works whether or not `SIGNUP_ENABLED` is on, so turning signup off never
strands a half-provisioned workspace. It prints counts only.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from crm_app.settings import Process, validate_settings


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("usage: python -m crm_app.signup_maintenance", file=sys.stderr)
        return 2
    validate_settings(Process.WORKER)
    # Imported only after validation: SaaS-OS resolves configuration at import time.
    from crm_app import signups  # noqa: PLC0415

    report = signups.maintain()
    print(
        f"signups: resumed {report.resumed} (completed {report.completed},"
        f" expired {report.expired}, failed {report.failed});"
        f" removed {report.removed}; attempts removed {report.attempts_removed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
