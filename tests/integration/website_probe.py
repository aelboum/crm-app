"""Drives website integration (decision P12-W) and prints one `RESULT <json>`
line.

Run in a fresh interpreter by `tests/integration/test_websites.py`. Seeds
throwaway workspaces and submits their published forms the way an external
site's browser would (with an `Origin` header). Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace

FIELDS = [
    {"key": "first", "type": "text", "label": "First name", "required": True,
     "target": "first_name"},
    {"key": "email", "type": "email", "label": "Email", "required": True, "target": "email"},
]  # fmt: skip
SITE = "https://www.acme-shop.example"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("website_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("site-a")
    b = _new_workspace("site-b")
    _, member = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        # --- Managing websites ----------------------------------------------------------
        made = client.post(
            f"{base}/websites",
            json={"name": " Acme shop ", "origins": [SITE + "/", "https://ACME-SHOP.example"]},
            headers=auth(),
        )
        site = made.json()
        one = f"{base}/websites/{site['id']}"
        result["created"] = [made.status_code, site.get("name"), site.get("origins")]

        def create(origins: list[str], caller: str = "owner") -> int:
            return client.post(
                f"{base}/websites", json={"name": "x", "origins": origins}, headers=auth(caller)
            ).status_code

        result["refused"] = [
            create(["http://plain.example"]),
            create(["https://*.example"]),
            create([]),
            create([SITE], "member"),
            create([SITE], "other_owner"),
        ]
        result["member_reads"] = len(
            client.get(f"{base}/websites", headers=auth("member")).json()["items"]
        )
        result["other_lists"] = len(
            client.get(f"/v1/workspaces/{b.id}/websites", headers=auth("other_owner")).json()[
                "items"
            ]
        )

        def published_form(workspace: uuid.UUID, caller: str) -> str:
            forms = f"/v1/workspaces/{workspace}/forms"
            form = client.post(
                forms,
                json={"name": "Contact", "fields": FIELDS},
                headers={**auth(caller), "Idempotency-Key": secrets.token_hex(8)},
            ).json()
            client.patch(
                f"{forms}/{form['id']}", json={"status": "published"}, headers=auth(caller, 1)
            )
            return f"/v1/public/forms/{workspace}/{form['public_key']}"

        public = published_form(a.id, "owner")
        public_b = published_form(b.id, "other_owner")

        def submit(
            path: str, origin: str | None, email: str, attribution: Any = None
        ) -> tuple[int, str | None]:
            headers = {"Idempotency-Key": secrets.token_hex(8)}
            if origin:
                headers["Origin"] = origin
            body: dict[str, Any] = {"answers": {"first": "Sam", "email": email}}
            if attribution is not None:
                body["attribution"] = attribution
            response = client.post(path, json=body, headers=headers)
            return response.status_code, response.headers.get("access-control-allow-origin")

        # --- Cross-site submissions -------------------------------------------------------
        result["allowed"] = submit(
            public,
            SITE,
            "sam@example.test",
            {
                "utm_source": "newsletter",
                "utm_campaign": "autumn",
                "page_url": f"{SITE}/contact?utm_source=newsletter",
                "referrer": "https://search.example/q",
                "extra": "ignored",
            },
        )
        result["unlisted"] = submit(public, "https://evil.example", "eve@example.test")
        result["other_workspace_site"] = submit(public_b, SITE, "sam@example.test")
        result["no_origin"] = submit(public, None, "server@example.test")
        app_origin = os.environ.get("PUBLIC_APP_ORIGIN", "http://localhost:8000")
        result["same_origin"] = submit(public, app_origin, "hosted@example.test")
        result["foreign_page"] = submit(
            public, SITE, "pat@example.test", {"page_url": "https://evil.example/x"}
        )
        preflight = client.options(
            public, headers={"Origin": SITE, "Access-Control-Request-Method": "POST"}
        )
        result["preflight"] = [
            preflight.status_code,
            preflight.headers.get("access-control-allow-origin"),
            "idempotency-key" in preflight.headers.get("access-control-allow-headers", ""),
        ]
        refused = client.options(
            public,
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        result["preflight_refused"] = [
            refused.status_code,
            refused.headers.get("access-control-allow-origin"),
        ]

        with tenant_session_scope(a.id) as session:
            rows = [
                dict(r._mapping)
                for r in session.execute(
                    text(
                        "SELECT website_id, attribution FROM crm_app.form_submission"
                        " WHERE tenant_id = :t ORDER BY created_at"
                    ),
                    {"t": a.id},
                )
            ]
        result["stored"] = [
            {
                "website": str(r["website_id"]) if r["website_id"] else None,
                "attribution": r["attribution"],
            }
            for r in rows
        ]
        result["site_id"] = site["id"]

        # --- Disabling and removing ---------------------------------------------------------
        disabled = client.patch(one, json={"status": "disabled"}, headers=auth(version=1))
        result["disabled"] = [disabled.status_code, submit(public, SITE, "late@example.test")[0]]
        result["stale"] = client.patch(one, json={"name": "x"}, headers=auth(version=1)).status_code
        enabled = client.patch(one, json={"status": "active"}, headers=auth(version=2))
        result["enabled"] = [enabled.status_code, submit(public, SITE, "back@example.test")[0]]
        result["removed"] = [
            client.delete(one, headers=auth("member")).status_code,
            client.delete(one, headers=auth("other_owner")).status_code,
            client.delete(one, headers=auth()).status_code,
            submit(public, SITE, "gone@example.test")[0],
        ]
        with tenant_session_scope(a.id) as session:
            result["kept_submissions"] = int(
                session.execute(
                    text("SELECT count(*) FROM crm_app.form_submission WHERE tenant_id = :t"),
                    {"t": a.id},
                ).scalar_one()
            )
            result["unlinked"] = int(
                session.execute(
                    text(
                        "SELECT count(*) FROM crm_app.form_submission"
                        " WHERE tenant_id = :t AND website_id IS NOT NULL"
                    ),
                    {"t": a.id},
                ).scalar_one()
            )
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
