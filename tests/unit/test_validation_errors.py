"""422 bodies never echo submitted values (`crm_app.api.errors`).

The handler drops `input`, `ctx` and `url`, keeps messages that name a
rule (the product's validators, missing and unknown fields, fixed choices)
and replaces every other message, because pydantic's parsing messages can
quote part of the value ("found `x` at 1").
"""

from __future__ import annotations

import asyncio
import json

from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from crm_app.api.errors import validation_error

MARKER = "leak-check-55"


def _body(errors: list[dict[str, object]]) -> dict[str, object]:
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    response = asyncio.run(validation_error(request, RequestValidationError(errors)))
    assert response.status_code == 422
    return json.loads(bytes(response.body))


def test_parsing_messages_are_replaced_and_values_never_returned() -> None:
    body = _body(
        [
            {
                "type": "uuid_parsing",
                "loc": ("body", "company_id"),
                "msg": f"Input should be a valid UUID, invalid character: found `{MARKER}`",
                "input": MARKER,
                "ctx": {"error": MARKER},
            }
        ]
    )
    assert body == {
        "detail": [{"loc": ["body", "company_id"], "msg": "Invalid value.", "type": "uuid_parsing"}]
    }
    assert MARKER not in json.dumps(body)


def test_rule_messages_are_kept() -> None:
    body = _body(
        [
            {
                "type": "value_error",
                "loc": ("body", "email"),
                "msg": "Value error, must be an email address",
                "input": MARKER,
            },
            {
                "type": "missing",
                "loc": ("body", "first_name"),
                "msg": "Field required",
                "input": {},
            },
            {
                "type": "extra_forbidden",
                "loc": ("body", "tenant_id"),
                "msg": "Extra inputs are not permitted",
                "input": MARKER,
            },
        ]
    )
    detail = body["detail"]
    assert isinstance(detail, list)
    assert [error["msg"] for error in detail] == [
        "Value error, must be an email address",
        "Field required",
        "Extra inputs are not permitted",
    ]
    assert MARKER not in json.dumps(body)
