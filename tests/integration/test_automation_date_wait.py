"""The automation step that waits until a contact's date (decision P8-D).

Drives `automation_date_wait_probe` in a fresh interpreter: a step without
an hour, or with days out of range, is refused when saved; a key that is
not an active contact date field is refused at activation; a contact's
future date makes the run wait until that day moved by the days, at the
hour in the workspace's zone; a past date or no date skips the step; a
date changed after the wait began does not move it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
GONE = "the date field it waits for is not an active contact date field"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automation_date_wait")
    result = run_module("tests.integration.automation_date_wait_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_date_wait_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422]
    assert probe["refused_activate"] == [[422, GONE], [422, GONE]]
    assert probe["activated"] == 200
    assert probe["stored"] == {
        "type": "wait_until_date",
        "field_key": "renewal",
        "offset_days": -3,
        "hour": 9,
    }


def test_a_run_waits_for_the_contacts_date_or_skips_without_one(probe: Probe) -> None:
    runs = probe["runs"]
    assert runs["Ann"] == {
        "status": "waiting",
        "steps": [[0, "wait_until_date", "done", None]],
        "resume_at": probe["expected_resume"],
    }
    assert runs["Bob"]["status"] == "completed"
    assert runs["Bob"]["steps"] == [
        [0, "wait_until_date", "skipped", "date_passed"],
        [1, "add_tag", "done", None],
    ]
    assert runs["Cy"]["steps"][0] == [0, "wait_until_date", "skipped", "no_date"]
    assert probe["runs_listed"] == 200


def test_a_wait_keeps_its_time_and_then_goes_on(probe: Probe) -> None:
    assert probe["still_waiting"] == "waiting"
    assert probe["resumed"] == "completed"
    assert probe["resumed_steps"] == [
        [0, "wait_until_date", "done", None],
        [1, "add_tag", "done", None],
    ]
