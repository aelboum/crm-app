"""Inbound email (decision P6-I).

Drives `inbound_probe` in a fresh interpreter with a test double of the
receiving API: routing addresses are created with a thread's first email
reply and used as Reply-To only while inbound is on; the webhook needs its
switch, its own secret and a valid recent signature, records each email
once, ignores other event types and refuses malformed received events;
processing routes by token only, quarantines mail from someone other than
the contact or failing DMARC, keeps unknown, absent, several or forged
routing addresses unmatched, waits on transient fetch failures and fails
permanent ones; HTML is reduced to text; attachments are listed, never
fetched; a redelivered or concurrently processed email is added once;
reviews are for members who may reply, need the version and are decided
once; another workspace sees none of it; production receives nothing.
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
        "EMAIL_DEFAULT_SENDER": "hello@mail.example.test",
    }
    for name in (
        "EMAIL_SENDING_ENABLED",
        "EMAIL_INBOUND_ENABLED",
        "EMAIL_PARENT_DOMAIN",
        "RESEND_INBOUND_WEBHOOK_SECRET",
    ):
        env.pop(name, None)
    tmp = tmp_path_factory.mktemp("inbound")
    result = run_module("tests.integration.inbound_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_thread_gets_a_routing_address_used_only_while_inbound_is_on(probe: Probe) -> None:
    assert probe["route"] == [True, True]
    assert probe["index"] == [True]
    assert probe["reply_to_inbound_off"] is None
    assert probe["reply_to_inbound_on"] == [201, probe["expected_reply_to"]]


def test_the_webhook_needs_its_switch_secret_and_a_valid_signature(probe: Probe) -> None:
    assert probe["no_secret"] == 404
    assert probe["switched_off"] == 404
    assert probe["signatures"] == [401, 401, 401, 0]
    assert probe["malformed_event"] == 400


def test_each_received_email_is_recorded_once_before_processing(probe: Probe) -> None:
    assert probe["recorded"] == [204, 204, 204, 1]
    assert probe["other_type"] == [204, 1]
    after = probe["after_webhook"]
    assert (after["status"], after["attempts"], after["workspace_id"]) == ("received", 0, None)


def _state(probe: Probe, key: str) -> tuple[Any, ...]:
    row = probe["rows"][key]
    return row["status"], row["reason"], row["last_error"], row["waiting"]


def test_mail_from_the_contact_joins_its_thread_and_reopens_it(probe: Probe) -> None:
    assert _state(probe, "re_1") == ("routed", None, None, False)
    assert probe["reopened"] == "open"
    inbound = [m for m in probe["messages"] if m["kind"] == "inbound"]
    assert [m["body"] for m in inbound] == ["Thanks, got it.", "See attached."]
    assert all(m["from_contact"] for m in inbound)


def test_suspicious_mail_is_quarantined_for_review(probe: Probe) -> None:
    assert _state(probe, "re_2")[0] == "quarantined"
    assert _state(probe, "re_8")[0] == "quarantined"
    assert probe["reviews"] == ["dmarc_failed", "sender_mismatch"]
    # HTML reduced to its text; script and style dropped.
    assert probe["review_text"] == "Hello there"


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("re_3", "unknown_routing_address"),
        ("re_4", "no_routing_address"),
        ("re_7", "malformed_sender"),
        ("re_10", "conversation_gone"),
        ("re_11", "several_routing_addresses"),
    ],
)
def test_mail_that_matches_no_thread_is_kept_unmatched(probe: Probe, key: str, reason: str) -> None:
    status, found, _, _ = _state(probe, key)
    assert (status, found) == ("unmatched", reason)
    assert probe["rows"][key]["workspace_id"] is None


def test_fetch_failures_wait_or_fail_never_vanish(probe: Probe) -> None:
    assert _state(probe, "re_5") == ("received", None, "rate_limited", True)
    assert _state(probe, "re_6") == ("failed", None, "not_found", False)


def test_attachments_are_listed_never_fetched(probe: Probe) -> None:
    listed = [a for a in probe["api_attachments"] if a]
    assert listed == [
        [
            {
                "filename": ".._.._etc_passwd.exe",
                "content_type": "application/x-msdownload",
                "size": 4096,
                "stored": False,
            }
        ]
    ]


def test_an_email_is_added_once_despite_retries_and_parallel_workers(probe: Probe) -> None:
    assert probe["redelivered_count"] == 1
    assert probe["parallel"] == ["Parallel 13", "Parallel 14", "Parallel 15", "Parallel 16"]
    assert len(probe["parallel_fetches"]) == 4


def test_reviews_are_for_repliers_versioned_and_decided_once(probe: Probe) -> None:
    # reader, other workspace's owner, outsider, the other workspace's own list
    assert probe["review_access"] == [403, 404, 404, 0]
    # no If-Match, stale, reader, other workspace, accepted, decided already
    assert probe["accept"] == [428, 409, 403, 404, 200, 409]
    assert probe["discard"] == "discarded"
    assert probe["after_review"] == [1, False]
    assert probe["pending_after"] == 0


def test_mail_routed_to_another_workspace_stays_there(probe: Probe) -> None:
    assert _state(probe, "re_9")[0] == "routed"
    assert probe["b_messages"] == ["Here is your quote.", "Thanks, got it."]
    assert probe["rows"]["re_9"]["workspace_id"] != probe["rows"]["re_1"]["workspace_id"]


def test_production_receives_and_processes_nothing(probe: Probe) -> None:
    assert probe["production"] == [404, {}]


def test_the_processor_audits_each_added_message_and_held_email_once(probe: Probe) -> None:
    audit, rows = probe["inbound_audit"], probe["inbound_rows"]
    assert rows["crm_app.conversation.inbound_received"] >= 1
    assert rows["crm_app.conversation.inbound_quarantined"] >= 1
    assert {action: count for action, (count, _) in audit.items()} == rows
    assert all(no_member for _, no_member in audit.values())
