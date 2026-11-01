"""Custom domains for hosted pages (decision P12-D).

- A member who may update the workspace claims a hostname; the claim gets
  a random token and is `pending` for at most `CLAIM_DAYS` days, during
  which the domain's owner publishes `_leadstack-challenge.<host>` TXT
  `leadstack-verification=<token>`.
- `check` looks the record up through a `TxtResolver`; when it holds the
  token the claim becomes `verified`, and only then does the global index
  map the hostname to the workspace. A unique index lets one workspace
  hold a verified hostname at a time; another workspace's pending claim
  never blocks the owner, and an expired claim must be made again with a
  new token.
- `recheck_due` (the maintenance command) checks verified domains again
  every day; one whose record is gone becomes `lapsed` and stops mapping,
  so a domain that changed hands is never served for the old workspace.
  It also removes expired pending claims.
- Removing a claim deletes its index row at once.
- `workspace_for_host` answers which workspace a request's Host belongs
  to: verified hostnames only.

No `TxtResolver` is configured yet: looking up DNS needs either a new
dependency (`dnspython`) or an external DNS-over-HTTPS service, which is an
owner decision (P12-D). Until then a check records `resolver_unavailable`
and nothing is verified; tests use a test double.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
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

from crm_app.domains import custom_domains as rules
from crm_app.domains import websites as site_rules
from crm_app.domains.records import InvalidValue
from crm_app.models import CustomDomain, CustomDomainIndex
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.custom_domain"
CLAIM_DAYS = 7
RECHECK_HOURS = 24
DOMAINS_MAX = 20
BATCH = 200

Item = dict[str, Any]


class ResolverError(Exception):
    """A DNS lookup that did not answer; `code` is a short fixed reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TxtResolver(Protocol):
    def txt(self, name: str) -> list[str]:
        """The TXT strings at `name` (empty when there are none); raises
        `ResolverError` when the lookup fails."""
        ...


def configured_resolver() -> TxtResolver | None:
    """The deployment's DNS resolver: none yet (see the module note)."""
    return None


class DomainRuleError(RecordError):
    status, code = 422, "invalid_domain"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class DomainTakenError(RecordError):
    """This workspace already claims the hostname."""

    status, code = 409, "domain_already_added"


class DomainLimitError(RecordError):
    status, code = 409, "domain_limit"


class ClaimExpiredError(RecordError):
    status, code = 409, "claim_expired"


def _now() -> datetime:
    return datetime.now(UTC)


def _app_host() -> str | None:
    origin = site_rules.request_origin(os.environ.get("PUBLIC_APP_ORIGIN"))
    return origin.split("://", 1)[1].split(":", 1)[0] if origin else None


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _audit(session: Session, scope: Scope, verb: str, row: CustomDomain) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"status": row.status, "error": row.last_error},
    )


def _item(row: CustomDomain) -> Item:
    return {
        "id": row.id,
        "hostname": row.hostname,
        "status": row.status,
        "record_name": rules.challenge_name(row.hostname),
        "record_value": rules.challenge_value(row.token),
        "expires_at": row.expires_at if row.status == "pending" else None,
        "verified_at": row.verified_at,
        "checked_at": row.checked_at,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "version": row.version,
    }


def _load(session: Session, scope: Scope, domain_id: uuid.UUID) -> CustomDomain:
    row = session.execute(
        select(CustomDomain)
        .where(CustomDomain.tenant_id == scope.workspace, CustomDomain.id == domain_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _index(domain_id: uuid.UUID, **values: Any) -> None:
    with session_scope() as session:
        row = session.get(CustomDomainIndex, domain_id)
        if row is not None:
            for name, value in values.items():
                setattr(row, name, value)


def _drop_index(domain_id: uuid.UUID) -> None:
    with session_scope() as session:
        row = session.get(CustomDomainIndex, domain_id)
        if row is not None:
            session.delete(row)


# --- Reads ------------------------------------------------------------------------------


def list_domains(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(CustomDomain)
            .where(CustomDomain.tenant_id == scope.workspace)
            .order_by(CustomDomain.created_at, CustomDomain.id)
        ).scalars()
        return [_item(row) for row in rows]


def workspace_for_host(host: str) -> uuid.UUID | None:
    """The workspace a verified hostname belongs to, or None."""
    try:
        name = rules.hostname(host.split(":", 1)[0])
    except InvalidValue:
        return None
    with session_scope() as session:
        row = session.execute(
            select(CustomDomainIndex.workspace_id).where(
                CustomDomainIndex.hostname == name, CustomDomainIndex.verified.is_(True)
            )
        ).first()
    return None if row is None else row[0]


# --- Writes -----------------------------------------------------------------------------


def add(scope: Scope, hostname: str) -> Item:
    try:
        host = rules.hostname(hostname, app_host=_app_host())
    except InvalidValue as exc:
        raise DomainRuleError(str(exc)) from None

    def business(session: Session) -> Item:
        existing = list(
            session.execute(
                select(CustomDomain.hostname).where(CustomDomain.tenant_id == scope.workspace)
            ).scalars()
        )
        if host in existing:
            raise DomainTakenError
        if len(existing) >= DOMAINS_MAX:
            raise DomainLimitError
        now = _now()
        row = CustomDomain(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            hostname=host,
            token=rules.new_token(),
            status="pending",
            expires_at=now + timedelta(days=CLAIM_DAYS),
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        # Index first, in its own transaction: if this one rolls back, the
        # unverified orphan maps nothing.
        with session_scope() as global_session:
            global_session.add(
                CustomDomainIndex(
                    domain_id=row.id, hostname=host, workspace_id=scope.workspace, verified=False
                )
            )
        session.add(row)
        session.flush()
        _audit(session, scope, "added", row)
        return _item(row)

    return _transaction(scope, business)


def _verify(row: CustomDomain, resolver: TxtResolver | None, now: datetime) -> bool:
    """Look the record up and update `row`; True when it proves ownership."""
    row.checked_at = now
    if resolver is None:
        row.last_error = "resolver_unavailable"
        return False
    try:
        records = resolver.txt(rules.challenge_name(row.hostname))
    except ResolverError as exc:
        row.last_error = exc.code if exc.code.isascii() else "lookup_failed"
        return False
    if not rules.proves(records, row.token):
        row.last_error = "record_not_found"
        return False
    row.last_error = None
    return True


def check(
    scope: Scope,
    domain_id: uuid.UUID,
    *,
    expected_version: int,
    resolver: TxtResolver | None = None,
) -> Item:
    """Look up a claim's TXT record now and verify it when it holds the
    token. A hostname another workspace holds verified stays pending with
    `claimed_elsewhere`."""
    resolver = resolver or configured_resolver()

    def business(session: Session) -> Item:
        row = _load(session, scope, domain_id)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        now = _now()
        if row.status == "pending" and row.expires_at is not None and row.expires_at < now:
            raise ClaimExpiredError
        proved = _verify(row, resolver, now)
        if proved and row.status != "verified":
            try:
                _index(row.id, verified=True)
            except IntegrityError:
                row.last_error = "claimed_elsewhere"
            else:
                row.status, row.verified_at, row.expires_at = "verified", now, None
        elif not proved and row.status == "verified" and row.last_error == "record_not_found":
            row.status = "lapsed"
            _index(row.id, verified=False)
        row.updated_at, row.version = now, row.version + 1
        _audit(session, scope, "checked", row)
        return _item(row)

    return _transaction(scope, business)


def remove(scope: Scope, domain_id: uuid.UUID) -> None:
    def business(session: Session) -> None:
        row = _load(session, scope, domain_id)
        _drop_index(row.id)
        _audit(session, scope, "removed", row)
        session.delete(row)

    _transaction(scope, business)


# --- Maintenance ------------------------------------------------------------------------


def recheck_due(resolver: TxtResolver | None = None, *, limit: int = BATCH) -> dict[str, int]:
    """Check verified domains not checked for `RECHECK_HOURS` and lapse
    those whose record is gone; delete expired pending claims. Returns
    counts. A lookup that fails (or no resolver) never lapses a domain."""
    resolver = resolver or configured_resolver()
    now = _now()
    with session_scope() as session:
        rows = session.execute(
            select(CustomDomainIndex.domain_id, CustomDomainIndex.workspace_id).limit(limit)
        ).all()
    counts = {"rechecked": 0, "lapsed": 0, "expired": 0}
    for domain_id, workspace in rows:
        with tenant_session_scope(workspace) as session:
            row = session.execute(
                select(CustomDomain)
                .where(CustomDomain.tenant_id == workspace, CustomDomain.id == domain_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                continue
            if row.status == "pending" and row.expires_at and row.expires_at < now:
                _drop_index(row.id)
                session.delete(row)
                counts["expired"] += 1
                continue
            due = row.checked_at is None or row.checked_at < now - timedelta(hours=RECHECK_HOURS)
            if row.status != "verified" or not due or resolver is None:
                continue
            counts["rechecked"] += 1
            if not _verify(row, resolver, now) and row.last_error == "record_not_found":
                row.status = "lapsed"
                row.updated_at, row.version = now, row.version + 1
                _index(row.id, verified=False)
                counts["lapsed"] += 1
    return counts


def forget_workspace(tenant_id: uuid.UUID) -> bool:
    """Remove a purged workspace's index rows; True when none remain."""
    from saas_os.infra.db import delete  # noqa: PLC0415

    with session_scope() as session:
        session.execute(
            delete(CustomDomainIndex).where(CustomDomainIndex.workspace_id == tenant_id)
        )
    with session_scope() as session:
        left = session.execute(
            select(CustomDomainIndex.domain_id)
            .where(CustomDomainIndex.workspace_id == tenant_id)
            .limit(1)
        ).first()
    return left is None
