"""Campaign routes (decision P7-C, slice 7C).

    GET    /v1/workspaces/{tenant_id}/campaigns                    crm_app.campaign:read
    POST   /v1/workspaces/{tenant_id}/campaigns                    crm_app.campaign:manage
    GET    /v1/workspaces/{tenant_id}/campaigns/{id}               crm_app.campaign:read
    PATCH  /v1/workspaces/{tenant_id}/campaigns/{id}               crm_app.campaign:manage
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/validate      crm_app.campaign:manage
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/submit        crm_app.campaign:manage
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/cancel        crm_app.campaign:manage
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/approve       crm_app.campaign:approve
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/reject        crm_app.campaign:approve
    POST   /v1/workspaces/{tenant_id}/campaigns/{id}/queue         crm_app.campaign:approve
    POST   /v1/public/unsubscribe/{workspace_id}/{token}           public, one-click

Every change needs `If-Match`. Editing returns a campaign to draft and
clears its approval. Queuing answers 409 `campaign_sending_unavailable`
until campaign sending is available (it is not: no `List-Unsubscribe`
support in SaaS-OS v0.6.0, and production email is not authorized), so no
route sends a campaign. The unsubscribe route takes the token from a
recipient's link; it answers 204 whether or not the token is known, so it
reveals nothing, and is limited per client address.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.route_policy import public_route

from crm_app import campaigns
from crm_app.api.forms import _limited
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import campaigns as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["campaigns"])
public_router = APIRouter(prefix="/v1/public/unsubscribe", tags=["campaigns"])

RESOURCE = "crm_app.campaign"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Manage = Annotated[RequestContext, Depends(require_permission(RESOURCE, "manage"))]
Approve = Annotated[RequestContext, Depends(require_permission(RESOURCE, "approve"))]

_TOKEN = re.compile(r"[0-9a-f]{32}")


class SegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: list[str] = Field(default_factory=list, max_length=10)
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=rules.FILTER_MAX)
    owner_ids: list[uuid.UUID] = Field(default_factory=list, max_length=rules.FILTER_MAX)
    company_ids: list[uuid.UUID] = Field(default_factory=list, max_length=rules.FILTER_MAX)
    all_contacts: bool = False


class CampaignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=4 * rules.NAME_MAX)
    subject: str = Field(max_length=4 * rules.SUBJECT_MAX)
    body: str = Field(max_length=2 * rules.BODY_MAX)
    segment: SegmentIn


class CampaignPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=4 * rules.NAME_MAX)
    subject: str | None = Field(default=None, max_length=4 * rules.SUBJECT_MAX)
    body: str | None = Field(default=None, max_length=2 * rules.BODY_MAX)
    segment: SegmentIn | None = None


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(max_length=2000)


class Estimate(BaseModel):
    eligible: int
    excluded: dict[str, int]


class SegmentOut(BaseModel):
    stages: list[str]
    tag_ids: list[uuid.UUID]
    owner_ids: list[uuid.UUID]
    company_ids: list[uuid.UUID]
    all_contacts: bool


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    subject: str
    body: str
    segment: SegmentOut
    status: Literal[
        "draft",
        "validated",
        "awaiting_approval",
        "approved",
        "queued",
        "processing",
        "completed",
        "partially_completed",
        "failed",
        "rejected",
        "cancelled",
    ]
    estimate: Estimate | None
    content_hash: str
    approved: bool
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    submitted_by_user_id: uuid.UUID | None
    submitted_at: datetime | None
    decision_note: str | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    version: int


class CampaignList(BaseModel):
    items: list[CampaignOut]
    sending_available: bool


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, (campaigns.CampaignRuleError, campaigns.CampaignStateError)):
        return HTTPException(exc.status, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_LIST = "/{tenant_id}/campaigns"
_ONE = f"{_LIST}/{{campaign_id}}"


@router.get(_LIST, response_model=CampaignList, name="list_campaigns")
def list_campaigns(context: Read) -> Any:
    return {
        "items": campaigns.list_campaigns(_scope(context)),
        "sending_available": campaigns.sending_available(),
    }


@router.post(_LIST, status_code=201, response_model=CampaignOut, name="create_campaign")
def create_campaign(body: CampaignIn, context: Manage, response: Response) -> Any:
    try:
        item = campaigns.create(
            _scope(context),
            name=body.name,
            subject=body.subject,
            body=body.body,
            segment=body.segment.model_dump(mode="json"),
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.get(_ONE, response_model=CampaignOut, name="get_campaign")
def get_campaign(campaign_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, campaigns.get(_scope(context), campaign_id))
    except RecordError as exc:
        raise _refusal(exc) from None


@router.patch(_ONE, response_model=CampaignOut, name="update_campaign")
def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignPatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set, mode="json")
    if any(value is None for value in changes.values()):
        raise HTTPException(422, detail={"code": "value_required"})
    try:
        item = campaigns.update(_scope(context), campaign_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


def _step(
    step: Any,
    campaign_id: uuid.UUID,
    context: RequestContext,
    response: Response,
    if_match: str | None,
) -> Any:
    expected = _version(if_match)
    try:
        item = step(_scope(context), campaign_id, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(f"{_ONE}/validate", response_model=CampaignOut, name="validate_campaign")
def validate_campaign(
    campaign_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    return _step(campaigns.validate, campaign_id, context, response, if_match)


@router.post(f"{_ONE}/submit", response_model=CampaignOut, name="submit_campaign")
def submit_campaign(
    campaign_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    return _step(campaigns.submit, campaign_id, context, response, if_match)


@router.post(f"{_ONE}/cancel", response_model=CampaignOut, name="cancel_campaign")
def cancel_campaign(
    campaign_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    return _step(campaigns.cancel, campaign_id, context, response, if_match)


@router.post(f"{_ONE}/approve", response_model=CampaignOut, name="approve_campaign")
def approve_campaign(
    campaign_id: uuid.UUID, context: Approve, response: Response, if_match: IfMatch = None
) -> Any:
    return _step(campaigns.approve, campaign_id, context, response, if_match)


@router.post(f"{_ONE}/reject", response_model=CampaignOut, name="reject_campaign")
def reject_campaign(
    campaign_id: uuid.UUID,
    body: RejectIn,
    context: Approve,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        item = campaigns.reject(
            _scope(context), campaign_id, note=body.note, expected_version=expected
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(f"{_ONE}/queue", response_model=CampaignOut, name="queue_campaign")
def queue_campaign(
    campaign_id: uuid.UUID, context: Approve, response: Response, if_match: IfMatch = None
) -> Any:
    return _step(campaigns.queue, campaign_id, context, response, if_match)


_public = Depends(
    public_route(
        "a campaign recipient's one-click unsubscribe; the token from the email's link,"
        " not a session, identifies the recipient"
    )
)


@public_router.post(
    "/{workspace_id}/{token}", status_code=204, dependencies=[_public], name="unsubscribe"
)
async def unsubscribe(workspace_id: uuid.UUID, token: str, request: Request) -> Response:
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"unsubscribe:{address}")
    if _TOKEN.fullmatch(token):
        await run_in_threadpool(campaigns.unsubscribe, workspace_id, token)
    return Response(status_code=204)
