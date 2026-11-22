"""The automation step that sends one marketing email (decision P8-E).

Drives `automation_email_probe` in a fresh interpreter. A step with a limit
out of range or no template id is refused when saved, and a template that
does not exist at activation; content sent with a draft is dropped. Only a
member who may approve campaigns activates it, and activation freezes the
template's subject and body: editing the template later changes nothing
sent. While campaigns cannot send the step is skipped; once they can, a
contact with consent gets one email with one-click unsubscribe (sent through
a recording provider), a retried job queues nothing more, and a contact
without consent or an address is skipped, as is one past the daily limit
until 24 hours have gone by. The unsubscribe link suppresses the address,
also after the automation is deleted, and only in its own workspace. In a
rehearsal workspace the email is recorded and closed unsent.
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
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        env.pop(name, None)
    tmp = tmp_path_factory.mktemp("automation_email")
    result = run_module("tests.integration.automation_email_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_email_step_is_refused_and_a_draft_names_its_template_only(probe: Probe) -> None:
    assert probe["refused_save"] == [422, 422, 422]
    assert probe["refused_activate"] == [422, "an email template it sends no longer exists"]
    stored = probe["stored"]
    assert stored == {"type": "send_email", "template_id": stored["template_id"], "daily_limit": 2}


def test_only_a_campaign_approver_activates_it_and_the_content_is_frozen(probe: Probe) -> None:
    assert probe["member_activate"] == [403, "campaign_approval_required"]
    assert probe["activated"] == 200
    frozen = probe["frozen"]
    assert frozen["subject"] == "Welcome {{first_name}}"
    assert frozen["body"] == "Hello {{first_name}},\nthanks for joining."
    assert frozen["daily_limit"] == 2


def test_nothing_is_queued_while_campaigns_cannot_send(probe: Probe) -> None:
    assert probe["ann"] == ["completed", [["skipped", "sending_unavailable"]], 0]


def test_a_contact_with_consent_gets_one_email(probe: Probe) -> None:
    assert probe["bob"] == ["completed", [["done", None]], 1]
    # The subject frozen at activation, not the template's later edit.
    assert probe["bob_email"] == ["automation", "Welcome Bob", True, "queued", True]
    assert probe["bob_sent"] == "sent"
    assert probe["bob_headers"] == [1, True]
    assert probe["bob_again"] == ["completed", 1]


def test_no_consent_no_address_or_the_daily_limit_skips_the_step(probe: Probe) -> None:
    assert probe["cal"] == ["completed", [["skipped", "not_eligible"]]]
    assert probe["dan"] == ["completed", [["skipped", "no_email"]]]
    assert probe["eve"] == ["completed", [["done", None]]]
    assert probe["fay"] == ["completed", [["skipped", "daily_limit"]], 2]
    assert probe["gus"] == ["completed", [["done", None]], 3]


def test_the_unsubscribe_link_suppresses_the_address(probe: Probe) -> None:
    # The public route answers alike for a known, repeated or foreign token.
    assert probe["unsubscribe"] == [204, 204, 204]
    assert probe["unsubscribed"] == ["unsubscribed", 1]
    # Both rows outlive the automation (its reference is cleared) and both
    # links worked: Bob's before, Eve's after the deletion.
    assert probe["after_delete"] == [204, 204, 2]


def test_a_rehearsal_workspace_records_the_email_unsent(probe: Probe) -> None:
    assert probe["rehearsal"] == [
        "completed",
        [["done", "rehearsal"]],
        0,
        [["failed", "rehearsal"]],
    ]
    assert probe["isolated"] == 0
