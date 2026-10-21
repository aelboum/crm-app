"""The product roles and the permissions each one holds.

Decision P2-A approves four product roles (Owner, Admin, Member, Read-only);
their permissions are the matrix in `docs/project/PHASE2-PLAN.md` §5.2,
approved by the owner on 2026-10-21 (Q6). SaaS-OS has no built-in roles: a
role is a tenant-local row created with `saas_os.core.rbac.create_role` and
given permissions with `grant_permission`.

This module is declarative. `crm_app.permissions` registers the granted
permissions into SaaS-OS's shared catalog during migration; registering
grants nothing. No role is created and nothing is granted to any workspace
until the provisioning command exists (gate G2). Importing this module
touches no configuration, database or tenant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Every product resource is prefixed so it can never collide with a
# platform permission.
PREFIX = "crm_app."


class Role(StrEnum):
    OWNER = "Owner"
    ADMIN = "Admin"
    MEMBER = "Member"
    READ_ONLY = "Read-only"


class Kind(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ADMINISTRATIVE = "administrative"


@dataclass(frozen=True)
class Permission:
    """One `(resource, action)` pair. A sensitive permission names its
    `safeguard`: what the backend must check beyond holding the permission."""

    resource: str
    action: str
    kind: Kind
    safeguard: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.resource, self.action)

    @property
    def sensitive(self) -> bool:
        return bool(self.safeguard)


def _crud(resource: str) -> tuple[Permission, ...]:
    return (
        Permission(resource, "read", Kind.READ),
        Permission(resource, "create", Kind.CREATE),
        Permission(resource, "update", Kind.UPDATE),
        Permission(resource, "delete", Kind.DELETE),
    )


_NOT_OWNERS = "Admins may not act on an Owner's membership."
_LAST_OWNER = "Product last-Owner guard under a per-workspace lock."
_FIXED_ROLES = "Roles are fixed templates in Phase 2; no route edits them."
_LATER_PHASE = "Not granted in Phase 2."

# Defined by SaaS-OS at the pinned commit (`saas_os/api/v1/permissions.py`,
# `tenant_status.py`, `tenant_suspension.py`, `saas_os/core/rbac/service.py`).
# Listed so the templates can name them; this module never registers them.
PLATFORM_PERMISSIONS: tuple[Permission, ...] = (
    Permission("tenant", "read_status", Kind.READ),
    Permission(
        "tenant",
        "suspend",
        Kind.ADMINISTRATIVE,
        "Locks every member out; only a platform operator can reactivate.",
    ),
    Permission("membership", "read", Kind.READ),
    Permission("membership", "suspend", Kind.ADMINISTRATIVE, f"{_LAST_OWNER} {_NOT_OWNERS}"),
    Permission("membership", "reactivate", Kind.ADMINISTRATIVE, _NOT_OWNERS),
    Permission("membership", "revoke", Kind.ADMINISTRATIVE, f"{_LAST_OWNER} {_NOT_OWNERS}"),
    Permission("invitation", "read", Kind.READ),
    Permission(
        "invitation",
        "create",
        Kind.ADMINISTRATIVE,
        "Rate-limited; the intended role may not exceed the inviter's own.",
    ),
    Permission("invitation", "revoke", Kind.ADMINISTRATIVE, "Only pending invitations; audited."),
    Permission(
        "membership_role",
        "create",
        Kind.ADMINISTRATIVE,
        "SaaS-OS refuses a role holding any permission the caller lacks.",
    ),
    Permission("membership_role", "delete", Kind.ADMINISTRATIVE, _LAST_OWNER),
    Permission("role_permission", "grant", Kind.ADMINISTRATIVE, _FIXED_ROLES),
    Permission("role_permission", "revoke", Kind.ADMINISTRATIVE, _FIXED_ROLES),
    Permission("api_key", "self_manage", Kind.ADMINISTRATIVE, _LATER_PHASE),
    Permission("billing_subscription", "read", Kind.READ),
    Permission("billing_subscription", "create", Kind.ADMINISTRATIVE, _LATER_PHASE),
    Permission("billing_subscription", "cancel", Kind.ADMINISTRATIVE, _LATER_PHASE),
    Permission("billing_account", "read", Kind.READ),
)

PRODUCT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(f"{PREFIX}workspace", "read", Kind.READ),
    Permission(f"{PREFIX}workspace", "update", Kind.UPDATE),
    Permission(
        f"{PREFIX}workspace_security",
        "update",
        Kind.ADMINISTRATIVE,
        "Owner only; the caller re-confirms the change.",
    ),
    Permission(
        f"{PREFIX}owner",
        "manage",
        Kind.ADMINISTRATIVE,
        f"The caller re-confirms the change. {_LAST_OWNER}",
    ),
    Permission(f"{PREFIX}member_profile", "read", Kind.READ),
    Permission(
        f"{PREFIX}audit",
        "read",
        Kind.READ,
        "Shows member activity; never personal data or secrets.",
    ),
    *_crud(f"{PREFIX}contact"),
    *_crud(f"{PREFIX}company"),
    *_crud(f"{PREFIX}opportunity"),
    Permission(f"{PREFIX}pipeline", "read", Kind.READ),
    Permission(
        f"{PREFIX}pipeline",
        "manage",
        Kind.ADMINISTRATIVE,
        "Changing stages affects every open opportunity.",
    ),
    *_crud(f"{PREFIX}task"),
    *_crud(f"{PREFIX}activity"),
    Permission(
        f"{PREFIX}crm_data",
        "export",
        Kind.ADMINISTRATIVE,
        "Bounded, audited and rate-limited.",
    ),
)

CATALOGUE: tuple[Permission, ...] = PLATFORM_PERMISSIONS + PRODUCT_PERMISSIONS


def _keys(*names: str) -> frozenset[tuple[str, str]]:
    """`"resource:action"` names as catalogue keys."""
    keys: set[tuple[str, str]] = set()
    for name in names:
        resource, _, action = name.rpartition(":")
        keys.add((resource, action))
    return frozenset(keys)


_READ_ONLY = _keys(
    "tenant:read_status",
    "membership:read",
    f"{PREFIX}workspace:read",
    f"{PREFIX}member_profile:read",
    f"{PREFIX}contact:read",
    f"{PREFIX}company:read",
    f"{PREFIX}opportunity:read",
    f"{PREFIX}pipeline:read",
    f"{PREFIX}task:read",
    f"{PREFIX}activity:read",
)

_MEMBER = _READ_ONLY | _keys(
    f"{PREFIX}contact:create",
    f"{PREFIX}contact:update",
    f"{PREFIX}company:create",
    f"{PREFIX}company:update",
    f"{PREFIX}opportunity:create",
    f"{PREFIX}opportunity:update",
    f"{PREFIX}task:create",
    f"{PREFIX}task:update",
    f"{PREFIX}task:delete",
    f"{PREFIX}activity:create",
)

_ADMIN = _MEMBER | _keys(
    f"{PREFIX}workspace:update",
    f"{PREFIX}audit:read",
    f"{PREFIX}contact:delete",
    f"{PREFIX}company:delete",
    f"{PREFIX}opportunity:delete",
    f"{PREFIX}activity:update",
    f"{PREFIX}activity:delete",
    f"{PREFIX}pipeline:manage",
    f"{PREFIX}crm_data:export",
    "invitation:read",
    "invitation:create",
    "invitation:revoke",
    "membership:suspend",
    "membership:reactivate",
    "membership:revoke",
    "membership_role:create",
    "membership_role:delete",
)

_OWNER = _ADMIN | _keys(
    f"{PREFIX}owner:manage",
    f"{PREFIX}workspace_security:update",
)

ROLE_TEMPLATES: dict[Role, frozenset[tuple[str, str]]] = {
    Role.OWNER: _OWNER,
    Role.ADMIN: _ADMIN,
    Role.MEMBER: _MEMBER,
    Role.READ_ONLY: _READ_ONLY,
}

# Held by no role in Phase 2: suspension locks the whole workspace out,
# roles are fixed templates, and API keys and billing belong to later
# phases. Workspace deletion and purge are operator commands, never request
# paths (SaaS-OS ADR-0040), so they have no permission at all.
UNGRANTED: frozenset[tuple[str, str]] = _keys(
    "tenant:suspend",
    "role_permission:grant",
    "role_permission:revoke",
    "api_key:self_manage",
    "billing_subscription:read",
    "billing_subscription:create",
    "billing_subscription:cancel",
    "billing_account:read",
)

# Every permission some role holds, in catalogue order. These are the pairs
# the product registers; the ungranted ones are left to SaaS-OS.
GRANTED: tuple[tuple[str, str], ...] = tuple(p.key for p in CATALOGUE if p.key not in UNGRANTED)
