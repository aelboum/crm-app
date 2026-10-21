"""The application entrypoint.

    uvicorn crm_app.app:create_app --factory

`create_app()` validates the environment, then builds the application on
SaaS-OS's `build_platform_app()` (SaaS-OS ADR-0017). The platform
contributes the fail-closed startup checks (every route declares exactly
one policy; the database role cannot bypass Row-Level Security), request
correlation, the health routes and the OIDC routes under `/auth`. Product
routers (`crm_app.api`) are mounted on top; the platform's startup check
then covers them too.

There is deliberately no module-level `app`: importing this module must not
resolve configuration, so tests and tools can import it safely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crm_app import __version__
from crm_app.settings import Process, validate_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

TITLE = "crm-app"


def create_app() -> FastAPI:
    validate_settings(Process.APP)
    # Imported only after validation: SaaS-OS resolves configuration at import time.
    from saas_os.api.platform import build_platform_app  # noqa: PLC0415

    from crm_app.api.workspaces import router as workspaces_router  # noqa: PLC0415

    app = build_platform_app(title=TITLE, version=__version__)
    app.include_router(workspaces_router)
    return app
