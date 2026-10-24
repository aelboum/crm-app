"""Invitations (`PHASE2-PLAN.md` §8.2; decisions Q4, Q5, P2-F).

SaaS-OS owns the invitation itself (`core.identity`): a random token stored
only as a SHA-256 hash, a 7-day expiry, one-time use under a row lock,
revocation, acceptance only by a signed-in person whose verified email is
the invited one, and the audit events `invitation.create`, `.revoke` and
`.accept`. The product adds, in `crm_app.invitation_intent`, the role the
inviter intends and how the link was delivered:

- **manual** (default, Q4): the link is returned once to the inviter, who
  is told it was not sent; the product never says it was sent.
- **email** (P2-F 3): the link is sent through SaaS-OS `send_email` with
  the configured provider; if the provider does not accept it, the
  invitation is revoked and the inviter is told so.

Acceptance gives a membership with no role (SaaS-OS). An Owner or Admin
then confirms the intended role with the existing role route (Q5); nothing
here assigns a role, impersonates anyone or uses PROVISIONING.

The raw token exists only in this request: in the link returned to the
inviter or in the email body. It is never stored, logged, put in an audit
entry, a job or an error. The link carries it in the URL fragment, which
browsers do not send to servers or in `Referer`.

Rules: Owner and Admin invite (`invitation:create`); only a holder of
`crm_app.owner:manage` (Owner) may invite an Owner, as for every other
Owner change (§5.4), checked here so every caller gets the rule; at most
`MAX_PENDING` pending invitations per workspace, kept under concurrency by
a per-workspace advisory lock around the check and the creation; one
pending invitation per address (SaaS-OS).

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.email import (
    EmailConfigurationError,
    EmailMessage,
    EmailProviderError,
    InvalidEmailAddressError,
    get_email_default_sender,
    get_email_provider,
    send_email,
)
from saas_os.core.identity import (
    DuplicateInvitationError,
    InvalidInvitationEmailError,
    Invitation,
    InvitationAlreadyAcceptedError,
    InvitationNotAuthorizedError,
    InvitationNotFoundError,
    InvitationStatus,
    compute_invitation_status,
    create_invitation,
    list_invitations_for_tenant,
    revoke_invitation,
)
from saas_os.core.rbac import can
from saas_os.core.tenancy import (
    TenantClosedError,
    TenantNotFoundError,
    get_tenant,
    lock_open_tenant,
)
from saas_os.infra.db import acquire_tenant_advisory_lock, select, tenant_session_scope

from crm_app.models import InvitationIntent
from crm_app.records import RecordError, RecordNotFoundError, Scope
from crm_app.roles import Role
from crm_app.settings import invitation_delivery

_log = logging.getLogger(__name__)

RESOURCE = "crm_app.invitation"
MAX_PENDING = 100


class InvitationRefusedError(RecordError):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _refused(status: int, code: str) -> InvitationRefusedError:
    return InvitationRefusedError(status, code)


@dataclass(frozen=True)
class _Created:
    invitation: Invitation
    token: str


@dataclass(frozen=True)
class Created:
    invitation: dict[str, Any]
    # The link with its token, only in manual mode, only in this response.
    link: str | None


def _link(origin: str, workspace: uuid.UUID, token: str) -> str:
    return f"{origin}/app/invite/{workspace}#{token}"


def _view(invitation: Invitation, intent: InvitationIntent | None) -> dict[str, Any]:
    return {
        "id": invitation.id,
        "email": invitation.invited_email,
        "role": intent.role if intent else None,
        "delivery": intent.delivery if intent else None,
        "status": str(compute_invitation_status(invitation)),
        "invited_by_user_id": invitation.inviter_user_id,
        "created_at": invitation.created_at,
        "expires_at": invitation.expires_at,
        "accepted_by_user_id": invitation.accepted_by_user_id,
    }


def _intents(scope: Scope) -> dict[uuid.UUID, InvitationIntent]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(InvitationIntent).where(InvitationIntent.tenant_id == scope.workspace)
        ).scalars()
        intents = {row.invitation_id: row for row in rows}
        for row in intents.values():
            session.expunge(row)
        return intents


def list_invitations(scope: Scope) -> list[dict[str, Any]]:
    """Every invitation of the workspace with its status and intended role,
    newest first. For Owners and Admins (`invitation:read`)."""
    intents = _intents(scope)
    invitations = sorted(
        list_invitations_for_tenant(scope.workspace),
        key=lambda invitation: (invitation.created_at, str(invitation.id)),
        reverse=True,
    )
    return [_view(invitation, intents.get(invitation.id)) for invitation in invitations]


def _pending_count(scope: Scope) -> int:
    return sum(
        compute_invitation_status(invitation) == InvitationStatus.PENDING
        for invitation in list_invitations_for_tenant(scope.workspace)
    )


def _send(email: str, workspace: uuid.UUID, link: str, expires_at: datetime) -> None:
    """Sends the link; raises `InvitationRefusedError` if the provider does
    not accept it. The error never carries the link or the address."""
    try:
        sender = get_email_default_sender()
        if not sender:
            raise _refused(503, "delivery_not_configured")
        name = get_tenant(workspace).name
        message = EmailMessage(
            sender=sender,
            to=(email,),
            subject=f"You are invited to {name}",
            text_body=(
                f"You have been invited to join the workspace {name}.\n\n"
                f"Open this link and sign in with this email address to accept:\n{link}\n\n"
                f"The link works once and expires on {expires_at:%Y-%m-%d %H:%M} UTC.\n"
                "If you did not expect this invitation, you can ignore this email.\n"
            ),
        )
        result = send_email(message, provider=get_email_provider())
    except (EmailProviderError, InvalidEmailAddressError, EmailConfigurationError):
        raise _refused(502, "delivery_failed") from None
    if not result.accepted:
        raise _refused(502, "delivery_failed")


def _create_locked(scope: Scope, email: str) -> _Created:
    """Creates the SaaS-OS invitation while holding a per-workspace lock, so
    the pending cap holds when invitations are created at the same time
    (the lock is released when this transaction ends)."""
    with tenant_session_scope(scope.workspace) as session:
        lock_open_tenant(session, scope.workspace)
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        if _pending_count(scope) >= MAX_PENDING:
            raise _refused(409, "too_many_pending")
        invitation, token = create_invitation(
            scope.workspace, email, caller=UserCaller(scope.actor)
        )
        return _Created(invitation, token)


def create(scope: Scope, email: str, role: Role, *, origin: str) -> Created:
    """Invite `email` to the workspace with the intended `role`. The intent
    is recorded before any email is sent, so a delivered link always has
    one; if anything fails, the invitation is revoked."""
    if role is Role.OWNER and not can(
        actor_id=scope.actor, tenant_id=scope.workspace, action="manage", resource="crm_app.owner"
    ):
        raise _refused(403, "role_not_allowed")
    delivery = invitation_delivery()
    try:
        created = _create_locked(scope, email)
    except DuplicateInvitationError:
        raise _refused(409, "duplicate_invitation") from None
    except InvalidInvitationEmailError:
        raise _refused(422, "invalid_email") from None
    except InvitationNotAuthorizedError:
        raise _refused(403, "not_authorized") from None
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    invitation = created.invitation
    link = _link(origin, scope.workspace, created.token)
    try:
        intent = _record_intent(scope, invitation, role, delivery)
        if delivery == "email":
            _send(invitation.invited_email, scope.workspace, link, invitation.expires_at)
    except Exception:
        # Leave no usable invitation behind: not described, or not delivered.
        _revoke_quietly(scope, invitation.id)
        raise
    return Created(
        invitation=_view(invitation, intent),
        link=link if delivery == "manual" else None,
    )


def _revoke_quietly(scope: Scope, invitation_id: uuid.UUID) -> None:
    """Clean-up after a failed delivery or intent write; the original error
    is what the caller reports."""
    try:
        revoke_invitation(scope.workspace, invitation_id, caller=UserCaller(scope.actor))
    except Exception as exc:  # noqa: BLE001 - the original failure matters more
        # IDs and the error class only: never the link, token or address.
        _log.warning(
            "invitation_cleanup_revoke_failed",
            extra={
                "tenant_id": str(scope.workspace),
                "invitation_id": str(invitation_id),
                "error": type(exc).__name__,
            },
        )


def _record_intent(
    scope: Scope, invitation: Invitation, role: Role, delivery: str
) -> InvitationIntent:
    intent = InvitationIntent(
        tenant_id=scope.workspace,
        invitation_id=invitation.id,
        role=role.value,
        invited_by_user_id=scope.actor,
        delivery=delivery,
        created_at=datetime.now(UTC),
    )
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            session.add(intent)
            session.flush()
            record_in_transaction(
                session,
                caller=UserCaller(scope.actor),
                tenant_id=scope.workspace,
                action=f"{RESOURCE}.intent_recorded",
                resource_type=RESOURCE,
                resource_id=str(invitation.id),
                metadata={"role": role.value, "delivery": delivery},
            )
            session.expunge(intent)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    return intent


def revoke(scope: Scope, invitation_id: uuid.UUID) -> dict[str, Any]:
    try:
        invitation = revoke_invitation(
            scope.workspace, invitation_id, caller=UserCaller(scope.actor)
        )
    except InvitationNotFoundError:
        raise _refused(404, "invitation_not_found") from None
    except InvitationAlreadyAcceptedError:
        raise _refused(409, "invitation_accepted") from None
    except InvitationNotAuthorizedError:
        raise _refused(403, "not_authorized") from None
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    return _view(invitation, _intents(scope).get(invitation.id))
