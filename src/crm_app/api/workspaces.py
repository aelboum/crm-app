"""Read-only workspace routes (PHASE2-PLAN.md §11, S3).

A workspace is a SaaS-OS tenant (decision D-WS). Each route depends on
`require_permission`, which authenticates the caller, admits the request
only if the caller has a membership row in that exact workspace (one
indistinguishable 404 for an unknown workspace, a closed one, or one the
caller does not belong to) and then checks the permission (403). The
workspace used afterwards is `context.tenant_id`, never the raw path value.

Changing memberships or roles is deliberately not offered here: those
routes wait for the last-Owner safeguard (PHASE2-PLAN.md §5.4, §11.1).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.identity import list_tenant_members
from saas_os.core.rbac import can, list_membership_roles, list_roles
from saas_os.core.tenancy import get_tenant

from crm_app.domains.membership import MANAGE_SUSPENDED, visible_statuses

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

ReadWorkspace = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]
ReadMembers = Annotated[RequestContext, Depends(require_permission("membership", "read"))]

MAX_PAGE_SIZE = 200


class Workspace(BaseModel):
    id: uuid.UUID
    name: str
    status: str


class Member(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    roles: list[str]


class MemberPage(BaseModel):
    items: list[Member]
    total: int
    limit: int
    offset: int


@router.get("/{tenant_id}", response_model=Workspace)
def get_workspace(tenant_id: uuid.UUID, context: ReadWorkspace) -> Workspace:
    tenant = get_tenant(context.tenant_id)
    return Workspace(id=tenant.id, name=tenant.name, status=tenant.status)


@router.get("/{tenant_id}/members", response_model=MemberPage)
def list_members(
    tenant_id: uuid.UUID,
    context: ReadMembers,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberPage:
    """Active members for everyone with `membership:read`; suspended ones
    only for callers who may reactivate them; revoked ones never
    (`crm_app.domains.membership`)."""
    workspace = context.tenant_id
    resource, action = MANAGE_SUSPENDED
    statuses = visible_statuses(
        may_reactivate=can(
            actor_id=context.actor_id, tenant_id=workspace, action=action, resource=resource
        )
    )
    memberships = sorted(
        (m for m in list_tenant_members(workspace) if m.status in statuses),
        key=lambda m: str(m.id),
    )
    page = memberships[offset : offset + limit]
    role_names = {role.id: role.name for role in list_roles(workspace)} if page else {}
    items = [
        Member(
            membership_id=m.id,
            user_id=m.user_id,
            status=m.status,
            roles=sorted(
                role_names[a.role_id]
                for a in list_membership_roles(workspace, m.id)
                if a.role_id in role_names
            ),
        )
        for m in page
    ]
    return MemberPage(items=items, total=len(memberships), limit=limit, offset=offset)
