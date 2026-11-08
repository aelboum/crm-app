"""Integration and API-key routes (decision P12-K).

All need `crm_app.integration:manage`, under /v1/workspaces/{tenant_id}:

    GET    /integrations                                 list
    POST   /integrations                                 create (name, role)
    POST   /integrations/{id}/disable                    revoke its keys, disable
    POST   /integrations/{id}/keys                       issue a key, shown once
    POST   /integrations/{id}/keys/{key_id}/revoke       revoke a key

A member's session only: none of these accepts an API key, so a key can
never mint, see or revoke keys. SaaS-OS checks its own permissions inside
each change as well (`crm_app.integrations`). The response that issues a
key is the only one that carries it, and is never cached.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import integrations
from crm_app.api.webhooks import router as webhooks_router
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["integrations"])
# Webhook endpoints sit in Settings > Integrations too (P12-H); exported here
# so the app registers both from one import (`routers`).
__all__ = ["router", "routers"]

Manage = Annotated[RequestContext, Depends(require_permission("crm_app.integration", "manage"))]
# P12-N: every role reads integrations' names, as it reads members' names.
ReadNames = Annotated[RequestContext, Depends(require_permission("membership", "read"))]


class IntegrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=4 * integrations.NAME_MAX)
    role: Literal["Member", "Read-only"]


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=4 * integrations.NAME_MAX)
    # 30, 90 or 365; null never expires.
    expires_in_days: int | None = None


class KeyOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class IntegrationOut(BaseModel):
    id: uuid.UUID
    name: str
    status: Literal["active", "disabled"]
    # Null only if its role was removed outside LeadStack.
    role: Literal["Member", "Read-only"] | None
    created_at: datetime
    keys: list[KeyOut]


class IntegrationList(BaseModel):
    items: list[IntegrationOut]


class IntegrationName(BaseModel):
    id: uuid.UUID
    name: str


class IntegrationNameList(BaseModel):
    items: list[IntegrationName]


class IssuedKey(BaseModel):
    key: KeyOut
    # The key itself, shown once: send it as the `X-API-Key` header.
    secret: str


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _http(exc: RecordError) -> HTTPException:
    detail: dict[str, Any] = {"code": exc.code}
    if isinstance(exc, integrations.IntegrationError):
        detail["detail"] = exc.detail
    return HTTPException(status_code=exc.status, detail=detail)


_ITEM = "/{tenant_id}/integrations/{integration_id}"


@router.get(
    "/{tenant_id}/integration-names",
    response_model=IntegrationNameList,
    name="list_integration_names",
)
def list_integration_names(tenant_id: uuid.UUID, context: ReadNames) -> dict[str, Any]:
    """Who made an entry, by name, for every role (P12-N)."""
    return {"items": integrations.names(context.tenant_id)}


@router.get("/{tenant_id}/integrations", response_model=IntegrationList, name="list_integrations")
def list_integrations(tenant_id: uuid.UUID, context: Manage) -> dict[str, Any]:
    return {"items": integrations.list_integrations(_scope(context))}


@router.post(
    "/{tenant_id}/integrations",
    status_code=201,
    response_model=IntegrationOut,
    name="create_integration",
)
def create_integration(
    tenant_id: uuid.UUID, body: IntegrationIn, context: Manage
) -> dict[str, Any]:
    try:
        return integrations.create(_scope(context), body.name, body.role)
    except RecordError as exc:
        raise _http(exc) from None


@router.post(f"{_ITEM}/disable", response_model=IntegrationOut, name="disable_integration")
def disable_integration(
    tenant_id: uuid.UUID, integration_id: uuid.UUID, context: Manage
) -> dict[str, Any]:
    try:
        return integrations.disable(_scope(context), integration_id)
    except RecordError as exc:
        raise _http(exc) from None


@router.post(
    f"{_ITEM}/keys", status_code=201, response_model=IssuedKey, name="create_integration_key"
)
def create_key(
    tenant_id: uuid.UUID,
    integration_id: uuid.UUID,
    body: KeyIn,
    context: Manage,
    response: Response,
) -> dict[str, Any]:
    try:
        key, secret = integrations.create_key(
            _scope(context), integration_id, body.name, body.expires_in_days
        )
    except RecordError as exc:
        raise _http(exc) from None
    response.headers["Cache-Control"] = "no-store"
    return {"key": key, "secret": secret}


@router.post(f"{_ITEM}/keys/{{key_id}}/revoke", status_code=204, name="revoke_integration_key")
def revoke_key(
    tenant_id: uuid.UUID, integration_id: uuid.UUID, key_id: uuid.UUID, context: Manage
) -> Response:
    try:
        integrations.revoke_key(_scope(context), integration_id, key_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)


routers = (router, webhooks_router)
