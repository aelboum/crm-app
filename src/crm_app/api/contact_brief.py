"""The contact brief route (decision P9-B).

    POST /v1/workspaces/{tenant_id}/contacts/{contact_id}/brief
        crm_app.contact:read here; SaaS-OS then checks ai.inference:run,
        the workspace's AI policy, its budget and the platform's own rules

A member asks for one short, suggestions-only summary of a contact. The
request carries only the allowlisted facts (`crm_app.domains.ai_brief`);
the answer is shown to that member and never stored, logged or acted on.
Users only: an integration's key is refused. While AI is off for the
workspace (the default), or the member may not use it, the answer is the
state `unavailable`, never provider detail. The path's `tenant_id` is only
the request; the handler uses `context.tenant_id` alone.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission
from saas_os.core.authority import UserCaller

from crm_app import ai, contact_brief
from crm_app.records import Scope

router = APIRouter(prefix="/v1/workspaces", tags=["ai"])

ReadContact = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]


class BriefOut(BaseModel):
    """`text` only when `state` is `ready`: a suggestion to check, not a fact."""

    state: Literal["ready", "unavailable", "quota_reached", "busy", "failed"]
    text: str | None


@router.post(
    "/{tenant_id}/contacts/{contact_id}/brief",
    response_model=BriefOut,
    name="contact_brief",
)
async def brief_contact(contact_id: uuid.UUID, context: ReadContact) -> BriefOut:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=403, detail={"code": "user_only"})
    scope = Scope(workspace=context.tenant_id, actor=context.actor_id)
    found = await run_in_threadpool(contact_brief.facts, scope, contact_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    facts, today = found
    outcome = await ai.contact_brief(
        UserCaller(context.actor_id), tenant_id=context.tenant_id, facts=facts, today=today
    )
    return BriefOut(state=outcome.state.value, text=outcome.text)
