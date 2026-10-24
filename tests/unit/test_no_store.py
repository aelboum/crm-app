"""Authenticated API and sign-in responses are never cached
(`crm_app.api.headers.NoStoreMiddleware`; Phase 2 security review L3)."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from crm_app.api.headers import NoStoreMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(NoStoreMiddleware)

    @app.get("/v1/workspaces/x")
    def api() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/auth/me")
    def me() -> dict[str, str]:
        return {"user": "u"}

    @app.get("/v1/own")
    def own() -> Response:
        return Response("x", headers={"Cache-Control": "private, max-age=5"})

    @app.get("/app/index.html")
    def page() -> Response:
        return Response("<!doctype html>", headers={"Cache-Control": "no-cache"})

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_api_and_auth_responses_are_not_stored() -> None:
    client = _client()
    assert client.get("/v1/workspaces/x").headers["cache-control"] == "no-store"
    assert client.get("/auth/me").headers["cache-control"] == "no-store"
    # Errors too: a 404 body can name a workspace.
    assert client.get("/v1/missing").headers["cache-control"] == "no-store"


def test_a_response_that_chose_its_caching_and_other_paths_are_left_alone() -> None:
    client = _client()
    assert client.get("/v1/own").headers["cache-control"] == "private, max-age=5"
    assert client.get("/app/index.html").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/healthz").headers
