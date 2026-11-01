"""Inbound email rules (decision P6-I): pure, no database, network or
framework.

- `received_event` validates Resend's `email.received` webhook body, which
  carries metadata only (no body, headers or attachment content).
- `received_content` validates the receiving API's answer for one email
  (`GET /emails/receiving/{id}`).
- `plain_text` turns the email into plain text: the text part when there is
  one, otherwise the HTML reduced to its text (never rendered; scripts,
  styles and markup dropped), control characters removed, bounded.
- `decide` routes an email using only this deployment's routing addresses
  and server-side data: the workspace and conversation come from the
  routing token, never from anything else in the email.
- Attachments are described (name, type, size) and never fetched: no
  malware scanner is approved yet.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr
from html import unescape
from html.parser import HTMLParser

from crm_app.domains import email_streams as streams

BODY_MAX = 20_000
SUBJECT_MAX = 200
ADDRESSES_MAX = 50
ATTACHMENTS_MAX = 50
FILENAME_MAX = 120
EVENT_TYPE = "email.received"

_EMAIL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_ADDRESS = re.compile(r"[^\s@<>\"(),;:\\]+@[a-z0-9.-]+\.[a-z0-9-]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SUBJECT_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FILENAME_UNSAFE = re.compile(r"[^\w .()+-]")
_CONTENT_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]{1,64}/[a-z0-9!#$&^_.+-]{1,64}")
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}
)
_SKIPPED_TAGS = frozenset({"script", "style", "head", "title", "noscript", "template"})


class InboundRejected(ValueError):
    """A body or an answer this product will not process; `code` says why."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReceivedEvent:
    email_id: str
    occurred_at: datetime


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    size: int | None


@dataclass(frozen=True)
class ReceivedContent:
    sender: str
    recipients: tuple[str, ...]
    subject: str
    text: str
    truncated: bool
    attachments: tuple[Attachment, ...]
    dmarc: str


@dataclass(frozen=True)
class Decision:
    """`route` (with a token), or `quarantine` / `unmatched` with a reason.
    `unmatched` mail names no workspace and is reviewed by an operator;
    `quarantine` mail names one and is reviewed by its members."""

    outcome: str
    reason: str | None = None
    token: str | None = None


def new_token() -> str:
    """A routing token: 128 random bits, lower-case hex."""
    return secrets.token_hex(16)


def token_hash(token: str) -> str:
    """How a token is looked up across workspaces (the token itself stays in
    the workspace's own row)."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def bare_address(value: object) -> str | None:
    """`a@b.c` from `a@b.c` or `Name <a@b.c>`, lower-cased, or None."""
    if not isinstance(value, str) or len(value) > 512 or _CONTROL.search(value):
        return None
    address = parseaddr(value)[1].strip().lower()
    return address if _ADDRESS.fullmatch(address) else None


def _addresses(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > ADDRESSES_MAX:
        raise InboundRejected("malformed_recipients")
    found: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise InboundRejected("malformed_recipients")
        for _, raw in getaddresses([item]):
            address = bare_address(raw)
            if address and address not in found:
                found.append(address)
    return tuple(found)


def _timestamp(value: object) -> datetime:
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        raise InboundRejected("malformed_time") from None
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(UTC)


def received_event(payload: object) -> ReceivedEvent | None:
    """The received email a verified webhook body names; None for another
    event type (acknowledged and ignored); `InboundRejected` for a body of
    the right type that is malformed."""
    if not isinstance(payload, dict) or payload.get("type") != EVENT_TYPE:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        raise InboundRejected("malformed_event")
    email_id = data.get("email_id")
    if not isinstance(email_id, str) or not _EMAIL_ID.fullmatch(email_id):
        raise InboundRejected("malformed_event")
    return ReceivedEvent(email_id=email_id, occurred_at=_timestamp(payload.get("created_at")))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skipping += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS and self._skipping:
            self._skipping -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_text(html: str) -> str:
    """The visible text of an HTML body; links keep their text only."""
    parser = _TextExtractor()
    parser.feed(html[: BODY_MAX * 10])
    parser.close()
    return unescape("".join(parser.parts))


def plain_text(text: object, html: object) -> tuple[str, bool]:
    """The message as bounded plain text, and whether it was cut."""
    if isinstance(text, str) and text.strip():
        raw = text
    elif isinstance(html, str) and html.strip():
        raw = html_text(html)
    else:
        raw = ""
    lines = [
        " ".join(_CONTROL.sub(" ", line).replace("\t", " ").split())
        for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(body) > BODY_MAX:
        return body[:BODY_MAX].rstrip(), True
    return body, False


def _subject(value: object) -> str:
    subject = " ".join(_SUBJECT_CONTROL.sub(" ", value).split()) if isinstance(value, str) else ""
    return (subject or "(no subject)")[:SUBJECT_MAX]


def _attachments(value: object) -> tuple[Attachment, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InboundRejected("malformed_attachments")
    found: list[Attachment] = []
    for item in value[:ATTACHMENTS_MAX]:
        if not isinstance(item, dict):
            raise InboundRejected("malformed_attachments")
        name = item.get("filename")
        filename = _FILENAME_UNSAFE.sub("_", name)[:FILENAME_MAX] if isinstance(name, str) else ""
        kind = item.get("content_type")
        content_type = (
            kind.lower() if isinstance(kind, str) and _CONTENT_TYPE.fullmatch(kind.lower()) else ""
        )
        size = item.get("size")
        found.append(
            Attachment(
                filename=filename or "attachment",
                content_type=content_type or "application/octet-stream",
                size=size if isinstance(size, int) and size >= 0 else None,
            )
        )
    return tuple(found)


def received_content(answer: object) -> ReceivedContent:
    """The parts of a received email this product keeps, or
    `InboundRejected` for an answer it cannot trust."""
    if not isinstance(answer, dict):
        raise InboundRejected("malformed_content")
    sender = bare_address(answer.get("from"))
    if sender is None:
        raise InboundRejected("malformed_sender")
    recipients = _addresses(answer.get("to") or [])
    received_for = answer.get("received_for")
    if received_for is not None:
        recipients = tuple(dict.fromkeys((*recipients, *_addresses(received_for))))
    text, truncated = plain_text(answer.get("text"), answer.get("html"))
    authentication = answer.get("authentication")
    dmarc = authentication.get("dmarc") if isinstance(authentication, dict) else None
    return ReceivedContent(
        sender=sender,
        recipients=recipients,
        subject=_subject(answer.get("subject")),
        text=text,
        truncated=truncated,
        attachments=_attachments(answer.get("attachments")),
        dmarc=dmarc if isinstance(dmarc, str) and dmarc.isascii() else "unknown",
    )


def routing_tokens(recipients: tuple[str, ...], parent: str) -> tuple[str, ...]:
    found: list[str] = []
    for address in recipients:
        token = streams.routing_token(address, parent)
        if token and token not in found:
            found.append(token)
    return tuple(found)


def decide(content: ReceivedContent, parent: str) -> Decision:
    """Which conversation, by routing token only; or why not."""
    match routing_tokens(content.recipients, parent):
        case ():
            return Decision("unmatched", "no_routing_address")
        case (token,):
            return Decision("route", token=token)
        case _:
            return Decision("unmatched", "several_routing_addresses")


def review_reason(content: ReceivedContent, contact_email: str | None) -> str | None:
    """Why a routed email needs a member's review before it joins the
    thread, or None: DMARC failed, the sender is not the conversation's
    contact, the thread has no contact, or there is no text."""
    if content.dmarc == "fail":
        return "dmarc_failed"
    if contact_email is None:
        return "no_contact"
    if content.sender != contact_email.strip().lower():
        return "sender_mismatch"
    if not content.text:
        return "empty_body"
    return None
