"""Integrations and API keys (decision P12-K).

Drives `integration_key_probe` in a fresh interpreter: Owners and Admins
create integrations, Members cannot, and an integration is only ever Member
or Read-only; a key is shown once, uncached, and never listed; a key reads,
creates and updates contacts, deals, tasks and companies, audited as the
service account; it never deletes, never reaches integrations, members or
automations, another workspace, or a request that also carries a session;
a Read-only integration only reads; at most two live keys; a revoked key
and a disabled integration's keys stop at once; another workspace cannot
touch the integration.
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
    tmp = tmp_path_factory.mktemp("integration_keys")
    result = run_module("tests.integration.integration_key_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_owners_and_admins_create_member_or_read_only_integrations(probe: Probe) -> None:
    assert probe["created"] == [201, "Member", []]
    assert probe["by_admin"] == 201
    assert probe["by_member"] == 403
    assert probe["refused_roles"] == [422, 422]
    assert probe["duplicate"] == "duplicate_integration"


def test_a_key_is_shown_once_and_never_listed(probe: Probe) -> None:
    status, cache, length = probe["issued"]
    assert status == 201
    assert cache == "no-store"
    assert length > 20
    assert probe["secret_listed"] is False


def test_a_key_reads_creates_and_updates_audited_as_the_integration(probe: Probe) -> None:
    assert probe["allowed"] == [201, 200, 200, 200, 201, 200]
    created = probe["audit"][0]
    assert created[0] == "crm_app.contact.created"
    assert created[1:] == ["service_account", True, probe["integration_id"]]


def test_a_key_never_reaches_beyond_its_routes(probe: Probe) -> None:
    refused = probe["refused"]
    # Routes that take no key answer as for a request without a session.
    assert refused["delete"] == 401
    assert refused["integrations"] == 401
    assert refused["members"] == 401
    assert refused["automations"] == 401
    assert refused["other_workspace"] == 404
    assert refused["with_a_session"] == 401
    assert refused["bad_key"] == 401


def test_a_read_only_integration_only_reads(probe: Probe) -> None:
    assert probe["read_only"] == [200, 403]


def test_limits_revocation_and_disabling_take_effect_at_once(probe: Probe) -> None:
    assert probe["third_key"] == 409
    assert probe["revoked"] == [204, 401, 200]
    assert probe["disabled"] == [200, "disabled", True, 401, 422]
    assert probe["other_workspace_integration"] == 404


def test_every_role_reads_integration_names_and_nothing_more(probe: Probe) -> None:
    """P12-N: a Member reads every integration's ID and name, the disabled
    one too; a key, another workspace's member and another workspace's
    list see none of them."""
    status, listed, fields, has_disabled, by_key, other_list, other_member = probe["names"]
    assert status == 200
    assert listed == ["Reader", "Sheets", "Zapier"]
    assert fields == ["id", "name"]
    assert has_disabled is True
    assert by_key == 401
    assert other_list == []
    assert other_member in (403, 404)
