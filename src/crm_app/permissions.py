"""The permissions this product declares into SaaS-OS's shared catalog.

A permission is a `(resource, action)` pair. Every resource is prefixed
`crm_app.` so it can never collide with a platform permission. Registration
is idempotent, needs the database, and runs in the migration step
(`crm_app.migrate`), never at import time. Registering a permission grants
nothing: a tenant's roles receive it through `saas_os.core.rbac`.

Phase 1 declares none; the first permissions arrive with the first product
routes.
"""

from __future__ import annotations

PREFIX = "crm_app."

PERMISSIONS: tuple[tuple[str, str], ...] = ()


def register_permissions() -> None:
    if not PERMISSIONS:
        return
    # Imported here: the RBAC module resolves configuration at import time.
    from saas_os.core.rbac import register_permission  # noqa: PLC0415

    for resource, action in PERMISSIONS:
        register_permission(resource, action)
