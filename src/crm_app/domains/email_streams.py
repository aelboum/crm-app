"""Email streams and sender identities (decision P6-S): pure, no database or
framework.

LeadStack sends three logically separate streams, each from its own
subdomain of one configurable parent domain, so the reputation of one never
carries the others (owner decision, 2026-11-01):

- `transactional`: `notify.<EMAIL_PARENT_DOMAIN>`, confirmations and
  account messages;
- `conversation`: `mail.<EMAIL_PARENT_DOMAIN>`, one-to-one replies from the
  Inbox;
- `campaign`: `campaigns.<EMAIL_PARENT_DOMAIN>`, approved marketing
  campaigns.

Inbound mail is received on `inbound.<EMAIL_PARENT_DOMAIN>`. The parent
domain is configuration only: no domain is assumed to exist, be owned or be
verified, and nothing here talks to DNS or to Resend.

Every email purpose belongs to exactly one stream (`stream_of`); a purpose
that is not listed has no stream and cannot be sent, so marketing content
can never travel as a transactional message.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum

from crm_app.domains.records import InvalidValue


class Stream(StrEnum):
    TRANSACTIONAL = "transactional"
    CONVERSATION = "conversation"
    CAMPAIGN = "campaign"


SUBDOMAINS: Mapping[Stream, str] = {
    Stream.TRANSACTIONAL: "notify",
    Stream.CONVERSATION: "mail",
    Stream.CAMPAIGN: "campaigns",
}
INBOUND_SUBDOMAIN = "inbound"

# Which stream each email purpose (`crm_app.domains.emails.PURPOSES`) uses.
PURPOSE_STREAMS: Mapping[str, Stream] = {
    "booking_confirmation": Stream.TRANSACTIONAL,
    "test": Stream.TRANSACTIONAL,
    "conversation_reply": Stream.CONVERSATION,
    "campaign": Stream.CAMPAIGN,
}

# The local part each stream sends from unless configured otherwise.
DEFAULT_LOCAL_PARTS: Mapping[Stream, str] = {
    Stream.TRANSACTIONAL: "no-reply",
    Stream.CONVERSATION: "team",
    Stream.CAMPAIGN: "news",
}

# Sends per minute, per workspace and across all workspaces, unless
# configured otherwise. Conservative on purpose: a new sending domain's
# reputation is built slowly.
DEFAULT_WORKSPACE_PER_MINUTE: Mapping[Stream, int] = {
    Stream.TRANSACTIONAL: 60,
    Stream.CONVERSATION: 30,
    Stream.CAMPAIGN: 20,
}
DEFAULT_GLOBAL_PER_MINUTE: Mapping[Stream, int] = {
    Stream.TRANSACTIONAL: 120,
    Stream.CONVERSATION: 60,
    Stream.CAMPAIGN: 60,
}

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_LOCAL = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")
_NAME_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f\"<>\\,;:@]")
_TOKEN = re.compile(r"[a-z0-9]{20,64}")


def stream_of(purpose: str) -> Stream:
    """The stream a purpose uses; `KeyError` for an unknown purpose."""
    return PURPOSE_STREAMS[purpose]


def parent_domain(value: str) -> str:
    """A parent domain in lower case, or `InvalidValue`: at least two DNS
    labels of letters, digits and inner hyphens, ASCII (an internationalised
    name must be given in its `xn--` form), at most 200 characters so every
    stream subdomain stays a valid name, no trailing dot, not an address."""
    domain = value.strip().lower()
    labels = domain.split(".")
    if (
        not domain
        or len(domain) > 200
        or len(labels) < 2
        or not all(_LABEL.fullmatch(label) for label in labels)
        or labels[-1].isdigit()
    ):
        raise InvalidValue("EMAIL_PARENT_DOMAIN: a domain name such as example.com")
    return domain


def stream_domain(stream: Stream, parent: str) -> str:
    return f"{SUBDOMAINS[stream]}.{parent}"


def inbound_domain(parent: str) -> str:
    return f"{INBOUND_SUBDOMAIN}.{parent}"


def local_part(value: str) -> str:
    """A sender's local part, or `InvalidValue`: lower-case letters, digits,
    dots, hyphens and underscores, no plus sign (reserved for reply routing)."""
    local = value.strip().lower()
    if not _LOCAL.fullmatch(local) or ".." in local:
        raise InvalidValue("local part: letters, digits, '.', '-' or '_', at most 64")
    return local


def sender(stream: Stream, parent: str, *, local: str | None = None) -> str:
    """The `From` of a stream: a bare `local@sub.parent`. SaaS-OS v0.6.0
    accepts no display name (`saas_os.core.email.validate_email_address`
    refuses whitespace), so none is added."""
    return f"{local_part(local or DEFAULT_LOCAL_PARTS[stream])}@{stream_domain(stream, parent)}"


def reply_address(token: str, parent: str) -> str:
    """The routing address of one conversation: `reply+<token>@inbound.<parent>`."""
    if not _TOKEN.fullmatch(token):
        raise ValueError("a routing token is 20 to 64 lower-case letters and digits")
    return f"reply+{token}@{inbound_domain(parent)}"


def routing_token(address: str, parent: str) -> str | None:
    """The token of a routing address on this deployment's inbound domain,
    or None for any other address. Case-insensitive; callers pass the bare
    address, never a display name."""
    value = address.strip().lower()
    local, at, domain = value.rpartition("@")
    if not at or domain != inbound_domain(parent):
        return None
    prefix, plus, token = local.partition("+")
    if prefix != "reply" or not plus or not _TOKEN.fullmatch(token):
        return None
    return token
