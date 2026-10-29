"""Form routes (decision P7-A, slice 7A).

Members, under `/v1/workspaces/{tenant_id}`:

    GET    /forms                          crm_app.form:read
    POST   /forms                          crm_app.form:manage
    GET    /forms/{form_id}                crm_app.form:read
    PATCH  /forms/{form_id}                crm_app.form:manage
    DELETE /forms/{form_id}                crm_app.form:manage
    GET    /forms/{form_id}/submissions    crm_app.form:read
    GET    /contacts/{record_id}/consent   crm_app.contact:read

The path's `tenant_id` is only the request; handlers use `context.tenant_id`
alone. `PATCH` needs `If-Match` (publishing is a change of `status`); `POST`
accepts an `Idempotency-Key`.

Public, for the hosted form page (SaaS-OS `public_route`, P7-A 5):

    GET    /v1/public/forms/{workspace_id}/{key}
    POST   /v1/public/forms/{workspace_id}/{key}

Both are limited per client address, and the submission also per form,
with the SaaS-OS limiter, which fails closed (503). An unknown workspace or
key, a draft form and a closed or suspended workspace are the same 404. The
submission needs an `Idempotency-Key`, is read only after the limits and at
most 16 KiB, and a filled honeypot field is answered like a success without
storing anything. Errors name field keys and rules, never answers.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import (
    idempotency_key_invalid,
    invalid_request,
    rate_limited,
    route_not_found,
    service_unavailable,
)
from saas_os.api.route_policy import public_route
from saas_os.core.idempotency import (
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyReusedError,
    validate_idempotency_key,
)
from saas_os.infra.ratelimit import (
    RateLimitBackendError,
    RateLimitExceededError,
    enforce_rate_limit,
    get_ratelimit_config,
)

from crm_app import forms
from crm_app.api.inputs import json_body
from crm_app.api.records import DEFAULT_LIMIT, MAX_LIMIT, IdempotencyKey, IfMatch, _http, _version
from crm_app.domains import forms as rules
from crm_app.domains import paging
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["forms"])
public_router = APIRouter(prefix="/v1/public/forms", tags=["public forms"])

RESOURCE = "crm_app.form"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Manage = Annotated[RequestContext, Depends(require_permission(RESOURCE, "manage"))]
ReadContacts = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]

FieldType = Literal["text", "email", "phone", "textarea", "select", "date", "checkbox"]
Target = Literal["first_name", "last_name", "email", "phone", "job_title", "city"]
Status = Literal["draft", "published"]
# Raw lengths are bounded generously; the service applies the real limits
# after trimming, without echoing the text.
_RAW = 4


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=40)
    type: FieldType
    label: str = Field(max_length=_RAW * rules.LABEL_MAX)
    required: StrictBool = False
    target: Target | None = None
    options: list[Annotated[str, Field(max_length=_RAW * rules.OPTION_MAX)]] | None = Field(
        default=None, max_length=rules.OPTIONS_MAX
    )


Fields = Annotated[list[FieldIn], Field(min_length=1, max_length=rules.FIELDS_MAX)]
Message = Annotated[str, Field(max_length=_RAW * rules.MESSAGE_MAX)]


class FormIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=_RAW * rules.NAME_MAX)
    fields: Fields
    tag_id: uuid.UUID | None = None
    thank_you: Message | None = None
    consent_text: Message | None = None
    contact_owner_user_id: uuid.UUID | None = None


class FormPatch(BaseModel):
    """Only the fields sent change; `null` clears the tag or the consent
    wording."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=_RAW * rules.NAME_MAX)
    fields: Fields | None = None
    tag_id: uuid.UUID | None = None
    thank_you: Message | None = None
    consent_text: Message | None = None
    contact_owner_user_id: uuid.UUID | None = None
    status: Status | None = None


class FieldOut(BaseModel):
    key: str
    type: FieldType
    label: str
    required: bool
    target: Target | None
    options: list[str] | None


class TagRef(BaseModel):
    id: uuid.UUID
    name: str


class FormOut(BaseModel):
    id: uuid.UUID
    name: str
    status: Status
    public_key: str
    fields: list[FieldOut]
    tag_id: uuid.UUID | None
    tag: TagRef | None
    thank_you: str
    consent_text: str | None
    contact_owner_user_id: uuid.UUID
    submission_count: int
    last_submission_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int


class FormList(BaseModel):
    items: list[FormOut]


class ContactRef(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class SubmissionOut(BaseModel):
    id: uuid.UUID
    answers: dict[str, str | bool]
    outcome: Literal["created", "matched"]
    consent: bool
    created_at: datetime
    contact_id: uuid.UUID | None
    contact: ContactRef | None


class SubmissionPage(BaseModel):
    items: list[SubmissionOut]
    next_cursor: str | None
    total: int
    total_capped: bool


class SubmissionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


class ConsentOut(BaseModel):
    """One consent record (P7-A 7, P7-B 3): given on a form, or recorded or
    withdrawn by a member. Wording is the exact text agreed to, or a
    withdrawal's optional note."""

    id: uuid.UUID
    channel: Literal["email"]
    status: Literal["granted", "withdrawn"]
    method: Literal["web_form", "manual"]
    wording: str | None
    form_id: uuid.UUID | None
    form_name: str | None
    recorded_by_user_id: uuid.UUID | None
    recorded_at: datetime


class ConsentList(BaseModel):
    items: list[ConsentOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, forms.FormRuleError) and exc.index is not None:
        return HTTPException(422, detail={"code": exc.code, "field": exc.index})
    if isinstance(exc, forms.AnswersError):
        return HTTPException(422, detail={"code": exc.code, "fields": exc.errors})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_FORMS = "/{tenant_id}/forms"
_FORM = f"{_FORMS}/{{form_id}}"


@router.get(_FORMS, response_model=FormList, name="list_forms")
def list_forms(context: Read) -> Any:
    return {"items": forms.list_forms(_scope(context))}


@router.post(_FORMS, status_code=201, response_model=FormOut, name="create_form")
def create_form(
    body: FormIn, context: Manage, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    values = body.model_dump(exclude_none=True)
    values["fields"] = [field.model_dump() for field in body.fields]
    try:
        item, replay = forms.create(_scope(context), values, idempotency_key=idempotency_key)
    except RecordError as exc:
        raise _refusal(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, item)


@router.get(_FORM, response_model=FormOut, name="get_form")
def get_form(form_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, forms.get(_scope(context), form_id))
    except RecordError as exc:
        raise _refusal(exc) from None


@router.patch(_FORM, response_model=FormOut, name="update_form")
def update_form(
    form_id: uuid.UUID,
    body: FormPatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    for name in ("name", "fields", "thank_you", "contact_owner_user_id", "status"):
        if name in changes and changes[name] is None:
            raise HTTPException(422, detail={"code": f"{name}_required"})
    if body.fields is not None:
        changes["fields"] = [field.model_dump() for field in body.fields]
    try:
        item = forms.update(_scope(context), form_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_FORM, status_code=204, name="delete_form")
def delete_form(form_id: uuid.UUID, context: Manage) -> Response:
    try:
        forms.remove(_scope(context), form_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


@router.get(f"{_FORM}/submissions", response_model=SubmissionPage, name="list_form_submissions")
def list_submissions(
    form_id: uuid.UUID, context: Read, params: Annotated[SubmissionParams, Query()]
) -> Any:
    query = forms.SubmissionQuery(limit=params.limit, cursor=params.cursor)
    try:
        return forms.submissions(_scope(context), form_id, query)
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None
    except RecordError as exc:
        raise _refusal(exc) from None


@router.get(
    "/{tenant_id}/contacts/{record_id}/consent",
    response_model=ConsentList,
    name="list_contact_consent",
)
def list_contact_consent(record_id: uuid.UUID, context: ReadContacts) -> Any:
    try:
        return {"items": forms.consent_of_contact(_scope(context), record_id)}
    except RecordError as exc:
        raise _refusal(exc) from None


# --- Public ----------------------------------------------------------------------------

_KEY = re.compile(r"[A-Za-z0-9_-]{22}")
_MAX_BODY_BYTES = 16 * 1024
_RETRY_AFTER_SECONDS = 5
_IDEMPOTENCY_KEY = "Idempotency-Key"


class PublicField(BaseModel):
    key: str
    type: FieldType
    label: str
    required: bool
    options: list[str] | None


class PublicForm(BaseModel):
    name: str
    fields: list[PublicField]
    consent_text: str | None
    thank_you: str


class SubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[
        Annotated[str, Field(max_length=40)],
        Annotated[StrictStr, Field(max_length=_RAW * rules.TEXTAREA_MAX)] | StrictBool | None,
    ] = Field(max_length=rules.FIELDS_MAX)
    consent: StrictBool = False
    # The honeypot (P7-A 5): the hosted page leaves it empty and hidden.
    website: str = Field(default="", max_length=200)


class Accepted(BaseModel):
    thank_you: str


async def _limited(key: str) -> None:
    try:
        await enforce_rate_limit(key, config=get_ratelimit_config())
    except RateLimitExceededError as exc:
        raise rate_limited(exc.retry_after_seconds) from None
    except RateLimitBackendError:
        raise service_unavailable(_RETRY_AFTER_SECONDS) from None


async def _address_limit(request: Request) -> None:
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"form:client:{address}")


def _known_key(key: str) -> None:
    """A malformed key is the same 404 as an unknown one, before any lookup."""
    if not _KEY.fullmatch(key):
        raise route_not_found()


def _idempotency_key(request: Request) -> str:
    key = request.headers.get(_IDEMPOTENCY_KEY)
    if key is None:
        raise invalid_request("idempotency_key_required")
    try:
        validate_idempotency_key(key)
    except IdempotencyKeyInvalidError:
        raise idempotency_key_invalid() from None
    return key


async def _submission(request: Request) -> SubmissionIn:
    payload = await json_body(request, _MAX_BODY_BYTES)
    try:
        return SubmissionIn.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_input=False)) from None


_public = Depends(
    public_route("a published form's page and its submission: anyone with the link may submit")
)
_PUBLIC = "/{workspace_id}/{key}"


@public_router.get(_PUBLIC, response_model=PublicForm, dependencies=[_public], name="public_form")
async def read_public_form(workspace_id: uuid.UUID, key: str, request: Request) -> Any:
    _known_key(key)
    await _address_limit(request)
    try:
        return await run_in_threadpool(forms.public_form, workspace_id, key)
    except forms.FormNotFoundError:
        raise route_not_found() from None


@public_router.post(
    _PUBLIC,
    status_code=201,
    response_model=Accepted,
    dependencies=[_public],
    name="submit_public_form",
    openapi_extra={
        "parameters": [
            {
                "name": _IDEMPOTENCY_KEY,
                "in": "header",
                "required": True,
                "schema": {"type": "string", "maxLength": 255},
            }
        ],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": SubmissionIn.model_json_schema()}},
        },
    },
)
async def submit_public_form(workspace_id: uuid.UUID, key: str, request: Request) -> Any:
    _known_key(key)
    await _address_limit(request)
    await _limited(f"form:submit:{workspace_id}:{key}")
    idempotency_key = _idempotency_key(request)
    body = await _submission(request)
    try:
        if body.website.strip():
            # A bot filled the hidden field: the same answer, nothing stored.
            form = await run_in_threadpool(forms.public_form, workspace_id, key)
            return {"thank_you": form["thank_you"]}
        submission = forms.Submission(answers=body.answers, consent=body.consent)
        thank_you = await run_in_threadpool(
            lambda: forms.submit(workspace_id, key, submission, idempotency_key=idempotency_key)
        )
    except forms.FormNotFoundError:
        raise route_not_found() from None
    except RecordError as exc:
        raise _refusal(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    return {"thank_you": thank_you}
