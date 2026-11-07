"""Drives customers' webhooks (decision P12-H) and prints one `RESULT
<json>` line.

Run in a fresh interpreter by `tests/integration/test_webhooks.py`.
Delivery itself is SaaS-OS's (its own tests); this checks what LeadStack
records for delivery, in which transaction and with which data. Seeds
throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

_FIELDS = [
    {"key": "first", "type": "text", "label": "First name", "required": True,
     "target": "first_name"},
    {"key": "email", "type": "email", "label": "Email", "required": True, "target": "email"},
]  # fmt: skip


def _events(workspace: uuid.UUID) -> list[dict[str, Any]]:
    """What is recorded for delivery: one row per endpoint and event."""
    with tenant_session_scope(workspace) as session:
        rows = session.execute(
            text(
                "SELECT aggregate_id, payload FROM core.outbox_events"
                " WHERE tenant_id = :t AND aggregate_type = 'webhook_subscription'"
                " ORDER BY created_at, id"
            ),
            {"t": workspace},
        )
        return [
            {
                "endpoint": r.aggregate_id,
                "event": r.payload["event_type"],
                "data": r.payload["event_data"],
            }
            for r in rows
        ]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("webhook_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("hooks-a")
    b = _new_workspace("hooks-b")
    _, member = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "other": issue_session(b.owner_id)[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def add(url: str, caller: str = "owner", where: str = base) -> Any:
            return client.post(f"{where}/webhooks", json={"url": url}, headers=auth(caller))

        # --- Endpoints: HTTPS only, Owners and Admins only, secret once -------------
        credentials = "https://user:pass@hooks.example.org/in"  # pragma: allowlist secret
        result["refused"] = [
            add("http://hooks.example.org/in").status_code,
            add("ftp://hooks.example.org/in").status_code,
            add(credentials).status_code,
            add("https://hooks.example.org/in", "member").status_code,
        ]
        # A contact before any endpoint exists records nothing.
        early = client.post(
            f"{base}/contacts",
            json={"first_name": "Early", "email": f"early.{uuid.uuid4().hex[:6]}@example.org"},
            headers=auth(),
        )
        result["before_any"] = [early.status_code, len(_events(a.id))]
        added = add("https://hooks.example.org/in?token=abc")
        assert added.status_code == 201, added.text
        endpoint = added.json()["endpoint"]
        result["added"] = [
            added.status_code,
            added.headers.get("cache-control"),
            endpoint["url"],
            len(added.json()["signing_secret"]) > 20,
        ]
        add("https://hooks.example.net/b", "other", f"/v1/workspaces/{b.id}")

        # --- Events, in the change's transaction, with small data ----------------------
        made = client.post(
            f"{base}/contacts",
            json={
                "first_name": "Ada",
                "last_name": "Lee",
                "email": "ada.hooks@example.org",
                "phone": "+31 6 5555 0000",
                "job_title": "Buyer",
            },
            headers=auth(),
        )
        contact = made.json()
        client.patch(
            f"{base}/contacts/{contact['id']}",
            json={"job_title": "Head buyer", "city": "Utrecht"},
            headers=auth(version=contact["version"]),
        )
        pipeline = client.get(f"{base}/pipelines", headers=auth()).json()["items"][0]
        stages = [s["id"] for s in pipeline["stages"]]
        deal_made = client.post(
            f"{base}/opportunities",
            json={"title": "Ada deal", "stage_id": stages[0], "contact_id": contact["id"]},
            headers=auth(),
        )
        assert deal_made.status_code == 201, deal_made.text
        deal = deal_made.json()
        moved = client.patch(
            f"{base}/opportunities/{deal['id']}",
            json={"stage_id": stages[1]},
            headers=auth(version=deal["version"]),
        )
        form_made = client.post(
            f"{base}/forms", json={"name": "Hooks", "fields": _FIELDS}, headers=auth()
        )
        assert form_made.status_code == 201, form_made.text
        form = form_made.json()
        client.patch(
            f"{base}/forms/{form['id']}", json={"status": "published"}, headers=auth(version=1)
        )
        submitted = client.post(
            f"/v1/public/forms/{a.id}/{form['public_key']}",
            json={"answers": {"first": "Bo", "email": "bo.hooks@example.org"}},
            headers={"Idempotency-Key": "hooks-1"},
        )
        result["changes"] = [made.status_code, moved.status_code, submitted.status_code]
        events = _events(a.id)
        result["events"] = [e["event"] for e in events]
        result["one_endpoint"] = {e["endpoint"] for e in events} == {endpoint["id"]}

        def first(name: str) -> Any:
            return next((e["data"] for e in events if e["event"] == name), None)

        result["contact_created"] = first("contact.created")
        result["contact_updated"] = first("contact.updated")
        result["deal"] = first("deal.stage_changed")
        result["form"] = first("form.submitted")
        result["ids"] = {
            "contact": contact["id"],
            "deal": deal["id"],
            "pipeline": pipeline["id"],
            "stage": stages[1],
            "form": form["id"],
        }
        result["other_workspace"] = [e["event"] for e in _events(b.id)]

        # --- History, removal ------------------------------------------------------------
        listed = client.get(f"{base}/webhooks", headers=auth()).json()
        deliveries = listed["items"][0]["deliveries"]
        dumped = json.dumps(listed)
        result["history"] = [
            len(deliveries),
            sorted({d["status"] for d in deliveries}),
            "ada.hooks" in dumped or "event_data" in dumped,
            listed["events"],
        ]
        result["removed"] = [
            client.delete(f"{base}/webhooks/{endpoint['id']}", headers=auth()).status_code,
            client.delete(f"{base}/webhooks/{endpoint['id']}", headers=auth()).status_code,
        ]
        count = len(_events(a.id))
        client.post(
            f"{base}/contacts",
            json={"first_name": "Late", "email": f"late.{uuid.uuid4().hex[:6]}@example.org"},
            headers=auth(),
        )
        result["after_removal"] = len(_events(a.id)) - count
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
