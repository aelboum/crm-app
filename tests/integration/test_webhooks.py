"""Customers' webhooks (decision P12-H).

Drives `webhook_probe` in a fresh interpreter: only HTTPS endpoints
without credentials in the address, added by Owners and Admins, with the
signing secret once and uncached and the query string never shown;
nothing is recorded without an endpoint; a contact created and updated, a
deal moved and a form submitted each record one delivery for the
workspace's endpoint and none for another workspace's; the data is the
agreed small set, `contact.updated` naming changed fields without their
values; the history shows status and attempts but no payload; removing
an endpoint is repeatable and it gets nothing more.
"""

from __future__ import annotations

import base64
import json
import os
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
        # SaaS-OS keeps each signing secret encrypted; a throwaway key.
        "FIELD_ENCRYPTION_ACTIVE_KEY_VERSION": "v1",
        "FIELD_ENCRYPTION_KEY_V1": base64.b64encode(os.urandom(32)).decode("ascii"),
    }
    tmp = tmp_path_factory.mktemp("webhooks")
    result = run_module("tests.integration.webhook_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_only_https_endpoints_by_owners_and_admins(probe: Probe) -> None:
    assert probe["refused"] == [422, 422, 422, 403]


def test_the_secret_is_shown_once_and_the_query_never(probe: Probe) -> None:
    assert probe["added"] == [201, "no-store", "https://hooks.example.org/in", True]


def test_nothing_is_recorded_without_an_endpoint(probe: Probe) -> None:
    assert probe["before_any"] == [201, 0]


def test_each_change_records_one_delivery_for_this_workspace_only(probe: Probe) -> None:
    assert probe["changes"] == [201, 200, 201]
    # Events of one transaction share its timestamp, so they are compared
    # without their order.
    assert sorted(probe["events"]) == sorted(
        [
            "contact.created",
            "contact.updated",
            "deal.stage_changed",
            # The submission created its contact, then was recorded.
            "contact.created",
            "form.submitted",
        ]
    )
    assert probe["one_endpoint"] is True
    assert probe["other_workspace"] == []


def test_the_data_is_the_agreed_small_set(probe: Probe) -> None:
    ids = probe["ids"]
    assert probe["contact_created"] == {
        "id": ids["contact"],
        "first_name": "Ada",
        "last_name": "Lee",
        "email": "ada.hooks@example.org",
        "lifecycle_stage": "lead",
        "source": "manual",
    }
    updated = probe["contact_updated"]
    assert updated["changed"] == ["city", "job_title"]
    assert "Utrecht" not in json.dumps(updated)
    assert "phone" not in updated
    assert probe["deal"] == {
        "id": ids["deal"],
        "pipeline_id": ids["pipeline"],
        "stage_id": ids["stage"],
        "contact_id": ids["contact"],
    }
    assert set(probe["form"]) == {"id", "form_id", "contact_id"}
    assert probe["form"]["form_id"] == ids["form"]


def test_history_shows_deliveries_without_payloads(probe: Probe) -> None:
    count, statuses, leaked, events = probe["history"]
    assert count == 5
    assert statuses == ["pending"]
    assert leaked is False
    assert events == [
        "contact.created",
        "contact.updated",
        "deal.stage_changed",
        "form.submitted",
        "appointment.booked",
    ]


def test_a_removed_endpoint_gets_nothing_more(probe: Probe) -> None:
    # Removing is repeatable (SaaS-OS's unsubscribe).
    assert probe["removed"] == [204, 204]
    assert probe["after_removal"] == 0
