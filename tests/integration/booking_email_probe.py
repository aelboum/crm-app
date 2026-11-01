"""Drives booking confirmation emails (decision P6-E2) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_booking_emails.py`.
Sending stays off, so emails are recorded as queued and none leaves this
machine. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

_EMAILS = """
SELECT purpose, to_email, subject, text_body, status, contact_id, created_by_user_id
  FROM crm_app.email_message WHERE tenant_id = :t ORDER BY created_at
"""


def _emails(workspace: uuid.UUID) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(_EMAILS), {"t": workspace})]


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("booking_email_probe runs only with ENVIRONMENT=test")
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    a = _new_workspace("booking-email-a")
    auth = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    day = datetime.combine(datetime.now(UTC).date() + timedelta(days=2), time(), tzinfo=UTC)
    result: dict[str, Any] = {"owner": str(a.owner_id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        settings = client.get(f"{base}/settings", headers=auth).json()
        client.patch(
            f"{base}/settings",
            json={
                "time_zone": "Europe/Amsterdam",
                "business_hours": [{"opens": "08:00", "closes": "20:00"}] * 7,
            },
            headers={**auth, "If-Match": f'"{settings["version"]}"'},
        )

        def page(name: str, **extra: Any) -> tuple[dict[str, Any], str]:
            made = client.post(
                f"{base}/booking-pages",
                json={"name": name, "notice_minutes": 0, "kind": "phone", **extra},
                headers=auth,
            ).json()
            client.patch(
                f"{base}/booking-pages/{made['id']}",
                json={"status": "published"},
                headers={**auth, "If-Match": '"1"'},
            )
            return made, f"/v1/public/booking-pages/{a.id}/{made['public_key']}"

        def book(path: str, hour: int, key: str, **extra: Any) -> Any:
            body = {
                "starts_at": (day + timedelta(hours=hour)).isoformat(),
                "first_name": "Ada",
                "email": "Ada@Example.TEST",
                **extra,
            }
            return client.post(path, json=body, headers={"Idempotency-Key": key})

        on, on_path = page("Intro call")
        result["default_flag"] = on["confirmation_email"]
        first = book(on_path, 9, f"b-{secrets.token_hex(4)}-1")
        token = first.json()["token"]
        replay_key = f"b-{secrets.token_hex(4)}-2"
        book(on_path, 10, replay_key)
        book(on_path, 10, replay_key)  # an idempotent replay
        result["after_bookings"] = _emails(a.id)
        result["token_in_email"] = any(token in e["text_body"] for e in result["after_bookings"])

        off, off_path = page("Quiet call", confirmation_email=False)
        result["off_flag"] = off["confirmation_email"]
        book(off_path, 12, f"b-{secrets.token_hex(4)}-3", email="grace@example.test")
        book(on_path, 14, f"b-{secrets.token_hex(4)}-4", email="bot@example.test", website="x")
        result["after_off_and_bot"] = len(_emails(a.id))

        item = f"{base}/booking-pages/{off['id']}"
        match = {**auth, "If-Match": f'"{off["version"] + 1}"'}
        result["patch_null"] = client.patch(
            item, json={"confirmation_email": None}, headers=match
        ).status_code
        result["patch_string"] = client.patch(
            item, json={"confirmation_email": "yes"}, headers=match
        ).status_code
        turned = client.patch(item, json={"confirmation_email": True}, headers=match)
        result["patch_true"] = [turned.status_code, turned.json().get("confirmation_email")]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
