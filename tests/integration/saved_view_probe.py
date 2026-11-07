"""Drives saved views (decision P3-SV) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_saved_views.py`.
Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
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
from tests.integration.workspace_route_probe import _new_workspace


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("saved_view_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("views-a")
    b = _new_workspace("views-b")
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other": issue_session(b.owner_id)[1],
    }

    def auth(caller: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    contacts = f"/v1/workspaces/{a.id}/saved-views/contacts"
    deals = f"/v1/workspaces/{a.id}/saved-views/opportunities"
    filters = {"q": "acme", "lifecycle_stage": ["customer"], "sort": "updated_at"}
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def save(url: str, body: dict[str, Any], caller: str = "member") -> Any:
            return client.post(url, json=body, headers=auth(caller))

        made = save(contacts, {"name": "  My   customers ", "filters": filters})
        assert made.status_code == 201, made.text
        view = made.json()
        result["made"] = [made.status_code, view["name"], view["filters"]]
        listed = client.get(contacts, headers=auth("member")).json()["items"]
        result["mine"] = [v["name"] for v in listed]
        result["others_see"] = [
            client.get(contacts, headers=auth("owner")).json()["items"],
            client.get(contacts, headers=auth("reader")).json()["items"],
        ]
        foreign = f"/v1/workspaces/{b.id}/saved-views/contacts/{view['id']}"
        result["others_change"] = [
            client.patch(
                f"{contacts}/{view['id']}", json={"name": "Taken"}, headers=auth("owner")
            ).status_code,
            client.delete(f"{contacts}/{view['id']}", headers=auth("owner")).status_code,
            client.delete(foreign, headers=auth("other")).status_code,
        ]
        result["refused"] = {
            "duplicate": save(contacts, {"name": "my customers", "filters": {}}).json()["detail"][
                "code"
            ],
            "unknown_filter": save(contacts, {"name": "X", "filters": {"sql": "1=1"}}).status_code,
            "bad_stage": save(
                contacts, {"name": "Y", "filters": {"lifecycle_stage": ["vip"]}}
            ).status_code,
            "empty_name": save(contacts, {"name": "   ", "filters": {}}).status_code,
        }
        result["reader_saves"] = save(
            contacts, {"name": "Reader view", "filters": {}}, "reader"
        ).status_code
        renamed = client.patch(
            f"{contacts}/{view['id']}",
            json={"name": "Big customers", "filters": {"owner": ["me"]}},
            headers=auth("member"),
        ).json()
        result["renamed"] = [renamed["name"], renamed["filters"]["owner"]]
        deal = save(deals, {"name": "Idle deals", "filters": {"idle": True, "outcome": ["open"]}})
        result["deal"] = [deal.status_code, deal.json()["filters"]["idle"]]
        result["deal_bad"] = save(
            deals, {"name": "Z", "filters": {"lifecycle_stage": ["lead"]}}
        ).status_code
        result["deleted"] = [
            client.delete(f"{contacts}/{view['id']}", headers=auth("member")).status_code,
            client.delete(f"{contacts}/{view['id']}", headers=auth("member")).status_code,
        ]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
