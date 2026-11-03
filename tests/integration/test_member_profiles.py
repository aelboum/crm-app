"""Member display names (decision M-P1).

Drives `member_profile_probe` in a fresh interpreter. Every role sets its
own name and only its own; names show in the member list; values are
normalised and refused when invalid; another workspace cannot read or write
them; clearing removes the row; the audit records the change without the
name.
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
    tmp = tmp_path_factory.mktemp("member_profiles")
    result = run_module("tests.integration.member_profile_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_member_sets_their_own_normalised_name(probe: Probe) -> None:
    assert probe["empty"] is None
    status, body = probe["set_owner"]
    assert status == 200
    assert body["display_name"] == "Anna de Vries"
    assert body["user_id"] == probe["ids"][0]
    assert probe["set_reader"] == [200, "Bram"]


def test_names_show_in_the_member_list(probe: Probe) -> None:
    assert probe["listed"] == [[False, "Bram"], [True, "Anna de Vries"]]


def test_invalid_names_and_attempts_to_name_someone_else_are_refused(probe: Probe) -> None:
    assert probe["refused"] == {
        "too_long": 422,
        "control": 422,
        "newline": 422,
        "extra_field": 422,
        "not_text": 422,
    }


def test_another_workspace_can_neither_read_nor_write_them(probe: Probe) -> None:
    assert probe["foreign"] == [404, 404, None]
    assert probe["rows_b"] == 0


def test_clearing_removes_only_the_callers_name(probe: Probe) -> None:
    assert probe["cleared"] == [200, None]
    assert probe["unchanged_owner"] == "Anna de Vries"
    assert probe["rows"] == 1


def test_changes_are_audited_without_the_name(probe: Probe) -> None:
    assert probe["audits"] == [
        ["crm_app.member_profile.updated", False],
        ["crm_app.member_profile.updated", False],
        ["crm_app.member_profile.cleared", False],
    ]
