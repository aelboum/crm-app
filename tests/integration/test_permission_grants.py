"""The permission grant migrations' read-only report (PERMISSION-GRANT-
MIGRATIONS-PLAN.md, step A), against the test database.

Drives `permission_grants_probe` in a fresh interpreter: a workspace with the
Phase 2 templates lacks exactly what the migrations declare; a current one
lacks nothing; a tenant without the product's roles is `role_missing` for
every migration. Nothing is granted.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("permission_grants")
    result = run_module("tests.integration.permission_grants_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.mark.parametrize("name", ["standard", "administrative"])
def test_an_old_workspace_lacks_exactly_what_is_declared(probe: Probe, name: str) -> None:
    rows = probe[name]["old"]
    assert all(r["lacking"] == 1 and r["role_missing"] == 0 for r in rows)
    assert sum(r["grants_needed"] for r in rows) == probe[f"{name}_declared"]


@pytest.mark.parametrize("name", ["standard", "administrative"])
def test_a_current_workspace_lacks_nothing(probe: Probe, name: str) -> None:
    assert all(r["lacking"] == 0 and r["grants_needed"] == 0 for r in probe[name]["fresh"])


@pytest.mark.parametrize("name", ["standard", "administrative"])
def test_a_tenant_without_the_roles_is_role_missing(probe: Probe, name: str) -> None:
    assert all(r["role_missing"] == 1 and r["lacking"] == 0 for r in probe[name]["bare"])


def test_the_command_reports_every_standard_migration(probe: Probe) -> None:
    assert probe["cli"][0] == 0
    assert probe["cli"][1] == len(probe["standard"]["old"])
