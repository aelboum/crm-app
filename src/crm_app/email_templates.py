"""Reusable email templates (decision P7-T).

A template is a name, a one-line subject and a plain-text body with the
campaign placeholders (`{{first_name}}`, `{{last_name}}`, checked by
`crm_app.domains.campaigns`). It sends nothing: the campaign editor copies
it into a draft (which then needs its own approval, P7-C), and the reply
composer asks for it rendered for the conversation's contact. At most
`TEMPLATES_MAX` per workspace; names are unique per workspace. Every read
and write runs in `tenant_session_scope(workspace)` with an explicit
workspace predicate; changes are audited without their text.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import campaigns as rules
from crm_app.domains.records import InvalidValue
from crm_app.models import Contact, EmailTemplate
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.email_template"
TEMPLATES_MAX = 100
Item = dict[str, Any]


class TemplateRuleError(RecordError):
    """A name, subject or body the rules refuse; `detail` names the rule."""

    status, code = 422, "invalid_template"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class TemplateNameTakenError(RecordError):
    status, code = 409, "template_name_taken"


class TemplateLimitError(RecordError):
    status, code = 409, "template_limit"


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "email_template_name_key":
            raise TemplateNameTakenError from None
        raise
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _clean(values: Mapping[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    try:
        if "name" in values:
            cleaned["name"] = rules.name(str(values["name"]))
        if "subject" in values:
            cleaned["subject"] = rules.subject(str(values["subject"]))
        if "body" in values:
            cleaned["body"] = rules.body(str(values["body"]))
    except InvalidValue as exc:
        raise TemplateRuleError(str(exc)) from None
    return cleaned


def _item(row: EmailTemplate) -> Item:
    return {
        "id": row.id,
        "name": row.name,
        "subject": row.subject,
        "body": row.body,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def _audit(session: Session, scope: Scope, verb: str, template_id: uuid.UUID, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(template_id),
        metadata=meta,
    )


def _load(session: Session, scope: Scope, template_id: uuid.UUID, *, lock: bool) -> EmailTemplate:
    query = select(EmailTemplate).where(
        EmailTemplate.tenant_id == scope.workspace, EmailTemplate.id == template_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def list_templates(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(EmailTemplate)
            .where(EmailTemplate.tenant_id == scope.workspace)
            .order_by(EmailTemplate.name, EmailTemplate.id)
        ).scalars()
        return [_item(row) for row in rows]


def create(scope: Scope, values: Mapping[str, Any]) -> Item:
    cleaned = _clean(values)
    if set(cleaned) != {"name", "subject", "body"}:
        raise TemplateRuleError("name, subject and body are required")

    def apply(session: Session) -> Item:
        # Creations take turns, so concurrent ones never pass the limit.
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        count = len(
            session.execute(
                select(EmailTemplate.id).where(EmailTemplate.tenant_id == scope.workspace)
            ).all()
        )
        if count >= TEMPLATES_MAX:
            raise TemplateLimitError
        now = _now()
        row = EmailTemplate(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
            **cleaned,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", row.id)
        return _item(row)

    return _transaction(scope, apply)


def update(
    scope: Scope, template_id: uuid.UUID, changes: Mapping[str, Any], *, expected_version: int
) -> Item:
    cleaned = _clean(changes)

    def apply(session: Session) -> Item:
        row = _load(session, scope, template_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        changed = sorted(name for name, value in cleaned.items() if getattr(row, name) != value)
        if not changed:
            return _item(row)
        for name in changed:
            setattr(row, name, cleaned[name])
        row.updated_by_user_id, row.updated_at = scope.actor, _now()
        row.version += 1
        session.flush()
        _audit(session, scope, "updated", row.id, fields=changed)
        return _item(row)

    return _transaction(scope, apply)


def remove(scope: Scope, template_id: uuid.UUID) -> None:
    def apply(session: Session) -> None:
        row = _load(session, scope, template_id, lock=True)
        session.delete(row)
        session.flush()
        _audit(session, scope, "deleted", template_id)

    _transaction(scope, apply)


def render(scope: Scope, template_id: uuid.UUID, contact_id: uuid.UUID) -> dict[str, str]:
    """The template's subject and body with the contact's placeholders
    filled in (literally; nothing is evaluated). Both must be this
    workspace's."""

    def read(session: Session) -> dict[str, str]:
        row = _load(session, scope, template_id, lock=False)
        contact = session.execute(
            select(Contact).where(Contact.tenant_id == scope.workspace, Contact.id == contact_id)
        ).scalar_one_or_none()
        if contact is None:
            raise RecordNotFoundError
        values = {"first_name": contact.first_name, "last_name": contact.last_name}
        return {
            "subject": rules.render(row.subject, values),
            "body": rules.render(row.body, values),
        }

    return _transaction(scope, read)
