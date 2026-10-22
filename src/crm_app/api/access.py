"""What the caller may do in one workspace (PHASE2-PLAN.md §11.3, F1).

The frontend uses this to show only the actions the caller holds. It is a
convenience, never the enforcement: every changing route still checks its
own permission and the Owner rules (`crm_app.api.members`).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.identity import get_membership
from saas_os.core.rbac import can, list_membership_roles, list_roles

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

ReadWorkspace = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]

# The actions the frontend offers, each with the permission that admits it.
ACTIONS: dict[str, tuple[str, str]] = {
    "read_members": ("membership", "read"),
    "assign_role": ("membership_role", "create"),
    "remove_role": ("membership_role", "delete"),
    "suspend_member": ("membership", "suspend"),
    "reactivate_member": ("membership", "reactivate"),
    "revoke_member": ("membership", "revoke"),
    "manage_owners": ("crm_app.owner", "manage"),
}


class Access(BaseModel):
    membership_id: uuid.UUID
    roles: list[str]
    actions: dict[str, bool]


@router.get("/{tenant_id}/access", response_model=Access)
def get_access(tenant_id: uuid.UUID, context: ReadWorkspace) -> Access:
    workspace = context.tenant_id
    membership = get_membership(workspace, context.actor_id)
    if membership is None:
        # require_permission admitted the caller, so the row existed a moment ago.
        raise RuntimeError("membership disappeared after authorization")
    names = {role.id: role.name for role in list_roles(workspace)}
    roles = sorted(
        names[a.role_id]
        for a in list_membership_roles(workspace, membership.id)
        if a.role_id in names
    )
    actions = {
        name: can(actor_id=context.actor_id, tenant_id=workspace, action=action, resource=resource)
        for name, (resource, action) in ACTIONS.items()
    }
    return Access(membership_id=membership.id, roles=roles, actions=actions)
