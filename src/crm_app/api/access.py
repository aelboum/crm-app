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
from saas_os.api.errors import not_found
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
    # Workspace settings (decision P2-F 1).
    "update_workspace": ("crm_app.workspace", "update"),
    # Invitations (decisions Q4, Q5, P2-F); inviting an Owner also needs
    # manage_owners.
    "read_invitations": ("invitation", "read"),
    "create_invitation": ("invitation", "create"),
    "revoke_invitation": ("invitation", "revoke"),
    # Contact and company records (slice 3A, decision P3-A): create, update
    # (which covers archive and restore) and permanent delete.
    "create_contact": ("crm_app.contact", "create"),
    "update_contact": ("crm_app.contact", "update"),
    "delete_contact": ("crm_app.contact", "delete"),
    "create_company": ("crm_app.company", "create"),
    "update_company": ("crm_app.company", "update"),
    "delete_company": ("crm_app.company", "delete"),
    # Notes (slice 3B, decision P3-B D3): adding one, and changing any note
    # rather than only one's own. Each note also carries `can_edit` and
    # `can_delete` for the caller.
    "create_note": ("crm_app.activity", "create"),
    "edit_any_note": ("crm_app.activity", "update"),
    "delete_any_note": ("crm_app.activity", "delete"),
    # Contacts export (slice 3E): Owner and Admin. Display only; the export
    # route enforces the permission itself.
    "export_records": ("crm_app.crm_data", "export"),
    "import_records": ("crm_app.crm_data", "import"),
    # The sales pipeline and its stages (decision P4 4A.4).
    "manage_pipeline": ("crm_app.pipeline", "manage"),
    # Deals (decision P4-B 6): create, update (stages and outcomes too) and
    # delete.
    "create_opportunity": ("crm_app.opportunity", "create"),
    "update_opportunity": ("crm_app.opportunity", "update"),
    "delete_opportunity": ("crm_app.opportunity", "delete"),
    # Tasks (decision P4-C 3): Members may delete them too (Q6).
    "create_task": ("crm_app.task", "create"),
    "update_task": ("crm_app.task", "update"),
    "delete_task": ("crm_app.task", "delete"),
    # Appointments (decision P5-A 6): Owner and Admin delete; everyone
    # else with update cancels instead.
    "create_appointment": ("crm_app.appointment", "create"),
    "update_appointment": ("crm_app.appointment", "update"),
    "delete_appointment": ("crm_app.appointment", "delete"),
    # Forms (decision P7-A 4): every role reads; Owner and Admin manage.
    "read_forms": ("crm_app.form", "read"),
    "manage_forms": ("crm_app.form", "manage"),
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
        # Removed between `require_permission` and this read: answer as for
        # any non-member (the same 404 SaaS-OS gives), never a server error
        # (PHASE2-SECURITY-REVIEW.md I2, decision P2-F).
        raise not_found("tenant")
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
