"""The automation step that waits for business hours (decision P8-W): it is
skipped while no hours are set, waits for the next opening outside them
(a retried job changes nothing), and goes straight on inside them.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Any:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    result = run_module(
        "tests.integration.business_hours_wait_probe",
        [],
        env,
        tmp_path_factory.mktemp("bh"),
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_without_business_hours_the_step_is_skipped(probe: Any) -> None:
    assert probe["no_hours"] == {
        "status": "completed",
        "resume_at": None,
        "steps": [[0, "skipped", "no_hours"], [1, "done", None]],
    }


def test_before_opening_the_run_waits_for_it(probe: Any) -> None:
    assert probe["early"] == {
        "status": "waiting",
        "resume_at": "2026-11-09T09:00:00+00:00",
        "steps": [[0, "done", None]],
    }
    assert probe["at_opening"]["status"] == "completed"
    assert probe["at_opening"]["steps"] == [[0, "done", None], [1, "done", None]]


def test_while_open_the_run_goes_straight_on(probe: Any) -> None:
    assert probe["midday"]["status"] == "completed"
    assert probe["midday"]["steps"] == [[0, "done", None], [1, "done", None]]


def test_the_step_takes_no_arguments(probe: Any) -> None:
    assert probe["extra_key"] == 422
