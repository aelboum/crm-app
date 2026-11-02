"""Transactional email rules (decision P6-E): pure, no database or framework.

- What an email may hold (`content`), its `Message-ID`, and how far a
  delivery event may move its status (`after_event`).
- Resend's webhooks are signed the Svix way: the signed content is
  `"{id}.{timestamp}.{body}"`, HMAC-SHA256 with the base64 key after the
  secret's `whsec_` prefix, sent as space-separated `v1,<base64>` values.
  `signature_valid` checks it in constant time and refuses a timestamp
  more than five minutes away.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from crm_app.domains.records import InvalidValue, email

PURPOSES = ("booking_confirmation", "test", "conversation_reply", "campaign")
SUBJECT_MAX = 200
BODY_MAX = 20_000
# Tries before a message counts as failed; each try may itself be retried
# by the job queue (`JOBS_MAX_TRIES`).
MAX_ATTEMPTS = 5
SIGNATURE_TOLERANCE_SECONDS = 300
# Seconds since the epoch, ASCII digits only (security review 13-H3).
_TIMESTAMP = re.compile(r"[0-9]{1,12}")
WEBHOOK_BODY_MAX = 64 * 1024

# Final statuses: nothing is sent again. `failed`: never accepted by the
# provider; `rejected`: accepted, then reported as not sent (P6-S).
FINAL = (
    "sent",
    "delivery_delayed",
    "delivered",
    "bounced",
    "complained",
    "failed",
    "suppressed",
    "rejected",
)

# A provider's event moves a sent email forward, never back; a bounce, a
# rejection or a complaint is final. `delivery_delayed` after `delivered`
# is ignored. Acceptance (`sent`) is never delivery.
_RANK = {
    "sent": 1,
    "delivery_delayed": 2,
    "delivered": 3,
    "bounced": 4,
    "rejected": 4,
    "complained": 5,
}

EVENT_TYPES = {
    "email.sent": "sent",
    "email.delivery_delayed": "delivery_delayed",
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.suppressed": "suppressed",
}
# The status an event leads to, where it is not the event's own name.
_EVENT_STATUS = {"failed": "rejected", "suppressed": "rejected"}

# Retry timing after a transient failure (P6-S): exponential from
# `BACKOFF_BASE_SECONDS`, at most `BACKOFF_MAX_SECONDS`, stretched by up to
# `BACKOFF_JITTER` so retries of many emails spread out, and never sooner
# than the provider's own `Retry-After`.
BACKOFF_BASE_SECONDS = 30.0
BACKOFF_MAX_SECONDS = 3600.0
BACKOFF_JITTER = 0.25

_SUBJECT_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BODY_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_PROVIDER_ID = re.compile(r"[A-Za-z0-9_.:@<>-]{1,200}")
_EVENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


@dataclass(frozen=True)
class Content:
    to_email: str
    subject: str
    text_body: str


def content(to_email: str, subject: str, text_body: str) -> Content:
    """The recipient lower-cased, a one-line subject and a plain-text body,
    or `InvalidValue` naming the rule."""
    address = email(to_email)
    if address is None:
        raise InvalidValue("to_email: required")
    subject = subject.strip()
    if not 1 <= len(subject) <= SUBJECT_MAX or _SUBJECT_CONTROL.search(subject):
        raise InvalidValue(f"subject: one line of 1 to {SUBJECT_MAX} characters")
    body = text_body.replace("\r\n", "\n").strip()
    if not 1 <= len(body) <= BODY_MAX or _BODY_CONTROL.search(body):
        raise InvalidValue(f"text_body: 1 to {BODY_MAX} characters, no control characters")
    return Content(to_email=address, subject=subject, text_body=body)


def message_id(email_id: str, sender: str) -> str:
    """The `Message-ID` of an email, from its id and the sender's domain. The
    same on every try, so the provider's idempotency key is too."""
    domain = sender.rsplit("@", 1)[-1].strip().strip(">").lower() or "localhost"
    return f"<{email_id}@{domain}>"


def after_event(status: str, event: str) -> str:
    """The status after a provider's `event` for an email in `status`."""
    if status not in _RANK:
        return status  # never sent by us as far as we know: leave it
    target = _EVENT_STATUS.get(event, event)
    return target if _RANK[target] > _RANK[status] else status


def retry_delay(attempts: int, retry_after: float | None, jitter: float) -> float:
    """Seconds until the next try after `attempts` tries, for `jitter` in
    [0, 1): exponential backoff with jitter, at least `retry_after` (an
    unstated reset, `math.inf`, counts as the maximum)."""
    delay = min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_MAX_SECONDS)
    delay *= 1 + BACKOFF_JITTER * min(max(jitter, 0.0), 1.0)
    if retry_after is not None and retry_after > 0:
        delay = max(delay, min(retry_after, BACKOFF_MAX_SECONDS))
    return min(delay, BACKOFF_MAX_SECONDS * (1 + BACKOFF_JITTER))


@dataclass(frozen=True)
class ProviderEvent:
    """A delivery event from a provider's webhook, reduced to what is kept."""

    provider_event_id: str
    provider_message_id: str
    type: str
    occurred_at: datetime


def _decoded_secret(secret: str) -> bytes | None:
    raw = secret.removeprefix("whsec_")
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None


def signature_valid(  # noqa: PLR0913, PLR0917 - the headers, the body, the secret, the clock
    secret: str,
    event_id: str,
    timestamp: str,
    signatures: str,
    body: bytes,
    now: datetime,
) -> bool:
    """Whether a Svix-style signature over `body` is valid and recent."""
    key = _decoded_secret(secret)
    if not key or not _EVENT_ID.fullmatch(event_id) or not _TIMESTAMP.fullmatch(timestamp):
        return False
    if abs(now.timestamp() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    signed = f"{event_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest())
    valid = False
    for part in signatures.split():
        version, _, value = part.partition(",")
        if version == "v1" and hmac.compare_digest(value.encode("ascii", "replace"), expected):
            valid = True
    return valid


def provider_event(event_id: str, payload: object) -> ProviderEvent | None:
    """The event a verified webhook body describes, or `None` for a type this
    product does not track or a body without a usable email id."""
    if not isinstance(payload, dict):
        return None
    kind = EVENT_TYPES.get(str(payload.get("type", "")))
    data = payload.get("data")
    if kind is None or not isinstance(data, dict):
        return None
    message = data.get("email_id")
    if not isinstance(message, str) or not _PROVIDER_ID.fullmatch(message):
        return None
    occurred = payload.get("created_at")
    try:
        at = datetime.fromisoformat(str(occurred).replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return ProviderEvent(
        provider_event_id=event_id,
        provider_message_id=message,
        type=kind,
        occurred_at=at.astimezone(UTC),
    )
