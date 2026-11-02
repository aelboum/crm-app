"""Custom domains for hosted pages (decision P12-D).

Drives `custom_domain_probe` in a fresh interpreter with a DNS test double:
claims by members who may update the workspace, with reserved, local,
wildcard, address and app hostnames refused; nothing verified without a
resolver or without the exact TXT record; a verified hostname mapped to
its workspace only; another workspace's claim kept pending while the host
is held, then verifying once the record changes hands and the daily
re-check lapses the old claim (a failing lookup lapses nothing); removal
and expiry; other workspaces and outsiders see nothing.
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
    tmp = tmp_path_factory.mktemp("custom_domains")
    result = run_module("tests.integration.custom_domain_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_claim_shows_the_record_to_publish(probe: Probe) -> None:
    assert probe["added"] == [201, True, "pending", True, True, True]
    assert probe["reader_lists"] == 1


def test_unsafe_or_foreign_hostnames_and_callers_are_refused(probe: Probe) -> None:
    # localhost, wildcard, address, reserved, under the app, duplicate,
    # a member, another workspace's owner
    assert probe["refused"] == [422, 422, 422, 422, 422, 409, 403, 404]
    assert probe["member_check"] == 403
    assert probe["outsider"] == 404


def test_only_the_exact_record_verifies(probe: Probe) -> None:
    assert probe["no_resolver"] == ["pending", "resolver_unavailable"]
    assert probe["missing_record"] == {"status": "pending", "error": "record_not_found"}
    assert probe["resolve_pending"] == 404
    assert probe["verified"] == {"status": "verified", "error": None}
    assert probe["resolve_verified"] is True
    assert probe["resolve_with_port"] is True
    assert probe["resolve_unknown"] == 404


def test_one_workspace_holds_a_hostname_and_a_handover_needs_the_record(probe: Probe) -> None:
    assert probe["claimed_elsewhere"] == {"status": "pending", "error": "claimed_elsewhere"}
    assert probe["b_sees"] == [1, 404, 404]
    assert probe["recheck_failing_dns"] == 0
    assert probe["a_after"] == "lapsed"
    assert probe["resolve_after_lapse"] == 404
    assert probe["b_takes_over"] == {"status": "verified", "error": None}
    assert probe["resolve_b"] is True
    assert probe["resolve_suspended"] == 404
    assert probe["resolve_reactivated"] is True


def test_the_edge_may_ask_only_about_verified_open_hosts(probe: Probe) -> None:
    # 12D.2: yes (204, no body, no workspace id) only for a verified host of
    # an open workspace; otherwise 404.
    assert probe["allowed"] == [204, "", 204, 404, 404, 404]
    assert probe["allowed_suspended"] == 404


def test_removal_and_expiry_free_the_hostname(probe: Probe) -> None:
    assert probe["removed"] == [204, 404]
    assert probe["expired_check"] == {"code": "claim_expired"}
    assert probe["expired_cleared"] is True
