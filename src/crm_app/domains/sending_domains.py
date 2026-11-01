"""Customer-owned sending domain rules (decision P6-D): pure, no database,
network or framework.

A workspace may send conversation and campaign email from its own domain
(`jan@acme.nl`) once Resend has verified that domain. Resend, not
LeadStack, decides which DNS records the domain needs: the records shown
to the workspace are exactly the ones Resend returned (`records`), never
invented here. These rules validate what Resend sends back and what a
member enters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from crm_app.domains import custom_domains
from crm_app.domains import email_streams as streams
from crm_app.domains.records import InvalidValue

# Resend's domain states (Domains API, 2026-11-01); anything else is kept
# as `unknown` and never counts as verified.
STATUSES = ("not_started", "pending", "verified", "failed", "temporary_failure")
RECORD_TYPES = ("TXT", "MX", "CNAME")
RECORDS_MAX = 20
VALUE_MAX = 2000
NAME_MAX = 255
EVENT_TYPES = ("domain.created", "domain.updated", "domain.deleted")

_PROVIDER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RECORD_KIND = re.compile(r"[A-Za-z0-9 _-]{1,40}")


class ProviderAnswerError(ValueError):
    """An answer from the provider this product will not trust."""


def domain(value: str, *, parent: str | None) -> str:
    """A sending domain a workspace may register, or `InvalidValue`: a
    plain, non-reserved domain name, and never LeadStack's own email parent
    domain or a name under it."""
    try:
        name = custom_domains.hostname(value)
    except InvalidValue:
        raise InvalidValue("domain: a domain name you own, such as acme.nl") from None
    if parent and (name == parent or name.endswith(f".{parent}")):
        raise InvalidValue("domain: LeadStack's own sending domain cannot be registered")
    return name


def address(local: str, sending_domain: str) -> str:
    """A sender address on a sending domain: `local@domain`. No `+`
    (reserved for routing) and no display name (SaaS-OS v0.6.0)."""
    return f"{streams.local_part(local)}@{sending_domain}"


def status(value: object) -> str:
    return value if isinstance(value, str) and value in STATUSES else "unknown"


@dataclass(frozen=True)
class Record:
    """One DNS record exactly as the provider listed it."""

    kind: str
    type: str
    name: str
    value: str
    ttl: str | None
    priority: int | None
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "record": self.kind,
            "type": self.type,
            "name": self.name,
            "value": self.value,
            "ttl": self.ttl,
            "priority": self.priority,
            "status": self.status,
        }


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit or _CONTROL.search(value):
        raise ProviderAnswerError("record field")
    return value


def records(raw: object) -> list[Record]:
    """The provider's DNS records, checked but not changed."""
    if not isinstance(raw, list) or len(raw) > RECORDS_MAX:
        raise ProviderAnswerError("records")
    found: list[Record] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProviderAnswerError("record")
        kind = item.get("record")
        record_type = item.get("type")
        if not isinstance(kind, str) or not _RECORD_KIND.fullmatch(kind):
            raise ProviderAnswerError("record kind")
        if record_type not in RECORD_TYPES:
            raise ProviderAnswerError("record type")
        ttl = item.get("ttl")
        priority = item.get("priority")
        found.append(
            Record(
                kind=kind,
                type=str(record_type),
                name=_text(item.get("name"), NAME_MAX),
                value=_text(item.get("value"), VALUE_MAX),
                ttl=str(ttl)[:20] if isinstance(ttl, (str, int)) else None,
                priority=priority if isinstance(priority, int) and 0 <= priority <= 65535 else None,
                status=status(item.get("status")),
            )
        )
    return found


@dataclass(frozen=True)
class ProviderDomain:
    provider_id: str
    name: str | None
    status: str
    records: list[Record] | None


def provider_domain(raw: object) -> ProviderDomain:
    """A domain as the provider describes it (a create answer or the `data`
    of a domain event)."""
    if not isinstance(raw, dict):
        raise ProviderAnswerError("domain")
    provider_id = raw.get("id")
    if not isinstance(provider_id, str) or not _PROVIDER_ID.fullmatch(provider_id):
        raise ProviderAnswerError("domain id")
    name = raw.get("name")
    return ProviderDomain(
        provider_id=provider_id,
        name=name.lower() if isinstance(name, str) and len(name) <= 253 else None,
        status=status(raw.get("status")),
        records=records(raw["records"]) if "records" in raw else None,
    )


@dataclass(frozen=True)
class DomainEvent:
    type: str
    domain: ProviderDomain


def domain_event(payload: object) -> DomainEvent | None:
    """A verified webhook body's domain event, or None for other types."""
    if not isinstance(payload, dict) or payload.get("type") not in EVENT_TYPES:
        return None
    return DomainEvent(type=str(payload["type"]), domain=provider_domain(payload.get("data")))
