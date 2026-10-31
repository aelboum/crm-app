"""Drives the public booking routes' limits and link expiry (decision 13-H2)
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_booking_limits.py`,
which sets small limits in the environment. Every visitor gets its own
client address, unique to this run, so limiter windows left by an earlier
run cannot leak in. Seeds throwaway workspaces with made-up records.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

_COUNTS = """
SELECT (SELECT count(*) FROM crm_app.booking WHERE tenant_id = :tenant),
       (SELECT count(*) FROM crm_app.appointment WHERE tenant_id = :tenant
           AND status = 'cancelled')
"""
_SHIFT = """
UPDATE crm_app.appointment
   SET starts_at = :starts, ends_at = :ends
 WHERE tenant_id = :tenant AND id = :id
"""
_APPOINTMENT = """
SELECT appointment_id FROM crm_app.booking WHERE tenant_id = :tenant AND token_hash = :hash
"""
_RUN = secrets.token_hex(3)


def _address(n: int) -> tuple[str, int]:
    """A client address unique to this run and visitor."""
    return (f"visitor-{_RUN}-{n}", 50000)


def _counts(workspace: uuid.UUID) -> list[int]:
    with tenant_session_scope(workspace) as session:
        return list(session.execute(text(_COUNTS), {"tenant": workspace}).one())


def _appointment(workspace: uuid.UUID, token: str) -> str:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with tenant_session_scope(workspace) as session:
        return str(
            session.execute(text(_APPOINTMENT), {"tenant": workspace, "hash": digest}).scalar_one()
        )


def _shift(workspace: uuid.UUID, token: str, ends: datetime) -> None:
    """Moves a booking's appointment so it ended at `ends` (test data only)."""
    appointment_id = _appointment(workspace, token)
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(_SHIFT),
            {
                "tenant": workspace,
                "id": appointment_id,
                "starts": ends - timedelta(minutes=30),
                "ends": ends,
            },
        )


def _published_page(app: FastAPI, workspace: Any, name: str) -> str:
    """Creates and publishes a page with hours every day; its public path."""
    auth = {"Authorization": f"Bearer {issue_session(workspace.owner_id)[1]}"}
    with TestClient(app) as client:
        base = f"/v1/workspaces/{workspace.id}"
        page = client.post(
            f"{base}/booking-pages", json={"name": name, "notice_minutes": 0}, headers=auth
        ).json()
        settings = client.get(f"{base}/settings", headers=auth).json()
        client.patch(
            f"{base}/settings",
            json={
                "time_zone": "UTC",
                "business_hours": [{"opens": "08:00", "closes": "20:00"}] * 7,
            },
            headers={**auth, "If-Match": f'"{settings["version"]}"'},
        )
        client.patch(
            f"{base}/booking-pages/{page['id']}",
            json={"status": "published"},
            headers={**auth, "If-Match": '"1"'},
        )
    return f"/v1/public/booking-pages/{workspace.id}/{page['public_key']}"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("booking_limits_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("booking-limits-a")
    b = _new_workspace("booking-limits-b")
    race = _new_workspace("booking-limits-race")
    app = create_app()
    page_a = _published_page(app, a, "Limits")
    page_race = _published_page(app, race, "Race")
    day = datetime.combine(datetime.now(UTC).date() + timedelta(days=2), time(), tzinfo=UTC)
    slots = iter(range(16 * 2))

    def next_time() -> str:
        return (day + timedelta(hours=8, minutes=30 * next(slots))).isoformat()

    def booking(n: int) -> dict[str, str]:
        return {
            "starts_at": next_time(),
            "first_name": f"Visitor{n}",
            "email": f"v{n}.{_RUN}@example.test",
        }

    def book(client: TestClient, path: str, n: int) -> Any:
        return client.post(path, json=booking(n), headers={"Idempotency-Key": f"limits-{_RUN}-{n}"})

    result: dict[str, Any] = {"workspace": str(a.id)}
    clients = [TestClient(app, client=_address(n)) for n in range(6)]
    for client in clients:
        client.__enter__()
    try:
        alice, bob, carol, guesser, dave, erin = clients
        bookings_a = f"/v1/public/bookings/{a.id}"

        # --- Each visitor has their own budget per page (limit 3 an hour) ---------------
        by_alice = [book(alice, page_a, n) for n in range(4)]
        result["alice"] = [r.status_code for r in by_alice]
        result["alice_refusal"] = by_alice[3].headers.get("retry-after") is not None
        # Another visitor is not held back by Alice's spent budget.
        by_bob = [book(bob, page_a, n) for n in (10, 11)]
        result["bob"] = [r.status_code for r in by_bob]

        # --- The workspace's daily capacity (5) ------------------------------------------
        refused = book(carol, page_a, 20)
        result["capacity"] = [refused.status_code, refused.json()["detail"], _counts(a.id)[0]]

        # --- Link lookups: a visitor's own hourly budget (4) ------------------------------
        guesses = [
            guesser.post(
                f"{bookings_a}/view", json={"token": secrets.token_urlsafe(32)}
            ).status_code
            for _ in range(4)
        ]
        token = by_alice[0].json()["token"]
        result["guessing"] = [
            *guesses,
            guesser.post(f"{bookings_a}/view", json={"token": token}).status_code,
            guesser.post(f"{bookings_a}/cancel", json={"token": token}).status_code,
        ]
        # The token's owner, from their own address, still reaches it.
        result["owner_view"] = alice.post(f"{bookings_a}/view", json={"token": token}).status_code
        # Another workspace never answers for it.
        result["other_workspace"] = dave.post(
            f"/v1/public/bookings/{b.id}/view", json={"token": token}
        ).status_code

        # --- Expiry: a week after the appointment ends ------------------------------------
        recent, expired = by_alice[1].json(), by_alice[2].json()
        now = datetime.now(UTC)
        _shift(a.id, recent["token"], now - timedelta(days=6))
        _shift(a.id, expired["token"], now - timedelta(days=8))
        result["recent"] = [
            dave.post(f"{bookings_a}/view", json={"token": recent["token"]}).status_code,
            dave.post(f"{bookings_a}/cancel", json={"token": recent["token"]}).json()["detail"],
        ]
        result["expired"] = [
            erin.post(f"{bookings_a}/view", json={"token": expired["token"]}).status_code,
            erin.post(f"{bookings_a}/cancel", json={"token": expired["token"]}).status_code,
        ]

        # --- Two cancellations at once: one change, both see it --------------------------
        bob_token = by_bob[0].json()["token"]
        before = _counts(a.id)[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(
                pool.map(
                    lambda c: c.post(f"{bookings_a}/cancel", json={"token": bob_token}),
                    (bob, erin),
                )
            )
        result["double_cancel"] = [
            sorted(r.status_code for r in answers),
            [r.json().get("cancelled") for r in answers if r.status_code == 200],
            _counts(a.id)[1] - before,
        ]
        result["cancelled_appointment"] = _appointment(a.id, bob_token)
    finally:
        for client in clients:
            client.__exit__(None, None, None)

    # --- Two visitors take the last place at once (capacity 1 in that run) ------------------
    os.environ["BOOKINGS_PER_WORKSPACE_PER_24H"] = "1"
    racers = [TestClient(app, client=_address(n)) for n in (30, 31)]
    for client in racers:
        client.__enter__()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(
                pool.map(
                    lambda pair: book(pair[0], page_race, pair[1]),
                    zip(racers, (30, 31), strict=True),
                )
            )
        result["race"] = [sorted(r.status_code for r in answers), _counts(race.id)[0]]
    finally:
        for client in racers:
            client.__exit__(None, None, None)

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
