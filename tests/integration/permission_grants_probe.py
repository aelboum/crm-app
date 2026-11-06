"""Drives `crm_app.permission_grants`'s read-only report and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_permission_grants.py`.
An "old" workspace holds the Phase 2 templates (`BASELINE`), a fresh one the
current templates, and a bare tenant has no product roles. Refuses to run
unless ENVIRONMENT=test.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import secrets
import uuid
from typing import Any

from saas_os.core.rbac import create_role, grant_permission, register_permission
from saas_os.core.tenancy import TenantStatus, create_tenant, transition_tenant_status

from crm_app import permission_grants as pg
from crm_app.roles import ROLE_TEMPLATES, Role
from tests.integration.workspace_route_probe import PROVISIONING
from tests.unit.permission_grants_guard import BASELINE


def _workspace(label: str, *, current: bool) -> uuid.UUID:
    tenant = create_tenant(f"grants-{label}-{secrets.token_hex(4)}", caller=PROVISIONING)
    transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=PROVISIONING)
    for role in Role:
        created = create_role(tenant.id, role.value, caller=PROVISIONING)
        keys = (
            ROLE_TEMPLATES[role]
            if current
            else {tuple(name.rsplit(":", 1)) for name in BASELINE[role.value]}
        )
        for resource, action in sorted(keys):
            permission = register_permission(resource, action)
            grant_permission(tenant.id, created.id, permission.id, caller=PROVISIONING)
    return tenant.id


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("permission_grants_probe runs only with ENVIRONMENT=test")
    old = _workspace("old", current=False)
    fresh = _workspace("fresh", current=True)
    bare = create_tenant(f"grants-bare-{secrets.token_hex(4)}", caller=PROVISIONING)
    transition_tenant_status(bare.id, TenantStatus.ACTIVE, caller=PROVISIONING)
    result: dict[str, Any] = {}
    for name, migrations in (
        ("standard", pg.PERMISSION_GRANT_MIGRATIONS),
        ("administrative", pg.ADMINISTRATIVE_MIGRATIONS),
    ):
        result[name] = {
            label: [vars(r) for r in pg.report(migrations, [tenant])]
            for label, tenant in (("old", old), ("fresh", fresh), ("bare", bare.id))
        }
        result[f"{name}_declared"] = sum(len(m.permissions) for m in migrations)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = pg.main(["--report", "--workspace", str(old), "--json"])
    result["cli"] = [code, len(json.loads(out.getvalue()))]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
