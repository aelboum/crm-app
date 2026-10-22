"""Create a workspace with the four product roles and its first Owner.

    python -m crm_app.provision --name "Acme Ltd" \\
        --owner-issuer https://<zitadel-instance> --owner-subject <OIDC sub> \\
        [--dry-run] [--confirm-production]

An operator command, never an HTTP route (decision P2-C; PHASE2-PLAN.md
§7.4, gate G2). It uses only public SaaS-OS functions and
`SystemCaller(PROVISIONING)`, whose documented purpose includes "a
consumer's own provisioning/seed code", for the tenant's initial authority
structure. Every step before the last is inert; the Owner role is assigned
last, so no principal holds any permission until the structure is complete.

Steps run in separate transactions, as in SaaS-OS's own bootstrap, so each
one is find-or-create: a re-run after a crash resumes, and a re-run after
success changes nothing. A same-name workspace is resumed only if it has no
members or only this owner; otherwise the command refuses.

Prints identifiers only: never a URL, a credential or a token.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from crm_app.roles import ROLE_TEMPLATES, Role
from crm_app.settings import Process, validate_settings

OWNER_CHECK = ("crm_app.owner", "manage")


class ProvisioningRefusedError(RuntimeError):
    """The command will not act; the message says why."""


@dataclass(frozen=True)
class Request:
    name: str
    owner_issuer: str
    owner_subject: str
    dry_run: bool = False


@dataclass
class Result:
    tenant_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    membership_id: uuid.UUID | None = None
    performed: list[str] = field(default_factory=list)


def require_production_confirmation(environment: str, confirmed: bool) -> None:
    if environment == "production" and not confirmed:
        raise ProvisioningRefusedError(
            "ENVIRONMENT is production: pass --confirm-production to provision."
        )


def validate_request(request: Request) -> None:
    for label, value in (
        ("name", request.name),
        ("owner issuer", request.owner_issuer),
        ("owner subject", request.owner_subject),
    ):
        if not value.strip():
            raise ProvisioningRefusedError(f"The {label} must not be empty.")
    if len(request.name) > 255:
        raise ProvisioningRefusedError("The name must be at most 255 characters.")


def provision(request: Request) -> Result:  # noqa: PLR0912, PLR0915 - one ordered procedure
    """Run (or, with `dry_run`, only plan) the provisioning sequence."""
    # Imported here: SaaS-OS resolves configuration at import time.
    from saas_os.core.authority import SystemAuthority, SystemCaller  # noqa: PLC0415
    from saas_os.core.identity import (  # noqa: PLC0415
        add_tenant_membership,
        get_membership,
        get_or_create_user_for_external_identity,
        list_tenant_members,
    )
    from saas_os.core.rbac import (  # noqa: PLC0415
        DuplicatePermissionGrantError,
        DuplicateRoleAssignmentError,
        DuplicateRoleNameError,
        assign_first_role_for_new_tenant,
        can,
        create_role,
        grant_permission,
        list_membership_roles,
        list_roles,
        register_permission,
    )
    from saas_os.core.tenancy import (  # noqa: PLC0415
        TenantStatus,
        create_tenant,
        find_tenants_by_name,
        transition_tenant_status,
    )
    from saas_os.infra.db import get_engine, validate_application_role  # noqa: PLC0415

    validate_request(request)
    validate_application_role(get_engine())
    caller = SystemCaller(SystemAuthority.PROVISIONING)
    result = Result()

    matches = find_tenants_by_name(request.name)
    if len(matches) > 1:
        raise ProvisioningRefusedError("Several workspaces already have this name.")
    tenant = matches[0] if matches else None
    if tenant is not None and tenant.status not in (
        TenantStatus.PENDING.value,
        TenantStatus.ACTIVE.value,
    ):
        raise ProvisioningRefusedError(f"The workspace with this name is {tenant.status}.")

    if request.dry_run:
        result.tenant_id = tenant.id if tenant else None
        if tenant is None:
            result.performed.append("would create the workspace")
        else:
            members = list_tenant_members(tenant.id)
            result.performed.append(
                f"would resume the existing workspace ({len(members)} member(s); "
                "allowed only if none, or only this owner)"
            )
        result.performed.append("would create the roles, grants, owner membership and Owner role")
        return result

    # The user row is inert: it holds nothing until a role is assigned.
    user = get_or_create_user_for_external_identity(request.owner_issuer, request.owner_subject)
    result.owner_user_id = user.id

    if tenant is None:
        tenant = create_tenant(request.name, caller=caller)
        result.performed.append("workspace created")
    elif any(m.user_id != user.id for m in list_tenant_members(tenant.id)):
        raise ProvisioningRefusedError(
            "A workspace with this name already has other members; not claiming it."
        )
    result.tenant_id = tenant.id

    if tenant.status == TenantStatus.PENDING.value:
        transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=caller)
        result.performed.append("workspace activated")

    membership = get_membership(tenant.id, user.id)
    roles = {role.name: role for role in list_roles(tenant.id)}
    owner_held = (
        membership is not None
        and Role.OWNER.value in roles
        and any(
            a.role_id == roles[Role.OWNER.value].id
            for a in list_membership_roles(tenant.id, membership.id)
        )
    )

    # Roles and grants only while no principal holds authority.
    if not owner_held:
        for role, keys in ROLE_TEMPLATES.items():
            if role.value not in roles:
                try:
                    roles[role.value] = create_role(tenant.id, role.value, caller=caller)
                    result.performed.append(f"role {role.value} created")
                except DuplicateRoleNameError:
                    roles = {r.name: r for r in list_roles(tenant.id)}
            role_id = roles[role.value].id
            granted = 0
            for resource, action in sorted(keys):
                permission = register_permission(resource, action)
                try:
                    grant_permission(tenant.id, role_id, permission.id, caller=caller)
                    granted += 1
                except DuplicatePermissionGrantError:
                    pass
            if granted:
                result.performed.append(f"{granted} permission(s) granted to {role.value}")

        if membership is None:
            membership = add_tenant_membership(tenant.id, user.id, caller=caller)
            result.performed.append("owner membership created")
        try:
            assign_first_role_for_new_tenant(
                tenant.id, membership.id, roles[Role.OWNER.value].id, caller=caller
            )
            result.performed.append("Owner role assigned")
        except DuplicateRoleAssignmentError:
            pass

    if membership is None:
        raise ProvisioningRefusedError("Verification failed: no owner membership exists.")
    result.membership_id = membership.id
    resource, action = OWNER_CHECK
    if not can(actor_id=user.id, tenant_id=tenant.id, action=action, resource=resource):
        raise ProvisioningRefusedError("Verification failed: the owner does not hold Owner rights.")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crm_app.provision",
        description="Create a workspace, its four roles and its first Owner.",
    )
    parser.add_argument("--name", required=True, help="Display name of the workspace.")
    parser.add_argument("--owner-issuer", required=True, help="The owner's exact OIDC issuer.")
    parser.add_argument("--owner-subject", required=True, help="The owner's OIDC subject.")
    parser.add_argument("--dry-run", action="store_true", help="Report the plan; change nothing.")
    parser.add_argument(
        "--confirm-production", action="store_true", help="Required when ENVIRONMENT=production."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        require_production_confirmation(os.environ.get("ENVIRONMENT", ""), args.confirm_production)
        validate_settings(Process.APP)
        result = provision(
            Request(args.name, args.owner_issuer, args.owner_subject, dry_run=args.dry_run)
        )
    except ProvisioningRefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("DRY RUN: nothing was changed." if args.dry_run else "provisioning: OK")
    print(f"workspace id:   {result.tenant_id}")
    print(f"owner user id:  {result.owner_user_id}")
    print(f"membership id:  {result.membership_id}")
    print("performed:      " + ("; ".join(result.performed) if result.performed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
