"""Round-robin assignment in automations (decision P8-R): contacts alternate
between the listed members, a retried step never advances the turn, a
member who left is passed over, and a rotation of one member is refused.
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
        "tests.integration.round_robin_probe", [], env, tmp_path_factory.mktemp("rr"), timeout=600
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_contacts_alternate_and_a_retry_never_advances(probe: Any) -> None:
    first, second = probe["ids"]
    assert probe["owners"] == [first, second, first]


def test_a_member_who_left_is_passed_over(probe: Any) -> None:
    _, second = probe["ids"]
    assert probe["after_leaving"] == [second, second]


def test_a_rotation_needs_two_members(probe: Any) -> None:
    assert probe["one_member"] == 422
