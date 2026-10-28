"""Drives the booking page routes, members' and public, against the
integration database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_booking_page_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import hashlib
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
from crm_app.models import Appointment, Booking
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

_CONTACTS = """
SELECT c.id, c.first_name, c.last_name, c.email, c.phone, c.source, c.lifecycle_stage,
       c.owner_user_id, c.version
  FROM crm_app.contact c
 WHERE c.tenant_id = :tenant AND c.email = :email
"""
_COUNTS = """
SELECT (SELECT count(*) FROM crm_app.booking WHERE tenant_id = :tenant),
       (SELECT count(*) FROM crm_app.appointment WHERE tenant_id = :tenant),
       (SELECT count(*) FROM crm_app.contact WHERE tenant_id = :tenant)
"""


def _contacts(workspace: uuid.UUID, email: str) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        rows = session.execute(text(_CONTACTS), {"tenant": workspace, "email": email})
        return [dict(row._mapping) for row in rows]


def _counts(workspace: uuid.UUID) -> list[int]:
    with tenant_session_scope(workspace) as session:
        return list(session.execute(text(_COUNTS), {"tenant": workspace}).one())


def _past_booking(workspace: uuid.UUID, host: uuid.UUID) -> str:
    """A booking whose appointment has started: its token, made up here."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    appointment_id = uuid.uuid4()
    with tenant_session_scope(workspace) as session:
        session.add(
            Appointment(
                id=appointment_id,
                tenant_id=workspace,
                title="Earlier call",
                starts_at=now - timedelta(minutes=10),
                ends_at=now + timedelta(minutes=20),
                kind="video",
                status="confirmed",
                host_user_id=host,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
        session.flush()
        session.add(
            Booking(
                id=uuid.uuid4(),
                tenant_id=workspace,
                appointment_id=appointment_id,
                outcome="created",
                token_hash=hashlib.sha256(token.encode("ascii")).hexdigest(),
                created_at=now,
            )
        )
    return token


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("booking_page_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("booking-a")
    b = _new_workspace("booking-b")
    admin_id, admin = _member(a, Role.ADMIN)
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    def key(value: str) -> dict[str, str]:
        return {"Idempotency-Key": value}

    # The day after tomorrow, in UTC, which is the workspace's time zone here.
    day = datetime.combine(datetime.now(UTC).date() + timedelta(days=2), time(), tzinfo=UTC)

    def at(hour: int, minute: int = 0) -> str:
        return (day + timedelta(hours=hour, minutes=minute)).isoformat()

    base = f"/v1/workspaces/{a.id}/booking-pages"
    result: dict[str, Any] = {
        "workspace": str(a.id),
        "owner_id": str(a.owner_id),
        "admin_id": str(admin_id),
    }
    with TestClient(create_app(), follow_redirects=False) as client:
        # --- Who may do what ------------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["create"] = {
            caller: client.post(
                base, json={"name": f"By {caller}"}, headers=auth(caller)
            ).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }

        # --- Create and its refusals -----------------------------------------------------
        body = {
            "name": "  Intro call ",
            "description": "Thirty minutes\r\nto get to know you.",
            "location": "https://meet.example.test/intro",
            "notice_minutes": 0,
        }
        made = client.post(base, json=body, headers={**auth("admin"), **key("page-1")})
        page = made.json()
        result["created"] = [made.status_code, made.headers.get("etag"), page]
        again = client.post(base, json=body, headers={**auth("admin"), **key("page-1")})
        result["create_replay"] = [
            again.status_code,
            again.headers.get("idempotent-replayed"),
            again.json()["id"] == page["id"],
        ]
        result["refusals"] = {
            label: client.post(base, json=refused, headers=auth("owner")).json()["detail"]
            for label, refused in (
                ("blank_name", {"name": " "}),
                ("length", {"name": "P", "length_minutes": 20}),
                ("step", {"name": "P", "step_minutes": 5}),
                ("notice", {"name": "P", "notice_minutes": 99999}),
                ("horizon", {"name": "P", "horizon_days": 0}),
                ("description", {"name": "P", "description": "tab\there"}),
                ("foreign_host", {"name": "P", "host_user_id": str(b.owner_id)}),
            )
        }
        result["invalid"] = {
            label: client.post(base, json=refused, headers=auth("owner")).status_code
            for label, refused in (
                ("unknown_kind", {"name": "P", "kind": "pigeon"}),
                ("extra", {"name": "P", "status": "published"}),
            )
        }

        # --- Publish ---------------------------------------------------------------------
        item = f"{base}/{page['id']}"
        public = f"/v1/public/booking-pages/{a.id}/{page['public_key']}"
        result["draft_public"] = client.get(public).status_code
        result["publish_guards"] = {
            "no_if_match": client.patch(
                item, json={"status": "published"}, headers=auth("owner")
            ).status_code,
            "member": client.patch(
                item, json={"status": "published"}, headers=auth("member", 1)
            ).status_code,
            "stale": client.patch(
                item, json={"status": "published"}, headers=auth("owner", 9)
            ).status_code,
            "no_hours": client.patch(
                item, json={"status": "published"}, headers=auth("owner", 1)
            ).json()["detail"],
        }
        settings = f"/v1/workspaces/{a.id}/settings"
        version = client.get(settings, headers=auth("owner")).json()["version"]
        client.patch(
            settings,
            json={
                "time_zone": "UTC",
                "business_hours": [{"opens": "09:00", "closes": "17:00"}] * 7,
            },
            headers=auth("owner", version),
        )
        published = client.patch(item, json={"status": "published"}, headers=auth("owner", 1))
        result["published"] = [published.status_code, published.json()["status"]]

        # --- The public page and its free times --------------------------------------------
        shown = client.get(public)
        result["public"] = [shown.status_code, shown.json()]
        result["public_not_found"] = {
            "unknown_key": client.get(f"/v1/public/booking-pages/{a.id}/{'x' * 22}").status_code,
            "malformed_key": client.get(f"/v1/public/booking-pages/{a.id}/short").status_code,
            "other_workspace": client.get(
                f"/v1/public/booking-pages/{b.id}/{page['public_key']}"
            ).status_code,
            "unknown_workspace": client.get(
                f"/v1/public/booking-pages/{uuid.uuid4()}/{page['public_key']}"
            ).status_code,
        }

        def times() -> list[str]:
            answer = client.get(f"{public}/times", params={"start": at(0), "end": at(24)})
            return answer.json()["times"]

        result["times_first"] = times()
        result["times_invalid"] = {
            "too_long": client.get(
                f"{public}/times", params={"start": at(0), "end": at(24 * 15)}
            ).status_code,
            "backwards": client.get(
                f"{public}/times", params={"start": at(10), "end": at(9)}
            ).status_code,
            "naive": client.get(
                f"{public}/times", params={"start": "2026-11-01T00:00:00", "end": at(9)}
            ).status_code,
        }
        # The host's own appointment, booked by a member, hides 10:00 and 10:30.
        client.post(
            f"/v1/workspaces/{a.id}/appointments",
            json={
                "title": "Team sync",
                "starts_at": at(10),
                "ends_at": at(10, 45),
                "host_user_id": str(admin_id),
            },
            headers=auth("owner"),
        )
        result["times_busy"] = times()

        # --- Booking -----------------------------------------------------------------------
        visitor = {
            "starts_at": at(9),
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "Ada@Example.TEST",
            "phone": "+31 20 555 0100",
            "message": "About the engine.",
        }
        result["book_guards"] = {
            "no_key": client.post(public, json=visitor).status_code,
            "not_json": client.post(
                public,
                content=b"{",
                headers={**key("bad-json"), "Content-Type": "application/json"},
            ).status_code,
            "too_large": client.post(
                public, json={**visitor, "message": "x" * 9000}, headers=key("too-large")
            ).status_code,
            "naive": client.post(
                public, json={**visitor, "starts_at": "2026-11-01T09:00:00"}, headers=key("naive")
            ).status_code,
        }
        refused = client.post(
            public,
            json={**visitor, "first_name": " ", "email": "secret-not-an-email"},
            headers=key("refused-1"),
        )
        result["refused"] = [
            refused.status_code,
            refused.json(),
            "secret-not-an-email" in refused.text,
        ]
        before = _counts(a.id)
        first = client.post(public, json=visitor, headers=key("visit-1"))
        token = first.json()["token"]
        result["first"] = [first.status_code, first.json()["booking"], len(token or "")]
        replay = client.post(public, json=visitor, headers=key("visit-1"))
        reused = client.post(public, json={**visitor, "starts_at": at(11)}, headers=key("visit-1"))
        result["replay"] = [
            replay.status_code,
            replay.json()["token"],
            replay.json()["booking"] == first.json()["booking"],
            reused.status_code,
        ]
        result["after_first"] = [before, _counts(a.id)]
        result["contact_after_first"] = _contacts(a.id, "ada@example.test")
        result["taken"] = {
            label: client.post(
                public, json={**visitor, "email": "else@example.test", **change}, headers=key(label)
            ).json()["detail"]
            for label, change in (
                ("same_time", {}),
                ("off_grid", {"starts_at": at(9, 10)}),
                ("after_hours", {"starts_at": at(17)}),
                ("busy_host", {"starts_at": at(10, 30)}),
                ("beyond_horizon", {"starts_at": at(24 * 40 + 9)}),
            )
        }
        result["times_after_booking"] = times()
        # The same person again with another name: matched, never changed.
        second = client.post(
            public,
            json={**visitor, "starts_at": at(11), "first_name": "Augusta"},
            headers=key("visit-2"),
        )
        result["second"] = second.status_code
        result["contact_after_second"] = _contacts(a.id, "ada@example.test")
        third = client.post(
            public, json={**visitor, "starts_at": at(11, 30)}, headers=key("visit-3")
        )
        fourth = client.post(public, json={**visitor, "starts_at": at(12)}, headers=key("visit-4"))
        result["limit"] = [third.status_code, fourth.status_code, fourth.json()["detail"]]
        bot = client.post(
            public,
            json={**visitor, "starts_at": at(14), "email": "bot@example.test", "website": "x"},
            headers=key("bot-1"),
        )
        counted = _counts(a.id)
        result["honeypot"] = [bot.status_code, bot.json()["detail"], counted]

        # --- What members see -------------------------------------------------------------
        listed = client.get(
            f"/v1/workspaces/{a.id}/appointments",
            params={"start": at(0), "end": at(24)},
            headers=auth("reader"),
        ).json()["items"]
        result["members_see"] = [
            {
                name: item[name]
                for name in ("title", "status", "host_user_id", "kind", "location", "note")
            }
            | {"booking": item["booking"], "contact": item["contact"]}
            for item in listed
        ]

        # --- The visitor's link -------------------------------------------------------------
        bookings = f"/v1/public/bookings/{a.id}"
        result["view"] = client.post(f"{bookings}/view", json={"token": token}).json()
        result["view_not_found"] = {
            "unknown": client.post(
                f"{bookings}/view", json={"token": secrets.token_urlsafe(32)}
            ).status_code,
            "malformed": client.post(f"{bookings}/view", json={"token": "short"}).status_code,
            "other_workspace": client.post(
                f"/v1/public/bookings/{b.id}/view", json={"token": token}
            ).status_code,
            "too_long": client.post(f"{bookings}/view", json={"token": "x" * 65}).status_code,
        }
        cancelled = client.post(f"{bookings}/cancel", json={"token": token})
        result["cancelled"] = [cancelled.status_code, cancelled.json()]
        result["cancelled_again"] = client.post(f"{bookings}/cancel", json={"token": token}).json()
        result["times_after_cancel"] = times()
        after = client.get(
            f"/v1/workspaces/{a.id}/appointments",
            params={"start": at(9), "end": at(9, 30), "include_cancelled": "true"},
            headers=auth("owner"),
        ).json()["items"]
        result["members_after_cancel"] = [
            {
                name: item[name]
                for name in ("status", "cancelled_by_user_id", "booking", "updated_by_user_id")
            }
            for item in after
            if item["status"] == "cancelled"
        ]
        result["cancelled_appointment_id"] = next(
            item["id"] for item in after if item["status"] == "cancelled"
        )
        past = _past_booking(a.id, admin_id)
        result["started"] = [
            client.post(f"{bookings}/view", json={"token": past}).json()["can_cancel"],
            client.post(f"{bookings}/cancel", json={"token": past}).status_code,
        ]

        # --- Another workspace ----------------------------------------------------------------
        theirs = client.post(
            f"/v1/workspaces/{b.id}/booking-pages",
            json={"name": "Secret page"},
            headers=auth("other_owner"),
        ).json()
        foreign = f"{base}/{theirs['id']}"
        result["foreign"] = {
            "get": client.get(foreign, headers=auth("owner")).status_code,
            "patch": client.patch(
                foreign, json={"name": "Mine"}, headers=auth("owner", 1)
            ).status_code,
            "delete": client.delete(foreign, headers=auth("owner")).status_code,
            "listed": "Secret page" in client.get(base, headers=auth("owner")).text,
            "a_from_b": client.get(
                f"/v1/workspaces/{b.id}/booking-pages/{page['id']}", headers=auth("other_owner")
            ).status_code,
        }

        # --- Unpublish and delete -------------------------------------------------------------
        page_after = client.get(item, headers=auth("owner")).json()
        result["page_after"] = page_after
        client.patch(item, json={"status": "draft"}, headers=auth("owner", page_after["version"]))
        result["unpublished"] = [
            client.get(public).status_code,
            client.get(f"{public}/times", params={"start": at(0), "end": at(24)}).status_code,
            client.post(
                public, json={**visitor, "starts_at": at(15)}, headers=key("visit-5")
            ).status_code,
        ]
        result["delete"] = {
            "member": client.delete(item, headers=auth("member")).status_code,
            "admin": client.delete(item, headers=auth("admin")).status_code,
            "again": client.delete(item, headers=auth("admin")).status_code,
        }
        result["after_delete"] = _counts(a.id)
        result["view_after_delete"] = client.post(f"{bookings}/view", json={"token": token}).json()
        result["page_id"] = page["id"]
        result["contact_id"] = str(result["contact_after_first"][0]["id"])

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
