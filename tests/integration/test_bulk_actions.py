"""Bulk actions on contacts (decision P3-BK).

Drives `bulk_probe` in a fresh interpreter: a Member assigns an owner to
several contacts at once, and repeating it changes nothing; unknown ids
and another workspace's contacts are skipped as not found, the other
workspace's contact untouched; tags are added and removed, the stage set,
contacts archived and restored; each contact gets its own history and
audit entries; an owner who is not a member, an unknown stage, a missing
tag, more than 100 or no contacts, an unknown action and a Read-only
member are refused.
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
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("bulk")
    result = run_module("tests.integration.bulk_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_assigning_changes_each_contact_once_and_skips_the_unknown(probe: Probe) -> None:
    assigned = probe["assigned"]
    assert assigned["done"] == 3
    assert assigned["unchanged"] == 0
    assert sorted(s["id"] for s in assigned["skipped"]) == sorted(
        [probe["missing"], probe["foreign"]]
    )
    assert {s["reason"] for s in assigned["skipped"]} == {"not_found"}
    assert probe["owners"] is True
    assert probe["again"] == {"done": 0, "unchanged": 3, "skipped": []}
    assert probe["foreign_untouched"] is None


def test_tags_stage_archive_and_restore(probe: Probe) -> None:
    assert probe["tagged"] == [3, 3, 3]
    assert probe["staged"] == 3
    assert probe["archived"] == [2, 2, 2]


def test_each_contact_has_its_own_history_and_audit(probe: Probe) -> None:
    # Created, owner, two tag changes, stage, archived, restored.
    assert probe["history"] >= 6
    # Owner, stage (tags and archiving are audited under their own actions).
    assert probe["audit"] >= 2


def test_refusals(probe: Probe) -> None:
    refused = probe["refused"]
    assert refused["outsider_owner"]["code"] == "owner_not_member"
    assert refused["bad_stage"] == {"code": "invalid_bulk_action", "field": "stage"}
    assert refused["no_tag"] == {"code": "invalid_bulk_action", "field": "tag_id"}
    assert refused["too_many"] == 422
    assert refused["empty"] == 422
    assert refused["reader"] == 403
    assert refused["unknown_action"] == 422
