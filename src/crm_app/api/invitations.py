"""Invitation routes (`PHASE2-PLAN.md` §8.2; decisions Q4, Q5, P2-F).

    GET  /v1/workspaces/{tenant_id}/invitations                          invitation:read
    POST /v1/workspaces/{tenant_id}/invitations                          invitation:create
    POST /v1/workspaces/{tenant_id}/invitations/{invitation_id}/revoke   invitation:revoke

Owner and Admin hold all three (Q6). Inviting an Owner also needs
`crm_app.owner:manage` (Owner only), checked here with SaaS-OS `can()`, as
for every other Owner change. Creating is rate-limited per inviter.

Acceptance is SaaS-OS's own route, mounted by `create_app()`:
`POST /v1/tenants/{tenant_id}/invitations/accept` (signed in, the session's
verified email must be the invited one; one indistinguishable 404 for
every refusal; rate-limited per person).

The response to a manual-mode create carries the invitation link with its
token, once (`Cache-Control: no-store`, `crm_app.api.headers`); nothing
else ever does. Refusals carry a code, never the address or the link.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import rate_limited, service_unavailable
from saas_os.core.rbac import can
from saas_os.infra.ratelimit import (
    RateLimitBackendError,
    RateLimitExceededError,
    enforce_rate_limit,
    get_ratelimit_config,
)

from crm_app import invitations
from crm_app.domains import records as values
from crm_app.records import RecordError, Scope
from crm_app.roles import Role

router = APIRouter(prefix="/v1/workspaces", tags=["invitations"])

ReadInvitations = Annotated[RequestContext, Depends(require_permission("invitation", "read"))]
RevokeInvitation = Annotated[RequestContext, Depends(require_permission("invitation", "revoke"))]
_create_policy = require_permission("invitation", "create")

_RETRY_AFTER_SECONDS = 5


async def _inviter(context: Annotated[RequestContext, Depends(_create_policy)]) -> RequestContext:
    """The admitted inviter, after a per-inviter limit; a limiter failure
    refuses rather than allows."""
    try:
        await enforce_rate_limit(
            f"invitation-create:{context.actor_id}", config=get_ratelimit_config()
        )
    except RateLimitExceededError as exc:
        raise rate_limited(exc.retry_after_seconds) from None
    except RateLimitBackendError:
        raise service_unavailable(_RETRY_AFTER_SECONDS) from None
    return context


CreateInvitation = Annotated[RequestContext, Depends(_inviter)]

RoleName = Literal["Owner", "Admin", "Member", "Read-only"]
Status = Literal["pending", "accepted", "expired", "revoked"]


class InvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=values.EMAIL_MAX + 8)
    role: RoleName

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        normalised = values.email(value)
        if normalised is None:
            raise values.InvalidValue("is required")
        return normalised


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: RoleName | None
    delivery: Literal["manual", "email"] | None
    status: Status
    invited_by_user_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    accepted_by_user_id: uuid.UUID | None


class CreatedInvitation(BaseModel):
    invitation: InvitationOut
    # Manual mode only: the link to hand over yourself, shown this once.
    link: str | None


class InvitationList(BaseModel):
    items: list[InvitationOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _http(exc: RecordError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


@router.get("/{tenant_id}/invitations", response_model=InvitationList)
def list_invitations(tenant_id: uuid.UUID, context: ReadInvitations) -> Any:
    return {"items": invitations.list_invitations(_scope(context))}


@router.post("/{tenant_id}/invitations", status_code=201, response_model=CreatedInvitation)
def create_invitation(tenant_id: uuid.UUID, body: InvitationIn, context: CreateInvitation) -> Any:
    may_invite_owner = can(
        actor_id=context.actor_id,
        tenant_id=context.tenant_id,
        action="manage",
        resource="crm_app.owner",
    )
    try:
        created = invitations.create(
            _scope(context),
            body.email,
            Role(body.role),
            may_invite_owner=may_invite_owner,
            origin=os.environ["PUBLIC_APP_ORIGIN"].rstrip("/"),
        )
    except RecordError as exc:
        raise _http(exc) from None
    return {"invitation": created.invitation, "link": created.link}


@router.post("/{tenant_id}/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(
    tenant_id: uuid.UUID, invitation_id: uuid.UUID, context: RevokeInvitation
) -> Any:
    try:
        return invitations.revoke(_scope(context), invitation_id)
    except RecordError as exc:
        raise _http(exc) from None
