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
    from fastapi.exceptions import RequestValidationError  # noqa: PLC0415
    from saas_os.api.platform import build_platform_app  # noqa: PLC0415
    from saas_os.api.v1 import invitation_acceptance_router  # noqa: PLC0415

    from crm_app.api.access import router as access_router  # noqa: PLC0415
    from crm_app.api.custom_fields import router as custom_fields_router  # noqa: PLC0415
    from crm_app.api.errors import validation_error  # noqa: PLC0415
    from crm_app.api.headers import NoStoreMiddleware  # noqa: PLC0415
    from crm_app.api.history import router as history_router  # noqa: PLC0415
    from crm_app.api.imports import router as imports_router  # noqa: PLC0415
    from crm_app.api.invitations import router as invitations_router  # noqa: PLC0415
    from crm_app.api.members import router as members_router  # noqa: PLC0415
    from crm_app.api.notes import router as notes_router  # noqa: PLC0415
    from crm_app.api.opportunities import router as opportunities_router  # noqa: PLC0415
    from crm_app.api.pipelines import router as pipelines_router  # noqa: PLC0415
    from crm_app.api.records import router as records_router  # noqa: PLC0415
    from crm_app.api.sign_out import router as sign_out_router  # noqa: PLC0415
    from crm_app.api.signups import router as signups_router  # noqa: PLC0415
    from crm_app.api.spa import router as spa_router  # noqa: PLC0415
    from crm_app.api.tags import router as tags_router  # noqa: PLC0415
    from crm_app.api.tasks import router as tasks_router  # noqa: PLC0415
    from crm_app.api.workspace_settings import router as settings_router  # noqa: PLC0415
    from crm_app.api.workspaces import router as workspaces_router  # noqa: PLC0415
    from crm_app.purge import register_purge_participants  # noqa: PLC0415

    # A purge run from this process must also purge product data (crm_app.purge).
    register_purge_participants()
    app = build_platform_app(title=TITLE, version=__version__)
    # Rejected values are personal data: 422 bodies never echo them.
    app.add_exception_handler(RequestValidationError, validation_error)
    # Responses with personal data are never stored by browsers or proxies.
    app.add_middleware(NoStoreMiddleware)
    app.include_router(workspaces_router)
    app.include_router(settings_router)
    app.include_router(access_router)
    app.include_router(members_router)
    app.include_router(records_router)
    app.include_router(history_router)
    app.include_router(notes_router)
    app.include_router(tags_router)
    app.include_router(custom_fields_router)
    app.include_router(imports_router)
    app.include_router(pipelines_router)
    app.include_router(opportunities_router)
    app.include_router(tasks_router)
    app.include_router(invitations_router)
    # SaaS-OS's acceptance route (ADR-0046): the invitee, signed in with the
    # invited verified email, redeems the token; no role is given (Q5).
    app.include_router(invitation_acceptance_router)
    app.include_router(sign_out_router)
    # Self-service signup (S-1): 404 while SIGNUP_ENABLED is off.
    app.include_router(signups_router)
    app.include_router(spa_router)
    return app
