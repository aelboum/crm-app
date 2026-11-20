"""The contact brief's facts and route (decision P9-B).

Drives `contact_brief_probe` in a fresh interpreter: the facts are exactly
the allowlist (stage, source, tag names, history kinds, deal stages and
outcomes, task and appointment counts) and a request never carries a name,
address, phone number, job title or task title; with AI off (the default)
the route answers `unavailable` to an Owner and a Read-only member alike,
404 for a contact of another workspace or none, and 401 without a session.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
UNAVAILABLE = [200, {"state": "unavailable", "text": None}]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("contact_brief")
    result = run_module("tests.integration.contact_brief_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_the_facts_are_the_allowlist_only(probe: Probe) -> None:
    document = probe["document"]
    assert document["lifecycle_stage"] == "lead"
    assert document["source"] == "referral"
    assert document["tags"] == ["Priority"]
    assert [deal["outcome"] for deal in document["deals"]] == ["open"]
    assert document["open_tasks"] == 2
    assert document["overdue_tasks"] == 1
    assert document["upcoming_appointments"] == 1
    assert "created" in probe["history_kinds"]
    assert probe["leaked"] == []
    assert probe["missing"] is None


def test_with_ai_off_the_route_says_unavailable(probe: Probe) -> None:
    assert probe["owner"] == UNAVAILABLE
    assert probe["reader"] == UNAVAILABLE


def test_another_workspaces_contact_or_none_is_not_found(probe: Probe) -> None:
    assert probe["other_owner"] == 404
    assert probe["other_workspace_id"] == [404, {"detail": {"code": "not_found"}}]
    assert probe["unknown"] == [404, {"detail": {"code": "not_found"}}]
    assert probe["anonymous"] == 401
