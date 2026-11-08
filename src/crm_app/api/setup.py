"""The Home page's setup checklist (decision P4-S).

    GET /v1/workspaces/{tenant_id}/setup   crm_app.workspace:read

Mounted under the workspace settings router (`crm_app.api.workspace_settings`).
Every role may read it: it says only whether each first step exists, never
what any record holds. The path's `tenant_id` is only the request; the
handler uses `context.tenant_id` alone.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.infra.db import OperationalError, is_statement_timeout

from crm_app import setup_steps
from crm_app.records import Scope

router = APIRouter(tags=["workspaces"])

Read = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]

StepKey = Literal[
    "business_hours", "contact", "deal", "form", "booking_page", "automation", "teammate"
]


class SetupStep(BaseModel):
    key: StepKey
    done: bool


class Setup(BaseModel):
    steps: list[SetupStep]


@router.get("/{tenant_id}/setup", response_model=Setup, name="workspace_setup")
async def workspace_setup(context: Read) -> Any:
    scope = Scope(workspace=context.tenant_id, actor=context.actor_id)
    try:
        return {"steps": await run_in_threadpool(setup_steps.steps, scope)}
    except OperationalError as exc:
        if is_statement_timeout(exc):
            raise HTTPException(503, detail={"code": "setup_timeout"}) from None
        raise
