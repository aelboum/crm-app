"""Existing workspaces gain later template permissions (decision P2-G7).

Drives `role_upgrade_probe` in a fresh interpreter: a dry run changes
nothing; an upgrade grants each product role exactly what its template
gained, holds administrative permissions back unless asked, keeps grants
outside the template, and changes nothing on a re-run; a workspace not
named is untouched; a fresh workspace needs nothing; a workspace without
the product roles, an unknown id, a bad id and production without
confirmation are refused or skipped.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
READ = "crm_app.conversation:read"
REPLY = "crm_app.conversation:reply"
IMPORT = "crm_app.crm_data:import"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("role_upgrade")
    result = run_module("tests.integration.role_upgrade_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_dry_run_changes_nothing(probe: Probe) -> None:
    assert probe["before"] == [False, False]
    assert probe["dry_run"] == [0, "role upgrade: DRY RUN, nothing was changed"]
    assert probe["after_dry_run"] == [False, False]


def test_each_role_gains_only_its_template_and_administrative_waits(probe: Probe) -> None:
    roles = probe["first"]["roles"]
    assert roles["Owner"]["granted"] == [READ, REPLY]
    assert roles["Owner"]["held_back"] == [IMPORT]
    assert roles["Admin"]["held_back"] == [IMPORT]
    assert roles["Member"]["granted"] == [READ, REPLY]
    assert roles["Read-only"]["granted"] == [READ]
    # member reply, member read, owner reply, owner import, custom kept, member import
    assert probe["after_first"] == [True, True, True, False, True, False]


def test_administrative_grants_need_the_explicit_flag(probe: Probe) -> None:
    roles = probe["second"]["roles"]
    assert roles["Owner"]["granted"] == [IMPORT]
    assert roles["Admin"]["granted"] == [IMPORT]
    assert roles["Member"]["granted"] == []
    assert probe["after_second"] == [True, False]


def test_custom_grants_are_kept_and_a_rerun_changes_nothing(probe: Probe) -> None:
    for name, role in probe["again"]["roles"].items():
        assert role["granted"] == [], name
        assert role["missing"] == [], name
    assert probe["again"]["roles"]["Member"]["custom"] == 1


def test_other_and_fresh_workspaces(probe: Probe) -> None:
    assert probe["other_untouched"] == [False, False]
    assert probe["other_after_refusal"] is False
    for name, role in probe["fresh"]["roles"].items():
        assert role["missing"] == [], name
    assert probe["bare"].startswith("not a product workspace")
    assert probe["unknown"] == "not found"


def test_bad_input_and_unconfirmed_production_are_refused(probe: Probe) -> None:
    assert probe["bad_id"] == [2, "refused: A workspace id is not a UUID."]
    assert probe["production"][0] == 2
    assert "--confirm-production" in probe["production"][1]
