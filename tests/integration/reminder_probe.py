"""Drives appointment reminders (decision P5-D) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_reminders.py`. Seeds
throwaway workspaces with made-up records; nothing is handed to an email
provider (sending stays off). Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import reminders
from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.task_route_probe import _archive
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("reminder_probe runs only with ENVIRONMENT=test")
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    a = _new_workspace("remind-a")
    b = _new_workspace("remind-b")
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    now = datetime.now(UTC)
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(workspace: uuid.UUID, caller: str, **body: Any) -> str:
            return str(
                client.post(
                    f"/v1/workspaces/{workspace}/contacts", json=body, headers=auth(caller)
                ).json()["id"]
            )

        ada = contact(a.id, "owner", first_name="Ada", email="ada@customer.example.org")
        bob = contact(a.id, "owner", first_name="Bob", phone="+31 20 555 0100")
        old = contact(a.id, "owner", first_name="Old", email="old@customer.example.org")
        bo = contact(b.id, "other_owner", first_name="Bo", email="bo@customer.example.org")

        def book(
            workspace: Any, caller: str, hours: float, contact_id: str | None, **extra: Any
        ) -> dict[str, Any]:
            start = now + timedelta(hours=hours)
            body = {
                "title": extra.pop("title", "Intro call"),
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
                "host_user_id": str(workspace.owner_id),
                "contact_id": contact_id,
                "allow_conflict": True,
                **extra,
            }
            made = client.post(
                f"/v1/workspaces/{workspace.id}/appointments",
                json=body,
                headers=auth(caller),
            )
            if made.status_code != 201:
                raise SystemExit(f"booking failed: {made.status_code} {made.text[:300]}")
            return made.json()

        def made_earlier(workspace: uuid.UUID, appointment_id: str) -> None:
            with tenant_session_scope(workspace) as session:
                session.execute(
                    text(
                        "UPDATE crm_app.appointment SET created_at = now() - interval '3 days'"
                        " WHERE tenant_id = :t AND id = :i"
                    ),
                    {"t": workspace, "i": appointment_id},
                )

        due = book(a, "owner", 23, ada, note="Internal: discount up to 10%")
        no_email = book(a, "owner", 20, bob)
        archived = book(a, "owner", 21, old)
        _archive(a.id, old)
        nobody = book(a, "owner", 22, None)
        just_booked = book(a, "owner", 23.5, ada)
        later = book(a, "owner", 30, ada)
        cancelled = book(a, "owner", 10, ada)
        other = book(b, "other_owner", 23, bo)
        for appointment in (due, no_email, archived, nobody, later, cancelled):
            made_earlier(a.id, appointment["id"])
        made_earlier(b.id, other["id"])
        client.patch(
            f"/v1/workspaces/{a.id}/appointments/{cancelled['id']}",
            json={"status": "cancelled"},
            headers=auth("owner", cancelled["version"]),
        )

        # Off by default: nothing is reminded.
        result["off"] = reminders.run_due()["queued"]

        def settings(caller: str, lead: int | None) -> int:
            current = client.get(f"/v1/workspaces/{a.id}/settings", headers=auth(caller))
            return client.patch(
                f"/v1/workspaces/{a.id}/settings",
                json={"reminder_lead_minutes": lead},
                headers=auth(caller, current.json()["version"]),
            ).status_code

        result["setting"] = [
            settings("member", 1440),
            settings("owner", 45),
            settings("owner", 1440),
            client.get(f"/v1/workspaces/{a.id}/settings", headers=auth()).json()[
                "reminder_lead_minutes"
            ],
        ]

        def outcomes(appointment: dict[str, Any]) -> list[list[Any]]:
            with tenant_session_scope(a.id) as session:
                rows = session.execute(
                    text(
                        "SELECT kind, outcome, skip_reason FROM crm_app.appointment_reminder"
                        " WHERE tenant_id = :t AND appointment_id = :i ORDER BY created_at"
                    ),
                    {"t": a.id, "i": appointment["id"]},
                ).all()
            return [list(row) for row in rows]

        first = reminders.run_due()
        second = reminders.run_due()
        result["runs"] = [first["queued"], first["skipped"], second["queued"], second["skipped"]]
        result["outcomes"] = {
            name: outcomes(appointment)
            for name, appointment in {
                "due": due,
                "no_email": no_email,
                "archived": archived,
                "nobody": nobody,
                "just_booked": just_booked,
                "later": later,
                "cancelled": cancelled,
            }.items()
        }
        with tenant_session_scope(b.id) as session:
            result["other_workspace"] = session.execute(
                text("SELECT count(*) FROM crm_app.appointment_reminder WHERE tenant_id = :t"),
                {"t": b.id},
            ).scalar_one()

        with tenant_session_scope(a.id) as session:
            email = session.execute(
                text(
                    "SELECT m.purpose, m.to_email, m.subject, m.text_body, m.status"
                    " FROM crm_app.email_message m JOIN crm_app.appointment_reminder r"
                    " ON r.email_message_id = m.id AND r.tenant_id = m.tenant_id"
                    " WHERE r.tenant_id = :t AND r.appointment_id = :i"
                ),
                {"t": a.id, "i": due["id"]},
            ).one()
        result["email"] = [
            email[0],
            email[1],
            email[2].startswith("Reminder: Intro call, "),
            "Ada" in email[3],
            "discount" in email[3],
            email[4],
        ]

        # Rescheduled: reminded again for the new time.
        moved = (now + timedelta(hours=22)).isoformat()
        client.patch(
            f"/v1/workspaces/{a.id}/appointments/{due['id']}",
            json={
                "starts_at": moved,
                "ends_at": (now + timedelta(hours=22, minutes=30)).isoformat(),
                "allow_conflict": True,
            },
            headers=auth("owner", due["version"]),
        )
        result["rescheduled"] = reminders.run_due()["queued"]

        status_path = f"/v1/workspaces/{a.id}/appointments/{{}}/reminders"
        due_status = client.get(status_path.format(due["id"]), headers=auth("reader")).json()
        later_status = client.get(status_path.format(later["id"]), headers=auth()).json()
        result["status"] = [
            due_status["lead_minutes"],
            len(due_status["items"]),
            due_status["next_at"],
            later_status["next_at"] is not None,
            client.get(status_path.format(no_email["id"]), headers=auth()).json()[
                "recipient_problem"
            ],
        ]

        # Sending one now.
        def send(appointment: dict[str, Any], caller: str = "owner", ws: Any = a) -> Any:
            return client.post(
                f"/v1/workspaces/{ws.id}/appointments/{appointment['id']}/reminders",
                headers=auth(caller),
            )

        sent = send(later, "member")
        result["manual"] = [
            sent.status_code,
            sent.json()["kind"],
            send(later).json()["detail"]["code"],
            send(no_email).json()["detail"],
            send(cancelled).json()["detail"]["reason"],
            send(later, "reader").status_code,
            send(other, "owner").status_code,
            send(later, "outsider").status_code,
        ]

        # Off again: the workspace leaves the registry.
        settings("owner", None)
        with session_scope() as session:
            result["registry_after_off"] = session.execute(
                text("SELECT count(*) FROM crm_app.reminder_workspace WHERE workspace_id = :w"),
                {"w": a.id},
            ).scalar_one()
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
