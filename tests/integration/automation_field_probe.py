"""Drives the automation step that sets a contact custom field (decision
P8-F) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_field.py`.
Runs are advanced by calling the job's function directly, as the worker
would. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
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

from crm_app import automations
from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _run(workspace: uuid.UUID, contact: str) -> uuid.UUID:
    rows = _q(
        workspace,
        "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t AND contact_id = :c",
        c=contact,
    )
    return rows[0]["id"]


def _steps(workspace: uuid.UUID, run: uuid.UUID) -> list[list[Any]]:
    rows = _q(
        workspace,
        "SELECT position, action, outcome, detail FROM crm_app.automation_step"
        " WHERE tenant_id = :t AND run_id = :r ORDER BY position",
        r=run,
    )
    return [[r["position"], r["action"], r["outcome"], r["detail"]] for r in rows]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_field_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("field-a")
    token = issue_session(a.owner_id)[1]

    def auth(version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def field(**body: object) -> dict[str, Any]:
            made = client.post(f"{base}/custom-fields", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()

        def create(name: str, yes: list[dict[str, Any]]) -> Any:
            return client.post(
                f"{base}/automations",
                json={
                    "name": name,
                    "definition": {"trigger": {"type": "contact_created"}, "yes": yes},
                },
                headers=auth(),
            )

        def activate(made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{base}/automations/{body['id']}/activate",
                headers=auth(version=body["version"]),
            )

        def contact(name: str) -> dict[str, Any]:
            email = f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org"
            made = client.post(
                f"{base}/contacts", json={"first_name": name, "email": email}, headers=auth()
            )
            assert made.status_code == 201, made.text
            return made.json()

        def step(key: str, value: object) -> dict[str, Any]:
            return {"type": "set_custom_field", "field_key": key, "value": value}

        tier = field(
            entity="contact",
            key="tier",
            label="Tier",
            field_type="select",
            options=["Gold", "Silver"],
        )
        seats = field(entity="contact", key="seats", label="Seats", field_type="number")
        field(entity="contact", key="vip", label="VIP", field_type="boolean")
        field(entity="company", key="region", label="Region", field_type="text")

        # --- Refused when saved (shape) and when activated (the field) -----------------
        result["refused_save"] = [
            create("Bad key", [step("Not a key", "x")]).status_code,
            create("No value", [step("tier", None)]).status_code,
        ]

        def refusal(yes: list[dict[str, Any]]) -> list[Any]:
            made = create("Refused", yes)
            assert made.status_code == 201, made.text
            answer = activate(made)
            return [answer.status_code, answer.json()["detail"]["rule"]]

        result["refused_activate"] = [
            refusal([step("unknown", "x")]),
            refusal([step("region", "North")]),
            refusal([step("tier", "Platinum")]),
            refusal([step("seats", "5")]),
            refusal([step("vip", 1)]),
        ]

        # --- A run sets the fields; a retry changes nothing ----------------------------
        made = create(
            "Set the plan",
            [step("tier", "Gold"), step("seats", 5.0), step("vip", True)],
        )
        result["stored"] = made.json()["definition"]["yes"]
        result["activated"] = activate(made).status_code
        ann = contact("Ann")
        run = _run(a.id, ann["id"])
        result["status"] = automations.advance(a.id, run)
        result["steps"] = _steps(a.id, run)
        after = client.get(f"{base}/contacts/{ann['id']}", headers=auth()).json()
        result["values"] = after["custom_fields"]
        automations.advance(a.id, run)
        again = client.get(f"{base}/contacts/{ann['id']}", headers=auth()).json()
        result["retry_same_version"] = again["version"] == after["version"]
        result["history"] = _q(
            a.id,
            "SELECT kind, fields, source, actor_user_id FROM crm_app.activity"
            " WHERE tenant_id = :t AND contact_id = :c AND source = 'automation'",
            c=ann["id"],
        )
        result["audit"] = _q(
            a.id,
            "SELECT metadata->'custom_field_keys' AS keys, metadata::text AS raw"
            " FROM core.audit_log WHERE tenant_id = :t AND resource_id = :c"
            " AND action = 'crm_app.contact.updated' ORDER BY created_at",
            c=ann["id"],
        )
        runs = client.get(f"{base}/automations/{made.json()['id']}/runs", headers=auth())
        result["runs_listed"] = [
            runs.status_code,
            [s["action"] for s in runs.json()["items"][0]["steps"]] if runs.is_success else None,
        ]

        # --- A field archived, an option removed: the step is skipped ------------------
        client.post(f"{base}/custom-fields/{seats['id']}/archive", headers=auth())
        changed = client.patch(
            f"{base}/custom-fields/{tier['id']}",
            json={"options": ["Silver"]},
            headers=auth(version=tier["version"]),
        )
        assert changed.is_success, changed.text
        bob = contact("Bob")
        bob_run = _run(a.id, bob["id"])
        result["later_status"] = automations.advance(a.id, bob_run)
        result["later_steps"] = _steps(a.id, bob_run)
        result["later_values"] = client.get(f"{base}/contacts/{bob['id']}", headers=auth()).json()[
            "custom_fields"
        ]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
