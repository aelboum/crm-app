"""Request inputs shared by several route modules (security review 13-H1).

`json_body` reads a JSON body that must stay small: a declared or actual
size above the limit is refused as soon as it is seen, without buffering
the rest, and a body nested too deeply for the parser is the same 422 as
one that is not JSON, never a server error. Validation errors carry no
input.

`Instant` is an aware time between 1900 and 2999. Python cannot convert or
add to times at the edges of its range, so an extreme time sent by a
client is refused as a validation error instead of failing later.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator, AwareDatetime
from saas_os.api.errors import invalid_request

_NOT_JSON = [{"loc": ("body",), "msg": "The body is not JSON.", "type": "json_invalid"}]


async def raw_body(request: Request, max_bytes: int) -> bytes:
    """The body's bytes, refused as `body_too_large` past `max_bytes`, by its
    declared length or while streaming."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise invalid_request("body_too_large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise invalid_request("body_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_json(body: bytes) -> Any:
    """JSON, or a 422 `json_invalid` (deep nesting included)."""
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        raise RequestValidationError(_NOT_JSON) from None


async def json_body(request: Request, max_bytes: int) -> Any:
    return parse_json(await raw_body(request, max_bytes))


_EARLIEST = datetime(1900, 1, 1, tzinfo=UTC)
_END = datetime(3000, 1, 1, tzinfo=UTC)


def _in_range(value: datetime) -> datetime:
    try:
        moment = value.astimezone(UTC)
    except OverflowError:
        raise ValueError("the time must be between 1900 and 2999") from None
    if not _EARLIEST <= moment < _END:
        raise ValueError("the time must be between 1900 and 2999")
    return value


Instant = Annotated[AwareDatetime, AfterValidator(_in_range)]
