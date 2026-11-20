"""Drives the contact brief's facts and route (decision P9-B) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_contact_brief.py`.
AI stays off in these workspaces (the default), so no provider is ever
called: the route's answer is `unavailable`. Seeds throwaway workspaces.
Refuses to run unless ENVIRONMENT=test.
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

from crm_app import ai, contact_brief
from crm_app.app import create_app
from crm_app.domains import ai_brief
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

SECRETS = ("Ada", "Lovelace", "ada.brief@example.org", "+31 20 123 4567", "Engineer", "Call Ada")


def _sql(workspace: uuid.UUID, statement: str, **values: object) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(text(statement), {"t": workspace, **values})


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("contact_brief_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("brief-a")
    b = _new_workspace("brief-b")
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str | None = "owner") -> dict[str, str]:
        return {} if caller is None else {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    now = datetime.now(UTC)
    with TestClient(create_app(), follow_redirects=False) as client:

        def post(kind: str, body: dict[str, Any]) -> str:
            made = client.post(f"{base}/{kind}", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()["id"]

        ada = post(
            "contacts",
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada.brief@example.org",
                "phone": "+31 20 123 4567",
                "job_title": "Engineer",
                "source": "referral",
                "lifecycle_stage": "lead",
            },
        )
        tag = post("tags", {"name": "Priority"})
        tagged = client.put(
            f"{base}/contacts/{ada}/tags",
            json={"tag_ids": [tag]},
            headers={**auth(), "If-Match": '"1"'},
        )
        assert tagged.is_success, tagged.text
        client.get(f"{base}/pipelines", headers=auth())
        deal = post("opportunities", {"title": "Big deal"})
        _sql(
            a.id,
            "UPDATE crm_app.opportunity SET contact_id = :c WHERE tenant_id = :t AND id = :d",
            c=ada,
            d=deal,
        )
        for title, due, done in (
            ("Call Ada", now - timedelta(days=1), None),  # open, overdue
            ("Send offer", None, None),  # open, no due time
            ("Old", now - timedelta(days=9), now - timedelta(days=8)),  # done
        ):
            task = post("tasks", {"title": title})
            _sql(
                a.id,
                "UPDATE crm_app.task SET contact_id = :c, due_at = :due, completed_at = :done,"
                " completed_by_user_id = CASE WHEN CAST(:done AS timestamptz) IS NULL"
                " THEN NULL ELSE CAST(:by AS uuid) END"
                " WHERE tenant_id = :t AND id = :k",
                c=ada,
                due=due,
                done=done,
                by=str(a.owner_id),
                k=task,
            )
        for starts, status in (
            (now + timedelta(days=2), "confirmed"),  # upcoming
            (now + timedelta(days=3), "cancelled"),
            (now - timedelta(days=2), "completed"),
        ):
            made = post(
                "appointments",
                {
                    "title": "Meet Ada",
                    "starts_at": "2030-01-01T09:00:00Z",
                    "ends_at": "2030-01-01T09:30:00Z",
                    "host_user_id": str(a.owner_id),
                    "allow_conflict": True,
                },
            )
            _sql(
                a.id,
                "UPDATE crm_app.appointment SET contact_id = :c, starts_at = :s,"
                " ends_at = CAST(:s AS timestamptz) + interval '30 minutes', status = :st,"
                " cancelled_at = CASE WHEN :st = 'cancelled' THEN now() END"
                " WHERE tenant_id = :t AND id = :m",
                c=ada,
                s=starts,
                st=status,
                m=made,
            )

        # --- The facts, and what a request would carry ---------------------------------
        found = contact_brief.facts(Scope(workspace=a.id, actor=a.owner_id), uuid.UUID(ada))
        assert found is not None
        facts, today = found
        document = ai_brief.facts_document(facts, today=today)
        result["document"] = {
            key: value
            for key, value in document.items()
            if key not in ("today", "created_on", "recent_history")
        }
        result["history_kinds"] = sorted({h["kind"] for h in document["recent_history"]})
        request = ai.brief_request(facts, today=today)
        sent = json.dumps(
            [part.text for message in request.messages for part in message.parts],
            ensure_ascii=False,
        )
        result["leaked"] = [secret for secret in SECRETS if secret in sent]
        result["missing"] = contact_brief.facts(
            Scope(workspace=b.id, actor=b.owner_id), uuid.UUID(ada)
        )

        # --- The route --------------------------------------------------------------
        def brief(caller: str | None = "owner", contact: str = ada, where: str = base) -> Any:
            answer = client.post(f"{where}/contacts/{contact}/brief", headers=auth(caller))
            return [answer.status_code, answer.json()]

        result["owner"] = brief()
        result["reader"] = brief("reader")
        result["other_owner"] = brief("other_owner")[0]
        result["other_workspace_id"] = brief("other_owner", where=f"/v1/workspaces/{b.id}")
        result["unknown"] = brief(contact=str(uuid.uuid4()))
        result["anonymous"] = brief(None)[0]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
