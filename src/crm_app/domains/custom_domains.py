"""Custom domain rules (decision P12-D): pure, no database, DNS or framework.

A workspace may serve its LeadStack-hosted pages (published forms, booking
pages) on a hostname it owns, such as `forms.acme.example`. Ownership is
proved with a DNS TXT record at `_leadstack-challenge.<hostname>` holding
`leadstack-verification=<token>`, a random token issued for that claim
alone. These rules check hostnames and the record; looking the record up
is the caller's job.
"""

from __future__ import annotations

import hmac
import re
import secrets

from crm_app.domains.records import InvalidValue

HOSTNAME_MAX = 253
CHALLENGE_LABEL = "_leadstack-challenge"
VALUE_PREFIX = "leadstack-verification="

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TOKEN = re.compile(r"[0-9a-f]{32}")
# Names no workspace may claim: local, reserved for documentation or tests,
# and internal-only top-level names.
_RESERVED_SUFFIXES = (
    "localhost",
    "local",
    "internal",
    "invalid",
    "test",
    "example",
    "example.com",
    "example.net",
    "example.org",
)
_HOSTNAME_RULE = "hostname: a domain name you own, such as forms.example.com"


def hostname(value: str, *, app_host: str | None = None) -> str:
    """A claimable hostname in lower case, or `InvalidValue`: ASCII labels
    (punycode for international names), at least two, no wildcard, port,
    path or trailing dot, not an address, not a reserved name, and neither
    the app's own host nor a name under it."""
    host = value.strip().lower()
    labels = host.split(".")
    if (
        not host
        or len(host) > HOSTNAME_MAX
        or len(labels) < 2
        or not all(_LABEL.fullmatch(label) for label in labels)
        or labels[-1].isdigit()
    ):
        raise InvalidValue(_HOSTNAME_RULE)
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _RESERVED_SUFFIXES):
        raise InvalidValue(_HOSTNAME_RULE)
    if app_host and (host == app_host or host.endswith(f".{app_host}")):
        raise InvalidValue("hostname: the app's own domain cannot be claimed")
    return host


def new_token() -> str:
    return secrets.token_hex(16)


def challenge_name(host: str) -> str:
    """Where the TXT record goes."""
    return f"{CHALLENGE_LABEL}.{host}"


def challenge_value(token: str) -> str:
    """What the TXT record holds."""
    if not _TOKEN.fullmatch(token):
        raise ValueError("a verification token is 32 lower-case hex digits")
    return f"{VALUE_PREFIX}{token}"


def proves(records: list[str], token: str) -> bool:
    """Whether any TXT string at the challenge name is exactly the expected
    value (compared in constant time; quotes and surrounding spaces from
    resolvers are ignored)."""
    expected = challenge_value(token)
    found = False
    for record in records:
        text = record.strip().strip('"').strip()
        if hmac.compare_digest(text.encode("utf-8", "replace"), expected.encode("ascii")):
            found = True
    return found
