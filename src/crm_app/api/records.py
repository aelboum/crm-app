"""Contact and company routes (`PHASE3-PLAN.md` §19, slice 3A).

    /v1/workspaces/{tenant_id}/contacts[/{record_id}[/archive|/restore]]
    /v1/workspaces/{tenant_id}/companies[/{record_id}[/archive|/restore]]

Each route declares exactly one `require_permission` from the existing
catalogue (decision Q6): read for every role; create and update (which
covers archive and restore, P3-A) for Owner, Admin and Member; permanent
delete for Owner and Admin. The path's `tenant_id` is only the request:
SaaS-OS admits it for an active member of an open workspace and otherwise
answers with one indistinguishable 404. Handlers then use
`context.tenant_id` alone (§19.3); a record ID from another workspace gives
the same 404 as an unknown one.

Request bodies forbid unknown fields, so `tenant_id`, `version`,
`archived_at` and the audit columns cannot be set. `PATCH` needs
`If-Match: <version>`; `POST` accepts an `Idempotency-Key`.

No `from __future__ import annotations` here: the routes are built per kind
in `_add_routes`, and FastAPI must resolve their annotations from the
enclosing function, which only works when annotations are evaluated.
"""

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import get_idempotency_key, require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError

from crm_app import records
from crm_app.domains import paging
from crm_app.domains import records as values
from crm_app.records import COMPANY, CONTACT, Kind, RecordError, Scope

router = APIRouter(prefix="/v1/workspaces")

IdempotencyKey = Annotated[str | None, Depends(get_idempotency_key)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_IF_MATCH = re.compile(r'(?:W/)?"?([0-9]{1,9})"?')
# A ceiling before normalisation, so oversized input is refused early.
_RAW_MAX = 4096


def _apply(rule: Callable[[Any], Any], value: Any) -> Any:
    if isinstance(value, str) and len(value) > _RAW_MAX:
        raise values.InvalidValue(f"must be at most {_RAW_MAX} characters")
    return rule(value)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Contacts ---------------------------------------------------------------------

_CONTACT_RULES: dict[str, Callable[[Any], Any]] = {
    "first_name": lambda v: values.text(v, values.NAME_MAX, required=True),
    "last_name": lambda v: values.text(v, values.NAME_MAX),
    "email": values.email,
    "phone": values.phone,
    "job_title": lambda v: values.text(v, values.JOB_TITLE_MAX),
    "city": lambda v: values.text(v, values.CITY_MAX),
    "lifecycle_stage": values.stage,
    "source": values.user_source,
}
_CONTACT_REQUIRED = {"first_name", "lifecycle_stage", "source"}


class ContactCreate(_Strict):
    first_name: str
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    city: str | None = None
    lifecycle_stage: str = "lead"
    source: str = "manual"
    company_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None

    @field_validator(*_CONTACT_RULES, mode="before")
    @classmethod
    def _normalise(cls, value: Any, info: ValidationInfo) -> Any:
        return _apply(_CONTACT_RULES[info.field_name or ""], value)

    @model_validator(mode="after")
    def _email_or_phone(self) -> Self:
        if self.email is None and self.phone is None:
            raise values.InvalidValue("an email or a phone number is required")
        return self


class ContactUpdate(_Strict):
    """Fields left out are unchanged; `null` clears an optional field."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    city: str | None = None
    lifecycle_stage: str | None = None
    source: str | None = None
    company_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None

    @field_validator(*_CONTACT_RULES, mode="before")
    @classmethod
    def _normalise(cls, value: Any, info: ValidationInfo) -> Any:
        name = info.field_name or ""
        if value is None and name in _CONTACT_REQUIRED:
            raise values.InvalidValue("cannot be cleared")
        return _apply(_CONTACT_RULES[name], value)


class CompanySummary(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class _RecordOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int
    archived_at: datetime | None


class ContactOut(_RecordOut):
    first_name: str
    last_name: str | None
    email: str | None
    phone: str | None
    job_title: str | None
    city: str | None
    lifecycle_stage: str
    source: str
    company_id: uuid.UUID | None
    company: CompanySummary | None


# --- Companies --------------------------------------------------------------------

_COMPANY_RULES: dict[str, Callable[[Any], Any]] = {
    "name": lambda v: values.text(v, values.NAME_MAX, required=True),
    "domain": values.domain,
    "website": values.website,
    "phone": values.phone,
    "industry": lambda v: values.text(v, values.INDUSTRY_MAX),
    "city": lambda v: values.text(v, values.CITY_MAX),
    "country_code": values.country_code,
}


class CompanyCreate(_Strict):
    """`domain` is derived from `website` when it is not given."""

    name: str
    domain: str | None = None
    website: str | None = None
    phone: str | None = None
    industry: str | None = None
    city: str | None = None
    country_code: str | None = None
    owner_user_id: uuid.UUID | None = None

    @field_validator(*_COMPANY_RULES, mode="before")
    @classmethod
    def _normalise(cls, value: Any, info: ValidationInfo) -> Any:
        return _apply(_COMPANY_RULES[info.field_name or ""], value)

    @model_validator(mode="after")
    def _derive_domain(self) -> Self:
        if self.domain is None:
            self.domain = values.domain_from_website(self.website)
        return self


class CompanyUpdate(_Strict):
    """Fields left out are unchanged; `null` clears an optional field. The
    domain is not re-derived when only the website changes."""

    name: str | None = None
    domain: str | None = None
    website: str | None = None
    phone: str | None = None
    industry: str | None = None
    city: str | None = None
    country_code: str | None = None
    owner_user_id: uuid.UUID | None = None

    @field_validator(*_COMPANY_RULES, mode="before")
    @classmethod
    def _normalise(cls, value: Any, info: ValidationInfo) -> Any:
        name = info.field_name or ""
        if value is None and name == "name":
            raise values.InvalidValue("cannot be cleared")
        return _apply(_COMPANY_RULES[name], value)


class CompanyOut(_RecordOut):
    name: str
    domain: str | None
    website: str | None
    phone: str | None
    industry: str | None
    city: str | None
    country_code: str | None


# --- Shared handling --------------------------------------------------------------


def _http(exc: RecordError) -> HTTPException:
    detail: dict[str, object] = {"code": exc.code}
    if isinstance(exc, records.DuplicateRecordError) and exc.existing_id is not None:
        detail["existing_id"] = str(exc.existing_id)
    if isinstance(exc, records.StaleVersionError):
        detail["current_version"] = exc.current
    return HTTPException(status_code=exc.status, detail=detail)


def _scope(context: RequestContext) -> Scope:
    """The workspace and actor SaaS-OS validated for this request (§19.3)."""
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _version(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail={"code": "version_required"})
    match = _IF_MATCH.fullmatch(if_match.strip())
    if match is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_if_match"})
    return int(match.group(1))


def _etag(response: Response, record: dict[str, Any]) -> None:
    response.headers["ETag"] = f'"{record["version"]}"'


def _add_routes(
    kind: Kind,
    path: str,
    create_model: type[BaseModel],
    update_model: type[BaseModel],
    out: type[BaseModel],
) -> None:
    resource = kind.resource
    read = Annotated[RequestContext, Depends(require_permission(resource, "read"))]
    create = Annotated[RequestContext, Depends(require_permission(resource, "create"))]
    change = Annotated[RequestContext, Depends(require_permission(resource, "update"))]
    remove = Annotated[RequestContext, Depends(require_permission(resource, "delete"))]
    collection = f"/{{tenant_id}}/{path}"
    item = f"{collection}/{{record_id}}"
    tags: list[str | Any] = [path]

    @router.post(
        collection, status_code=201, response_model=out, name=f"create_{kind.name}", tags=tags
    )
    def create_record(
        body: create_model,  # pyright: ignore[reportInvalidTypeForm]
        context: create,  # pyright: ignore[reportInvalidTypeForm]
        response: Response,
        idempotency_key: IdempotencyKey,
    ) -> Any:
        try:
            record, replay = records.create(
                kind,
                _scope(context),
                body.model_dump(),
                idempotency_key=idempotency_key,
            )
        except RecordError as exc:
            raise _http(exc) from None
        except IdempotencyKeyReusedError:
            raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
        except IdempotencyInProgressError:
            raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
        if replay:
            response.headers["Idempotent-Replayed"] = "true"
        _etag(response, record)
        return record

    @router.get(item, response_model=out, name=f"get_{kind.name}", tags=tags)
    def get_record(
        record_id: uuid.UUID,
        context: read,  # pyright: ignore[reportInvalidTypeForm]
        response: Response,
    ) -> Any:
        try:
            record = records.get(kind, _scope(context), record_id)
        except RecordError as exc:
            raise _http(exc) from None
        _etag(response, record)
        return record

    @router.patch(item, response_model=out, name=f"update_{kind.name}", tags=tags)
    def update_record(
        record_id: uuid.UUID,
        body: update_model,  # pyright: ignore[reportInvalidTypeForm]
        context: change,  # pyright: ignore[reportInvalidTypeForm]
        response: Response,
        if_match: IfMatch = None,
    ) -> Any:
        expected = _version(if_match)
        changes = body.model_dump(include=body.model_fields_set)
        try:
            record = records.update(
                kind,
                _scope(context),
                record_id,
                changes,
                expected_version=expected,
            )
        except RecordError as exc:
            raise _http(exc) from None
        _etag(response, record)
        return record

    def archive_route(*, archived: bool) -> None:
        verb = "archive" if archived else "restore"

        @router.post(f"{item}/{verb}", response_model=out, name=f"{verb}_{kind.name}", tags=tags)
        def set_archived(
            record_id: uuid.UUID,
            context: change,  # pyright: ignore[reportInvalidTypeForm]
            response: Response,
        ) -> Any:
            try:
                record = records.set_archived(kind, _scope(context), record_id, archived=archived)
            except RecordError as exc:
                raise _http(exc) from None
            _etag(response, record)
            return record

    archive_route(archived=True)
    archive_route(archived=False)

    @router.delete(item, status_code=204, name=f"delete_{kind.name}", tags=tags)
    def delete_record(
        record_id: uuid.UUID,
        context: remove,  # pyright: ignore[reportInvalidTypeForm]
    ) -> Response:
        try:
            records.remove(kind, _scope(context), record_id)
        except RecordError as exc:
            raise _http(exc) from None
        return Response(status_code=204)


_add_routes(CONTACT, "contacts", ContactCreate, ContactUpdate, ContactOut)
_add_routes(COMPANY, "companies", CompanyCreate, CompanyUpdate, CompanyOut)


# --- Lists (PHASE3-PLAN.md §19.5) ----------------------------------------------------

_MAX_VALUES = 20  # per repeatable filter

Order = Literal["name", "created_at", "updated_at"]
Direction = Literal["asc", "desc"]
Archived = Literal["false", "true", "all"]
Stage = Literal["lead", "prospect", "customer", "inactive"]


class _ListParams(_Strict):
    """Query parameters shared by both lists; unknown parameters are refused."""

    q: str | None = Field(default=None, max_length=100, pattern=r"^[^\x00]*$")
    owner: list[str] = Field(default_factory=list, max_length=_MAX_VALUES)
    archived: Archived = "false"
    sort: Order = "name"
    direction: Direction = "asc"
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


class ContactListParams(_ListParams):
    lifecycle_stage: list[Stage] = Field(default_factory=list, max_length=_MAX_VALUES)
    company_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)


class CompanyListParams(_ListParams):
    pass


class ContactPage(BaseModel):
    items: list[ContactOut]
    next_cursor: str | None
    total: int
    total_capped: bool


class CompanyPage(BaseModel):
    items: list[CompanyOut]
    next_cursor: str | None
    total: int
    total_capped: bool


def _owners(raw: list[str], context: RequestContext) -> tuple[uuid.UUID, ...]:
    """User IDs, where `me` is the caller."""
    owners: list[uuid.UUID] = []
    for value in raw:
        if value == "me":
            owners.append(context.actor_id)
            continue
        try:
            owners.append(uuid.UUID(value))
        except ValueError:
            raise HTTPException(422, detail={"code": "invalid_owner_filter"}) from None
    return tuple(owners)


def _query(params: _ListParams, context: RequestContext, **extra: Any) -> records.ListQuery:
    q = params.q.strip() if params.q else ""
    return records.ListQuery(
        order=params.sort,
        direction=params.direction,
        limit=params.limit,
        cursor=params.cursor,
        q=q or None,
        archived=params.archived,
        owners=_owners(params.owner, context),
        **extra,
    )


def _page(kind: Kind, context: RequestContext, query: records.ListQuery) -> records.Page:
    try:
        return records.list_records(kind, _scope(context), query)
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None


@router.get("/{tenant_id}/contacts", response_model=ContactPage, tags=["contacts"])
def list_contacts(
    context: Annotated[RequestContext, Depends(require_permission(CONTACT.resource, "read"))],
    params: Annotated[ContactListParams, Query()],
) -> Any:
    query = _query(
        params,
        context,
        stages=tuple(params.lifecycle_stage),
        companies=tuple(params.company_id),
    )
    return _page(CONTACT, context, query)


@router.get("/{tenant_id}/companies", response_model=CompanyPage, tags=["companies"])
def list_companies(
    context: Annotated[RequestContext, Depends(require_permission(COMPANY.resource, "read"))],
    params: Annotated[CompanyListParams, Query()],
) -> Any:
    return _page(COMPANY, context, _query(params, context))
