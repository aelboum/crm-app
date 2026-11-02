"""Email template routes (decision P7-T).

    GET    /v1/workspaces/{tenant_id}/email-templates                 campaign:read
    POST   /v1/workspaces/{tenant_id}/email-templates                 campaign:manage
    PATCH  /v1/workspaces/{tenant_id}/email-templates/{id}            campaign:manage
    DELETE /v1/workspaces/{tenant_id}/email-templates/{id}            campaign:manage
    POST   /v1/workspaces/{tenant_id}/email-templates/{id}/render     conversation:reply

Templates use the campaign permissions (every role reads; Owners, Admins
and Members manage), so no new permission is needed. Rendering for a
contact is for the reply composer, so it takes the permission to reply.
The path's `tenant_id` is only the request; handlers use
`context.tenant_id` alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import email_templates
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import campaigns as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["email templates"])

Read = Annotated[RequestContext, Depends(require_permission("crm_app.campaign", "read"))]
Manage = Annotated[RequestContext, Depends(require_permission("crm_app.campaign", "manage"))]
Reply = Annotated[RequestContext, Depends(require_permission("crm_app.conversation", "reply"))]


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=4 * rules.NAME_MAX)
    subject: str = Field(max_length=4 * rules.SUBJECT_MAX)
    body: str = Field(max_length=2 * rules.BODY_MAX)


class TemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=4 * rules.NAME_MAX)
    subject: str | None = Field(default=None, max_length=4 * rules.SUBJECT_MAX)
    body: str | None = Field(default=None, max_length=2 * rules.BODY_MAX)


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    subject: str
    body: str
    created_at: datetime
    updated_at: datetime
    version: int


class TemplateList(BaseModel):
    items: list[TemplateOut]


class RenderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID


class Rendered(BaseModel):
    subject: str
    body: str


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, email_templates.TemplateRuleError):
        return HTTPException(422, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_LIST = "/{tenant_id}/email-templates"
_ONE = f"{_LIST}/{{template_id}}"


@router.get(_LIST, response_model=TemplateList, name="list_email_templates")
async def list_email_templates(context: Read) -> Any:
    items = await run_in_threadpool(email_templates.list_templates, _scope(context))
    return {"items": items}


@router.post(_LIST, status_code=201, response_model=TemplateOut, name="create_email_template")
async def create_email_template(body: TemplateIn, context: Manage, response: Response) -> Any:
    try:
        item = await run_in_threadpool(email_templates.create, _scope(context), body.model_dump())
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.patch(_ONE, response_model=TemplateOut, name="update_email_template")
async def update_email_template(
    template_id: uuid.UUID,
    body: TemplatePatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(exclude_none=True)
    try:
        item = await run_in_threadpool(
            lambda: email_templates.update(
                _scope(context), template_id, changes, expected_version=expected
            )
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_ONE, status_code=204, name="delete_email_template")
async def delete_email_template(template_id: uuid.UUID, context: Manage) -> Response:
    try:
        await run_in_threadpool(email_templates.remove, _scope(context), template_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


@router.post(f"{_ONE}/render", response_model=Rendered, name="render_email_template")
async def render_email_template(template_id: uuid.UUID, body: RenderIn, context: Reply) -> Any:
    """The template filled in for one of the workspace's contacts."""
    try:
        return await run_in_threadpool(
            email_templates.render, _scope(context), template_id, body.contact_id
        )
    except RecordError as exc:
        raise _refusal(exc) from None
