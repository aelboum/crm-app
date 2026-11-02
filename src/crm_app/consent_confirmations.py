"""Email confirmation of consent given on a public form (decision P7-V).

An email typed into a public form is an unverified claim of identity. When
it matches an existing contact, the form's consent is not recorded; a
confirmation is created instead and a transactional email with a link is
queued to that address. Only the person who receives it can confirm.

- The link carries a random 256-bit token; only its SHA-256 hash is kept.
- It expires after `VALID_FOR` and is used once; confirming again with the
  same token is a no-op that answers the same (idempotent).
- Confirming records consent `granted` with method `email_confirmation`,
  the form's wording and the time, and an audit entry; never more.
- Lookups run in the link's own workspace under Row-Level Security; there
  is no cross-workspace lookup.
- The email is only queued: it reaches a provider only while sending is on
  (P6-E 3), and is never sent after `VALID_FOR` (13-H5).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import Session, select, tenant_session_scope

from crm_app import emails
from crm_app.domains.records import InvalidValue
from crm_app.models import ConsentConfirmation, ConsentRecord, Contact, Form
from crm_app.records import Scope

VALID_FOR = timedelta(days=7)
# A new confirmation for the same contact and form is not sent while one
# younger than this is still pending.
RESEND_AFTER = timedelta(days=1)
RESOURCE = "crm_app.consent_confirmation"
_CHANNEL = "email"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _link(workspace: uuid.UUID, token: str) -> str | None:
    origin = os.environ.get("PUBLIC_APP_ORIGIN", "").strip().rstrip("/")
    if not origin.startswith("https://") and not origin.startswith("http://localhost"):
        return None
    # The token travels in the fragment, so it never reaches a server log.
    return f"{origin}/app/c/{workspace}#{token}"


def request(  # noqa: PLR0913, PLR0917 - one confirmation's facts
    session: Session,
    scope: Scope,
    contact: Contact,
    form: Form,
    submission_id: uuid.UUID,
    now: datetime,
) -> uuid.UUID | None:
    """Create a confirmation for `contact` and queue its email, in the
    submission's transaction; None when the contact has no address."""
    if not contact.email or not form.consent_text:
        return None
    # One pending confirmation per contact and form a day: repeated
    # submissions by a stranger cannot flood the address with emails.
    pending = session.execute(
        select(ConsentConfirmation.id).where(
            ConsentConfirmation.tenant_id == scope.workspace,
            ConsentConfirmation.contact_id == contact.id,
            ConsentConfirmation.form_id == form.id,
            ConsentConfirmation.confirmed_at.is_(None),
            ConsentConfirmation.created_at > now - RESEND_AFTER,
        )
    ).first()
    if pending is not None:
        return None
    token = secrets.token_urlsafe(32)
    row = ConsentConfirmation(
        id=uuid.uuid4(),
        tenant_id=scope.workspace,
        contact_id=contact.id,
        form_id=form.id,
        submission_id=submission_id,
        wording=form.consent_text,
        token_hash=token_hash(token),
        expires_at=now + VALID_FOR,
        confirmed_at=None,
        email_message_id=None,
        created_at=now,
    )
    session.add(row)
    session.flush()
    link = _link(scope.workspace, token)
    if link is not None:
        lines = [
            f"Hello {contact.first_name}," if contact.first_name else "Hello,",
            "",
            f"Someone asked to receive email from us using this address, on the form {form.name}:",
            "",
            form.consent_text,
            "",
            "If this was you, confirm here (the link works once, for 7 days):",
            link,
            "",
            "If it was not you, ignore this email: nothing changes.",
        ]
        try:
            row.email_message_id = emails.queue(
                session,
                scope,
                purpose="consent_confirmation",
                to_email=contact.email,
                subject="Please confirm your email preferences",
                text_body="\n".join(lines),
                contact_id=contact.id,
            )
        except InvalidValue:
            row.email_message_id = None
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.requested",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"contact_id": str(contact.id), "form_id": str(form.id), "by": "visitor"},
    )
    return row.id


def confirm(workspace: uuid.UUID, token: str, now: datetime | None = None) -> bool:
    """Confirm by the link's token: True when it is (or already was)
    confirmed, False for an unknown or expired one. Never says which."""
    if not 20 <= len(token) <= 100 or not token.isascii():
        return False
    now = now or datetime.now(UTC)
    digest = token_hash(token)
    try:
        with tenant_session_scope(workspace) as session:
            lock_open_tenant(session, workspace)
            row = session.execute(
                select(ConsentConfirmation)
                .where(
                    ConsentConfirmation.tenant_id == workspace,
                    ConsentConfirmation.token_hash == digest,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return False
            if row.confirmed_at is not None:
                return True
            if row.expires_at <= now:
                return False
            row.confirmed_at = now
            session.add(
                ConsentRecord(
                    id=uuid.uuid4(),
                    tenant_id=workspace,
                    contact_id=row.contact_id,
                    channel=_CHANNEL,
                    status="granted",
                    method="email_confirmation",
                    wording=row.wording,
                    form_id=row.form_id,
                    submission_id=row.submission_id,
                    recorded_at=now,
                )
            )
            owner = session.execute(
                select(Form.contact_owner_user_id).where(
                    Form.tenant_id == workspace, Form.id == row.form_id
                )
            ).scalar_one_or_none()
            if owner is not None:
                # SaaS-OS has no system caller: the form's owner, as the
                # submission itself acts (P7-A); marked as the visitor's act.
                record_in_transaction(
                    session,
                    caller=UserCaller(owner),
                    tenant_id=workspace,
                    action=f"{RESOURCE}.confirmed",
                    resource_type=RESOURCE,
                    resource_id=str(row.id),
                    metadata={"contact_id": str(row.contact_id), "by": "visitor"},
                )
            return True
    except (TenantClosedError, TenantNotFoundError):
        return False
