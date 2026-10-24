"""Lists workspaces through `GET /v1/workspaces` as different callers
against the integration database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_directory.py`
(SaaS-OS caches configuration per process). Workspaces and members are
created with `workspace_route_probe`'s helpers; deleting a workspace uses a
test operator enrolled with `PLATFORM_BOOTSTRAP`, as in
`record_route_probe`. All values are made up. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import (
    add_tenant_membership,
    issue_session,
    revoke_membership,
    suspend_membership,
)
from saas_os.core.platform_authority import (
    PlatformPermission,
    enroll_operator,
    grant_platform_permission,
)
from saas_os.core.rbac import assign_role
from saas_os.core.tenancy import TenantStatus, transition_tenant_status

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("directory_probe runs only with ENVIRONMENT=test")
    own = _new_workspace("dir-own")  # the person is its Owner
    person = own.owner_id
    joined = _new_workspace("dir-joined")  # Read-only member
    suspended = _new_workspace("dir-suspended")  # membership suspended
    revoked = _new_workspace("dir-revoked")  # membership revoked
    closed = _new_workspace("dir-closed")  # workspace deleted
    other = _new_workspace("dir-other")  # never a member

    for workspace in (joined, suspended, revoked, closed):
        membership = add_tenant_membership(workspace.id, person, caller=PROVISIONING)
        assign_role(
            workspace.id,
            membership.id,
            workspace.role_ids[Role.READ_ONLY],
            caller=UserCaller(workspace.owner_id),
        )
        if workspace is suspended:
            suspend_membership(workspace.id, membership.id, caller=UserCaller(workspace.owner_id))
        if workspace is revoked:
            revoke_membership(workspace.id, membership.id, caller=UserCaller(workspace.owner_id))

    bootstrap = SystemCaller(SystemAuthority.PLATFORM_BOOTSTRAP)
    operator_user = _new_user()
    operator = enroll_operator(operator_user, caller=bootstrap, reason="crm-app directory test")
    grant_platform_permission(
        operator.id,
        PlatformPermission.TENANT_DELETE,
        caller=bootstrap,
        reason="crm-app directory test",
    )
    transition_tenant_status(closed.id, TenantStatus.DELETED, caller=UserCaller(operator_user))

    outsider = _new_user()
    tokens = {"person": issue_session(person)[1], "outsider": issue_session(outsider)[1]}

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    result: dict[str, Any] = {
        "ids": {
            "own": str(own.id),
            "joined": str(joined.id),
            "suspended": str(suspended.id),
            "revoked": str(revoked.id),
            "closed": str(closed.id),
            "other": str(other.id),
        }
    }
    with TestClient(create_app(), follow_redirects=False) as client:
        mine = client.get("/v1/workspaces", headers=auth("person"))
        result["person"] = [mine.status_code, mine.json()]
        theirs = client.get("/v1/workspaces", headers=auth("outsider"))
        result["outsider"] = [theirs.status_code, theirs.json()]
        result["anonymous"] = client.get("/v1/workspaces").status_code
        # Listing grants nothing: each workspace is still authorized on its own.
        result["open"] = {
            name: client.get(f"/v1/workspaces/{workspace.id}", headers=auth("person")).status_code
            for name, workspace in (
                ("own", own),
                ("joined", joined),
                ("suspended", suspended),
                ("revoked", revoked),
                ("closed", closed),
                ("other", other),
            )
        }
        result["unknown_query"] = client.get(
            "/v1/workspaces", params={"tenant_id": str(other.id)}, headers=auth("person")
        ).json()

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
