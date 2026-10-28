"""Drives the appointment routes against the integration database and prints
one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_appointment_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.task_route_probe import _archive
from tests.integration.workspace_route_probe import _new_workspace

CALLERS = ("owner", "admin", "member", "reader", "other_owner")


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("appointment_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("appointments-a")
    b = _new_workspace("appointments-b")
    member_id, member = _member(a, Role.MEMBER)
    _, admin = _member(a, Role.ADMIN)
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

    base = f"/v1/workspaces/{a.id}/appointments"
    now = datetime.now(UTC)
    day = (now + timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)

    def at(hour: int, minute: int = 0) -> str:
        return _iso(day + timedelta(hours=hour, minutes=minute))

    def booking(start: str, end: str, **extra: Any) -> dict[str, Any]:
        return {
            "title": "Call",
            "starts_at": start,
            "ends_at": end,
            "host_user_id": str(a.owner_id),
            **extra,
        }

    window = {"start": _iso(day), "end": _iso(day + timedelta(days=1))}
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        contact = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Sam", "last_name": "Jansen", "email": "sam@example.test"},
            headers=auth("owner"),
        ).json()
        old = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Old", "email": "old@example.test"},
            headers=auth("owner"),
        ).json()
        _archive(a.id, old["id"])
        foreign_contact = client.post(
            f"/v1/workspaces/{b.id}/contacts",
            json={"first_name": "Bo", "email": "bo@example.test"},
            headers=auth("other_owner"),
        ).json()

        # --- Who may do what ----------------------------------------------------------
        result["read"] = {
            caller: client.get(base, params=window, headers=auth(caller)).status_code
            for caller in CALLERS
        }
        result["create"] = {
            caller: client.post(
                base,
                json=booking(at(13 + i), at(13 + i, 30), title=f"By {caller}"),
                headers=auth(caller),
            ).status_code
            for i, caller in enumerate(CALLERS)
        }

        # --- Create --------------------------------------------------------------------
        full = client.post(
            base,
            json={
                "title": "  Intro call with Sam ",
                "starts_at": at(9),
                "ends_at": at(9, 30),
                "kind": "video",
                "location": " https://meet.example.test/sam ",
                "note": "Bring the quote\r\nand the plan",
                "status": "pending",
                "host_user_id": str(member_id),
                "contact_id": contact["id"],
            },
            headers=auth("member"),
        )
        appointment = full.json()
        result["created"] = [full.status_code, full.headers.get("etag"), appointment]
        result["references"] = {
            label: client.post(
                base, json=booking(at(20), at(20, 30), **body), headers=auth("owner")
            ).json()["detail"]
            for label, body in (
                ("foreign_contact", {"contact_id": foreign_contact["id"]}),
                ("archived_contact", {"contact_id": old["id"]}),
                ("unknown_contact", {"contact_id": str(uuid.uuid4())}),
                ("foreign_host", {"host_user_id": str(b.owner_id)}),
            )
        }
        result["invalid"] = {
            label: client.post(base, json=body, headers=auth("owner")).status_code
            for label, body in (
                (
                    "missing_title",
                    {k: v for k, v in booking(at(20), at(21)).items() if k != "title"},
                ),
                (
                    "missing_host",
                    {k: v for k, v in booking(at(20), at(21)).items() if k != "host_user_id"},
                ),
                ("naive_start", booking("2026-12-01T10:00:00", at(21))),
                ("ends_before_start", booking(at(21), at(20))),
                ("too_short", booking(at(20), at(20, 4))),
                ("longer_than_a_day", booking(at(1), _iso(day + timedelta(hours=26)))),
                ("bad_kind", booking(at(20), at(21), kind="pigeon")),
                ("cancelled_on_create", booking(at(20), at(21), status="cancelled")),
                ("string_allow", booking(at(20), at(21), allow_conflict="yes")),
                ("unknown_field", booking(at(20), at(21), reminder=True)),
                ("long_location", booking(at(20), at(21), location="x" * 301)),
            )
        }
        result["invalid_times_code"] = client.post(
            base, json=booking(at(21), at(20)), headers=auth("owner")
        ).json()["detail"]

        # --- Conflicts -----------------------------------------------------------------
        overlap = client.post(
            base,
            json=booking(at(9, 15), at(10), host_user_id=str(member_id)),
            headers=auth("owner"),
        )
        result["conflict"] = [overlap.status_code, overlap.json()["detail"]]
        result["back_to_back"] = client.post(
            base,
            json=booking(at(9, 30), at(10), host_user_id=str(member_id), title="Next"),
            headers=auth("owner"),
        ).status_code
        result["other_host"] = client.post(
            base, json=booking(at(9), at(9, 30), title="Owner's own"), headers=auth("owner")
        ).status_code
        forced = client.post(
            base,
            json=booking(
                at(9, 15),
                at(9, 45),
                host_user_id=str(member_id),
                title="Forced",
                allow_conflict=True,
            ),
            headers=auth("owner"),
        )
        result["forced"] = forced.status_code
        check = f"{base}/conflicts"
        result["check"] = {
            "busy": [
                c["title"]
                for c in client.get(
                    check,
                    params={
                        "host_user_id": str(member_id),
                        "starts_at": at(9),
                        "ends_at": at(9, 20),
                    },
                    headers=auth("reader"),
                ).json()["conflicts"]
            ],
            "excluded": [
                c["title"]
                for c in client.get(
                    check,
                    params={
                        "host_user_id": str(member_id),
                        "starts_at": at(9),
                        "ends_at": at(9, 20),
                        "exclude_id": forced.json()["id"],
                    },
                    headers=auth("reader"),
                ).json()["conflicts"]
            ],
            "free": client.get(
                check,
                params={"host_user_id": str(member_id), "starts_at": at(11), "ends_at": at(12)},
                headers=auth("reader"),
            ).json()["conflicts"],
            "bad_times": client.get(
                check,
                params={"host_user_id": str(member_id), "starts_at": at(12), "ends_at": at(11)},
                headers=auth("reader"),
            ).status_code,
        }
        client.delete(f"{base}/{forced.json()['id']}", headers=auth("owner"))

        key = {"Idempotency-Key": "appointment-create-0001"}
        once = booking(at(22), at(22, 30), title="Once")
        first = client.post(base, json=once, headers={**auth("owner"), **key})
        again = client.post(base, json=once, headers={**auth("owner"), **key})
        result["idempotent"] = [
            first.status_code,
            again.headers.get("idempotent-replayed"),
            first.json()["id"] == again.json()["id"],
        ]

        # --- Update, status, cancel ---------------------------------------------------
        item = f"{base}/{appointment['id']}"
        result["no_version"] = client.patch(
            item, json={"title": "X"}, headers=auth("member")
        ).status_code
        stale = client.patch(item, json={"title": "X"}, headers=auth("member", 9))
        result["stale"] = [stale.status_code, stale.json()["detail"]]
        result["reader_update"] = client.patch(
            item, json={"status": "confirmed"}, headers=auth("reader", 1)
        ).status_code
        into_conflict = client.patch(
            item, json={"starts_at": at(9, 30), "ends_at": at(10)}, headers=auth("member", 1)
        )
        result["reschedule_conflict"] = [
            into_conflict.status_code,
            [c["title"] for c in into_conflict.json()["detail"]["conflicts"]],
        ]
        moved = client.patch(
            item, json={"starts_at": at(10), "ends_at": at(10, 45)}, headers=auth("member", 1)
        ).json()
        confirmed = client.patch(
            item, json={"status": "confirmed"}, headers=auth("member", 2)
        ).json()
        unchanged = client.patch(
            item, json={"status": "confirmed", "kind": "video"}, headers=auth("member", 3)
        ).json()
        result["update_invalid"] = {
            label: client.patch(item, json=body, headers=auth("owner", 3)).status_code
            for label, body in (
                ("null_title", {"title": None}),
                ("null_start", {"starts_at": None}),
                ("null_host", {"host_user_id": None}),
                ("null_status", {"status": None}),
                ("ends_before_start", {"ends_at": at(9)}),
                ("foreign_host", {"host_user_id": str(b.owner_id)}),
            )
        }
        cleared = client.patch(
            item,
            json={"location": None, "note": "  ", "contact_id": None},
            headers=auth("owner", 3),
        ).json()
        cancelled = client.patch(item, json={"status": "cancelled"}, headers=auth("member", 4))
        after_cancel = client.patch(item, json={"status": "confirmed"}, headers=auth("member", 5))
        result["lifecycle"] = {
            "moved": [moved["starts_at"], moved["ends_at"], moved["version"]],
            "confirmed": [confirmed["status"], confirmed["version"]],
            "unchanged_version": unchanged["version"],
            "cleared": [
                cleared["location"],
                cleared["note"],
                cleared["contact"],
                cleared["version"],
            ],
            "cancelled": [
                cancelled.status_code,
                cancelled.json()["status"],
                cancelled.json()["cancelled_at"] is not None,
                cancelled.json()["cancelled_by_user_id"] == str(member_id),
            ],
            "after_cancel": [after_cancel.status_code, after_cancel.json()["detail"]],
            # The cancelled slot is free again.
            "rebooked": client.post(
                base,
                json=booking(at(10), at(10, 45), host_user_id=str(member_id), title="Rebooked"),
                headers=auth("owner"),
            ).status_code,
        }

        # --- Range, filters, upcoming ----------------------------------------------------
        def titles(**params: Any) -> list[str]:
            response = client.get(base, params={**window, **params}, headers=auth("owner"))
            return [x["title"] for x in response.json()["items"]]

        past = client.post(
            base,
            json=booking(
                _iso(now - timedelta(hours=3)),
                _iso(now - timedelta(hours=2)),
                title="Earlier today",
                contact_id=contact["id"],
            ),
            headers=auth("owner"),
        ).json()
        soon = client.post(
            base,
            json=booking(at(8), at(8, 30), title="Sam follow-up", contact_id=contact["id"]),
            headers=auth("owner"),
        ).json()
        result["range"] = {
            "day": titles(),
            "with_cancelled": "Intro call with Sam" in titles(include_cancelled="true"),
            "member_hosted": titles(host=str(member_id)),
            "mine": titles(host="me")[:2],
            "contact": titles(contact_id=contact["id"]),
            "too_wide": client.get(
                base,
                params={"start": _iso(day), "end": _iso(day + timedelta(days=43))},
                headers=auth("owner"),
            ).status_code,
            "backwards": client.get(
                base, params={"start": window["end"], "end": window["start"]}, headers=auth("owner")
            ).status_code,
            "naive": client.get(
                base,
                params={"start": "2026-10-28T00:00:00", "end": "2026-10-29T00:00:00"},
                headers=auth("owner"),
            ).status_code,
            "missing": client.get(base, headers=auth("owner")).status_code,
        }
        result["upcoming"] = [
            x["id"]
            for x in client.get(
                f"{base}/upcoming", params={"contact_id": contact["id"]}, headers=auth("reader")
            ).json()["items"]
        ]
        result["upcoming_expected"] = [soon["id"]]
        result["past_id"] = past["id"]

        # --- Another workspace -----------------------------------------------------------
        theirs = client.post(
            f"/v1/workspaces/{b.id}/appointments",
            json={
                "title": "Secret",
                "starts_at": at(9),
                "ends_at": at(10),
                "host_user_id": str(b.owner_id),
            },
            headers=auth("other_owner"),
        ).json()
        mine_path = f"{base}/{theirs['id']}"
        result["foreign"] = {
            "get": client.get(mine_path, headers=auth("owner")).json(),
            "patch": client.patch(
                mine_path, json={"status": "completed"}, headers=auth("owner", 1)
            ).status_code,
            "delete": client.delete(mine_path, headers=auth("owner")).status_code,
            "listed": "Secret"
            in client.get(
                base, params={**window, "include_cancelled": "true"}, headers=auth("owner")
            ).text,
            "conflict_check": client.get(
                check,
                params={"host_user_id": str(b.owner_id), "starts_at": at(9), "ends_at": at(10)},
                headers=auth("owner"),
            ).json()["conflicts"],
        }

        # --- Delete (Owner and Admin, P5-A 6) ----------------------------------------
        result["delete"] = {
            "reader": client.delete(item, headers=auth("reader")).status_code,
            "member": client.delete(item, headers=auth("member")).status_code,
            "admin": client.delete(item, headers=auth("admin")).status_code,
            "again": client.delete(item, headers=auth("admin")).status_code,
        }
        result["appointment_id"] = appointment["id"]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
