"""The automation trigger on a contact's date (decision P8-I).

Drives `automation_date_trigger_probe` in a fresh interpreter: a trigger
without an hour, or with days out of range, is refused when saved; a key
that is not an active contact date field is refused at activation;
activating registers the workspace for the maintenance run, which starts
the automation, once, for every unarchived contact whose date moved by the
days is today in the workspace's zone, once the hour has come, and never
for another workspace's contacts; with nothing active the workspace's row
goes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
GONE = "the date field its trigger reads is not an active contact date field"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automation_date_trigger")
    result = run_module(
        "tests.integration.automation_date_trigger_probe", [], env, tmp, timeout=600
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_date_trigger_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422]
    assert probe["refused_activate"] == [[422, GONE], [422, GONE]]
    assert probe["registered_before"] == 0


def test_the_maintenance_run_starts_it_on_the_day_once_the_hour_has_come(probe: Probe) -> None:
    assert probe["stored"] == {
        "type": "date_reached",
        "field_key": "renewal",
        "offset_days": -7,
        "hour": 9,
    }
    assert probe["activated"] == [200, 200]
    assert probe["registered"] == 1
    assert probe["first"]["started"] >= 1
    assert probe["after_first"] == {"Week before": ["Ann"]}
    assert probe["too_soon"]["workspaces"] == 0
    assert probe["after_second"] == {"On the day": ["Fay"], "Week before": ["Ann"]}
    assert probe["other_workspace"] == {}


def test_the_runs_do_their_steps_and_a_workspace_without_one_is_dropped(probe: Probe) -> None:
    assert probe["statuses"] == ["completed"]
    assert probe["tagged"] == ["Ann", "Fay"]
    assert probe["registered_after"] == 0
