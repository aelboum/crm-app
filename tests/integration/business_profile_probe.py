"""Saves the business's contact details and reads them back, on the
settings and on a public booking page (decision P2-BP); prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_business_profile.py`.
Refuses to run unless ENVIRONMENT=test.
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

CONTACT = {
    "business_phone": " +31 20 123 4567 ",
    "business_email": "Hello@Example.TEST",
    "business_website": "https://www.example.test",
    "business_address": "  Keizersgracht 1 \r\n\r\n 1015 CJ Amsterdam  ",
}


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("business_profile_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("profile-a")
    owner = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    _, member = _member(a, Role.MEMBER)
    settings = f"/v1/workspaces/{a.id}/settings"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def patch(body: dict[str, Any], who: dict[str, str] = owner) -> Any:
            version = client.get(settings, headers=owner).json()["version"]
            return client.patch(settings, json=body, headers={**who, "If-Match": f'"{version}"'})

        result["defaults"] = {
            k: v for k, v in client.get(settings, headers=owner).json().items() if "business_" in k
        }
        saved = patch({**CONTACT, "business_hours": [{"opens": "09:00", "closes": "17:00"}] * 7})
        result["saved"] = [
            saved.status_code,
            {k: v for k, v in saved.json().items() if k in CONTACT},
        ]
        result["member"] = patch(
            {"business_phone": "123"}, {"Authorization": f"Bearer {member}"}
        ).status_code
        result["refused"] = {
            name: patch({name: value}).status_code
            for name, value in (
                ("business_phone", "call me"),
                ("business_email", "not-an-email"),
                ("business_website", "javascript:alert(1)"),
                ("business_address", "\n".join(["line"] * 7)),
                ("business_address", "tab\there"),
            )
        }

        # A published booking page: no contact until the workspace shows it.
        pages = f"/v1/workspaces/{a.id}/booking-pages"
        page = client.post(pages, json={"name": "Intro"}, headers=owner).json()
        client.patch(
            f"{pages}/{page['id']}",
            json={"status": "published"},
            headers={**owner, "If-Match": '"1"'},
        )
        public = f"/v1/public/booking-pages/{a.id}/{page['public_key']}"
        result["hidden"] = client.get(public).json().get("contact")
        patch({"business_contact_public": True})
        result["shown"] = client.get(public).json().get("contact")

        # Clearing: "" removes a detail; null leaves it.
        cleared = patch({"business_phone": "", "business_email": None})
        result["cleared"] = {k: cleared.json()[k] for k in ("business_phone", "business_email")}
        patch(dict.fromkeys(CONTACT, ""))
        result["all_cleared"] = client.get(public).json().get("contact")
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
