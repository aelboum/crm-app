"""Gate G-LOCK: the last active Owner can never be removed, demoted or
disabled, including by competing requests, and only Owners touch Owners.

Drives `owner_route_probe` in a fresh interpreter against the integration
database. Every assertion on the invariant uses state read back from the
database after the requests finished.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    cwd: Path = tmp_path_factory.mktemp("owners")
    result = run_module("tests.integration.owner_route_probe", [], env, cwd, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.mark.parametrize(
    "scenario", ["revoke", "suspend", "drop_role", "revoke_vs_drop_role", "both_step_down"]
)
def test_two_owners_removing_each_other_leave_exactly_one_active_owner(
    probe: Probe, scenario: str
) -> None:
    for round_ in probe[f"race_{scenario}"]:
        assert round_["active_owners"] == 1, round_
        assert round_["statuses"].count(200) == 1, round_
        assert all(status in (200, 403, 409) for status in round_["statuses"]), round_


def test_ownership_can_be_transferred(probe: Probe) -> None:
    transfer = probe["transfer"]
    assert (transfer["grant"], transfer["step_down"]) == (200, 200)
    assert "Owner" in transfer["admin_roles"]
    assert "Owner" not in transfer["former_owner_roles"]
    assert transfer["active_owners"] == 1


def test_refused_changes_return_the_right_status(probe: Probe) -> None:
    refusals = probe["refusals"]
    assert refusals["last_owner_steps_down"] == 409
    assert refusals["owner_revokes_self"] == 403
    assert refusals["admin_grants_owner"] == 403
    assert refusals["admin_revokes_owner"] == 403
    assert refusals["admin_suspends_owner"] == 403
    assert refusals["admin_promotes_self"] == 403
    assert refusals["member_grants_admin"] == 403
    assert refusals["reader_suspends_member"] == 403
    assert refusals["owner_change_unconfirmed"] == 409
    assert refusals["unknown_membership"] == 404


def test_refused_changes_left_the_state_untouched(probe: Probe) -> None:
    refusals = probe["refusals"]
    assert refusals["active_owners"] == 1
    assert refusals["owner_roles"] == ["Owner"]
    assert refusals["admin_roles"] == ["Admin"]
    assert refusals["member_roles"] == ["Member"]


def test_an_admin_manages_ordinary_members(probe: Probe) -> None:
    managed = probe["admin_manages_member"]
    assert (managed["suspend"], managed["reactivate"], managed["grant_admin"]) == (200, 200, 200)
    assert managed["member_roles"] == ["Admin", "Member"]


def test_another_workspaces_membership_is_not_found(probe: Probe) -> None:
    assert probe["cross_workspace"] == 404
    assert probe["other_workspace_active_owners"] == 1
