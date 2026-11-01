"""Sending domain routes (decision P6-D, slice 6D).

    GET    /v1/workspaces/{tenant_id}/sending-domains                    crm_app.workspace:read
    POST   /v1/workspaces/{tenant_id}/sending-domains                    crm_app.workspace:update
    POST   /v1/workspaces/{tenant_id}/sending-domains/{id}/verify        crm_app.workspace:update
    DELETE /v1/workspaces/{tenant_id}/sending-domains/{id}               crm_app.workspace:update
    POST   /v1/workspaces/{tenant_id}/sending-domains/{id}/identities    crm_app.workspace:update
    PATCH  /v1/workspaces/{tenant_id}/sender-identities/{id}             crm_app.workspace:update
    DELETE /v1/workspaces/{tenant_id}/sender-identities/{id}             crm_app.workspace:update

`verify` and the identity `PATCH` need `If-Match`. The list says whether a
provider is configured; without one, domains are kept as
`not_registered` and nothing is created at Resend.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import sending_domains
from crm_app.api.records import IfMatch, _http, _version
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["sending domains"])

Read = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]
Manage = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "update"))]

Status = Literal[
    "not_registered",
    "not_started",
    "pending",
    "verified",
    "failed",
    "temporary_failure",
    "unknown",
]


class DomainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(max_length=300)


class IdentityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_part: str = Field(max_length=100)
    for_conversation: bool = False
    for_campaign: bool = False
    default_conversation: bool = False
    default_campaign: bool = False


class IdentityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    for_conversation: bool | None = None
    for_campaign: bool | None = None
    default_conversation: bool | None = None
    default_campaign: bool | None = None
    status: Literal["active", "disabled"] | None = None


class RecordOut(BaseModel):
    record: str
    type: str
    name: str
    value: str
    ttl: str | None
    priority: int | None
    status: str


class IdentityOut(BaseModel):
    id: uuid.UUID
    address: str
    for_conversation: bool
    for_campaign: bool
    default_conversation: bool
    default_campaign: bool
    status: Literal["active", "disabled"]
    usable: bool
    version: int


class SendingDomainOut(BaseModel):
    id: uuid.UUID
    domain: str
    status: Status
    records: list[RecordOut]
    last_error: str | None
    checked_at: datetime | None
    created_at: datetime
    version: int
    identities: list[IdentityOut]


class SendingDomainList(BaseModel):
    items: list[SendingDomainOut]
    provider_configured: bool


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, sending_domains.DomainRuleError):
        return HTTPException(exc.status, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_LIST = "/{tenant_id}/sending-domains"
_ONE = f"{_LIST}/{{domain_id}}"
_IDENTITY = "/{tenant_id}/sender-identities/{identity_id}"


@router.get(_LIST, response_model=SendingDomainList, name="list_sending_domains")
def list_sending_domains(context: Read) -> Any:
    return {
        "items": sending_domains.list_domains(_scope(context)),
        "provider_configured": sending_domains.configured_provider() is not None,
    }


@router.post(_LIST, status_code=201, response_model=SendingDomainOut, name="add_sending_domain")
async def add_sending_domain(body: DomainIn, context: Manage, response: Response) -> Any:
    try:
        item = await run_in_threadpool(sending_domains.register, _scope(context), body.domain)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(f"{_ONE}/verify", response_model=SendingDomainOut, name="verify_sending_domain")
async def verify_sending_domain(
    domain_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    expected = _version(if_match)
    try:
        item = await run_in_threadpool(
            lambda: sending_domains.verify(_scope(context), domain_id, expected_version=expected)
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_ONE, status_code=204, name="remove_sending_domain")
def remove_sending_domain(domain_id: uuid.UUID, context: Manage) -> Response:
    try:
        sending_domains.remove(_scope(context), domain_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


@router.post(
    f"{_ONE}/identities",
    status_code=201,
    response_model=IdentityOut,
    name="add_sender_identity",
)
def add_sender_identity(
    domain_id: uuid.UUID, body: IdentityIn, context: Manage, response: Response
) -> Any:
    flags = body.model_dump(exclude={"local_part"})
    try:
        item = sending_domains.add_identity(
            _scope(context), domain_id, local_part=body.local_part, flags=flags
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.patch(_IDENTITY, response_model=IdentityOut, name="update_sender_identity")
def update_sender_identity(
    identity_id: uuid.UUID,
    body: IdentityPatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, detail={"code": "value_required"})
    try:
        item = sending_domains.update_identity(
            _scope(context), identity_id, changes, expected_version=expected
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_IDENTITY, status_code=204, name="remove_sender_identity")
def remove_sender_identity(identity_id: uuid.UUID, context: Manage) -> Response:
    try:
        sending_domains.remove_identity(_scope(context), identity_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)
