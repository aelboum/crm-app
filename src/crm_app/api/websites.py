"""Website routes (decision P12-W, slice 12W).

    GET    /v1/workspaces/{tenant_id}/websites                crm_app.form:read
    POST   /v1/workspaces/{tenant_id}/websites                crm_app.form:manage
    PATCH  /v1/workspaces/{tenant_id}/websites/{id}           crm_app.form:manage
    DELETE /v1/workspaces/{tenant_id}/websites/{id}           crm_app.form:manage

A website lets pages on its origins submit the workspace's published forms
from the browser (`crm_app.api.forms`, CORS). Websites belong to forms, so
they use the form permissions; no new permission. `PATCH` needs
`If-Match`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import websites
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import websites as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["websites"])

Read = Annotated[RequestContext, Depends(require_permission("crm_app.form", "read"))]
Manage = Annotated[RequestContext, Depends(require_permission("crm_app.form", "manage"))]

Origins = Annotated[
    list[Annotated[str, Field(max_length=300)]], Field(max_length=rules.ORIGINS_MAX * 2)
]


class WebsiteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=4 * rules.NAME_MAX)
    origins: Origins


class WebsitePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=4 * rules.NAME_MAX)
    origins: Origins | None = None
    status: Literal["active", "disabled"] | None = None


class WebsiteOut(BaseModel):
    id: uuid.UUID
    name: str
    origins: list[str]
    status: Literal["active", "disabled"]
    created_at: datetime
    updated_at: datetime
    version: int


class WebsiteList(BaseModel):
    items: list[WebsiteOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, websites.WebsiteRuleError):
        return HTTPException(exc.status, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


_LIST = "/{tenant_id}/websites"
_ONE = f"{_LIST}/{{website_id}}"


@router.get(_LIST, response_model=WebsiteList, name="list_websites")
def list_websites(context: Read) -> Any:
    return {"items": websites.list_websites(_scope(context))}


@router.post(_LIST, status_code=201, response_model=WebsiteOut, name="create_website")
def create_website(body: WebsiteIn, context: Manage, response: Response) -> Any:
    try:
        item = websites.create(_scope(context), name=body.name, origins=body.origins)
    except RecordError as exc:
        raise _refusal(exc) from None
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


@router.patch(_ONE, response_model=WebsiteOut, name="update_website")
def update_website(
    website_id: uuid.UUID,
    body: WebsitePatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, detail={"code": "value_required"})
    try:
        item = websites.update(_scope(context), website_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


@router.delete(_ONE, status_code=204, name="delete_website")
def delete_website(website_id: uuid.UUID, context: Manage) -> Response:
    try:
        websites.remove(_scope(context), website_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)
