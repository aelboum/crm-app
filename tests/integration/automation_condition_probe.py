"""Drives automation conditions on a contact custom field (decision P8-G)
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_condition.py`.
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


def _branch(workspace: uuid.UUID, run: uuid.UUID) -> str:
    rows = _q(
        workspace,
        "SELECT branch FROM crm_app.automation_run WHERE tenant_id = :t AND id = :r",
        r=run,
    )
    return rows[0]["branch"]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_condition_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("cond-a")
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

        def tag(name: str) -> str:
            made = client.post(f"{base}/tags", json={"name": name}, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()["id"]

        def create(name: str, condition: dict[str, Any], yes: str, no: str) -> Any:
            return client.post(
                f"{base}/automations",
                json={
                    "name": name,
                    "definition": {
                        "trigger": {"type": "contact_created"},
                        "condition": condition,
                        "yes": [{"type": "add_tag", "tag_id": yes}],
                        "no": [{"type": "add_tag", "tag_id": no}],
                    },
                },
                headers=auth(),
            )

        def activate(made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{base}/automations/{body['id']}/activate",
                headers=auth(version=body["version"]),
            )

        def contact(name: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
            email = f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org"
            body: dict[str, Any] = {"first_name": name, "email": email}
            if values:
                body["custom_fields"] = values
            made = client.post(f"{base}/contacts", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()

        def tags_of(contact_id: str) -> list[str]:
            rows = _q(
                a.id,
                "SELECT tag_id FROM crm_app.contact_tag WHERE tenant_id = :t AND contact_id = :c",
                c=contact_id,
            )
            return sorted(str(r["tag_id"]) for r in rows)

        tier = field(
            entity="contact",
            key="tier",
            label="Tier",
            field_type="select",
            options=["Gold", "Silver"],
        )
        field(entity="contact", key="vip", label="VIP", field_type="boolean")
        field(entity="company", key="region", label="Region", field_type="text")
        gold, other = tag("gold"), tag("other")
        result["tags"] = {"gold": gold, "other": other}

        def on(key: str, op: str, values: list[Any] | None = None) -> dict[str, Any]:
            condition: dict[str, Any] = {"field": "custom_field", "key": key, "op": op}
            if values is not None:
                condition["values"] = values
            return condition

        # --- Refused when saved (shape) and when activated (the field) -----------------
        result["refused_save"] = [
            create("Bad op", on("tier", "has", ["Gold"]), gold, other).status_code,
            create("No values", on("tier", "in"), gold, other).status_code,
        ]

        def refusal(condition: dict[str, Any]) -> list[Any]:
            made = create("Refused", condition, gold, other)
            assert made.status_code == 201, made.text
            answer = activate(made)
            return [answer.status_code, answer.json()["detail"]["rule"]]

        result["refused_activate"] = [
            refusal(on("unknown", "present")),
            refusal(on("region", "in", ["North"])),
            refusal(on("tier", "in", ["Platinum"])),
            refusal(on("vip", "in", ["yes"])),
        ]

        # --- A run takes the branch the stored value picks -----------------------------
        made = create("By tier", on("tier", "in", ["Gold"]), gold, other)
        result["stored"] = made.json()["definition"]["condition"]
        result["activated"] = activate(made).status_code
        people = {
            "ann": contact("Ann", {"tier": "Gold"}),
            "bob": contact("Bob", {"tier": "Silver"}),
            "cy": contact("Cy"),
        }
        result["branches"] = {}
        for name, person in people.items():
            run = _run(a.id, person["id"])
            status = automations.advance(a.id, run)
            result["branches"][name] = [status, _branch(a.id, run), tags_of(person["id"])]

        # --- A field archived before the run starts counts as having no value ----------
        dee = contact("Dee", {"tier": "Gold"})
        archived = client.post(f"{base}/custom-fields/{tier['id']}/archive", headers=auth())
        assert archived.is_success, archived.text
        dee_run = _run(a.id, dee["id"])
        result["archived"] = [automations.advance(a.id, dee_run), _branch(a.id, dee_run)]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
