"""The steps that give a new workspace its roles and its first Owner, shared
by the operator command (`crm_app.provision`) and self-service signup
(`crm_app.signups`; `SIGNUP-PLAN.md` §4, Stage B).

Each step is find-or-create and runs in SaaS-OS's own transactions, so a
caller that is interrupted can run it again and get the same result. Only
public SaaS-OS functions are used, with `SystemCaller(PROVISIONING)`. No
principal holds any permission until `assign_owner()` has run.

The callers differ in when the workspace becomes active: the operator
command activates first (its tested behaviour), signup activates last,
after `owner_verified()` has passed.

SaaS-OS resolves configuration at import time, so its imports are inside
the functions.
"""

from __future__ import annotations

import uuid
from typing import Any

from crm_app.roles import ROLE_TEMPLATES, Role

# What the Owner must hold before a signup workspace is activated: the
# right to give roles (ADR-0043 counts an Owner as an administrator by it)
# and the product's own Owner permission.
OWNER_CHECKS: tuple[tuple[str, str], ...] = (
    ("membership_role", "create"),
    ("crm_app.owner", "manage"),
)


def _caller() -> Any:
    from saas_os.core.authority import SystemAuthority, SystemCaller  # noqa: PLC0415

    return SystemCaller(SystemAuthority.PROVISIONING)


def roles_by_name(tenant_id: uuid.UUID) -> dict[str, Any]:
    from saas_os.core.rbac import list_roles  # noqa: PLC0415

    return {role.name: role for role in list_roles(tenant_id)}


def owner_held(tenant_id: uuid.UUID, membership: Any, roles: dict[str, Any]) -> bool:
    """Whether `membership` already holds the Owner role."""
    from saas_os.core.rbac import list_membership_roles  # noqa: PLC0415

    owner = roles.get(Role.OWNER.value)
    return (
        membership is not None
        and owner is not None
        and any(a.role_id == owner.id for a in list_membership_roles(tenant_id, membership.id))
    )


def seed_roles(tenant_id: uuid.UUID, performed: list[str]) -> dict[str, Any]:
    """The four product roles with their permissions; returns them by name.
    Call only while no principal holds authority in the workspace."""
    from saas_os.core.rbac import (  # noqa: PLC0415
        DuplicatePermissionGrantError,
        DuplicateRoleNameError,
        create_role,
        grant_permission,
        register_permission,
    )

    caller = _caller()
    roles = roles_by_name(tenant_id)
    for role, keys in ROLE_TEMPLATES.items():
        if role.value not in roles:
            try:
                roles[role.value] = create_role(tenant_id, role.value, caller=caller)
                performed.append(f"role {role.value} created")
            except DuplicateRoleNameError:
                roles = roles_by_name(tenant_id)
        role_id = roles[role.value].id
        granted = 0
        for resource, action in sorted(keys):
            permission = register_permission(resource, action)
            try:
                grant_permission(tenant_id, role_id, permission.id, caller=caller)
                granted += 1
            except DuplicatePermissionGrantError:
                pass
        if granted:
            performed.append(f"{granted} permission(s) granted to {role.value}")
    return roles


def ensure_membership(tenant_id: uuid.UUID, user_id: uuid.UUID, performed: list[str]) -> Any:
    """The person's membership of the workspace, created if missing."""
    from saas_os.core.identity import add_tenant_membership, get_membership  # noqa: PLC0415

    membership = get_membership(tenant_id, user_id)
    if membership is None:
        membership = add_tenant_membership(tenant_id, user_id, caller=_caller())
        performed.append("owner membership created")
    return membership


def assign_owner(
    tenant_id: uuid.UUID, membership_id: uuid.UUID, roles: dict[str, Any], performed: list[str]
) -> None:
    """The Owner role for the workspace's first member; a repeat is a no-op."""
    from saas_os.core.rbac import (  # noqa: PLC0415
        DuplicateRoleAssignmentError,
        assign_first_role_for_new_tenant,
    )

    try:
        assign_first_role_for_new_tenant(
            tenant_id, membership_id, roles[Role.OWNER.value].id, caller=_caller()
        )
        performed.append("Owner role assigned")
    except DuplicateRoleAssignmentError:
        pass


def owner_verified(
    tenant_id: uuid.UUID, user_id: uuid.UUID, checks: tuple[tuple[str, str], ...] = OWNER_CHECKS
) -> bool:
    """Whether the person passes every check through SaaS-OS's own `can()`."""
    from saas_os.core.rbac import can  # noqa: PLC0415

    return all(
        can(actor_id=user_id, tenant_id=tenant_id, action=action, resource=resource)
        for resource, action in checks
    )
