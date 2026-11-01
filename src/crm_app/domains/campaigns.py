"""Campaign rules (decision P7-C): pure, no database or framework.

A campaign moves through

    draft → validated → awaiting_approval → approved → queued → processing
          → completed | partially_completed | failed

and may end `rejected` (by an approver; editable again) or `cancelled`.
Editing a campaign in any state before `queued` returns it to `draft` and
clears its approval, so a modified campaign is never sent on an earlier
approval: approval records the hash of exactly the content and audience
that were approved (`content_hash`), and queuing checks it again.

Content is plain text with two placeholders, `{{first_name}}` and
`{{last_name}}`, replaced literally; nothing in a campaign is evaluated.
An audience is a segment of the workspace's contacts by lifecycle stage,
tag, owner and company; an empty segment must say `all_contacts`, so a
bulk send to everyone is never an accident.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from crm_app.domains.records import InvalidValue

NAME_MAX = 120
SUBJECT_MAX = 200
BODY_MAX = 18_000  # leaves room for the unsubscribe footer within an email's 20,000
FILTER_MAX = 50

STATUSES = (
    "draft",
    "validated",
    "awaiting_approval",
    "approved",
    "queued",
    "processing",
    "completed",
    "partially_completed",
    "failed",
    "rejected",
    "cancelled",
)
# States in which the content may still change (any change returns it to draft).
EDITABLE = ("draft", "validated", "awaiting_approval", "approved", "rejected")
CANCELLABLE = ("draft", "validated", "awaiting_approval", "approved", "rejected")
FINAL = ("completed", "partially_completed", "failed", "cancelled")

# Which step leads from which states.
TRANSITIONS: Mapping[str, tuple[tuple[str, ...], str]] = {
    "validate": (("draft", "rejected"), "validated"),
    "submit": (("validated",), "awaiting_approval"),
    "approve": (("awaiting_approval",), "approved"),
    "reject": (("awaiting_approval",), "rejected"),
    "cancel": (CANCELLABLE, "cancelled"),
    "queue": (("approved",), "queued"),
}

PLACEHOLDERS = ("first_name", "last_name")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_SUBJECT_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BODY_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_BRACES = re.compile(r"\{\{|\}\}")


class StepRefused(ValueError):
    """A step that is not allowed from the campaign's state."""

    def __init__(self, step: str, status: str) -> None:
        super().__init__(f"{step} from {status}")
        self.step = step
        self.status = status


def after(step: str, status: str) -> str:
    """The state after `step`, or `StepRefused`."""
    sources, target = TRANSITIONS[step]
    if status not in sources:
        raise StepRefused(step, status)
    return target


@dataclass(frozen=True)
class Segment:
    stages: tuple[str, ...] = ()
    tag_ids: tuple[uuid.UUID, ...] = ()
    owner_ids: tuple[uuid.UUID, ...] = ()
    company_ids: tuple[uuid.UUID, ...] = ()
    all_contacts: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "stages": sorted(self.stages),
            "tag_ids": sorted(str(v) for v in self.tag_ids),
            "owner_ids": sorted(str(v) for v in self.owner_ids),
            "company_ids": sorted(str(v) for v in self.company_ids),
            "all_contacts": self.all_contacts,
        }

    @property
    def empty(self) -> bool:
        return not (self.stages or self.tag_ids or self.owner_ids or self.company_ids)


def _ids(values: object, name: str) -> tuple[uuid.UUID, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)) or len(values) > FILTER_MAX:
        raise InvalidValue(f"segment.{name}: at most {FILTER_MAX} ids")
    found: list[uuid.UUID] = []
    for value in values:
        try:
            parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except ValueError:
            raise InvalidValue(f"segment.{name}: ids only") from None
        if parsed not in found:
            found.append(parsed)
    return tuple(found)


def segment(raw: Mapping[str, object], stages: Sequence[str]) -> Segment:
    """A segment from its parts, or `InvalidValue`. `stages` are the
    lifecycle stages contacts may have."""
    chosen = raw.get("stages") or []
    if not isinstance(chosen, (list, tuple)) or len(chosen) > len(stages):
        raise InvalidValue("segment.stages: lifecycle stages")
    unknown = [s for s in chosen if s not in stages]
    if unknown:
        raise InvalidValue("segment.stages: lifecycle stages")
    result = Segment(
        stages=tuple(dict.fromkeys(str(s) for s in chosen)),
        tag_ids=_ids(raw.get("tag_ids"), "tag_ids"),
        owner_ids=_ids(raw.get("owner_ids"), "owner_ids"),
        company_ids=_ids(raw.get("company_ids"), "company_ids"),
        all_contacts=raw.get("all_contacts") is True,
    )
    if result.empty and not result.all_contacts:
        raise InvalidValue("segment: choose at least one filter, or all_contacts")
    if not result.empty and result.all_contacts:
        raise InvalidValue("segment: all_contacts takes no filters")
    return result


def name(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= NAME_MAX or _SUBJECT_CONTROL.search(text):
        raise InvalidValue(f"name: 1 to {NAME_MAX} characters")
    return text


def subject(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= SUBJECT_MAX or _SUBJECT_CONTROL.search(text):
        raise InvalidValue(f"subject: one line of 1 to {SUBJECT_MAX} characters")
    _placeholders(text, "subject")
    return text


def body(value: str) -> str:
    text = value.replace("\r\n", "\n").strip()
    if not 1 <= len(text) <= BODY_MAX or _BODY_CONTROL.search(text):
        raise InvalidValue(f"body: 1 to {BODY_MAX} characters, no control characters")
    _placeholders(text, "body")
    return text


def _placeholders(text: str, where: str) -> None:
    for match in _PLACEHOLDER.finditer(text):
        if match.group(1) not in PLACEHOLDERS:
            raise InvalidValue(f"{where}: unknown placeholder {{{{{match.group(1)}}}}}")
    if _BRACES.search(_PLACEHOLDER.sub("", text)):
        raise InvalidValue(f"{where}: '{{{{' and '}}}}' only around a placeholder")


def content_hash(
    campaign_name: str, campaign_subject: str, campaign_body: str, audience: Segment
) -> str:
    """What an approval binds: the exact name, subject, body and audience."""
    canonical = json.dumps(
        {
            "name": campaign_name,
            "subject": campaign_subject,
            "body": campaign_body,
            "segment": audience.as_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render(text: str, values: Mapping[str, str | None]) -> str:
    """`text` with each placeholder replaced by the contact's value (empty
    when unknown). Replacement is literal: a value containing braces is not
    expanded again."""

    def one(match: re.Match[str]) -> str:
        value = values.get(match.group(1)) or ""
        return " ".join(value.split())

    return _PLACEHOLDER.sub(one, text)


def footer(workspace_name: str, unsubscribe_url: str) -> str:
    return f"\n\n--\nYou receive this email from {workspace_name}.\nUnsubscribe: {unsubscribe_url}"


@dataclass
class Eligibility:
    """How many of a segment's contacts may receive a campaign, and why the
    others may not."""

    eligible: int = 0
    excluded: dict[str, int] = field(default_factory=dict)

    def exclude(self, reason: str) -> None:
        self.excluded[reason] = self.excluded.get(reason, 0) + 1


def eligibility_reason(
    *, email: str | None, suppressed: bool, consent: str, seen: bool
) -> str | None:
    """Why one contact may not receive a campaign, or None."""
    if not email:
        return "no_email"
    if seen:
        return "duplicate_email"
    if suppressed:
        return "suppressed"
    if consent != "granted":
        return "no_consent"
    return None
