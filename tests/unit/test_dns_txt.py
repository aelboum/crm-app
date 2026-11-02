"""The DNS wire format and the DNS-over-HTTPS TXT resolver (decision 12D.2).

No network: replies are built here, and the resolver runs in a fresh
interpreter against a test egress client.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from crm_app.domains import dns_wire
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

NAME = "_leadstack-challenge.book.acme.nl"


def _encoded(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def _reply(
    query_id: int,
    records: list[tuple[bytes, int, bytes]],
    *,
    rcode: int = 0,
    flags: int = 0x8180,
    questions: int = 1,
) -> bytes:
    header = struct.pack(">HHHHHH", query_id, flags | rcode, questions, len(records), 0, 0)
    question = _encoded(NAME) + struct.pack(">HH", 16, 1) if questions else b""
    body = b""
    for owner, kind, rdata in records:
        body += owner + struct.pack(">HHIH", kind, 1, 300, len(rdata)) + rdata
    return header + question + body


def _txt(*parts: bytes) -> bytes:
    return b"".join(bytes([len(p)]) + p for p in parts)


POINTER = b"\xc0\x0c"  # the question's name


def test_the_query_is_a_recursive_txt_question() -> None:
    query = dns_wire.txt_query(NAME + ".", 0x1234)
    assert query[:12] == struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    assert query[12:] == _encoded(NAME) + struct.pack(">HH", 16, 1)
    for bad in ("", "a" * 64 + ".nl", "münchen.de", "x." * 130):
        with pytest.raises(dns_wire.DnsAnswerError):
            dns_wire.txt_query(bad, 1)


def test_txt_values_are_read_joined_and_only_for_the_asked_name() -> None:
    reply = _reply(
        7,
        [
            (POINTER, 16, _txt(b"leadstack-verification=abc", b"def")),
            (_encoded("other.example.org"), 16, _txt(b"not-ours")),
            (POINTER, 1, b"\x01\x02\x03\x04"),
        ],
    )
    assert dns_wire.txt_answer(reply, 7, NAME) == ["leadstack-verification=abcdef"]


def test_a_cname_is_followed_to_its_txt_records() -> None:
    target = _encoded("verify.provider.example.org")
    reply = _reply(9, [(POINTER, 5, target), (target, 16, _txt(b"token"))])
    assert dns_wire.txt_answer(reply, 9, NAME) == ["token"]


def test_no_such_name_is_an_empty_answer() -> None:
    assert dns_wire.txt_answer(_reply(3, [], rcode=3), 3, NAME) == []


@pytest.mark.parametrize(
    "reply",
    [
        b"\x00\x07",
        _reply(8, []),  # another query's id
        _reply(7, [], flags=0x0100),  # not a reply
        _reply(7, [], flags=0x8380),  # truncated
        _reply(7, [], rcode=2),  # server failure
        _reply(7, [(b"\xc0\x30", 16, b"")]),  # pointer past the end
        _reply(7, [(b"\xc0\x0c", 16, b"\x05ab")]),  # string longer than its record
    ],
)
def test_unusable_replies_are_refused(reply: bytes) -> None:
    with pytest.raises(dns_wire.DnsAnswerError):
        dns_wire.txt_answer(reply, 7, NAME)


def test_a_compression_loop_is_refused() -> None:
    header = struct.pack(">HHHHHH", 7, 0x8180, 0, 1, 0, 0)
    looping = header + b"\xc0\x0c" + struct.pack(">HHIH", 16, 1, 1, 0)
    with pytest.raises(dns_wire.DnsAnswerError):
        dns_wire.txt_answer(looping, 7, NAME)


_RESOLVER_PROBE = """
import json, os
from dataclasses import dataclass
from crm_app import custom_domains
from crm_app.domains import dns_wire

@dataclass
class Response:
    status_code: int
    body: bytes

class Client:
    def __init__(self, status, reply):
        self.calls, self.status, self.reply = [], status, reply
    async def post(self, url, *, headers, content, deadline):
        self.calls.append([url, headers["Content-Type"], len(content)])
        query_id = int.from_bytes(content[:2], "big")
        return Response(self.status, self.reply(query_id))

def good(query_id):
    head = query_id.to_bytes(2, "big") + bytes.fromhex("8180")
    head += (1).to_bytes(2, "big") * 2 + bytes(4)
    question = dns_wire.txt_query("_leadstack-challenge.book.acme.nl", 0)[12:]
    rdata = bytes([5]) + b"token"
    answer = bytes.fromhex("c00c") + (16).to_bytes(2, "big") + (1).to_bytes(2, "big")
    answer += (60).to_bytes(4, "big") + len(rdata).to_bytes(2, "big") + rdata
    return head + question + answer

out = {}
client = Client(200, good)
resolver = custom_domains.DohTxtResolver("https://dns.example.org/dns-query", client=client)
out["values"] = resolver.txt("_leadstack-challenge.book.acme.nl")
out["call"] = client.calls[0][:2]
errors = []
for status, reply in ((503, good), (200, lambda q: b"junk")):
    try:
        custom_domains.DohTxtResolver("https://x", client=Client(status, reply)).txt("a.nl")
    except custom_domains.ResolverError as exc:
        errors.append(exc.code)
out["errors"] = errors
configured = []
for value in ("", "http://dns.example.org/dns-query", "https://dns.example.org/dns-query"):
    os.environ[custom_domains.DOH_URL_SETTING] = value
    configured.append(type(custom_domains.configured_resolver()).__name__)
out["configured"] = configured
print(json.dumps(out))
"""


def test_the_resolver_posts_a_dns_message_and_is_off_unless_configured(
    tmp_path: Path,
) -> None:
    result = run_python(_RESOLVER_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["values"] == ["token"]
    assert out["call"] == ["https://dns.example.org/dns-query", "application/dns-message"]
    assert out["errors"] == ["resolver_refused", "bad_answer"]
    assert out["configured"] == ["NoneType", "NoneType", "DohTxtResolver"]
