"""The post-logout redirect URIs `deploy/local/configure-zitadel.py` writes
to the local OIDC application (decision P2-G.1). Only the pure list logic is
tested; nothing is contacted."""

from __future__ import annotations

import importlib.util
from types import ModuleType

from tests.support import REPO_ROOT


def _script() -> ModuleType:
    path = REPO_ROOT / "deploy" / "local" / "configure-zitadel.py"
    spec = importlib.util.spec_from_file_location("configure_zitadel", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORIGIN = "http://localhost:8000"


def test_adds_auth_login_and_drops_the_obsolete_app_entry() -> None:
    uris = _script().post_logout_uris([f"{ORIGIN}/app"], ORIGIN + "/")
    assert uris == [f"{ORIGIN}/auth/login"]


def test_keeps_unrelated_entries_in_order() -> None:
    current = [
        "https://staging.example/app",
        f"{ORIGIN}/app/",
        f"{ORIGIN}/app",
        "http://localhost:3000/signed-out",
    ]
    uris = _script().post_logout_uris(current, ORIGIN)
    # Only exactly <origin>/app goes; look-alikes and other origins stay.
    assert uris == [
        "https://staging.example/app",
        f"{ORIGIN}/app/",
        "http://localhost:3000/signed-out",
        f"{ORIGIN}/auth/login",
    ]


def test_is_idempotent() -> None:
    script = _script()
    once = script.post_logout_uris([f"{ORIGIN}/app", "https://other.example/x"], ORIGIN)
    assert script.post_logout_uris(once, ORIGIN) == once
    assert once.count(f"{ORIGIN}/auth/login") == 1


def test_from_empty() -> None:
    assert _script().post_logout_uris([], ORIGIN) == [f"{ORIGIN}/auth/login"]
