"""Unverified public matches and consent confirmation (decision P7-V).

Drives `consent_confirmation_probe` in a fresh interpreter: a stranger who
types an existing contact's email into a public form does not tag the
contact, record consent or start automations, though the submission is
kept; a confirmation is queued to that address, keeping only the token's
hash; confirming works once, answers the same when repeated, only in its
own workspace, and records consent by `email_confirmation`; an expired
link confirms nothing; a new person's submission behaves as before.
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
    env.pop("EMAIL_SENDING_ENABLED", None)
    tmp = tmp_path_factory.mktemp("consent_confirmations")
    result = run_module("tests.integration.consent_confirmation_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_matched_contact_is_not_changed_by_an_unverified_submission(probe: Probe) -> None:
    assert probe["matched_submit"] == 201
    assert probe["matched"] == {
        "tags": 0,
        "consent": 0,
        "runs": 0,
        "stage": "lead",
        "submission": [{"outcome": "matched", "consent": True}],
    }


def test_a_confirmation_is_queued_with_only_the_tokens_hash_kept(probe: Probe) -> None:
    count, purpose, status, to, confirmed, hash_length, not_stored, has_link = probe["pending"]
    assert (count, purpose, status, to) == (
        1,
        "consent_confirmation",
        "queued",
        "ada@customer.example.org",
    )
    assert confirmed is None
    assert (hash_length, not_stored, has_link) == (64, True, True)


def test_confirming_works_once_idempotently_and_only_in_its_workspace(probe: Probe) -> None:
    other_workspace, wrong_token, first, again, records = probe["confirm"]
    assert (other_workspace, wrong_token, first, again) == (404, 404, 204, 204)
    assert records == [
        {"status": "granted", "method": "email_confirmation", "wording": "Yes, send me news."}
    ]


def test_repeated_submissions_do_not_flood_the_address(probe: Probe) -> None:
    assert probe["pending_after_repeat"] == 1


def test_an_expired_link_confirms_nothing(probe: Probe) -> None:
    assert probe["expired"] == [404, 1]


def test_a_new_persons_submission_behaves_as_before(probe: Probe) -> None:
    assert probe["new_submit"] == 201
    assert probe["new"] == {
        "tags": 1,
        "consent": [{"method": "web_form"}],
        "runs": 2,
        "confirmations": 0,
    }


def test_requesting_and_confirming_are_audited_as_the_form_and_the_link(probe: Probe) -> None:
    assert probe["confirm_audit"] == [
        {
            "action": "crm_app.consent_confirmation.requested",
            "no_member": True,
            "component": "crm_app.public_form",
        },
        {
            "action": "crm_app.consent_confirmation.confirmed",
            "no_member": True,
            "component": "crm_app.consent_link",
        },
    ]
