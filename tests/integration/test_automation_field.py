"""The automation step that sets a contact custom field (decision P8-F).

Drives `automation_field_probe` in a fresh interpreter: a bad key or no
value is refused when saved; an unknown key, a company field or a value
that does not fit the field's type or options is refused at activation; a
run sets each field, writes a history entry by the automation and an audit
entry naming the key and never the value; a retried run changes nothing;
the run history lists the steps; after activation, an archived field or a
removed option skips its step with a code and leaves the field as it was.
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
    tmp = tmp_path_factory.mktemp("automation_field")
    result = run_module("tests.integration.automation_field_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_step_is_refused_when_saved_or_activated(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422]
    unknown = "a custom field it sets is not an active contact field"
    assert probe["refused_activate"] == [
        [422, unknown],
        [422, unknown],
        [422, "the value for the custom field tier does not fit it"],
        [422, "the value for the custom field seats does not fit it"],
        [422, "the value for the custom field vip does not fit it"],
    ]


def test_a_run_sets_each_field_once(probe: Probe) -> None:
    assert probe["activated"] == 200
    assert probe["stored"] == [
        {"type": "set_custom_field", "field_key": "tier", "value": "Gold"},
        {"type": "set_custom_field", "field_key": "seats", "value": 5},
        {"type": "set_custom_field", "field_key": "vip", "value": True},
    ]
    assert probe["status"] == "completed"
    assert probe["steps"] == [[i, "set_custom_field", "done", None] for i in range(3)]
    assert probe["values"] == {"tier": "Gold", "seats": 5, "vip": True}
    assert probe["retry_same_version"] is True


def test_history_and_audit_name_the_automation_and_the_key_only(probe: Probe) -> None:
    entry = {"kind": "updated", "fields": ["custom_fields"], "source": "automation"}
    assert probe["history"] == [{**entry, "actor_user_id": None}] * 3
    assert [row["keys"] for row in probe["audit"]] == [["tier"], ["seats"], ["vip"]]
    assert not any("Gold" in row["raw"] for row in probe["audit"])


def test_the_run_history_lists_the_steps(probe: Probe) -> None:
    assert probe["runs_listed"] == [200, ["set_custom_field"] * 3]


def test_an_archived_field_or_removed_option_skips_the_step(probe: Probe) -> None:
    assert probe["later_status"] == "completed"
    assert probe["later_steps"] == [
        [0, "set_custom_field", "skipped", "invalid"],
        [1, "set_custom_field", "skipped", "field_gone"],
        [2, "set_custom_field", "done", None],
    ]
    assert probe["later_values"] == {"vip": True}
