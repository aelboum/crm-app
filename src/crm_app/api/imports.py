"""CSV import routes (decision P3-F, `PHASE3-PLAN.md` §9).

    POST /v1/workspaces/{tenant_id}/imports?entity=&column=     crm_app.crm_data:import
    GET  /v1/workspaces/{tenant_id}/imports                      crm_app.crm_data:import
    GET  /v1/workspaces/{tenant_id}/imports/{import_id}          crm_app.crm_data:import
    GET  /v1/workspaces/{tenant_id}/imports/{import_id}/errors.csv

Owner and Admin only (decision P3-F 1), each route with exactly one
`require_permission`. The path's `tenant_id` is only the request; handlers
use `context.tenant_id` alone, and another workspace's import is the same
404 as an unknown one.

The upload is the CSV file itself as the request body (`text/csv`): read in
chunks and refused past 5 MB, never stored. `column` maps a field to a
column position (`email:2`), repeatable; without it the mapping is
proposed from the header. Ten previews per user per window on SaaS-OS's
limiter, which counts in fixed windows and refuses when it fails (P3-F 6).
"""

import csv
import io
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import rate_limited, service_unavailable
from saas_os.infra.ratelimit import (
    RateLimitBackendError,
    RateLimitExceededError,
    enforce_rate_limit,
    get_ratelimit_config,
)

from crm_app import imports
from crm_app.api.records import _http
from crm_app.domains import imports as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["imports"])

Import = Annotated[RequestContext, Depends(require_permission("crm_app.crm_data", "import"))]

PREVIEWS_PER_WINDOW = 10
PREVIEW_WINDOW_SECONDS = 3600
_LIMITER_RETRY_SECONDS = 5
_CSV_TYPES = ("text/csv", "text/plain", "application/csv", "application/vnd.ms-excel")


class PreviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: Literal["contact", "company"]
    # `field:position`, for example `email:2`; at most one per field.
    column: list[str] = Field(default_factory=list, max_length=20)


class RowError(BaseModel):
    row: int
    field: str | None
    code: str


class ImportSummary(BaseModel):
    id: uuid.UUID
    entity: Literal["contact", "company"]
    status: str
    mapping: dict[str, int]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    created_rows: int
    skipped_rows: int
    failed_rows: int
    cancel_requested: bool
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    # The first refused rows: row number, field and code, never a value.
    errors: list[RowError]


class ImportPreview(BaseModel):
    summary: ImportSummary
    # The file's column names, to check the mapping against.
    header: list[str]
    # The first valid rows as they would be stored.
    sample: list[dict[str, Any]]


class ImportList(BaseModel):
    items: list[ImportSummary]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _mapping(entity: str, columns: list[str]) -> dict[str, int] | None:
    if not columns:
        return None
    mapping: dict[str, int] = {}
    for item in columns:
        name, _, position = item.partition(":")
        valid = name in rules.FIELDS[entity] and position.isdigit() and len(position) <= 3
        if not valid or name in mapping:
            raise HTTPException(422, detail={"code": "invalid_mapping"})
        mapping[name] = int(position)
    return mapping


async def _count_preview(context: RequestContext) -> None:
    config = replace(
        get_ratelimit_config(),
        requests_per_window=PREVIEWS_PER_WINDOW,
        window_seconds=PREVIEW_WINDOW_SECONDS,
    )
    try:
        await enforce_rate_limit(f"crm-import-preview:{context.actor_id}", config=config)
    except RateLimitExceededError as exc:
        raise rate_limited(exc.retry_after_seconds) from None
    except RateLimitBackendError:
        raise service_unavailable(_LIMITER_RETRY_SECONDS) from None


async def _body(request: Request) -> bytes:
    """The uploaded file, refused as soon as it passes the size limit."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in _CSV_TYPES:
        raise HTTPException(415, detail={"code": "csv_required"})
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > rules.MAX_BYTES:
            raise HTTPException(
                413, detail={"code": "file_too_large", "max_bytes": rules.MAX_BYTES}
            )
        chunks.append(chunk)
    return b"".join(chunks)


_IMPORTS = "/{tenant_id}/imports"
_IMPORT = f"{_IMPORTS}/{{import_id}}"


@router.post(
    _IMPORTS,
    status_code=201,
    response_model=ImportPreview,
    name="preview_import",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
    responses={
        413: {"description": "The file is larger than 5 MB."},
        415: {"description": "The body is not CSV."},
        429: {"description": "Preview limit reached; see Retry-After."},
    },
)
async def preview_import(
    request: Request, context: Import, params: Annotated[PreviewParams, Query()]
) -> Any:
    """Read, validate and stage a CSV file of contacts or companies. Nothing
    is imported until the import is committed."""
    mapping = _mapping(params.entity, params.column)
    await _count_preview(context)
    body = await _body(request)
    try:
        result = await run_in_threadpool(
            imports.preview, _scope(context), params.entity, body, mapping
        )
    except RecordError as exc:
        raise _http(exc) from None
    return {"summary": result.summary, "header": result.header, "sample": result.sample}


@router.get(_IMPORTS, response_model=ImportList, name="list_imports")
def list_imports(context: Import) -> Any:
    return {"items": imports.recent(_scope(context))}


@router.get(_IMPORT, response_model=ImportSummary, name="get_import")
def get_import(import_id: uuid.UUID, context: Import) -> Any:
    try:
        return imports.get(_scope(context), import_id)
    except RecordError as exc:
        raise _http(exc) from None


@router.get(
    f"{_IMPORT}/errors.csv",
    response_class=Response,
    name="import_errors",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
def import_errors(import_id: uuid.UUID, context: Import) -> Response:
    """Every refused row as row number, field and code; never a value."""
    try:
        rows = imports.error_rows(_scope(context), import_id)
    except RecordError as exc:
        raise _http(exc) from None
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(("row", "field", "code"))
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="import-{import_id}-errors.csv"',
            "Cache-Control": "no-store",
        },
    )
