"""Drives automation conditions on a contact's deals (decision P8-H) and
prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_deal_condition.py`.
The automations start when a tag is added, after the contacts' deals exist.
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


def _runs(workspace: uuid.UUID, contact: str) -> list[dict[str, Any]]:
    return _q(
        workspace,
        "SELECT r.id, a.name FROM crm_app.automation_run r"
        " JOIN crm_app.automation a ON a.tenant_id = r.tenant_id AND a.id = r.automation_id"
        " WHERE r.tenant_id = :t AND r.contact_id = :c",
        c=contact,
    )


def _branch(workspace: uuid.UUID, run: uuid.UUID) -> str:
    rows = _q(
        workspace,
        "SELECT branch FROM crm_app.automation_run WHERE tenant_id = :t AND id = :r",
        r=run,
    )
    return rows[0]["branch"]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_deal_condition_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("deal-cond-a")
    b = _new_workspace("deal-cond-b")
    tokens = {"a": issue_session(a.owner_id)[1], "b": issue_session(b.owner_id)[1]}

    def auth(who: str = "a", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[who]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def post(kind: str, body: dict[str, Any]) -> Any:
            made = client.post(f"{base}/{kind}", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()

        def stages(where: str, who: str) -> list[str]:
            listed = client.get(f"{where}/pipelines", headers=auth(who))
            assert listed.is_success, listed.text
            return [s["id"] for s in listed.json()["items"][0]["stages"]]

        first, second, *_ = stages(base, "a")
        foreign = stages(f"/v1/workspaces/{b.id}", "b")[0]
        start, yes, no = (post("tags", {"name": n})["id"] for n in ("start", "yes", "no"))

        def create(name: str, condition: dict[str, Any]) -> Any:
            return client.post(
                f"{base}/automations",
                json={
                    "name": name,
                    "definition": {
                        "trigger": {"type": "tag_added", "tag_id": start},
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

        # --- Refused when saved (shape) and when activated (the stages) ----------------
        result["refused_save"] = [
            create(
                "Bad outcome", {"field": "deal", "op": "has", "values": ["pending"]}
            ).status_code,
            create("Bad op", {"field": "deal_stage", "op": "in", "values": [first]}).status_code,
        ]
        refused = []
        for stage in (str(uuid.uuid4()), foreign):
            made = create("Refused", {"field": "deal_stage", "op": "has", "values": [stage]})
            assert made.status_code == 201, made.text
            answer = activate(made)
            refused.append([answer.status_code, answer.json()["detail"]["rule"]])
        result["refused_activate"] = refused

        # --- Contacts and their deals, before the automations are active ---------------
        def contact(name: str) -> str:
            email = f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org"
            return post("contacts", {"first_name": name, "email": email})["id"]

        def deal(contact_id: str, stage: str, outcome: str | None = None) -> None:
            made = post(
                "opportunities", {"title": "Deal", "stage_id": stage, "contact_id": contact_id}
            )
            if outcome is not None:
                closed = client.post(
                    f"{base}/opportunities/{made['id']}/outcome",
                    json={"outcome": outcome},
                    headers=auth(version=made["version"]),
                )
                assert closed.is_success, closed.text

        people = {name: contact(name) for name in ("Ann", "Bob", "Cy")}
        deal(people["Ann"], first)  # open, in the first stage
        deal(people["Bob"], first, "won")  # won, so no open deal
        deal(people["Bob"], second)  # open, in another stage
        # Cy has no deal.

        made_outcome = create("Has won", {"field": "deal", "op": "has", "values": ["won"]})
        made_stage = create(
            "Open in first", {"field": "deal_stage", "op": "has", "values": [first]}
        )
        result["stored"] = [
            made_outcome.json()["definition"]["condition"],
            made_stage.json()["definition"]["condition"],
        ]
        result["activated"] = [activate(made_outcome).status_code, activate(made_stage).status_code]

        result["branches"] = {}
        for name, contact_id in people.items():
            tagged = client.put(
                f"{base}/contacts/{contact_id}/tags",
                json={"tag_ids": [start]},
                headers=auth(version=1),
            )
            assert tagged.is_success, tagged.text
            branches = {}
            for run in _runs(a.id, contact_id):
                automations.advance(a.id, run["id"])
                branches[run["name"]] = _branch(a.id, run["id"])
            result["branches"][name] = branches
        result["first_stage"] = first
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
