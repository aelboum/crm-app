"""Booking confirmation emails (decision P6-E2).

Drives `booking_email_probe` in a fresh interpreter with sending off: a
booking on a page with confirmations on queues one email to the visitor,
in the workspace's time zone, acting as the host, never with the private
link; a replay queues nothing more; a page with confirmations off and the
honeypot queue nothing; the setting accepts only true or false.
"""

from __future__ import annotations

import json
from typing import Any

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
        "BOOKING_REQUESTS_PER_VISITOR_PER_HOUR": "1000",
    }
    env.pop("EMAIL_SENDING_ENABLED", None)
    tmp = tmp_path_factory.mktemp("booking-emails")
    result = run_module("tests.integration.booking_email_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_booking_queues_one_confirmation_to_the_visitor(probe: Probe) -> None:
    assert probe["default_flag"] is True
    emails = probe["after_bookings"]
    assert len(emails) == 2  # two bookings; the replay added none
    email = emails[0]
    assert email["purpose"] == "booking_confirmation"
    assert email["to_email"] == "ada@example.test"
    assert email["status"] == "queued"  # sending is off
    assert email["contact_id"] is not None
    assert email["created_by_user_id"] == probe["owner"]  # the host
    assert email["subject"].startswith("Booked: Intro call, ")
    assert "(Europe/Amsterdam)" in email["text_body"]
    assert "Phone call" in email["text_body"]


def test_the_email_never_holds_the_private_link(probe: Probe) -> None:
    assert probe["token_in_email"] is False


def test_pages_with_confirmations_off_and_the_honeypot_queue_nothing(probe: Probe) -> None:
    assert probe["off_flag"] is False
    assert probe["after_off_and_bot"] == 2


def test_the_setting_is_true_or_false(probe: Probe) -> None:
    assert probe["patch_null"] == 422
    assert probe["patch_string"] == 422
    assert probe["patch_true"] == [200, True]
