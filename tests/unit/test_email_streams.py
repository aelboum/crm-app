"""Email streams and routing addresses (decision P6-S, `crm_app.domains.email_streams`)."""

from __future__ import annotations

import pytest

from crm_app.domains import email_streams as streams
from crm_app.domains.emails import PURPOSES
from crm_app.domains.records import InvalidValue

TOKEN = "a1b2c3d4e5f6a7b8c9d0e1f2"


def test_every_email_purpose_belongs_to_exactly_one_stream() -> None:
    assert set(streams.PURPOSE_STREAMS) == set(PURPOSES)
    assert streams.stream_of("conversation_reply") is streams.Stream.CONVERSATION
    assert streams.stream_of("booking_confirmation") is streams.Stream.TRANSACTIONAL
    with pytest.raises(KeyError):
        streams.stream_of("newsletter")


def test_streams_use_separate_subdomains() -> None:
    domains = {streams.stream_domain(s, "example.com") for s in streams.Stream}
    assert domains == {"notify.example.com", "mail.example.com", "campaigns.example.com"}
    assert streams.inbound_domain("example.com") == "inbound.example.com"
    assert streams.inbound_domain("example.com") not in domains


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost",
        "example",
        "exa mple.com",
        "-bad.com",
        "bad-.com",
        "a..com",
        "1.2.3.4",
        "example.com.",
        "ex_ample.com",
        "münchen.de",
        "x" * 64 + ".com",
        ("a." * 101) + "com",
    ],
)
def test_a_parent_domain_must_be_a_plain_domain_name(value: str) -> None:
    with pytest.raises(InvalidValue):
        streams.parent_domain(value)


def test_a_parent_domain_is_lowercased_and_accepts_punycode() -> None:
    assert streams.parent_domain(" Example.COM ") == "example.com"
    assert streams.parent_domain("xn--mnchen-3ya.de") == "xn--mnchen-3ya.de"


@pytest.mark.parametrize("value", ["", "a+b", "a b", "a@b", ".a", "a.", "a..b", "x" * 65, "ä"])
def test_a_local_part_has_no_plus_or_unsafe_characters(value: str) -> None:
    with pytest.raises(InvalidValue):
        streams.local_part(value)


def test_a_sender_is_a_bare_address_on_its_stream_subdomain() -> None:
    assert streams.sender(streams.Stream.CAMPAIGN, "example.com") == "news@campaigns.example.com"
    assert (
        streams.sender(streams.Stream.CONVERSATION, "example.com", local="Support")
        == "support@mail.example.com"
    )


def test_routing_addresses_round_trip_only_on_the_inbound_domain() -> None:
    address = streams.reply_address(TOKEN, "example.com")
    assert address == f"reply+{TOKEN}@inbound.example.com"
    assert streams.routing_token(address.upper(), "example.com") == TOKEN
    for other in (
        f"reply+{TOKEN}@mail.example.com",
        f"reply+{TOKEN}@inbound.example.com.evil.test",
        f"reply+{TOKEN}@inbound.other.com",
        f"noreply+{TOKEN}@inbound.example.com",
        "reply@inbound.example.com",
        "reply+short@inbound.example.com",
        f"reply+{TOKEN}!@inbound.example.com",
        f"Ada <reply+{TOKEN}@inbound.example.com>",
    ):
        assert streams.routing_token(other, "example.com") is None, other
    with pytest.raises(ValueError, match="routing token"):
        streams.reply_address("UPPER-case", "example.com")
