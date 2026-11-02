"""Transactional email rules (decision P6-E, `crm_app.domains.emails`)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from crm_app.domains import emails as rules
from crm_app.domains.records import InvalidValue

# A made-up webhook key for tests only.
KEY = b"0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
SECRET = "whsec_" + base64.b64encode(KEY).decode()  # pragma: allowlist secret
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _sign(event_id: str, timestamp: str, body: bytes, key: bytes = KEY) -> str:
    digest = hmac.new(key, f"{event_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def test_content_is_normalised_or_refused_by_rule() -> None:
    made = rules.content(" Ada@Example.TEST ", "  Your booking ", "Line one\r\nLine two\n")
    assert made == rules.Content("ada@example.test", "Your booking", "Line one\nLine two")
    for to, subject, body in (
        ("not-an-email", "S", "B"),
        ("a@example.test", "", "B"),
        ("a@example.test", "two\nlines", "B"),
        ("a@example.test", "x" * 201, "B"),
        ("a@example.test", "S", ""),
        ("a@example.test", "S", "bell\x07"),
    ):
        with pytest.raises(InvalidValue):
            rules.content(to, subject, body)


def test_the_message_id_is_stable_and_names_the_senders_domain() -> None:
    assert rules.message_id("e1", "LeadStack <hello@Mail.Example.test>") == "<e1@mail.example.test>"
    assert rules.message_id("e1", "hello@x.test") == rules.message_id("e1", "other@x.test")


def test_events_move_a_status_forward_only() -> None:
    assert rules.after_event("sent", "delivered") == "delivered"
    assert rules.after_event("delivered", "delivery_delayed") == "delivered"
    assert rules.after_event("delivered", "bounced") == "bounced"
    assert rules.after_event("delivered", "complained") == "complained"
    assert rules.after_event("complained", "delivered") == "complained"
    # Not sent by us as far as we know: an event never invents a status.
    assert rules.after_event("queued", "delivered") == "queued"
    assert rules.after_event("failed", "delivered") == "failed"
    # A provider's own failure or suppression after acceptance is a rejection.
    assert rules.after_event("sent", "failed") == "rejected"
    assert rules.after_event("sent", "suppressed") == "rejected"
    assert rules.after_event("rejected", "delivered") == "rejected"
    assert "rejected" in rules.FINAL


def test_retries_back_off_exponentially_with_bounded_jitter() -> None:
    assert rules.retry_delay(1, None, 0.0) == 30
    assert rules.retry_delay(2, None, 0.0) == 60
    assert rules.retry_delay(3, None, 0.5) == 120 * 1.125
    assert rules.retry_delay(50, None, 0.0) == rules.BACKOFF_MAX_SECONDS
    assert rules.retry_delay(1, None, 0.99) < 30 * 1.25


def test_a_retry_is_never_sooner_than_the_providers_retry_after() -> None:
    assert rules.retry_delay(1, 600, 0.0) == 600
    assert rules.retry_delay(1, 5, 0.0) == 30
    assert rules.retry_delay(1, float("inf"), 0.0) == rules.BACKOFF_MAX_SECONDS
    assert rules.retry_delay(1, 10**9, 0.0) == rules.BACKOFF_MAX_SECONDS


def test_a_valid_recent_signature_is_accepted() -> None:
    body = b'{"type":"email.delivered"}'
    stamp = str(int(NOW.timestamp()))
    signature = _sign("msg_1", stamp, body)
    assert rules.signature_valid(SECRET, "msg_1", stamp, signature, body, NOW)
    # Several signatures (a rotated secret): one valid is enough.
    assert rules.signature_valid(SECRET, "msg_1", stamp, f"v1,bm90 {signature}", body, NOW)


@pytest.mark.parametrize(
    "case",
    [
        "tampered",
        "wrong_secret",
        "old",
        "future",
        "no_signature",
        "v2_only",
        "bad_id",
        "bad_secret",
        "unicode_digit",
        "huge_stamp",
    ],
)
def test_anything_else_is_refused(case: str) -> None:
    body = b'{"type":"email.delivered"}'
    event_id, secret = "msg_1", SECRET
    stamp = str(int(NOW.timestamp()))
    signature = _sign(event_id, stamp, body)
    if case == "tampered":
        body = b'{"type":"email.bounced"}'
    elif case == "wrong_secret":
        signature = _sign(event_id, stamp, body, key=b"another key of thirty-two bytes!")
    elif case == "old":
        stamp = str(int((NOW - timedelta(minutes=6)).timestamp()))
        signature = _sign(event_id, stamp, body)
    elif case == "future":
        stamp = str(int((NOW + timedelta(minutes=6)).timestamp()))
        signature = _sign(event_id, stamp, body)
    elif case == "no_signature":
        signature = ""
    elif case == "v2_only":
        signature = signature.replace("v1,", "v2,")
    elif case == "bad_id":
        event_id = "msg 1; drop"
    elif case == "bad_secret":
        secret = "whsec_not base64!"  # pragma: allowlist secret
    elif case == "unicode_digit":
        # str.isdigit() accepts it and int() then raised (13-H3).
        stamp = "²"
    elif case == "huge_stamp":
        stamp = "9" * 5000
    assert not rules.signature_valid(secret, event_id, stamp, signature, body, NOW)


def test_provider_events_are_reduced_to_what_is_kept() -> None:
    payload = {
        "type": "email.bounced",
        "created_at": "2026-11-01T11:59:00.000Z",
        "data": {"email_id": "4ef9a417-02e9-4d39-ad75-9611e0fcc33c", "to": ["ada@example.test"]},
    }
    event = rules.provider_event("msg_1", json.loads(json.dumps(payload)))
    assert event == rules.ProviderEvent(
        provider_event_id="msg_1",
        provider_message_id="4ef9a417-02e9-4d39-ad75-9611e0fcc33c",
        type="bounced",
        occurred_at=datetime(2026, 11, 1, 11, 59, tzinfo=UTC),
    )
    for ignored in (
        {**payload, "type": "email.opened"},
        {**payload, "data": {"email_id": "bad id!"}},
        {**payload, "data": None},
        {**payload, "created_at": "yesterday"},
        ["not", "an", "object"],
    ):
        assert rules.provider_event("msg_1", ignored) is None
