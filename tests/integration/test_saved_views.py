"""Saved views of the lists (decision P3-SV).

Drives `saved_view_probe` in a fresh interpreter: a member saves a view of
the contacts list, its name tidied and its filters kept; nobody else sees,
renames or deletes it, nor another workspace; a duplicate name, an unknown
filter, an unknown stage and an empty name are refused; a Read-only member
saves their own; renaming and new filters are saved; a deals view keeps
the deals list's filters and refuses the contacts list's; deleting is
final.
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
    tmp = tmp_path_factory.mktemp("saved_views")
    result = run_module("tests.integration.saved_view_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_member_saves_a_view_for_themselves_only(probe: Probe) -> None:
    status, name, filters = probe["made"]
    assert status == 201
    assert name == "My customers"
    assert filters["q"] == "acme"
    assert filters["lifecycle_stage"] == ["customer"]
    assert filters["sort"] == "updated_at"
    assert probe["mine"] == ["My customers"]
    assert probe["others_see"] == [[], []]
    assert probe["others_change"] == [404, 404, 404]


def test_refusals(probe: Probe) -> None:
    refused = probe["refused"]
    assert refused["duplicate"] == "duplicate_saved_view"
    assert refused["unknown_filter"] == 422
    assert refused["bad_stage"] == 422
    assert refused["empty_name"] == 422


def test_changes_deals_and_deletion(probe: Probe) -> None:
    assert probe["reader_saves"] == 201
    assert probe["renamed"] == ["Big customers", ["me"]]
    assert probe["deal"] == [201, True]
    assert probe["deal_bad"] == 422
    assert probe["deleted"] == [204, 404]
