"""The Home page's setup checklist (decision P4-S, `crm_app.setup_steps`).

Drives `setup_probe` in a fresh interpreter: a new workspace has done
nothing; a contact, a deal, business hours and a second member tick their
steps and no others; another workspace is unaffected; every member reads
it and nobody else does.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
STEPS = ["business_hours", "contact", "deal", "form", "booking_page", "automation", "teammate"]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("setup")
    result = run_module("tests.integration.setup_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_new_workspace_has_done_nothing(probe: Probe) -> None:
    assert probe["order"] == STEPS
    assert probe["new"] == dict.fromkeys(STEPS, False)


def test_each_first_step_ticks_only_itself(probe: Probe) -> None:
    assert probe["after"] == {
        "business_hours": True,
        "contact": True,
        "deal": True,
        "form": False,
        "booking_page": False,
        "automation": False,
        "teammate": True,
    }
    assert probe["other"] == dict.fromkeys(STEPS, False)


def test_every_member_reads_it_and_nobody_else(probe: Probe) -> None:
    assert probe["access"] == {
        "reader": 200,
        "other_owner": 404,
        "outsider": 404,
        "anonymous": 401,
    }
