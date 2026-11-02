"""Customer-owned sending domains (decision P6-D).

Drives `sending_domain_probe` in a fresh interpreter with a provider test
double: without a provider a domain is kept unregistered and says why;
reserved, platform and malformed domains and callers who may not update
the workspace are refused; the provider's records are kept exactly; a
domain belongs to one workspace; identities are addresses on the
workspace's own domains; replies use the platform sender until the
provider reports the domain verified (by signed event), then the
workspace's address; when the domain fails, an email queued with that
address waits and is never sent from another; other workspaces see
nothing; removal frees the domain.
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
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CUSTOMER_DOMAINS_ENABLED"):
        env.pop(name, None)
    tmp = tmp_path_factory.mktemp("sending_domains")
    result = run_module("tests.integration.sending_domain_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_without_a_provider_nothing_is_created_and_the_reason_is_shown(probe: Probe) -> None:
    assert probe["no_provider"] == [201, "not_registered", "provider_unavailable", False]


def test_unsafe_domains_and_callers_are_refused(probe: Probe) -> None:
    # malformed, the platform's own, reserved, a member, an outsider
    assert probe["refused"] == [422, 422, 422, 403, 404]


def test_the_providers_records_are_kept_and_a_domain_has_one_workspace(probe: Probe) -> None:
    status, kinds, value, created = probe["registered"]
    assert (status, kinds, created) == ("not_started", ["SPF", "DKIM"], True)
    assert value == "v=spf1 include:provider.example.org ~all"
    assert probe["taken"] == [409, 409]


def test_identities_live_on_the_workspaces_own_domain(probe: Probe) -> None:
    address, usable = probe["identity"]
    assert address.startswith("jan@acme-")
    assert usable is False
    # a plus sign, no stream, a duplicate address, another workspace
    assert probe["identity_refused"] == [422, 422, 409, 404]


def test_the_workspaces_address_is_used_only_while_verified(probe: Probe) -> None:
    assert probe["before_verify"] is None
    assert probe["verify_request"] == "pending"
    assert probe["events"] == [204, 204, 204]
    assert probe["after_verify"] == ["verified", True]
    address, outcome, sent_from = probe["own_sender"]
    assert outcome == "sent"
    assert sent_from == address
    queued_from, waiting, sent = probe["after_failure"]
    assert queued_from == address
    assert waiting == "sender_unverified"
    assert sent == 0


def test_late_or_mismatched_domain_events_change_nothing(probe: Probe) -> None:
    assert probe["late_events"] == [204, "failed", 204, "failed"]


def test_a_name_never_verified_is_released_after_its_claim_time(probe: Probe) -> None:
    assert probe["claim_held"] == [True, 409]
    assert probe["claim_released"] == [True, "expired", "claim_expired", None, 422, 201]
    assert probe["verified_kept"] == 409


def test_other_workspaces_see_nothing_and_removal_frees_the_domain(probe: Probe) -> None:
    assert probe["isolation"] == [False, 404, 403]
    assert probe["removed"] == [204, 201]
