"""The worker entrypoint.

    crm-app-worker            # long-running worker
    crm-app-worker --check    # health probe

It is SaaS-OS's own production worker (`saas_os.api.worker.main`) with this
product's jobs added: the same startup order, the same fail-closed
database-role guard, the same health probe, and every platform job still
running. Run this instead of `python -m saas_os.api.worker`, never next to it.
"""

from __future__ import annotations

import sys

from crm_app.settings import Process, validate_settings


def run(argv: list[str] | None = None) -> int:
    validate_settings(Process.WORKER)
    # Imported only after validation: both resolve configuration at import time.
    from saas_os.api.worker import main as platform_worker_main  # noqa: PLC0415

    from crm_app.jobs import JOB_FUNCTIONS  # noqa: PLC0415

    return platform_worker_main(argv, extra_functions=JOB_FUNCTIONS)


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
