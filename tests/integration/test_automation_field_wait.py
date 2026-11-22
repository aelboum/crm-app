"""The automation step that waits for a contact field's value (decision P8-J).

Drives `automation_field_wait_probe` in a fresh interpreter: a step without
days, or with days out of range, is refused when saved; a key that is not an
active contact field is refused at activation. A contact that has a value
goes on at once; one without stays on the step, looked at again every 10
minutes (a retried job early changes nothing), and goes on once the value
is filled in; filling it in wakes the run at once, another field does
not; after the days without one the step is skipped as `timed_out`, and a
field archived meanwhile skips it as `field_gone`. The run history lists
the step.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
DAYS_2 = 2 * 24 * 3600.0


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automation_field_wait")
    result = run_module("tests.integration.automation_field_wait_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _state(status: str, steps: list[list[Any]], resume: float | None = None) -> dict[str, Any]:
    waiting = status == "waiting"
    return {
        "status": status,
        "next_step": 0 if waiting else 2,
        "resume_in": resume,
        "wait_ends_in": DAYS_2 if waiting else None,
        "steps": steps,
    }


DONE = [[0, "done", None], [1, "done", None]]


def test_a_bad_field_wait_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422, 422]
    assert probe["refused_activate"] == [
        422,
        "the custom field it waits for is not an active contact field",
    ]
    assert probe["stored"] == {"type": "wait_for_field", "field_key": "seats", "max_days": 2}
    assert probe["activated"] == 200


def test_the_run_goes_on_once_the_field_has_a_value(probe: Probe) -> None:
    assert probe["ann"] == ["completed", _state("completed", DONE)]
    assert probe["bob_waiting"] == ["waiting", _state("waiting", [], 600.0)]
    # The run history shows the next look and when the wait gives up.
    assert probe["history_waiting"] == ["waiting", 600.0, DAYS_2]
    assert probe["bob_early"] == ["waiting", _state("waiting", [], 600.0)]
    assert probe["bob_still"] == ["waiting", _state("waiting", [], 1200.0)]
    assert probe["bob_found"] == ["completed", _state("completed", DONE)]


def test_filling_the_field_wakes_the_run_at_once(probe: Probe) -> None:
    # Another field's change leaves the next look where it was.
    assert probe["eve_other_field"] == _state("waiting", [], 600.0)
    # The awaited field filled in at +3 minutes: due now, and the sweeper takes it.
    assert probe["eve_woken"] == [_state("waiting", [], 180.0), True]
    assert probe["eve_done"] == ["completed", _state("completed", DONE)]


def test_the_step_is_skipped_when_the_days_run_out_or_the_field_goes(probe: Probe) -> None:
    # The last look is due when the days end, not ten minutes later.
    assert probe["cy_last_look"] == ["waiting", _state("waiting", [], DAYS_2)]
    assert probe["cy_timed_out"] == [
        "completed",
        _state("completed", [[0, "skipped", "timed_out"], [1, "done", None]]),
    ]
    assert probe["dee_gone"] == [
        "completed",
        _state("completed", [[0, "skipped", "field_gone"], [1, "done", None]]),
    ]
    assert probe["tagged"] == ["Ann", "Bob", "Cy", "Dee", "Eve"]
    assert probe["history"] == 200
    assert probe["history_actions"] == ["add_tag", "wait_for_field"]
