"""Reads and changes workspace settings through the routes as different
callers against the integration database and prints one `RESULT <json>`
line.

Run in a fresh interpreter by `tests/integration/test_workspace_settings.py`
(SaaS-OS caches configuration per process). Workspaces and members are
created as in `record_route_probe`. All values are made up. Refuses to run
unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

ROLES = (Role.OWNER, Role.ADMIN, Role.MEMBER, Role.READ_ONLY)


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("settings_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("settings-a")
    b = _new_workspace("settings-b")
    race = _new_workspace("settings-race")
    users: dict[str, uuid.UUID] = {
        Role.OWNER.value: a.owner_id,
        "other_owner": b.owner_id,
        "race_owner": race.owner_id,
    }
    for role in (Role.ADMIN, Role.MEMBER, Role.READ_ONLY):
        user = _new_user()
        membership = add_tenant_membership(a.id, user, caller=PROVISIONING)
        assign_role(a.id, membership.id, a.role_ids[role], caller=UserCaller(a.owner_id))
        users[role.value] = user
    users["outsider"] = _new_user()
    tokens = {name: issue_session(user)[1] for name, user in users.items()}

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    path = f"/v1/workspaces/{a.id}/settings"
    result: dict[str, Any] = {"workspace": str(a.id), "admin": str(users[Role.ADMIN.value])}

    with TestClient(create_app(), follow_redirects=False) as client:

        def patch(url: str, body: object, version: object, caller: str | None = "Owner") -> Any:
            return client.patch(
                url, json=body, headers={**auth(caller), "If-Match": f'"{version}"'}
            )

        first = client.get(path, headers=auth("Owner"))
        result["defaults"] = [first.status_code, first.json(), first.headers.get("etag")]
        result["read"] = {
            role.value: client.get(path, headers=auth(role.value)).status_code for role in ROLES
        }
        result["read"]["outsider"] = client.get(path, headers=auth("outsider")).status_code
        result["read"]["other_owner"] = client.get(path, headers=auth("other_owner")).status_code
        result["read"]["anonymous"] = client.get(path).status_code

        # Who may change them: each role tries from the current version.
        result["change"] = {}
        for role in (Role.MEMBER, Role.READ_ONLY, Role.ADMIN):
            version = client.get(path, headers=auth("Owner")).json()["version"]
            result["change"][role.value] = patch(
                path, {"currency": "USD"}, version, role.value
            ).status_code
        after_admin = client.get(path, headers=auth("Owner")).json()
        result["after_admin"] = after_admin

        version = after_admin["version"]
        saved = patch(
            path, {"locale": " nl-nl ", "time_zone": "Europe/Berlin", "currency": "eur"}, version
        )
        result["normalised"] = [saved.status_code, saved.json(), saved.headers.get("etag")]
        version = saved.json()["version"]
        result["unchanged"] = patch(path, {"currency": "EUR"}, version).json()["version"]
        result["stale"] = [
            patch(path, {"currency": "GBP"}, version - 1).status_code,
            patch(path, {"currency": "GBP"}, version - 1).json()["detail"],
        ]
        result["missing_version"] = client.patch(
            path, json={"currency": "GBP"}, headers=auth("Owner")
        ).status_code

        refused = patch(path, {"time_zone": "Mars/Olympus-leak-3c1d"}, version)
        result["validation"] = {
            "time_zone": refused.status_code,
            "time_zone_body": refused.text,
            "currency": patch(path, {"currency": "XAU"}, version).status_code,
            "locale": patch(path, {"locale": "english"}, version).status_code,
            "unknown_field": patch(path, {"name": "Renamed"}, version).status_code,
            "tenant_id": patch(path, {"tenant_id": str(b.id)}, version).status_code,
            "version_field": patch(path, {"version": 99}, version).status_code,
        }

        # Business hours (P5-B): set, unchanged, refused, cleared.
        week = [{"opens": "09:00", "closes": "17:00"}] * 5 + [None, None]
        hours = patch(path, {"business_hours": week}, version)
        version = hours.json()["version"]
        result["hours"] = {
            "set": [hours.status_code, hours.json()["business_hours"], version],
            "same": patch(path, {"business_hours": week}, version).json()["version"],
            "member": patch(path, {"business_hours": None}, version, "Member").status_code,
            "backwards": patch(
                path, {"business_hours": [{"opens": "17:00", "closes": "09:00"}] * 7}, version
            ).status_code,
            "six_days": patch(path, {"business_hours": week[:6]}, version).status_code,
            "extra_key": patch(
                path,
                {"business_hours": [{"opens": "09:00", "closes": "17:00", "x": 1}] * 7},
                version,
            ).status_code,
        }
        cleared = patch(path, {"business_hours": None, "currency": None}, version)
        version = cleared.json()["version"]
        result["hours"]["cleared"] = [
            cleared.status_code,
            cleared.json()["business_hours"],
            cleared.json()["currency"],
            version,
        ]

        # Another workspace's member naming A's settings, and B's own.
        result["cross"] = {
            "other_owner_patch": patch(
                path, {"currency": "JPY"}, version, "other_owner"
            ).status_code,
            "outsider_patch": patch(path, {"currency": "JPY"}, version, "outsider").status_code,
            "b_defaults": client.get(
                f"/v1/workspaces/{b.id}/settings", headers=auth("other_owner")
            ).json()["currency"],
            "a_after": client.get(path, headers=auth("Owner")).json()["currency"],
        }

        # Two first saves at once: one wins, the other is told it is stale.
        race_path = f"/v1/workspaces/{race.id}/settings"
        barrier = threading.Barrier(2)

        def first_save(code: str) -> int:
            barrier.wait()
            return patch(race_path, {"currency": code}, 0, "race_owner").status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            result["race"] = sorted(
                f.result() for f in [pool.submit(first_save, "USD"), pool.submit(first_save, "GBP")]
            )
        result["race_after"] = client.get(race_path, headers=auth("race_owner")).json()["version"]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
