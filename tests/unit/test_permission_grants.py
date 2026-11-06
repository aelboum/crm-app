"""The permission grant migrations (`crm_app.permission_grants`): append-only,
tied to the role templates, never authority-changing, administrative ones
held back (PERMISSION-GRANT-MIGRATIONS-PLAN.md, step A).

The checks run in `permission_grants_guard`, in a fresh interpreter with
placeholder settings (importing SaaS-OS's permission grants reads its
configuration); each is reported here as its own test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import PLACEHOLDER_SETTINGS, REPO_ROOT, clean_environment, run_module

CHECKS = (
    "valid_declarations",
    "no_authority_permission",
    "administrative_held_back",
    "registered_permissions",
    "templates_are_baseline_plus_migrations",
    "role_names",
    "digests_pinned",
)


@pytest.fixture(scope="module")
def problems(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[str]]:
    env = clean_environment({**PLACEHOLDER_SETTINGS, "PYTHONPATH": str(REPO_ROOT)})
    result = run_module(
        "tests.unit.permission_grants_guard", [], env, tmp_path_factory.mktemp("grants")
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_every_check_ran(problems: dict[str, list[str]]) -> None:
    assert set(problems) == set(CHECKS)


@pytest.mark.parametrize("check", CHECKS)
def test_check_finds_no_problem(problems: dict[str, list[str]], check: str) -> None:
    assert problems[check] == []


def test_the_report_refuses_without_a_scope(tmp_path: Path) -> None:
    env = clean_environment({**PLACEHOLDER_SETTINGS, "PYTHONPATH": str(REPO_ROOT)})
    result = run_module("crm_app.permission_grants", ["--report"], env, tmp_path)
    assert result.returncode == 2
