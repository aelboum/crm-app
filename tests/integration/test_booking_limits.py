"""Public booking limits and link expiry (decision 13-H2; 13-H1 findings).

Drives `booking_limits_probe` in a fresh interpreter with small limits: a
visitor's own booking budget per page, which never holds back another
visitor; the workspace's daily capacity, also when two visitors race for
the last place; a visitor's own budget for link lookups, which slows token
guessing; links that expire a week after their appointment ends; two
cancellations at once; and another workspace never answering for a token.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
        "BOOKING_REQUESTS_PER_VISITOR_PER_HOUR": "3",
        "BOOKING_LOOKUPS_PER_VISITOR_PER_HOUR": "4",
        "BOOKINGS_PER_WORKSPACE_PER_24H": "5",
    }
    tmp = tmp_path_factory.mktemp("booking-limits")
    result = run_module("tests.integration.booking_limits_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_each_visitor_has_their_own_budget_per_page(probe: Probe) -> None:
    assert probe["alice"] == [201, 201, 201, 429]
    assert probe["alice_refusal"] is True  # with Retry-After
    # A page-wide budget would have refused Bob too.
    assert probe["bob"] == [201, 201]


def test_a_workspace_takes_a_bounded_number_of_bookings_a_day(probe: Probe) -> None:
    status, detail, bookings = probe["capacity"]
    assert (status, detail) == (429, {"code": "booking_capacity"})
    assert bookings == 5  # the refusal stored nothing


def test_two_visitors_racing_for_the_last_place_get_one_booking(probe: Probe) -> None:
    assert probe["race"] == [[201, 429], 1]


def test_guessing_tokens_is_cut_off_per_visitor(probe: Probe) -> None:
    # Four wrong guesses, then even a real token is refused for that visitor.
    assert probe["guessing"] == [404, 404, 404, 404, 429, 429]
    assert probe["owner_view"] == 200
    assert probe["other_workspace"] == 404


def test_a_link_expires_a_week_after_its_appointment_ends(probe: Probe) -> None:
    assert probe["recent"] == [200, {"code": "booking_not_cancellable"}]
    assert probe["expired"] == [404, 404]


def test_two_cancellations_at_once_cancel_once(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    statuses, views, cancelled = probe["double_cancel"]
    assert statuses == [200, 200]
    assert views == [True, True]
    assert cancelled == 1
    rows = owner_connection.execute(
        "SELECT action FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.appointment' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["cancelled_appointment"]),
    ).fetchall()
    assert [action for (action,) in rows] == [
        "crm_app.appointment.created",
        "crm_app.appointment.cancelled",
    ]
