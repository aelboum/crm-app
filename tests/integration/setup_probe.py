"""Reads the setup checklist as a workspace takes its first steps (decision
P4-S); prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_setup.py`. Refuses to
run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("setup_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("setup-a")
    b = _new_workspace("setup-b")
    owner = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def done() -> dict[str, bool]:
            response = client.get(f"{base}/setup", headers=owner)
            assert response.status_code == 200, response.text
            return {step["key"]: step["done"] for step in response.json()["steps"]}

        result["order"] = [
            step["key"] for step in client.get(f"{base}/setup", headers=owner).json()["steps"]
        ]
        result["new"] = done()

        made = client.post(
            f"{base}/contacts",
            json={"first_name": "Sam", "email": "sam@example.test"},
            headers=owner,
        )
        assert made.status_code == 201, made.text
        made = client.post(f"{base}/opportunities", json={"title": "First"}, headers=owner)
        assert made.status_code == 201, made.text
        settings = client.get(f"{base}/settings", headers=owner).json()
        changed = client.patch(
            f"{base}/settings",
            json={"business_hours": [{"opens": "09:00", "closes": "17:00"}] * 7},
            headers={**owner, "If-Match": f'"{settings["version"]}"'},
        )
        assert changed.status_code == 200, changed.text
        _, reader = _member(a, Role.READ_ONLY)
        result["after"] = done()

        # Another workspace's steps are its own; the reader sees the same list.
        result["other"] = {
            step["key"]: step["done"]
            for step in client.get(
                f"/v1/workspaces/{b.id}/setup",
                headers={"Authorization": f"Bearer {issue_session(b.owner_id)[1]}"},
            ).json()["steps"]
        }
        result["access"] = {
            "reader": client.get(
                f"{base}/setup", headers={"Authorization": f"Bearer {reader}"}
            ).status_code,
            "other_owner": client.get(
                f"{base}/setup",
                headers={"Authorization": f"Bearer {issue_session(b.owner_id)[1]}"},
            ).status_code,
            "outsider": client.get(
                f"{base}/setup",
                headers={"Authorization": f"Bearer {issue_session(_new_user())[1]}"},
            ).status_code,
            "anonymous": client.get(f"{base}/setup").status_code,
        }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
