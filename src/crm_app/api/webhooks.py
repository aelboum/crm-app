"""Webhook endpoint routes (decision P12-H).

All need `crm_app.integration:manage`, under /v1/workspaces/{tenant_id}:

    GET    /webhooks                     endpoints with their recent deliveries
    POST   /webhooks                     add an HTTPS endpoint; its secret, once
    DELETE /webhooks/{id}                remove it

A member's session only: none accepts an API key. SaaS-OS checks its own
`webhook_subscription` permissions inside each change as well. The
response that carries the signing secret is never cached.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import webhooks
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["webhooks"])

Manage = Annotated[RequestContext, Depends(require_permission("crm_app.integration", "manage"))]


class EndpointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=webhooks.URL_MAX)


class DeliveryOut(BaseModel):
    id: uuid.UUID
    event: str
    # SaaS-OS's outbox status: pending, published or dead_lettered.
    status: str
    attempts: int
    created_at: datetime
    published_at: datetime | None
    last_error: str | None


class EndpointOut(BaseModel):
    id: uuid.UUID
    # Without its query string, which may carry the receiver's token.
    url: str
    created_at: datetime
    deliveries: list[DeliveryOut]


class EndpointList(BaseModel):
    items: list[EndpointOut]
    events: list[str]


class AddedEndpoint(BaseModel):
    endpoint: EndpointOut
    # Shown once: verify `X-Webhook-Signature` with it.
    signing_secret: str


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _http(exc: RecordError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


@router.get("/{tenant_id}/webhooks", response_model=EndpointList, name="list_webhooks")
def list_webhooks(tenant_id: uuid.UUID, context: Manage) -> dict[str, Any]:
    return {"items": webhooks.list_endpoints(_scope(context)), "events": list(webhooks.EVENTS)}


@router.post(
    "/{tenant_id}/webhooks", status_code=201, response_model=AddedEndpoint, name="add_webhook"
)
def add_webhook(
    tenant_id: uuid.UUID, body: EndpointIn, context: Manage, response: Response
) -> dict[str, Any]:
    try:
        endpoint, secret = webhooks.add(_scope(context), body.url)
    except RecordError as exc:
        raise _http(exc) from None
    response.headers["Cache-Control"] = "no-store"
    return {"endpoint": endpoint, "signing_secret": secret}


@router.delete("/{tenant_id}/webhooks/{endpoint_id}", status_code=204, name="remove_webhook")
def remove_webhook(tenant_id: uuid.UUID, endpoint_id: uuid.UUID, context: Manage) -> Response:
    try:
        webhooks.remove(_scope(context), endpoint_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)
