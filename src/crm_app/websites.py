"""Websites (decision P12-W): the external sites whose pages may submit a
workspace's published forms.

Members who manage forms (`crm_app.form:manage`) add, edit, disable and
remove websites; members who read forms see them. A website is a name and
its allowed origins (`crm_app.domains.websites.origins`). The public form
routes ask `allowed_site` whether a request's `Origin` belongs to an
active website of the form's workspace; only then is a cross-site
submission accepted and answered with CORS headers for that origin.
Removing a website keeps its submissions, without the link. Every change
is audited with ids and counts, never the origins themselves.
"""

from __future__ import annotations

import os
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

from crm_app.domains import websites as rules
from crm_app.domains.records import InvalidValue
from crm_app.models import Website
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.website"
WEBSITES_MAX = 50

Item = dict[str, Any]


class WebsiteRuleError(RecordError):
    status, code = 422, "invalid_website"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class WebsiteLimitError(RecordError):
    status, code = 409, "website_limit"


def _now() -> datetime:
    return datetime.now(UTC)


def _local_allowed() -> bool:
    """`http://localhost` origins are for development and tests only."""
    return os.environ.get("ENVIRONMENT", "").strip().lower() in ("development", "test")


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _audit(session: Session, scope: Scope, verb: str, row: Website) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(row.id),
        metadata={"status": row.status, "origins": len(row.origins)},
    )


def _item(row: Website) -> Item:
    return {
        "id": row.id,
        "name": row.name,
        "origins": list(row.origins),
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def _clean(name: str, origins: list[str]) -> tuple[str, list[str]]:
    try:
        return rules.name(name), rules.origins(origins, allow_local=_local_allowed())
    except InvalidValue as exc:
        raise WebsiteRuleError(str(exc)) from None


def _load(session: Session, scope: Scope, website_id: uuid.UUID) -> Website:
    row = session.execute(
        select(Website)
        .where(Website.tenant_id == scope.workspace, Website.id == website_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def list_websites(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(Website)
            .where(Website.tenant_id == scope.workspace)
            .order_by(Website.created_at, Website.id)
        ).scalars()
        return [_item(row) for row in rows]


def create(scope: Scope, *, name: str, origins: list[str]) -> Item:
    clean_name, clean_origins = _clean(name, origins)

    def business(session: Session) -> Item:
        count = len(
            session.execute(
                select(Website.id).where(Website.tenant_id == scope.workspace).limit(WEBSITES_MAX)
            ).all()
        )
        if count >= WEBSITES_MAX:
            raise WebsiteLimitError
        now = _now()
        row = Website(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            name=clean_name,
            origins=clean_origins,
            status="active",
            created_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", row)
        return _item(row)

    return _transaction(scope, business)


def update(
    scope: Scope, website_id: uuid.UUID, changes: dict[str, Any], *, expected_version: int
) -> Item:
    def business(session: Session) -> Item:
        row = _load(session, scope, website_id)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        name, origins = _clean(changes.get("name", row.name), changes.get("origins", row.origins))
        status = changes.get("status", row.status)
        if status not in ("active", "disabled"):
            raise WebsiteRuleError("status: active or disabled")
        row.name, row.origins, row.status = name, origins, status
        row.updated_at, row.version = _now(), row.version + 1
        _audit(session, scope, "updated", row)
        return _item(row)

    return _transaction(scope, business)


def remove(scope: Scope, website_id: uuid.UUID) -> None:
    def business(session: Session) -> None:
        row = _load(session, scope, website_id)
        _audit(session, scope, "removed", row)
        session.delete(row)

    _transaction(scope, business)


def allowed_site(session: Session, workspace: uuid.UUID, origin: str) -> uuid.UUID | None:
    """The active website of `workspace` that allows `origin` (canonical),
    inside the caller's session, or None."""
    rows = session.execute(
        select(Website.id, Website.origins).where(
            Website.tenant_id == workspace, Website.status == "active"
        )
    ).all()
    for website_id, origins in rows:
        if origin in origins:
            return website_id
    return None


def site_for_origin(workspace: uuid.UUID, origin: str) -> uuid.UUID | None:
    with tenant_session_scope(workspace) as session:
        return allowed_site(session, workspace, origin)
