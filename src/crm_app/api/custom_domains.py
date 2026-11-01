"""Custom domain routes (decision P12-D, slice 12D).

    GET    /v1/workspaces/{tenant_id}/domains               crm_app.workspace:read
    POST   /v1/workspaces/{tenant_id}/domains               crm_app.workspace:update
    POST   /v1/workspaces/{tenant_id}/domains/{id}/check    crm_app.workspace:update
    DELETE /v1/workspaces/{tenant_id}/domains/{id}          crm_app.workspace:update
    GET    /v1/public/domains/resolve                       public

`check` needs `If-Match`. The public route answers which workspace the
request's `Host` belongs to, for verified hostnames only (404 otherwise);
it reveals only the workspace id, which every hosted page's address
already carries. Serving pages on these hostnames also needs the
deployment's edge to accept them and obtain certificates, an operator
decision recorded in P12-D.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import route_not_found
from saas_os.api.route_policy import public_route

from crm_app import custom_domains
from crm_app.api.forms import _address_limit
from crm_app.api.records import IfMatch, _http, _version
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["domains"])
public_router = APIRouter(prefix="/v1/public/domains", tags=["domains"])

Read = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]
Manage = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "update"))]


class DomainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str = Field(max_length=300)


class DomainOut(BaseModel):
    id: uuid.UUID
    hostname: str
    status: Literal["pending", "verified", "lapsed"]
    record_name: str
    record_value: str
    expires_at: datetime | None
    verified_at: datetime | None
    checked_at: datetime | None
    last_error: str | None
    created_at: datetime
    version: int


class DomainList(BaseModel):
    items: list[DomainOut]


class Resolved(BaseModel):
    workspace_id: uuid.UUID


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, custom_domains.DomainRuleError):
        return HTTPException(exc.status, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


_LIST = "/{tenant_id}/domains"
_ONE = f"{_LIST}/{{domain_id}}"


@router.get(_LIST, response_model=DomainList, name="list_domains")
def list_domains(context: Read) -> Any:
    return {"items": custom_domains.list_domains(_scope(context))}


@router.post(_LIST, status_code=201, response_model=DomainOut, name="add_domain")
def add_domain(body: DomainIn, context: Manage, response: Response) -> Any:
    try:
        item = custom_domains.add(_scope(context), body.hostname)
    except RecordError as exc:
        raise _refusal(exc) from None
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


@router.post(f"{_ONE}/check", response_model=DomainOut, name="check_domain")
def check_domain(
    domain_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    expected = _version(if_match)
    try:
        item = custom_domains.check(_scope(context), domain_id, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


@router.delete(_ONE, status_code=204, name="remove_domain")
def remove_domain(domain_id: uuid.UUID, context: Manage) -> Response:
    try:
        custom_domains.remove(_scope(context), domain_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


_public = Depends(
    public_route(
        "which workspace a verified custom domain belongs to, for its hosted pages;"
        " the Host header, not a session, names it"
    )
)


@public_router.get(
    "/resolve", response_model=Resolved, dependencies=[_public], name="resolve_domain"
)
async def resolve_domain(request: Request) -> Any:
    await _address_limit(request)
    host = request.headers.get("host", "")
    workspace = await run_in_threadpool(custom_domains.workspace_for_host, host)
    if workspace is None:
        raise route_not_found()
    return {"workspace_id": workspace}
