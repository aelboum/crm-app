"""Serves the built frontend from the API's own origin (decision P-6.1).

The single-page app lives under `/app`. Serving it from the same origin as
the API is what the SaaS-OS session cookie and its same-origin check for
cookie-authenticated changes expect (`PUBLIC_APP_ORIGIN`, SaaS-OS ADR-0024
and ADR-0044); there is no second web server and no CORS.

Every route here is public: the files are the same for every visitor and
contain no data. Data is fetched by the app from the authenticated `/v1`
and `/auth` routes. A Starlette `Mount` is not used because SaaS-OS's
startup check refuses any route without a declared policy.

The build output is read from `CRM_APP_FRONTEND_DIST` (default
`frontend/dist`, relative to the working directory). Without a build the
routes answer 404; the API itself is unaffected.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from saas_os.api.route_policy import public_route

DIST_ENV = "CRM_APP_FRONTEND_DIST"
DEFAULT_DIST = "frontend/dist"
BASE = "/app"

# The app loads only its own files and talks only to its own origin.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
# Vite fingerprints everything under assets/, so those never change.
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"

_static = Depends(public_route("static frontend files; identical for every visitor, no data"))

router = APIRouter(include_in_schema=False)


def frontend_root() -> Path:
    return Path(os.environ.get(DIST_ENV, DEFAULT_DIST)).resolve()


def _file(path: Path, cache: str) -> FileResponse:
    return FileResponse(path, headers={**SECURITY_HEADERS, "Cache-Control": cache})


def resolve(root: Path, requested: str) -> tuple[Path, str] | None:
    """The file to send for `/app/<requested>` and its cache policy, or
    `None` for 404. Paths outside `root` and hidden files are never served;
    a path without a file extension is an app route and gets `index.html`."""
    index = root / "index.html"
    if not index.is_file():
        return None
    if not requested:
        return index, REVALIDATE
    if any(part.startswith(".") for part in Path(requested).parts):
        return None
    candidate = (root / requested).resolve()
    if not candidate.is_relative_to(root):
        return None
    if candidate.is_file() and candidate != index:
        inside = candidate.relative_to(root).parts
        return candidate, IMMUTABLE if inside[0] == "assets" else REVALIDATE
    return None if Path(requested).suffix else (index, REVALIDATE)


@router.get("/", dependencies=[_static])
def root_redirect() -> RedirectResponse:
    return RedirectResponse(BASE, status_code=307)


@router.get(BASE, dependencies=[_static])
@router.get(BASE + "/{requested:path}", dependencies=[_static])
def frontend(requested: str = "") -> FileResponse:
    found = resolve(frontend_root(), requested)
    if found is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return _file(*found)
