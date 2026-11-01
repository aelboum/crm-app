"""Campaigns (decision P7-C): drafts, audiences, validation, approval,
recipients and unsubscribing.

- A campaign is drafted and edited by members with
  `crm_app.campaign:manage`; any edit returns it to `draft` and clears its
  estimate and approval.
- `validate` computes the audience estimate (eligible contacts, and how
  many are excluded for which reason: no address, duplicate address,
  suppressed, no marketing consent) and needs at least one eligible
  contact; `submit` asks for approval.
- `approve` (only `crm_app.campaign:approve`) records the hash of the exact
  content and audience; `reject` sends it back with a note. Every step is
  audited with ids, states and hashes, never content.
- `queue` is refused unless campaign sending is available
  (`SENDING_AVAILABLE`, false: SaaS-OS v0.6.0 cannot set the
  `List-Unsubscribe` headers bulk mail needs) and the campaign stream is
  switched on (never in production), and only while the approved hash
  still matches. Nothing sends a campaign because it was saved, validated
  or approved.
- `process` (run after queuing) adds each eligible contact once (a unique
  key per campaign and contact) and queues one email per recipient through
  `crm_app.emails` (purpose `campaign`, the campaign stream), where consent
  and suppression are checked again at send time.
- `unsubscribe` takes a recipient's token from the email's link: it
  suppresses the address (reason `unsubscribed`) and records the
  withdrawal of consent.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import lock_open_tenant
from saas_os.infra.db import (
    OperationalError,
    Session,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app import emails, suppression
from crm_app.domains import campaigns as rules
from crm_app.domains import email_streams as streams
from crm_app.domains.records import STAGES, InvalidValue
from crm_app.models import (
    Campaign,
    CampaignRecipient,
    Contact,
    ContactTag,
)
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)
from crm_app.settings import stream_enabled

RESOURCE = "crm_app.campaign"
LIST_LIMIT = 100
AUDIENCE_MAX = 50_000
# Bulk mail needs `List-Unsubscribe` and `List-Unsubscribe-Post` headers,
# which SaaS-OS v0.6.0 cannot set (EMAIL-ARCHITECTURE.md, section 1).
SENDING_AVAILABLE = False

Item = dict[str, Any]


class CampaignRuleError(RecordError):
    """A value or step the rules refuse; `detail` names the rule."""

    status, code = 422, "invalid_campaign"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class CampaignStateError(RecordError):
    """A step that is not allowed from the campaign's state."""

    status, code = 409, "campaign_state"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class SendingUnavailableError(RecordError):
    status, code = 409, "campaign_sending_unavailable"


class ApprovalOutdatedError(RecordError):
    status, code = 409, "approval_outdated"


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _audit(session: Session, scope: Scope, verb: str, row: Campaign, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"status": row.status, **meta},
    )


def _segment(raw: dict[str, Any]) -> rules.Segment:
    try:
        return rules.segment(raw, STAGES)
    except InvalidValue as exc:
        raise CampaignRuleError(str(exc)) from None


def _content(name: str, subject: str, body: str) -> tuple[str, str, str]:
    try:
        return rules.name(name), rules.subject(subject), rules.body(body)
    except InvalidValue as exc:
        raise CampaignRuleError(str(exc)) from None


def _item(row: Campaign) -> Item:
    return {
        "id": row.id,
        "name": row.name,
        "subject": row.subject,
        "body": row.body,
        "segment": row.segment,
        "status": row.status,
        "estimate": row.estimate,
        "content_hash": row.content_hash,
        "approved": row.approved_hash is not None and row.approved_hash == row.content_hash,
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at,
        "submitted_by_user_id": row.submitted_by_user_id,
        "submitted_at": row.submitted_at,
        "decision_note": row.decision_note,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def _load(session: Session, scope: Scope, campaign_id: uuid.UUID, *, lock: bool) -> Campaign:
    query = select(Campaign).where(
        Campaign.tenant_id == scope.workspace, Campaign.id == campaign_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _checked(row: Campaign, expected_version: int) -> None:
    if row.version != expected_version:
        raise StaleVersionError(row.version)


def _step(row: Campaign, step: str) -> None:
    try:
        row.status = rules.after(step, row.status)
    except rules.StepRefused as exc:
        raise CampaignStateError(f"{exc.step}: not from {exc.status}") from None


def _touch(row: Campaign) -> None:
    row.updated_at = _now()
    row.version += 1


# --- Reads ---------------------------------------------------------------------------------


def list_campaigns(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(Campaign)
            .where(Campaign.tenant_id == scope.workspace)
            .order_by(Campaign.updated_at.desc(), Campaign.id.desc())
            .limit(LIST_LIMIT)
        ).scalars()
        return [_item(row) for row in rows]


def get(scope: Scope, campaign_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        return _item(_load(session, scope, campaign_id, lock=False))


# --- Audience ------------------------------------------------------------------------------


def _audience(session: Session, scope: Scope, audience: rules.Segment) -> list[Contact]:
    query = select(Contact).where(
        Contact.tenant_id == scope.workspace, Contact.archived_at.is_(None)
    )
    if audience.stages:
        query = query.where(Contact.lifecycle_stage.in_(audience.stages))
    if audience.owner_ids:
        query = query.where(Contact.owner_user_id.in_(audience.owner_ids))
    if audience.company_ids:
        query = query.where(Contact.company_id.in_(audience.company_ids))
    if audience.tag_ids:
        query = query.where(
            Contact.id.in_(
                select(ContactTag.contact_id).where(
                    ContactTag.tenant_id == scope.workspace, ContactTag.tag_id.in_(audience.tag_ids)
                )
            )
        )
    rows = list(
        session.execute(query.order_by(Contact.created_at, Contact.id).limit(AUDIENCE_MAX + 1))
        .scalars()
        .all()
    )
    if len(rows) > AUDIENCE_MAX:
        raise CampaignRuleError(f"audience: at most {AUDIENCE_MAX} contacts")
    return rows


def _eligible(
    session: Session, scope: Scope, audience: rules.Segment
) -> tuple[rules.Eligibility, list[Contact]]:
    result = rules.Eligibility()
    chosen: list[Contact] = []
    seen: set[str] = set()
    for contact in _audience(session, scope, audience):
        email = (contact.email or "").strip().lower() or None
        reason = rules.eligibility_reason(
            email=email,
            suppressed=bool(email)
            and not suppression.may_send(
                session, scope.workspace, email or "", None, marketing=False
            ),
            consent=suppression.consent_state(session, scope.workspace, contact.id),
            seen=email in seen if email else False,
        )
        if reason is None and email:
            result.eligible += 1
            seen.add(email)
            chosen.append(contact)
        else:
            result.exclude(reason or "no_email")
    return result, chosen


# --- Writes --------------------------------------------------------------------------------


def create(scope: Scope, *, name: str, subject: str, body: str, segment: dict[str, Any]) -> Item:
    clean = _content(name, subject, body)
    audience = _segment(segment)

    def business(session: Session) -> Item:
        now = _now()
        row = Campaign(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            name=clean[0],
            subject=clean[1],
            body=clean[2],
            segment=audience.as_dict(),
            status="draft",
            content_hash=rules.content_hash(*clean, audience),
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", row, content_hash=row.content_hash)
        return _item(row)

    return _transaction(scope, business)


def update(
    scope: Scope, campaign_id: uuid.UUID, changes: dict[str, Any], *, expected_version: int
) -> Item:
    """Edit a campaign; any change returns it to `draft` and clears its
    estimate, submission and approval."""

    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        if row.status not in rules.EDITABLE:
            raise CampaignStateError(f"edit: not from {row.status}")
        name, subject, body = _content(
            changes.get("name", row.name),
            changes.get("subject", row.subject),
            changes.get("body", row.body),
        )
        audience = _segment(changes.get("segment", row.segment))
        new_hash = rules.content_hash(name, subject, body, audience)
        if new_hash == row.content_hash:
            return _item(row)
        was = row.status
        row.name, row.subject, row.body = name, subject, body
        row.segment, row.content_hash = audience.as_dict(), new_hash
        row.status, row.estimate, row.validated_at = "draft", None, None
        row.submitted_by_user_id = row.submitted_at = None
        row.approved_hash = row.approved_by_user_id = row.approved_at = None
        row.decision_note = None
        _touch(row)
        _audit(
            session,
            scope,
            "updated",
            row,
            previous_status=was,
            approval_cleared=was in ("awaiting_approval", "approved"),
            content_hash=new_hash,
        )
        return _item(row)

    return _transaction(scope, business)


def validate(scope: Scope, campaign_id: uuid.UUID, *, expected_version: int) -> Item:
    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        estimate, _ = _eligible(session, scope, _segment(row.segment))
        if estimate.eligible == 0:
            raise CampaignRuleError("audience: no contact may receive this campaign")
        _step(row, "validate")
        row.estimate = {"eligible": estimate.eligible, "excluded": estimate.excluded}
        row.validated_at = _now()
        _touch(row)
        _audit(session, scope, "validated", row, eligible=estimate.eligible)
        return _item(row)

    return _transaction(scope, business)


def submit(scope: Scope, campaign_id: uuid.UUID, *, expected_version: int) -> Item:
    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        _step(row, "submit")
        row.submitted_by_user_id, row.submitted_at = scope.actor, _now()
        _touch(row)
        _audit(session, scope, "submitted", row, content_hash=row.content_hash)
        return _item(row)

    return _transaction(scope, business)


def approve(scope: Scope, campaign_id: uuid.UUID, *, expected_version: int) -> Item:
    """Approve exactly the content and audience the campaign now has."""

    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        current = rules.content_hash(row.name, row.subject, row.body, _segment(row.segment))
        if current != row.content_hash:
            raise ApprovalOutdatedError
        _step(row, "approve")
        row.approved_hash, row.approved_by_user_id, row.approved_at = current, scope.actor, _now()
        _touch(row)
        _audit(session, scope, "approved", row, approved_hash=current)
        return _item(row)

    return _transaction(scope, business)


def reject(scope: Scope, campaign_id: uuid.UUID, *, note: str, expected_version: int) -> Item:
    text = " ".join(note.split())
    if not 1 <= len(text) <= 500:
        raise CampaignRuleError("note: 1 to 500 characters")

    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        _step(row, "reject")
        row.decision_note, row.rejected_by_user_id, row.rejected_at = text, scope.actor, _now()
        _touch(row)
        _audit(session, scope, "rejected", row)
        return _item(row)

    return _transaction(scope, business)


def cancel(scope: Scope, campaign_id: uuid.UUID, *, expected_version: int) -> Item:
    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        _step(row, "cancel")
        row.cancelled_by_user_id, row.cancelled_at = scope.actor, _now()
        _touch(row)
        _audit(session, scope, "cancelled", row)
        return _item(row)

    return _transaction(scope, business)


def _production() -> bool:
    import os  # noqa: PLC0415

    return os.environ.get("ENVIRONMENT", "").strip().lower() == "production"


def sending_available() -> bool:
    return SENDING_AVAILABLE and not _production() and stream_enabled(streams.Stream.CAMPAIGN)


def queue(scope: Scope, campaign_id: uuid.UUID, *, expected_version: int) -> Item:
    """Queue an approved campaign for sending, if sending is available and
    the approval still matches its content and audience."""
    if not sending_available():
        raise SendingUnavailableError

    def business(session: Session) -> Item:
        row = _load(session, scope, campaign_id, lock=True)
        _checked(row, expected_version)
        current = rules.content_hash(row.name, row.subject, row.body, _segment(row.segment))
        if row.approved_hash is None or current != row.approved_hash:
            raise ApprovalOutdatedError
        _step(row, "queue")
        row.queued_at = _now()
        _touch(row)
        _audit(session, scope, "queued", row, approved_hash=row.approved_hash)
        return _item(row)

    return _transaction(scope, business)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def process(
    scope: Scope, campaign_id: uuid.UUID, *, workspace_name: str, unsubscribe_base: str
) -> Item:
    """Add the eligible recipients of a queued campaign, each at most once,
    and queue one email each. Safe to run again: recipients already added
    are skipped, and a finished campaign is left as it is."""
    if not sending_available():
        raise SendingUnavailableError

    def business(session: Session) -> tuple[Item, list[uuid.UUID]]:
        row = _load(session, scope, campaign_id, lock=True)
        if row.status not in ("queued", "processing"):
            return _item(row), []
        if row.approved_hash != row.content_hash:
            row.status = "failed"
            _touch(row)
            _audit(session, scope, "failed", row, error="approval_outdated")
            return _item(row), []
        row.status = "processing"
        _, chosen = _eligible(session, scope, _segment(row.segment))
        done = set(
            session.execute(
                select(CampaignRecipient.contact_id).where(
                    CampaignRecipient.tenant_id == scope.workspace,
                    CampaignRecipient.campaign_id == row.id,
                )
            ).scalars()
        )
        queued: list[uuid.UUID] = []
        failed = 0
        for contact in chosen:
            if contact.id in done:
                continue
            token = secrets.token_hex(16)
            values = {"first_name": contact.first_name, "last_name": contact.last_name}
            text = rules.render(row.body, values) + rules.footer(
                workspace_name, f"{unsubscribe_base}/{scope.workspace}/{token}"
            )
            try:
                email_id = emails.queue(
                    session,
                    scope,
                    purpose="campaign",
                    to_email=contact.email or "",
                    subject=rules.render(row.subject, values),
                    text_body=text,
                    contact_id=contact.id,
                )
            except InvalidValue:
                failed += 1
                continue
            session.add(
                CampaignRecipient(
                    id=uuid.uuid4(),
                    tenant_id=scope.workspace,
                    campaign_id=row.id,
                    contact_id=contact.id,
                    email=(contact.email or "").strip().lower(),
                    status="queued",
                    email_message_id=email_id,
                    unsubscribe_hash=_token_hash(token),
                    created_at=_now(),
                )
            )
            queued.append(email_id)
        row.status = "partially_completed" if failed else "completed"
        _touch(row)
        _audit(session, scope, row.status, row, queued=len(queued), failed=failed)
        session.flush()
        return _item(row), queued

    item, queued = _transaction(scope, business)
    return {**item, "queued_emails": [str(e) for e in queued]}


# --- Unsubscribe -----------------------------------------------------------------------------


def unsubscribe(workspace: uuid.UUID, token: str) -> bool:
    """Act on a recipient's unsubscribe link; True when the token is known.
    Repeating it changes nothing more."""
    if len(token) != 32 or not all(c in "0123456789abcdef" for c in token):
        return False
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            select(CampaignRecipient)
            .where(
                CampaignRecipient.tenant_id == workspace,
                CampaignRecipient.unsubscribe_hash == _token_hash(token),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return False
        if row.status != "unsubscribed":
            row.status, row.unsubscribed_at = "unsubscribed", _now()
            suppression.suppress_unsubscribed(session, workspace, row.email, row.contact_id)
        return True
