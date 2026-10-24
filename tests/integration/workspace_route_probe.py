"""Calls the workspace routes as different callers against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_workspace_routes.py`,
because SaaS-OS caches its configuration per process. It sets up two
throwaway workspaces in the integration database with
`SystemCaller(PROVISIONING)`, whose documented purposes include "test
fixtures" (`saas_os.core.authority.SystemAuthority`). Never run it against
any other database.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import (
    add_tenant_membership,
    get_or_create_user_for_external_identity,
    issue_session,
    revoke_membership,
    suspend_membership,
)
from saas_os.core.rbac import (
    assign_first_role_for_new_tenant,
    assign_role,
    create_role,
    grant_permission,
    register_permission,
)
from saas_os.core.tenancy import TenantStatus, create_tenant, transition_tenant_status

from crm_app.app import create_app
from crm_app.roles import ROLE_TEMPLATES, Role

PROVISIONING = SystemCaller(SystemAuthority.PROVISIONING)
ISSUER = "https://identity.invalid/route-probe"
CALLERS = (
    None,
    "owner",
    "reader",
    "roleless",
    "outsider",
    "other_owner",
    "suspended",
    "revoked",
)


@dataclass(frozen=True)
class Workspace:
    id: uuid.UUID
    role_ids: dict[Role, uuid.UUID]
    owner_id: uuid.UUID


def _new_user() -> uuid.UUID:
    return get_or_create_user_for_external_identity(ISSUER, secrets.token_hex(12)).id


def _new_workspace(label: str) -> Workspace:
    tenant = create_tenant(f"route-probe-{label}-{secrets.token_hex(4)}", caller=PROVISIONING)
    transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=PROVISIONING)
    role_ids: dict[Role, uuid.UUID] = {}
    for role, keys in ROLE_TEMPLATES.items():
        created = create_role(tenant.id, role.value, caller=PROVISIONING)
        for resource, action in sorted(keys):
            permission = register_permission(resource, action)
            grant_permission(tenant.id, created.id, permission.id, caller=PROVISIONING)
        role_ids[role] = created.id
    owner_id = _new_user()
    membership = add_tenant_membership(tenant.id, owner_id, caller=PROVISIONING)
    assign_first_role_for_new_tenant(
        tenant.id, membership.id, role_ids[Role.OWNER], caller=PROVISIONING
    )
    return Workspace(tenant.id, role_ids, owner_id)


def main() -> None:
    # It creates tenants with the provisioning authority: refuse anything but
    # the integration database (the pytest fixture enforces the same).
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("workspace_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("a")
    b = _new_workspace("b")

    reader = _new_user()
    reader_membership = add_tenant_membership(a.id, reader, caller=PROVISIONING)
    assign_role(
        a.id, reader_membership.id, a.role_ids[Role.READ_ONLY], caller=UserCaller(a.owner_id)
    )
    roleless = _new_user()
    add_tenant_membership(a.id, roleless, caller=PROVISIONING)
    outsider = _new_user()
    owner_caller = UserCaller(a.owner_id)
    # Read-only members with a session, then suspended or revoked: the
    # session they already hold must stop working on the next request.
    suspended = _new_user()
    suspended_membership = add_tenant_membership(a.id, suspended, caller=PROVISIONING)
    assign_role(a.id, suspended_membership.id, a.role_ids[Role.READ_ONLY], caller=owner_caller)
    revoked = _new_user()
    revoked_membership = add_tenant_membership(a.id, revoked, caller=PROVISIONING)
    assign_role(a.id, revoked_membership.id, a.role_ids[Role.READ_ONLY], caller=owner_caller)
    removed_tokens = {
        "suspended": issue_session(suspended)[1],
        "revoked": issue_session(revoked)[1],
    }
    suspend_membership(a.id, suspended_membership.id, caller=owner_caller)
    revoke_membership(a.id, revoked_membership.id, caller=owner_caller)

    users = {
        "owner": a.owner_id,
        "reader": reader,
        "roleless": roleless,
        "outsider": outsider,
        "other_owner": b.owner_id,
    }
    tokens = {name: issue_session(user)[1] for name, user in users.items()} | removed_tokens

    def headers(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    workspace = f"/v1/workspaces/{a.id}"
    members = f"{workspace}/members"
    access = f"{workspace}/access"
    # A stand-in frontend build for the static routes (crm_app.api.spa).
    dist = Path.cwd() / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "assets" / "app-1.js").write_text("export {};", encoding="utf-8")
    os.environ["CRM_APP_FRONTEND_DIST"] = str(dist)
    with TestClient(create_app(), follow_redirects=False) as client:

        def status(path: str, caller: str | None) -> int:
            return client.get(path, headers=headers(caller)).status_code

        listed = client.get(members, headers=headers("reader")).json()["items"]
        owner_listed = client.get(members, headers=headers("owner")).json()
        shown_response = client.get(workspace, headers=headers("owner"))
        shown = shown_response.json()
        api_cache = shown_response.headers.get("cache-control")
        access_seen = {
            c: client.get(access, headers=headers(c)).json() for c in ("owner", "reader")
        }
        app_page = client.get("/app/w/anything")
        asset = client.get("/app/assets/app-1.js")
        frontend = {
            "root": [client.get("/").status_code, client.get("/").headers.get("location")],
            "page": [app_page.status_code, app_page.headers.get("cache-control")],
            "page_csp": app_page.headers.get("content-security-policy", ""),
            "asset": [asset.status_code, asset.headers.get("cache-control")],
            "missing_asset": client.get("/app/assets/missing.js").status_code,
            "head": [
                client.head("/app").status_code,
                client.head("/app").content.decode(),
                client.head("/app/assets/app-1.js").status_code,
            ],
            "traversal": client.get("/app/..%2F..%2Fpyproject.toml").status_code,
        }
        result = {
            "workspace": {c or "anonymous": status(workspace, c) for c in CALLERS},
            "members": {c or "anonymous": status(members, c) for c in CALLERS},
            "access": {c or "anonymous": status(access, c) for c in CALLERS},
            "unknown_workspace": status(f"/v1/workspaces/{uuid.uuid4()}", "owner"),
            "unknown_members": status(f"/v1/workspaces/{uuid.uuid4()}/members", "owner"),
            "page_too_large": status(f"{members}?limit=1000", "owner"),
        }
    result |= {
        "owner_workspace_id_matches": shown.get("id") == str(a.id),
        "member_user_ids": sorted(item["user_id"] for item in listed),
        "expected_member_user_ids": sorted(str(u) for u in (a.owner_id, reader, roleless)),
        "owner_sees_user_ids": sorted(item["user_id"] for item in owner_listed["items"]),
        "owner_expected_user_ids": sorted(
            str(u) for u in (a.owner_id, reader, roleless, suspended)
        ),
        "owner_sees_total": owner_listed["total"],
        "statuses_seen_by_reader": sorted({item["status"] for item in listed}),
        "statuses_seen_by_owner": sorted({item["status"] for item in owner_listed["items"]}),
        "revoked_id": str(revoked),
        "member_roles": {item["user_id"]: item["roles"] for item in listed},
        "owner_id": str(a.owner_id),
        "reader_id": str(reader),
        "roleless_id": str(roleless),
        "other_owner_listed": str(b.owner_id) in {item["user_id"] for item in listed},
        "access_seen": access_seen,
        "frontend": frontend,
        "api_cache": api_cache,
    }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
