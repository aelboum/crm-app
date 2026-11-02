"""Email templates (decision P7-T).

Drives `email_template_probe` in a fresh interpreter: members who may
manage campaigns create templates (name trimmed, line endings normalised);
readers only read; other workspaces see nothing and cannot act; the
campaign placeholder rules apply (unknown placeholders and stray braces
are refused, a subject is one line); names are unique per workspace;
changes need the current version; rendering for a contact needs the
permission to reply, fills the placeholders literally (a value is never
expanded again) and only for the workspace's own contacts; deleting needs
the manage permission.
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
    tmp = tmp_path_factory.mktemp("email_templates")
    result = run_module("tests.integration.email_template_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_members_create_templates_and_others_may_not(probe: Probe) -> None:
    assert probe["created"] == [
        201,
        "Follow up",
        "Dear {{first_name}} {{last_name}},\n\nThank you.",
        '"1"',
    ]
    assert probe["create_access"] == {"reader": 403, "other_owner": 404, "outsider": 404}


def test_the_campaign_placeholder_rules_apply(probe: Probe) -> None:
    refused = probe["refused"]
    assert refused["unknown_placeholder"] == "invalid_template"
    assert refused["stray_braces"] == "invalid_template"
    # a subject is always one line: line breaks become spaces
    assert refused["two_line_subject"] == 201
    assert refused["taken_name"] == "template_name_taken"
    assert refused["extra_field"] == 422


def test_every_role_reads_and_other_workspaces_see_nothing(probe: Probe) -> None:
    assert probe["list"] == {"reader": ["Follow up", "Z"], "other_owner": []}


def test_changes_need_the_current_version_and_the_manage_permission(probe: Probe) -> None:
    assert probe["update"] == ["stale_version", 403]
    assert probe["updated"] == ["Hi {{first_name}}", 2]


def test_rendering_fills_placeholders_literally_for_own_contacts(probe: Probe) -> None:
    assert probe["rendered"] == {
        "subject": "Hi Ada",
        "body": "Dear Ada {{last_name}},\n\nThank you.",
    }
    assert probe["render_refused"] == {
        "reader": 403,
        "foreign_contact": 404,
        "other_workspace": 404,
    }


def test_deleting_needs_the_manage_permission(probe: Probe) -> None:
    reader, other, member, left = probe["delete"]
    assert (reader, other, member) == (403, 404, 204)
    assert [item["name"] for item in left] == ["Z"]
