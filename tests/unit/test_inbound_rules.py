"""Inbound email rules (decision P6-I, `crm_app.domains.inbound`)."""

from __future__ import annotations

import pytest

from crm_app.domains import inbound as rules

PARENT = "example.test"
# Made-up routing tokens for tests only.
TOKEN = "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
OTHER = "fedcba9876543210fedcba9876543210"  # pragma: allowlist secret


def _answer(**extra: object) -> dict[str, object]:
    return {
        "from": "Ada Lovelace <Ada@Example.test>",
        "to": [f"reply+{TOKEN}@inbound.{PARENT}"],
        "subject": "Re: quote",
        "text": "Hello",
        **extra,
    }


def test_only_received_events_are_taken_and_must_name_an_email() -> None:
    event = rules.received_event(
        {
            "type": "email.received",
            "created_at": "2026-11-01T10:00:00Z",
            "data": {"email_id": "e-1"},
        }
    )
    assert event is not None
    assert event.email_id == "e-1"
    assert rules.received_event({"type": "email.delivered", "data": {}}) is None
    assert rules.received_event("not an object") is None
    for data in ({}, {"email_id": ""}, {"email_id": "a b"}, {"email_id": 5}, None):
        with pytest.raises(rules.InboundRejected):
            rules.received_event(
                {"type": "email.received", "created_at": "2026-11-01", "data": data}
            )


def test_content_keeps_the_bare_sender_and_every_recipient() -> None:
    content = rules.received_content(
        _answer(received_for=["Team <TEAM@inbound.example.test>"], authentication={"dmarc": "pass"})
    )
    assert content.sender == "ada@example.test"
    assert content.recipients == (f"reply+{TOKEN}@inbound.{PARENT}", "team@inbound.example.test")
    assert content.dmarc == "pass"


@pytest.mark.parametrize(
    "answer",
    [
        "text",
        {"to": []},
        {"from": "not an address", "to": []},
        {"from": "a@b.c", "to": "x@y.z"},
        {"from": "a@b.c", "to": [5]},
        {"from": "a@b.c", "to": [], "attachments": "x"},
        {"from": "a@b.c\r\nBcc: x@y.z", "to": []},
    ],
)
def test_malformed_answers_are_refused(answer: object) -> None:
    with pytest.raises(rules.InboundRejected):
        rules.received_content(answer)


def test_html_is_reduced_to_text_without_scripts_or_styles() -> None:
    html = (
        "<html><head><title>T</title><style>p{color:red}</style></head><body>"
        "<p>Hello&nbsp;<b>there</b></p><script>steal()</script>"
        '<a href="https://evil.test">click</a><div>Line two</div></body></html>'
    )
    text, truncated = rules.plain_text(None, html)
    assert text == "Hello there\nclick\nLine two"
    assert "steal" not in text
    assert "evil.test" not in text
    assert truncated is False


def test_text_is_preferred_cleaned_and_bounded() -> None:
    text, truncated = rules.plain_text("Hi\x00 there\r\n\r\n\r\n\r\nBye\t!", "<p>ignored</p>")
    assert text == "Hi there\n\nBye !"
    assert truncated is False
    long, cut = rules.plain_text("x" * (rules.BODY_MAX + 10), None)
    assert len(long) == rules.BODY_MAX
    assert cut is True
    assert rules.plain_text(None, None) == ("", False)


def test_attachments_are_described_with_safe_names_only() -> None:
    content = rules.received_content(
        _answer(
            attachments=[
                {"filename": "../../etc/passwd", "content_type": "Text/Plain", "size": 10},
                {"filename": "<script>.js", "content_type": "bad type", "size": -1},
                {"content_type": None},
            ]
        )
    )
    assert content.attachments == (
        rules.Attachment(".._.._etc_passwd", "text/plain", 10),
        rules.Attachment("_script_.js", "application/octet-stream", None),
        rules.Attachment("attachment", "application/octet-stream", None),
    )


def test_routing_trusts_only_this_deployments_routing_addresses() -> None:
    route = rules.decide(rules.received_content(_answer()), PARENT)
    assert route == rules.Decision("route", token=TOKEN)
    cases = {
        "no_routing_address": ["info@example.test", f"reply+{TOKEN}@inbound.other.test"],
        "several_routing_addresses": [
            f"reply+{TOKEN}@inbound.{PARENT}",
            f"reply+{OTHER}@inbound.{PARENT}",
        ],
    }
    for reason, to in cases.items():
        decision = rules.decide(rules.received_content(_answer(to=to)), PARENT)
        assert decision == rules.Decision("unmatched", reason), reason


def test_a_routed_email_needs_review_unless_it_is_clean_mail_from_the_contact() -> None:
    clean = rules.received_content(_answer(authentication={"dmarc": "pass"}))
    assert rules.review_reason(clean, "ADA@example.test") is None
    assert rules.review_reason(clean, "grace@example.test") == "sender_mismatch"
    assert rules.review_reason(clean, None) == "no_contact"
    failed = rules.received_content(_answer(authentication={"dmarc": "fail"}))
    assert rules.review_reason(failed, "ada@example.test") == "dmarc_failed"
    empty = rules.received_content(_answer(text="   "))
    assert rules.review_reason(empty, "ada@example.test") == "empty_body"


def test_tokens_are_random_and_only_their_hash_is_shared() -> None:
    first, second = rules.new_token(), rules.new_token()
    assert first != second
    assert len(first) == 32
    assert len(rules.token_hash(first)) == 64
    assert rules.token_hash(first) != first
