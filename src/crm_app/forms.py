"""Forms and lead capture: the service layer (decision P7-A, slice 7A).

Members' functions take a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it. Every
write takes `lock_open_tenant` and records its audit entry in the same
transaction: the form ID and field names, never the form's text.

The public side (`public_form`, `submit`) has no member: the workspace comes
from the address and is only a lookup key. An unknown workspace or key, a
draft form and a closed or suspended workspace are all `FormNotFoundError`.
A submission creates or matches a contact in one transaction, acting as the
form's contact owner (P7-A 6, 8); a matched contact gains at most the
form's tag, never a changed field.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.idempotency import run_idempotent
from saas_os.core.identity import get_membership
from saas_os.core.tenancy import (
    PRINCIPAL_INACCESSIBLE_STATUSES,
    TenantClosedError,
    TenantNotFoundError,
    TenantStatus,
    lock_open_tenant,
    require_open_tenant,
)
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import forms as rules
from crm_app.domains import paging
from crm_app.domains.records import InvalidValue
from crm_app.models import ConsentRecord, Contact, ContactTag, Form, FormSubmission, Tag
from crm_app.records import (
    CONTACT,
    MAX_RECORD_TAGS,
    TOTAL_CAP,
    ConstraintViolationError,
    DuplicateRecordError,
    InvalidReferenceError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    _after,
    _audit,
    _Event,
    _OrderKey,
    _touch,
    check_owner,
    history_entry,
    insert_record,
)

RESOURCE = "crm_app.form"
MAX_FORMS = 200
FIELDS = (
    "name",
    "fields",
    "tag_id",
    "thank_you",
    "consent_text",
    "contact_owner_user_id",
    "status",
)
_ACTIVE = "active"
_CONSENT_CHANNEL = "email"


class FormNotFoundError(RecordError):
    status, code = 404, "form_not_found"


class FormLimitError(RecordError):
    status, code = 409, "form_limit"


class FormRuleError(RecordError):
    """A form the rules refuse: the code and, for a field, its position."""

    status = 422

    def __init__(self, code: str, index: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.index = index


class AnswersError(RecordError):
    """A visitor's answers the form refuses: a code per field key. Keys are
    the form's configuration, never what the visitor typed."""

    status, code = 422, "invalid_answers"

    def __init__(self, errors: Mapping[str, str]) -> None:
        super().__init__(self.code)
        self.errors = dict(errors)


Item = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](workspace: uuid.UUID, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(workspace) as session:
            lock_open_tenant(session, workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "form_tag_fkey":
            raise InvalidReferenceError("tag_not_found") from None
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _form_audit(session: Session, scope: Scope, verb: str, form_id: uuid.UUID, **meta: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(form_id),
        metadata=meta,
    )


def _load(session: Session, scope: Scope, form_id: uuid.UUID, *, lock: bool) -> Form:
    query = select(Form).where(Form.tenant_id == scope.workspace, Form.id == form_id)
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise FormNotFoundError
    return row


def _tag_names(session: Session, workspace: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = session.execute(
        select(Tag.id, Tag.name).where(Tag.tenant_id == workspace, Tag.id.in_(ids))
    )
    return dict(rows.tuples().all())


def _item(row: Form, tags: Mapping[uuid.UUID, str]) -> Item:
    tag = None
    if row.tag_id is not None and row.tag_id in tags:
        tag = {"id": row.tag_id, "name": tags[row.tag_id]}
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "public_key": row.public_key,
        "fields": row.fields,
        "tag_id": row.tag_id,
        "tag": tag,
        "thank_you": row.thank_you,
        "consent_text": row.consent_text,
        "contact_owner_user_id": row.contact_owner_user_id,
        "submission_count": row.submission_count,
        "last_submission_at": row.last_submission_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_by_user_id": row.created_by_user_id,
        "updated_by_user_id": row.updated_by_user_id,
        "version": row.version,
    }


# --- Validation ----------------------------------------------------------------------


def _fields(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise FormRuleError("field_count", -1)
    try:
        return rules.fields(raw)
    except rules.FieldError as exc:
        raise FormRuleError(exc.code, exc.index) from None


def _message(raw: object, code: str, *, required: bool) -> str | None:
    if raw is not None and not isinstance(raw, str):
        raise FormRuleError(code)
    try:
        return rules.message(raw, required=required)
    except InvalidValue:
        raise FormRuleError(code) from None


def _normalised(values: Mapping[str, Any]) -> dict[str, Any]:
    """The given values as stored; names and messages are checked here so a
    refusal never echoes them."""
    result: dict[str, Any] = {}
    for name, value in values.items():
        if name == "name":
            try:
                result[name] = rules.name(value)
            except InvalidValue:
                raise FormRuleError("invalid_name") from None
        elif name == "fields":
            result[name] = _fields(value)
        elif name == "thank_you":
            result[name] = _message(value, "invalid_thank_you", required=True)
        elif name == "consent_text":
            result[name] = _message(value, "invalid_consent_text", required=False)
        elif name == "status":
            if value not in rules.STATUSES:
                raise FormRuleError("invalid_status")
            result[name] = value
        else:
            result[name] = value
    return result


def _check_contact_owner(scope: Scope, user_id: uuid.UUID) -> None:
    try:
        check_owner(scope, user_id)
    except InvalidReferenceError:
        raise InvalidReferenceError("contact_owner_not_member") from None


def _check_tag(session: Session, scope: Scope, tag_id: uuid.UUID | None) -> None:
    if tag_id is None:
        return
    found = session.execute(
        select(Tag.id)
        .where(Tag.tenant_id == scope.workspace, Tag.id == tag_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if found is None:
        raise InvalidReferenceError("tag_not_found")


def _check_rules(row: Form) -> None:
    """What every saved form must satisfy, and a published one too."""
    refusal = rules.consent_refusal(row.fields, row.consent_text)
    if refusal is None and row.status == "published":
        refusal = rules.publish_refusal(row.fields)
    if refusal is not None:
        raise FormRuleError(refusal)


# --- Members: reads --------------------------------------------------------------------


def list_forms(scope: Scope) -> list[Item]:
    """Every form of the workspace (at most `MAX_FORMS`), last changed first."""
    with tenant_session_scope(scope.workspace) as session:
        rows = list(
            session.execute(
                select(Form)
                .where(Form.tenant_id == scope.workspace)
                .order_by(Form.updated_at.desc(), Form.id.desc())
                .limit(MAX_FORMS)
            ).scalars()
        )
        tags = _tag_names(session, scope.workspace, {r.tag_id for r in rows if r.tag_id})
        return [_item(row, tags) for row in rows]


def get(scope: Scope, form_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        row = _load(session, scope, form_id, lock=False)
        tags = _tag_names(session, scope.workspace, {row.tag_id} if row.tag_id else set())
        return _item(row, tags)


@dataclass(frozen=True)
class SubmissionQuery:
    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[Item]
    next_cursor: str | None
    total: int
    total_capped: bool


def submissions(scope: Scope, form_id: uuid.UUID, query: SubmissionQuery) -> Page:
    """A form's submissions, newest first, with the contact each one created
    or matched. Raises `paging.InvalidCursor` for another form's cursor."""
    filters = paging.filter_hash({"form": str(form_id)})
    after = (
        paging.decode(query.cursor, "form_submission", "created_at", "desc", filters)
        if query.cursor
        else None
    )
    keys = [
        _OrderKey(FormSubmission.created_at, FormSubmission.created_at, "created_at"),
        _OrderKey(FormSubmission.id, FormSubmission.id, "id"),
    ]
    with tenant_session_scope(scope.workspace) as session:
        _load(session, scope, form_id, lock=False)
        conditions = [
            FormSubmission.tenant_id == scope.workspace,
            FormSubmission.form_id == form_id,
        ]
        counted = session.execute(
            select(FormSubmission.id).where(*conditions).limit(TOTAL_CAP + 1)
        ).all()
        statement = select(FormSubmission).where(*conditions)
        if after is not None:
            statement = statement.where(_after(keys, after, ascending=False))
        rows = list(
            session.execute(
                statement.order_by(
                    FormSubmission.created_at.desc(), FormSubmission.id.desc()
                ).limit(query.limit + 1)
            ).scalars()
        )
        more = len(rows) > query.limit
        rows = rows[: query.limit]
        contact_ids = {row.contact_id for row in rows if row.contact_id}
        names: dict[uuid.UUID, dict[str, Any]] = {}
        if contact_ids:
            for record_id, first, last, archived in session.execute(
                select(
                    Contact.id, Contact.first_name, Contact.last_name, Contact.archived_at
                ).where(Contact.tenant_id == scope.workspace, Contact.id.in_(contact_ids))
            ):
                names[record_id] = {
                    "id": record_id,
                    "name": " ".join(part for part in (first, last) if part),
                    "archived": archived is not None,
                }
        items = [
            {
                "id": row.id,
                "answers": row.answers,
                "outcome": row.outcome,
                "consent": row.consent,
                "created_at": row.created_at,
                "contact_id": row.contact_id,
                "contact": names.get(row.contact_id) if row.contact_id else None,
            }
            for row in rows
        ]
        last_key = (rows[-1].created_at, rows[-1].id) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode("form_submission", "created_at", "desc", filters, last_key)
    return Page(
        items=items,
        next_cursor=next_cursor,
        total=min(len(counted), TOTAL_CAP),
        total_capped=len(counted) > TOTAL_CAP,
    )


def consent_of_contact(scope: Scope, contact_id: uuid.UUID) -> list[Item]:
    """A contact's consent records, newest first (at most 100): given on a
    form, recorded or withdrawn by a member (decision P7-B 3). Another
    workspace's contact, or an unknown one, is `RecordNotFoundError`."""
    with tenant_session_scope(scope.workspace) as session:
        found = session.execute(
            select(Contact.id).where(Contact.tenant_id == scope.workspace, Contact.id == contact_id)
        ).scalar_one_or_none()
        if found is None:
            raise RecordNotFoundError
        rows = session.execute(
            select(ConsentRecord, Form.name)
            .outerjoin(
                Form,
                (Form.tenant_id == ConsentRecord.tenant_id) & (Form.id == ConsentRecord.form_id),
            )
            .where(
                ConsentRecord.tenant_id == scope.workspace, ConsentRecord.contact_id == contact_id
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(100)
        ).all()
        return [
            {
                "id": record.id,
                "channel": record.channel,
                "status": record.status,
                "method": record.method,
                "wording": record.wording,
                "form_id": record.form_id,
                "form_name": form_name,
                "recorded_by_user_id": record.recorded_by_user_id,
                "recorded_at": record.recorded_at,
            }
            for record, form_name in rows
        ]


# --- Members: writes -------------------------------------------------------------------


def create(
    scope: Scope, values: Mapping[str, Any], *, idempotency_key: str | None = None
) -> tuple[Item, bool]:
    """A new draft form; returns it and whether this was an idempotent replay
    (the key is scoped to the workspace and the acting member). The contact
    owner defaults to the creator."""
    given = _normalised(values)
    given.setdefault("thank_you", rules.DEFAULT_THANK_YOU)
    given.setdefault("consent_text", None)
    given.setdefault("tag_id", None)
    owner = given.get("contact_owner_user_id") or scope.actor
    given["contact_owner_user_id"] = owner
    _check_contact_owner(scope, owner)
    form_id = uuid.uuid4()
    public_key = secrets.token_urlsafe(16)

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        count = len(
            session.execute(
                select(Form.id).where(Form.tenant_id == scope.workspace).limit(MAX_FORMS)
            ).all()
        )
        if count >= MAX_FORMS:
            raise FormLimitError
        _check_tag(session, scope, given["tag_id"])
        now = _now()
        row = Form(
            id=form_id,
            tenant_id=scope.workspace,
            name=given["name"],
            status="draft",
            public_key=public_key,
            fields=given["fields"],
            tag_id=given["tag_id"],
            thank_you=given["thank_you"],
            consent_text=given["consent_text"],
            contact_owner_user_id=owner,
            submission_count=0,
            last_submission_at=None,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        _check_rules(row)
        session.add(row)
        session.flush()
        _form_audit(session, scope, "created", form_id)
        return {"id": str(form_id)}

    replay = False
    if idempotency_key is None:
        result = _transaction(scope.workspace, business)
    else:
        fingerprint = {
            name: None if given.get(name) is None else str(given[name])
            for name in FIELDS
            if name != "status"
        }
        try:
            replay, result = run_idempotent(
                scope.workspace,
                f"{RESOURCE}.create:{scope.actor}",
                idempotency_key,
                fingerprint,
                business,
            )
        except (TenantClosedError, TenantNotFoundError):
            raise RecordNotFoundError from None
        except IntegrityError:
            raise ConstraintViolationError from None
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
    return get(scope, uuid.UUID(str(result["id"]))), replay


def update(
    scope: Scope, form_id: uuid.UUID, changes: Mapping[str, Any], *, expected_version: int
) -> Item:
    """Apply `changes` if the form is still at `expected_version`. Publishing
    and unpublishing are a change of `status`; the audit entry says which.
    A change that alters nothing is a no-op."""
    given = _normalised(changes)
    if given.get("contact_owner_user_id") is not None:
        _check_contact_owner(scope, given["contact_owner_user_id"])

    def apply(session: Session) -> None:
        row = _load(session, scope, form_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if "tag_id" in given and given["tag_id"] != row.tag_id:
            _check_tag(session, scope, given["tag_id"])
        changed = sorted(name for name, value in given.items() if getattr(row, name) != value)
        if not changed:
            return
        before = row.status
        for name in changed:
            setattr(row, name, given[name])
        if row.status == "published" and "contact_owner_user_id" not in given:
            _check_contact_owner(scope, row.contact_owner_user_id)
        _check_rules(row)
        row.version += 1
        row.updated_at = _now()
        row.updated_by_user_id = scope.actor
        session.flush()
        other = [name for name in changed if name != "status"]
        if other:
            _form_audit(session, scope, "updated", form_id, fields=other)
        if row.status != before:
            verb = "published" if row.status == "published" else "unpublished"
            _form_audit(session, scope, verb, form_id)

    _transaction(scope.workspace, apply)
    return get(scope, form_id)


def remove(scope: Scope, form_id: uuid.UUID) -> None:
    """Delete a form and its submissions; contacts and consent records stay
    (P7-A 9)."""

    def apply(session: Session) -> None:
        row = _load(session, scope, form_id, lock=True)
        session.delete(row)
        session.flush()
        _form_audit(session, scope, "deleted", form_id)

    _transaction(scope.workspace, apply)


# --- Public ----------------------------------------------------------------------------


def _published(session: Session, workspace: uuid.UUID, key: str, *, lock: bool) -> Form:
    query = select(Form).where(
        Form.tenant_id == workspace, Form.public_key == key, Form.status == "published"
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise FormNotFoundError
    return row


def _accessible(status: str) -> bool:
    return TenantStatus(status) not in PRINCIPAL_INACCESSIBLE_STATUSES


def public_form(workspace: uuid.UUID, key: str) -> Item:
    """What the hosted page shows: the form's name, fields, consent wording
    and thank-you message, and nothing about the workspace."""
    try:
        tenant = require_open_tenant(workspace)
    except (TenantClosedError, TenantNotFoundError):
        raise FormNotFoundError from None
    if not _accessible(tenant.status):
        raise FormNotFoundError
    with tenant_session_scope(workspace) as session:
        row = _published(session, workspace, key, lock=False)
        return {
            "name": row.name,
            "fields": [
                {name: field[name] for name in ("key", "type", "label", "required", "options")}
                for field in row.fields
            ],
            "consent_text": row.consent_text,
            "thank_you": row.thank_you,
        }


@dataclass(frozen=True)
class Submission:
    answers: Mapping[str, object]
    consent: bool


def _match(session: Session, workspace: uuid.UUID, email: str | None) -> Contact | None:
    if email is None:
        return None
    return session.execute(
        select(Contact)
        .where(
            Contact.tenant_id == workspace,
            Contact.archived_at.is_(None),
            Contact.email == email,
        )
        .with_for_update()
    ).scalar_one_or_none()


def _add_tag(session: Session, scope: Scope, contact: Contact, tag_id: uuid.UUID) -> bool:
    """Tag a matched contact, unless it has the tag or is at the limit."""
    current = set(
        session.execute(
            select(ContactTag.tag_id).where(
                ContactTag.tenant_id == scope.workspace, ContactTag.contact_id == contact.id
            )
        ).scalars()
    )
    if tag_id in current or len(current) >= MAX_RECORD_TAGS:
        return False
    session.add(
        ContactTag(
            tenant_id=scope.workspace,
            contact_id=contact.id,
            tag_id=tag_id,
            created_by_user_id=scope.actor,
            created_at=_now(),
        )
    )
    return True


def _active_member(workspace: uuid.UUID, user_id: uuid.UUID) -> bool:
    membership = get_membership(workspace, user_id)
    return membership is not None and membership.status == _ACTIVE


def _gate(session: Session, workspace: uuid.UUID) -> None:
    """The workspace exists, is open and is not suspended."""
    try:
        tenant = lock_open_tenant(session, workspace)
    except (TenantClosedError, TenantNotFoundError):
        raise FormNotFoundError from None
    if not _accessible(tenant.status):
        raise FormNotFoundError


@dataclass(frozen=True)
class _Accepted:
    """A submission whose answers passed the form's checks."""

    scope: Scope
    key: str
    fields: list[dict[str, Any]]
    answers: dict[str, Any]
    consent: bool
    owned: bool


def _create_contact(session: Session, accepted: _Accepted, form: Form) -> uuid.UUID:
    scope = accepted.scope
    contact_id = uuid.uuid4()
    insert_record(
        session,
        CONTACT,
        scope,
        {
            **rules.contact_values(accepted.fields, accepted.answers),
            "lifecycle_stage": "lead",
            "source": "form",
            "owner_user_id": scope.actor if accepted.owned else None,
        },
        record_id=contact_id,
        form_id=form.id,
    )
    if form.tag_id is not None:
        session.add(
            ContactTag(
                tenant_id=scope.workspace,
                contact_id=contact_id,
                tag_id=form.tag_id,
                created_by_user_id=scope.actor,
                created_at=_now(),
            )
        )
    return contact_id


def _tag_matched(session: Session, scope: Scope, contact: Contact, form: Form) -> None:
    """The only change a submission makes to a matched contact (P7-A 6)."""
    if form.tag_id is None or not _add_tag(session, scope, contact, form.tag_id):
        return
    _touch(contact, scope)
    session.flush()
    session.add(history_entry(CONTACT, scope, contact.id, "updated", fields=["tags"]))
    metadata = {"fields": ["tags"], "form_id": str(form.id)}
    _audit(session, CONTACT, scope, _Event("updated", contact.id, metadata))


def _record(session: Session, accepted: _Accepted) -> dict[str, object]:
    """The submission's whole effect, in the idempotency transaction."""
    workspace = accepted.scope.workspace
    _gate(session, workspace)
    form = _published(session, workspace, accepted.key, lock=True)
    if form.fields != accepted.fields:
        # Changed since the answers were checked: the visitor retries.
        raise TransactionConflictError
    email = rules.contact_values(accepted.fields, accepted.answers).get("email")
    contact = _match(session, workspace, email)
    if contact is None:
        contact_id, outcome = _create_contact(session, accepted, form), "created"
    else:
        _tag_matched(session, accepted.scope, contact, form)
        contact_id, outcome = contact.id, "matched"
    consent = accepted.consent and email is not None and form.consent_text is not None
    now = _now()
    submission_id = uuid.uuid4()
    session.add(
        FormSubmission(
            id=submission_id,
            tenant_id=workspace,
            form_id=form.id,
            contact_id=contact_id,
            answers=accepted.answers,
            outcome=outcome,
            consent=consent,
            created_at=now,
        )
    )
    session.flush()
    if consent and form.consent_text is not None:
        session.add(
            ConsentRecord(
                id=uuid.uuid4(),
                tenant_id=workspace,
                contact_id=contact_id,
                channel=_CONSENT_CHANNEL,
                status="granted",
                method="web_form",
                wording=form.consent_text,
                form_id=form.id,
                submission_id=submission_id,
                recorded_at=now,
            )
        )
    form.submission_count += 1
    form.last_submission_at = now
    return {"id": str(submission_id)}


def submit(workspace: uuid.UUID, key: str, submission: Submission, *, idempotency_key: str) -> str:
    """Accept one submission of a published form; returns its thank-you
    message. The idempotency record keeps the submission ID only."""
    with tenant_session_scope(workspace) as session:
        _gate(session, workspace)
        form = _published(session, workspace, key, lock=False)
        form_id, fields, owner = form.id, form.fields, form.contact_owner_user_id
        thank_you = form.thank_you
    try:
        given = rules.answers(fields, submission.answers)
    except rules.InvalidAnswers as exc:
        raise AnswersError(exc.errors) from None
    accepted = _Accepted(
        scope=Scope(workspace=workspace, actor=owner),
        key=key,
        fields=fields,
        answers=given,
        consent=submission.consent,
        owned=_active_member(workspace, owner),
    )
    fingerprint = {"answers": str(sorted(given.items())), "consent": str(submission.consent)}
    # Two first submissions with one new email can race; the loser's unique
    # violation rolls everything back and the retry matches the winner.
    for attempt in (1, 2):
        try:
            run_idempotent(
                workspace,
                f"{RESOURCE}.submit:{form_id}",
                idempotency_key,
                fingerprint,
                lambda session: _record(session, accepted),
            )
        except (TenantClosedError, TenantNotFoundError):
            raise FormNotFoundError from None
        except (DuplicateRecordError, IntegrityError):
            if attempt == 2:
                raise TransactionConflictError from None
            continue
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
        return thank_you
    raise TransactionConflictError
