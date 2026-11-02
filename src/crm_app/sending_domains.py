"""Customer-owned sending domains and sender identities (decision P6-D).

- Owners and Admins (`crm_app.workspace:update`) register a domain the
  workspace owns. A domain belongs to at most one workspace on the platform
  (global `sending_domain_index`). With a provider configured, registering
  creates the domain at Resend and stores exactly the DNS records Resend
  returns; "verify" asks Resend to check them; Resend's signed
  `domain.updated` events carry the result (`apply_event`).
- Sender identities are addresses on the workspace's own domains, allowed
  for conversation mail, campaign mail or both, one default per stream.
  An identity sends only while it is active and its domain is `verified`
  by the provider (`sender_valid`): a workspace can never send as an
  unverified domain or another workspace's domain.
- Removing a domain removes its identities and frees the domain; emails
  queued with one of its identities are not sent from another address.

The Resend adapter (`ResendDomains`) uses SaaS-OS's egress client, which
sends POST only: it can create and verify a domain, but not read or delete
one (`saas-os-gaps.md`, items 2 and 3); state changes arrive by webhook,
and a removed domain is left at Resend for an operator to delete. It is
used only when `EMAIL_CUSTOMER_DOMAINS_ENABLED` is on, never in production
(creating Resend configuration there is not authorized).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    is_transaction_conflict,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app.domains import email_streams as streams
from crm_app.domains import sending_domains as rules
from crm_app.domains.records import InvalidValue
from crm_app.models import SenderIdentity, SendingDomain, SendingDomainIndex
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)
from crm_app.settings import email_parent_domain

RESOURCE = "crm_app.sending_domain"
DOMAINS_MAX = 10
# An unverified domain holds its name this long (security review 13-H3).
CLAIM_DAYS = timedelta(days=7)
IDENTITIES_MAX = 50
FLAG = "EMAIL_CUSTOMER_DOMAINS_ENABLED"
RESEND_DOMAINS_URL = "https://api.resend.com/domains"

Item = dict[str, Any]


class ProviderError(Exception):
    """The provider refused or did not answer; `code` is short and fixed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DomainProvider(Protocol):
    def create(self, name: str) -> rules.ProviderDomain: ...

    def verify(self, provider_id: str) -> None: ...


class ResendDomains:
    """Resend's Domains API over SaaS-OS's egress client (POST only)."""

    def __init__(self, client: Any = None) -> None:
        from saas_os.infra.secrets import get_secrets_provider  # noqa: PLC0415

        api_key = get_secrets_provider().get("RESEND_API_KEY")
        if not api_key or not api_key.isascii() or any(c.isspace() for c in api_key):
            raise ProviderError("not_configured")
        self._api_key = api_key
        if client is None:
            from saas_os.infra.egress import (  # noqa: PLC0415
                StrictEgressClient,
                StrictEgressPolicy,
                default_resolver,
                get_egress_proxy,
            )

            policy = StrictEgressPolicy(
                connect_timeout_seconds=10.0,
                read_timeout_seconds=10.0,
                max_response_bytes=64 * 1024,
            )
            proxy = get_egress_proxy()
            client = (
                StrictEgressClient(policy, resolver=default_resolver, proxy=proxy)
                if proxy is not None
                else StrictEgressClient(policy, resolver=default_resolver)
            )
        self._client = client

    def _post(self, url: str, payload: dict[str, Any]) -> object:
        from saas_os.infra.egress import Deadline, EgressError  # noqa: PLC0415

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        content = json.dumps(payload).encode("utf-8")

        async def call() -> Any:
            return await self._client.post(
                url, headers=headers, content=content, deadline=Deadline.after(15)
            )

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                response = asyncio.run(call())
            else:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    response = pool.submit(asyncio.run, call()).result()
        except EgressError:
            raise ProviderError("unreachable") from None
        if not 200 <= response.status_code < 300:
            code = "rate_limited" if response.status_code == 429 else "refused"
            raise ProviderError(code)
        try:
            return json.loads(response.body or b"{}")
        except ValueError:
            raise ProviderError("malformed_answer") from None

    def create(self, name: str) -> rules.ProviderDomain:
        answer = self._post(
            RESEND_DOMAINS_URL,
            {"name": name, "capabilities": {"sending": "enabled", "receiving": "disabled"}},
        )
        try:
            return rules.provider_domain(answer)
        except rules.ProviderAnswerError:
            raise ProviderError("malformed_answer") from None

    def verify(self, provider_id: str) -> None:
        self._post(f"{RESEND_DOMAINS_URL}/{provider_id}/verify", {})


def configured_provider() -> DomainProvider | None:
    """Resend's Domains API when switched on outside production; else none."""
    values = os.environ
    if values.get("ENVIRONMENT", "").strip().lower() == "production":
        return None
    if values.get(FLAG, "").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        return ResendDomains()
    except ProviderError:
        return None


class DomainRuleError(RecordError):
    status, code = 422, "invalid_sending_domain"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class DomainInUseError(RecordError):
    """Another workspace, or this one, already registered the domain."""

    status, code = 409, "domain_in_use"


class DomainLimitError(RecordError):
    status, code = 409, "sending_domain_limit"


class IdentityConflictError(RecordError):
    status, code = 409, "identity_conflict"


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


def _audit(session: Session, scope: Scope, verb: str, resource_id: uuid.UUID, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(resource_id),
        metadata=meta,
    )


def _identity_item(row: SenderIdentity, verified: bool) -> Item:
    return {
        "id": row.id,
        "address": row.address,
        "for_conversation": row.for_conversation,
        "for_campaign": row.for_campaign,
        "default_conversation": row.default_conversation,
        "default_campaign": row.default_campaign,
        "status": row.status,
        "usable": row.status == "active" and verified,
        "version": row.version,
    }


def _claim_expires(row: SendingDomain) -> datetime | None:
    """When an unverified claim lapses (13-H3); None once ever verified."""
    if row.verified_at is not None or row.status == "expired":
        return None
    return row.created_at + CLAIM_DAYS


def _domain_item(row: SendingDomain, identities: list[SenderIdentity]) -> Item:
    verified = row.status == "verified"
    return {
        "id": row.id,
        "domain": row.domain,
        "status": row.status,
        "records": list(row.records),
        "last_error": row.last_error,
        "checked_at": row.checked_at,
        "created_at": row.created_at,
        "claim_expires_at": _claim_expires(row),
        "version": row.version,
        "identities": [_identity_item(i, verified) for i in identities],
    }


def _load(session: Session, scope: Scope, domain_id: uuid.UUID) -> SendingDomain:
    row = session.execute(
        select(SendingDomain)
        .where(SendingDomain.tenant_id == scope.workspace, SendingDomain.id == domain_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _identities(
    session: Session, workspace: uuid.UUID, domain_id: uuid.UUID
) -> list[SenderIdentity]:
    return list(
        session.execute(
            select(SenderIdentity)
            .where(
                SenderIdentity.tenant_id == workspace,
                SenderIdentity.sending_domain_id == domain_id,
            )
            .order_by(SenderIdentity.created_at, SenderIdentity.id)
        ).scalars()
    )


def _set_index_provider(name: str, provider_id: str | None) -> None:
    with session_scope() as session:
        index = session.get(SendingDomainIndex, name)
        if index is not None:
            index.provider_id = provider_id


# --- Domains -----------------------------------------------------------------------------


def list_domains(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(SendingDomain)
            .where(SendingDomain.tenant_id == scope.workspace)
            .order_by(SendingDomain.created_at, SendingDomain.id)
        ).scalars()
        return [_domain_item(row, _identities(session, scope.workspace, row.id)) for row in rows]


def _apply_provider(row: SendingDomain, answer: rules.ProviderDomain) -> None:
    row.provider_id = answer.provider_id
    row.status = answer.status
    if answer.status == "verified" and row.verified_at is None:
        row.verified_at = _now()
    if answer.records is not None:
        row.records = [record.as_dict() for record in answer.records]


def _create_at_provider(row: SendingDomain, provider: DomainProvider | None) -> None:
    if provider is None:
        row.last_error = "provider_unavailable"
        return
    try:
        _apply_provider(row, provider.create(row.domain))
    except ProviderError as exc:
        row.last_error = exc.code
    else:
        row.last_error = None
        _set_index_provider(row.domain, row.provider_id)


def register(scope: Scope, domain: str, *, provider: DomainProvider | None = None) -> Item:
    """Register a domain; with a provider, create it there and keep its
    records. A provider failure keeps the domain `not_registered` with the
    reason; "verify" tries the registration again."""
    try:
        name = rules.domain(domain, parent=email_parent_domain())
    except InvalidValue as exc:
        raise DomainRuleError(str(exc)) from None
    provider = provider or configured_provider()
    domain_id = uuid.uuid4()
    try:
        with session_scope() as global_session:
            global_session.add(
                SendingDomainIndex(
                    domain=name,
                    workspace_id=scope.workspace,
                    sending_domain_id=domain_id,
                    claimed_at=_now(),
                )
            )
    except IntegrityError:
        raise DomainInUseError from None

    def business(session: Session) -> Item:
        count = len(
            session.execute(
                select(SendingDomain.id).where(SendingDomain.tenant_id == scope.workspace)
            ).all()
        )
        if count >= DOMAINS_MAX:
            raise DomainLimitError
        now = _now()
        row = SendingDomain(
            id=domain_id,
            tenant_id=scope.workspace,
            domain=name,
            status="not_registered",
            records=[],
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        _create_at_provider(row, provider)
        row.checked_at = now
        session.add(row)
        session.flush()
        _audit(session, scope, "registered", row.id, status=row.status, error=row.last_error)
        return _domain_item(row, [])

    try:
        return _transaction(scope, business)
    except BaseException:
        # The workspace's row did not commit: free the domain again.
        with session_scope() as session:
            index = session.get(SendingDomainIndex, name)
            if index is not None and index.sending_domain_id == domain_id:
                session.delete(index)
        raise


def verify(
    scope: Scope,
    domain_id: uuid.UUID,
    *,
    expected_version: int,
    provider: DomainProvider | None = None,
) -> Item:
    """Ask the provider to check the domain's records (or to register it,
    if that failed before); the result arrives as a signed event."""
    provider = provider or configured_provider()

    def business(session: Session) -> Item:
        row = _load(session, scope, domain_id)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if row.status == "expired":
            raise DomainRuleError("domain: the claim expired; remove it and register it again")
        now = _now()
        if provider is None or row.provider_id is None:
            _create_at_provider(row, provider)
        else:
            try:
                provider.verify(row.provider_id)
            except ProviderError as exc:
                row.last_error = exc.code
            else:
                row.last_error = None
                if row.status != "verified":
                    row.status = "pending"
        row.checked_at, row.updated_at, row.version = now, now, row.version + 1
        _audit(session, scope, "verify_requested", row.id, status=row.status, error=row.last_error)
        return _domain_item(row, _identities(session, scope.workspace, row.id))

    return _transaction(scope, business)


def remove(scope: Scope, domain_id: uuid.UUID) -> None:
    def business(session: Session) -> str:
        row = _load(session, scope, domain_id)
        name = row.domain
        _audit(session, scope, "removed", row.id, provider_registered=row.provider_id is not None)
        session.delete(row)
        return name

    name = _transaction(scope, business)
    with session_scope() as session:
        index = session.get(SendingDomainIndex, name)
        if index is not None and index.sending_domain_id == domain_id:
            session.delete(index)


def apply_event(event: rules.DomainEvent) -> str:
    """Record a provider's signed domain event; returns `applied` or
    `unknown` (no workspace registered that provider id)."""
    with session_scope() as session:
        index = session.execute(
            select(SendingDomainIndex).where(
                SendingDomainIndex.provider_id == event.domain.provider_id
            )
        ).scalar_one_or_none()
        found = (index.workspace_id, index.sending_domain_id, index.domain) if index else None
    if found is None:
        return "unknown"
    workspace, domain_id, name = found
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            select(SendingDomain)
            .where(SendingDomain.tenant_id == workspace, SendingDomain.id == domain_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None or row.provider_id != event.domain.provider_id:
            return "unknown"
        # Defense in depth (13-H3): the event must name the registered domain,
        # and an event older than one already applied changes nothing.
        if event.domain.name is not None and event.domain.name != name:
            return "unknown"
        moment = event.occurred_at
        if moment is not None and row.event_at is not None and moment <= row.event_at:
            return "stale"
        now = _now()
        if moment is not None:
            row.event_at = moment
        if event.type == "domain.deleted":
            row.status, row.provider_id = "not_registered", None
            row.last_error = "deleted_at_provider"
        else:
            _apply_provider(row, event.domain)
            row.last_error = None
        row.checked_at, row.updated_at, row.version = now, now, row.version + 1
    if event.type == "domain.deleted":
        _set_index_provider(name, None)
    return "applied"


# --- Sender identities ---------------------------------------------------------------------


def _check_flags(values: dict[str, Any]) -> None:
    if not (values["for_conversation"] or values["for_campaign"]):
        raise DomainRuleError("identity: allow conversation mail, campaign mail or both")
    if (values["default_conversation"] and not values["for_conversation"]) or (
        values["default_campaign"] and not values["for_campaign"]
    ):
        raise DomainRuleError("identity: a default must be allowed for its stream")


def _clear_defaults(
    session: Session, workspace: uuid.UUID, *, conversation: bool, campaign: bool
) -> None:
    if not (conversation or campaign):
        return
    rows = session.execute(
        select(SenderIdentity).where(SenderIdentity.tenant_id == workspace).with_for_update()
    ).scalars()
    for row in rows:
        if conversation and row.default_conversation:
            row.default_conversation = False
        if campaign and row.default_campaign:
            row.default_campaign = False
    session.flush()


def add_identity(
    scope: Scope, domain_id: uuid.UUID, *, local_part: str, flags: dict[str, bool]
) -> Item:
    values = {
        "for_conversation": flags.get("for_conversation", False),
        "for_campaign": flags.get("for_campaign", False),
        "default_conversation": flags.get("default_conversation", False),
        "default_campaign": flags.get("default_campaign", False),
    }
    _check_flags(values)

    def business(session: Session) -> Item:
        domain = _load(session, scope, domain_id)
        try:
            address = rules.address(local_part, domain.domain)
        except InvalidValue as exc:
            raise DomainRuleError(str(exc)) from None
        count = len(
            session.execute(
                select(SenderIdentity.id).where(SenderIdentity.tenant_id == scope.workspace)
            ).all()
        )
        if count >= IDENTITIES_MAX:
            raise DomainLimitError
        taken = session.execute(
            select(SenderIdentity.id).where(
                SenderIdentity.tenant_id == scope.workspace, SenderIdentity.address == address
            )
        ).first()
        if taken is not None:
            raise IdentityConflictError
        _clear_defaults(
            session,
            scope.workspace,
            conversation=values["default_conversation"],
            campaign=values["default_campaign"],
        )
        now = _now()
        row = SenderIdentity(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            sending_domain_id=domain.id,
            address=address,
            status="active",
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
            **values,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "identity_added", row.id, domain_id=str(domain.id))
        return _identity_item(row, domain.status == "verified")

    return _transaction(scope, business)


def update_identity(
    scope: Scope, identity_id: uuid.UUID, changes: dict[str, Any], *, expected_version: int
) -> Item:
    def business(session: Session) -> Item:
        row = session.execute(
            select(SenderIdentity)
            .where(SenderIdentity.tenant_id == scope.workspace, SenderIdentity.id == identity_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise RecordNotFoundError
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        values = {
            name: changes.get(name, getattr(row, name))
            for name in (
                "for_conversation",
                "for_campaign",
                "default_conversation",
                "default_campaign",
                "status",
            )
        }
        if values["status"] not in ("active", "disabled"):
            raise DomainRuleError("status: active or disabled")
        _check_flags(values)
        _clear_defaults(
            session,
            scope.workspace,
            conversation=bool(values["default_conversation"]) and not row.default_conversation,
            campaign=bool(values["default_campaign"]) and not row.default_campaign,
        )
        for name, value in values.items():
            setattr(row, name, value)
        row.updated_at, row.version = _now(), row.version + 1
        domain = session.get(SendingDomain, row.sending_domain_id)
        _audit(session, scope, "identity_updated", row.id, status=row.status)
        return _identity_item(row, domain is not None and domain.status == "verified")

    return _transaction(scope, business)


def remove_identity(scope: Scope, identity_id: uuid.UUID) -> None:
    def business(session: Session) -> None:
        row = session.execute(
            select(SenderIdentity)
            .where(SenderIdentity.tenant_id == scope.workspace, SenderIdentity.id == identity_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise RecordNotFoundError
        _audit(session, scope, "identity_removed", row.id)
        session.delete(row)

    _transaction(scope, business)


# --- Sending -------------------------------------------------------------------------------


def _allowed(identity: SenderIdentity, stream: streams.Stream) -> bool:
    if stream is streams.Stream.CONVERSATION:
        return identity.for_conversation
    if stream is streams.Stream.CAMPAIGN:
        return identity.for_campaign
    return False


def _with_domain(session: Session, workspace: uuid.UUID, condition: Any) -> Any:
    return session.execute(
        select(SenderIdentity, SendingDomain.status)
        .join(
            SendingDomain,
            (SendingDomain.tenant_id == SenderIdentity.tenant_id)
            & (SendingDomain.id == SenderIdentity.sending_domain_id),
        )
        .where(SenderIdentity.tenant_id == workspace, condition)
    ).first()


def default_sender(
    session: Session, workspace: uuid.UUID, stream: streams.Stream
) -> tuple[uuid.UUID, str] | None:
    """The workspace's default identity for a stream, when it is usable."""
    if stream is streams.Stream.TRANSACTIONAL:
        return None
    column = (
        SenderIdentity.default_conversation
        if stream is streams.Stream.CONVERSATION
        else SenderIdentity.default_campaign
    )
    row = _with_domain(session, workspace, column.is_(True))
    if row is None:
        return None
    identity, domain_status = row
    if identity.status != "active" or domain_status != "verified":
        return None
    return identity.id, identity.address


def sender_valid(
    session: Session,
    workspace: uuid.UUID,
    identity_id: uuid.UUID,
    address: str,
    stream: streams.Stream,
) -> bool:
    """Whether an email queued with this identity may be sent from it now:
    the identity still exists in this workspace with the same address, is
    active, is allowed for the stream, and its domain is verified."""
    row = _with_domain(session, workspace, SenderIdentity.id == identity_id)
    if row is None:
        return False
    identity, domain_status = row
    return (
        identity.address == address
        and identity.status == "active"
        and _allowed(identity, stream)
        and domain_status == "verified"
    )


def release_unverified(limit: int = 200) -> int:
    """Free names claimed longer than `CLAIM_DAYS` ago by domains never
    verified (security review 13-H3: a workspace cannot squat a business's
    domain). The workspace keeps its row as `expired`; the provider-side
    domain, if any, is left for an operator (no DELETE, saas-os-gaps 2-3).
    Returns how many were released."""
    cutoff = _now() - CLAIM_DAYS
    with session_scope() as session:
        claims = [
            (row.domain, row.workspace_id, row.sending_domain_id)
            for row in session.execute(
                select(SendingDomainIndex)
                .where(SendingDomainIndex.claimed_at <= cutoff)
                .order_by(SendingDomainIndex.claimed_at)
                .limit(limit)
            ).scalars()
        ]
    released = 0
    for name, workspace, domain_id in claims:
        with tenant_session_scope(workspace) as session:
            row = session.execute(
                select(SendingDomain)
                .where(SendingDomain.tenant_id == workspace, SendingDomain.id == domain_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is not None and (row.verified_at is not None or row.created_at > cutoff):
                continue
            if row is not None:
                now = _now()
                row.status, row.last_error = "expired", "claim_expired"
                row.updated_at, row.version = now, row.version + 1
        with session_scope() as session:
            index = session.get(SendingDomainIndex, name)
            if index is not None and index.sending_domain_id == domain_id:
                session.delete(index)
                released += 1
    return released


def forget_workspace(tenant_id: uuid.UUID) -> bool:
    """Remove a purged workspace's index rows; True when none remain."""
    from saas_os.infra.db import delete  # noqa: PLC0415

    with session_scope() as session:
        session.execute(
            delete(SendingDomainIndex).where(SendingDomainIndex.workspace_id == tenant_id)
        )
    with session_scope() as session:
        left = session.execute(
            select(SendingDomainIndex.domain)
            .where(SendingDomainIndex.workspace_id == tenant_id)
            .limit(1)
        ).first()
    return left is None
