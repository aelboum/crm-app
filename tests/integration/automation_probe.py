"""Drives automations (decision P8-A) against the integration database and
prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automations.py`.
Runs are advanced by calling the job's function directly, as the worker
would. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from crm_app.models import AutomationDue
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace

_TAGS_OF = "SELECT tag_id FROM crm_app.contact_tag WHERE tenant_id = :t AND contact_id = :c"
_TASKS_OF = (
    "SELECT title, priority, assignee_user_id, due_at IS NOT NULL AS due FROM crm_app.task"
    " WHERE tenant_id = :t AND contact_id = :c ORDER BY created_at"
)


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        rows = session.execute(text(sql), {"t": workspace, **values})
        if not sql.lstrip().upper().startswith("SELECT"):
            return []
        return [dict(r._mapping) for r in rows]


def _run(workspace: uuid.UUID, contact: str) -> dict[str, Any] | None:
    rows = _q(
        workspace,
        "SELECT id, status, branch, next_step, attempts, last_error FROM crm_app.automation_run"
        " WHERE tenant_id = :t AND contact_id = :c",
        c=contact,
    )
    return rows[0] if rows else None


def _due(run_id: object) -> bool:
    with session_scope() as session:
        return session.get(AutomationDue, uuid.UUID(str(run_id))) is not None


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("automation-a")
    b = _new_workspace("automation-b")
    admin_id, admin = _member(a, Role.ADMIN)
    _, member = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
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
    result: dict[str, Any] = {"owner": str(a.owner_id), "admin": str(admin_id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def tag(name: str) -> str:
            return str(
                client.post(f"{base}/tags", json={"name": name}, headers=auth()).json()["id"]
            )

        hot, cold, doomed = tag("Hot lead"), tag("Not a lead"), tag("Doomed")
        result["tags"] = {"hot": hot, "cold": cold}
        definition = {
            "trigger": {"type": "contact_created", "sources": ["manual", "form"]},
            "condition": {"field": "lifecycle_stage", "op": "in", "values": ["lead"]},
            "yes": [
                {"type": "add_tag", "tag_id": hot},
                {"type": "assign_owner", "user_id": str(admin_id)},
                {
                    "type": "create_task",
                    "title": "Call the new lead",
                    "priority": "high",
                    "due_minutes": 15,
                },
                {"type": "wait", "minutes": 60},
                {"type": "create_task", "title": "Follow up", "assignee": "contact_owner"},
            ],
            "no": [{"type": "add_tag", "tag_id": cold}],
        }

        def create(name: str, body: dict[str, Any], caller: str = "owner") -> Any:
            return client.post(
                f"{base}/automations", json={"name": name, "definition": body}, headers=auth(caller)
            )

        # --- Definitions: who may, and the rules ----------------------------------------
        result["create_access"] = {
            caller: create("x", definition, caller).status_code
            for caller in ("member", "outsider", "other_owner")
        }
        made = create("  New lead follow-up ", definition)
        auto = made.json()
        result["created"] = [made.status_code, auto["name"], auto["status"], auto["active_version"]]
        item = f"{base}/automations/{auto['id']}"
        result["read_access"] = {
            caller: client.get(item, headers=auth(caller)).status_code
            for caller in ("member", "other_owner", "outsider")
        }
        bad = {
            "unknown_action": {**definition, "yes": [{"type": "run_code", "code": "x"}]},
            "no_without_condition": {**definition, "condition": None},
            "bad_minutes": {**definition, "yes": [{"type": "wait", "minutes": 0}]},
            "import_source": {
                **definition,
                "trigger": {"type": "contact_created", "sources": ["import"]},
            },
            "extra_field": {**definition, "script": "x"},
        }
        result["refused"] = {
            label: create("Bad", body).json()["detail"]["code"] for label, body in bad.items()
        }
        empty = create("Empty", {"trigger": {"type": "contact_created"}}).json()
        result["activate_empty"] = client.post(
            f"{base}/automations/{empty['id']}/activate", headers=auth("owner", empty["version"])
        ).json()["detail"]
        gone_body = {**definition, "yes": [{"type": "add_tag", "tag_id": doomed}], "no": []}
        gone = create("Gone tag", gone_body).json()
        client.delete(f"{base}/tags/{doomed}", headers=auth())
        result["activate_gone_tag"] = client.post(
            f"{base}/automations/{gone['id']}/activate", headers=auth("owner", gone["version"])
        ).json()["detail"]

        activated = client.post(f"{item}/activate", headers=auth("owner", auto["version"]))
        auto = activated.json()
        result["activated"] = [activated.status_code, auto["status"], auto["active_version"]]
        result["edit_active"] = client.patch(
            item, json={"definition": definition}, headers=auth("owner", auto["version"])
        ).json()["detail"]

        def contact(
            stage: str = "lead", source: str | None = None, where: str = base, caller: str = "owner"
        ) -> str:
            body: dict[str, Any] = {
                "first_name": "C",
                "email": f"c.{secrets.token_hex(4)}@example.test",
                "lifecycle_stage": stage,
            }
            if source is not None:
                body["source"] = source
            response = client.post(f"{where}/contacts", json=body, headers=auth(caller))
            assert response.status_code == 201, response.text
            return str(response.json()["id"])

        # --- A matching contact runs the yes branch, waits, then finishes ------------------
        lead = contact()
        run = _run(a.id, lead)
        assert run is not None
        result["started"] = [run["status"], _due(run["id"])]
        result["first_advance"] = automations.advance(a.id, run["id"])
        owner_row = _q(
            a.id,
            "SELECT owner_user_id FROM crm_app.contact WHERE tenant_id = :t AND id = :c",
            c=lead,
        )
        result["after_first"] = {
            "run": _run(a.id, lead),
            "tags": [r["tag_id"] for r in _q(a.id, _TAGS_OF, c=lead)],
            "owner": owner_row[0]["owner_user_id"],
            "tasks": _q(a.id, _TASKS_OF, c=lead),
            "due": _due(run["id"]),
        }
        # A retried job while waiting does nothing.
        result["while_waiting"] = [
            automations.advance(a.id, run["id"]),
            len(_q(a.id, _TASKS_OF, c=lead)),
        ]
        _q(
            a.id,
            "UPDATE crm_app.automation_run SET resume_at = now() - interval '1 minute'"
            " WHERE tenant_id = :t AND id = :r",
            r=run["id"],
        )
        # Two jobs at once after the wait: one follow-up task.
        with ThreadPoolExecutor(max_workers=2) as pool:
            result["parallel"] = sorted(
                pool.map(lambda _: automations.advance(a.id, run["id"]), range(2))
            )
        tasks = _q(a.id, _TASKS_OF, c=lead)
        result["after_wait"] = {
            "tasks": [r["title"] for r in tasks],
            "follow_up_assignee": tasks[-1]["assignee_user_id"],
            "run": _run(a.id, lead),
            "due": _due(run["id"]),
            "steps": _q(
                a.id,
                "SELECT branch, position, action, outcome FROM crm_app.automation_step"
                " WHERE tenant_id = :t AND run_id = :r ORDER BY position",
                r=run["id"],
            ),
        }
        result["replay_completed"] = [
            automations.advance(a.id, run["id"]),
            len(_q(a.id, _TASKS_OF, c=lead)),
        ]

        # --- The no branch, sources, other workspaces --------------------------------------
        customer = contact(stage="customer")
        cust_run = _run(a.id, customer)
        assert cust_run is not None
        result["no_branch"] = [
            automations.advance(a.id, cust_run["id"]),
            [r["tag_id"] for r in _q(a.id, _TAGS_OF, c=customer)],
            (_run(a.id, customer) or {}).get("branch"),
        ]
        result["other_source"] = _run(a.id, contact(source="referral"))
        contact(where=f"/v1/workspaces/{b.id}", caller="other_owner")
        result["other_workspace_runs"] = _q(
            b.id, "SELECT count(*) AS n FROM crm_app.automation_run"
        )[0]["n"]

        # --- A deleted contact cancels its run ----------------------------------------------
        vanishing = contact()
        van_run = _run(a.id, vanishing)
        assert van_run is not None
        client.delete(f"{base}/contacts/{vanishing}", headers=auth())
        result["deleted_contact"] = automations.advance(a.id, van_run["id"])

        # --- Failures are counted and end the run -------------------------------------------
        flaky = contact()
        flaky_run = _run(a.id, flaky)
        assert flaky_run is not None
        statuses = [
            automations.record_failure(a.id, flaky_run["id"], "operationalerror") for _ in range(5)
        ]
        result["failures"] = [statuses, _run(a.id, flaky), _due(flaky_run["id"])]

        # --- History; pausing stops new runs; deleting removes everything -------------------
        history = client.get(f"{item}/runs", headers=auth("member"))
        items = history.json()["items"]
        result["history"] = [history.status_code, len(items), items[-1]["steps"][0]]
        paused = client.post(f"{item}/pause", headers=auth("owner", auto["version"])).json()
        result["paused"] = [paused["status"], _run(a.id, contact())]
        result["delete_member"] = client.delete(item, headers=auth("member")).status_code
        result["deleted"] = client.delete(item, headers=auth()).status_code
        result["after_delete"] = [
            _q(a.id, "SELECT count(*) AS n FROM crm_app.automation_run")[0]["n"],
            _due(cust_run["id"]),
        ]

    # The sweeper's read hands out what is due once, pushed back for a retry.
    stale = uuid.uuid4()
    with session_scope() as session:
        session.add(
            AutomationDue(
                run_id=stale, workspace_id=a.id, due_at=datetime.now(UTC) - timedelta(minutes=1)
            )
        )
    first = [run_id for _, run_id in automations.due()]
    second = [run_id for _, run_id in automations.due()]
    result["due_twice"] = [stale in first, stale in second]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
