"""Transactional email and delivery tracking (decision P6-E).

Drives `email_probe` in a fresh interpreter with a recording provider and
a made-up webhook secret; no real provider is ever called. Covers the off
switch, one send per email with a stable Message-ID (also for a replayed
job and for two jobs at once), transient and permanent failures, the
suppression list, bounded tries, orphaned index rows, the signed webhook
(no secret, valid, duplicate, out of order, bounce suppression, forged,
stale, unknown email, untracked type, too large), audit entries without
addresses, and another workspace seeing nothing.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
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
        "EMAIL_DEFAULT_SENDER": "hello@mail.example.test",
    }
    env.pop("EMAIL_SENDING_ENABLED", None)
    env.pop("RESEND_WEBHOOK_SECRET", None)
    tmp = tmp_path_factory.mktemp("emails")
    result = run_module("tests.integration.email_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_nothing_is_sent_while_sending_is_off(probe: Probe) -> None:
    assert probe["disabled"] == ["disabled", "queued", 0]
    assert probe["queued_index"] == {"provider_message_id": None, "retry_at": True}


def test_an_email_is_sent_once_with_a_stable_message_id(probe: Probe) -> None:
    assert probe["sent"] == "sent"
    assert probe["sent_row"] == {"status": "sent", "attempts": 1, "provider": "fake"}
    message = probe["message"]
    assert message["message_id"] == message["expected"]
    assert message["to"] == ["ada@example.test"]
    assert probe["sent_index"]["retry_at"] is False
    assert probe["sent_index"]["provider_message_id"].startswith("re_")
    # A replayed job finds it sent and sends nothing.
    assert probe["replay"] == ["sent", 1]


def test_two_jobs_at_once_send_one_email(probe: Probe) -> None:
    answers, sends = probe["race"]
    assert answers == ["sending", "sent"]
    assert sends == 1


def test_a_transient_failure_is_retried_and_a_permanent_one_fails(probe: Probe) -> None:
    outcome, row, index = probe["transient"]
    assert outcome == "deferred:rate_limit_exceeded"
    assert (row["status"], row["attempts"], row["last_error"]) == (
        "queued",
        1,
        "rate_limit_exceeded",
    )
    assert index["retry_at"] is True
    # Not sooner than the backoff (30 s, up to 25% jitter); nothing sent meanwhile.
    waiting, seconds, sent = probe["backoff"]
    assert waiting == "waiting"
    assert 25 <= seconds <= 40
    assert sent == 2
    assert probe["after_transient"] == ["sent", 2]
    assert probe["permanent"] == [
        "failed",
        "validation_error",
        {"provider_message_id": None, "retry_at": False},
    ]


def test_suppressed_addresses_are_never_sent_to_and_tries_are_bounded(probe: Probe) -> None:
    assert probe["suppressed"] == ["suppressed", 0]
    assert probe["exhausted"] == ["failed", "attempts_exhausted"]


def test_a_rolled_back_email_leaves_no_index_row(probe: Probe) -> None:
    assert probe["orphan"] == [True, None, False]


def test_the_webhook_needs_its_secret_and_a_valid_recent_signature(probe: Probe) -> None:
    assert probe["no_secret"] == 404
    forged_body, bad_signature, stale, events = probe["forged"]
    assert (forged_body, bad_signature, stale) == (401, 401, 401)
    assert events == 3  # only the delivered, delayed and bounced events
    assert probe["too_large"] == 400


def test_delivery_events_are_recorded_once_and_move_forward_only(probe: Probe) -> None:
    assert probe["delivered"] == [204, "delivered", 1]
    assert probe["duplicate"] == [204, 1]
    assert probe["late_delay"] == [204, "delivered"]
    assert probe["bounced"] == [204, "bounced"]
    assert probe["bounce_suppression"] == 1
    assert probe["unknown_email"] == [204, 3]
    assert probe["ignored_type"] == [204, 3]


def test_another_workspace_sees_none_of_it(probe: Probe) -> None:
    assert probe["own_rows"] == 8
    assert probe["other_workspace_rows"] == 0
    assert probe["other_workspace_events"] == 0


def test_audit_entries_name_the_email_never_the_address(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.email' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["first"]),
    ).fetchall()
    assert [action for action, _ in rows] == [
        "crm_app.email.queued",
        "crm_app.email.sent",
        "crm_app.email.bounced",
    ]
    assert "example.test" not in json.dumps([meta for _, meta in rows])


# --- Streams, limits and production (decision P6-S) -------------------------------------


def test_a_retry_waits_at_least_as_long_as_the_provider_asks(probe: Probe) -> None:
    outcome, seconds = probe["retry_after"]
    assert outcome == "deferred:rate_limit_exceeded"
    assert 590 <= seconds <= 610


def test_each_workspace_is_held_to_its_stream_rate(probe: Probe) -> None:
    assert probe["rate_limited"] == [["sent", "sent", "rate_limited"], "queued"]
    assert probe["rate_wait"] is True


def test_conversation_mail_needs_its_switch_and_its_own_sender(probe: Probe) -> None:
    streams = probe["streams"]
    assert streams["outcomes"] == ["disabled", "no_sender", "sent"]
    assert streams["from"] == "team@mail.example.test"
    assert streams["message_id_domain"] == "mail.example.test>"
    assert probe["transactional_from"] == "no-reply@notify.example.test"


def test_production_never_hands_email_to_a_provider(probe: Probe) -> None:
    assert probe["production"] == ["disabled", 0]


def test_a_provider_rejection_after_acceptance_is_final(probe: Probe) -> None:
    assert probe["provider_failed"] == [204, "rejected", 204, "rejected"]
