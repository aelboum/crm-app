"""Apply every migration this deployment needs, in the one valid order.

    crm-app-migrate

1. SaaS-OS's own history (`alembic_version_saas_os`), through the installed
   package, never by pointing Alembic at a path inside `site-packages`.
2. This product's own history (`alembic_version`). It may reference
   `core.*` tables, so it always runs second (SaaS-OS ADR-0016).
3. This product's permissions, registered into the shared catalog.

Steps 1 and 2 connect with `MIGRATIONS_DATABASE_URL` (the privileged
migration role). Step 3 connects with `DATABASE_URL` (the restricted
application role). Run it as a deployment step, before the application and
the worker start. Running it again changes nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

from crm_app.settings import Process, validate_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def migrate() -> None:
    validate_settings(Process.MIGRATE)
    # Imported only after validation: SaaS-OS resolves configuration at import time.
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415
    from saas_os.infra.db import run_core_migrations  # noqa: PLC0415

    from crm_app.permissions import register_permissions  # noqa: PLC0415

    run_core_migrations()
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    command.upgrade(config, "head")
    register_permissions()


def main() -> int:
    migrate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
