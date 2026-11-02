"""The queue-age health check (decision 13-O1).

Drives `health_check_probe` in a fresh interpreter: an automation run due an
hour ago is counted as overdue; one due 10 minutes before the check is not
yet late; nothing is overdue as of the year 2000; stray arguments print the
usage and exit 2.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Any:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("health_check")
    result = run_module("tests.integration.health_check_probe", [], env, tmp, timeout=300)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_overdue_work_is_counted_and_recent_work_is_not(probe: Any) -> None:
    assert probe["keys"] == ["automation_runs", "emails", "imports"]
    assert probe["detected"] == 1
    # checked 50 minutes ago, the row was due only 10 minutes before: not late
    assert probe["not_yet_late"] == 0
    assert probe["nothing_in_2000"] == {"emails": 0, "automation_runs": 0, "imports": 0}


def test_stray_arguments_print_the_usage(probe: Any) -> None:
    assert probe["usage"] == [2, True]
