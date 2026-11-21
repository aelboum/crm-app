"""Drives the automation step that waits until a contact's date (decision
P8-D) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_date_wait.py`.
Runs are advanced by calling the job's function directly, as the worker
would. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from crm_app.domains import automations as rules
from tests.integration.workspace_route_probe import _new_workspace


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _run(workspace: uuid.UUID, contact: str) -> dict[str, Any]:
    return _q(
        workspace,
        "SELECT id, status, resume_at FROM crm_app.automation_run"
        " WHERE tenant_id = :t AND contact_id = :c",
        c=contact,
    )[0]


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
        raise SystemExit("automation_date_wait_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("date-wait-a")
    token = issue_session(a.owner_id)[1]

    def auth(version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def field(**body: object) -> None:
            made = client.post(f"{base}/custom-fields", json=body, headers=auth())
            assert made.status_code == 201, made.text

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

        def wait(key: str, **extra: object) -> dict[str, Any]:
            return {"type": "wait_until_date", "field_key": key, "hour": 9, **extra}

        field(entity="contact", key="renewal", label="Renewal", field_type="date")
        field(entity="contact", key="note", label="Note", field_type="text")
        tag = client.post(f"{base}/tags", json={"name": "after"}, headers=auth()).json()["id"]

        # --- Refused when saved (shape) and when activated (the field) -----------------
        result["refused_save"] = [
            create("No hour", [{"type": "wait_until_date", "field_key": "renewal"}]).status_code,
            create("Far", [wait("renewal", offset_days=400)]).status_code,
        ]
        refused = []
        for key in ("unknown", "note"):
            made = create("Refused", [wait(key)])
            assert made.status_code == 201, made.text
            answer = activate(made)
            refused.append([answer.status_code, answer.json()["detail"]["rule"]])
        result["refused_activate"] = refused

        made = create(
            "Before renewal",
            [wait("renewal", offset_days=-3), {"type": "add_tag", "tag_id": tag}],
        )
        result["stored"] = made.json()["definition"]["yes"][0]
        result["activated"] = activate(made).status_code

        def contact(name: str, renewal: str | None) -> str:
            body: dict[str, Any] = {
                "first_name": name,
                "email": f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org",
            }
            if renewal is not None:
                body["custom_fields"] = {"renewal": renewal}
            made = client.post(f"{base}/contacts", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()["id"]

        soon = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
        people = {"Ann": contact("Ann", soon), "Bob": contact("Bob", "2020-01-01")}
        people["Cy"] = contact("Cy", None)
        result["runs"] = {}
        for name, contact_id in people.items():
            run = _run(a.id, contact_id)
            status = automations.advance(a.id, run["id"])
            after = _run(a.id, contact_id)
            result["runs"][name] = {
                "status": status,
                "steps": _steps(a.id, run["id"]),
                "resume_at": None if after["resume_at"] is None else after["resume_at"].isoformat(),
            }
        expected = rules.date_wait_at(soon, -3, 9, "Europe/Amsterdam")
        assert expected is not None
        result["expected_resume"] = expected.isoformat()

        # The run history lists the new step (its response names every action).
        listed = client.get(f"{base}/automations/{made.json()['id']}/runs", headers=auth())
        result["runs_listed"] = listed.status_code

        # A date changed after the wait began does not move it; once due, the
        # run goes on.
        ann_run = _run(a.id, people["Ann"])["id"]
        changed = client.patch(
            f"{base}/contacts/{people['Ann']}",
            json={"custom_fields": {"renewal": "2030-01-01"}},
            headers=auth(version=1),
        )
        assert changed.is_success, changed.text
        result["still_waiting"] = automations.advance(a.id, ann_run)
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "UPDATE crm_app.automation_run SET resume_at = now() - interval '1 minute'"
                    " WHERE tenant_id = :t AND id = :r"
                ),
                {"t": a.id, "r": ann_run},
            )
        result["resumed"] = automations.advance(a.id, ann_run)
        result["resumed_steps"] = _steps(a.id, ann_run)
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
