"""The DNS wire format for one TXT lookup (RFC 1035; decision 12D.2): pure
functions, no network.

`txt_query` builds the query a DNS-over-HTTPS resolver receives (RFC 8484,
`application/dns-message`); `txt_answer` reads the reply defensively: every
length is bounds-checked, compression pointers may not loop, and only TXT
records of the asked name (or of a name it is a CNAME of) count.
"""

from __future__ import annotations

import struct

TYPE_TXT = 16
TYPE_CNAME = 5
CLASS_IN = 1
_RCODE_NXDOMAIN = 3
MAX_RECORDS = 50
_MAX_JUMPS = 20


class DnsAnswerError(ValueError):
    """A reply that cannot be used; the message is a short fixed reason."""


def _labels(name: str) -> list[bytes]:
    text = name.strip().rstrip(".").lower()
    if not text or len(text) > 253 or not text.isascii():
        raise DnsAnswerError("bad_name")
    labels = [label.encode("ascii") for label in text.split(".")]
    if any(not 1 <= len(label) <= 63 for label in labels):
        raise DnsAnswerError("bad_name")
    return labels


def txt_query(name: str, query_id: int) -> bytes:
    """A recursive TXT query for `name` with the given id."""
    header = struct.pack(">HHHHHH", query_id & 0xFFFF, 0x0100, 1, 0, 0, 0)
    question = b"".join(bytes([len(label)]) + label for label in _labels(name))
    return header + question + b"\x00" + struct.pack(">HH", TYPE_TXT, CLASS_IN)


def _name(message: bytes, offset: int) -> tuple[str, int]:
    """The name at `offset` and the offset after it (in place)."""
    labels: list[str] = []
    jumps, end = 0, None
    while True:
        if offset >= len(message):
            raise DnsAnswerError("truncated")
        length = message[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(message):
                raise DnsAnswerError("truncated")
            jumps += 1
            if jumps > _MAX_JUMPS:
                raise DnsAnswerError("pointer_loop")
            if end is None:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | message[offset + 1]
            continue
        if length & 0xC0:
            raise DnsAnswerError("bad_label")
        offset += 1
        if length == 0:
            break
        if offset + length > len(message):
            raise DnsAnswerError("truncated")
        labels.append(message[offset : offset + length].decode("ascii", "replace").lower())
        offset += length
    return ".".join(labels), (end if end is not None else offset)


def _strings(rdata: bytes) -> str:
    """A TXT record's character-strings, joined (long values are split)."""
    parts: list[bytes] = []
    offset = 0
    while offset < len(rdata):
        length = rdata[offset]
        offset += 1
        if offset + length > len(rdata):
            raise DnsAnswerError("truncated")
        parts.append(rdata[offset : offset + length])
        offset += length
    return b"".join(parts).decode("ascii", "replace")


def txt_answer(message: bytes, query_id: int, name: str) -> list[str]:  # noqa: PLR0912 - one check per field
    """The TXT values for `name` in a reply to query `query_id`; empty when
    the name does not exist or has none. `DnsAnswerError` otherwise."""
    if len(message) < 12:
        raise DnsAnswerError("truncated")
    reply_id, flags, questions, answers, _, _ = struct.unpack(">HHHHHH", message[:12])
    if reply_id != query_id & 0xFFFF or not flags & 0x8000:
        raise DnsAnswerError("not_our_reply")
    if flags & 0x0200:
        raise DnsAnswerError("truncated")
    rcode = flags & 0x000F
    if rcode == _RCODE_NXDOMAIN:
        return []
    if rcode != 0:
        raise DnsAnswerError("server_failure")
    if answers > MAX_RECORDS:
        raise DnsAnswerError("too_many_records")
    offset = 12
    for _ in range(questions):
        _, offset = _name(message, offset)
        offset += 4
    wanted = {".".join(label.decode() for label in _labels(name))}
    values: list[str] = []
    records: list[tuple[str, int, bytes]] = []
    for _ in range(answers):
        owner, offset = _name(message, offset)
        if offset + 10 > len(message):
            raise DnsAnswerError("truncated")
        kind, klass, _ttl, length = struct.unpack(">HHIH", message[offset : offset + 10])
        offset += 10
        if offset + length > len(message):
            raise DnsAnswerError("truncated")
        rdata_offset = offset
        offset += length
        if klass != CLASS_IN:
            continue
        if kind == TYPE_CNAME:
            target, _ = _name(message, rdata_offset)
            records.append((owner, kind, target.encode("ascii", "replace")))
        elif kind == TYPE_TXT:
            records.append((owner, kind, message[rdata_offset:offset]))
    # Follow CNAMEs from the asked name (resolvers list them before the data).
    for owner, kind, data in records:
        if kind == TYPE_CNAME and owner in wanted:
            wanted.add(data.decode("ascii", "replace"))
    for owner, kind, data in records:
        if kind == TYPE_TXT and owner in wanted:
            values.append(_strings(data))
    return values
