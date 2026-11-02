"""Drives email templates (decision P7-T) and prints one `RESULT <json>`
line.

Run in a fresh interpreter by `tests/integration/test_email_templates.py`.
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
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("email_template_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("templates-a")
    b = _new_workspace("templates-b")
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}/email-templates"
    body = {
        "name": "  Follow   up ",
        "subject": "Hello {{first_name}}",
        "body": "Dear {{first_name}} {{last_name}},\r\n\r\nThank you.",
    }
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        made = client.post(base, json=body, headers=auth("member"))
        template = made.json()
        result["created"] = [
            made.status_code,
            template["name"],
            template["body"],
            made.headers.get("etag"),
        ]
        result["create_access"] = {
            caller: client.post(
                base, json={**body, "name": f"By {caller}"}, headers=auth(caller)
            ).status_code
            for caller in ("reader", "other_owner", "outsider")
        }

        def refused(**changes: str) -> Any:
            return client.post(base, json={**body, **changes}, headers=auth())

        result["refused"] = {
            "unknown_placeholder": refused(name="X", body="Hi {{email}}").json()["detail"]["code"],
            "stray_braces": refused(name="Y", subject="Hi {{").json()["detail"]["code"],
            "two_line_subject": refused(name="Z", subject="a\nb").status_code,
            "taken_name": refused(name="Follow up").json()["detail"]["code"],
            "extra_field": refused(name="W", html="<b>").status_code,
        }
        result["list"] = {
            caller: [
                item["name"]
                for item in client.get(base, headers=auth(caller)).json().get("items", [])
            ]
            for caller in ("reader", "other_owner")
        }
        item = f"{base}/{template['id']}"
        change = {"subject": "Hi {{first_name}}"}
        result["update"] = [
            client.patch(item, json=change, headers=auth("owner", 9)).json()["detail"]["code"],
            client.patch(item, json=change, headers=auth("reader", 1)).status_code,
        ]
        updated = client.patch(item, json=change, headers=auth("owner", template["version"])).json()
        result["updated"] = [updated["subject"], updated["version"]]

        contact = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Ada", "last_name": "{{last_name}}", "email": "ada@example.org"},
            headers=auth(),
        ).json()
        foreign = client.post(
            f"/v1/workspaces/{b.id}/contacts",
            json={"first_name": "Bo", "email": "bo@example.org"},
            headers=auth("other_owner"),
        ).json()
        render = f"{item}/render"

        def fill(contact_id: str, caller: str = "owner", path: str = render) -> Any:
            return client.post(path, json={"contact_id": contact_id}, headers=auth(caller))

        result["rendered"] = fill(contact["id"], "member").json()
        result["render_refused"] = {
            "reader": fill(contact["id"], "reader").status_code,
            "foreign_contact": fill(foreign["id"]).status_code,
            "other_workspace": fill(
                foreign["id"],
                "other_owner",
                f"/v1/workspaces/{b.id}/email-templates/{template['id']}/render",
            ).status_code,
        }
        result["delete"] = [
            client.delete(item, headers=auth("reader")).status_code,
            client.delete(
                f"/v1/workspaces/{b.id}/email-templates/{template['id']}",
                headers=auth("other_owner"),
            ).status_code,
            client.delete(item, headers=auth("member")).status_code,
            client.get(base, headers=auth()).json()["items"],
        ]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
