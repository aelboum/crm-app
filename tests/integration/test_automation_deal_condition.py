"""Automation conditions on a contact's deals (decision P8-H).

Drives `automation_deal_condition_probe` in a fresh interpreter: an unknown
outcome or operator is refused when saved; a stage that does not exist, or
belongs to another workspace, is refused at activation; a `deal` condition
takes the yes branch when the contact has a deal with one of the outcomes,
and a `deal_stage` condition when it has an open deal in one of the stages
(a won deal in that stage does not count).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
GONE = "a stage its condition names no longer exists"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automation_deal_condition")
    result = run_module(
        "tests.integration.automation_deal_condition_probe", [], env, tmp, timeout=600
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_deal_condition_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422]
    assert probe["refused_activate"] == [[422, GONE], [422, GONE]]


def test_a_run_takes_the_branch_the_contacts_deals_pick(probe: Probe) -> None:
    assert probe["activated"] == [200, 200]
    assert probe["stored"] == [
        {"field": "deal", "op": "has", "values": ["won"]},
        {"field": "deal_stage", "op": "has", "values": [probe["first_stage"]]},
    ]
    assert probe["branches"] == {
        "Ann": {"Has won": "no", "Open in first": "yes"},
        "Bob": {"Has won": "yes", "Open in first": "no"},
        "Cy": {"Has won": "no", "Open in first": "no"},
    }
