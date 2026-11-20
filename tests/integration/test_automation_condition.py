"""Automation conditions on a contact custom field (decision P8-G).

Drives `automation_condition_probe` in a fresh interpreter: a bad operator
or missing values are refused when saved; an unknown key, a company field
or a value that does not fit the field's type or options is refused at
activation; a run takes the yes branch when the stored value is one of the
values (text without regard to case) and the no branch otherwise, also
when the contact has no value; a field archived before the run starts
counts as having no value.
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
    tmp = tmp_path_factory.mktemp("automation_condition")
    result = run_module("tests.integration.automation_condition_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_condition_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422]
    unknown = "the custom field its condition reads is not an active contact field"
    assert probe["refused_activate"] == [
        [422, unknown],
        [422, unknown],
        [422, "a value in its condition does not fit the custom field tier"],
        [422, "a value in its condition does not fit the custom field vip"],
    ]


def test_a_run_takes_the_branch_the_stored_value_picks(probe: Probe) -> None:
    gold, other = probe["tags"]["gold"], probe["tags"]["other"]
    assert probe["activated"] == 200
    assert probe["stored"] == {
        "field": "custom_field",
        "key": "tier",
        "op": "in",
        "values": ["Gold"],
    }
    assert probe["branches"] == {
        "ann": ["completed", "yes", [gold]],
        "bob": ["completed", "no", [other]],
        "cy": ["completed", "no", [other]],
    }


def test_an_archived_field_counts_as_having_no_value(probe: Probe) -> None:
    assert probe["archived"] == ["completed", "no"]
