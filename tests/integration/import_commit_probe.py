"""Commits CSV imports against the integration database, running the worker
job's function directly as the worker would, and prints one `RESULT <json>`
line.

Run in a fresh interpreter by `tests/integration/test_import_commit.py`.
Seeds made-up records into throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import import_commit
from crm_app.app import create_app
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

FILE = (
    "first_name,email,phone\r\n"
    "Sam,sam@example.test,\r\n"  # 1 created
    "Ann,ann@example.test,\r\n"  # 2 becomes a duplicate after the preview: skipped
    "Bo,,\r\n"  # 3 invalid
    "Cy,taken@example.test,\r\n"  # 4 duplicate at preview
    "Di,,+31 6 1234 5678\r\n"  # 5 created
)


def _statuses(workspace: uuid.UUID, import_id: str) -> list[list[Any]]:
    with tenant_session_scope(workspace) as session:
        rows = session.execute(
            text(
                "SELECT row_number, status, record_id IS NOT NULL FROM crm_app.import_row"
                " WHERE import_id = :id ORDER BY row_number"
            ),
            {"id": import_id},
        ).all()
    return [list(row) for row in rows]


def _due(import_id: str) -> str | None:
    with session_scope() as session:
        due = session.execute(
            text("SELECT due_at FROM crm_app.import_expiry WHERE import_id = :id"),
            {"id": import_id},
        ).scalar_one_or_none()
    return None if due is None else due.isoformat()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("import_commit_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("commit-a")
    b = _new_workspace("commit-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "other_owner": issue_session(b.owner_id)[1],
    }
    owner_id = a.owner_id

    def auth(caller: str, content_type: str = "text/csv") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}", "Content-Type": content_type}

    base = f"/v1/workspaces/{a.id}"
    imports = f"{base}/imports"
    scope = Scope(workspace=a.id, actor=owner_id)
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(body: dict[str, object]) -> None:
            response = client.post(
                f"{base}/contacts", json=body, headers=auth("owner", "application/json")
            )
            assert response.status_code == 201, response.text

        def preview(body: str, caller: str = "owner") -> str:
            response = client.post(
                imports, params={"entity": "contact"}, content=body.encode(), headers=auth(caller)
            )
            assert response.status_code == 201, response.text
            return str(response.json()["summary"]["id"])

        def act(import_id: str, verb: str, caller: str = "owner") -> Any:
            return client.post(f"{imports}/{import_id}/{verb}", headers=auth(caller))

        contact({"first_name": "Taken", "email": "taken@example.test"})
        main_id = preview(FILE)
        contact({"first_name": "Ann", "email": "ann@example.test"})  # after the preview

        # --- Who may commit --------------------------------------------------------------
        result["member"] = act(main_id, "commit", "member").status_code
        result["foreign"] = client.post(
            f"/v1/workspaces/{b.id}/imports/{main_id}/commit", headers=auth("other_owner")
        ).status_code

        # --- Committing -------------------------------------------------------------------
        queued = act(main_id, "commit")
        result["queued"] = [queued.status_code, queued.json()["status"]]
        result["commit_again"] = act(main_id, "commit").json()
        second = preview("first_name,email\r\nEd,ed@example.test\r\n", "admin")
        result["one_at_a_time"] = act(second, "commit").json()
        import_commit.run(scope, uuid.UUID(main_id))
        done = client.get(f"{imports}/{main_id}", headers=auth("owner")).json()
        result["done"] = {
            key: done[key]
            for key in (
                "status",
                "created_rows",
                "skipped_rows",
                "failed_rows",
                "invalid_rows",
                "duplicate_rows",
            )
        }
        result["finished"] = done["finished_at"]
        result["rows"] = _statuses(a.id, main_id)
        result["due"] = _due(main_id)
        import_commit.run(scope, uuid.UUID(main_id))  # delivered again
        listed = client.get(f"{base}/contacts", params={"limit": 200}, headers=auth("owner")).json()
        result["contacts"] = sorted(
            [item["first_name"], item["source"]] for item in listed["items"]
        )
        result["second_now"] = act(second, "commit").status_code
        import_commit.run(scope, uuid.UUID(second))

        # --- Nothing to import, cancel, and the queue being unreachable ------------------
        result["nothing"] = act(preview("first_name,email\r\nX,bad\r\n"), "commit").json()
        cancelled = preview("first_name,email\r\nFi,fi@example.test\r\n")
        act(cancelled, "commit")
        result["cancel"] = act(cancelled, "cancel").json()["cancel_requested"]
        import_commit.run(scope, uuid.UUID(cancelled))
        after_cancel = client.get(f"{imports}/{cancelled}", headers=auth("owner")).json()
        result["cancelled"] = [after_cancel["status"], after_cancel["created_rows"]]
        result["cancel_finished"] = act(cancelled, "cancel").json()
        unqueued = preview("first_name,email\r\nGo,go@example.test\r\n")
        act(unqueued, "commit")
        import_commit.unqueue(scope, uuid.UUID(unqueued))
        result["unqueued"] = client.get(f"{imports}/{unqueued}", headers=auth("owner")).json()[
            "status"
        ]
        import_commit.run(scope, uuid.UUID(unqueued))  # a stale delivery finds it previewed

        # --- Batches, a failure and resuming ----------------------------------------------
        big = "first_name,email\r\n" + "".join(
            f"Bulk{n},bulk{n}@example.test\r\n" for n in range(1, 1201)
        )
        big_id = preview(big, "admin")
        act(big_id, "commit", "admin")
        calls = {"n": 0}
        original = import_commit.insert_record

        def flaky(*args: Any, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 700:
                raise RuntimeError("worker lost its connection")
            original(*args, **kwargs)

        import_commit.insert_record = flaky  # type: ignore[assignment]
        import_commit.run(Scope(workspace=a.id, actor=owner_id), uuid.UUID(big_id))
        import_commit.insert_record = original
        failed = client.get(f"{imports}/{big_id}", headers=auth("admin")).json()
        result["failed"] = [
            failed["status"],
            failed["created_rows"],
            failed["finished_at"] is not None,
        ]
        resumed = act(big_id, "resume", "admin")
        result["resumed"] = [resumed.status_code, resumed.json()["status"]]
        import_commit.run(scope, uuid.UUID(big_id))
        finished = client.get(f"{imports}/{big_id}", headers=auth("admin")).json()
        result["big"] = [finished["status"], finished["created_rows"], finished["failed_rows"]]
        result["resume_again"] = act(big_id, "resume", "admin").json()
        result["ids"] = {"main": main_id, "big": big_id}
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
