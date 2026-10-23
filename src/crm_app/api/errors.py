"""Request validation errors without the submitted values.

FastAPI's default 422 body echoes each rejected `input` (and `ctx`, `url`).
For contact and company records that is personal data, so the product
answers with the location, message and type of each error only. Messages
come from pydantic or from `crm_app.domains.records`, which names rules,
never values. The shape is otherwise FastAPI's: `{"detail": [...]}`.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in errors
    ]
    return JSONResponse(status_code=422, content={"detail": detail})
