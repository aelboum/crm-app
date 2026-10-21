"""The permissions this product declares into SaaS-OS's shared catalog.

A permission is a `(resource, action)` pair. Product resources are prefixed
`crm_app.` so they can never collide with a platform permission.
Registration is idempotent, needs the database, and runs in the migration
step (`crm_app.migrate`), never at import time.

Registering a permission grants nothing: it only makes the pair known, so
that a tenant's roles can later receive it through `saas_os.core.rbac`
(`saas_os.core.rbac.register_permission`; SaaS-OS CONSUMER-GUIDE "Registering
grants nothing"). The product registers exactly the permissions its role
templates grant (`crm_app.roles.GRANTED`): its own `crm_app.*` permissions
and the platform permissions its routes and roles rely on, such as
`membership:read`. Registration does not create roles or give existing
workspaces any permission.
"""

from __future__ import annotations

from crm_app.roles import GRANTED, PREFIX

__all__ = ["PERMISSIONS", "PREFIX", "register_permissions"]

PERMISSIONS: tuple[tuple[str, str], ...] = GRANTED


def register_permissions() -> None:
    if not PERMISSIONS:
        return
    # Imported here: the RBAC module resolves configuration at import time.
    from saas_os.core.rbac import register_permission  # noqa: PLC0415

    for resource, action in PERMISSIONS:
        register_permission(resource, action)
