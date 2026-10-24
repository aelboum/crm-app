"""The workspace directory (`GET /v1/workspaces`, decision P2-F 2).

Drives `directory_probe` in a fresh interpreter against the integration
database. Covers `PHASE2-PLAN.md` §13 "Workspace directory": only
workspaces with an ACTIVE membership are listed, suspended, revoked and
closed ones are not, nobody else's workspaces appear, and listing never
grants data access.
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
    cwd: Path = tmp_path_factory.mktemp("directory")
    result = run_module("tests.integration.directory_probe", [], env, cwd, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_it_lists_only_workspaces_with_an_active_membership(probe: Probe) -> None:
    status, body = probe["person"]
    assert status == 200
    listed = {item["id"] for item in body["items"]}
    ids = probe["ids"]
    assert listed >= {ids["own"], ids["joined"]}
    assert listed.isdisjoint({ids["suspended"], ids["revoked"], ids["closed"], ids["other"]})
    assert set(body["items"][0]) == {"id", "name"}


def test_it_is_sorted_by_name(probe: Probe) -> None:
    names = [item["name"].casefold() for item in probe["person"][1]["items"]]
    assert names == sorted(names)


def test_someone_without_memberships_sees_none_and_strangers_are_refused(probe: Probe) -> None:
    assert probe["outsider"] == [200, {"items": []}]
    assert probe["anonymous"] == 401


def test_listing_grants_nothing(probe: Probe) -> None:
    assert probe["open"] == {
        "own": 200,
        "joined": 200,
        "suspended": 403,
        "revoked": 403,
        "closed": 404,
        "other": 404,
    }


def test_a_query_parameter_cannot_widen_the_list(probe: Probe) -> None:
    assert probe["ids"]["other"] not in {item["id"] for item in probe["unknown_query"]["items"]}
