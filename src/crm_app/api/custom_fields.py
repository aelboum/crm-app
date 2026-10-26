"""Custom field definition routes (decision P3-D, `PHASE3-PLAN.md` §6.1).

    GET  /v1/workspaces/{tenant_id}/custom-fields[?entity=]         crm_app.contact:read
    POST /v1/workspaces/{tenant_id}/custom-fields                    crm_app.workspace:update
    PATCH /v1/workspaces/{tenant_id}/custom-fields/{field_id}        crm_app.workspace:update
    POST /v1/workspaces/{tenant_id}/custom-fields/{field_id}/archive crm_app.workspace:update
    POST /v1/workspaces/{tenant_id}/custom-fields/{field_id}/restore crm_app.workspace:update

Each declares exactly one `require_permission` from the existing catalogue:
every role reads; definitions are workspace configuration, changed by
Owner and Admin (P3-D 4). The path's `tenant_id` is only the request;
handlers use `context.tenant_id` alone, and an ID from another workspace is
the same 404 as an unknown one.

Bodies forbid unknown fields and are normalised once
(`crm_app.domains.custom_fields`); `PATCH` needs `If-Match: <version>`.
A key and a type are set on creation only. `POST` takes no
`Idempotency-Key`: keys are unique, so a repeated request is refused with
`duplicate_custom_field_key`.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import custom_fields
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import custom_fields as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["custom-fields"])

Entity = Literal["contact", "company"]
FieldType = Literal["text", "number", "date", "boolean", "select"]
# Ceilings before trimming, so oversized input is refused early.
_RAW_LABEL = 4 * rules.LABEL_MAX
_RAW_OPTION = 4 * rules.OPTION_MAX

Read = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]
Configure = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "update"))]

Option = Annotated[str, Field(max_length=_RAW_OPTION)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DefinitionCreate(_Strict):
    entity: Entity
    key: str = Field(max_length=40)
    label: str = Field(max_length=_RAW_LABEL)
    field_type: FieldType
    options: list[Option] | None = Field(default=None, max_length=rules.OPTIONS_MAX)
    position: int = Field(default=0, ge=0, le=10_000)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return rules.key(value)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return rules.label(value)

    @field_validator("options")
    @classmethod
    def _options(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else rules.options(value)


class DefinitionUpdate(_Strict):
    label: str | None = Field(default=None, max_length=_RAW_LABEL)
    options: list[Option] | None = Field(default=None, max_length=rules.OPTIONS_MAX)
    position: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("cannot be null")
        return rules.label(value)

    @field_validator("options")
    @classmethod
    def _options(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("cannot be null")
        return rules.options(value)

    @field_validator("position")
    @classmethod
    def _position(cls, value: int | None) -> int:
        if value is None:
            raise ValueError("cannot be null")
        return value


class DefinitionOut(BaseModel):
    id: uuid.UUID
    entity: Entity
    key: str
    label: str
    field_type: FieldType
    options: list[str] | None
    position: int
    version: int
    archived: bool
    created_at: datetime
    updated_at: datetime


class DefinitionList(BaseModel):
    items: list[DefinitionOut]
    max_active: int


class DefinitionListParams(_Strict):
    entity: Entity | None = None


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _etag(response: Response, definition: dict[str, Any]) -> None:
    response.headers["ETag"] = f'"{definition["version"]}"'


_FIELDS = "/{tenant_id}/custom-fields"
_FIELD = f"{_FIELDS}/{{field_id}}"


@router.get(_FIELDS, response_model=DefinitionList, name="list_custom_fields")
def list_custom_fields(context: Read, params: Annotated[DefinitionListParams, Query()]) -> Any:
    return {
        "items": custom_fields.list_definitions(_scope(context), params.entity),
        "max_active": rules.MAX_ACTIVE,
    }


@router.post(_FIELDS, status_code=201, response_model=DefinitionOut, name="create_custom_field")
def create_custom_field(body: DefinitionCreate, context: Configure, response: Response) -> Any:
    try:
        definition = custom_fields.create_definition(
            _scope(context),
            entity=body.entity,
            key=body.key,
            label=body.label,
            field_type=body.field_type,
            options=body.options,
            position=body.position,
        )
    except RecordError as exc:
        raise _http(exc) from None
    _etag(response, definition)
    return definition


@router.patch(_FIELD, response_model=DefinitionOut, name="update_custom_field")
def update_custom_field(
    field_id: uuid.UUID,
    body: DefinitionUpdate,
    context: Configure,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        definition = custom_fields.update_definition(
            _scope(context),
            field_id,
            body.model_dump(include=body.model_fields_set),
            expected_version=expected,
        )
    except RecordError as exc:
        raise _http(exc) from None
    _etag(response, definition)
    return definition


def _archive_route(*, archived: bool) -> None:
    verb = "archive" if archived else "restore"

    @router.post(f"{_FIELD}/{verb}", response_model=DefinitionOut, name=f"{verb}_custom_field")
    def set_archived(field_id: uuid.UUID, context: Configure, response: Response) -> Any:
        try:
            definition = custom_fields.set_definition_archived(
                _scope(context), field_id, archived=archived
            )
        except RecordError as exc:
            raise _http(exc) from None
        _etag(response, definition)
        return definition


_archive_route(archived=True)
_archive_route(archived=False)
