"""`Cache-Control: no-store` on authenticated API and sign-in responses.

Member lists, contact lists and `/access` carry personal data. Without a
cache directive a browser's back/forward cache or an intermediary could
show them again after sign-out on a shared machine. The frontend's static
files (`crm_app.api.spa`) set their own caching and are left alone, as is
any response that already chose a `Cache-Control`.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

PRIVATE_PREFIXES = ("/v1/", "/auth/")
_HEADER = b"cache-control"


class NoStoreMiddleware:
    """Adds `Cache-Control: no-store` to responses under `PRIVATE_PREFIXES`
    that set none themselves. A plain ASGI middleware, so streaming and
    background tasks are untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith(PRIVATE_PREFIXES):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == _HEADER for name, _ in headers):
                    headers.append((_HEADER, b"no-store"))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
